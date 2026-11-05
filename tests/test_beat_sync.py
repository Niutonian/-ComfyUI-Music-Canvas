import unittest
from beat_sync import beat_plan


class BeatMotionTests(unittest.TestCase):
    def setUp(self):
        self.analysis=dict(beats=[i*.5 for i in range(80)],downbeats=[i*2. for i in range(20)])

    def test_duration_ends_on_downbeat_and_events_hit_frames(self):
        plan=beat_plan(self.analysis,0,158,24,.75)
        self.assertEqual(plan['duration'],6)
        self.assertEqual(len(plan['events']),12)
        self.assertEqual(plan['frame_count'],144)
        for event in plan['events']:
            self.assertLessEqual(abs(event['time']-event['frame']/24),.5/24)
            i=event['frame']
            self.assertGreaterEqual(plan['zooms'][i],plan['zooms'][max(0,i-1)])
            self.assertGreaterEqual(plan['zooms'][i],plan['zooms'][min(143,i+1)])
        self.assertFalse(plan['spotify_playback_phase_synchronization'])

    def test_source_phase_is_monotonic_and_downbeats_stronger(self):
        plan=beat_plan(self.analysis,0,158)
        self.assertTrue(all(a<b for a,b in zip(plan['source_positions'],plan['source_positions'][1:])))
        self.assertLess(plan['source_positions'][-1],158)
        self.assertGreater(plan['zooms'][0],plan['zooms'][12])

    def test_no_fabricated_grid(self):
        with self.assertRaises(ValueError):
            beat_plan(dict(beats=[],downbeats=[]),0,158)

    def test_disabled_preserves_input_timing(self):
        plan=beat_plan(self.analysis,0,158,strength=0)
        self.assertTrue(plan['disabled'])
        self.assertEqual(plan['source_positions'],list(range(158)))
        self.assertEqual(plan['duration'],158/24)

    def test_end_beat_is_not_duplicated_by_quantization(self):
        analysis=dict(beats=[i*.51 for i in range(40)],downbeats=[i*2.04 for i in range(10)])
        plan=beat_plan(analysis,0,158)
        self.assertTrue(all(e['frame']<plan['frame_count'] for e in plan['events']))


if __name__=='__main__':
    unittest.main()
