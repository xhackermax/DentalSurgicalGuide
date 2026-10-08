"""Blender-side client for DSG 9.10 multi-engine dental segmentation pipeline.

Only subprocess launch, tiny JSON polling and cleanup happen here. No Torch,
VTK, Tooth Path, calibration or full-volume copy runs on Blender's UI thread.
"""
from __future__ import annotations

import logging as _dsg_logging
_DSG_LOG = _dsg_logging.getLogger(__name__)
import json, os, subprocess, sys, tempfile, time, shutil, uuid
from pathlib import Path
from . import error_handling
from .pipeline_core import ResultManifest,ContractError

_JOB={'process':None,'log':None,'job_dir':'','request_path':'','started':0.0,'consumed':False,'error':'','fallback_attempted':False,'env':None,'fallback_events':[],'run_id':'','diagnostic_path':''}

def _tail(path,n=5000):
    try: return path.read_text(encoding='utf-8',errors='replace')[-n:]
    except OSError:
        _DSG_LOG.debug('No se pudo leer el log del worker',exc_info=True)
        return ''


def _json_geometry(value):
    if value is None:
        return None
    try:
        import numpy as np
        if isinstance(value, np.ndarray):
            return _json_geometry(value.tolist())
        if isinstance(value, np.generic):
            return float(value)
    except ImportError:
        _DSG_LOG.debug('NumPy no disponible para adaptar geometría',exc_info=True)
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

def _launch_python_worker(request_path, log, env, python_executable):
    py = str(python_executable or '').strip()
    if not py or not Path(py).is_file():
        raise RuntimeError('No se encontró el Python interno de Blender para el worker IA')
    script = Path(__file__).resolve().parent / 'cbct_pipeline_worker.py'
    return subprocess.Popen(
        [py, str(script), str(request_path)],
        stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
        env=env, creationflags=_creationflags(),
    )


def _launch_blender_fallback(job, request_path, log, env):
    import bpy
    binary=str(getattr(bpy.app,'binary_path','') or '')
    if not binary:
        raise RuntimeError('No se encontró Blender para fallback del worker')
    script=Path(__file__).resolve().parent/'cbct_pipeline_worker.py'
    cmd=[binary,'--background','--factory-startup','--python',str(script),'--',str(request_path)]
    return subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,env=env,creationflags=_creationflags())

