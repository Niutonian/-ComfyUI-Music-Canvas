"""Bounded-memory H3 full-song rendering, checkpointed on disk."""
import gc
import hashlib
import json
import math
import shutil
import subprocess
import time
from pathlib import Path


def plan_segments(samples, rate, seconds, fps=24):
    if samples<=0 or rate<=0 or not .25<=seconds<=15:
        raise ValueError('Provide nonempty audio and a segment length from 0.25 to 15 seconds')
    frames=math.ceil(samples/rate*fps)
    per=round(seconds*fps)
    return [dict(index=i,start_frame=start,frames=min(per,frames-start),
                 start_seconds=start/fps,duration=min(per,frames-start)/fps,
                 model_frames=5+17*math.ceil(max(0,min(per,frames-start)-5)/17))
            for i,start in enumerate(range(0,frames,per))]


def continuity_studio_timeline(timeline_json, samples, rate, seed, visual_memory=True, audio_file=None):
    """Convert Music Canvas timing to Continuity Studio's external Timeline v1."""
    source=json.loads(timeline_json)
    plan=plan_segments(samples,rate,float(source['segment_seconds']))
    _,prompts=timeline_prompts(timeline_json,'',plan)
    boxes=[]
    for slot,prompt in zip(plan,prompts):
        index=slot['index']
        boxes.append(dict(id=f'canvas-{index+1:04d}',frames=slot['frames'],exact=True,
            seed=(seed+index)%2**64,cut=index>0,memory='scene' if visual_memory and index>0 else 'off',
            prompt='Use @audio1 as the music timing reference. '+prompt))
    lane=dict(slot='audio1',start=0,source_start=0,duration=samples/rate,
              source_duration=samples/rate,description='Selected Music Canvas audio',layer='music')
    if audio_file is not None:
        lane.update(file=audio_file,in_full_video=True)
    return dict(version=1,prompt='',boxes=boxes,audio_clips=[lane])


class MusicCanvasContinuityExport:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required':dict(timeline_json=('STRING',{'forceInput':True}),audio=('AUDIO',),
            seed=('INT',{'default':42,'min':0,'max':2**64-1}),
            visual_memory=('BOOLEAN',{'default':True}))}

    RETURN_TYPES=('STRING','STRING')
    RETURN_NAMES=('studio_timeline_json','saved_timeline_path')
    FUNCTION='export'
    CATEGORY='Music Canvas'
    OUTPUT_NODE=True

    def export(self,timeline_json,audio,seed,visual_memory):
        import tempfile
        import folder_paths
        import soundfile as sf
        from comfy.model_management import throw_exception_if_processing_interrupted

        waveform=audio['waveform'].detach().cpu()
        rate=int(audio['sample_rate'])
        if waveform.ndim!=3 or waveform.shape[0]!=1 or waveform.shape[1] not in (1,2):
            raise ValueError('Continuity Studio export needs one mono or stereo audio track')
        samples=waveform.shape[-1]
        timeline=continuity_studio_timeline(timeline_json,samples,rate,seed,visual_memory)
        fingerprint=hashlib.sha256(json.dumps([timeline,rate,waveform.shape[1]],sort_keys=True).encode())
        for start in range(0,samples,rate*30):
            throw_exception_if_processing_interrupted()
            fingerprint.update(waveform[0,:,start:start+rate*30].contiguous().numpy().tobytes())
        subfolder='music_canvas/continuity_studio/'+fingerprint.hexdigest()
        descriptor=dict(type='output',subfolder=subfolder,filename='source_audio.wav')
        timeline['audio_clips'][0].update(file=descriptor,in_full_video=True)
        folder=Path(folder_paths.get_output_directory())/subfolder
        folder.mkdir(parents=True,exist_ok=True)
        audio_path=folder/'source_audio.wav'
        if not audio_path.is_file():
            with tempfile.NamedTemporaryFile(dir=folder,suffix='.wav',delete=False) as handle:
                temporary=Path(handle.name)
            try:
                with sf.SoundFile(str(temporary),mode='w',samplerate=rate,
                                  channels=waveform.shape[1],subtype='FLOAT') as stream:
                    for start in range(0,samples,rate*30):
                        throw_exception_if_processing_interrupted()
                        stream.write(waveform[0,:,start:start+rate*30].T.contiguous().numpy())
                temporary.replace(audio_path)
            finally:
                temporary.unlink(missing_ok=True)
        path=folder/'studio_timeline.json'
        if not path.is_file():atomic_json(path,timeline)
        return {'ui':{'text':[str(path)]},'result':(json.dumps(timeline,ensure_ascii=False),str(path))}


