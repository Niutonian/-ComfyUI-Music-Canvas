"""Isolated, offline MOSS-Music + Beat This inference with full-track coverage."""
WORKER_STARTED = __import__("time").monotonic()
import argparse
import gc
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import sys
import time
from analysis_core import VERSION, absolute_sections, chunk_ranges, json_response, rhythm_result, string_list, usable_caption, normalize_analysis
from runtime_security import disable_custom_generation,verify_beat_checkpoint

TASKS = {
    'description': 'Describe the audible instruments, rhythm, mood and production texture in two concise sentences. Return JSON with a summary string. Do not identify the track or artist, invent metadata, dates, keys, chords or exact tempo. Describe only what is heard.',
    'attributes': 'Analyze only audible evidence. Return a JSON object with keys style_tags, moods, instruments, production (arrays of short strings), and vocals (string or null). Unknown fields must be null. No commentary outside JSON.',
    'structure': 'Describe audible changes within this excerpt. Return JSON with a sections array of objects {"start": seconds, "end": seconds, "label": "brief observed musical change"}. Times are relative to this excerpt. Labels are estimates, not verified song structure. Return an empty array if no defensible boundary exists.',
    'lyrics': 'Transcribe only the sung lyrics in this excerpt. Mark unclear words [unclear]. If there are no intelligible vocals, return [no intelligible vocals]. Do not invent words. Timestamps are not required.',
}

SCHEMAS = {
    'description': {'type':'object','required':['summary'],'additionalProperties':False,
        'properties':{'summary':{'type':'string','maxLength':700}}},
    'attributes': {'type':'object','additionalProperties':False,
        'required':['style_tags','moods','instruments','production','vocals'],
        'properties':{**{key:{'anyOf':[{'type':'null'},{'type':'array','maxItems':6,'items':{'type':'string','maxLength':60}}]}
            for key in ('style_tags','moods','instruments','production')},
            'vocals':{'anyOf':[{'type':'null'},{'type':'string','maxLength':120}]}}},
    'structure': {'type':'object','required':['sections'],'additionalProperties':False,
        'properties':{'sections':{'type':'array','maxItems':6,'items':{'type':'object',
            'required':['start','end','label'],'additionalProperties':False,'properties':{
                'start':{'type':'number'},'end':{'type':'number'},'label':{'type':'string','maxLength':100}}}}}},
}


