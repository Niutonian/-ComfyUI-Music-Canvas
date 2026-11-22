"""ComfyUI audio analysis nodes; heavy model dependencies stay in a worker."""
import json
import subprocess
import tempfile
import wave
import sys
import os
import hashlib
import time
from pathlib import Path
from . import model_paths
from .analysis_cache import reusable_analysis


class MusicCanvasAnalyze:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {
            'audio': ('AUDIO',),
            'moss_model': (model_paths.moss_names(),),
            'beat_model': (model_paths.beat_names(),),
            'transcribe_lyrics': ('BOOLEAN', {'default': False}),
            'device': (['cuda:0', 'cpu'],),
        }, 'optional': {
            'allow_model_download': ('BOOLEAN', {'default': False}),
            'chunk_seconds': ('INT', {'default': 30, 'min': 10, 'max': 60, 'step': 5}),
            'precision': (['4bit', 'bf16'],),
            'reanalyze': ('INT', {'default': 0, 'min': 0, 'max': 2147483647}),
            'analysis_profile': (['Quick direction','Detailed music','Lyrics'],),
            'structure': (['auto','on','off'],),
            'coverage_mode': (['full','sampled'],),
            'beat_device': (['cpu','cuda:0'],),
            'analysis_timeout_seconds': ('INT', {'default':3600,'min':0,'max':2147483647,'step':60,'tooltip':'Maximum worker time; 0 disables the timeout for long songs. Cancellation remains available.'}),
        }}

    RETURN_TYPES = ('STRING', 'STRING')
    RETURN_NAMES = ('analysis_json', 'musical_description')
    FUNCTION = 'analyze'
    CATEGORY = 'Music Canvas'

    def analyze(self, audio, moss_model, beat_model,
                transcribe_lyrics, device, allow_model_download=False, chunk_seconds=30, precision='4bit', reanalyze=0,
                analysis_profile='Quick direction',structure='auto',coverage_mode='full',beat_device='cpu',analysis_timeout_seconds=3600):
        began_parent=time.monotonic()
        import torch
        waveform = audio['waveform'].detach().cpu()
        rate = int(audio['sample_rate'])
        if waveform.ndim != 3 or waveform.shape[0] != 1 or waveform.shape[1]<1 or rate <= 0:
            raise ValueError('Expected one AUDIO item with shape [1, channels, samples]')
        if waveform.shape[-1] == 0 or not torch.isfinite(waveform).all():
            raise ValueError('Audio must contain finite, nonempty samples')
        pack = Path(__file__).parent
        config_file = pack / 'runtime_config.json'
        config = json.loads(config_file.read_text()) if config_file.is_file() else {}
        bundled_python = pack / '.audio-env' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
        worker_python = os.environ.get('MUSIC_CANVAS_PYTHON', config.get('python', str(bundled_python) if bundled_python.is_file() else sys.executable))
        moss_repository = os.environ.get('MUSIC_CANVAS_MOSS_SOURCE', config.get('source', str(pack / 'runtime' / 'MOSS-Music')))
        moss_checkpoint = model_paths.resolve('moss_music', moss_model)
        beat_checkpoint = model_paths.resolve('beat_this', beat_model)
        if not (Path(moss_repository) / 'src' / 'modeling_moss_music.py').is_file():
            raise RuntimeError('MOSS runtime source is missing. Run setup_runtime.py once; no node paths need configuration.')
        if allow_model_download:
            if moss_model!=model_paths.DEFAULT_MOSS or beat_model!=model_paths.DEFAULT_BEATS:
                raise ValueError('Automatic download supports the default named models only')
            from .audio_assets import assets_ready
            if not assets_ready(moss_checkpoint,beat_checkpoint):
                from .resources import run_worker
                run_worker([worker_python,str(pack/'audio_assets.py'),'--model',str(moss_checkpoint),'--beats',str(beat_checkpoint)],timeout=analysis_timeout_seconds)
        with tempfile.TemporaryDirectory(prefix='music_canvas_') as temp:
            source = Path(temp) / 'analysis.wav'
            mono = waveform[0].mean(dim=0).clamp(-1, 1)
            pcm=(mono*32767).to(torch.int16).numpy()
            pcm_hash=hashlib.sha256(memoryview(pcm)).hexdigest()
            result_path = Path(temp) / 'result.json'
            from .analysis_core import VERSION
            from .audio_performance import SEMANTIC_VERSION, asset_signature
            import folder_paths
            signature = [(str(p), p.stat().st_size, p.stat().st_mtime_ns)
                for p in list(moss_checkpoint.glob('*')) + [beat_checkpoint]
                if p.is_file() and not p.name.startswith('.')]
            identity = dict(version=VERSION, audio_sha256=pcm_hash,sample_rate=rate,
                models=signature, lyrics=transcribe_lyrics, device=device, precision=precision,
                chunk_seconds=chunk_seconds, overlap=2, reanalyze=reanalyze,
                semantic_version=SEMANTIC_VERSION,profile=analysis_profile,structure=structure,coverage=coverage_mode,
                beat_device=beat_device,source=asset_signature(Path(moss_repository)/'src'))
            if device=='cpu': identity['effective_precision']='bf16'
            key = hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()
            cache = Path(folder_paths.get_user_directory()) / 'MusicCanvas' / 'analysis_cache' / (key+'.json')
            if cache.is_file():
                try:
                    result = json.loads(cache.read_text(encoding='utf-8'))
                    if reusable_analysis(result):
                        result['cache_hit'] = True
                        result['runtime']['parent_cache_lookup_seconds']=time.monotonic()-began_parent
                        print('[MusicCanvas] Reusing completed audio analysis ('+result['analysis_status']+'); no model inference.',flush=True)
                        return json.dumps(result,ensure_ascii=False,indent=2), result['summary']
                except (OSError,ValueError,AttributeError): pass
            with wave.open(str(source), 'wb') as output:
                output.setnchannels(1)
                output.setsampwidth(2)
                output.setframerate(rate)
                output.writeframes(memoryview(pcm))
            command = [worker_python, str(Path(__file__).with_name('worker.py')),
                '--audio', str(source), '--output', str(result_path),
                '--repository', moss_repository, '--model', str(moss_checkpoint),
                '--beats', str(beat_checkpoint), '--device', device,
                '--chunk-seconds', str(chunk_seconds), '--precision', precision]
            command += ['--profile',analysis_profile,'--structure',structure,'--coverage',coverage_mode,
                '--beat-device',beat_device,'--reanalyze',str(reanalyze),
                '--stage-cache',str(Path(folder_paths.get_user_directory())/'MusicCanvas'/'stage_cache')]
            if transcribe_lyrics:
                command.append('--lyrics')
            if allow_model_download:
                if moss_model != model_paths.DEFAULT_MOSS or beat_model != model_paths.DEFAULT_BEATS:
                    raise ValueError('Automatic download supports the default named models only; select them or install your selected models locally.')
                command.append('--download')
            from .resources import prepare_gpu, run_worker
            if device.startswith('cuda') or beat_device.startswith('cuda'):
                prepare_gpu()
            began = time.monotonic()
            lifecycle = run_worker(command,timeout=analysis_timeout_seconds)
            result = json.loads(result_path.read_text(encoding='utf-8'))
            result['runtime']['worker_wall_seconds'] = time.monotonic()-began
            result['runtime']['parent_prepare_seconds']=began-began_parent
            result['runtime'].update(lifecycle)
            result.update(analysis_id=key, cache_hit=False, cache_identity=identity)
            if reusable_analysis(result):
                cache.parent.mkdir(parents=True,exist_ok=True)
                import uuid
                partial = cache.with_name(cache.name+'.'+uuid.uuid4().hex+'.partial')
                try:
                    partial.write_text(json.dumps(result,ensure_ascii=False,allow_nan=False),encoding='utf-8')
                    partial.replace(cache)
                finally:
                    partial.unlink(missing_ok=True)
        return json.dumps(result, ensure_ascii=False, indent=2), result['summary']


