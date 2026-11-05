"""Verify owned audio-worker processes exit on timeout and cancellation."""
import importlib.util
import subprocess
import sys
import types
import unittest
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('resources_tested', 'resources.py')
resources = importlib.util.module_from_spec(spec)
spec.loader.exec_module(resources)


class WorkerLifecycleTests(unittest.TestCase):
    def test_unlimited_timeout_completes(self):
        mm=types.SimpleNamespace(throw_exception_if_processing_interrupted=lambda:None)
        with patch.dict(sys.modules,{'comfy':types.ModuleType('comfy'),'comfy.model_management':mm}):
            result=resources.run_worker([sys.executable,'-c','import time; time.sleep(.1)'],timeout=0)
        self.assertTrue(result['worker_exit_verified'])
    def test_unicode_progress_on_windows_console(self):
        import io
        from contextlib import redirect_stdout
        buffer=io.BytesIO()
        stream=io.TextIOWrapper(buffer,encoding='cp1252')
        mm=types.SimpleNamespace(throw_exception_if_processing_interrupted=lambda:None)
        with patch.dict(sys.modules,{'comfy':types.ModuleType('comfy'),'comfy.model_management':mm}),redirect_stdout(stream):
            result=resources.run_worker([sys.executable,'-c','print(chr(20013))'],10)
        stream.flush()
        self.assertIn(b'\\u4e2d',buffer.getvalue())
        self.assertTrue(result['worker_exit_verified'])
    def run_case(self, interrupt, timeout, expected):
        children = []
        original = subprocess.Popen
        def spawn(*args, **kwargs):
            child = original(*args, **kwargs)
            if args[0][0] == sys.executable:
                children.append(child)
            return child
        mm = types.SimpleNamespace(throw_exception_if_processing_interrupted=interrupt)
        with patch.dict(sys.modules, {'comfy': types.ModuleType('comfy'), 'comfy.model_management': mm}), patch.object(resources.subprocess, 'Popen', spawn):
            with self.assertRaises(expected):
                resources.run_worker([sys.executable, '-c', 'import time; time.sleep(20)'], timeout)
        self.assertEqual(len(children), 1)
        self.assertIsNotNone(children[0].poll())

    def test_timeout_reaps_worker(self):
        self.run_case(lambda: None, .05, TimeoutError)

    def test_cancellation_reaps_worker(self):
        def interrupt():
            raise InterruptedError('cancel')
        self.run_case(interrupt, 20, InterruptedError)

    @unittest.skipUnless(os.name == 'nt','Windows venv launchers require tree termination')
    def test_cancellation_stops_child_interpreter(self):
        with tempfile.TemporaryDirectory() as temp:
            marker=Path(temp)/'child.txt'
            code='import subprocess,sys,time; from pathlib import Path; p=subprocess.Popen([sys.executable,"-c","import time; time.sleep(30)"]); Path(sys.argv[1]).write_text(str(p.pid)); time.sleep(30)'
            def interrupt():
                if marker.exists():
                    raise InterruptedError('cancel owned tree')
            mm=types.SimpleNamespace(throw_exception_if_processing_interrupted=interrupt)
            with patch.dict(sys.modules,{'comfy':types.ModuleType('comfy'),'comfy.model_management':mm}):
                with self.assertRaises(InterruptedError):
                    resources.run_worker([sys.executable,'-c',code,str(marker)],10)
            child=marker.read_text()
            listing=subprocess.check_output(['tasklist','/FI',f'PID eq {child}','/FO','CSV','/NH'],text=True)
            self.assertNotIn('"'+child+'"',listing)


if __name__ == '__main__':
    unittest.main()
