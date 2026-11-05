"""Contract tests; real inference evidence lives in test_results/audio_understanding."""
import math
import unittest
from analysis_core import absolute_sections, bounded_times, chunk_ranges, rhythm_result, usable_caption, string_list, normalize_analysis


class AudioContractTests(unittest.TestCase):
    def test_director_evidence_does_not_include_caption_claims(self):
        original=dict(summary='Invented identity and 75 dB claims',chunks=[dict(start=0,end=20,
            attributes=dict(instruments=['drums','piano? likely not present'],moods=['tense']))],
            instruments=['drums','piano? likely not present'],tempo_bpm=100,warnings=[])
        result=normalize_analysis(original)
        self.assertNotIn('Invented',result['summary'])
        self.assertEqual(result['raw_music_caption'],original['summary'])
        self.assertEqual(result['instruments'],['drums'])
        self.assertIn('100.00 BPM',result['summary'])
        self.assertTrue(result['requires_artist_review'])

    def test_hallucinated_identifier_and_repetition_are_rejected(self):
        self.assertFalse(usable_caption('This excerpt is by 123456789012345678901234567890'))
        self.assertFalse(usable_caption('gentle music in the background ' * 10))
        self.assertTrue(usable_caption('A steady electronic drum groove supports a low synth bass with a bright repeating melody.'))

    def test_actual_model_label_shapes(self):
        self.assertEqual(string_list([{'genre':'electronic','subgenre':'trap'},'ambient']),['electronic / trap','ambient'])
        self.assertIsNone(string_list(None))

    def test_chunk_coverage_includes_tail_and_overlap(self):
        spans = chunk_ranges(79.848)
        self.assertEqual(spans, [(0.,30.),(28.,58.),(56.,79.848)])
        self.assertEqual(chunk_ranges(4), [(0.,4)])
        for a,b in zip(spans,spans[1:]):
            self.assertEqual(a[1]-b[0],2)

    def test_invalid_chunking(self):
        for duration in (0,-1,float('nan')):
            with self.assertRaises(ValueError):
                chunk_ranges(duration)
        with self.assertRaises(ValueError):
            chunk_ranges(100,30,30)

    def test_timestamps_are_sorted_finite_and_bounded(self):
        self.assertEqual(bounded_times([3,1,1,-1,5,float('nan'),float('inf')],4),[1,3])

    def test_offsets_and_invalid_sections(self):
        values=[dict(start=0,end=5,label='intro'),dict(start=5,end=40,label='outside'),dict(start=0,end=float('nan'),label='bad')]
        result=absolute_sections(values,28,58)
        self.assertEqual([(x['start'],x['end']) for x in result],[(28,33)])

    def test_beat_order_and_tempo(self):
        result=rhythm_result([0,.5,1,1.5,2],[0,2],3)
        self.assertEqual(result['tempo_bpm'],120)
        self.assertGreater(len(result['beats']),len(result['downbeats']))
        self.assertEqual(result['downbeats'],[0,2])
        self.assertIsNone(rhythm_result([],[],3)['tempo_bpm'])
        self.assertIsNone(rhythm_result([0,.5],[],3)['tempo_bpm'])


if __name__ == '__main__':
    unittest.main()
