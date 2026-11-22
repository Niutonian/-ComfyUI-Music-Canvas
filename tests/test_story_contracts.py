import copy
import json
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
from test_story_planner import story,global_plan,CONCEPT,events,timeline


class StoryContracts(unittest.TestCase):
    def test_short_camera_labels_work_and_bookkeeping_is_owned_by_code(self):
        slots=timeline.timeline_plan(30,15); world=global_plan(2)
        for camera in ('low-angle','medium','Performance-led'):
            value=events(slots,2)
            for scene in value:
                scene['camera_intent']=camera
                for key in ('index','is_resolution','next_obligation'):scene.pop(key)
            canonical=story.prepare_events({'scenes':value},slots,world)['scenes']
            story.link_scene_obligations(canonical,world)
            self.assertEqual(canonical[0]['index'],0)
            self.assertFalse(canonical[0]['is_resolution'])
            self.assertEqual(canonical[0]['next_obligation'],canonical[1]['event'])
            self.assertTrue(canonical[1]['next_obligation'].startswith('Resolved final image:'))
        schema=story.event_schema(world,False)['properties']['scenes']['items']
        self.assertFalse({'index','is_resolution','next_obligation'} & set(schema['required']))

    def test_incomplete_sentences_are_rewritten_not_silently_clipped(self):
        for value in ('The light flares while','The limbs settle into the','The column glows,'):
            with self.subTest(value=value),self.assertRaisesRegex(ValueError,'mid-sentence'):
                story.description(value,'event')
        self.assertEqual(story.description('The column glows.','event'),'The column glows.')
        self.assertGreater(story.EVENT_SCHEMA['properties']['event']['maxLength'],240)

    def test_initial_locked_fact_cannot_make_the_ending_unreachable(self):
        world=global_plan(2); world.pop('scene_count')
        world['initial_facts'].append(dict(entity='boat',attribute='arrived',value='false',locked=True))
        with self.assertRaisesRegex(ValueError,'locked fact'):story.prepare_global(world,CONCEPT)

    def test_conflicting_global_ending_is_repaired_before_scenes(self):
        world=global_plan(2); world.pop('scene_count')
        world['treatment']['climax']='The loop breaks into separate rings.'
        world['destination']='The loop remains unbroken.'
        world['final_facts']=[dict(entity='boat',attribute='loop_state',value='unbroken',locked=True)]
        stages=[]
        class Session:
            recovery_round=0
            def request(self,stage,system,user,schema,prepare):
                stages.append(stage)
                if stage.startswith('world_review'):
                    bad=user['world_contract']['final_facts'][0]['value']=='unbroken'
                    value=dict(accepted=not bad,issues=[dict(index=0,code='contract_mismatch',feedback='Reconcile the broken climax with the unbroken ending.')] if bad else [])
                else:
                    value=copy.deepcopy(world)
                    value['destination']='The loop rests as separate rings.'
                    value['final_facts'][0]['value']='separated'
                    value={k:v for k,v in value.items() if k in schema['properties']}
                return prepare(value)
        fixed=story.reconcile_world(Session(),world,CONCEPT,CONCEPT,{},['boat'])
        self.assertEqual(fixed['final_facts'][0]['value'],'separated')
        self.assertEqual(stages,['world_review_0','world_revision_0','world_review_1'])

    def test_unresolved_global_contradiction_still_fails_closed(self):
        class Session:
            recovery_round=0
            def request(self,stage,system,user,schema,prepare):
                if stage.startswith('world_review'):
                    return prepare(dict(accepted=False,issues=[dict(index=0,code='continuity',feedback='The ending contradicts the visible climax.')]))
                world=global_plan(2); world.pop('scene_count')
                return prepare({k:v for k,v in world.items() if k in schema['properties']})
        with self.assertRaisesRegex(story.PlanningRepairError,'World contract could not resolve'):
            story.reconcile_world(Session(),global_plan(2),CONCEPT,CONCEPT,{},['boat'])

    def test_earlier_edit_repairs_only_invalid_downstream_facts(self):
        slots=timeline.timeline_plan(60,15); world=global_plan(4)
        scenes=story.prepare_events({'scenes':events(slots,4)},slots,world)['scenes']
        scenes[1]['state_updates'].append(dict(entity='boat',attribute='passage_2',value='false',locked=True))
        stages=[]
        class Session:
            recovery_round=0
            def request(self,stage,system,user,schema,prepare):
                stages.append(stage)
                value={'scenes':events(user['slots'],4)}
                value['scenes'][0]['state_updates'][0]['attribute']='new_channel'
                return prepare(value)
        fixed,repairs=story.rebuild_after_edits(Session(),world,slots,scenes,0)
        self.assertEqual(repairs,1)
        self.assertEqual(stages,['dependency_revision_0_2'])
        self.assertEqual(fixed[0],scenes[0])
        self.assertEqual(fixed[3]['opening_state'],fixed[2]['consequence'])
        story.prepare_events({'scenes':fixed},slots,world)

    def test_rejected_reviews_are_uncached_logged_and_retry_after_terminal_failure(self):
        from pathlib import Path
        with tempfile.TemporaryDirectory() as root:
            folders=types.SimpleNamespace(get_user_directory=lambda:root)
            mm=types.SimpleNamespace(throw_exception_if_processing_interrupted=lambda:None)
            calls=[]
            def api(url,endpoint,request,**kwargs):
                calls.append(copy.deepcopy(request))
                return {'message':{'content':json.dumps(dict(accepted=False,issues=[dict(index=0,code='continuity',feedback='The pose contradicts the visible action.')]))},'done_reason':'stop'}
            connection=dict(base_url='http://127.0.0.1:11434',model='local',device='CPU',context_length=8192)
            with patch.dict(sys.modules,{'folder_paths':folders,'comfy':types.ModuleType('comfy'),'comfy.model_management':mm}),patch.object(story.ollama,'api',side_effect=api):
                common={'version':story.VERSION}
                first=story.PlanningSession(connection,common,2048,42,.8)
                args=('outline_review_0',story.EDITOR_SYSTEM,{'task':'Check continuity'},story.REVIEW_SCHEMA,lambda v:story.validate_review(v,[0]))
                first.request(*args); first.request(*args)
                self.assertEqual(first.cache_hits,0)
                first.terminal(story.PlanningRepairError('Unresolved pose'))
                second=story.PlanningSession(connection,common,2048,42,.8)
                second.request(*args)
            self.assertEqual(len(calls),3)
            self.assertLessEqual(calls[0]['options']['temperature'],.15)
            self.assertNotEqual(calls[0]['options']['seed'],calls[2]['options']['seed'])
            attempts=list((Path(root)/'MusicCanvas/story_cache/failures/attempts').glob('*.json'))
            self.assertEqual(len(attempts),4)
            self.assertTrue(any(json.loads(path.read_text()).get('request') for path in attempts))

    def test_short_destination_is_expressed_using_its_existing_visible_goals(self):
        world=global_plan(2); world['destination']='Arrival'
        before=copy.deepcopy(world['final_facts'])
        text=story.event_schema(world,True)['properties']['scenes']['items']['properties']['consequence']['enum'][0]
        self.assertGreaterEqual(len(text.split()),3)
        self.assertIn('boat arrived',text)
        self.assertEqual(world['final_facts'],before)

    def test_conflicting_goals_are_rejected_before_the_outline(self):
        world=global_plan(2); world.pop('scene_count')
        world['final_facts']=[dict(entity='boat',attribute='pose',value=v,locked=True) for v in ('reaching','settled')]
        with self.assertRaisesRegex(ValueError,'Contradictory poses'):story.prepare_global(world,CONCEPT)

    def test_ordinary_pose_lock_is_normalized_but_milestone_locks_remain(self):
        world=global_plan(2); world.pop('scene_count')
        world['initial_facts']=[dict(entity='boat',attribute='pose',value='tilted',locked=True)]
        world=story.prepare_global(world,CONCEPT)
        self.assertFalse(world['initial_facts'][0]['locked'])
        self.assertTrue(story.transient_fact(dict(entity='boat',attribute='destroyed',value='true',locked=True))['locked'])

    def test_repairs_are_fresh_bounded_deterministic_and_success_is_cached(self):
        with tempfile.TemporaryDirectory() as root:
            folders=types.SimpleNamespace(get_user_directory=lambda:root)
            mm=types.SimpleNamespace(throw_exception_if_processing_interrupted=lambda:None)
            calls=[]
            def api(url,endpoint,request,**kwargs):
                calls.append(copy.deepcopy(request))
                return {'message':{'content':json.dumps({'valid':len(calls)==3})}}
            def prepare(value):
                if not value['valid']:raise ValueError('Scene leaves all object facts unchanged')
                return value
            connection=dict(base_url='http://127.0.0.1:11434',model='local',device='CPU',context_length=8192)
            with patch.dict(sys.modules,{'folder_paths':folders,'comfy':types.ModuleType('comfy'),'comfy.model_management':mm}),patch.object(story.ollama,'api',side_effect=api):
                session=story.PlanningSession(connection,{'version':story.VERSION},2048,42,.6)
                args=('repair_case',story.PLANNER_SYSTEM,{'task':'A new physical consequence'},story.object_schema({'valid':{'type':'boolean'}}),prepare)
                self.assertEqual(session.request(*args),{'valid':True})
                self.assertEqual(session.request(*args),{'valid':True})
            self.assertEqual(len(calls),3)
            self.assertEqual(len({r['options']['seed'] for r in calls}),3)
            self.assertLess(calls[1]['options']['temperature'],calls[0]['options']['temperature'])
            self.assertFalse(any(m['role']=='assistant' for m in calls[1]['messages']))
            self.assertEqual(session.cache_hits,1)

    def test_entity_registry_constrains_both_global_fact_lists(self):
        schema=story.global_schema(['figure','plant'])
        self.assertNotIn('chapters',schema['properties'])
        for key in ('initial_facts','final_facts'):
            self.assertEqual(schema['properties'][key]['items']['properties']['entity']['enum'],['figure','plant'])
        value=global_plan(); value.pop('scene_count'); value['initial_facts'][0]['entity']='posture'
        with self.assertRaisesRegex(ValueError,'declared entity'):story.prepare_global(value,CONCEPT)

    def test_final_schema_requires_every_exact_goal_without_duplicate_choice(self):
        world=global_plan(2)
        world['final_facts'].append(dict(entity='boat',attribute='sail',value='furled',locked=True))
        schema=story.event_schema(world,True)['properties']['scenes']['items']
        self.assertEqual(schema['properties']['state_updates']['enum'],[world['final_facts']])
        self.assertNotIn('enum',story.event_schema(world,False)['properties']['scenes']['items']['properties']['state_updates'])

    def test_wrong_chapter_count_stays_invalid(self):
        value=global_plan(2); value.pop('scene_count')
        with self.assertRaisesRegex(ValueError,'one distinct chapter'):
            story.prepare_global(value,CONCEPT,[dict(first_scene=i,last_scene=i) for i in range(3)])

    def test_noop_cannot_be_repaired_by_accepting_unchanged_metadata(self):
        slots=timeline.timeline_plan(45,15); world=global_plan(3)
        prior=story.prepare_events({'scenes':events(slots[:1],3)},slots[:1],world)['scenes']
        second=events(slots[1:2],3); second[0]['state_updates']=copy.deepcopy(prior[0]['state_updates'])
        with self.assertRaisesRegex(ValueError,'unchanged'):story.prepare_events({'scenes':second},slots[1:2],world,prior)


if __name__=='__main__':unittest.main()
