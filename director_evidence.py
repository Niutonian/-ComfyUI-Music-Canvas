"""Bound long-song evidence without silently claiming complete prompt coverage."""
import json
import math


MOVEMENT_DIRECTION = '''Build the sequence around visible movement shaped by the music. Start an action in the opening shot. Give each phrase a preparation, readable physical accents and follow-through into a new pose, spacing or interaction. In a 10–15 second performance segment, use several connected movements with a change of direction, level, speed or pattern. Do not stretch one slow rise, turn or sway across the segment or split it into developments in multiple segments. For dance, frame actual foot contact when footwork carries the rhythm. Let quiet passages use restrained gestures, changes of weight and secondary motion. Use a short visible premise when needed; a change in choreography can be the whole development. Spend screen time on actions the viewer can see. Keep explicit artist directions and style locks.
Use the supplied local beat grid to choose a few action accents, such as a foot plant, a turn finishing, a rebound or an object impact. Favor downbeats for important phrase changes or purposeful cuts, leaving room for the action to read. Use the signal level only as a relative clue to movement size. Do not invent beats, drops, lyrics or precise sync. When timing evidence is absent, describe the physical phrasing without claiming exact timestamps. Camera movement supports the subject's action.'''


def measured_rhythm(analysis, start, duration):
    """Small timing summary in seconds relative to the requested clip or scene."""
    end = start + duration
    result = {}
    for source, target, limit in (
        ('beats', 'preferred_local_beats', 24),
        ('downbeats', 'preferred_local_downbeats', 12),
    ):
        times = sorted({round(t - start, 3) for t in analysis.get(source) or []
                        if type(t) in (int, float) and math.isfinite(t) and start <= t < end})
        if len(times) > limit:
            times = [times[round(i * (len(times) - 1) / (limit - 1))] for i in range(limit)]
        if times:
            result[target] = times

    thirds = [[], [], []]
    for sample in analysis.get('energy_envelope') or []:
        if not isinstance(sample, dict):
            continue
        time, rms = sample.get('time'), sample.get('rms')
        if (type(time) in (int, float) and type(rms) in (int, float)
                and start <= time < end and math.isfinite(rms) and rms >= 0):
            third = min(2, int(3 * (time - start) / duration))
            thirds[third].append(rms)
    if all(thirds):
        average = [sum(samples) / len(samples) for samples in thirds]
        peak = max(average)
        if peak:
            result['relative_signal_level_by_third'] = [round(value / peak, 2) for value in average]
    return result

def bound_evidence(evidence,budget):
    if len(json.dumps(evidence))<=budget: return evidence
    def trim(value,items,chars):
        if isinstance(value,str):
            if len(value)<=chars: return value
            lines=value.splitlines()
            if len(lines)>1:
                selected=lines if len(lines)<=items else [lines[round(i*(len(lines)-1)/(items-1))] for i in range(items)]
                per=max(1,chars//len(selected)-15)
                return '\n'.join(line[:per] for line in selected)+' [selected excerpts]'
            return value[:chars]+' [excerpt]'
        if isinstance(value,list):
            selected=value if len(value)<=items else [value[round(i*(len(value)-1)/(items-1))] for i in range(items)]
            return [trim(v,items,chars) for v in selected]
        if isinstance(value,dict): return {k:trim(v,items,chars) for k,v in value.items()}
        return value
    for items,chars in ((12,2000),(8,900),(4,400),(2,100)):
        result=trim(evidence,items,chars)
        result['evidence_scope']='A bounded selection of the supplied long-song evidence. Omitted detail is not evidence of absence; do not invent missing sections or lyrics.'
        if len(json.dumps(result))<=budget: return result
    raise ValueError('Artist direction and exclusions leave insufficient space for musical evidence; shorten those text fields')
