import unittest
from analysis_cache import reusable_analysis, reusable_task


class AnalysisCacheContract(unittest.TestCase):
    def test_completed_partial_keeps_limitations_and_is_reusable(self):
        value = dict(analysis_status='partial', summary='Slow soul, restrained drums',
                     runtime={}, chunks=[{'summary': 'Slow soul', 'task_errors': ['lyrics token limit']}],
                     warnings=['lyrics token limit'])
        self.assertTrue(reusable_analysis(value))
        self.assertEqual(value['analysis_status'], 'partial')
        self.assertEqual(value['warnings'], ['lyrics token limit'])

    def test_failures_and_empty_partial_are_not_cache_hits(self):
        for status in ('failed', 'running', 'interrupted', 'partial'):
            self.assertFalse(reusable_analysis(dict(analysis_status=status,summary='No description',runtime={},chunks=[])))
        self.assertFalse(reusable_analysis(None))

    def test_only_completed_retry_is_reused_when_truncated(self):
        value=dict(text='uncertain lyrics',raw=dict(task='lyrics',possibly_truncated=True))
        self.assertFalse(reusable_task(value, 'lyrics'))
        value['raw']['retry_exhausted']=True
        self.assertTrue(reusable_task(value, 'lyrics'))
        self.assertFalse(reusable_task(value, 'attributes'))
        self.assertFalse(reusable_task({'text':'orphan'}, 'lyrics'))


if __name__ == '__main__': unittest.main()
