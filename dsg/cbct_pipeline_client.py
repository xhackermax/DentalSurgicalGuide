"""Blender-side client for DSG 9.5 TotalSegmentator external pipeline.

Only subprocess launch, tiny JSON polling and cleanup happen here. No Torch,
VTK, Tooth Path, calibration or full-volume copy runs on Blender's UI thread.
"""
from __future__ import annotations

import logging as _dsg_logging
_DSG_LOG = _dsg_logging.getLogger(__name__)
import json, os, subprocess, sys, tempfile, time, shutil
from pathlib import Path

_JOB={'process':None,'log':None,'job_dir':'','request_path':'','started':0.0,'consumed':False,'error':'','fallback_attempted':False,'env':None}

def _tail(path,n=5000):
    try: return path.read_text(encoding='utf-8',errors='replace')[-n:]
    except Exception: return ''


def _json_geometry(value):
    if value is None:
        return None
    try:
        import numpy as np
        if isinstance(value, np.ndarray):
            return _json_geometry(value.tolist())
        if isinstance(value, np.generic):
            return float(value)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    if isinstance(value, (list, tuple)):
        return [_json_geometry(v) for v in value]
    return float(value)

def _python_prefix():
    import bpy
    # Blender 5.2 exposes the supported direct-Python invocation prefix.
    return [str(sys.executable), *[str(v) for v in tuple(getattr(bpy.app,'python_args',()) or ())]]

def _creationflags():
    if os.name!='nt': return 0
    return getattr(subprocess,'CREATE_NO_WINDOW',0)|getattr(subprocess,'BELOW_NORMAL_PRIORITY_CLASS',0)

def _launch_blender_fallback(job, request_path, log, env):
    import bpy
    binary=str(getattr(bpy.app,'binary_path','') or '')
    if not binary:
        raise RuntimeError('No se encontró Blender para fallback del worker')
    script=Path(__file__).resolve().parent/'cbct_pipeline_worker.py'
    cmd=[binary,'--background','--factory-startup','--python',str(script),'--',str(request_path)]
    return subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,env=env,creationflags=_creationflags())

