"""Reuse completed analysis, including explicitly reported model limitations."""


def reusable_analysis(result):
    if not isinstance(result, dict):
        return False
    if result.get('analysis_status') not in ('succeeded', 'partial'):
        return False
    if not isinstance(result.get('summary'), str) or not result['summary'].strip():
        return False
    if not isinstance(result.get('runtime'), dict):
        return False
    if result['analysis_status'] == 'partial':
        # A partial completed pass is different from a failed/interrupted worker.
        chunks = result.get('chunks')
        return isinstance(chunks, list) and bool(chunks) and any(
            isinstance(chunk, dict) and isinstance(chunk.get('summary'), str)
            and bool(chunk['summary'].strip()) for chunk in chunks)
    return True


def reusable_task(value, task):
    if not isinstance(value, dict) or not isinstance(value.get('text'), str):
        return False
    raw = value.get('raw')
    if not isinstance(raw, dict) or raw.get('task') != task:
        return False
    return not raw.get('possibly_truncated') or raw.get('retry_exhausted') is True
