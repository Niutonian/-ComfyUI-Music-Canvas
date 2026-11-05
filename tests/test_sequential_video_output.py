import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
from sequential import MusicCanvasSequential,video_result

class VideoOutputContract(unittest.TestCase):
    def test_preview_and_video_preserve_existing_ports(self):
        lazy=object()
        api=types.ModuleType('comfy_api.latest')
        api.InputImpl=types.SimpleNamespace(VideoFromFile=lambda path:lazy)
        with tempfile.TemporaryDirectory() as temp,patch.dict(sys.modules,{'comfy_api':types.ModuleType('comfy_api'),'comfy_api.latest':api}):
            root=Path(temp); target=root/'music_canvas/sequential/demo/full_song.mp4'
            target.parent.mkdir(parents=True); target.write_bytes(b'existing video')
            result=video_result(target,{'status':'complete'},root)
            self.assertEqual(MusicCanvasSequential.RETURN_TYPES,('STRING','STRING','VIDEO'))
            self.assertEqual(result['result'][0],str(target.resolve()))
            self.assertEqual(json.loads(result['result'][1])['status'],'complete')
            self.assertIs(result['result'][2],lazy)
            self.assertEqual(result['ui']['images'][0],dict(filename='full_song.mp4',subfolder='music_canvas/sequential/demo',type='output'))
            self.assertEqual(result['ui']['animated'],[True])
            self.assertEqual(target.read_bytes(),b'existing video')

if __name__=='__main__': unittest.main()
