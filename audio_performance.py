"""Versioned stage caches, deterministic task seeds and sampling plans."""
import contextlib
import hashlib
import json
import os
from pathlib import Path
import time
import uuid

SEMANTIC_VERSION='audio-performance-1'
BUDGETS={'description':192,'attributes':192,'structure':256,'lyrics':384}

def identity(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def asset_signature(path):
    path=Path(path)
    files=sorted(p for p in path.rglob('*') if p.is_file() and not p.name.startswith('.') and '__pycache__' not in p.parts) if path.is_dir() else [path]
    return [(str(p.resolve()),p.stat().st_size,p.stat().st_mtime_ns) for p in files]

def sampled_ranges(ranges,limit=3):
    if len(ranges)<=limit: return ranges
    return [ranges[round(i*(len(ranges)-1)/(limit-1))] for i in range(limit)]

def coverage(ranges,duration):
    covered=0.; end=0.
    for a,b in sorted(ranges):
        covered+=max(0,b-max(a,end)); end=max(end,b)
    return min(1.,covered/duration)

class StageCache:
    def __init__(self,root):
        self.root=Path(root); self.root.mkdir(parents=True,exist_ok=True)
    def path(self,key): return self.root/(identity(key)+'.json')
    def get(self,key):
        try: return json.loads(self.path(key).read_text(encoding='utf-8'))
        except (OSError,ValueError): return None
    def put(self,key,value):
        path=self.path(key); temp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
        try:
            temp.write_text(json.dumps(value,allow_nan=False,ensure_ascii=False),encoding='utf-8'); os.replace(temp,path)
        finally:
            temp.unlink(missing_ok=True)
    @contextlib.contextmanager
    def lock(self,key):
        # OS locks release on process death, avoiding stale lock-directory recovery.
        with self.path(key).with_suffix('.lock').open('a+b') as stream:
            stream.seek(0); stream.write(b'0'); stream.flush(); stream.seek(0)
            if os.name=='nt':
                import msvcrt
                while True:
                    try: msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1); break
                    except OSError: time.sleep(.1); stream.seek(0)
                try: yield
                finally: stream.seek(0); msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
            else:
                import fcntl
                fcntl.flock(stream,fcntl.LOCK_EX)
                try: yield
                finally: fcntl.flock(stream,fcntl.LOCK_UN)

class AudioFeatureMemo:
    """Reuse the exact encoder output, including all DeepStack hidden states."""
    def __init__(self,model):
        self.model=model; self.original=model.get_audio_features; self.saved=None; self.hits=0; self.encoder_seconds=0.
        model.get_audio_features=self.get
    def clear(self): self.saved=None
    def get(self,features,lengths):
        import torch
        if self.saved is not None:
            previous,previous_lengths,result=self.saved
            if torch.equal(previous_lengths,lengths) and torch.equal(previous,features):
                self.hits+=1; return result
        started=time.monotonic()
        result=self.original(features,lengths)
        if features.is_cuda: torch.cuda.synchronize(features.device)
        self.encoder_seconds+=time.monotonic()-started
        self.saved=(features.detach().clone(),lengths.detach().clone(),result)
        return result
    def close(self):
        self.model.get_audio_features=self.original
        self.clear(); self.model=None; self.original=None

class FirstTokenClock:
    def __init__(self): self.calls=0; self.started=time.monotonic(); self.first=None
    def put(self,value):
        if self.calls==1: self.first=time.monotonic()-self.started
        self.calls+=1
    def end(self): pass

def memory_snapshot():
    result={'process_cpu_seconds':time.process_time()}
    if os.name=='nt':
        import ctypes
        class Memory(ctypes.Structure):
            _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong)]+[(n,ctypes.c_ulonglong) for n in ('physical_total','physical_free','commit_total','commit_free','virtual_total','virtual_free','extended')]
        state=Memory(); state.length=ctypes.sizeof(state)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(state)):
            result.update(ram_total=state.physical_total,ram_free=state.physical_free,commit_free=state.commit_free)
    return result
