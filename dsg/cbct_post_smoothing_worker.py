"""On-demand, process-isolated tooth finishing. This script never imports bpy."""
from pathlib import Path
import json,os,sys,time,types,traceback

def atomic_json(path,payload):
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(payload,ensure_ascii=False),encoding='utf-8')
    # Windows cannot replace a file during the UI's brief read handle.
    for attempt in range(40):
        try:os.replace(temp,path);return
        except PermissionError:
            if attempt==39:raise
            time.sleep(.025)

def run(request):
    for p in reversed(request.get('site_paths',[])):
        if p:sys.path.insert(0,p)
    addon=Path(__file__).resolve().parent
    if 'dsg' not in sys.modules:
        pkg=types.ModuleType('dsg');pkg.__path__=[str(addon)];pkg.__package__='dsg';sys.modules['dsg']=pkg
    from dsg import surface_nets_geometry as g
    from dsg.cbct_surface_meshing import _configure_vtk_smp
    _configure_vtk_smp(g.vtk)
    np=g.np;root=Path(request['job_dir']);started=time.perf_counter()
    def status(text):atomic_json(root/'status.json',{'message':text})
    if request.get('mode')=='VISUAL':
        from dsg.surface_smoothing import smooth_surface_preserving_volume
        rows=[]
        for target in request['targets']:
            k=int(target['label']);status(f"Suavizando diente {target['fdi']}…")
            row={'label':k,'fdi':int(target['fdi']),'status':'SKIPPED','method':'WINDOWED_SINC_VOLUME_CAGED_2','fallback_reason':''};rows.append(row)
            try:
                v=np.load(target['source_vertices_path'],allow_pickle=False);f=np.load(target['source_faces_path'],allow_pickle=False)
                limit=min(.25,1.25*min(target['spacing_zyx_mm']))
                q,stats=smooth_surface_preserving_volume(v,f,max_distance_mm=limit,vtk_module=g.vtk)
                vp=root/f'v_{k}.npy';fp=root/f'f_{k}.npy';np.save(vp,q);np.save(fp,f)
                row.update(stats,status='READY',vertices_path=str(vp),faces_path=str(fp),raw_vertex_count=len(v),final_vertex_count=len(q))
            except Exception as exc:row['fallback_reason']=str(exc)[:240]
        atomic_json(root/'result.json',{'status':'OK','mode':'VISUAL','teeth':rows,'elapsed_s':time.perf_counter()-started,
                    'mask_modified':False,'segmentation_consistency_checked':False,'anatomical_accuracy_validated':False})
        status('Suavizado terminado');return
    status('Localizando dientes segmentados…')
    labels=np.load(request['labels_path'],mmap_mode='r');spacing=np.asarray(request['spacing_zyx_mm'],dtype=float)
    boxes=g.ndimage.find_objects(labels,max_label=int(labels.max()))
    requested=[int(t['label']) for t in request['targets']]
    selected=[boxes[k-1] for k in requested if 0<k<=len(boxes) and boxes[k-1] is not None]
    if not selected:raise RuntimeError('No hay labels dentales en esta segmentación')
    lo=np.maximum([min(b[i].start for b in selected)-3 for i in range(3)],0)
    hi=np.minimum([max(b[i].stop for b in selected)+3 for i in range(3)],labels.shape)
    a=np.pad(np.asarray(labels[tuple(slice(int(l),int(h)) for l,h in zip(lo,hi))]),1);origin=lo-1
    all_labels=np.unique(a);all_labels=all_labels[all_labels!=0]
    # No cavity filling: all gates refer to the actual immutable segmentation.
    status('Extrayendo todas las interfaces compartidas…')
    raw=g.surface_nets(a,all_labels,iterations=0)
    final=g.surface_nets(a,all_labels,half=.45,relax=.2,iterations=16)
    parts,route=g.split_atlas(final,requested)
    boundary=g.vtk_to_numpy(final.GetCellData().GetArray('BoundaryLabels'))
    unresolved_array=final.GetPointData().GetArray('NonManifoldTableIndices')
    unresolved=int(np.count_nonzero(g.vtk_to_numpy(unresolved_array)==-1)) if unresolved_array is not None else None
    rows=[];candidate={};a_boxes=g.ndimage.find_objects(a,max_label=int(a.max()));cross=g.ndimage.generate_binary_structure(3,1)
    for target in request['targets']:
        k=int(target['label']);fdi=int(target['fdi']);status(f'Comprobando diente {fdi}…')
        t=time.perf_counter();row={'label':k,'fdi':fdi,'status':'SKIPPED','method':'SURFACE_NETS_BOX','preset':'CLEAN',
             'constraint_box_half_width_voxels':.45,'constraint_box_full_width_argument':.9,'iterations':16,'relaxation_factor':.2,
             'vtk_version':g.vtk.vtkVersion.GetVTKVersion(),'split_route':route,'non_manifold_unresolved_points_in_batch':unresolved,
             'mask_modified':False,'fallback_reason':''}
        rows.append(row)
        try:
            if k not in parts:raise ValueError('Label no disponible')
            pd=parts[k];v,f=g.arrays(pd);manual,ids=g.split_manual(final,k);vm,fm=g.arrays(manual)
            raw_manual,raw_ids=g.split_manual(raw,k);vrm,frm=g.arrays(raw_manual)
            if not np.array_equal(ids,raw_ids):raise ValueError('Cambió la correspondencia de la superficie')
            distance,index=g.cKDTree(vm).query(v)
            if distance.max()>1e-7:raise ValueError('Atlas cambió las posiciones compartidas')
            v0=vrm[index];raw_pd=g.poly(v0,f)
            topo=g.topology(v,f);raw_topo=g.topology(v0,f);_,areas,_=g.geometry(v,f)
            row.update(topo,raw_vertex_count=int(target['vertex_count']),final_vertex_count=len(v))
            if not topo['closed']:raise ValueError(f"Malla abierta/no manifold: {topo['bad_edges']} aristas")
            if topo['components']>raw_topo['components']:raise ValueError('Aumentó el número de componentes')
            if np.any(areas<1e-10):raise ValueError('Caras colapsadas')
            if len(v)>1.1*int(target['vertex_count']):raise ValueError('Supera el límite de vértices (+10%)')
            displacement=(v-v0)*spacing[::-1];max_axis=np.max(abs(v-v0),axis=0)
            if max_axis.max()>.45003:raise ValueError('Supera la caja de movimiento')
            row.update(mean_displacement_mm=float(np.linalg.norm(displacement,axis=1).mean()),
                       p95_displacement_mm=float(np.percentile(np.linalg.norm(displacement,axis=1),95)),
                       max_displacement_mm=float(np.linalg.norm(displacement,axis=1).max()),max_axis_displacement_voxels=max_axis.tolist())
            # Crop the classification samples per label, retaining its six exterior neighbors.
            box=a_boxes[k-1];bl=np.maximum([b.start-1 for b in box],0);bh=np.minimum([b.stop+1 for b in box],a.shape)
            mask=a[tuple(slice(int(l),int(h)) for l,h in zip(bl,bh))]==k
            pts,expected=g.boundary_samples(mask);pts+=bl[::-1]
            voxel_count=int(mask.sum());boundary_count=int(np.count_nonzero(mask&~g.ndimage.binary_erosion(mask,structure=cross)))
            reference=float(voxel_count*np.prod(spacing));uncertainty=float(boundary_count*np.prod(spacing)*.5)
            vol=g.volume(v*spacing[::-1],f);raw_vol=g.volume(v0*spacing[::-1],f)
            if vol<=0 or raw_vol<=0:raise ValueError('Orientación de caras incorrecta')
            error=100*(vol/reference-1);delta=abs(vol-reference)
            row.update(voxel_count_volume_mm3=reference,segmentation_reference_volume_mm3=reference,voxel_count=voxel_count,
                       volume_uncertainty_band_mm3=uncertainty,final_volume_mm3=vol,raw_volume_mm3=raw_vol,
                       delta_vs_voxel_count_percent=error,delta_vs_raw_mesh_percent=100*(vol/raw_vol-1),
                       volume_warning=abs(error)>1 or delta>.25*uncertainty)
            if abs(error)>2 or delta>.5*uncertainty:raise ValueError('Cambio de volumen fuera del control permitido')
            occupancy=g.consistency(pd,pts,expected);row.update(occupancy)
            if occupancy['occupancy_consistency']<.995:raise ValueError('Consistencia de segmentación inferior al 99,5%')
            radius=2*float(max(spacing));rough0=g.roughness_radius(v0*spacing[::-1],f,radius);rough=g.roughness_radius(v*spacing[::-1],f,radius)
            reduction=100*(1-rough/max(rough0,1e-20));row.update(roughness_raw=rough0,roughness_final=rough,roughness_reduction_percent=reduction,
                          roughness_target_reached=reduction>=60)
            if reduction<5:raise ValueError('El filtro no mejora suficientemente la superficie')
            row['hausdorff_vertex_sampled_mm']=g.sampled_distance(g.poly(v*spacing[::-1],f),g.poly(v0*spacing[::-1],f))
            # Spacing/orientation applied after voxel-space smoothing. Root supplies patient affine.
            global_zyx=v[:,::-1]+origin;dims=np.asarray(request['dims_zyx']);signs=np.asarray(request['display_signs_xyz'])
            xyz=((global_zyx-.5*(dims-1))*spacing)[:,::-1]*signs
            if np.prod(signs)<0:f=f[:,::-1]
            candidate[k]=(xyz.astype(np.float32),f.astype(np.int32));row['status']='READY'
        except Exception as exc:row['fallback_reason']=str(exc)[:240]
        row['elapsed_s']=time.perf_counter()-t
    # A partial update must not split a shared tooth contact: reject its entire contact group.
    adj={k:set() for k in requested}
    for left,right in np.unique(boundary,axis=0):
        left,right=int(left),int(right)
        if 0<left<=32 and 0<right<=32:
            if left in adj:adj[left].add(right)
            if right in adj:adj[right].add(left)
    bad={k for k in requested if k not in candidate}
    bad.update(k for k,neighbors in adj.items() if any(n not in requested for n in neighbors))
    while True:
        grown=bad|{k for k,neighbors in adj.items() if neighbors&bad}
        if grown==bad:break
        bad=grown
    for row in rows:
        k=row['label']
        if k in bad and row['status']=='READY':row.update(status='SKIPPED',fallback_reason='Contacto compartido con un diente que no pasó los controles')
        if row['status']=='READY':
            v,f=candidate[k];vp=root/f'v_{k}.npy';fp=root/f'f_{k}.npy';np.save(vp,v);np.save(fp,f)
            row.update(vertices_path=str(vp),faces_path=str(fp))
    result={'status':'OK','mode':'CLEAN','method':'SURFACE_NETS_BOX','teeth':rows,'all_labels':all_labels.tolist(),
            'elapsed_s':time.perf_counter()-started,'mask_modified':False,'shared_contacts_preserved_by_group_policy':True,
            'self_intersections_checked':False,'anatomical_intensity_refinement':False}
    atomic_json(root/'result.json',result);status('Suavizado terminado')

if __name__=='__main__':
    request=json.loads(Path(sys.argv[-1]).read_text(encoding='utf-8'));root=Path(request['job_dir'])
    try:run(request)
    except Exception as exc:
        atomic_json(root/'result.json',{'status':'ERROR','error':str(exc)[:400]});traceback.print_exc();sys.exit(1)