def start_full_pipeline(*, volume_path,slopes_path,intercepts_path,dims_zyx,spacing_zyx,source_signature,orientation_xyz,image_origin_patient,device_preference,engine,engine_site_paths,engine_env,dicom_vendor_dir,python_executable="",route_mode="FULL",toothseg_repo="",umamba2_repo="",umamba2_models=""):

    import bpy
    proc=_JOB.get('process')
    if proc is not None and proc.poll() is None: return False
    addon=Path(__file__).resolve().parent; job=Path(tempfile.mkdtemp(prefix='DSG_PIPELINE_'))
    req={'job_dir':str(job),'addon_dir':str(addon),'volume_path':str(volume_path),'slopes_path':str(slopes_path),'intercepts_path':str(intercepts_path),'dims_zyx':[int(v) for v in dims_zyx],'spacing_zyx':[float(v) for v in spacing_zyx],'source_signature':str(source_signature),'orientation_xyz':_json_geometry(orientation_xyz),'image_origin_patient':_json_geometry(image_origin_patient),'device_preference':str(device_preference),'engine':str(engine or 'TOTALSEG').upper(),'engine_site_paths':[str(v) for v in (engine_site_paths or [])],'engine_env':dict(engine_env or {}),'dicom_vendor_dir':str(dicom_vendor_dir),'python_executable':str(python_executable or ''),'route_mode':str(route_mode or 'FULL').upper(),'toothseg_repo':str(toothseg_repo or ''),'umamba2_repo':str(umamba2_repo or ''),'umamba2_models':str(umamba2_models or ''),'python_prefix':_python_prefix(),'blender_binary':str(getattr(bpy.app,'binary_path','') or sys.executable)}
    run_id=uuid.uuid4().hex
    diagnostic=Path(bpy.utils.user_resource('SCRIPTS'))/'dsg_diagnostics'/f'{run_id}.json'
    req.update(schema_version=1,run_id=run_id,diagnostic_path=str(diagnostic),launcher_fallbacks=[])
    rp=job/'request.json'; rp.write_text(json.dumps(req,ensure_ascii=False),encoding='utf-8'); log=(job/'pipeline.log').open('w',encoding='utf-8',errors='replace')
    env=os.environ.copy(); env['PYTHONUNBUFFERED']='1'; logical=max(1,int(os.cpu_count() or 1)); boot_threads=max(1,min(8,logical//2 if logical>=4 else logical)); env['OMP_NUM_THREADS']=str(boot_threads); env['MKL_NUM_THREADS']=str(boot_threads); env['OPENBLAS_NUM_THREADS']=str(boot_threads); env['NUMEXPR_NUM_THREADS']=str(boot_threads)
    # Prefer Blender's bundled standalone Python: it avoids launching a second
    # Blender instance and cuts worker startup overhead. A Blender-background
    # fallback remains available if a particular installation lacks that binary.
    fallback_events=[]
    try:
        p=_launch_python_worker(rp,log,env,python_executable)
        fallback_attempted=False
    except Exception as exc:
        fallback_events.append(error_handling.log_fallback(_DSG_LOG,"DSG-F210",reason=exc,context={"phase":"initial_launch"}))
        try:
            req['launcher_fallbacks'].append('INITIAL_PYTHON_LAUNCH_FAILED')
            rp.write_text(json.dumps(req,ensure_ascii=False),encoding='utf-8')
            p=_launch_blender_fallback(job,rp,log,env)
        except Exception as fallback_exc:
            error_handling.log_exception(_DSG_LOG,"DSG-E210",fallback_exc,context={"phase":"initial_fallback_launch"})
            try: log.close()
            except Exception: _DSG_LOG.debug("suppressed exception",exc_info=True)
            shutil.rmtree(job,ignore_errors=True)
            raise RuntimeError(error_handling.user_message("DSG-E210")) from fallback_exc
        fallback_attempted=True
    _JOB.update(process=p,log=log,job_dir=str(job),request_path=str(rp),started=time.perf_counter(),consumed=False,error='',fallback_attempted=fallback_attempted,env=env,fallback_events=fallback_events,run_id=run_id,diagnostic_path=str(diagnostic))
    return True

def state():
    proc=_JOB.get('process'); job=Path(str(_JOB.get('job_dir') or ''))
    payload={'running':False,'done':False,'error':'','phase':'','message':'','factor':0.0,'fallback_events':list(_JOB.get('fallback_events') or []),'elapsed_s':max(0.0,time.perf_counter()-float(_JOB.get('started') or time.perf_counter()))}
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
            payload['error']=error_handling.user_message('DSG-E210'); _DSG_LOG.error('DSG-E210 worker startup timeout | tail=%s', error_handling.redact(_tail(job/'pipeline.log',2200)))
        return payload
    manifest=job/'manifest.json'
    if manifest.is_file():
        try:
            meta=ResultManifest.parse(json.loads(manifest.read_text(encoding='utf-8')),_JOB['run_id']).payload
            if str(meta.get('status')).upper()=='OK': payload['done']=True; payload['factor']=max(float(payload.get('factor',0.0)),0.94)
            else: payload['error']=str(meta.get('error') or f'Pipeline terminó con código {rc}')
        except Exception as exc: error_handling.log_exception(_DSG_LOG,'DSG-E240',exc,context={'manifest':str(manifest)}); payload['error']=str(exc) if isinstance(exc,ContractError) else error_handling.user_message('DSG-E240')
    else:
        # Direct Python is preferred. If a specific Blender build cannot launch
        # it with bpy.app.python_args, retry once in a background Blender process.
        if not bool(_JOB.get('fallback_attempted')):
            try:
                lg=_JOB.get('log')
                if lg is not None:
                    try: lg.flush()
                    except Exception: _DSG_LOG.debug("suppressed exception", exc_info=True)
                request_path=Path(str(_JOB['request_path']))
                request=json.loads(request_path.read_text(encoding='utf-8'))
                request['launcher_fallbacks'].append('PYTHON_WORKER_NO_MANIFEST')
                request_path.write_text(json.dumps(request,ensure_ascii=False),encoding='utf-8')
                p=_launch_blender_fallback(job,request_path,lg,_JOB.get('env') or os.environ.copy())
                _JOB['process']=p; _JOB['fallback_attempted']=True
                event=error_handling.log_fallback(_DSG_LOG,'DSG-F210',reason=f'python_worker_rc={rc}',context={'phase':'retry'}); _JOB.setdefault('fallback_events',[]).append(event); payload.update(running=True,error='',message=error_handling.user_message('DSG-F210'))
                return payload
            except Exception as exc:
                error_handling.log_exception(_DSG_LOG,'DSG-E210',exc,context={'python_worker_rc':rc}); payload['error']=error_handling.user_message('DSG-E210')
        else:
            _DSG_LOG.error('DSG-E230 pipeline rc=%s | tail=%s',rc,error_handling.redact(_tail(job/'pipeline.log',1800))); payload['error']=error_handling.user_message('DSG-E230')
    return payload


def snapshot_failure_diagnostics():
    """Persist redacted worker evidence before transactional cleanup.

    Raw request files may contain patient/workstation paths and are never copied
    verbatim into the persistent failure snapshot. Diagnostic snapshots are
    retained only as a small rotating set.
    """
    job=Path(str(_JOB.get('job_dir') or ''))
    if not job.is_dir(): return ''
    try:
        lg=_JOB.get('log')
        if lg is not None:
            try: lg.flush()
            except Exception: _DSG_LOG.debug("suppressed exception", exc_info=True)
        base=Path(tempfile.gettempdir())/'DSG_SEGMENTATION_FAILURES'
        base.mkdir(parents=True,exist_ok=True)
        # Keep only the ten newest diagnostic snapshots.
        old=sorted((p for p in base.iterdir() if p.is_dir()),key=lambda p:p.name,reverse=True)
        for stale in old[9:]:
            try: shutil.rmtree(stale,ignore_errors=True)
            except Exception: _DSG_LOG.debug("suppressed exception",exc_info=True)
        stamp=time.strftime('%Y%m%d_%H%M%S')
        root=base/stamp
        root.mkdir(parents=True,exist_ok=True)
        request=job/'request.json'
        if request.is_file():
            try:
                raw=json.loads(request.read_text(encoding='utf-8',errors='replace'))
                for key in ('job_dir','addon_dir','volume_path','slopes_path','intercepts_path','dicom_vendor_dir','python_executable','blender_binary','toothseg_repo','umamba2_repo','umamba2_models'):
                    if key in raw: raw[key]='<REDACTED_PATH>'
                raw['engine_site_paths']=['<REDACTED_PATH>' for _ in raw.get('engine_site_paths',[])]
                raw['python_prefix']=['<REDACTED_PATH>' for _ in raw.get('python_prefix',[])]
                (root/'request_redacted.json').write_text(json.dumps(raw,ensure_ascii=False,indent=2),encoding='utf-8')
            except Exception as exc:
                error_handling.log_exception(_DSG_LOG,'DSG-E900',exc,context={'phase':'redact_request_snapshot'})
        for name in ('status.json','manifest.json','pipeline.log','teeth.log','surfaces.log'):
            src=job/name
            if src.is_file():
                try:
                    text=src.read_text(encoding='utf-8',errors='replace')
                    (root/name).write_text(error_handling.redact(text),encoding='utf-8')
                except Exception: _DSG_LOG.debug("suppressed exception", exc_info=True)
        try:
            (root/'client_state.json').write_text(error_handling.redact(json.dumps(state(),ensure_ascii=False,indent=2,default=str)),encoding='utf-8')
        except Exception: _DSG_LOG.debug("suppressed exception", exc_info=True)
        return str(root)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
        return ''

def consume_manifest():
    st=state()
    if not st.get('done') or _JOB.get('consumed'): return None
    job=Path(str(_JOB.get('job_dir') or '')); meta=ResultManifest.parse(json.loads((job/'manifest.json').read_text(encoding='utf-8')),_JOB['run_id']).payload; _JOB['consumed']=True; return meta

def diagnostic_text(diagnostics_root=None):
    """Copy only the structured run record, never private request/log contents."""
    path=Path(_JOB['diagnostic_path']) if _JOB['diagnostic_path'] else None
    if path is None or not path.is_file():
        if diagnostics_root is None:return ''
        root=Path(diagnostics_root)
        files=list(root.glob('*.json')) if root.is_dir() else []
        if not files:return ''
        path=max(files,key=lambda p:p.stat().st_mtime)
    payload=json.loads(path.read_text(encoding='utf-8'))
    return json.dumps(payload,ensure_ascii=False,indent=2)

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
    _JOB.update(job_dir='',request_path='',consumed=False,started=0.0,fallback_attempted=False,env=None,fallback_events=[])
    if job:
        try: shutil.rmtree(job,ignore_errors=True)
        except Exception: _DSG_LOG.debug("suppressed exception", exc_info=True)
