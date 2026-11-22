import json
import unittest
from sequential import plan_segments,choose_prompts,continuity_studio_timeline,reference_prompt
from sequence_timing import timing_range

class Planning(unittest.TestCase):
    def test_reference_prompt_prioritizes_current_action_over_reference_pose(self):
        prompt=('integrated_multimodal_description: [Shot 1] Painted scenery. '
                'Opening state: The gate is open. [Shot 2] Track from behind.')
        directed=reference_prompt(prompt,{'start_state':'The gate is open.',
                                         'narrative_beat':'The dancer crosses the courtyard.'})
        self.assertIn('<Picture 1> is a design reference',directed)
        self.assertIn('[Shot 1] Cut directly into the current state: The gate is open.',directed)
        self.assertLess(directed.index('The dancer crosses'),directed.index('Painted scenery'))
        self.assertEqual(directed.count('The gate is open.'),1)
        self.assertTrue(directed.endswith('[Shot 2] Track from behind.'))
        self.assertTrue(reference_prompt(prompt).endswith(prompt))

    def test_studio_export_preserves_exact_timing_and_uses_memory_at_cuts(self):
        rate=48000
        samples=30*rate+1
        plan=plan_segments(samples,rate,15)
        source=json.dumps(dict(segment_seconds=15,segments=[dict(**slot,prompt=f'Scene {i}') for i,slot in enumerate(plan)]))
        audio=dict(type='output',subfolder='music_canvas/test',filename='source_audio.wav')
        studio=continuity_studio_timeline(source,samples,rate,2**64-1,audio_file=audio)
        self.assertEqual([box['frames'] for box in studio['boxes']],[360,360,1])
        self.assertEqual([box['cut'] for box in studio['boxes']],[False,True,True])
        self.assertEqual([box['memory'] for box in studio['boxes']],['off','scene','scene'])
        self.assertTrue(all(box['exact'] and '@audio1' in box['prompt'] for box in studio['boxes']))
        self.assertEqual([box['seed'] for box in studio['boxes']],[2**64-1,0,1])
        self.assertEqual(studio['audio_clips'][0]['duration'],samples/rate)
        self.assertEqual(studio['audio_clips'][0]['file'],audio)
        self.assertTrue(studio['audio_clips'][0]['in_full_video'])
        with self.assertRaisesRegex(ValueError,'timing'):
            continuity_studio_timeline(source,samples+2400,rate,42)

    def test_long_song_coverage(self):
        samples=round(608.757551*44100)
        plan=plan_segments(samples,44100,15)
        self.assertEqual(len(plan),41)
        self.assertEqual(sum(s['frames'] for s in plan),__import__('math').ceil(samples/44100*24))
        for a,b in zip(plan,plan[1:]):
            self.assertEqual(a['start_frame']+a['frames'],b['start_frame'])
        self.assertTrue(all((s['model_frames']-5)%17==0 for s in plan))
        self.assertTrue(all(s['model_frames']>=s['frames'] for s in plan))

    def test_tiny_tail_and_no_total_duration_cap(self):
        plan=plan_segments(30*48000+1,48000,15)
        self.assertEqual([s['frames'] for s in plan],[360,360,1])
        self.assertEqual(len(plan_segments(48*3600*16000,16000,15)),11520)

    def test_invalid_inputs(self):
        for args in [(0,44100,15),(5,0,15),(100,10,16)]:
            with self.assertRaises(ValueError): plan_segments(*args)

    def test_total_vs_scene_and_short_tests(self):
        a,b,per=timing_range(600*48000,48000,0,30,15)
        self.assertEqual((a,b,per),(0,30*48000,15))
        self.assertEqual(len(plan_segments(b-a,48000,per)),2)
        a,b,per=timing_range(600*48000,48000,0,1,15)
        self.assertEqual(per,1)
        self.assertEqual(plan_segments(b-a,48000,per)[0]['frames'],24)
        self.assertEqual(timing_range(600*48000,48000,0,0,15)[1],600*48000)
        self.assertEqual(timing_range(600*48000,48000,0,30,30)[2],15)
        self.assertEqual(plan_segments(12000,48000,.25)[0]['frames'],6)

    def test_prompt_rotation(self):
        self.assertEqual(choose_prompts('base','["scene A","scene B"]',3),['scene A','scene B','scene A'])
        self.assertEqual(choose_prompts('base','',2),['base','base'])
        for value in ['{}','[]','[7]']:
            with self.assertRaises(ValueError): choose_prompts('x',value,2)

if __name__=='__main__': unittest.main()