class MusicCanvasPrompt:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {
            'analysis_json': ('STRING', {'multiline': True}),
            'visual_direction': ('STRING', {'multiline': True, 'default': ''}),
            'motion_cycle': ('STRING', {'default': 'A slow cycle returning to the opening pose and lighting.'}),
        }}

    RETURN_TYPES = ('STRING', 'STRING')
    RETURN_NAMES = ('h3_prompt', 'brief_json')
    FUNCTION = 'compile'
    CATEGORY = 'Music Canvas'

    def compile(self, analysis_json, visual_direction, motion_cycle):
        analysis = json.loads(analysis_json)
        if not visual_direction.strip():
            raise ValueError('Describe the visible subject, environment and treatment')
        brief = dict(schema_version=1, musical_evidence=analysis['summary'],
            visual_direction=visual_direction, motion_cycle=motion_cycle,
            requested_duration=6, profile='spotify_canvas', synthesis='artist direction template')
        prompt = f'{visual_direction}\nLocked camera, portrait composition. {motion_cycle}\nContinuous motion, steady lighting, no cuts, captions or logos.'
        return prompt, json.dumps(brief, ensure_ascii=False, indent=2)


NODE_CLASS_MAPPINGS = {'MusicCanvasAnalyze': MusicCanvasAnalyze, 'MusicCanvasPrompt': MusicCanvasPrompt}
NODE_DISPLAY_NAME_MAPPINGS = {'MusicCanvasAnalyze': 'Music Canvas · Analyze Audio', 'MusicCanvasPrompt': 'Music Canvas · Animation Prompt'}


