import unittest
from sequential import plan_segments,choose_prompts
from sequence_timing import timing_range

class Planning(unittest.TestCase):
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