def choose_prompts(prompt, scenes, count):
    values=json.loads(scenes) if scenes.strip() else [prompt]
    if not isinstance(values,list) or not values or any(not isinstance(p,str) or not p.strip() for p in values):
        raise ValueError('Scene prompts must be a JSON array of nonempty strings')
    return [values[i%len(values)] for i in range(count)]


def timeline_prompts(timeline_json,scene_prompts_json,plan):
    """A directed timeline must cover the film exactly; never cycle its scenes."""
    timeline=json.loads(timeline_json)
    if not isinstance(timeline,dict) or not isinstance(timeline.get('segments'),list):
        raise ValueError('Connect the full Ollama timeline JSON')
    segments=timeline['segments']
    if len(segments)!=len(plan): raise ValueError('Timeline scene count does not match the selected audio range')
    prompts=[]
    for segment,slot in zip(segments,plan):
        if not isinstance(segment,dict) or any(segment.get(k)!=slot[k] for k in ('index','start_frame','frames')):
            raise ValueError('Timeline timing does not match the selected audio range and scene length')
        prompt=segment.get('prompt')
        if not isinstance(prompt,str) or not prompt.strip(): raise ValueError('Timeline contains an empty scene prompt')
        prompts.append(prompt)
    if len(set(prompts))!=len(prompts): raise ValueError('Directed timeline contains repeated scene prompts')
    if scene_prompts_json.strip() and json.loads(scene_prompts_json)!=prompts:
        raise ValueError('Scene prompt list and timeline disagree; connect both from the same planner')
    return timeline,prompts


def invoke(kind, **kwargs):
    import nodes
    cls=nodes.NODE_CLASS_MAPPINGS[kind]
    result=getattr(cls(),getattr(cls,'FUNCTION','execute'))(**kwargs)
    return result.result if hasattr(result,'result') else result


def atomic_json(path,value):
    temp=path.with_suffix('.tmp')
    temp.write_text(json.dumps(value,indent=2),encoding='utf-8')
    temp.replace(path)


def file_digest(path):
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''): digest.update(chunk)
    return digest.hexdigest()


def video_result(target,state,output_directory):
    """Expose a native lazy VIDEO and the same preview payload as SaveVideo."""
    from comfy_api.latest import InputImpl
    target=Path(target).resolve()
    relative=target.relative_to(Path(output_directory).resolve())
    preview=dict(filename=relative.name,subfolder=relative.parent.as_posix(),type='output')
    return {'ui':{'text':[str(target)],'images':[preview],'animated':[True]},
            'result':(str(target),json.dumps(state,indent=2),InputImpl.VideoFromFile(str(target)))}


def run_ffmpeg(arguments):
    import comfy.model_management as mm
    with __import__('tempfile').TemporaryFile() as log:
        process=subprocess.Popen([shutil.which('ffmpeg'),'-v','error','-y',*arguments],stdout=subprocess.DEVNULL,stderr=log)
        try:
            while process.poll() is None:
                mm.throw_exception_if_processing_interrupted()
                time.sleep(.1)
            if process.returncode:
                log.seek(0)
                raise RuntimeError('FFmpeg: '+log.read().decode(errors='replace')[-3000:])
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait()


def encode_frames(images,path,count):
    import comfy.model_management as mm
    h,w=images.shape[1:3]
    temp=path.with_suffix('.partial.mp4')
    with __import__('tempfile').TemporaryFile() as log:
        process=subprocess.Popen([shutil.which('ffmpeg'),'-v','error','-y','-f','rawvideo','-pix_fmt','rgb24',
            '-s',f'{w}x{h}','-r','24','-i','pipe:0','-an','-c:v','libx264','-crf','18','-pix_fmt','yuv420p',str(temp)],
            stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=log)
        try:
            if len(images)<count: raise RuntimeError('Decoder returned fewer frames than the segment requires')
            for frame in images[:count]:
                mm.throw_exception_if_processing_interrupted()
                process.stdin.write((frame[...,:3].clamp(0,1)*255).to(__import__('torch').uint8).cpu().numpy().tobytes())
            process.stdin.close()
            while process.poll() is None:
                mm.throw_exception_if_processing_interrupted()
                time.sleep(.1)
            if process.returncode:
                log.seek(0)
                raise RuntimeError(log.read().decode(errors='replace')[-3000:])
            temp.replace(path)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()


