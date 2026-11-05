"""Measured beat timing -> reversible motion retiming and gentle camera accents."""
import bisect
import json
import math


def beat_plan(analysis, start, source_frames, fps=24., strength=.75):
    if not 0<=strength<=1 or fps<=0 or source_frames<2:
        raise ValueError('Invalid strength, frame rate or source frame count')
    if strength==0:
        return dict(disabled=True,frame_count=source_frames,duration=source_frames/fps,fps=fps,
            source_positions=list(range(source_frames)),zooms=[1.]*source_frames,events=[])
    beats=sorted(set(float(t) for t in analysis.get('beats',[]) if math.isfinite(float(t))))
    downbeats=sorted(set(float(t) for t in analysis.get('downbeats',[]) if math.isfinite(float(t))))
    if len(beats)<4 or start<0:
        raise ValueError('Beat matching needs a usable measured beat grid and a nonnegative excerpt start')
    desired=source_frames/fps
    endings=[t for t in downbeats if 3<=t-start<=8]
    method='inferred-downbeat-to-downbeat' if any(abs(start-d)<.025 for d in downbeats) else 'end-downbeat aligned; start is not a downbeat'
    if not endings:
        endings=[t for t in beats if 3<=t-start<=8]
        method='beat-boundary fallback'
    if not endings:
        raise ValueError('No measured beat boundary inside the Canvas duration range')
    end=min(endings,key=lambda t:abs((t-start)-desired))
    count=round((end-start)*fps)
    duration=count/fps
    events=[]
    for t in beats:
        relative=t-start
        if 0<=relative<duration and round(relative*fps)<count:
            events.append(dict(time=relative,frame=round(relative*fps),
                downbeat=any(abs(t-d)<.025 for d in downbeats)))
    if len(events)<4:
        raise ValueError('Too few measured beats inside the selected loop')
    interval=min((b['time']-a['time'] for a,b in zip(events,events[1:]) if b['time']>a['time']),default=.5)
    width=min(.09,interval*.2)
    boundaries=sorted(set([0.,duration]+[e['time'] for e in events if 0<e['time']<duration]))
    positions,zooms=[],[]
    for frame in range(count):
        t=frame/fps
        idx=min(len(boundaries)-2,max(0,bisect.bisect_right(boundaries,t)-1))
        left,right=boundaries[idx:idx+2]
        q=(t-left)/(right-left)
        # Continuous positive speed, fastest at each measured beat.
        phase=left+(right-left)*(q+strength*.8*math.sin(2*math.pi*q)/(2*math.pi))
        positions.append(phase/duration*source_frames)
        accent=0.
        for event in events:
            distance=abs(t-event['time'])
            distance=min(distance,duration-distance)
            amplitude=(.06 if event['downbeat'] else .035)*strength
            accent+=amplitude*math.exp(-.5*(distance/width)**2)
        zooms.append(1+min(.065,accent))
    return dict(disabled=False,frame_count=count,duration=duration,fps=fps,strength=strength,
        source_frame_count=source_frames,source_positions=positions,zooms=zooms,events=events,
        excerpt_start=start,measured_end=end,frame_quantization_error_seconds=duration-(end-start),
        alignment_method=method,method='beat-shaped motion speed plus smooth central camera accents; brightness unchanged',
        model_motion_itself_was_not_beat_locked=True,
        spotify_playback_phase_synchronization=False)


def frame_transform(get_frame, plan, index, base_grid):
    import torch
    import torch.nn.functional as F
    position=plan['source_positions'][index]
    count=plan['source_frame_count']
    first=int(math.floor(position))%count
    second=(first+1)%count
    fraction=position-math.floor(position)
    image=get_frame(first)*(1-fraction)+get_frame(second)*fraction
    grid=base_grid/plan['zooms'][index]
    return F.grid_sample(image.permute(2,0,1).unsqueeze(0),grid,mode='bilinear',padding_mode='border',align_corners=False)[0].permute(1,2,0).clamp(0,1)


class MusicCanvasBeatSync:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required':dict(images=('IMAGE',),analysis_json=('STRING',{'multiline':True,'default':'{}'}),
            excerpt_start=('FLOAT',{'default':0.,'min':0.,'step':.01}),
            fps=('FLOAT',{'default':24.,'min':1.,'max':60.}),
            strength=('FLOAT',{'default':.75,'min':0.,'max':1.,'step':.05}))}

    RETURN_TYPES=('IMAGE','STRING','FLOAT')
    RETURN_NAMES=('beat_frames','timing_report','duration_seconds')
    FUNCTION='match'
    CATEGORY='Music Canvas'

    def match(self,images,analysis_json,excerpt_start,fps,strength):
        import torch
        import torch.nn.functional as F
        import comfy.model_management as mm
        if images.ndim!=4 or len(images)<2:
            raise ValueError('Connect the decoded video IMAGE batch')
        plan=beat_plan(json.loads(analysis_json),excerpt_start,len(images),fps,strength)
        if plan['disabled']:
            return images,json.dumps(plan),plan['duration']
        source=images.detach().to(device='cpu',dtype=torch.float32)
        n,h,w,c=source.shape
        base=F.affine_grid(torch.tensor([[[1.,0.,0.],[0.,1.,0.]]]),[1,c,h,w],align_corners=False)
        output=torch.empty((plan['frame_count'],h,w,c),dtype=torch.float32)
        for i in range(len(output)):
            mm.throw_exception_if_processing_interrupted()
            output[i]=frame_transform(lambda j:source[j],plan,i,base)
        return output,json.dumps(plan,indent=2),plan['duration']
