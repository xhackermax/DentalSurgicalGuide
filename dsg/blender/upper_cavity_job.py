"""Background cavity recovery for saved cases and non-TotalSeg dental routes."""
import json,os,subprocess,tempfile
from pathlib import Path
import bpy

STATE={'process':None,'log':None,'scene':None,'input':'','dir':None,'message':''}

@bpy.app.handlers.persistent
def on_load(_unused):stop()

def source_signature():
    from .. import dicom_module as dicom
    return dicom._semantic_source_signature()

def input_path(scene):
    value=str(scene.get('DSG_upper_cavity_input_nifti',''))
    if value and Path(value).is_file():return value
    from .. import dicom_module as dicom
    folder=str(dicom.RUNTIME.pipeline_result_dir or '')
    path=Path(folder)/'input_cbct.nii.gz'
    return str(path) if folder and path.is_file() else ''

def stop():
    process=STATE['process']
    if process is not None and process.poll() is None:
        # Worker children may be resampling processes on Windows.
        if os.name=='nt':subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW)
        else:process.terminate()
    if STATE['log'] is not None:STATE['log'].close()
    STATE.update(process=None,log=None,scene=None,message='')

def start(context):
    if STATE['process'] is not None:raise RuntimeError('La identificación de cavidades ya está en curso.')
    source=input_path(context.scene)
    if not source:raise RuntimeError('Recarga y segmenta el CBCT: falta el volumen preparado de este caso.')
    from .. import segmentation_engines as engines
    from ..cbct_pipeline_client import _creationflags
    folder=Path(tempfile.mkdtemp(prefix='DSG_UPPER_'))
    addon=Path(__file__).resolve().parents[1]
    req={'addon_dir':str(addon),'job_dir':str(folder),'input_nifti':source,'device':'gpu',
         'engine_site_paths':engines.active_site_paths('TOTALSEG'),'engine_env':engines.environment_for_engine('TOTALSEG')}
    request=folder/'request.json';request.write_text(json.dumps(req),encoding='utf-8')
    log=(folder/'worker.log').open('w',encoding='utf-8')
    try:process=subprocess.Popen([engines._python_path(),str(addon/'cbct_upper_worker.py'),str(request)],stdout=log,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,env=os.environ.copy(),creationflags=_creationflags())
    except Exception:
        log.close();raise
    context.scene['DSG_upper_cavity_input_nifti']=source
    STATE.update(process=process,log=log,scene=context.scene,input=source,dir=folder,message='Identificando cavidades…',signature=source_signature())
    bpy.app.timers.register(poll,first_interval=.5)

def poll():
    process=STATE['process']
    if process is None:return None
    scene=STATE['scene']
    if bpy.context.scene!=scene or str(scene.get('DSG_upper_cavity_input_nifti',''))!=STATE['input'] or source_signature()!=STATE['signature']:
        stop();return None
    progress=STATE['dir']/'progress.json'
    if progress.is_file():
        try:STATE['message']=json.loads(progress.read_text('utf-8'))['message']
        except (ValueError,KeyError,OSError):pass
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type=='VIEW_3D':area.tag_redraw()
    if process.poll() is None:return .5
    result=STATE['dir']/'result.json'
    try:
        data=json.loads(result.read_text('utf-8'))
        if not data['ok']:raise RuntimeError(data['error'])
        from . import upper_cavity_safety as upper
        upper.import_surfaces(bpy.context,data['upper_cavities'])
        scene['DSG_upper_cavity_job_message']='Cavidades preparadas: revisa el CBCT y confirma.'
    except (ValueError,KeyError,OSError,RuntimeError) as exc:scene['DSG_upper_cavity_job_message']='Identificación no completada: '+str(exc)
    finally:stop()
    return None