def reference_prompt(prompt,scene=None):
    role=('<Picture 1> is a design reference for the recurring subjects, materials and animation medium. '
          'Use the shot directions for the current setting, pose, framing, lighting and action.')
    if isinstance(scene,dict) and all(isinstance(scene.get(key),str) and scene[key].strip()
                                      for key in ('start_state','narrative_beat')):
        opening=scene['start_state'].strip().rstrip('.')
        event=scene['narrative_beat'].strip().rstrip('.')
        direction=(f'[Shot 1] Cut directly into the current state: {opening}. '
                   f'The new event for this segment is: {event}. '
                   'Begin with visible movement that advances this event. ')
        marker='[Shot 1]'
        if marker in prompt:
            prompt=prompt.replace('Opening state: '+opening+'. ','',1)
            return role+'\n'+prompt.replace(marker,direction,1)
    return role+' Begin with the new action and framing described for this segment.\n'+prompt


def render_segment(model,clip,vae,audio_vae,audio,prompt,segment,width,height,steps,seed,visual_reference=None,scene=None):
    import comfy.model_management as mm
    # Conditioning must be encoded before GPU sampling; no HTTP calls to our own queue.
    length=max(5,segment['model_frames'])
    if visual_reference is None:
        positive,latent=invoke('MiniMaxH3ImageToVideo',clip=clip,vae=vae,prompt=prompt,
            width=width,height=height,length=length)
    else:
        positive,latent=invoke('MiniMaxH3ReferenceToVideo',clip=clip,vae=vae,prompt=reference_prompt(prompt,scene),
            width=width,height=height,length=length,ref_images={'ref_image_1':visual_reference})
    positive=invoke('MiniMaxH3AddGuide',positive=positive,latent=latent,frame_idx=0,audio_vae=audio_vae,audio=audio)[0]
    shifted=invoke('MiniMaxH3SigmaShift',model=model,shift_video=12.,shift_audio=3.)[0]
    guider=invoke('BasicGuider',model=shifted,conditioning=positive)[0]
    sigmas=invoke('BasicScheduler',model=shifted,scheduler='beta',steps=steps,denoise=1.)[0]
    noise=invoke('RandomNoise',noise_seed=seed)[0]
    sampler=invoke('KSamplerSelect',sampler_name='euler')[0]
    sampled=invoke('SamplerCustomAdvanced',noise=noise,guider=guider,sampler=sampler,sigmas=sigmas,latent_image=latent)[0]
    video=invoke('LTXVSeparateAVLatent',av_latent=sampled)[0]
    del positive,latent,guider,sampled,noise,sigmas,sampler,shifted
    gc.collect()
    mm.throw_exception_if_processing_interrupted()
    return invoke('VAEDecode',samples=video,vae=vae)[0]


