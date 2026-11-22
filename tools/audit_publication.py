"""Scan the explicit publication set or actual staged Git blobs, including ZIP contents."""
import argparse,hashlib,io,json,re,subprocess,sys,zipfile
from pathlib import Path,PurePosixPath

ROOT=Path(__file__).resolve().parents[1]
NAMES=('music_canvas_start_here',)
SECRET_RULES={
    'private-key':re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    'github-token':re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{25,}|github_pat_[A-Za-z0-9_]{30,})\b'),
    'hf-token':re.compile(r'\bhf_[A-Za-z0-9]{25,}\b'),
    'aws-access-key':re.compile(r'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b'),
    'credential-url':re.compile(r'https?://[^\s/"\']+:[^\s/"\']+@'),
    'query-credential':re.compile(r'[?&](?:token|api_key|access_token)=[A-Za-z0-9_%.-]{8,}',re.I),
    'personal-windows-path':re.compile(r'\b[A-Z]:[\\/](?:Users|CLAUDE)[\\/]',re.I),
}
MAX_FILE=2*1024*1024
MEDIA_TYPES={
    'docs/media/comparison-a.mp4':'video/mp4',
    'docs/media/comparison-b.mp4':'video/mp4',
    'docs/media/comparison-a.gif':'image/gif',
    'docs/media/comparison-b.gif':'image/gif',
}

def git(*args):
    return subprocess.check_output(['git','-C',str(ROOT),*args],stderr=subprocess.PIPE)

def inspect_text(path,data,findings):
    try:text=data.decode('utf-8-sig')
    except UnicodeDecodeError:
        findings.append(dict(path=path,rule='unexpected-binary'));return
    for label,pattern in SECRET_RULES.items():
        if pattern.search(text):findings.append(dict(path=path,rule=label))
    if path.endswith('.json'):
        try:json.loads(text)
        except ValueError:findings.append(dict(path=path,rule='invalid-json'))

def audit(files,read,allowed,required,media=None):
    findings=[]
    media=media or {}
    for missing in sorted(required-set(files)):findings.append(dict(path=missing,rule='missing-publication-file'))
    for path in files:
        if path not in allowed:
            findings.append(dict(path=path,rule='outside-publication-allowlist'));continue
        payload=read(path)
        if path in MEDIA_TYPES:
            expected=media.get(path,{})
            valid_header=(payload.startswith((b'GIF87a',b'GIF89a')) if path.endswith('.gif') else payload[4:8]==b'ftyp')
            if (not valid_header or len(payload)>10*1024*1024 or expected.get('mime_type')!=MEDIA_TYPES[path]
                or expected.get('size_bytes')!=len(payload) or expected.get('sha256')!=hashlib.sha256(payload).hexdigest()):
                findings.append(dict(path=path,rule='showcase-media-not-verified'))
            continue
        if len(payload)>MAX_FILE:findings.append(dict(path=path,rule='unexpected-large-file'));continue
        if path.endswith('.zip'):
            with zipfile.ZipFile(io.BytesIO(payload)) as z:
                seen=set()
                for entry in z.infolist():
                    p=PurePosixPath(entry.filename)
                    if p.is_absolute() or '..' in p.parts or '\\' in entry.filename or entry.filename in seen:
                        findings.append(dict(path=path,rule='unsafe-zip-member'));continue
                    seen.add(entry.filename)
                    if entry.is_dir():continue
                    if entry.file_size>MAX_FILE or p.name not in ('README.md','manifest.json','workflow.api.json'):
                        findings.append(dict(path=path,rule='unexpected-zip-member'));continue
                    content=z.read(entry)
                    inspect_text(path+'!'+entry.filename,content,findings)
                    if p.name in ('manifest.json','workflow.api.json'):
                        expected='examples/'+p.parent.name+'/'+p.name
                        if expected not in files or json.loads(content)!=json.loads(read(expected)):findings.append(dict(path=path,rule='zip-source-mismatch'))
        else:inspect_text(path,payload,findings)
    return findings

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--working-tree',action='store_true');mode.add_argument('--index',action='store_true')
    parser.add_argument('--release',action='store_true',help='Also require a chosen source license and automatically ready manifests')
    args=parser.parse_args()
    config=json.loads((ROOT/'publication_files.json').read_text(encoding='utf-8'))
    required=set(config['files']);allowed=required|set(config.get('optional_files',[]))
    if args.index:
        paths=[p for p in git('ls-files','-z').decode().split('\0') if p]
        read=lambda p:git('show',':'+p)
    else:
        paths=[p for p in sorted(allowed) if (ROOT/p).is_file()]
        read=lambda p:(ROOT/p).read_bytes()
    findings=audit(paths,read,allowed,required,config.get('media_files'))
    lock=json.loads(read('docs/model_sources.json')) if 'docs/model_sources.json' in paths else {}
    for name in NAMES:
        base='examples/'+name+'/'
        if base+'manifest.json' not in paths or base+'workflow.api.json' not in paths:continue
        manifest=json.loads(read(base+'manifest.json'));workflow=json.loads(read(base+'workflow.api.json'))
        kinds={n['class_type'] for n in workflow.values()}
        if not any(n['class_type']=='SaveVideo' for n in workflow.values()):findings.append(dict(path=base,rule='missing-video-output'))
        own=[n for n in manifest['nodes'] if n['name']=='ComfyUI_LocalMusicCanvas']
        if len(own)!=1 or not {k for k in kinds if k.startswith('MusicCanvas')}<=set(own[0]['class_types']):findings.append(dict(path=base,rule='undeclared-music-canvas-nodes'))
        for model in manifest['models']:
            expected=lock.get(model['filename'],{})
            if any(model.get(k)!=expected.get(k) for k in ('url','sha256','size_bytes')):findings.append(dict(path=base,rule='model-lock-mismatch'))
        if args.release:
            status=json.loads(read(base+'readiness.json'))
            if not status.get('ready'):findings.append(dict(path=base,rule='manual-dependency-setup-required'))
    if args.release:
        if 'LICENSE' not in paths:findings.append(dict(path='LICENSE',rule='source-license-not-selected'))
        status_file='docs/runtime_validation.json'
        status=json.loads(read(status_file)) if status_file in paths else {}
        if not all(status.get(key) is True for key in ('patched_environment_installed','compatibility_passed','full_inference_passed','dependency_audit_completed')):
            findings.append(dict(path=status_file,rule='runtime-upgrade-validation-incomplete'))
    result=dict(mode='index' if args.index else 'working-tree',files_checked=len(paths),passed=not findings,findings=findings)
    print(json.dumps(result,indent=2))
    return int(bool(findings))

if __name__=='__main__':raise SystemExit(main())
