import copy
import importlib
import json
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
from test_ollama_timeline import timeline,scenes_for

story=importlib.import_module('timeline_test_pack.story_planner')


CONCEPT=dict(title='Paper Journey',subject='A paper boat on an indigo sea',environment='A layered paper sea',
             palette='Indigo and warm ochre',treatment='Tactile cut-paper stop motion',rationale='Quiet reflective texture')


def global_plan(count=4):
    value=dict(treatment={k:'A paper boat discovers a new coastline' for k in timeline.BIBLE_SCHEMA['properties']},
        opening_state='The paper boat is tied to the folded dock',destination='The boat reaches the hidden paper cove',entities=['boat'],
        initial_facts=[dict(entity='boat',attribute='departed',value='false',locked=False)],
        final_facts=[dict(entity='boat',attribute='arrived',value='true',locked=True)],
        chapters=[dict(first_scene=i,last_scene=i,development=f'Boat discovers passage number {i}',consequence=f'A new coastline opens at step {i}') for i in range(count)])
    value=story.prepare_global(value,CONCEPT); value['scene_count']=count
    return value


def events(slots,count=4):
    values=[dict(index=s['index'],event=f'The paper boat reveals new passage number {s["index"]}',
        consequence=f'The boat has completed passage number {s["index"]}',next_obligation='Enter the newly opened paper passage',
        camera_intent='Reveal the changed spatial relationship',is_resolution=s['index']==count-1,
        state_updates=[dict(entity='boat',attribute='departed' if s['index']==0 else f'passage_{s["index"]}',value='true',locked=True)]) for s in slots]
    for value in values:
        if value['is_resolution']: value['state_updates'].append(dict(entity='boat',attribute='arrived',value='true',locked=True))
    return values


