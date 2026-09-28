from __future__ import annotations

import logging as _dsg_logging
_DSG_LOG = _dsg_logging.getLogger(__name__)
import json, os, re, sys, time, types, subprocess, threading
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
    runtime_paths=[str(p) for p in (req.get('totalseg_site_paths') or []) if p]
    if parent not in sys.path: sys.path.insert(0,parent)
    for p in reversed(runtime_paths):
        if p and str(p) not in sys.path: sys.path.insert(0,str(p))
    dv=req.get('dicom_vendor_dir')
    if dv and str(dv) not in sys.path: sys.path.insert(0,str(dv))
    py_path=os.pathsep.join(runtime_paths+[parent]+(([str(dv)] if dv else [])))
    if py_path:
        existing=os.environ.get('PYTHONPATH','')
        os.environ['PYTHONPATH']=py_path+(os.pathsep+existing if existing else '')
    if 'dsg' not in sys.modules:
        pkg=types.ModuleType('dsg'); pkg.__path__=[str(addon)]; pkg.__package__='dsg'; sys.modules['dsg']=pkg
    os.environ['TOTALSEG_HOME_DIR']=str(req.get('totalseg_home_dir') or '')
    logical=max(1,int(os.cpu_count() or 1)); threads=max(1,logical-1)
    for key in ('OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS','NUMEXPR_NUM_THREADS'):
        os.environ[key]=str(threads)
    os.environ['DSG_WORKER_CPU_THREADS']=str(threads)

def _fdi_to_compat(fdi:int)->int|None:
    fdi=int(fdi)
    if 11<=fdi<=18: return 19-fdi
    if 21<=fdi<=28: return fdi-12
    if 31<=fdi<=38: return 55-fdi
    if 41<=fdi<=48: return fdi-16
    return None

def _make_affine(np,spacing_zyx,orientation_xyz,origin_lps):
    sz,sy,sx=(float(v) for v in spacing_zyx)
    if orientation_xyz is not None:
        o=np.asarray(orientation_xyz,dtype=np.float64)
        if o.shape==(3,3):
            lps=np.eye(4,dtype=np.float64)
            lps[:3,0]=o[:,0]*sx; lps[:3,1]=o[:,1]*sy; lps[:3,2]=o[:,2]*sz
            if origin_lps is not None and len(origin_lps)>=3: lps[:3,3]=np.asarray(origin_lps[:3],dtype=np.float64)
            ras=np.diag([-1.0,-1.0,1.0,1.0])@lps
            return ras
    aff=np.eye(4,dtype=np.float64); aff[0,0]=sx; aff[1,1]=sy; aff[2,2]=sz
    return aff

def _translate_totalseg_simple_arches(np, ts_labels, class_map):
    """Collapse raw TotalSegmentator labels directly to 1=upper / 2=lower.

    SIMPLE never needs FDI identity. A tiny lookup table avoids constructing the
    full compatibility labelmap and avoids dozens of full-volume equality masks.
    """
    max_id=max((int(v) for v in class_map.keys()),default=0)
    lut=np.zeros(max_id+1,dtype=np.uint8)
    for raw_id,name in class_map.items():
        rid=int(raw_id); name=str(name)
        if name=='upper_jawbone': lut[rid]=1; continue
        if name=='lower_jawbone': lut[rid]=2; continue
        if '_pulp_' in name: continue
        m=re.search(r'_fdi(\d+)$',name)
        if not m: continue
        fdi=int(m.group(1)); quadrant=fdi//10
        if quadrant in (1,2): lut[rid]=1
        elif quadrant in (3,4): lut[rid]=2
    if max_id <= 0:
        return np.zeros(ts_labels.shape,dtype=np.uint8), {'upper_voxels':0,'lower_voxels':0}
    route=lut[np.asarray(ts_labels,dtype=np.uint8)]
    return route, {
        'upper_voxels':int(np.count_nonzero(route==1)),
        'lower_voxels':int(np.count_nonzero(route==2)),
    }


