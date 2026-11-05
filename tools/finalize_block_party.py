"""Pin this project's published source and rebuild its three native Block Party ZIPs."""
import argparse,json,re,sys,urllib.parse,urllib.request,zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
NAMES=('music_canvas_simple','music_canvas_sequential_Good','music_canvas_14sec_max')

def add_release_notes(archive,name):
    """Keep native job members and append self-contained notes to its generated README."""
    archive=Path(archive).resolve()
    if name not in NAMES or archive!=ROOT/'share'/(name+'.zip'):raise ValueError('Unexpected archive destination')
    with zipfile.ZipFile(archive) as source:members=[(info,source.read(info)) for info in source.infolist()]
    manifest=json.loads((ROOT/'examples'/name/'manifest.json').read_text(encoding='utf-8'))
    own=next(p for p in manifest['nodes'] if p['name']=='ComfyUI_LocalMusicCanvas')
    source_note=own.get('git_url') or 'Not assigned yet: install the reviewed Music Canvas source manually; do not substitute ComfyUI as its repository.'
    notes='\n\n## Music Canvas export notes\n\n'+(ROOT/'examples'/name/'README.md').read_text(encoding='utf-8')
    notes+='\n\nMusic Canvas source: '+source_note+'\n\n'
    notes+='Model rights are separate from this job. MiniMax H3 has a restricted community license, including territorial exclusions. Read https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/LICENSE before downloading or using its weights. Derivative model-card badges do not establish unrestricted rights. No weights or music are bundled. Original Music Canvas source and documentation are MIT-licensed; model terms remain separate.\n\n'
    notes+='For the analysis examples, install/check an isolated audio candidate with `uv run python setup_runtime.py --install-environment`, explicitly download the pinned MOSS snapshot using the configured Python and `audio_assets.py --models-root <ComfyUI/models>`, and run local Ollama with a compatible model selected in the graph. The `ornith-1.5:35b` name is a local alias: the full repository provides a pinned public GGUF and Modelfile. Block Party does not install that service or import that model for you. The legacy runtime has known advisories, and installing and fully validating the patched candidate remains pending; read SECURITY.md in the source repository.\n'
    notes+='\n\n## Music Canvas license\n\n'+(ROOT/'LICENSE').read_text(encoding='utf-8')
    temporary=archive.with_suffix('.tmp.zip')
    with zipfile.ZipFile(temporary,'w',compression=zipfile.ZIP_DEFLATED) as target:
        for info,payload in members:
            if Path(info.filename).name=='README.md':payload+=notes.encode('utf-8')
            target.writestr(info,payload)
    temporary.replace(archive)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--block-party-root',required=True,type=Path)
    parser.add_argument('--repository',required=True,help='Published HTTPS GitHub repository URL')
    parser.add_argument('--commit',required=True,help='Published full 40-character source commit')
    args=parser.parse_args()
    url=urllib.parse.urlsplit(args.repository)
    if url.scheme!='https' or url.hostname!='github.com' or url.username or url.password or url.query or url.fragment:
        parser.error('Use a credential-free HTTPS github.com repository URL')
    parts=url.path.strip('/').removesuffix('.git').split('/')
    if len(parts)!=2 or any(not re.fullmatch(r'[A-Za-z0-9_.-]+',part) or part in ('.','..') for part in parts):parser.error('Expected owner/repository')
    if not re.fullmatch(r'[a-fA-F0-9]{40}',args.commit):parser.error('Use a complete source commit SHA')
    # Check a real published commit, without installing code or storing credentials.
    request=urllib.request.Request('https://api.github.com/repos/'+'/'.join(parts)+'/commits/'+args.commit,headers={'User-Agent':'MusicCanvas-release-finalizer'})
    with urllib.request.urlopen(request,timeout=30) as response:published=json.load(response)
    if published.get('sha','').lower()!=args.commit.lower():raise ValueError('Repository commit verification failed')
    bp=args.block_party_root.resolve()
    if not (bp/'one_job/export_job.py').is_file():parser.error('Block Party root must contain one_job/export_job.py')
    sys.path.insert(0,str(bp))
    from one_job.export_job import write_job,write_share
    from one_job.job import check_contract
    from one_job.readiness import export_readiness
    from one_job.security import reject_embedded_secrets
    replacements=[]
    for name in NAMES:
        folder=ROOT/'examples'/name
        manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
        workflow=json.loads((folder/'workflow.api.json').read_text(encoding='utf-8'))
        own=[p for p in manifest['nodes'] if p['name']=='ComfyUI_LocalMusicCanvas']
        if len(own)!=1:raise ValueError('Expected one Music Canvas pack in '+name)
        own[0].update(git_url='https://github.com/'+'/'.join(parts)+'.git',commit=args.commit.lower())
        manifest['runtime_requirements']=[r for r in manifest.get('runtime_requirements',[]) if r.get('module')!='music_canvas_source']
        reject_embedded_secrets(manifest);reject_embedded_secrets(workflow)
        check_contract(workflow,manifest)
        replacements.append((name,workflow,manifest))
    # Validate every example before changing any export.
    for name,workflow,manifest in replacements:
        folder=write_job(ROOT/'examples',name,workflow,manifest)
        readiness=export_readiness(manifest)
        (folder/'readiness.json').write_text(json.dumps(readiness,indent=2)+'\n',encoding='utf-8')
        archive=write_share(ROOT/'examples',name,workflow,manifest,include_inputs=False)
        add_release_notes(archive,name)
        print(name+': '+readiness['label']+'; '+archive.name)

if __name__=='__main__':main()
