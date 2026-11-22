"""Director pool, cache, explicit locks, rejection and release regressions."""
import importlib.util
import json
import math
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('director','ollama_director.py')
director=importlib.util.module_from_spec(spec); spec.loader.exec_module(director)


def payload_of(data):return json.loads(data['messages'][1]['content'].split('Input data:\n',1)[-1])


def candidate(index,revised=False):
    c={field:f'{field} {index}' for field in director.FIELDS}
    c['title']=f'{"Revised" if revised else "Concept"} {index}'
    if index==6:c['motion_cycle']='[Shot 1] A rolling orange wheel travels right. [Shot 2] At 00:05.000 the camera cuts to an orange sun that continues the wheel’s motion across a painted horizon.'
    if revised:c['subject']=f'new physical subject {index}'
    return c


class FakeOllama:
    def __init__(self):
        self.calls=[]; self.tag={'name':'test:local','digest':'first'}
        self.bad_index=None; self.bad_kind='repeated'; self.always_bad=False; self.duplicate_revision=False
    def __call__(self,url,endpoint,data=None,**kwargs):
        self.calls.append((endpoint,data))
        if endpoint=='/api/tags':return {'models':[self.tag]}
        if endpoint=='/api/ps':return {'models':[]}
        if endpoint!='/api/chat':return {}
        p=payload_of(data); props=data['format']['properties']
        if 'approaches' in props:
            choices=props['approaches']['items']['enum']; media=props['media']['items']['enum']
            count=props['approaches']['minItems']
            value=dict(music_direction='Intimate flowing gestures, soft tactile surfaces and restrained expressive pacing.',
                approaches=choices*count if len(choices)==1 else choices[:count],media=[media[i%len(media)] for i in range(count)],
                premises=[f'A different physical subject performs action number {i} in a distinct setting' for i in range(count)])
        elif 'concept' in props:
            revised='concept_to_replace' in p
            index=p['concept_index_to_replace'] if revised else len(p['reserved_titles'])+1
            value={'concept':candidate(2 if revised and self.duplicate_revision else index,revised=revised and not self.duplicate_revision)}
            if p['animation_medium_lock']!='none':value['concept']['treatment']=p['animation_medium_lock']+': coherent animation grammar and tactile surfaces.'
            if p['directing_approach']['name']=='Associative montage':value['concept']['motion_cycle']='[Shot 1] A rolling orange wheel travels right. [Shot 2] At 00:05.000 the camera cuts to an orange sun that continues the wheel’s motion across a painted horizon.'
        else:
            reviews=[]
            for local,c in enumerate(p['concepts'],1):
                index=int(c['title'].split()[-1]); bad=index==self.bad_index and (self.always_bad or not c['title'].startswith('Revised'))
                reviews.append(dict(index=local,music_fit='weak' if bad and self.bad_kind=='music' else 'grounded',
                    cue_ids=[c['id'] for c in p['music_cues'][:2]],fit_reason='Pacing and surfaces match the supplied observations.',
                    novelty='repeated' if bad and self.bad_kind=='repeated' else 'fresh',revision_needed=bad,
                    feedback='Change the unlocked premise, retaining musical pacing and requested style.' if bad else '',
                    direction_fit='weak' if bad and self.bad_kind=='direction' else 'strong',development_fit='strong',
                    direction_reason='Actual movement and treatment follow the assigned direction.'))
            value={'reviews':reviews}
        return {'message':{'content':json.dumps(value)},'done_reason':'stop','eval_count':100}


