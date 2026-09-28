from __future__ import annotations

import logging as _dsg_logging
_DSG_LOG = _dsg_logging.getLogger(__name__)
import json, os, sys, time, types
from pathlib import Path

def atomic_json(path,payload):
    data=json.dumps(payload,ensure_ascii=False,default=str)
    for attempt in range(20):
        tmp=path.with_name(f"{path.name}.{os.getpid()}.{attempt}.tmp")
        try:
            tmp.write_text(data,encoding='utf-8')
            os.replace(tmp,path)
            return
        except PermissionError:
            try: tmp.unlink(missing_ok=True)
            except Exception: _DSG_LOG.debug("suppressed exception", exc_info=True)
            time.sleep(0.05)
    path.write_text(data,encoding='utf-8')

def bootstrap(req):
    addon=Path(req['addon_dir']).resolve(); parent=str(addon.parent)
    if parent not in sys.path: sys.path.insert(0,parent)
    for p in (req.get('runtime_site_packages'),req.get('dicom_vendor_dir')):
        if p and str(p) not in sys.path: sys.path.insert(0,str(p))
    if 'dsg' not in sys.modules:
        pkg=types.ModuleType('dsg'); pkg.__path__=[str(addon)]; pkg.__package__='dsg'; sys.modules['dsg']=pkg

def main():
    req=json.loads(Path(sys.argv[-1]).read_text(encoding='utf-8')); out=Path(req['output_dir']); out.mkdir(parents=True,exist_ok=True); status=out/'status.json'; result=out/'result.json'
    bootstrap(req)
    from dsg import cbct_pipeline_tasks
    def cb(msg): atomic_json(status,{'message':str(msg),'task':req.get('task'),'time':time.time()})
    cb('Worker CPU iniciado')
    payload=cbct_pipeline_tasks.run_task(req,cb)
    atomic_json(result,{'status':'OK','payload':payload}); cb('Listo')
if __name__=='__main__':
    try: main()
    except Exception as exc:
        try:
            req=json.loads(Path(sys.argv[-1]).read_text(encoding='utf-8')); out=Path(req['output_dir']); out.mkdir(parents=True,exist_ok=True)
            atomic_json(out/'result.json',{'status':'ERROR','error':f'{type(exc).__name__}: {exc}'})
            atomic_json(out/'status.json',{'message':f'Error: {type(exc).__name__}: {exc}','time':time.time()})
        except Exception: _DSG_LOG.debug("suppressed exception", exc_info=True)
        raise