class StoryPlanning(unittest.TestCase):
    def test_single_scene_repair_preserves_timing_and_requires_visible_ending(self):
        with tempfile.TemporaryDirectory() as root:
            folders=types.SimpleNamespace(get_user_directory=lambda:root)
            mm=types.SimpleNamespace(throw_exception_if_processing_interrupted=lambda:None)
            utils=types.SimpleNamespace(ProgressBar=lambda n:types.SimpleNamespace(update_absolute=lambda n:None))
            corrections=[]
            def api(url,endpoint,request,**kwargs):
                user=json.loads(request['messages'][1]['content'])
                if 'world_contract' in user:value=dict(accepted=True,issues=[])
                elif 'review_scenes' in user:
                    bad=user['review_scenes'][0]['event'].startswith('Only begins')
                    value=dict(accepted=not bad,issues=[dict(index=0,code='contract_mismatch',feedback='Complete the arrival in this scene, then show the resting boat.')] if bad else [])
                elif 'slots' in user:
                    value={'scenes':events(user['slots'],1)}
                    if 'replaced_scene_index' not in user:value['scenes'][0]['event']='Only begins sailing toward the final cove'
                    else:
                        corrections.append(user)
                        value['scenes'][0].update(event='The boat enters the hidden cove and comes to rest',consequence='The boat rests fully inside the hidden cove')
                else:
                    world=global_plan(1); world.pop('scene_count')
                    value={k:v for k,v in world.items() if k in request['format']['properties']}
                return {'message':{'content':json.dumps(value)},'done_reason':'stop'}
            connection=dict(base_url='http://127.0.0.1:11434',model='test',device='CPU',context_length=8192)
            with patch.dict(sys.modules,{'folder_paths':folders,'comfy':types.ModuleType('comfy'),'comfy.model_management':mm,'comfy.utils':utils}),patch.object(story.ollama,'models',return_value=[{'name':'test'}]),patch.object(story.ollama,'api',side_effect=api),patch.object(story.ollama,'release',return_value={'verified_absent':True}):
                result=story.MusicCanvasOllamaStoryPlanner().plan(connection,'{"summary":"Reflective music"}',json.dumps({'concept':CONCEPT}),15,15,False,.6,42,4096,0)
            self.assertEqual(len(json.loads(result[0])['scenes']),1)
            self.assertEqual(len(corrections),1)
            self.assertEqual(corrections[0]['required_visible_ending'],global_plan(1)['destination'])
            self.assertFalse({'setup','development','climax'} & set(corrections[0]['film']['treatment']))

    def test_locked_changes_cannot_be_undone_or_replayed_as_progress(self):
        world=global_plan(); slots=timeline.timeline_plan(60,15)
        first=story.prepare_events({'scenes':events(slots[:1])},slots[:1],world)['scenes']
        second=events(slots[1:2]); second[0]['state_updates'][0].update(attribute='departed',value='false')
        with self.assertRaisesRegex(ValueError,'locked fact'): story.prepare_events({'scenes':second},slots[1:2],world,first)
        second[0]['state_updates'][0]['value']='true'
        with self.assertRaisesRegex(ValueError,'unchanged'): story.prepare_events({'scenes':second},slots[1:2],world,first)

    def test_openings_are_carried_and_final_payoff_is_reserved(self):
        world=global_plan(); slots=timeline.timeline_plan(60,15); value=events(slots)
        canonical=story.prepare_events({'scenes':value},slots,world)['scenes']
        self.assertEqual(canonical[0]['opening_state'],world['opening_state'])
        self.assertEqual(canonical[1]['opening_state'],canonical[0]['consequence'])
        value[0]['is_resolution']=True
        corrected=story.prepare_events({'scenes':value},slots,world)
        self.assertFalse(corrected['scenes'][0]['is_resolution'])
        self.assertTrue(corrected['scenes'][-1]['is_resolution'])
        self.assertEqual(world['treatment']['visual_style'],CONCEPT['treatment'])
        self.assertEqual(world['treatment']['palette'],CONCEPT['palette'])

    def test_final_scene_must_achieve_ending_and_early_arrival_is_rejected(self):
        world=global_plan(); slots=timeline.timeline_plan(60,15)
        missing=events(slots); missing[-1]['state_updates']=missing[-1]['state_updates'][:1]
        with self.assertRaisesRegex(ValueError,'must visibly achieve'): story.prepare_events({'scenes':missing},slots,world)
        early=events(slots); early[0]['state_updates'].append(dict(entity='boat',attribute='arrived',value='true',locked=True))
        with self.assertRaisesRegex(ValueError,'before the ending'): story.prepare_events({'scenes':early},slots,world)

    def test_wrong_story_timing_and_concept_are_rejected(self):
        slots=timeline.timeline_plan(60,15); world=global_plan()
        canonical=story.prepare_events({'scenes':events(slots)},slots,world)['scenes']
        value=dict(version=story.VERSION,**world,scenes=[{**s,**v} for s,v in zip(slots,canonical)],editor_status='accepted',
                   source_analysis_id='audio-a',concept_key=story.identity(CONCEPT))
        story.validate_story_plan(value,slots,{'analysis_id':'audio-a'},{'concept':CONCEPT})
        directed={'concept':CONCEPT,'directing_approach':{'name':'Character journey'},'music_direction':'Quiet flowing gestures'}
        with self.assertRaisesRegex(ValueError,'different directing approaches'):story.validate_story_plan(value,slots,brief=directed)
        value['directing_approach']=directed['directing_approach']
        with self.assertRaisesRegex(ValueError,'different visual music direction'):story.validate_story_plan(value,slots,brief=directed)
        value['music_direction']=directed['music_direction']
        story.validate_story_plan(value,slots,brief=directed)
        with self.assertRaisesRegex(ValueError,'different audio'): story.validate_story_plan(value,slots,{'analysis_id':'audio-b'})
        with self.assertRaisesRegex(ValueError,'different selected concepts'): story.validate_story_plan(value,slots,brief={'concept':{}})
        value['scenes'][1]['frames']=1
        with self.assertRaisesRegex(ValueError,'timing'): story.validate_story_plan(value,slots)

    def test_editor_revises_only_rejected_scene_and_all_stages_are_cached(self):
        with tempfile.TemporaryDirectory() as temp:
            folders=types.ModuleType('folder_paths'); folders.get_user_directory=lambda:temp
            mm=types.ModuleType('comfy.model_management'); mm.unload_all_models=lambda:None
            mm.soft_empty_cache=lambda:None; mm.throw_exception_if_processing_interrupted=lambda:None
            utils=types.ModuleType('comfy.utils'); utils.ProgressBar=lambda count:types.SimpleNamespace(update_absolute=lambda n:None)
            comfy=types.ModuleType('comfy'); comfy.__path__=[]; comfy.model_management=mm
            calls=[]; released=[]
            def api(url,endpoint,request,**kwargs):
                calls.append(request); user=json.loads(request['messages'][1]['content'])
                if 'world_contract' in user:value=dict(accepted=True,issues=[])
                elif 'review_scenes' in user:
                    bad=any(s['index']==1 and 'repeats departure' in s['event'] for s in user['review_scenes'])
                    value=dict(accepted=not bad,issues=[dict(index=1,code='repetition',feedback='The boat already departed. Reveal a new passage instead.')] if bad else [])
                elif 'slots' in user:
                    value={'scenes':events(user['slots'])}
                    if 'replaced_scene_index' not in user:
                        for s in value['scenes']:
                            if s['index']==1: s['event']='The boat repeats departure with a different camera angle'
                else:
                    value=global_plan(); value.pop('scene_count')
                    keys=set(request['format']['properties'])
                    if 'inspired_action' in keys:value['inspired_action']='The boat rocks through a steady double accent, timed like a marching cadence.'
                    value={k:v for k,v in value.items() if k in keys}
                return {'message':{'content':json.dumps(value)},'done_reason':'stop'}
            conn=dict(base_url='http://127.0.0.1:11434',model='local:9b',device='GPU',context_length=8192)
            inspiration,=story.MusicCanvasStoryHelper().provide('  Red Army 1940 March  ')
            options=dict(connection=conn,analysis_json='{"summary":"Soft ambient textures","analysis_id":"audio-a"}',
                base_brief_json=json.dumps({'concept':CONCEPT}),total_seconds=60.,segment_seconds=15.,lyrics_approved=False,
                temperature=.6,seed=42,max_tokens=4096,regenerate=0,batch_size=2,editor_revisions=2,story_inspiration=inspiration)
            with patch.dict(sys.modules,{'folder_paths':folders,'comfy':comfy,'comfy.model_management':mm,'comfy.utils':utils}),patch.object(story.ollama,'models',return_value=[dict(name='local:9b',digest='revision')]),patch.object(story.ollama,'api',side_effect=api),patch.object(story.ollama,'release',side_effect=lambda *args:released.append(args) or {'verified_absent':True}):
                first=story.MusicCanvasOllamaStoryPlanner().plan(**options)
                count=len(calls); second=story.MusicCanvasOllamaStoryPlanner().plan(**options)
            value=json.loads(first[0]); self.assertNotIn('repeats departure',value['scenes'][1]['event'])
            self.assertEqual(value['story_inspiration']['reference'],'Red Army 1940 March')
            self.assertIn('marching cadence',value['inspired_action'])
            world_request=next(json.loads(r['messages'][1]['content']) for r in calls if 'initial_facts' in r['format']['properties'])
            self.assertEqual(world_request['chosen_concept']['story_inspiration'],value['story_inspiration'])
            self.assertNotIn(inspiration,json.dumps(world_request['musical_evidence']))
            self.assertEqual(json.loads(first[2])['editor_revisions'],1)
            self.assertEqual(json.loads(second[2])['requests'],0); self.assertEqual(len(calls),count)
            self.assertEqual(first[:2],second[:2]); self.assertEqual(len(released),2)
            revision_calls=[json.loads(r['messages'][1]['content']) for r in calls if 'replaced_scene_index' in json.loads(r['messages'][1]['content'])]
            self.assertEqual([u['slots'][0]['index'] for u in revision_calls],[1])
            self.assertNotIn('previous_version',revision_calls[0])
            self.assertNotIn('chapters',revision_calls[0]['film'])
            self.assertEqual(revision_calls[0]['film']['story_inspiration'],value['story_inspiration'])
            self.assertNotIn(1,[s['index'] for s in revision_calls[0]['history']['upcoming_outline']])

    def test_expanded_shot_editor_corrects_visible_reset_and_keeps_other_scene(self):
        slots=timeline.timeline_plan(30,15); world=global_plan(2)
        planned=story.prepare_events({'scenes':events(slots,2)},slots,world)['scenes']
        full=dict(**world,scenes=[{**s,**v} for s,v in zip(slots,planned)],max_editor_revisions=2)
        value=timeline.prepare_story_scenes({'scenes':scenes_for(slots)},slots,None,{},full)
        value['scenes'][1]['shots'][0]['description']='The boat returns to the dock and departs again'
        kept=copy.deepcopy(value['scenes'][0]); requests=[]
        def request(stage,user,schema,validator,prepare=None,**kwargs):
            requests.append(stage)
            if stage.startswith('shot_editor'):
                bad='departs again' in user['review_scenes'][1]['shots'][0]['description']
                result=dict(accepted=not bad,issues=[dict(index=1,code='contract_mismatch',feedback='Show the new paper passage; the boat already departed.')] if bad else [])
            else: result={'scenes':scenes_for(user['slots'])}
            if prepare: result=prepare(result)
            validator(result); return result
        result,reviews,revisions=timeline.edit_scene_batch(request,world['treatment'],slots,value,full,None,[],{})
        self.assertEqual(revisions,1); self.assertEqual(result['scenes'][0],kept)
        self.assertNotIn('departs again',result['scenes'][1]['shots'][0]['description'])
        self.assertTrue(reviews[-1]['accepted'])

    def test_shot_adjudication_can_accept_compatible_wording_but_not_a_real_reset(self):
        slots=timeline.timeline_plan(15,15); world=global_plan(1)
        planned=story.prepare_events({'scenes':events(slots,1)},slots,world)['scenes']
        full=dict(**world,scenes=[{**s,**v} for s,v in zip(slots,planned)],max_editor_revisions=0)
        value=timeline.prepare_story_scenes({'scenes':scenes_for(slots)},slots,None,{},full)
        for accept in (True,False):
            def request(stage,user,schema,validator,prepare=None,**kwargs):
                self.assertEqual(user['editable_fields'],['shots'])
                self.assertNotIn('upcoming_outline',user['history'])
                self.assertEqual(user['review_scenes'][0]['assigned_event_contract']['index'],0)
                accepted=accept and stage.startswith('shot_editor_confirm')
                review=dict(accepted=accepted,issues=[] if accepted else [dict(index=0,code='continuity',feedback='Verify the visible action against the ending.')])
                validator(review);return review
            if accept:
                result,reviews,revisions=timeline.edit_scene_batch(request,world['treatment'],slots,copy.deepcopy(value),full,None,[],{})
                self.assertEqual(result['scenes'],value['scenes'])
                self.assertTrue(reviews[-1]['accepted']);self.assertEqual(revisions,0)
            else:
                with self.assertRaisesRegex(story.PlanningRepairError,'Shot editor could not resolve'):
                    timeline.edit_scene_batch(request,world['treatment'],slots,copy.deepcopy(value),full,None,[],{})

    def test_next_scene_event_is_not_spent_in_current_segment_prompt(self):
        slots=timeline.timeline_plan(30,15); world=global_plan(2)
        scenes=story.prepare_events({'scenes':events(slots,2)},slots,world)['scenes']
        scenes=story.link_scene_obligations(scenes,world)
        full=dict(**world,scenes=[{**slot,**scene} for slot,scene in zip(slots,scenes)])
        realized=timeline.prepare_story_scenes({'scenes':scenes_for(slots)},slots,None,{},full)
        first=realized['scenes'][0]
        self.assertNotEqual(first['transition'],scenes[0]['next_obligation'])
        self.assertNotIn(scenes[1]['event'],timeline.compile_scene(world['treatment'],first))
        self.assertNotIn('next_obligation',timeline.shot_contract(scenes[0]))


if __name__=='__main__': unittest.main()