class DirectorTests(unittest.TestCase):
    def test_duplicate_title_keeps_distinct_fast_mode_candidate(self):
        with tempfile.TemporaryDirectory() as root,self.environment(root):
            api=FakeOllama()
            def repeated_title(url,endpoint,data=None,**kwargs):
                response=api(url,endpoint,data,**kwargs)
                if endpoint=='/api/chat' and 'concept' in data['format']['properties']:
                    value=json.loads(response['message']['content'])
                    if value['concept']['title']=='Concept 3':
                        value['concept']['title']=' concept 1 '
                        response['message']['content']=json.dumps(value)
                return response
            # The fake editor identifies proposals by the number in their titles.
            def chat(url,endpoint,data=None,**kwargs):
                if endpoint=='/api/chat' and 'reviews' in data['format']['properties']:
                    payload=payload_of(data)
                    for index,concept in enumerate(payload['concepts'],1):
                        concept['title']=f'Concept {index}'
                    data={**data,'messages':[data['messages'][0],{'role':'user','content':json.dumps(payload)}]}
                return repeated_title(url,endpoint,data,**kwargs)
            with patch.object(director,'api',side_effect=chat):
                _,_,concepts,report=director.MusicCanvasOllamaDirector().direct(**self.args(director_mode='Fast (3 concepts)'))
            third=json.loads(concepts)['concepts'][2]
            self.assertEqual(third['title'],'concept 1 (2)')
            self.assertEqual(third['subject'],candidate(3)['subject'])
            self.assertEqual(json.loads(report)['llm_requests'],5)

    def environment(self,root):
        mm=types.SimpleNamespace(throw_exception_if_processing_interrupted=lambda:None)
        return patch.dict(sys.modules,{'folder_paths':types.SimpleNamespace(get_user_directory=lambda:root),
            'comfy':types.ModuleType('comfy'),'comfy.model_management':mm})
    def args(self,**updates):
        args=dict(connection=dict(model='test:local',base_url='http://127.0.0.1:11434',device='CPU',context_length=8192),
            analysis_json=json.dumps(dict(summary='Reviewed sparse piano with intimate vocals',instruments=['piano'],moods=['intimate'],lyrics='SECRET_LYRICS')),
            artist_direction='',exclusions='text, flashing',profile='social_preview',duration_seconds=15,
            concept_index=0,lyrics_approved=False,temperature=.6,seed=42,max_tokens=2400,regenerate=0)
        args.update(updates); return args

    def test_nonvisual_motion_is_rejected(self):
        value={'concepts':[candidate(i) for i in (1,2,3)]}; value['concepts'][0]['motion_cycle']='Raise audio volume from 0 to 100'
        with self.assertRaisesRegex(ValueError,'visible action'):director.validate(value,3)

    def test_loopback_only(self):
        for url in ('https://ollama.com','http://10.0.0.1:11434','http://localhost@remote.example','http://127.0.0.1/path'):
            with self.assertRaises(ValueError):director.local_url(url)
        self.assertEqual(director.local_url('http://127.0.0.1:11434/'),'http://127.0.0.1:11434')

    def test_resident_model_blocks_release(self):
        with patch.object(director,'api',return_value={'models':[{'name':'selected'}]}),patch.object(director.time,'monotonic',side_effect=[0,21]):
            with self.assertRaisesRegex(RuntimeError,'still resident'):director.release('http://127.0.0.1:11434','selected')

    def test_release_barrier_always_changes_and_passes_text(self):
        self.assertTrue(math.isnan(director.MusicCanvasOllamaRelease.IS_CHANGED()))
        with patch.object(director,'release',return_value={'verified_absent':True}) as release:
            text,report=director.MusicCanvasOllamaRelease().unload(dict(base_url='http://127.0.0.1:11434',model='selected'),'reviewed prompt')
            self.assertEqual(text,'reviewed prompt'); self.assertTrue(json.loads(report)['verified_absent']); release.assert_called_once()

    def test_six_candidates_auto_and_explicit_cache_model_digest_and_lyrics(self):
        with tempfile.TemporaryDirectory() as root,self.environment(root):
            api=FakeOllama()
            with patch.object(director,'api',side_effect=api):
                node=director.MusicCanvasOllamaDirector(); first=node.direct(**self.args()); report=json.loads(first[3])
                self.assertEqual(len(json.loads(first[2])['concepts']),6)
                self.assertEqual(len({d['name'] for d in report['candidate_directions']}),6)
                self.assertEqual(report['selection_mode'],'automatic'); self.assertEqual(report['llm_requests'],9)
                explicit=node.direct(**self.args(concept_index=6)); again=node.direct(**self.args())
                self.assertEqual(json.loads(explicit[1])['concept']['title'],'Concept 6')
                self.assertEqual(json.loads(explicit[3])['llm_requests'],0)
                self.assertEqual(json.loads(again[1])['concept'],json.loads(first[1])['concept'])
                self.assertNotIn('SECRET_LYRICS',json.dumps(api.calls))
                api.tag['digest']='replacement'; changed=node.direct(**self.args())
                self.assertFalse(json.loads(changed[3])['cache_hit'])
                self.assertEqual(sum(endpoint=='/api/chat' for endpoint,_ in api.calls),18)
                self.assertEqual(sum(endpoint=='/api/generate' for endpoint,_ in api.calls),4)
                refreshed=node.direct(**self.args(regenerate=1))
                self.assertNotEqual(json.loads(refreshed[3])['effective_generation_seed'],report['effective_generation_seed'])
                self.assertFalse(json.loads(refreshed[3])['cache_hit'])

    def test_independent_dropdown_locks_are_forwarded_and_none_is_default(self):
        controls=director.MusicCanvasOllamaDirector.INPUT_TYPES()
        for name in ('directing_approach','animation_medium'):self.assertEqual(controls['optional'][name][0][0],'none')
        with tempfile.TemporaryDirectory() as root,self.environment(root):
            api=FakeOllama(); approach='Character journey'; medium='Clay or puppet stop-motion'
            with patch.object(director,'api',side_effect=api):
                result=director.MusicCanvasOllamaDirector().direct(**self.args(directing_approach=approach,animation_medium=medium))
            brief=json.loads(result[1]); self.assertEqual(brief['directing_approach']['name'],approach)
            self.assertEqual(brief['category_locks'],dict(directing_approach=approach,animation_medium=medium))
            payloads=[payload_of(d) for e,d in api.calls if e=='/api/chat' and 'concept' in d['format']['properties']]
            self.assertEqual(len(payloads),6)
            self.assertTrue(all(p['animation_medium_lock']==medium and p['directing_approach']['name']==approach for p in payloads))

    def test_fast_mode_reviews_three_concepts_and_reuses_their_pool(self):
        with tempfile.TemporaryDirectory() as root,self.environment(root):
            api=FakeOllama()
            mode='Fast (3 concepts)'
            analysis=json.dumps(dict(summary='Steady dance pulse',beats=[0,1,2,15],downbeats=[0,2]))
            with patch.object(director,'api',side_effect=api):
                node=director.MusicCanvasOllamaDirector()
                results=node.direct(**self.args(director_mode=mode,analysis_json=analysis))
                report=json.loads(results[3])
                self.assertEqual(report['llm_requests'],5)
                self.assertEqual(len(json.loads(results[2])['concepts']),3)
                review=next(payload_of(d) for endpoint,d in api.calls if endpoint=='/api/chat' and 'reviews' in d['format']['properties'])
                self.assertEqual(review['measured_rhythm']['preferred_local_beats'],[0,1,2])
                selected=node.direct(**self.args(director_mode=mode,analysis_json=analysis,concept_index=3))
                self.assertEqual(json.loads(selected[3])['llm_requests'],0)
                self.assertEqual(json.loads(selected[1])['concept']['title'],'Concept 3')
                with self.assertRaisesRegex(ValueError,'concept_index'):
                    node.direct(**self.args(director_mode=mode,concept_index=4))

    def test_revises_only_rejected_candidate_and_preserves_other_five(self):
        with tempfile.TemporaryDirectory() as root,self.environment(root):
            api=FakeOllama(); api.bad_index=2
            with patch.object(director,'api',side_effect=api):
                result=director.MusicCanvasOllamaDirector().direct(**self.args(concept_index=2,artist_direction='Keep the requested subject'))
            concepts=json.loads(result[2])['concepts']; self.assertEqual(concepts[1],candidate(2,True))
            self.assertEqual([c for i,c in enumerate(concepts) if i!=1],[candidate(i) for i in (1,3,4,5,6)])
            self.assertEqual(json.loads(result[3])['revised_concept_indices'],[2])
            revisions=[payload_of(d) for e,d in api.calls if e=='/api/chat' and 'concept_to_replace' in payload_of(d)]
            self.assertEqual(len(revisions),1); self.assertEqual(revisions[0]['artist_direction'],'Keep the requested subject')

    def test_failed_rewrites_cannot_make_auto_choose_a_repeated_or_weak_candidate(self):
        with tempfile.TemporaryDirectory() as root,self.environment(root):
            api=FakeOllama(); api.bad_index=1; api.always_bad=True; api.duplicate_revision=True
            with patch.object(director,'api',side_effect=api):
                node=director.MusicCanvasOllamaDirector(); result=node.direct(**self.args())
                self.assertNotEqual(json.loads(result[1])['concept_index'],1)
                self.assertEqual(len(json.loads(result[3])['revision_failures']),2)
                count=len(api.calls)
                with self.assertRaisesRegex(ValueError,'did not pass'):node.direct(**self.args(concept_index=1))
                self.assertEqual(sum(e=='/api/chat' for e,_ in api.calls[count:]),0)

    def test_invalid_model_response_still_unloads_and_caches_no_pool(self):
        with tempfile.TemporaryDirectory() as root,self.environment(root):
            with patch.object(director,'models',return_value=[{'name':'test:local'}]),patch.object(director,'api',return_value={'message':{'content':'{}'}}),patch.object(director,'release') as release:
                with self.assertRaises(ValueError):director.MusicCanvasOllamaDirector().direct(**self.args())
                release.assert_called_once()
            from pathlib import Path
            self.assertFalse(list((Path(root)/'MusicCanvas/ollama_cache').glob('*.json')))

    def test_partial_generation_resumes_valid_stages_without_exposing_a_partial_pool(self):
        with tempfile.TemporaryDirectory() as root,self.environment(root):
            api=FakeOllama(); failures=0; failed_seed=None
            def flaky(url,endpoint,data=None,**kwargs):
                nonlocal failures,failed_seed
                if endpoint=='/api/chat' and 'concept' in data['format']['properties']:
                    payload=payload_of(data)
                    if len(payload['reserved_titles'])==3 and failures<3:
                        if failed_seed is None:failed_seed=data['options']['seed']
                        failures+=1; api.calls.append((endpoint,data))
                        return {'message':{'content':'{}'},'done_reason':'stop'}
                return api(url,endpoint,data,**kwargs)
            with patch.object(director,'api',side_effect=flaky):
                node=director.MusicCanvasOllamaDirector()
                with self.assertRaisesRegex(ValueError,'concept_4'):node.direct(**self.args())
                from pathlib import Path
                self.assertFalse(list((Path(root)/'MusicCanvas/ollama_cache').glob('*.json')))
                start=len(api.calls); result=node.direct(**self.args())
                report=json.loads(result[3]); self.assertEqual(report['stage_cache_hits'],4)
                new_chats=[d for e,d in api.calls[start:] if e=='/api/chat']
                self.assertEqual(len(new_chats),5)
                self.assertEqual(new_chats[0]['options']['seed'],failed_seed)
                self.assertEqual(len(json.loads(result[2])['concepts']),6)


if __name__=='__main__':unittest.main()
