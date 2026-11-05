"""ComfyUI model registry integration, including extra_model_paths.yaml roots."""
from pathlib import Path
import folder_paths

DEFAULT_MOSS = 'MOSS-Music-8B-Instruct'
DEFAULT_BEATS = 'beat_this-final0.ckpt'


def register():
    for key in ('moss_music', 'beat_this'):
        folder_paths.add_model_folder_path(key, str(Path(folder_paths.models_dir) / key))


def moss_names():
    register()
    names = {DEFAULT_MOSS}
    for root in folder_paths.get_folder_paths('moss_music'):
        base = Path(root)
        if base.exists():
            names.update(str(p.parent.relative_to(base)) for p in base.rglob('config.json'))
    return sorted(names)


def beat_names():
    register()
    names = {DEFAULT_BEATS}
    for root in folder_paths.get_folder_paths('beat_this'):
        base = Path(root)
        if base.exists():
            names.update(str(p.relative_to(base)) for p in base.rglob('*.ckpt'))
    return sorted(names)


def resolve(key, name):
    register()
    roots = [Path(x).resolve() for x in folder_paths.get_folder_paths(key)]
    for base in roots:
        candidate = (base / name).resolve()
        if not candidate.is_relative_to(base):
            raise ValueError('Model selection escapes registered model folder')
        if candidate.exists():
            return candidate
    return roots[0] / name
