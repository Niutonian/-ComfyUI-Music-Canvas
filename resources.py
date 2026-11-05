"""Release GPU allocations and manage only this node's subprocess on cancellation."""
import subprocess
import time
import os
import signal
import contextlib

@contextlib.contextmanager
def worker_log_directory():
    import tempfile
    import shutil
    path=tempfile.mkdtemp(prefix='music_canvas_logs_')
    try: yield path
    finally:
        for attempt in range(15):
            try:
                shutil.rmtree(path)
                break
            except PermissionError:
                if attempt==14:
                    print('[MusicCanvas] Temporary logs are still locked: '+path,flush=True)
                else: time.sleep(.2)


def stop_owned_worker(process):
    # A Windows venv launcher may have a child interpreter holding the GPU.
    # Kill only the tree rooted at this Popen PID, before its launcher exits.
    if os.name == 'nt':
        subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True,timeout=15)
    else:
        try:
            os.killpg(process.pid,signal.SIGTERM)
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        if os.name != 'nt':
            os.killpg(process.pid,signal.SIGKILL)
        process.kill()
        process.wait()


def prepare_gpu():
    import comfy.model_management as mm
    from .ollama_director import release_owned
    mm.throw_exception_if_processing_interrupted()
    release_owned()
    mm.unload_all_models()
    mm.soft_empty_cache()


def run_worker(command, timeout=3600):
    import comfy.model_management as mm
    import tempfile
    # File-backed logs avoid pipe deadlock when a model emits large diagnostics.
    from pathlib import Path
    import json
    from contextlib import ExitStack
    with worker_log_directory() as log_dir, ExitStack() as stack:
        stdout=stack.enter_context((Path(log_dir)/'stdout.log').open('wb'))
        stderr=stack.enter_context((Path(log_dir)/'stderr.log').open('w+b'))
        reader=stack.enter_context((Path(log_dir)/'stdout.log').open('rb'))
        pending=b''
        def drain():
            nonlocal pending
            pending+=reader.read()
            while b'\n' in pending:
                line,pending=pending.split(b'\n',1)
                message=line.decode(errors='replace')
                import sys
                encoding=getattr(sys.stdout,'encoding',None) or 'utf-8'
                print(('[MusicCanvas] '+message).encode(encoding,errors='backslashreplace').decode(encoding),flush=True)
                try:
                    event=json.loads(message)
                    if event.get('event')=='music_canvas_progress' and 'total' in event:
                        from comfy.utils import ProgressBar
                        ProgressBar(event['total']).update_absolute(event['current'])
                except (ValueError,TypeError): pass
        environment=os.environ.copy()
        environment.update(PYTHONIOENCODING='utf-8',PYTHONUTF8='1')
        process = subprocess.Popen(command, stdout=stdout, stderr=stderr, start_new_session=os.name != 'nt',env=environment)
        try:
            deadline = time.monotonic() + timeout if timeout else float('inf')
            while process.poll() is None:
                drain()
                mm.throw_exception_if_processing_interrupted()
                if time.monotonic() > deadline:
                    raise TimeoutError('Audio model worker timed out')
                time.sleep(.2)
            drain()
            stderr.seek(0)
            diagnostic = stderr.read().decode(errors='replace')
            if process.returncode:
                raise RuntimeError('Music worker failed: ' + diagnostic[-4000:])
            return {'worker_pid': process.pid, 'worker_exit_code': process.returncode, 'worker_exit_verified': process.poll() is not None}
        finally:
            if process.poll() is None:
                stop_owned_worker(process)
