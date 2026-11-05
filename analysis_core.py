"""Pure timestamp/normalization helpers shared with focused tests."""
import json
import math
import statistics
import re
import unicodedata

VERSION = 'audio-understanding-4'


def chunk_ranges(duration, seconds=30., overlap=2.):
    if not math.isfinite(duration) or duration <= 0 or not 0 <= overlap < seconds:
        raise ValueError('Invalid source duration or chunk overlap')
    spans = []
    start = 0.
    while start < duration:
        end = min(start + seconds, duration)
        spans.append((start, end))
        if end >= duration:
            break
        start = end - overlap
    return spans


def bounded_times(values, duration):
    return sorted({float(x) for x in values if math.isfinite(float(x)) and 0 <= float(x) <= duration})


def rhythm_result(beats, downbeats, duration):
    beats, downbeats = bounded_times(beats, duration), bounded_times(downbeats, duration)
    intervals = [b-a for a,b in zip(beats, beats[1:]) if b > a]
    warnings = ['Half/double-tempo ambiguity is unresolved; timestamps are estimates.']
    bpm = None
    if len(intervals) >= 3:
        median = statistics.median(intervals)
        deviation = statistics.median(abs(x-median) for x in intervals) / median
        if deviation < .25:
            bpm = 60/median
        else:
            warnings.append('Irregular inter-beat intervals; global tempo withheld.')
    else:
        warnings.append('Too few beats for a defensible global tempo.')
    return dict(beats=beats, downbeats=downbeats, tempo_bpm=bpm,
        tempo_method='median inter-beat interval, at least 4 beats; withheld for irregular rhythm', warnings=warnings)


def json_response(text):
    cleaned = text.strip()
    if cleaned.startswith('```'):
        cleaned = '\n'.join(cleaned.splitlines()[1:-1])
    return json.loads(cleaned)


def string_list(value):
    if isinstance(value, list):
        result = []
        for item in value:
            if isinstance(item, str) and item.strip():
                result.append(item.strip())
            elif isinstance(item, dict):
                labels = [item[k].strip() for k in ('genre','subgenre','mood','instrument','type','name','tag','texture')
                    if isinstance(item.get(k), str) and item[k].strip()]
                if labels:
                    result.append(' / '.join(labels))
        return result or None
    return None


def usable_caption(text):
    if not isinstance(text,str) or len(text.split()) < 8 or re.search(r'\d{12,}|\bmetadata\b|\bkey detection\b|excerpt from ["“]',text,re.I):
        return False
    words = text.casefold().split()
    phrases = [tuple(words[i:i+5]) for i in range(len(words)-4)]
    return not phrases or max(phrases.count(p) for p in set(phrases)) < 4


def normalize_analysis(value):
    """Keep raw caption claims out of director evidence; use bounded estimated tags."""
    value = dict(value)
    if value.get('normalization_version') == 3:
        return value
    keys = ('style_tags','moods','instruments','production')
    value.setdefault('raw_music_caption',value.get('summary'))
    value.setdefault('raw_tag_estimates',{key:value.get(key) for key in keys})
    rejected = []
    def clean(labels, category=None):
        output = []
        for label in labels or []:
            if not isinstance(label,str):
                continue
            text = label.strip().replace('_',' ')
            if len(text)>=58 or len(text.split())>9 or text.endswith('-') or text.count('-')>4 or re.search(r'\b(no|not|ignore|unknown|likely|maybe|metadata)\b|[?\[\]%<>]|\b\d+\s*(?:bpm|db|hz|khz|seconds)\b|\b(?:19|20)\d{2}\b',text,re.I) or any(c.isalpha() and ord(c)>127 and 'LATIN' not in unicodedata.name(c,'') for c in text):
                rejected.append(label)
                continue
            if category == 'instruments':
                canonical = next((name for pattern,name in (
                    ('synth','synthesizer'),('electricguitar','electric guitar'),('electric guitar','electric guitar'),
                    ('acoustic guitar','acoustic guitar'),('guitar','guitar'),('drum machine','drum machine'),
                    ('drum-machine','drum machine'),('drum','drums'),('bass','bass'),('keyboard','keyboard'),
                    ('piano','piano'),('percussion','percussion'),('violin','violin'),('cello','cello'),
                    ('strings','strings'),('saxophone','saxophone'),('trumpet','trumpet'),('flute','flute'))
                    if pattern in text.casefold()),None)
                if canonical is None:
                    rejected.append(label)
                    continue
                text = canonical
            if text and text.casefold() not in {x.casefold() for x in output}:
                output.append(text)
        return output or None
    for key in keys:
        value[key] = clean(value['raw_tag_estimates'].get(key),key)
    lines = ['MOSS-Music estimates requiring artist review; measured rhythm is reported separately.']
    for chunk in value.get('chunks',[]):
        attributes = chunk.get('attributes') or {}
        descriptions = [f'{key}: {", ".join(labels)}' for key in keys if (labels:=clean(attributes.get(key),key))]
        lines.append(f'[{chunk["start"]:.2f}–{chunk["end"]:.2f}s] '+('; '.join(descriptions) if descriptions else 'No usable structured musical tags; review raw responses.'))
    if value.get('tempo_bpm') is not None:
        lines.append(f'Beat This median-interval tempo estimate: {value["tempo_bpm"]:.2f} BPM; half/double-tempo ambiguity remains.')
    value['summary'] = '\n'.join(lines)
    value['normalization_version'] = 3
    if value.get('lyrics'):
        rejected_starts = {x['source_start'] for x in value.get('raw_responses',[]) if x.get('task')=='lyrics' and x.get('possibly_truncated')}
        value['lyrics_rejected_chunks'] = [x for x in value['lyrics'] if x['start'] in rejected_starts]
        value['lyrics'] = [x for x in value['lyrics'] if x['start'] not in rejected_starts] or None
        if rejected_starts:
            value['lyrics_status'] = 'partial_unverified_untimed; truncated chunks excluded'
    value['requires_artist_review'] = True
    value['rejected_tag_estimates'] = sorted(set(rejected))
    value['field_status'] = {key:'model_estimate' if value[key] else 'unknown_or_unavailable; inspect raw_responses and chunk task_errors' for key in keys}
    value['warnings'] = list(value.get('warnings',[])) + [
        'Raw free-form captions may contain unsupported identity, harmonic, numeric or loudness claims; they are excluded from director evidence.',
        'Musical tags and section boundaries remain unverified estimates. Conflicting chunk tags are retained for review.']
    return value


def absolute_sections(items, offset, end):
    result = []
    for item in items if isinstance(items, list) else []:
        try:
            a, b = float(item['start']), float(item['end'])
            if not (math.isfinite(a) and math.isfinite(b) and 0 <= a < b <= end-offset):
                continue
            label = item.get('label')
            if not isinstance(label, str):
                continue
            result.append(dict(start=offset+a, end=offset+b, label=label,
                estimated=True, chunk_offset=offset))
        except (ValueError, TypeError, KeyError):
            continue
    return result
