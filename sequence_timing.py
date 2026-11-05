"""Separate total video length from bounded native H3 scene length."""
import math


def timing_range(samples,rate,start_seconds,total_seconds,segment_seconds):
    if rate<=0 or samples<=0 or not all(math.isfinite(v) for v in (start_seconds,total_seconds,segment_seconds)):
        raise ValueError('Provide finite durations and nonempty audio')
    if start_seconds<0 or total_seconds<0 or segment_seconds<=0:
        raise ValueError('Start and total duration must be nonnegative; segment duration must be positive')
    start=round(start_seconds*rate)
    end=samples if total_seconds==0 else min(samples,start+round(total_seconds*rate))
    if start>=end or end-start<rate/24:
        raise ValueError('Choose an audio range containing at least one video frame')
    # Short tests need short native renders; long requests stay in the trained window.
    per=max(.25,min(15.,segment_seconds,(end-start)/rate))
    return start,end,per


class MusicCanvasSequenceTiming:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required':dict(audio=('AUDIO',),
            start_seconds=('FLOAT',{'default':0.,'min':0.,'step':.25}),
            total_seconds=('FLOAT',{'default':0.,'min':0.,'step':.25,'tooltip':'0 = whole song; 1 = one-second test; 30 = thirty-second video.'}),
            segment_seconds=('FLOAT',{'default':15.,'min':.25,'max':15.,'step':.25}))}
    RETURN_TYPES=('AUDIO','FLOAT','FLOAT')
    RETURN_NAMES=('selected_audio','scene_seconds','selected_seconds')
    FUNCTION='select'
    CATEGORY='Music Canvas'

    def select(self,audio,start_seconds,total_seconds,segment_seconds):
        waveform=audio['waveform']
        if waveform.ndim!=3 or waveform.shape[0]!=1 or waveform.shape[1]<1:
            raise ValueError('Provide one AUDIO item with shape [1, channels, samples]')
        a,b,per=timing_range(waveform.shape[-1],int(audio['sample_rate']),start_seconds,total_seconds,segment_seconds)
        return dict(waveform=waveform[...,a:b],sample_rate=audio['sample_rate']),per,(b-a)/int(audio['sample_rate'])