class MusicCanvasSave:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {key: ('STRING', {'multiline': True})
            for key in ('analysis_json', 'prompt', 'brief_json')},
            'optional': {key: ('STRING', {'forceInput': True}) for key in ('concepts_json', 'report_json', 'beat_report_json','timeline_json','story_plan_json','story_report_json')}}

    RETURN_TYPES = ()
    FUNCTION = 'save'
    CATEGORY = 'Music Canvas'
    OUTPUT_NODE = True

    def save(self, analysis_json, prompt, brief_json, concepts_json='', report_json='', beat_report_json='',timeline_json='',story_plan_json='',story_report_json=''):
        import folder_paths
        import uuid
        analysis, brief = json.loads(analysis_json), json.loads(brief_json)
        target = Path(folder_paths.get_output_directory()) / 'music_canvas' / uuid.uuid4().hex
        target.mkdir(parents=True)
        for name, value in [('analysis.json', analysis), ('animation_brief.json', brief)]:
            (target / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
        (target / 'prompt_h3.txt').write_text(prompt, encoding='utf-8')
        for name, value in [('concepts.json', concepts_json), ('director_report.json', report_json), ('beat_timing.json',beat_report_json),('animation_timeline.json',timeline_json),('story_plan.json',story_plan_json),('story_editor_report.json',story_report_json)]:
            if value:
                (target / name).write_text(json.dumps(json.loads(value), ensure_ascii=False, indent=2), encoding='utf-8')
        return {'ui': {'text': [str(target)]}}


NODE_CLASS_MAPPINGS['MusicCanvasSave'] = MusicCanvasSave
NODE_DISPLAY_NAME_MAPPINGS['MusicCanvasSave'] = 'Music Canvas · Save Analysis and Prompt'

from .ollama_director import MusicCanvasOllamaModel, MusicCanvasOllamaDirector, MusicCanvasOllamaRelease
NODE_CLASS_MAPPINGS.update(MusicCanvasOllamaModel=MusicCanvasOllamaModel, MusicCanvasOllamaDirector=MusicCanvasOllamaDirector, MusicCanvasOllamaRelease=MusicCanvasOllamaRelease)
NODE_DISPLAY_NAME_MAPPINGS.update(MusicCanvasOllamaModel='Music Canvas · Ollama Model', MusicCanvasOllamaDirector='Music Canvas · Ollama Director', MusicCanvasOllamaRelease='Music Canvas · Unload Ollama Before Video')

from .beat_sync import MusicCanvasBeatSync
NODE_CLASS_MAPPINGS['MusicCanvasBeatSync'] = MusicCanvasBeatSync
NODE_DISPLAY_NAME_MAPPINGS['MusicCanvasBeatSync'] = 'Music Canvas · Match Beat Motion'

from .sequential import MusicCanvasContinuityExport, MusicCanvasSequential
NODE_CLASS_MAPPINGS['MusicCanvasSequential'] = MusicCanvasSequential
NODE_DISPLAY_NAME_MAPPINGS['MusicCanvasSequential'] = 'Music Canvas · Full Song Sequential H3'
NODE_CLASS_MAPPINGS['MusicCanvasContinuityExport'] = MusicCanvasContinuityExport
NODE_DISPLAY_NAME_MAPPINGS['MusicCanvasContinuityExport'] = 'Music Canvas · Export H3 Continuity Timeline'

from .sequence_timing import MusicCanvasSequenceTiming
NODE_CLASS_MAPPINGS['MusicCanvasSequenceTiming'] = MusicCanvasSequenceTiming
NODE_DISPLAY_NAME_MAPPINGS['MusicCanvasSequenceTiming'] = 'Music Canvas · Video Duration and Test Range'

from .ollama_timeline import MusicCanvasOllamaTimeline
NODE_CLASS_MAPPINGS['MusicCanvasOllamaTimeline'] = MusicCanvasOllamaTimeline
NODE_DISPLAY_NAME_MAPPINGS['MusicCanvasOllamaTimeline'] = 'Music Canvas · Full Song Ollama Timeline'

from .story_planner import MusicCanvasOllamaStoryPlanner, MusicCanvasStoryHelper
NODE_CLASS_MAPPINGS['MusicCanvasOllamaStoryPlanner'] = MusicCanvasOllamaStoryPlanner
NODE_DISPLAY_NAME_MAPPINGS['MusicCanvasOllamaStoryPlanner'] = 'Music Canvas · Story Planner and Editor'
NODE_CLASS_MAPPINGS['MusicCanvasStoryHelper'] = MusicCanvasStoryHelper
NODE_DISPLAY_NAME_MAPPINGS['MusicCanvasStoryHelper'] = 'Music Canvas · Story Helper'
