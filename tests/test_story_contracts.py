import copy
import json
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
from test_story_planner import story,global_plan,CONCEPT,events,timeline


class StoryContracts(unittest.TestCase):
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
