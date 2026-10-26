"""One local background Blender process for either immutable search snapshot."""
import sys,json,time
from pathlib import Path
def run(request):
    import numpy as np
    from dsg.implant_optimization import search_position,search_size,search_joint_sizes
    from dsg.blender.implant_optimizer_geometry import Solid,PlanarSlab,Evaluator,transformed
    last_progress=[0.]
    def progress(percent,text):
        if not request.get('job_dir'):return
        now=time.monotonic()
        if now-last_progress[0]<.2 and percent not in (0,100):return
        last_progress[0]=now;folder=Path(request['job_dir']);temp=folder/'progress.tmp'
        temp.write_text(json.dumps({'percent':float(percent),'text':text},ensure_ascii=False),'utf-8');temp.replace(folder/'progress.json')
    progress(0,'Preparando las superficies del caso')
    def mesh(item):
        return np.load(item['vertices_path'],allow_pickle=False),np.load(item['faces_path'],allow_pickle=False)
    bone_v,bone_f=mesh(request['bone'])
    bone=Solid(transformed(bone_v,request['bone']['matrix']),bone_f,'Hueso nativo')
    progress(15,'Preparando las estructuras protegidas')
    obstacles=[]
    for index,item in enumerate(request['obstacles']):
        progress(15+20*index/max(1,len(request['obstacles'])),'Preparando '+item['kind'])
        vertices,faces=mesh(item)
        if item.get('plane'):solid=PlanarSlab(transformed(vertices,item['matrix']),faces,item['name'],item['plane']['point'],item['plane']['normal'])
        else:solid=Solid(transformed(vertices,item['matrix']),faces,item['name'],allow_hull=item.get('allow_hull',False))
        obstacles.append((solid,float(item['margin_mm']),item['kind'],float(item.get('max_invasion_mm',0.))))
    source=mesh(request['implant'])
    pose=np.asarray(request['implant']['matrix'],float);platform=np.asarray(request['platform'],float)
    platform_local=(np.linalg.inv(pose)@np.r_[platform,1.])[:3]
    settings=request['settings']
    sockets=[]
    for item in request.get('sockets',[]):
        vertices,faces=mesh(item);sockets.append(Solid(transformed(vertices,item['matrix']),faces,item['name'],allow_hull=True))
    evaluator=Evaluator(source,bone,obstacles,settings,asset_loader=mesh,source_platform_local=platform_local,sockets=sockets,source_nominal_length_mm=request.get('source_nominal_length_mm',(request.get('current') or {}).get('length_mm')))
    section_field=[None]
    def measured(result):
        from dsg.bone_interpretation import interpret_search_result
        interpret_search_result(result,immediate=bool(sockets),minimum_coverage=settings.get('min_coverage',.8))
        progress(95,'Midiendo hueso, huecos y espesor de pared')
        result['original_support']=evaluator.measure_bone(pose)
        if section_field[0] is not None and request.get('current'):
            current=request['current']
            if current.get('diameter_mm') and current.get('length_mm'):
                result['original_section_metrics']=section_field[0].assess_matrix(pose,dict(current,platform_local_mm=platform_local.tolist()))
        shown=result.get('best') or result.get('conditional') or result.get('closest')
        if shown:shown['evaluation']['surround']=evaluator.measure_bone(shown['matrix'],shown.get('asset'))['surround']
        progress(100,'Resultado preparado para revisar')
        if settings.get('section_fallback_reason'):result['section_fallback_reason']=settings['section_fallback_reason']
        return result
    if request['mode']=='POSITION':
        progress(40,'Buscando posición sin cambiar los límites configurados')
        return measured(search_position(evaluator,pose,platform,max_shift_mm=settings['max_shift_mm'],max_tilt_deg=settings['max_tilt_deg'],
            max_depth_mm=settings.get('max_depth_mm',0.),budget=settings.get('budget',90),min_gain=settings.get('min_gain',.03)))
    if request['mode']=='SIZE':
        if settings.get('section_search') and settings.get('combine_size_position') and request.get('catalogue'):
            try:
                from dsg.section_optimizer import SectionField,search_sections
                from dsg.implant_search_frames import search_frames,frame_request
                progress(25,'Calculando el espacio local por cortes')
                frames=search_frames(request)
                field=SectionField(frame_request(request,frames[0]),bone,obstacles,sockets,progress=progress)
                section_field[0]=field
                if request.get('section_debug_export'):field.export(Path(request['job_dir'])/'section_map.npz')
                progress(45,'Comparando medidas en el mapa de cortes')
                alternatives=[]
                for frame in frames[1:]:
                    try:alternatives.append(SectionField(frame_request(request,frame),bone,obstacles,sockets,progress=progress))
                    except ValueError:continue
                return measured(search_sections(request,field,evaluator,progress,additional_fields=alternatives))
            except (ImportError,ValueError) as exc:
                # Never silently change the placement reference/objective.
                return {'mode':'SIZE','status':'REFERENCE_UNVERIFIABLE','best':None,
                        'evaluated':0,'reasons':[str(exc)],'reference_error':str(exc)}
        progress(40,'Comparando medidas y comprobando hueso y estructuras')
        search=search_joint_sizes if settings.get('combine_size_position') else search_size
        extra={'max_shift_mm':settings['max_shift_mm'],'max_depth_mm':settings.get('max_depth_mm',0.),
               'progress':lambda index,total,asset:progress(40+50*index/max(1,total),f"Ø {asset['diameter_mm']:g} × {asset['length_mm']:g} mm · posición {index}/{total}")} if settings.get('combine_size_position') else {}
        result=search(evaluator,request.get('catalogue',[]),request.get('family',''),pose,platform,current_id=request.get('current_id'),
            current=request.get('current'),policy=settings.get('size_policy','LARGEST'),
            max_diameter_mm=settings.get('max_diameter_mm',0.),max_length_mm=settings.get('max_length_mm',0.),**extra)
        if result.get('best') and result['best']['asset'].get('dimension_only') and result['status'] in {'PROPOSAL','COMPARISON'}:
            result['status']='NOMINAL_PROPOSAL'
        return measured(result)
    if request['mode']=='VALIDATE':
        row=request['candidate']
        # A nominal size is validated with its circumscribed envelope; the DSG
        # implant of that size is checked to fit inside it before it is applied.
        if row.get('evaluation',{}).get('metric')=='SECTION_ENVELOPE_AND_NATIVE_SUPPORT_NOT_STABILITY':
            from dsg.section_optimizer import SectionField,exact_section_evaluation
            from dsg.implant_search_frames import validate_candidate_reference,frame_request
            frame=validate_candidate_reference(request,row)
            field=SectionField(frame_request(request,frame),bone,obstacles,sockets,progress=progress)
            evaluation=exact_section_evaluation(field,evaluator,np.asarray(row['matrix'],float),row['asset'])
        else:evaluation=evaluator(np.asarray(row['matrix'],float),asset=row.get('asset'))
        return {'status':'VALIDATED' if evaluation['admissible'] else 'REJECTED','evaluation':evaluation}
    raise ValueError('Modo desconocido.')

def main():
    request_path=Path(sys.argv[-1]);request=json.loads(request_path.read_text('utf-8'))
    sys.path.insert(0,str(Path(request['addon_dir']).parent))
    out=Path(request['job_dir']);started=time.perf_counter()
    try:result={'ok':True,'result':run(request),'elapsed_s':time.perf_counter()-started,'run_id':request['run_id']}
    except Exception as exc:result={'ok':False,'error':str(exc),'run_id':request['run_id']}
    temporary=out/'result.tmp';temporary.write_text(json.dumps(result,ensure_ascii=False),'utf-8');temporary.replace(out/'result.json')
    print('DSG_OPTIMIZER_DONE',json.dumps({k:v for k,v in result.items() if k!='result'},ensure_ascii=False),flush=True)

if __name__=='__main__':main()
