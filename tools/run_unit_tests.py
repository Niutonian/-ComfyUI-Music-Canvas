"""Run only portable unit tests; never discover local rendering/install scripts."""
import json,os,subprocess,sys
from pathlib import Path

root=Path(__file__).resolve().parents[1]
files=json.loads((root/'publication_files.json').read_text())['files']
modules=[Path(path).stem for path in files if path.startswith('tests/test_') and path.endswith('.py')]
if not modules:raise SystemExit('No published tests found; check publication_files.json')
temp_root=root/'test_results/unit-temp'
temp_root.mkdir(parents=True,exist_ok=True)
raise SystemExit(subprocess.call([sys.executable,'-m','unittest',*modules],cwd=root,
    env={**os.environ,'PYTHONIOENCODING':'utf-8','TMP':str(temp_root),'TEMP':str(temp_root),'TMPDIR':str(temp_root),
        'PYTHONPATH':os.pathsep.join([str(root),str(root/'tests'),os.environ.get('PYTHONPATH','')])}))
