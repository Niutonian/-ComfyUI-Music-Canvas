"""No-network regression: download must precede model fingerprinting/cache lookup."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
from audio_assets import MOSS_REVISION

class Bootstrap(unittest.TestCase):
    def test_first_download_then_analysis_then_result_cache(self):
        self.check_result_cache('succeeded')

    def test_completed_partial_is_reused_until_analysis_changes(self):
        self.check_result_cache('partial')

    def check_result_cache(self,status):
        try: import torch
        except ImportError: self.skipTest('Requires the isolated torch runtime')
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); model=root/'missing_model'; beats=root/'missing_beats.ckpt'
            source=root/'source/src'; source.mkdir(parents=True)
            (source/'modeling_moss_music.py').write_text('# runtime')
            name='bootstrap_pack'
            package=types.ModuleType(name); package.__path__=[str(Path.cwd())]
            paths=types.ModuleType(name+'.model_paths')
            paths.DEFAULT_MOSS='MOSS-Music-8B-Instruct'; paths.DEFAULT_BEATS='beat_this-final0.ckpt'
            paths.resolve=lambda kind,value:model if kind=='moss_music' else beats
            folders=types.ModuleType('folder_paths'); folders.get_user_directory=lambda:str(root/'user')
            resources=types.ModuleType(name+'.resources'); resources.prepare_gpu=lambda:None
            calls=[]
            def worker(command,**kwargs):
                calls.append(command)
                if command[1].endswith('audio_assets.py'):
                    self.assertFalse(model.exists())
                    model.mkdir(); (model/'config.json').write_text('{}')
                    (model/'model.safetensors.index.json').write_text(json.dumps({'weight_map':{'x':'shard.safetensors'}}))
                    (model/'music_canvas_assets.json').write_text(json.dumps({'model_revision':MOSS_REVISION}))
                    (model/'shard.safetensors').write_bytes(b'weights'); beats.write_bytes(b'beats')
                else:
                    self.assertTrue(beats.exists())
                    output=Path(command[command.index('--output')+1])
                    output.write_text(json.dumps(dict(summary='valid evidence',analysis_status=status,runtime={},
                        chunks=[dict(summary='valid evidence')],warnings=['lyrics token limit'] if status=='partial' else [])))
                return dict(worker_exit_verified=True)
            resources.run_worker=worker
            with patch.dict(sys.modules,{name:package,name+'.model_paths':paths,name+'.resources':resources,'folder_paths':folders}),patch.dict('os.environ',{'MUSIC_CANVAS_MOSS_SOURCE':str(source.parent)}):
                spec=importlib.util.spec_from_file_location(name+'.nodes','nodes.py')
                module=importlib.util.module_from_spec(spec); sys.modules[spec.name]=module; spec.loader.exec_module(module)
                node=module.MusicCanvasAnalyze()
                options=dict(audio={'waveform':torch.ones(1,1,1600)*.1,'sample_rate':16000},
                    moss_model=paths.DEFAULT_MOSS,beat_model=paths.DEFAULT_BEATS,transcribe_lyrics=False,device='cuda:0',allow_model_download=True)
                first=json.loads(node.analyze(**options)[0]); second=json.loads(node.analyze(**options)[0])
                self.assertEqual(len(calls),2)
                self.assertFalse(first['cache_hit']); self.assertTrue(second['cache_hit'])
                self.assertEqual(first['analysis_id'],second['analysis_id'])
                self.assertEqual(second['analysis_status'],status)
                self.assertEqual(first['warnings'],second['warnings'])
                # A new node instance (as after memory eviction/restart) still uses disk.
                third=json.loads(module.MusicCanvasAnalyze().analyze(**options)[0])
                self.assertTrue(third['cache_hit']); self.assertEqual(len(calls),2)
                options['reanalyze']=1
                refreshed=json.loads(node.analyze(**options)[0])
                self.assertFalse(refreshed['cache_hit']); self.assertEqual(len(calls),3)
                self.assertNotEqual(first['analysis_id'],refreshed['analysis_id'])
                options['transcribe_lyrics']=True
                self.assertFalse(json.loads(node.analyze(**options)[0])['cache_hit'])
                self.assertEqual(len(calls),4)
                options['audio']={**options['audio'],'waveform':options['audio']['waveform']*.5}
                self.assertFalse(json.loads(node.analyze(**options)[0])['cache_hit'])
                self.assertEqual(len(calls),5)

if __name__=='__main__': unittest.main()