def save_visual_reference(images,count,path):
    import torch
    from PIL import Image
    frame=images[count//4,:,:,:3].clamp(0,1).mul(255).round().to(torch.uint8).cpu()
    temporary=path.with_suffix('.partial.png')
    Image.fromarray(frame.numpy()).save(temporary)
    temporary.replace(path)


def load_visual_reference(path):
    import numpy as np
    import torch
    from PIL import Image
    with Image.open(path) as image:
        return torch.from_numpy(np.array(image.convert('RGB'),dtype=np.float32)).div_(255).unsqueeze(0)


class MusicCanvasSequential:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required':dict(model=('MODEL',),clip=('CLIP',),vae=('VAE',),audio_vae=('VAE',),audio=('AUDIO',),
            prompt=('STRING',{'multiline':True,'default':'integrated_multimodal_description: [Shot 1] Expressive hand-drawn animation. A ribbon dancer leaps across a painted landscape, fabric following in sweeping arcs.\n\noverall_soundscape: N/A\n\nnon_diegetic_music: N/A'}),
            run_name=('STRING',{'default':'full_song','tooltip':'Project label. Run folders are numbered automatically; changed inputs start a fresh revision. Spaces and Unicode are supported.'}),segment_seconds=('FLOAT',{'default':15.,'min':.25,'max':15.,'step':.25}),
            width=('INT',{'default':432,'min':256,'max':2048,'step':16}),height=('INT',{'default':768,'min':256,'max':2048,'step':16}),
            steps=('INT',{'default':20,'min':1,'max':100}),seed=('INT',{'default':42,'min':0,'max':0xffffffffffffffff}),
            resume=('BOOLEAN',{'default':True,'tooltip':'Reuse the latest matching checkpoint for this project. Disable to create a fresh revision even with identical inputs.'})),
            'optional':dict(scene_prompts_json=('STRING',{'multiline':True,'default':''}),timeline_json=('STRING',{'forceInput':True}),
                visual_continuity=('BOOLEAN',{'default':False,'tooltip':'Use one image from the first segment as an H3 visual reference for all later segments.'})),
            'hidden':dict(prompt_graph='PROMPT',unique_id='UNIQUE_ID')}

    RETURN_TYPES=('STRING','STRING','VIDEO')
    RETURN_NAMES=('video_path','render_report','video')
    FUNCTION='generate'
    CATEGORY='Music Canvas'
    OUTPUT_NODE=True
    @classmethod
    def IS_CHANGED(cls,**kwargs): return float('nan')

    def generate(self,model,clip,vae,audio_vae,audio,prompt,run_name,segment_seconds,width,height,steps,seed,resume,scene_prompts_json='',prompt_graph=None,unique_id=None,timeline_json='',visual_continuity=False):
        import torch
        import folder_paths
        if not shutil.which('ffmpeg'): raise RuntimeError('FFmpeg must be available on PATH')
        waveform=audio['waveform'].detach().cpu()
        rate=int(audio['sample_rate'])
        if rate<=0: raise ValueError('Audio sample rate must be positive')
        if not 256<=width<=2048 or not 256<=height<=2048: raise ValueError('Video dimensions must be between 256 and 2048 pixels')
        width=width//16*16; height=height//16*16 # Match native H3 latent allocation.
        segment_seconds=float(segment_seconds)
        if waveform.ndim!=3 or waveform.shape[0]!=1 or waveform.shape[1]<1: raise ValueError('Provide one audio track with at least one channel')
        if waveform.shape[-1]==0: raise ValueError('Audio is empty')
        digest=hashlib.sha256()
        # Avoid a second full-song byte buffer and validate long audio in slices.
        for start in range(0,waveform.shape[-1],rate*30):
            chunk=waveform[:,:,start:start+rate*30]
            if not torch.isfinite(chunk).all(): raise ValueError('Audio contains nonfinite samples')
            digest.update(chunk.numpy().tobytes())
        plan=plan_segments(waveform.shape[-1],rate,segment_seconds)
        timeline=None
        if timeline_json.strip(): timeline,prompts=timeline_prompts(timeline_json,scene_prompts_json,plan)
        else: prompts=choose_prompts(prompt,scene_prompts_json,len(plan))
        from .model_identity import model_identity
        model_folders=[]
        for category in ('diffusion_models','unet','checkpoints','text_encoders','clip','vae','loras'):
            try: model_folders.extend(folder_paths.get_folder_paths(category))
            except KeyError: pass
        connected_models=model_identity(prompt_graph,unique_id,model_folders)
        config=dict(version=2,models=connected_models,audio_sha256=digest.hexdigest(),rate=rate,samples=waveform.shape[-1],
            channels=waveform.shape[1],segment_seconds=segment_seconds,width=width,height=height,steps=steps,seed=seed,prompts=prompts)
        if visual_continuity and len(plan)>1:
            config['visual_reference']='first_segment_quarter_frame_handoff_v2'
            if timeline is not None:
                config['reference_handoffs']=[reference_prompt(segment['prompt'],segment.get('scene'))
                    for segment in timeline['segments'][1:]]
        key=hashlib.sha256(json.dumps(config,sort_keys=True).encode()).hexdigest()
        from .run_folders import select_run
        base=Path(folder_paths.get_output_directory())/'music_canvas'/'sequential'
        with select_run(base,run_name,key,resume,connected_models['verified']) as selection:
            root=selection.root; state=selection.state
            if state is None:
                from datetime import datetime
                state=dict(config_hash=key,config=config,segments={},status='running',model_resume_note='Matching inputs and verified model revisions resume automatically within this project.',
                    created_at=datetime.now().astimezone().isoformat(timespec='seconds'),duration=waveform.shape[-1]/rate,
                    segment_count=len(plan),continuous_object_identity_guaranteed=False)
            state.update(project_label=run_name.strip() or 'music_canvas',project_folder=selection.project,
                run_id=root.name,run_folder=str(root),run_selection=selection.reason)
            atomic_json(root/'manifest.json',state)
            print(f'[MusicCanvas Sequential] {selection.reason}: {root}',flush=True)
            return self._render(model,clip,vae,audio_vae,waveform,rate,plan,prompts,width,height,steps,seed,root,state,timeline)

    def _render(self,model,clip,vae,audio_vae,waveform,rate,plan,prompts,width,height,steps,seed,root,state,timeline):
        import folder_paths
        import comfy.model_management as mm
        from comfy.utils import ProgressBar
        from .ollama_director import release_owned
        manifest=root/'manifest.json'
        if timeline is not None: atomic_json(root/'animation_timeline.json',timeline)
        bar=ProgressBar(len(plan))
        use_reference=bool(state['config'].get('visual_reference'))
        reference_path=root/'visual_reference.png'
        reference=None
        reference_digest=None
        try:
            release_owned()
            state.pop('error',None)
            for item in plan:
                mm.throw_exception_if_processing_interrupted()
                index=item['index']
                path=root/f'segment_{index:06d}.mp4'
                previous=state['segments'].get(str(index))
                if previous and path.is_file() and file_digest(path)==previous['sha256']:
                    if use_reference and index==0:
                        if reference_path.is_file() and file_digest(reference_path)==previous.get('visual_reference_sha256'):
                            reference=load_visual_reference(reference_path)
                            reference_digest=previous['visual_reference_sha256']
                    if not use_reference or (reference_digest and previous.get('visual_reference_sha256')==reference_digest):
                        bar.update_absolute(index+1)
                        continue
                begin=round(item['start_seconds']*rate)
                # Give the guide at least the native generation duration for short tails.
                end=min(waveform.shape[-1],begin+math.ceil(max(5,item['model_frames'])/24*rate))
                guide=dict(waveform=waveform[:,:,begin:end].clone(),sample_rate=rate)
                segment_seed=(seed+index)%2**64
                print(f'[MusicCanvas Sequential] Segment {index+1}/{len(plan)}, {item["start_seconds"]:.3f}s, seed {segment_seed}',flush=True)
                scene=timeline['segments'][index].get('scene') if timeline is not None else None
                images=render_segment(model,clip,vae,audio_vae,guide,prompts[index],item,width,height,steps,segment_seed,
                    visual_reference=reference,scene=scene)
                encode_frames(images,path,item['frames'])
                if use_reference and index==0:
                    save_visual_reference(images,item['frames'],reference_path)
                    reference=load_visual_reference(reference_path)
                    reference_digest=file_digest(reference_path)
                del images,guide
                gc.collect()
                mm.soft_empty_cache()
                state['segments'][str(index)]={**item,'seed':segment_seed,'file':path.name,'sha256':file_digest(path)}
                if use_reference:
                    state['segments'][str(index)]['visual_reference_sha256']=reference_digest
                state['status']='running'
                atomic_json(manifest,state)
                bar.update_absolute(index+1)
            import soundfile as sf
            wav=root/'source_audio.wav'
            if not wav.exists() or state.get('audio_file_sha256')!=file_digest(wav):
                wav_temp=root/'source_audio.partial.wav'
                with sf.SoundFile(str(wav_temp),mode='w',samplerate=rate,channels=waveform.shape[1],subtype='FLOAT') as stream:
                    for start in range(0,waveform.shape[-1],rate*30):
                        mm.throw_exception_if_processing_interrupted()
                        stream.write(waveform[0,:,start:start+rate*30].T.numpy())
                wav_temp.replace(wav)
                state['audio_file_sha256']=file_digest(wav)
                atomic_json(manifest,state)
            listing=root/'segments.txt'
            listing.write_text(''.join(f"file 'segment_{i:06d}.mp4'\n" for i in range(len(plan))),encoding='utf-8')
            target=root/'full_song.mp4'
            partial=root/'full_song.partial.mp4'
            run_ffmpeg(['-f','concat','-safe','0','-i',str(listing),'-i',str(wav),'-map','0:v:0','-map','1:a:0',
                '-c:v','copy','-c:a','aac','-b:a','192k','-t',str(state['duration']),'-movflags','+faststart',str(partial)])
            partial.replace(target)
            state.update(status='complete',video_path=str(target))
            state.pop('error',None)
            atomic_json(manifest,state)
            return video_result(target,state,folder_paths.get_output_directory())
        except BaseException as error:
            state.update(status='interrupted_or_failed',error=str(error))
            atomic_json(manifest,state)
            raise