def main():
    from audio_performance import StageCache, SEMANTIC_VERSION, BUDGETS, identity, asset_signature, sampled_ranges, coverage, AudioFeatureMemo, FirstTokenClock, memory_snapshot
    phases={'memory_before':memory_snapshot()}
    def event(stage, **data):
        print(json.dumps(dict(event='music_canvas_progress',stage=stage,**data)),flush=True)
    event('starting')
    parser = argparse.ArgumentParser()
    for key in ('audio', 'output', 'repository', 'model', 'beats', 'device'):
        parser.add_argument('--' + key, required=True)
    parser.add_argument('--lyrics', action='store_true')
    parser.add_argument('--download', action='store_true')
    parser.add_argument('--chunk-seconds', type=float, default=30.)
    parser.add_argument('--overlap', type=float, default=2.)
    parser.add_argument('--precision', choices=['4bit','bf16'], default='4bit')
    parser.add_argument('--max-tokens', type=int, default=384)
    parser.add_argument('--profile', choices=['Quick direction','Detailed music','Lyrics'], default='Quick direction')
    parser.add_argument('--structure', choices=['auto','on','off'], default='auto')
    parser.add_argument('--coverage', choices=['full','sampled'], default='full')
    parser.add_argument('--beat-device', choices=['cpu','cuda:0'], default='cpu')
    parser.add_argument('--stage-cache', default='')
    parser.add_argument('--reanalyze',type=int,default=0)
    parser.add_argument('--reuse-features',choices=['on','off'],default='on')
    args = parser.parse_args()
    args.lyrics = args.lyrics or args.profile=='Lyrics'
    tasks=(['attributes'] if args.profile=='Quick direction' else ['description','attributes'])
    if args.structure=='on' or args.structure=='auto' and args.profile!='Quick direction': tasks.append('structure')
    if args.lyrics: tasks.append('lyrics')
    cache=StageCache(args.stage_cache or str(Path(args.output).parent/'stage_cache'))
    if args.download:
        from audio_assets import download
        download(args.model, args.beats)
    for item in (args.repository, args.model, args.beats, args.audio):
        if not item or not Path(item).exists():
            raise ValueError(f'Required local asset missing: {item!r}; run setup_runtime.py and install checkpoints')
    os.environ.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
    # Enforce offline inference, rather than relying only on HF's cache flags.
    import socket
    def offline_connect(*unused_args, **unused_kwargs):
        raise RuntimeError('Network access is disabled during audio inference; install assets during setup')
    socket.socket.connect = offline_connect
    socket.socket.connect_ex = offline_connect
    sys.path.insert(0, str(Path(args.repository).resolve()))
    import numpy as np
    import soundfile as sf
    import soxr
    torch=None

    phases["imports_seconds"]=time.monotonic()-WORKER_STARTED
    started = time.monotonic()
    signal, rate = sf.read(args.audio, dtype='float32', always_2d=True)
    mono = signal.mean(axis=1)
    if not len(mono) or not np.isfinite(mono).all():
        raise ValueError('Decoded audio is empty or contains nonfinite samples')
    if float(np.max(np.abs(mono))) < 1e-7:
        raise ValueError('Audio is silent; no defensible musical analysis can be produced')
    duration = len(mono)/rate
    ranges = chunk_ranges(duration, args.chunk_seconds, args.overlap)
    all_ranges=ranges
    if args.coverage=='sampled': ranges=sampled_ranges(ranges)
    audio_id=hashlib.sha256(Path(args.audio).read_bytes()).hexdigest()
    model_id=asset_signature(args.model)
    effective_precision=args.precision if args.device.startswith('cuda') else 'bf16'
    base_key=dict(version=SEMANTIC_VERSION,audio=audio_id,model=model_id,source=asset_signature(Path(args.repository)/'src'),
        precision=effective_precision,device=args.device,processor='mono-pcm16-soxr-v1',reanalyze=args.reanalyze)
    def task_key(task,offset,end):
        return dict(**base_key,task=task,prompt=TASKS[task],schema=SCHEMAS.get(task),start=offset,end=end,
            budget=min(args.max_tokens,BUDGETS[task]),retry_budget=max(384,args.max_tokens,min(args.max_tokens,BUDGETS[task])*2),decoding='sample-temp1-topk50-topp.8-rp1.1-taskseed-v1')
    def cached_task(task,offset,end):
        value=cache.get(task_key(task,offset,end))
        from analysis_cache import reusable_task
        if not reusable_task(value,task): return None
        try:
            if task in SCHEMAS:
                parsed=json_response(value['text'])
                if not isinstance(parsed,dict) or not set(SCHEMAS[task]['required']).issubset(parsed): return None
                if task=='description' and (not isinstance(parsed.get('summary'),str) or not usable_caption(parsed['summary'])): return None
                if task=='attributes' and any(parsed[k] is not None and not isinstance(parsed[k],list) for k in ('style_tags','moods','instruments','production')): return None
                if task=='attributes' and parsed['vocals'] is not None and not isinstance(parsed['vocals'],str): return None
                if task=='structure' and not isinstance(parsed['sections'],list): return None
        except (ValueError,TypeError): return None
        return value
    missing=any(cached_task(t,a,b) is None for a,b in ranges for t in tasks)
    model=processor=memo=tokenizer_data=None
    if missing:
        heavy_import_started=time.monotonic()
        import torch
        from transformers import BitsAndBytesConfig
        from src.modeling_moss_music import MossMusicModel
        from src.processing_moss_music import MossMusicProcessor
        disable_custom_generation(MossMusicModel)
        phases['imports_seconds']+=time.monotonic()-heavy_import_started
        torch.manual_seed(42)
        if args.device.startswith('cuda') and not torch.cuda.is_available():
            raise RuntimeError('CUDA requested but unavailable in the isolated audio runtime')
        if torch.cuda.is_available():
            torch.cuda.reset_peak_memory_stats()
        options = dict(trust_remote_code=False, use_safetensors=True, torch_dtype=torch.bfloat16,
            device_map={'': args.device}, local_files_only=True, attn_implementation='sdpa')
        if args.precision == '4bit' and args.device.startswith('cuda'):
            options['quantization_config'] = BitsAndBytesConfig(load_in_4bit=True,
                bnb_4bit_quant_type='nf4', bnb_4bit_compute_dtype=torch.bfloat16,
                llm_int8_skip_modules=['audio_encoder','audio_adapter','deepstack_audio_merger_list','lm_head'])
        event('model_loading',needed=missing)
        load_started=time.monotonic()
        model = MossMusicModel.from_pretrained(args.model, **options).eval()
        processor = MossMusicProcessor.from_pretrained(args.model, local_files_only=True, enable_time_marker=True)
        phases['model_load_seconds']=time.monotonic()-load_started
        memo=AudioFeatureMemo(model) if model is not None and args.reuse_features=='on' else None
        from lmformatenforcer import JsonSchemaParser
        from lmformatenforcer.integrations.transformers import build_token_enforcer_tokenizer_data, build_transformers_prefix_allowed_tokens_fn
        tokenizer_data = build_token_enforcer_tokenizer_data(processor.tokenizer)
    else:
        phases['model_load_seconds']=0.
        event('model_loading',needed=False)
    oom_error=torch.cuda.OutOfMemoryError if torch is not None else MemoryError
    preprocess_started=time.monotonic()
    target_rate=processor.config.mel_sr if processor is not None else rate
    raw=soxr.resample(mono,rate,target_rate) if rate!=target_rate else mono
    phases['resampling_seconds']=time.monotonic()-preprocess_started
    responses, chunks, sections, lyric_chunks, warnings = [], [], [], [], []
    if effective_precision!=args.precision:
        warnings.append('CPU inference uses BF16; the CUDA 4-bit quantization setting is not applied on CPU.')
    if coverage(ranges,duration)<.999999:
        warnings.append(f'Semantic analysis samples {len(ranges)} windows covering {coverage(ranges,duration):.1%} of the song; beat tracking covers the full input. This is not full-song semantic or lyric coverage.')
    task_hits=0
    completed_tasks=0
    total_tasks=len(ranges)*len(tasks)
    task_times=[]
    tags = {k: [] for k in ('style_tags','moods','instruments','production')}
    vocals = []

    def generate_task(task, chunk, offset, end):
        task_started=time.monotonic()
        torch.manual_seed(int(identity(task_key(task,offset,end))[:8],16))
        event('task_running',task=task,start=offset,end=end)
        feature_started=time.monotonic()
        inputs = processor(text=TASKS[task], audios=[chunk], return_tensors='pt').to(args.device)
        inputs['audio_data'] = inputs['audio_data'].to(torch.bfloat16)
        inputs['audio_input_mask'] = inputs['input_ids'] == processor.audio_token_id
        represented = int(inputs['audio_data_seqlens'][0]) * processor.config.mel_hop_length / target_rate
        if abs(represented - len(chunk)/target_rate) > .2:
            raise ValueError('Processor audio coverage differs from the supplied chunk; refusing truncated analysis')
        input_length = inputs['input_ids'].shape[1]
        constraints = {}
        if task in SCHEMAS:
            constraints['prefix_allowed_tokens_fn'] = build_transformers_prefix_allowed_tokens_fn(tokenizer_data,JsonSchemaParser(SCHEMAS[task]))
        preprocess_seconds=time.monotonic()-feature_started
        generation_started=time.monotonic()
        budget=min(args.max_tokens,BUDGETS[task])
        attempt_tokens=[]
        generation_attempts=[]
        task_seed=int(identity(task_key(task,offset,end))[:8],16)
        for limit in (budget,max(384,args.max_tokens,budget*2)):
            torch.manual_seed(task_seed)
            clock=FirstTokenClock()
            with torch.inference_mode():
                output = model.generate(**inputs, max_new_tokens=limit, do_sample=True,
                    temperature=1.0, top_p=.8, top_k=50, repetition_penalty=1.1, use_cache=True, streamer=clock, **constraints)
            attempt_tokens.append(int(output.shape[1]-input_length))
            candidate=processor.decode(output[0,input_length:],skip_special_tokens=True)
            valid=True
            if task in SCHEMAS:
                try: json_response(candidate)
                except (ValueError,TypeError): valid=False
            generation_attempts.append(dict(response=candidate,tokens=attempt_tokens[-1],limit=limit,valid_json=valid))
            if attempt_tokens[-1]<limit and valid: break
            if attempt_tokens[-1]<limit and not valid: task_seed=(task_seed+1)%2**32
            event('task_retry',task=task,limit=limit,reason='token_limit' if attempt_tokens[-1]>=limit else 'malformed_json')
        task_times.append(dict(task=task,start=offset,preprocess_seconds=preprocess_seconds,generation_seconds=time.monotonic()-generation_started,total_seconds=time.monotonic()-task_started,final_attempt_first_token_seconds=clock.first))
        text = processor.decode(output[0, input_length:], skip_special_tokens=True)
        generated = int(output.shape[1]-input_length)
        responses.append(dict(task=task, source_start=offset, source_end=end, response=text,
            prompt=TASKS[task], input_tokens=input_length, output_tokens=generated,
            attempt_output_tokens=attempt_tokens,retried=len(attempt_tokens)>1,generation_attempts=generation_attempts,
            possibly_truncated=generated >= limit,retry_exhausted=generated >= limit and len(attempt_tokens)>1))
        if generated >= limit:
            warnings.append(f'{task} at {offset:.2f}s reached its token limit; review raw response')
        event('task_completed',task=task,tokens=generated,truncated=generated>=limit)
        return text

    def ask(task,chunk,offset,end):
        nonlocal task_hits,completed_tasks
        key=task_key(task,offset,end)
        with cache.lock(key):
            stored=cached_task(task,offset,end)
            if stored is not None:
                task_hits+=1
                responses.append({**stored['raw'],'cache_hit':True})
                if stored['raw'].get('possibly_truncated'):
                    warnings.append(f'{task} at {offset:.2f}s reached its token limit; review raw response (cached completed attempt)')
                completed_tasks+=1
                event('task_cache_hit',task=task,start=offset,current=completed_tasks,total=total_tasks+2)
                return stored['text']
            text=generate_task(task,chunk,offset,end)
            raw_response=responses[-1]
            if task in SCHEMAS: json_response(text)
            if (not raw_response['possibly_truncated'] or raw_response.get('retry_exhausted')) and (task!='description' or usable_caption(json_response(text)['summary'])):
                cache.put(key,dict(text=text,raw=raw_response))
            completed_tasks+=1
            event('task_finished',task=task,current=completed_tasks,total=total_tasks+2)
            return text

    try:
        for index, (offset, end) in enumerate(ranges):
            if memo: memo.clear()
            event('chunk',current=completed_tasks,total=total_tasks+2)
            print(f'Analyzing chunk {index+1}/{len(ranges)}: {offset:.2f}–{end:.2f}s', flush=True)
            chunk = raw[round(offset*target_rate):round(end*target_rate)]
            entry = dict(start=offset, end=end, summary=None, attributes=None, task_errors={})
            for task in tasks:
                try:
                    text = ask(task, chunk, offset, end)
                    if task == 'description':
                        text = json_response(text)['summary']
                        if not usable_caption(text):
                            raise ValueError('Degenerate or repetitive caption rejected; raw response preserved')
                        entry['summary'] = text.strip()
                    elif task == 'attributes':
                        parsed = json_response(text)
                        entry['attributes'] = {key:string_list(parsed.get(key)) for key in tags}
                        for key in tags:
                            for value in entry['attributes'][key] or []:
                                if value.casefold() not in {x.casefold() for x in tags[key]}:
                                    tags[key].append(value)
                        if args.profile=='Quick direction':
                            entry['summary']='Model-estimated musical attributes; see reviewed tags.'
                        if isinstance(parsed.get('vocals'), str) and parsed['vocals'].strip().casefold() not in ('null','none','unknown'):
                            vocals.append(dict(start=offset,end=end,observation=parsed['vocals']))
                    elif task == 'structure':
                        parsed = json_response(text)
                        sections.extend(absolute_sections(parsed.get('sections') if isinstance(parsed,dict) else parsed, offset, end))
                    else:
                        lyric_chunks.append(dict(start=offset,end=end,text=text,timing='untimed words; chunk boundaries only'))
                except oom_error:
                    raise
                except Exception as exc:
                    entry['task_errors'][task] = f'{type(exc).__name__}: {exc}'
                    warnings.append(f'{task} unavailable for {offset:.2f}–{end:.2f}s; see task_errors')
            chunks.append(entry)
    finally:
        cleanup_started=time.monotonic()
        feature_hits=memo.hits if memo else 0
        phases['audio_encoder_seconds']=memo.encoder_seconds if memo else None
        if memo: memo.close()
        memo=None
        del model, processor
        gc.collect()
        if torch is not None and torch.cuda.is_available():
            peak_memory = torch.cuda.max_memory_allocated()
            torch.cuda.empty_cache()
            remaining_memory = torch.cuda.memory_allocated()
        else:
            peak_memory = None
            remaining_memory = None

    phases['moss_cleanup_seconds']=time.monotonic()-cleanup_started
    event('beats',device=args.beat_device,current=total_tasks+1,total=total_tasks+2)
    beat_started=time.monotonic()
    # Verified in upstream Postprocessor.__call__: beats first, downbeats second.
    beat_key=dict(version='beat-this-final0-v1',audio=audio_id,checkpoint=asset_signature(args.beats),device=args.beat_device,dbn=False,reanalyze=args.reanalyze)
    with cache.lock(beat_key):
        rhythm=cache.get(beat_key)
        beat_hit=rhythm is not None
        if rhythm is None:
            verify_beat_checkpoint(args.beats,importlib.metadata.version('torch'))
            from beat_this.inference import Audio2Beats
            tracker=Audio2Beats(checkpoint_path=str(Path(args.beats).resolve()),device=args.beat_device,dbn=False)
            beats,downbeats=tracker(mono,rate)
            rhythm=rhythm_result(beats,downbeats,duration)
            cache.put(beat_key,rhythm)
            del tracker
    rhythm=dict(rhythm)
    warnings.extend(rhythm.pop('warnings',[]))
    phases['beats_seconds']=time.monotonic()-beat_started
    block = max(1, round(rate*.1))
    energy = [dict(time=i/rate,rms=float(np.sqrt(np.mean(mono[i:i+block]**2)))) for i in range(0,len(mono),block)]
    summary = '\n'.join(f'[{x["start"]:.2f}–{x["end"]:.2f}s] {x["summary"]}' for x in chunks if x['summary'])
    complete = all(x['summary'] for x in chunks)
    manifest_path = Path(args.model)/'music_canvas_assets.json'
    manifest = json.loads(manifest_path.read_text()) if manifest_path.is_file() else {}
    result = dict(schema_version=2, pipeline_version=VERSION, summary=summary or 'No musical description was produced; inspect task errors.',
        analysis_status='succeeded' if complete and all(not x['task_errors'] for x in chunks) else 'partial', full_track_coverage=complete and coverage(ranges,duration)>.999999,
        duration=duration, source_sample_rate=rate, source_channels=signal.shape[1],
        analysis_input_sha256=hashlib.sha256(Path(args.audio).read_bytes()).hexdigest(),
        chunk_seconds=args.chunk_seconds, overlap_seconds=args.overlap, chunks=chunks,
        **{key:values or None for key,values in tags.items()}, vocals=vocals or None,
        sections=sorted(sections,key=lambda x:x['start']) or None,
        section_warning='Overlapping chunk estimates are retained separately, not claimed to be definitive verse/chorus boundaries.',
        lyrics_status=('estimated_untimed' if lyric_chunks else 'failed') if args.lyrics else 'skipped',
        lyrics=lyric_chunks or None, lyrics_approved=False,
        energy_envelope=energy, energy_description='Signal RMS, not emotional intensity', **rhythm,
        model_path=args.model, model_revision=manifest.get('model_revision'), source_revision=manifest.get('source_revision'),
        beat_sha256=hashlib.sha256(Path(args.beats).read_bytes()).hexdigest(), precision=effective_precision,requested_precision=args.precision,
        raw_responses=responses, warnings=warnings + ['Model descriptions, instruments, moods, lyrics and section labels are estimates requiring artist review.'],
        runtime=dict(seconds=time.monotonic()-started, peak_cuda_allocated_bytes=peak_memory,
            cuda_allocated_after_moss_release=remaining_memory,
            versions={key:importlib.metadata.version(key) for key in ('torch','transformers','beat_this','bitsandbytes')},
            moss_released_before_beats=True, heavy_models_released_on_worker_exit=True))
    result = normalize_analysis(result)
    result.update(analysis_profile=args.profile,analyzed_ranges=ranges,coverage_ratio=coverage(ranges,duration),
        coverage_mode=args.coverage,full_track_coverage=complete and coverage(ranges,duration)>.999999)
    result['runtime'].update(phases=phases,task_timings=task_times,task_cache_hits=task_hits,
        task_cache_misses=len(task_times),beat_cache_hit=beat_hit,audio_feature_cache_hits=feature_hits,
        total_worker_seconds=time.monotonic()-WORKER_STARTED)
    phases['memory_after']=memory_snapshot()
    if any(r.get('possibly_truncated') for r in responses): result['analysis_status']='partial'
    event('complete',current=total_tasks+2,total=total_tasks+2)
    destination = Path(args.output)
    destination.parent.mkdir(parents=True,exist_ok=True)
    temporary = destination.with_suffix('.partial')
    temporary.write_text(json.dumps(result,ensure_ascii=False,allow_nan=False),encoding='utf-8')
    temporary.replace(destination)
    print(f'Audio understanding complete: {result["analysis_status"]}',flush=True)


if __name__ == '__main__':
    main()
