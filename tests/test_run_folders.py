import concurrent.futures
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from run_folders import project_slug,select_run


def config(**changes):
    value=dict(version=2,models=dict(verified=True,revision='weight-v1'),seed=42,audio_sha256='song-a',
               prompts=['scene-a'],width=448,steps=8)
    value.update(changes)
    return value


def key(value): return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()


def checkpoint(root,value):
    state=dict(config_hash=key(value),config=value,segments={},status='interrupted_or_failed',duration=60.,segment_count=4)
    (root/'manifest.json').write_text(json.dumps(state),encoding='utf-8')
    return state


class AutomaticRunFolders(unittest.TestCase):
    def test_changed_inputs_get_revisions_and_original_inputs_find_old_checkpoint(self):
        with tempfile.TemporaryDirectory() as temp:
            original=config()
            with select_run(temp,'My Song',key(original),True,True) as first:
                root=first.root; checkpoint(root,original)
                (root/'segment_000000.mp4').write_bytes(b'original segment')
                self.assertEqual(root.relative_to(temp).as_posix(),'My_Song/runs/run_000001')
            before=(root/'manifest.json').read_bytes()
            variants=[config(seed=43),config(audio_sha256='song-b'),config(prompts=['new scene']),
                      config(width=768),config(models=dict(verified=True,revision='different-lora'))]
            for index,value in enumerate(variants,2):
                with select_run(temp,'My Song',key(value),True,True) as new:
                    self.assertIsNone(new.state)
                    self.assertEqual(new.root.name,f'run_{index:06d}')
                    checkpoint(new.root,value)
            with select_run(temp,'My Song',key(original),True,True) as resumed:
                self.assertEqual(resumed.root,root)
                self.assertEqual(resumed.state['config'],original)
            self.assertEqual((root/'manifest.json').read_bytes(),before)
            self.assertEqual((root/'segment_000000.mp4').read_bytes(),b'original segment')

    def test_resume_disabled_always_creates_fresh_revision(self):
        with tempfile.TemporaryDirectory() as temp:
            value=config(); roots=[]
            for _ in range(3):
                with select_run(temp,'song',key(value),False,True) as selected:
                    self.assertIsNone(selected.state); roots.append(selected.root)
                    checkpoint(selected.root,value)
            self.assertEqual(len(set(roots)),3)
            with select_run(temp,'song',key(value),True,True) as resumed:
                self.assertEqual(resumed.root,roots[-1])

    def test_legacy_checkpoint_resumes_and_mismatches_are_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            legacy=Path(temp)/'old_project'; legacy.mkdir()
            original=config(); checkpoint(legacy,original)
            before=(legacy/'manifest.json').read_bytes()
            with select_run(temp,'old_project',key(original),True,True) as selected:
                self.assertEqual(selected.root,legacy)
                self.assertEqual(selected.reason,'resumed_legacy_checkpoint')
            changed=config(seed=99)
            with select_run(temp,'old_project',key(changed),True,True) as selected:
                self.assertEqual(selected.root,legacy/'runs/run_000001')
            self.assertEqual((legacy/'manifest.json').read_bytes(),before)

    def test_active_run_is_not_shared_and_exception_releases_lock(self):
        with tempfile.TemporaryDirectory() as temp:
            value=config(); root=None
            with self.assertRaisesRegex(RuntimeError,'simulated interruption'):
                with select_run(temp,'song',key(value),True,True) as running:
                    root=running.root; checkpoint(root,value)
                    with select_run(temp,'song',key(value),True,True) as parallel:
                        self.assertNotEqual(parallel.root,root)
                    raise RuntimeError('simulated interruption')
            with select_run(temp,'song',key(value),True,True) as resumed:
                self.assertEqual(resumed.root,root)

    def test_concurrent_allocations_are_unique(self):
        with tempfile.TemporaryDirectory() as temp:
            value=config()
            def allocate(_):
                with select_run(temp,'song',key(value),False,True) as selected:
                    checkpoint(selected.root,value)
                    return selected.root
            with concurrent.futures.ThreadPoolExecutor(4) as pool:
                roots=list(pool.map(allocate,range(12)))
            self.assertEqual(len(set(roots)),12)
            self.assertEqual(sorted(int(p.name[4:]) for p in roots),list(range(1,13)))

    def test_corrupt_manifest_and_unverified_models_get_fresh_runs(self):
        with tempfile.TemporaryDirectory() as temp:
            value=config()
            with select_run(temp,'song',key(value),True,True) as initial:
                root=initial.root; checkpoint(root,value)
            for invalid in ('{',json.dumps(dict(config_hash=key(value),segments={},config={}))) :
                (root/'manifest.json').write_text(invalid)
                with select_run(temp,'song',key(value),True,True) as selected:
                    self.assertIsNone(selected.state); self.assertNotEqual(selected.root,root)
            checkpoint(root,value)
            with select_run(temp,'song',key(value),True,False) as selected:
                self.assertIsNone(selected.state); self.assertNotEqual(selected.root,root)

    def test_project_names_support_spaces_unicode_and_safe_path_components(self):
        self.assertEqual(project_slug('  Été / Song: 2026  '),'Été_Song_2026')
        self.assertEqual(project_slug(''),'music_canvas')
        self.assertEqual(project_slug('CON'),'project_CON')
        self.assertEqual(project_slug('../../other'),'other')
        self.assertLessEqual(len(project_slug('長'*100).encode('utf-16-le')),128)
        with tempfile.TemporaryDirectory() as temp:
            with select_run(temp,'../../other',key(config()),False,True) as selected:
                self.assertTrue(selected.root.is_relative_to(Path(temp)))


if __name__=='__main__': unittest.main()
