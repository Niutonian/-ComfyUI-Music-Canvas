"""Worker-scoped safeguards; no mutation of ComfyUI's Python environment."""
import hashlib
import re
from pathlib import Path

BEAT_SHA256='8c328b45f59d8dd3dff219253ff6a8d6482be57d0133a29140e2febbf8eb8331'

def verify_sha256(path,expected):
    if not isinstance(expected,str) or not re.fullmatch(r'[a-fA-F0-9]{64}',expected):
        raise ValueError('A complete expected SHA-256 is required')
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):digest.update(chunk)
    actual=digest.hexdigest()
    if actual!=expected.lower():raise ValueError('Checkpoint checksum mismatch; refusing to load or install '+Path(path).name)
    return actual

def disable_custom_generation(model_class):
    """Reject the unused remote/custom generation loader before it can fetch Python."""
    def blocked(*args,**kwargs):
        # from_pretrained probes this optional hook and treats OSError as absent.
        # Explicit custom generation still fails, without looking up any files.
        raise OSError('Custom generation code is disabled in the Music Canvas audio worker')
    model_class.load_custom_generate=blocked

def version_tuple(value):
    match=re.match(r'^(\d+)\.(\d+)\.(\d+)(?:\+[^\s]+)?$',str(value))
    if not match:raise ValueError('Expected a stable package version, got '+str(value))
    return tuple(int(part) for part in match.groups())

def verify_beat_checkpoint(path,torch_version):
    path=Path(path)
    if path.name=='beat_this-final0.ckpt':return verify_sha256(path,BEAT_SHA256)
    if version_tuple(torch_version)<(2,10,0):
        raise RuntimeError('Custom Beat This checkpoints require Torch 2.10.0 or later; use the verified default or upgrade the isolated audio runtime')
    return None
