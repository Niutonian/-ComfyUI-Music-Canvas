"""Build and check a separate audio environment before activating it."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import uuid
from audio_assets import SOURCE_REVISION

TORCH_VERSION='2.10.0'
TORCH_INDEX='https://download.pytorch.org/whl/cu128'

def install_candidate(root,source,uv,environment=None):
    root=Path(root).resolve()
    candidate=Path(environment).resolve() if environment else root/'.audio-env-candidates'/uuid.uuid4().hex[:12]
    if not candidate.is_relative_to(root) or candidate==root:raise ValueError('Candidate environment must stay inside this node pack')
    if candidate.exists():raise ValueError('Use a new candidate directory; existing audio environments are never overwritten')
    python=candidate/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    prefix=[str(uv),'--cache-dir',str(root/'.uv-cache')]
    subprocess.run([*prefix,'venv','--python','3.12',str(candidate)],check=True)
    subprocess.run([*prefix,'pip','install','--python',str(python),'torch=='+TORCH_VERSION,'torchaudio=='+TORCH_VERSION,
        '--index-url',TORCH_INDEX],check=True)
    subprocess.run([*prefix,'pip','install','--python',str(python),'-r',str(root/'audio_requirements.txt')],check=True)
    subprocess.run([*prefix,'pip','check','--python',str(python)],check=True)
    report=candidate/'music_canvas_runtime_check.json'
    subprocess.run([str(python),str(root/'runtime_check.py'),'--repository',str(source),'--output',str(report)],check=True)
    result=json.loads(report.read_text(encoding='utf-8'))
    if result.get('passed') is not True or result.get('patched_version_requirements') is not True:
        raise RuntimeError('Candidate check did not confirm patched dependencies; existing runtime remains active')
    return python,result

def activate_config(destinations,config):
    for destination in destinations:
        destination=Path(destination)
        if not destination.is_dir():raise ValueError('Node pack directory does not exist: '+str(destination))
    for destination in destinations:
        target=Path(destination)/'runtime_config.json'
        if target.is_file():
            backup=target.with_name('runtime_config.previous.json')
            shutil.copy2(target,backup)
        temporary=target.with_name('runtime_config.pending.json')
        temporary.write_text(json.dumps(config,indent=2)+'\n',encoding='utf-8')
        temporary.replace(target)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--install-environment',action='store_true')
    parser.add_argument('--configure-pack',type=Path)
    parser.add_argument('--environment-dir',type=Path,help='New candidate directory inside this node pack; existing directories are refused')
    args=parser.parse_args()
    root=Path(__file__).resolve().parent
    source=root/'runtime/MOSS-Music'
    if not source.exists():
        source.parent.mkdir(parents=True,exist_ok=True)
        subprocess.run(['git','clone','--filter=blob:none','--no-checkout','https://github.com/OpenMOSS/MOSS-Music',str(source)],check=True)
        subprocess.run(['git','sparse-checkout','set','src'],cwd=source,check=True)
    subprocess.run(['git','checkout',SOURCE_REVISION],cwd=source,check=True)
    if not args.install_environment:
        print('Pinned source is ready. Run with --install-environment to build/check a candidate; existing runtime configuration was preserved.')
        return
    uv=shutil.which('uv')
    if not uv:raise RuntimeError('Install uv to create the isolated audio environment')
    python,report=install_candidate(root,source,uv,args.environment_dir)
    config=dict(python=str(python),source=str(source),source_revision=SOURCE_REVISION,
        validation=report,full_model_inference_tested=False)
    activate_config([root]+([args.configure_pack] if args.configure_pack else []),config)
    print(json.dumps(config,indent=2))
    print('Candidate import/tiny-model checks passed and configuration was updated. Full pretrained-model inference is a separate test.')
    print('The previous environment remains on disk. runtime_config.previous.json restores its selection.')
    print('Download checkpoints explicitly with the configured Python and audio_assets.py, or enable allow_model_download.')

if __name__=='__main__':main()
