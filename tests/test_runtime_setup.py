import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import setup_runtime

class CandidateRuntime(unittest.TestCase):
    def test_failed_candidate_validation_preserves_existing_configuration(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);config=root/'runtime_config.json';config.write_text('{"python":"working"}')
            before=config.read_bytes();calls=[]
            def run(command,**kwargs):
                calls.append(command)
                if 'runtime_check.py' in ' '.join(command):raise RuntimeError('failed model import')
            with patch.object(setup_runtime.subprocess,'run',side_effect=run):
                with self.assertRaisesRegex(RuntimeError,'failed model import'):setup_runtime.install_candidate(root,root/'source','uv')
            self.assertEqual(config.read_bytes(),before)
            self.assertTrue(any('torch==2.10.0' in c for c in calls))

    def test_existing_environment_and_outside_paths_are_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);existing=root/'.audio-env';existing.mkdir()
            with self.assertRaisesRegex(ValueError,'never overwritten'):setup_runtime.install_candidate(root,root/'source','uv',existing)
            with self.assertRaisesRegex(ValueError,'inside'):setup_runtime.install_candidate(root,root/'source','uv',root.parent/'outside')

    def test_activation_keeps_the_previous_selection_for_rollback(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'runtime_config.json').write_text('{"python":"old"}')
            setup_runtime.activate_config([root],{'python':'checked candidate'})
            self.assertEqual(json.loads((root/'runtime_config.json').read_text())['python'],'checked candidate')
            self.assertEqual(json.loads((root/'runtime_config.previous.json').read_text())['python'],'old')

if __name__=='__main__':unittest.main()
