"""Explicit setup downloads, shared by the ComfyUI worker. Inference stays offline."""
import hashlib
import json
from pathlib import Path
import urllib.request
try:
    from .runtime_security import BEAT_SHA256,verify_sha256
except ImportError:
    from runtime_security import BEAT_SHA256,verify_sha256

MOSS_REPO = 'OpenMOSS-Team/MOSS-Music-8B-Instruct'
MOSS_REVISION = 'fce7f8304e96cc2d3398b8106456cbb2ecec3139'
SOURCE_REVISION = 'ad107c7ddaa06de168a0dfbc18d3e1e6a40c0e5e'
BEAT_URL = 'https://cloud.cp.jku.at/public.php/dav/files/7ik4RrBKTS273gp/final0.ckpt'

def model_ready(model):
    model=Path(model)
    try:
        manifest=json.loads((model/'music_canvas_assets.json').read_text())
        index=json.loads((model/'model.safetensors.index.json').read_text())
        if not index['weight_map']: return False
        return (manifest.get('model_revision')==MOSS_REVISION and (model/'config.json').is_file()
                and all((model/name).is_file() and (model/name).stat().st_size>0 for name in set(index['weight_map'].values())))
    except (OSError,ValueError,KeyError,TypeError): return False

def assets_ready(model,beats):
    beats=Path(beats)
    return model_ready(model) and beats.is_file() and beats.stat().st_size>0


def download(model, beats):
    from huggingface_hub import snapshot_download
    model, beats = Path(model), Path(beats)
    manifest_path = model/'music_canvas_assets.json'
    ready = model_ready(model)
    if not ready:
        snapshot_download(repo_id=MOSS_REPO, revision=MOSS_REVISION, local_dir=str(model),
            allow_patterns=['*.json', '*.jinja', '*.txt', '*.py', '*.safetensors'], max_workers=3)
    if not beats.is_file() or beats.stat().st_size==0:
        beats.parent.mkdir(parents=True, exist_ok=True)
        partial = beats.with_suffix('.partial')
        try:
            with urllib.request.urlopen(BEAT_URL, timeout=60) as source, partial.open('wb') as output:
                while block := source.read(1024 * 1024):
                    output.write(block)
            verify_sha256(partial,BEAT_SHA256)
            partial.replace(beats)
        finally:
            if partial.exists():partial.unlink()
    verify_sha256(beats,BEAT_SHA256)
    manifest = dict(model_repository=MOSS_REPO, model_revision=MOSS_REVISION,
        source_revision=SOURCE_REVISION, beat_url=BEAT_URL,
        beat_sha256=hashlib.sha256(beats.read_bytes()).hexdigest())
    try: existing=json.loads(manifest_path.read_text())
    except (OSError,ValueError): existing=None
    if existing != manifest:
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return manifest


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--models-root', type=Path)
    parser.add_argument('--model',type=Path)
    parser.add_argument('--beats',type=Path)
    args = parser.parse_args()
    if args.model and args.beats:
        paths=(args.model,args.beats)
    elif args.models_root:
        paths=(args.models_root/'moss_music/MOSS-Music-8B-Instruct',args.models_root/'beat_this/beat_this-final0.ckpt')
    else: parser.error('Provide --models-root or both --model and --beats')
    print(json.dumps(download(*paths),indent=2))
