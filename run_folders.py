"""Allocate render revisions automatically and resume only compatible idle runs."""
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import unicodedata


def project_slug(label):
    if not isinstance(label,str): raise ValueError('Project name must be text')
    name=re.sub(r'[^\w-]+','_',unicodedata.normalize('NFKC',label),flags=re.UNICODE).strip('_-')
    # Bound the Windows path component in UTF-16 code units as well as characters.
    name=name.encode('utf-16-le')[:128].decode('utf-16-le',errors='ignore').rstrip('_-') or 'music_canvas'
    if re.fullmatch(r'CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9]',name,re.IGNORECASE): name='project_'+name
    return name


@contextmanager
def try_run_lock(root):
    """Nonblocking process lock, released automatically even after a process crash."""
    acquired=False
    with (root/'.music_canvas_run.lock').open('a+b') as stream:
        stream.seek(0,2)
        if stream.tell()==0:
            stream.write(b'0'); stream.flush()
        stream.seek(0)
        if os.name=='nt':
            import msvcrt
            try:
                msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1); acquired=True
            except OSError: pass
        else:
            import fcntl
            try:
                fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB); acquired=True
            except BlockingIOError: pass
        try: yield acquired
        finally:
            if acquired:
                stream.seek(0)
                if os.name=='nt': msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
                else: fcntl.flock(stream,fcntl.LOCK_UN)


def compatible_state(root,key):
    try:
        state=json.loads((root/'manifest.json').read_text(encoding='utf-8'))
        if not isinstance(state,dict) or state.get('config_hash')!=key or not isinstance(state.get('segments'),dict): return None
        config=state.get('config')
        if not isinstance(config,dict) or not config.get('models',{}).get('verified'): return None
        if hashlib.sha256(json.dumps(config,sort_keys=True).encode()).hexdigest()!=key: return None
        if isinstance(state.get('duration'),bool) or not isinstance(state.get('duration'),(int,float)) or not math.isfinite(state['duration']) or state['duration']<=0: return None
        if not isinstance(state.get('segment_count'),int) or state['segment_count']<=0: return None
        return state
    except (OSError,ValueError,TypeError,AttributeError): return None


@dataclass
class RunFolder:
    root: Path
    state: dict | None
    project: str
    reason: str


@contextmanager
def select_run(base,label,key,resume,models_verified):
    """Keep a project label fixed; allocate or reuse its render revisions safely.

    The selected directory stays locked through rendering. Another process using
    the same output tree receives a fresh revision rather than sharing live files.
    Older checkpoints directly in <project>/ remain eligible for exact resume.
    """
    base=Path(base).resolve(); project=project_slug(label)
    parent=base/project
    if not parent.resolve().is_relative_to(base): raise ValueError('Project folder must stay inside the Music Canvas output directory')
    parent.mkdir(parents=True,exist_ok=True)
    revisions=parent/'runs'
    if not revisions.resolve().is_relative_to(parent.resolve()): raise ValueError('Run folder must stay inside its project directory')
    if resume and models_verified:
        candidates=sorted((p for p in revisions.glob('run_*') if p.is_dir() and re.fullmatch(r'run_\d+',p.name)),key=lambda p:int(p.name[4:]),reverse=True)
        candidates.append(parent)
        for root in candidates:
            if not root.resolve().is_relative_to(parent.resolve()) or not (root/'manifest.json').is_file(): continue
            with try_run_lock(root) as acquired:
                if not acquired: continue
                state=compatible_state(root,key)
                if state is None: continue
                yield RunFolder(root,state,project,'resumed_legacy_checkpoint' if root==parent else 'resumed_matching_checkpoint')
                return
    revisions.mkdir(exist_ok=True)
    numbers=[int(p.name[4:]) for p in revisions.glob('run_*') if re.fullmatch(r'run_\d+',p.name)]
    number=max(numbers,default=0)+1
    while True:
        root=revisions/f'run_{number:06d}'
        try: root.mkdir(); break
        except FileExistsError: number+=1
    with try_run_lock(root) as acquired:
        if not acquired: raise RuntimeError('The newly allocated render folder is already in use')
        reason='new_revision' if resume and models_verified else 'new_unverified_models' if resume else 'new_resume_disabled'
        yield RunFolder(root,None,project,reason)
