"""Identify the upstream model graph and local checkpoint revisions for resume."""
from pathlib import Path
import copy

def model_identity(graph,node_id,folders):
    if not graph or str(node_id) not in graph:
        return {'verified':False,'reason':'No ComfyUI prompt graph supplied; keep connected weights unchanged.'}
    sequence=graph[str(node_id)]['inputs']
    roots=[sequence[k][0] for k in ('model','clip','vae','audio_vae') if isinstance(sequence.get(k),list)]
    selected={}
    def visit(node):
        node=str(node)
        if node in selected or node not in graph: return
        selected[node]={'class_type':graph[node]['class_type'],'inputs':copy.deepcopy(graph[node].get('inputs',{}))}
        for value in graph[node].get('inputs',{}).values():
            if isinstance(value,list) and len(value)==2 and str(value[0]) in graph: visit(value[0])
    for root in roots: visit(root)
    names=set()
    for item in selected.values():
        for value in item.get('inputs',{}).values():
            if isinstance(value,str) and Path(value).suffix.lower() in ('.safetensors','.gguf','.ckpt','.pt','.bin'):
                names.add(value)
    files=[]; missing=[]
    for name in sorted(names):
        matches=[(Path(folder)/name).resolve() for folder in folders if (Path(folder)/name).is_file()]
        if not matches: missing.append(name)
        for path in sorted(set(matches)):
            stat=path.stat(); files.append((str(path),stat.st_size,stat.st_mtime_ns))
    return dict(verified=bool(files) and not missing,graph=selected,files=files,unresolved_files=missing)
