"""Remove nonpublication paths from the index only, then stage the explicit release set."""
import argparse,json,shutil,subprocess
from pathlib import Path

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true',help='Apply the displayed index-only changes; never deletes working files')
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    cfg=json.loads((root/'publication_files.json').read_text())
    allowed=set(cfg['files'])|set(cfg.get('optional_files',[]))
    def git(*cmd):return subprocess.check_output(['git','-C',str(root),*cmd])
    tracked={x for x in git('ls-files','-z').decode().split('\0') if x}
    excluded=sorted(tracked-allowed)
    existing=sorted(p for p in allowed if (root/p).is_file())
    print(json.dumps(dict(remove_from_index_only=excluded,stage=existing) if not args.apply else
        dict(remove_from_index_only_count=len(excluded),stage_count=len(existing)),indent=2),flush=True)
    if not args.apply:return
    backup=root/'test_results/publication/index-before-curation'
    backup.parent.mkdir(parents=True,exist_ok=True)
    index=Path(git('rev-parse','--absolute-git-dir').decode().strip())/'index'
    if index.is_file():shutil.copy2(index,backup)
    if excluded:
        result=subprocess.run(['git','-C',str(root),'rm','--cached','--ignore-unmatch','--',*excluded],capture_output=True,text=True)
        if result.returncode:
            print(result.stderr.strip());raise SystemExit(result.returncode)
    subprocess.run(['git','-C',str(root),'add','--',*existing],check=True)
    subprocess.run([__import__('sys').executable,str(root/'tools/audit_publication.py'),'--index'],check=True)

if __name__=='__main__':main()
