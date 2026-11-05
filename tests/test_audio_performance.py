import concurrent.futures
import tempfile
import time
import unittest
from pathlib import Path
from audio_performance import StageCache,coverage,sampled_ranges,identity,AudioFeatureMemo

class PerformanceContracts(unittest.TestCase):
    def test_atomic_concurrent_task_reuse(self):
        with tempfile.TemporaryDirectory() as temp:
            cache=StageCache(temp); generated=[]
            def request():
                with cache.lock({'task':'attributes','audio':'a'}):
                    value=cache.get({'task':'attributes','audio':'a'})
                    if value is None:
                        time.sleep(.02); generated.append(1)
                        value={'response':'valid'}; cache.put({'task':'attributes','audio':'a'},value)
                    return value
            with concurrent.futures.ThreadPoolExecutor(2) as pool:
                result=list(pool.map(lambda _:request(),range(2)))
            self.assertEqual(len(generated),1)
            self.assertEqual(result,[{'response':'valid'}]*2)
            self.assertIsNone(cache.get({'task':'lyrics','audio':'a'}))
            self.assertIsNone(cache.get({'task':'attributes','audio':'different'}))
    def test_corrupt_entry_is_recomputed(self):
        with tempfile.TemporaryDirectory() as temp:
            cache=StageCache(temp); key={'a':1}; cache.path(key).write_text('{')
            self.assertIsNone(cache.get(key))
    def test_sampled_coverage_is_honest(self):
        ranges=[(i,i+30) for i in range(0,600,30)]
        selected=sampled_ranges(ranges)
        self.assertEqual(len(selected),3)
        self.assertLess(coverage(selected,600),1)
        self.assertEqual(coverage([(0,30),(28,58),(56,60)],60),1)
    def test_feature_bundle_and_invalidation(self):
        try: import torch
        except ImportError: self.skipTest('torch runtime required')
        class Model:
            calls=0
            def get_audio_features(self,f,l):
                self.calls+=1
                return f*2,[f*3,f*4]
        model=Model(); memo=AudioFeatureMemo(model)
        f=torch.tensor([1.,2.]); l=torch.tensor([2])
        first=model.get_audio_features(f,l); second=model.get_audio_features(f.clone(),l.clone())
        self.assertIs(first,second); self.assertEqual(len(second[1]),2)
        model.get_audio_features(f+1,l); self.assertEqual(model.calls,2)
        memo.close(); model.get_audio_features(f,l); self.assertEqual(model.calls,3)

if __name__=='__main__': unittest.main()