def _translate_totalseg(np,ts_labels,class_map):
    """Translate TotalSegmentator task=teeth labels to DSG's proven mesh contract.

    This is not a second segmentation or semantic correction. It is only an
    integer relabeling so legacy Blender geometry builders can consume the new
    model without changing patient-space geometry.
    """
    compat=np.zeros(ts_labels.shape,dtype=np.uint8)
    counts={}
    for raw_id,name in class_map.items():
        rid=int(raw_id); name=str(name); mask=(ts_labels==rid)
        n=int(mask.sum())
        if not n: continue
        counts[name]=n
        if name=='lower_jawbone': compat[mask]=53; continue
        if name=='upper_jawbone': compat[mask]=54; continue
        if name in {'left_inferior_alveolar_canal','right_inferior_alveolar_canal'}:
            compat[mask]=55; continue
        m=re.search(r'_fdi(\d+)$',name)
        if not m or '_pulp_' in name: continue
        fdi=int(m.group(1))
        ul=_fdi_to_compat(fdi)
        if ul is None: continue
        compat[mask]=int(ul)
    return compat,counts

def main():
    req_path=Path(sys.argv[-1]).resolve(); req=json.loads(req_path.read_text(encoding='utf-8')); job=Path(req['job_dir']).resolve(); job.mkdir(parents=True,exist_ok=True)
    status_path=job/'status.json'; manifest_path=job/'manifest.json'; t0=time.perf_counter(); lock=threading.Lock(); heartbeat_stop=threading.Event(); live={'phase':'bootstrap','message':'Worker TotalSegmentator iniciado…','factor':0.01}
    def status(phase,msg,factor,extra=None):
        with lock:
            live.update(phase=str(phase),message=str(msg),factor=float(factor))
            payload={'status':'RUNNING','phase':str(phase),'message':str(msg),'factor':float(factor),'elapsed_s':float(time.perf_counter()-t0),'time':time.time()}
            if extra: payload.update(extra)
            atomic_json(status_path,payload)
    def heartbeat():
        while not heartbeat_stop.wait(2.0):
            with lock:
                atomic_json(status_path,{'status':'RUNNING','phase':live['phase'],'message':live['message'],'factor':live['factor'],'elapsed_s':float(time.perf_counter()-t0),'time':time.time(),'heartbeat':True})
    status('bootstrap','Worker externo TotalSegmentator iniciado · preparando task=teeth…',0.01)
    bootstrap(req); threading.Thread(target=heartbeat,daemon=True,name='DSG-TS-Heartbeat').start()
    try:
        home=Path(os.environ.get('TOTALSEG_HOME_DIR','')); home.mkdir(parents=True,exist_ok=True); cfg=home/'config.json'
        if not cfg.exists(): cfg.write_text(json.dumps({'totalseg_id':'dsg_local','send_usage_stats':False,'prediction_counter':0},indent=2),encoding='utf-8')
    except Exception: _DSG_LOG.debug("suppressed exception", exc_info=True)
    import numpy as np
    import nibabel as nib
    import torch
    from totalsegmentator.python_api import totalsegmentator
    from totalsegmentator.registry import get_task_classes
    from dsg import cbct_pipeline_tasks

    volume=np.load(req['volume_path'],mmap_mode='r'); slopes=np.load(req['slopes_path'],mmap_mode='r'); intercepts=np.load(req['intercepts_path'],mmap_mode='r')
    spacing=tuple(float(v) for v in req['spacing_zyx']); dims=tuple(int(v) for v in req['dims_zyx']); signature=str(req['source_signature']); pref=str(req.get('device_preference') or 'AUTO').upper(); route_mode=str(req.get('route_mode') or 'FULL').upper()
    logical=max(1,int(os.cpu_count() or 1)); threads=max(1,logical-1)
    resamp_threads=1 if os.name=='nt' else max(1,min(8,threads))
    try: torch.set_num_threads(threads)
    except Exception: _DSG_LOG.debug("suppressed exception", exc_info=True)
    status('input','Calibrando CBCT y construyendo NIfTI en memoria…',0.05)
    # Calibrate in a single float32 array. This is the only full-resolution input
    # copy and is released immediately after TotalSegmentator returns.
    calibrated=np.asarray(volume,dtype=np.float32).copy()
    calibrated*=np.asarray(slopes,dtype=np.float32)[:,None,None]
    calibrated+=np.asarray(intercepts,dtype=np.float32)[:,None,None]
    xyz=np.ascontiguousarray(np.transpose(calibrated,(2,1,0)))
    del calibrated
    affine=_make_affine(np,spacing,req.get('orientation_xyz'),req.get('image_origin_patient'))
    image=nib.Nifti1Image(xyz,affine)
    device='cpu' if pref=='CPU' else ('gpu' if torch.cuda.is_available() else 'cpu')
    if device=='gpu':
        try:
            torch.backends.cudnn.benchmark=True
            if hasattr(torch.backends.cuda.matmul,'allow_tf32'): torch.backends.cuda.matmul.allow_tf32=True
            if hasattr(torch.backends.cudnn,'allow_tf32'): torch.backends.cudnn.allow_tf32=True
        except Exception: _DSG_LOG.debug("suppressed exception", exc_info=True)
    status('totalsegmentator',f'TotalSegmentator · task=teeth · geometría suave · {device.upper()} · CPU {threads} hilos…',0.12,{'engine':'TotalSegmentator','task':'teeth','device':device,'cpu_threads':threads,'resample_workers':resamp_threads,'higher_order_resampling':True})
    ts_started=time.perf_counter(); gpu_error=''
    try:
        seg=totalsegmentator(image,None,ml=True,task='teeth',device=device,quiet=True,verbose=False,skip_saving=True,nr_thr_resamp=resamp_threads,nr_thr_saving=1,resampling_order=1,higher_order_resampling=True)
        used=device
    except Exception as exc:
        if device=='cpu': raise
        gpu_error=f'{type(exc).__name__}: {exc}'
        status('totalsegmentator',f'CUDA falló · reintentando task=teeth en CPU…',0.20,{'gpu_error':gpu_error})
        try: torch.cuda.empty_cache()
        except Exception: _DSG_LOG.debug("suppressed exception", exc_info=True)
        seg=totalsegmentator(image,None,ml=True,task='teeth',device='cpu',quiet=True,verbose=False,skip_saving=True,nr_thr_resamp=resamp_threads,nr_thr_saving=1,resampling_order=1,higher_order_resampling=True)
        used='cpu'
    ts_s=time.perf_counter()-ts_started
    status('translate','TotalSegmentator terminado · traduciendo FDI y anatomía…',0.67,{'compute_device':used,'totalseg_s':ts_s})
    ts_xyz=np.asanyarray(seg.dataobj).astype(np.uint8,copy=False)
    if tuple(ts_xyz.shape)!=tuple(xyz.shape):
        raise RuntimeError(f'TotalSegmentator devolvió {tuple(ts_xyz.shape)} y se esperaba {tuple(xyz.shape)}')
    ts_zyx=np.ascontiguousarray(np.transpose(ts_xyz,(2,1,0)))
    classes=get_task_classes('teeth')

    # SIMPLE bypasses the complete FDI compatibility translation. Convert the
    # model output in one vectorized lookup directly to upper/lower identity.
    if route_mode == 'SIMPLE_ARCHES':
        route_labels,class_counts=_translate_totalseg_simple_arches(np,ts_zyx,classes)
        del ts_zyx,ts_xyz,seg,image,xyz
        if not np.any(route_labels==1) or not np.any(route_labels==2):
            raise RuntimeError('TotalSegmentator no devolvió ambas arcadas para la ruta simple')
        status('simple_arches','Ruta simple · creando únicamente dos arcadas…',0.74)
        simple_dir=job/'simple_arches'; simple_dir.mkdir(exist_ok=True)
        simple=cbct_pipeline_tasks.prepare_simple_arches_route_map(
            route_labels, spacing, dims, simple_dir,
            lambda m: status('simple_arches',str(m),0.84))
        del route_labels
        timings={'totalsegmentator_teeth_s':float(ts_s),'simple_surface_s':float(simple.get('surface_prepare_s',0.0) or 0.0),'total_external_s':float(time.perf_counter()-t0)}
        metadata={'engine':'TotalSegmentator','version':str(req.get('totalseg_version') or ''),'task':'teeth','device':used,'cpu_threads':threads,'resample_workers':resamp_threads,'higher_order_resampling':True,'input_resampling_order':1,'gpu_fallback_error':gpu_error,'class_voxels':class_counts,'route_mode':'SIMPLE_ARCHES','identity_contract':'UPPER_LOWER_ONLY'}
        manifest={'status':'OK','source_signature':signature,'route_mode':'SIMPLE_ARCHES','simple_arches':True,'universal_labels_path':'','path_stats':{},'semantic_info':{'identity_exposed':False,'route':'SIMPLE_ARCHES','identity_contract':'UPPER_LOWER_ONLY'},'prepared_meshes':{},'prepared_surfaces':simple,'semantic_metadata':metadata,'universal_metadata':metadata,'timings':timings,'worker_failures_recovered':{},'segmentation_engine':'TotalSegmentator','totalseg_task':'teeth','hybrid_gpu_cpu':False}
        atomic_json(manifest_path,manifest); status('ready','Ruta simple lista · dos arcadas preparadas',0.94,{'done':True}); heartbeat_stop.set(); return

    # FULL/IMMEDIATE keeps the complete FDI compatibility labelmap as SSOT.
    universal,class_counts=_translate_totalseg(np,ts_zyx,classes)
    del ts_zyx,ts_xyz,seg,image,xyz
    if not np.any((universal>=1)&(universal<=52)):
        raise RuntimeError('TotalSegmentator task=teeth no devolvió ningún diente FDI')
    universal_path=job/'totalseg_compat_labels.npy'
    np.save(str(universal_path),universal,allow_pickle=False)

    # Geometry work is CPU-parallel after the single TotalSegmentator inference.
    cpu_total=max(2,threads); each=max(1,cpu_total//2)
    runtime_site_packages=os.pathsep.join(str(p) for p in (req.get('totalseg_site_paths') or []) if p)
    common={'addon_dir':req['addon_dir'],'runtime_site_packages':runtime_site_packages,'dicom_vendor_dir':req.get('dicom_vendor_dir'),'spacing_zyx':list(spacing),'dims_zyx':list(dims),'universal_labels_path':str(universal_path),'orientation_xyz':req.get('orientation_xyz'),'image_origin_patient':req.get('image_origin_patient')}
    teeth_dir=job/'teeth_task'; surf_dir=job/'surfaces_task'; teeth_dir.mkdir(exist_ok=True); surf_dir.mkdir(exist_ok=True)
    teeth_req=dict(common,task='teeth',output_dir=str(teeth_dir))
    surf_req=dict(common,task='surfaces',output_dir=str(surf_dir))
    tr=job/'teeth_request.json'; sr=job/'surfaces_request.json'; atomic_json(tr,teeth_req); atomic_json(sr,surf_req)
    child_script=Path(req['addon_dir'])/'cbct_pipeline_cpu_worker.py'; env=os.environ.copy()
    if runtime_site_packages:
        env['PYTHONPATH']=runtime_site_packages+(os.pathsep+env.get('PYTHONPATH','') if env.get('PYTHONPATH') else '')
    for k in ('OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS','NUMEXPR_NUM_THREADS'): env[k]=str(each)
    env['DSG_WORKER_CPU_THREADS']=str(each)
    flags=getattr(subprocess,'CREATE_NO_WINDOW',0) if os.name=='nt' else 0; children={}; logs={}
    for name,rp in [('teeth',tr),('surfaces',sr)]:
        lf=(job/f'{name}.log').open('w',encoding='utf-8',errors='replace'); logs[name]=lf
        children[name]=subprocess.Popen([*[str(v) for v in (req.get('python_prefix') or [sys.executable])],str(child_script),str(rp)],stdout=lf,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,env=env,creationflags=flags)
    status('postprocess','TotalSegmentator listo · dientes y superficies CPU en paralelo…',0.72)
    task_msgs={'teeth':'iniciando','surfaces':'iniciando'}
    while any(p.poll() is None for p in children.values()):
        for name,outdir in [('teeth',teeth_dir),('surfaces',surf_dir)]:
            sp=outdir/'status.json'
            if sp.is_file():
                try: task_msgs[name]=str(json.loads(sp.read_text(encoding='utf-8')).get('message') or task_msgs[name])
                except Exception: _DSG_LOG.debug("suppressed exception", exc_info=True)
        status('postprocess',f"Dientes: {task_msgs['teeth']} · Hueso/canal: {task_msgs['surfaces']}",0.82)
        time.sleep(0.12)
    for f in logs.values():
        try:f.close()
        except Exception:_DSG_LOG.debug("suppressed exception", exc_info=True)
    results={}; failures={}
    for name,outdir,rq in [('teeth',teeth_dir,teeth_req),('surfaces',surf_dir,surf_req)]:
        rp=outdir/'result.json'
        try:
            meta=json.loads(rp.read_text(encoding='utf-8'))
            if str(meta.get('status')).upper()!='OK': raise RuntimeError(str(meta.get('error') or 'worker error'))
            results[name]=meta['payload']
        except Exception as exc:
            failures[name]=f'{type(exc).__name__}: {exc}'; status('postprocess',f'{name} worker falló · reintentando en supervisor…',0.84)
            results[name]=cbct_pipeline_tasks.run_task(rq,lambda m: status('postprocess',f'{name}: {m}',0.86))
    teeth=results['teeth']; surfaces=results['surfaces']
    timings={'totalsegmentator_teeth_s':float(ts_s),'tooth_worker_s':float(teeth.get('elapsed_s',0.0) or 0.0),'surface_worker_s':float(surfaces.get('elapsed_s',0.0) or 0.0),'total_external_s':float(time.perf_counter()-t0)}
    metadata={'engine':'TotalSegmentator','version':str(req.get('totalseg_version') or ''),'task':'teeth','device':used,'cpu_threads':threads,'resample_workers':resamp_threads,'higher_order_resampling':True,'input_resampling_order':1,'gpu_fallback_error':gpu_error,'class_voxels':class_counts}
    manifest={'status':'OK','source_signature':signature,'universal_labels_path':teeth['corrected_labels_path'],'path_stats':teeth.get('path_stats') or {},'semantic_info':teeth.get('semantic_info') or {},'prepared_meshes':teeth.get('prepared_meshes') or {},'prepared_surfaces':surfaces.get('prepared_surfaces') or {},'semantic_metadata':metadata,'universal_metadata':metadata,'semantic_crop_info':{'engine':'TotalSegmentator','task':'teeth'},'universal_crop_info':{'engine':'TotalSegmentator','task':'teeth'},'roi_info':{'engine':'TotalSegmentator','crop_model':'craniofacial_structures'},'timings':timings,'cpu_worker_threads':each,'hybrid_gpu_cpu':True,'worker_failures_recovered':failures,'segmentation_engine':'TotalSegmentator','totalseg_task':'teeth'}
    atomic_json(manifest_path,manifest); status('ready','TotalSegmentator terminado · listo para importar en Blender',0.94,{'done':True}); heartbeat_stop.set()

if __name__=='__main__':
    try: main()
    except Exception as exc:
        try:
            req=json.loads(Path(sys.argv[-1]).read_text(encoding='utf-8')); job=Path(req['job_dir']); job.mkdir(parents=True,exist_ok=True)
            atomic_json(job/'manifest.json',{'status':'ERROR','error':f'{type(exc).__name__}: {exc}'})
            atomic_json(job/'status.json',{'status':'ERROR','phase':'error','message':f'{type(exc).__name__}: {exc}','factor':0.0,'time':time.time()})
        except Exception: _DSG_LOG.debug("suppressed exception", exc_info=True)
        raise