def start_full_pipeline(*, volume_path,slopes_path,intercepts_path,dims_zyx,spacing_zyx,source_signature,orientation_xyz,image_origin_patient,device_preference,totalseg_site_paths,totalseg_home_dir,totalseg_version,dicom_vendor_dir,route_mode="FULL"):

    proc=_JOB.get('process')
    if proc is not None and proc.poll() is None: return False
    addon=Path(__file__).resolve().parent; job=Path(tempfile.mkdtemp(prefix='DSG_PIPELINE_'))
    req={'job_dir':str(job),'addon_dir':str(addon),'volume_path':str(volume_path),'slopes_path':str(slopes_path),'intercepts_path':str(intercepts_path),'dims_zyx':[int(v) for v in dims_zyx],'spacing_zyx':[float(v) for v in spacing_zyx],'source_signature':str(source_signature),'orientation_xyz':_json_geometry(orientation_xyz),'image_origin_patient':_json_geometry(image_origin_patient),'device_preference':str(device_preference),'totalseg_site_paths':[str(v) for v in (totalseg_site_paths or [])],'totalseg_home_dir':str(totalseg_home_dir),'totalseg_version':str(totalseg_version),'dicom_vendor_dir':str(dicom_vendor_dir),'route_mode':str(route_mode or 'FULL').upper(),'python_prefix':_python_prefix()}
    rp=job/'request.json'; rp.write_text(json.dumps(req,ensure_ascii=False),encoding='utf-8'); log=(job/'pipeline.log').open('w',encoding='utf-8',errors='replace')
    env=os.environ.copy(); env['PYTHONUNBUFFERED']='1'; logical=max(1,int(os.cpu_count() or 1)); boot_threads=max(1,min(8,logical//2 if logical>=4 else logical)); env['OMP_NUM_THREADS']=str(boot_threads); env['MKL_NUM_THREADS']=str(boot_threads); env['OPENBLAS_NUM_THREADS']=str(boot_threads); env['NUMEXPR_NUM_THREADS']=str(boot_threads)
    # Blender's sys.executable is normally blender.exe on Windows. Passing a .py
    # file as if it were a standalone Python interpreter can leave a live Blender
    # process doing nothing forever. Run the isolated worker through Blender's
    # documented background --python path from the start.
    p=_launch_blender_fallback(job,rp,log,env)
    fallback_attempted=True
    _JOB.update(process=p,log=log,job_dir=str(job),request_path=str(rp),started=time.perf_counter(),consumed=False,error='',fallback_attempted=fallback_attempted,env=env)
    return True

def state():
    proc=_JOB.get('process'); job=Path(str(_JOB.get('job_dir') or ''))
    payload={'running':False,'done':False,'error':'','phase':'','message':'','factor':0.0,'elapsed_s':max(0.0,time.perf_counter()-float(_JOB.get('started') or time.perf_counter()))}
    if job and (job/'status.json').is_file():
        try: payload.update(json.loads((job/'status.json').read_text(encoding='utf-8')))
        except Exception: _DSG_LOG.debug("suppressed exception", exc_info=True)
    if proc is None: return payload
    rc=proc.poll(); payload['running']=rc is None
    if rc is None:
        # A worker must publish status.json almost immediately, before model load.
        # Never allow a permanently live but inert subprocess to look like valid
        # segmentation progress.
        age=max(0.0,time.perf_counter()-float(_JOB.get('started') or time.perf_counter()))
        if age > 20.0 and not (job/'status.json').is_file():
            try: proc.terminate()
            except Exception: _DSG_LOG.debug("suppressed exception", exc_info=True)
            payload['running']=False
            payload['error']='El worker de segmentación no arrancó en 20 s. '+_tail(job/'pipeline.log',2200)
        return payload
    manifest=job/'manifest.json'
    if manifest.is_file():
        try:
            meta=json.loads(manifest.read_text(encoding='utf-8'))
            if str(meta.get('status')).upper()=='OK': payload['done']=True; payload['factor']=max(float(payload.get('factor',0.0)),0.94)
            else: payload['error']=str(meta.get('error') or f'Pipeline terminó con código {rc}')
        except Exception as exc: payload['error']=f'Manifest inválido: {exc}'
    else:
        # Direct Python is preferred. If a specific Blender build cannot launch
        # it with bpy.app.python_args, retry once in a background Blender process.
        if not bool(_JOB.get('fallback_attempted')):
            try:
                lg=_JOB.get('log')
                if lg is not None:
                    try: lg.flush()
                    except Exception: _DSG_LOG.debug("suppressed exception", exc_info=True)
                p=_launch_blender_fallback(job,Path(str(_JOB.get('request_path'))),lg,_JOB.get('env') or os.environ.copy())
                _JOB['process']=p; _JOB['fallback_attempted']=True
                payload.update(running=True,error='',message='Python directo no inició · fallback aislado Blender…')
                return payload
            except Exception as exc:
                payload['error']=f'Python directo falló ({rc}) y fallback no inició: {exc}. '+_tail(job/'pipeline.log',1800)
        else:
            payload['error']=f'Pipeline terminó con código {rc}. '+_tail(job/'pipeline.log',1800)
    return payload

def consume_manifest():
    st=state()
    if not st.get('done') or _JOB.get('consumed'): return None
    job=Path(str(_JOB.get('job_dir') or '')); meta=json.loads((job/'manifest.json').read_text(encoding='utf-8')); _JOB['consumed']=True; return meta

def artifact_dir():
    return str(_JOB.get('job_dir') or '')

def release_process_keep_artifacts():
    p=_JOB.get('process')
    if p is not None and p.poll() is None:
        return False
    lg=_JOB.get('log')
    if lg is not None:
        try: lg.close()
        except Exception: _DSG_LOG.debug("suppressed exception", exc_info=True)
    _JOB.update(process=None,log=None)
    return True

def cancel():
    p=_JOB.get('process')
    if p is not None and p.poll() is None:
        try: p.terminate(); p.wait(timeout=2.0)
        except Exception:
            try: p.kill()
            except Exception: _DSG_LOG.debug("suppressed exception", exc_info=True)
    lg=_JOB.get('log')
    if lg is not None:
        try: lg.close()
        except Exception: _DSG_LOG.debug("suppressed exception", exc_info=True)
    _JOB.update(process=None,log=None,error='')

def cleanup_artifacts():
    cancel(); job=str(_JOB.get('job_dir') or '')
    _JOB.update(job_dir='',request_path='',consumed=False,started=0.0,fallback_attempted=False,env=None)
    if job:
        try: shutil.rmtree(job,ignore_errors=True)
        except Exception: _DSG_LOG.debug("suppressed exception", exc_info=True)
