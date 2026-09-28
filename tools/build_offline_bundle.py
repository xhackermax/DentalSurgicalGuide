from __future__ import annotations
import argparse, hashlib, json, shutil, tempfile, zipfile
from pathlib import Path


def sha256(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(8*1024*1024),b''): h.update(chunk)
    return h.hexdigest()


def main():
    ap=argparse.ArgumentParser(description='Build the self-contained DSG TotalSegmentator ZIP.')
    ap.add_argument('--addon-root', required=True, help='Folder containing dsg/')
    ap.add_argument('--runtime', required=True, help='runtime_win64_py313_cuda_totalseg218.zip')
    ap.add_argument('--dataset113', required=True, help='Dataset113_ToothFairy3.zip')
    ap.add_argument('--dataset115', required=True, help='Dataset115_mandible.zip')
    ap.add_argument('--output', required=True)
    ns=ap.parse_args()
    base=Path(ns.addon_root).resolve(); dsg=base/'dsg'; payload=dsg/'offline_totalseg'; mf=payload/'OFFLINE_PAYLOAD_MANIFEST.json'
    if not dsg.is_dir() or not mf.is_file(): raise SystemExit('addon-root must contain dsg/offline_totalseg/OFFLINE_PAYLOAD_MANIFEST.json')
    sources={'runtime_archive':Path(ns.runtime).resolve(),'dataset113':Path(ns.dataset113).resolve(),'dataset115':Path(ns.dataset115).resolve()}
    data=json.loads(mf.read_text(encoding='utf-8'))
    for key,src in sources.items():
        if not src.is_file(): raise SystemExit(f'Missing {key}: {src}')
        rel=Path(data['files'][key]['path']); dst=payload/rel; dst.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(src,dst)
        data['files'][key]['size']=dst.stat().st_size; data['files'][key]['sha256']=sha256(dst)
    mf.write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding='utf-8')
    out=Path(ns.output).resolve(); out.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6,allowZip64=True) as z:
        for p in dsg.rglob('*'):
            if p.is_file() and '__pycache__' not in p.parts and p.suffix not in {'.pyc','.pyo'}:
                z.write(p,p.relative_to(base).as_posix())
    print(out)

if __name__=='__main__': main()
