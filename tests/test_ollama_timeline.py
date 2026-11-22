import copy
import importlib
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
from sequential import plan_segments,timeline_prompts

# The planner has no tensor dependency; isolate the package without importing nodes.
package=types.ModuleType('timeline_test_pack'); package.__path__=[str(Path(__file__).resolve().parents[1])]
sys.modules.setdefault('timeline_test_pack',package)
timeline=importlib.import_module('timeline_test_pack.ollama_timeline')


def scenes_for(slots):
    return [dict(index=s['index'],narrative_beat=f'Development {s["index"]}',
                 start_state=f'state {s["index"]}',end_state=f'state {s["index"]+1}',
                 transition='Continue into the next scene',musical_rationale='Restrained drums guide the pacing',
                 shots=[dict(at=0,description=f'The bronze figure advances to platform {s["index"]+1} in a tracking shot')]) for s in slots]


class TimelineContract(unittest.TestCase):
    def test_each_cut_carries_the_same_design_without_repeating_the_opening_action(self):
        slot=timeline.timeline_plan(15,15)[0]
        bible={k:'Consistent film direction' for k in timeline.BIBLE_SCHEMA['properties']}
        bible.update(visual_style='Hand-drawn ink animation with dry-brush edges',palette='Vermilion and muted ivory',
            identity_anchors='A slender courier with a triangular collar and two ivory sleeve bands',
            lighting_continuity='Window light stays fixed in the room as the camera moves',
            spatial_continuity='The courier crosses the room from left to right',motion_grammar='Weighted drawn gestures with fabric follow-through')
        scene=scenes_for([slot])[0]
        scene['start_state']='The courier is already inside the open doorway'
        scene['shots']=[dict(at=0,description='The courier crosses the threshold toward the desk.'),
            dict(at=5,description='A close-up follows the same sleeve as the hand catches a sliding letter.'),
            dict(at=10,description='The courier carries the caught letter to the desk without changing hands.')]
        original=copy.deepcopy(scene)
        prompt=timeline.compile_scene(bible,scene)
        for part in (prompt.split('[Shot 1]')[1].split('[Shot 2]')[0],prompt.split('[Shot 2]')[1].split('[Shot 3]')[0],prompt.split('[Shot 3]')[1]):
            self.assertIn(bible['identity_anchors'],part)
        self.assertEqual(prompt.count(scene['start_state']),1)
        self.assertIn('Window light stays fixed',prompt)
        self.assertIn('preserve screen direction and prop contact',prompt)
        self.assertEqual(scene,original)

    def test_visual_identity_is_per_film_and_does_not_freeze_transformation(self):
        slot=timeline.timeline_plan(15,15)[0];scene=scenes_for([slot])[0]
        bible={k:'Specific film direction' for k in timeline.BIBLE_SCHEMA['properties']}
        bible.update(identity_anchors='A sculpture with a star-shaped opening',visual_style='Glazed ceramic animation',
            palette='Jade and ivory',world='An abstract tiled room')
        scene['start_state']='The star-shaped opening remains as the surface turns jade'
        scene['end_state']='The jade sculpture reaches the sunlit terrace'
        prompt=timeline.compile_scene(bible,scene)
        self.assertIn(scene['start_state'],prompt);self.assertIn(scene['end_state'],prompt)
        self.assertIn('take precedence over the baseline for changed attributes',prompt)
        other={**bible,'identity_anchors':'A red woven ribbon with square stitching','visual_style':'Textile stop motion','palette':'Red and charcoal'}
        other_prompt=timeline.compile_scene(other,scene)
        self.assertNotIn(bible['identity_anchors'],other_prompt)
        self.assertNotIn(other['identity_anchors'],prompt)
        self.assertNotIn('<Picture',prompt);self.assertNotIn('<Subject',prompt)

    def test_previous_shot_is_supplied_as_history_to_the_next_scene_batch(self):
        self.check_planning(False,check_handoff=True)

    def test_single_batch_scene_number_reset_and_reordered_batches(self):
        slots=timeline.timeline_plan(60,15)
        single={'scenes':scenes_for(slots[2:3])}
        single['scenes'][0]['index']=0
        result=timeline.prepare_scenes(single,slots[2:3],previous='state 2')
        timeline.validate_scenes(result,slots[2:3],previous='state 2')
        self.assertEqual(result['scenes'][0]['index'],2)
        unordered={'scenes':list(reversed(scenes_for(slots)))}
        ordered=timeline.prepare_scenes(unordered,slots)
        timeline.validate_scenes(ordered,slots)
        self.assertEqual([s['index'] for s in ordered['scenes']],[0,1,2,3])

    def test_out_of_range_and_absolute_cut_times_are_scheduled_inside_scene(self):
        slot=timeline.timeline_plan(30,15)[1]
        for times in ([0,15],[15,22.5],[0,45,60],[0,-1],[0,12,5],[3,3,3]):
            scene=scenes_for([slot])[0]
            scene['shots']=[dict(at=t,description=f'Action {i}') for i,t in enumerate(times)]
            raw={'scenes':[scene]}; original=copy.deepcopy(raw)
            result=timeline.prepare_scenes(raw,[slot],previous='carried state')
            timeline.validate_scenes(result,[slot],previous='carried state')
            scheduled=[s['at'] for s in result['scenes'][0]['shots']]
            self.assertEqual(scheduled[0],0)
            self.assertTrue(all(0<=t<slot['duration'] and abs(t*24-round(t*24))<1e-8 for t in scheduled))
            self.assertTrue(all(b-a>=1 for a,b in zip(scheduled,scheduled[1:])))
            self.assertEqual(raw,original)
            self.assertEqual(timeline.prepare_scenes(result,[slot],previous='carried state'),result)
            if times==[15,22.5]: self.assertEqual(scheduled,[0,7.5])

    def test_cut_scheduler_preserves_valid_cuts_and_prefers_nearby_downbeat(self):
        slot=timeline.timeline_plan(30,15)[1]
        raw={'scenes':scenes_for([slot])}
        raw['scenes'][0]['shots'].append(dict(at=7.5,description='The figure steps through the open doorway'))
        unchanged=timeline.prepare_scenes(raw,[slot])
        self.assertEqual(unchanged['scenes'],raw['scenes'])
        result=timeline.prepare_scenes(raw,[slot],analysis={'downbeats':[22.75],'beats':[22.5,26.]})
        self.assertEqual(result['scenes'][0]['shots'][1]['at'],7.75)
        distant=timeline.prepare_scenes(raw,[slot],analysis={'beats':[26.]})
        self.assertEqual(distant['scenes'],raw['scenes'])

    def test_short_scene_merges_shots_without_losing_actions(self):
        for duration in (1/24,.25,1.,2.):
            slot=timeline.timeline_plan(duration,.25 if duration<.25 else duration)[0]
            raw={'scenes':scenes_for([slot])}
            raw['scenes'][0]['shots'].append(dict(at=15,description='The door closes behind the figure'))
            result=timeline.prepare_scenes(raw,[slot])
            timeline.validate_scenes(result,[slot])
            self.assertEqual(len(result['scenes'][0]['shots']),1)
            self.assertIn('door closes',result['scenes'][0]['shots'][0]['description'])

    def test_nonfinite_or_nonnumeric_timing_is_still_rejected(self):
        slots=timeline.timeline_plan(15,15)
        for at in (float('nan'),float('inf'),'15',None,True):
            value={'scenes':scenes_for(slots)}
            value['scenes'][0]['shots'][0]['at']=at
            with self.subTest(at=at),self.assertRaises(ValueError): timeline.prepare_scenes(value,slots)

    def test_four_unique_connected_scenes_and_short_test(self):
        slots=timeline.timeline_plan(60,15)
        self.assertEqual(len(slots),4)
        scenes=scenes_for(slots)
        self.assertEqual(timeline.validate_scenes({'scenes':scenes},slots),scenes)
        bible={k:'Bronze sculpture in indigo light' for k in timeline.BIBLE_SCHEMA['properties']}
        prompts=[timeline.compile_scene(bible,s) for s in scenes]
        self.assertEqual(len(set(prompts)),4)
        value=dict(segments=[dict(**slot,prompt=p) for slot,p in zip(slots,prompts)])
        self.assertEqual(timeline_prompts(json.dumps(value),json.dumps(prompts),slots)[1],prompts)
        with self.assertRaises(ValueError): timeline_prompts(json.dumps(value),'',slots[:-1])
        value['segments'][1]['frames']=1
        with self.assertRaises(ValueError): timeline_prompts(json.dumps(value),'',slots)
        tiny=timeline.timeline_plan(.25,.25)
        self.assertEqual(tiny[0]['frames'],6)
        for samples in (44100,44101,682019,2646001):
            self.assertEqual(timeline.timeline_plan(samples/44100,15),plan_segments(samples,44100,15))

    def test_reject_reset_repeated_action_and_cuts_outside_scene(self):
        slots=timeline.timeline_plan(30,15); baseline=scenes_for(slots)
        for kind in ('continuity','repeat','end','cut','short'):
            scenes=copy.deepcopy(baseline)
            selected=slots
            if kind=='continuity': scenes[1]['start_state']='reset to opening'
            elif kind=='repeat': scenes[1]['shots']=copy.deepcopy(scenes[0]['shots'])
            elif kind=='end': scenes[0]['end_state']=scenes[0]['start_state']
            elif kind=='cut': scenes[0]['shots'].append(dict(at=15,description='Cut too late'))
            else:
                selected=timeline.timeline_plan(2,1); scenes=scenes_for(selected)
                scenes[0]['shots'].append(dict(at=.5,description='Unnecessary cut'))
            with self.subTest(kind=kind),self.assertRaises(ValueError): timeline.validate_scenes({'scenes':scenes},selected)

    def test_model_planning_cached_but_release_always_verified(self):
        self.check_planning(False)

    def test_large_response_automatically_reduces_batches_and_remembers_policy(self):
        self.check_planning(True)

    def test_model_timing_and_continuity_errors_are_fixed_without_another_request(self):
        self.check_planning(False,model_timing_errors=True)

    def check_planning(self,reduce_batches,model_timing_errors=False,check_handoff=False):
        with tempfile.TemporaryDirectory() as temp:
            folders=types.ModuleType('folder_paths'); folders.get_user_directory=lambda:temp
            mm=types.ModuleType('comfy.model_management'); mm.unload_all_models=lambda:None
            mm.soft_empty_cache=lambda:None; mm.throw_exception_if_processing_interrupted=lambda:None
            utils=types.ModuleType('comfy.utils')
            utils.ProgressBar=lambda count:types.SimpleNamespace(update_absolute=lambda n:None)
            comfy=types.ModuleType('comfy'); comfy.__path__=[]; comfy.model_management=mm
            modules={'folder_paths':folders,'comfy':comfy,'comfy.model_management':mm,'comfy.utils':utils}
            calls=[]; released=[]
            def api(url,endpoint,request,**kwargs):
                calls.append(request)
                user=json.loads(request['messages'][1]['content'])
                if reduce_batches and len(user.get('slots',[]))>1:
                    return {'message':{'content':'{"scenes":['},'done_reason':'length'}
                if 'slots' in user:
                    if check_handoff:
                        self.assertIn('lighting_continuity',user['visual_continuity'])
                        self.assertNotIn('identity_anchors',user['global_treatment'])
                        if user['slots'][0]['index']==2:
                            self.assertEqual(user['preceding_shot']['scene_index'],1)
                            self.assertEqual(user['preceding_shot']['end_state'],'state 2')
                            self.assertEqual(user['preceding_shot']['description'],scenes_for([timeline.timeline_plan(60,15)[1]])[0]['shots'][-1]['description'])
                        else:self.assertIsNone(user['preceding_shot'])
                    value={'scenes':scenes_for(user['slots'])}
                    if model_timing_errors:
                        for s in value['scenes']:
                            s['start_state']='Paraphrased opening state'
                            s['shots'].append(dict(at=60,description=f'The figure reveals a new room {s["index"]}'))
                            s['index']=0
                else: value={k:'Bronze figure travels across islands' for k in timeline.BIBLE_SCHEMA['properties']}
                return {'message':{'content':json.dumps(value)},'done_reason':'stop'}
            conn=dict(base_url='http://127.0.0.1:11434',model='local:9b',device='GPU',context_length=8192)
            options=dict(connection=conn,analysis_json=json.dumps(dict(summary='Soul groove',beats=[0,1,2],chunks=[])),
                         base_brief_json='{"concept":{}}',base_prompt='A bronze figure',total_seconds=60,segment_seconds=15,
                         lyrics_approved=False,temperature=.6,seed=42,max_tokens=3072,regenerate=0)
            if check_handoff:options['batch_size']=2
            with patch.dict(sys.modules,modules),patch.object(timeline.ollama,'models',return_value=[dict(name='local:9b',digest='revision')]),patch.object(timeline.ollama,'api',side_effect=api),patch.object(timeline.ollama,'release',side_effect=lambda *args:released.append(args) or {'verified_absent':True}):
                first=timeline.MusicCanvasOllamaTimeline().direct(**options)
                second=timeline.MusicCanvasOllamaTimeline().direct(**options)
            self.assertEqual(len(calls),3 if check_handoff else 7 if reduce_batches else 2)
            self.assertEqual(len(released),2)
            self.assertEqual(json.loads(second[2])['requests'],0)
            self.assertEqual(json.loads(second[2])['cache_hits'],1)
            self.assertTrue(json.loads(second[2])['approved_plan_cache_hit'])
            self.assertEqual(first[:2],second[:2])
            self.assertEqual(len(set(json.loads(first[0]))),4)
            if model_timing_errors:
                film=json.loads(first[1]); slots=timeline.timeline_plan(60,15)
                timeline.validate_scenes({'scenes':[s['scene'] for s in film['segments']]},slots)
                self.assertTrue(json.loads(first[2])['planning_adjustments'])
                self.assertEqual(json.loads(first[2])['planning_adjustments'],json.loads(second[2])['planning_adjustments'])


if __name__=='__main__': unittest.main()
