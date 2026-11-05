import hashlib
import importlib
import io
import sys
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch
import audio_assets
from runtime_security import disable_custom_generation,verify_sha256,verify_beat_checkpoint,version_tuple

class RuntimeSecurity(unittest.TestCase):
    def test_custom_generation_is_blocked_before_the_loader_is_called(self):
        calls=[]
        class Model:
            def load_custom_generate(self,*args,**kwargs):calls.append(True)
        disable_custom_generation(Model)
        with self.assertRaisesRegex(OSError,'disabled'):Model().load_custom_generate('untrusted/repo')
        self.assertEqual(calls,[])

    def test_existing_checkpoint_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'beat_this-final0.ckpt';path.write_bytes(b'wrong bytes')
            with self.assertRaisesRegex(ValueError,'checksum mismatch'):verify_beat_checkpoint(path,'2.9.1+cu128')

    def test_verified_checkpoint_is_accepted_and_prereleases_are_not_stable(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'file.ckpt';path.write_bytes(b'known')
            expected=hashlib.sha256(b'known').hexdigest()
            self.assertEqual(verify_sha256(path,expected),expected)
        self.assertEqual(version_tuple('2.10.0+cu128'),(2,10,0))
        with self.assertRaises(ValueError):version_tuple('2.10.0rc1')

    def test_custom_checkpoint_is_refused_on_vulnerable_torch(self):
        with self.assertRaisesRegex(RuntimeError,'Torch 2.10.0'):verify_beat_checkpoint('custom.ckpt','2.9.1+cu128')
        self.assertIsNone(verify_beat_checkpoint('custom.ckpt','2.10.0+cu128'))

    def test_failed_download_does_not_publish_a_checkpoint(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);model=root/'model';model.mkdir();beat=root/'beat_this-final0.ckpt'
            hub=types.ModuleType('huggingface_hub');hub.snapshot_download=lambda **kwargs:None
            with patch.dict(sys.modules,{'huggingface_hub':hub}),patch.object(audio_assets,'model_ready',return_value=True),patch.object(audio_assets.urllib.request,'urlopen',return_value=io.BytesIO(b'bad checkpoint')):
                with self.assertRaisesRegex(ValueError,'checksum mismatch'):audio_assets.download(model,beat)
            self.assertFalse(beat.exists());self.assertFalse(beat.with_suffix('.partial').exists())

    def test_verified_download_is_published_and_recorded(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);model=root/'model';model.mkdir();beat=root/'beat_this-final0.ckpt'
            good=b'known checkpoint';digest=hashlib.sha256(good).hexdigest()
            hub=types.ModuleType('huggingface_hub');hub.snapshot_download=lambda **kwargs:None
            with patch.dict(sys.modules,{'huggingface_hub':hub}),patch.object(audio_assets,'BEAT_SHA256',digest),patch.object(audio_assets,'model_ready',return_value=True),patch.object(audio_assets.urllib.request,'urlopen',return_value=io.BytesIO(good)):
                result=audio_assets.download(model,beat)
            self.assertEqual(result['beat_sha256'],digest);self.assertEqual(beat.read_bytes(),good)

if __name__=='__main__':unittest.main()
