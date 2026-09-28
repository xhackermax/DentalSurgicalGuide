"""DSG 9.3 process-only CBCT postprocessing tasks.

This module is deliberately bpy-free. It is imported by direct Python worker
processes, never by Blender's UI thread for heavy computation.
"""
from __future__ import annotations

import math
import time
from pathlib import Path
from typing import Callable

import numpy as np

from . import tooth_analysis
from . import cbct_surface_meshing

StatusCB = Callable[[str], None]


def _json_safe(value):
    if value is None or isinstance(value,(str,int,float,bool)):
        return value
    if isinstance(value, Path): return str(value)
    if isinstance(value, dict): return {str(k):_json_safe(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)): return [_json_safe(v) for v in value]
    if isinstance(value,np.ndarray): return value.tolist()
    if isinstance(value,np.generic): return value.item()
    return str(value)


def _load_vtk():
    try:
        import vtk
        return vtk
    except Exception:
        return None


def _load_measure():
    try:
        from skimage import measure
        return measure
    except Exception:
        return None


def compact_mask_for_classes(labels, classes):
    classes=tuple(sorted({int(v) for v in classes}))
    if not classes: return None,(0,0,0)
    arr=np.asarray(labels)
    selected=[]
    try:
        from scipy import ndimage
        boxes=ndimage.find_objects(arr,max_label=max(classes))
        selected=[boxes[v-1] for v in classes if 0<v<=len(boxes) and boxes[v-1] is not None]
    except Exception:
        selected=[]
    if not selected:
        coords=np.argwhere(np.isin(arr,np.asarray(classes,dtype=arr.dtype)))
        if coords.size==0: return None,(0,0,0)
        starts=tuple(int(v) for v in coords.min(axis=0)); stops=tuple(int(v)+1 for v in coords.max(axis=0))
    else:
        starts=tuple(min(int(b[a].start) for b in selected) for a in range(3))
        stops=tuple(max(int(b[a].stop) for b in selected) for a in range(3))
    roi=arr[starts[0]:stops[0],starts[1]:stops[1],starts[2]:stops[2]]
    mask=np.isin(roi,np.asarray(classes,dtype=arr.dtype))
    return np.ascontiguousarray(mask,dtype=np.bool_),starts




def _ellipsoid(radius_mm, spacing):
    """Binary morphology kernel in physical millimetres (Z,Y,X spacing)."""
    sz,sy,sx=(float(v) for v in spacing)
    rz=max(1,int(math.ceil(radius_mm/max(sz,1e-6))))
    ry=max(1,int(math.ceil(radius_mm/max(sy,1e-6))))
    rx=max(1,int(math.ceil(radius_mm/max(sx,1e-6))))
    zz,yy,xx=np.ogrid[-rz:rz+1,-ry:ry+1,-rx:rx+1]
    return np.asarray((zz*sz)**2+(yy*sy)**2+(xx*sx)**2 <= float(radius_mm)**2,dtype=np.bool_)


def refine_single_source_canal(mask, origin, spacing):
    """Preserve the historical 0.65 mm canal closing without fake verification.

    DSG 9.5.7 called this path a fusion between a universal mask and a verifier
    mask, but both masks came from the same TotalSegmentator task=teeth output.
    With identical inputs, the only geometry-changing step was a 0.65 mm binary
    closing followed by OR with the original mask.  Keep exactly that useful
    operation and report the real single-source provenance.
    """
    if mask is None:
        return None, tuple(int(v) for v in origin), {
            'source':'NONE','independent_verifier':False,'input_voxels':0,
            'final_voxels':0,'closing_radius_mm':0.65,
        }
    source=np.ascontiguousarray(mask,dtype=np.bool_)
    before=int(source.sum())
    refined=source
    try:
        from scipy import ndimage
        refined=ndimage.binary_closing(
            source,structure=_ellipsoid(0.65,spacing),iterations=1,border_value=0
        )
        refined |= source
    except Exception:
        refined=source
    final=int(refined.sum())
    return np.ascontiguousarray(refined,dtype=np.bool_),tuple(int(v) for v in origin),{
        'source':'TOTALSEGMENTATOR_SINGLE_SOURCE',
        'independent_verifier':False,
        'input_voxels':before,
        'final_voxels':final,
        'closing_radius_mm':0.65,
    }

def global_voxel_to_xyz(vertices_zyx,dims_zyx,spacing_zyx):
    v=np.asarray(vertices_zyx,dtype=np.float64)
    fz,fy,fx=(int(x) for x in dims_zyx); sz,sy,sx=(float(x) for x in spacing_zyx)
    out=np.empty((v.shape[0],3),dtype=np.float32)
    out[:,0]=(v[:,2]-0.5*float(fx-1))*sx
    out[:,1]=(v[:,1]-0.5*float(fy-1))*sy
    out[:,2]=(v[:,0]-0.5*float(fz-1))*sz
    return out


def _present_teeth(labels):
    vals=np.unique(np.asarray(labels))
    return [int(v) for v in vals if 1<=int(v)<=52 and tooth_analysis.universal_to_fdi(int(v),source='CBCT')]


def _bbox_slices(labels,max_label=55):
    from scipy import ndimage
    return ndimage.find_objects(labels,max_label=max_label)


def _dentition_bounds(shape,boxes,present,margin=2):
    valid=[]
    for label in present:
        idx=int(label)-1
        if 0<=idx<len(boxes) and boxes[idx] is not None: valid.append(boxes[idx])
    if not valid: return None
    z0=min(int(b[0].start) for b in valid); z1=max(int(b[0].stop) for b in valid)
    y0=min(int(b[1].start) for b in valid); y1=max(int(b[1].stop) for b in valid)
    x0=min(int(b[2].start) for b in valid); x1=max(int(b[2].stop) for b in valid)
    m=max(1,int(margin))
    return max(0,z0-m),min(int(shape[0]),z1+m),max(0,y0-m),min(int(shape[1]),y1+m),max(0,x0-m),min(int(shape[2]),x1+m)


def prepare_tooth_meshes(labels,spacing_zyx,dims_zyx,out_dir:Path,status_cb:StatusCB|None=None):
    started=time.perf_counter(); present=_present_teeth(labels); boxes=_bbox_slices(labels,55)
    if not present: raise RuntimeError('TotalSegmentator task=teeth no devolvió dientes individualizados')
    bounds=_dentition_bounds(labels.shape,boxes,present,2)
    if bounds is None: raise RuntimeError('No se pudo localizar la dentición TotalSegmentator')
    z0,z1,y0,y1,x0,x1=bounds
    crop=np.ascontiguousarray(labels[z0:z1,y0:y1,x0:x1])
    vtk=_load_vtk(); measure=_load_measure()
    if vtk is None and measure is None: raise RuntimeError('Falta VTK/scikit-image en el worker de superficies')
    if status_cb: status_cb('VTK multietiqueta · extrayendo todos los dientes en una pasada…')
    batch=cbct_surface_meshing.extract_multilabel_surface(crop,present,crop_origin_zyx=(z0,y0,x0),vtk_module=vtk,skimage_measure=measure,spacing_zyx=spacing_zyx)
    counts=np.bincount(crop.reshape(-1).astype(np.int64,copy=False),minlength=56)
    geom_dir=out_dir/'teeth_meshes'; geom_dir.mkdir(parents=True,exist_ok=True)
    items=[]; per=float(batch.elapsed_s)/max(1,len(batch.items))
    for idx,label in enumerate(present,1):
        surface=batch.items.get(int(label))
        if surface is None: continue
        fdi=tooth_analysis.universal_to_fdi(label,source='CBCT')
        if not fdi: continue
        xyz=global_voxel_to_xyz(surface.vertices_zyx,dims_zyx,spacing_zyx)
        faces=np.ascontiguousarray(surface.faces,dtype=np.int32)
        if len(faces)<4: continue
        xyz_path=geom_dir/f'{int(label):02d}_xyz.npy'; faces_path=geom_dir/f'{int(label):02d}_faces.npy'
        np.save(str(xyz_path),np.ascontiguousarray(xyz,dtype=np.float32),allow_pickle=False)
        np.save(str(faces_path),faces,allow_pickle=False)
        centroid=tuple(float(v) for v in np.asarray(xyz).mean(axis=0,dtype=np.float64))
        try: axis_info=tooth_analysis.pca_axis_from_xyz(np,xyz)
        except Exception: axis_info=None
        items.append({
            'label':int(label),'fdi':int(fdi),'xyz_path':str(xyz_path),'faces_path':str(faces_path),
            'voxel_count':int(counts[int(label)]) if int(label)<len(counts) else 0,
            'topology':dict(surface.topology or {}),'centroid':centroid,'refine_stats':{'status':'SKIPPED_NATIVE_SOURCE'},
            'axis_info':_json_safe(axis_info),'mesh_step_size':1,'mesh_step_requested':1,'full_resolution':True,
            'surface_mesher':str(batch.engine),'surface_extract_s':float(per),'surface_batch_extract_s':float(batch.elapsed_s),
            'surface_mesher_fallback':str(batch.fallback_reason or ''),'surface_mesher_diagnostics':_json_safe(batch.diagnostics or {}),
            'roi_origin_zyx':(int(z0),int(y0),int(x0)),'roi_shape_zyx':tuple(int(v) for v in crop.shape),
            'roi_voxels':int(crop.size),'roi_margin_voxels':2,'component_cleanup_stage':'POST_SURFACE',
            'single_multilabel_pass':bool((batch.diagnostics or {}).get('single_pass',False)),
        })
        if status_cb: status_cb(f'Dientes preparados {idx}/{len(present)} · FDI {int(fdi)}')
    diag=dict(batch.diagnostics or {}); smp=dict(diag.get('vtk_smp') or {})
    naive=int(labels.size)*max(1,len(items)); roi_fraction=float(crop.size)/float(naive) if naive else 0.0
    return {
        'items':items,'prepare_s':float(time.perf_counter()-started),'surface_extract_s':float(batch.elapsed_s),
        'candidate_count':len(present),'prepared_count':len(items),'engine_counts':{str(batch.engine):len(items)} if items else {},
        'vtk_available':vtk is not None,'mesher_fallback_count':int(bool(batch.fallback_reason)),
        'native_preview_count':len(items),'native_fullres_count':len(items),'roi_total_voxels':int(crop.size),
        'roi_vs_naive_fraction':roi_fraction,'bbox_cache':True,'roi_worker_count':1,
        'vtk_smp_backends':[str(smp.get('backend_after') or smp.get('backend_before') or '')],
        'vtk_smp_threads':int(smp.get('threads',0) or 0),'single_pass':bool(diag.get('single_pass',False)),
        'per_tooth_binary_masks':not bool(diag.get('single_pass',False)),'component_cleanup_stage':'POST_SURFACE','native_resolution':True,
    }


def _save_binary_surface(mask,origin,spacing,dims,out_dir,name,label):
    if mask is None or not bool(np.asarray(mask).any()): return None
    vtk=_load_vtk(); measure=_load_measure()
    extraction=cbct_surface_meshing.extract_binary_surface(np.ascontiguousarray(mask,dtype=np.uint8),step_size=1,preferred_engine='AUTO',vtk_module=vtk,skimage_measure=measure)
    vz=np.asarray(extraction.vertices_zyx,dtype=np.float64); vz += np.asarray(tuple(int(v) for v in origin),dtype=np.float64)[None,:]
    xyz=global_voxel_to_xyz(vz,dims,spacing); faces=np.ascontiguousarray(extraction.faces,dtype=np.int32)
    geom=out_dir/'surface_meshes'; geom.mkdir(parents=True,exist_ok=True)
    xp=geom/f'{name}_xyz.npy'; fp=geom/f'{name}_faces.npy'
    np.save(str(xp),np.ascontiguousarray(xyz,dtype=np.float32),allow_pickle=False); np.save(str(fp),faces,allow_pickle=False)
    return {'vertices_path':str(xp),'faces_path':str(fp),'stride':1,'origin':tuple(int(v) for v in origin),'kind':'JAW','label':int(label) if label is not None else None,'refine_stats':{'status':'SKIPPED_NATIVE_SOURCE'},'mask_voxels':int(np.asarray(mask).sum()),'surface_mesher':str(extraction.engine),'surface_extract_s':float(extraction.elapsed_s),'native_resolution':True}


UPPER_SIMPLE_CLASSES = tuple(range(1, 17)) + (54,)
LOWER_SIMPLE_CLASSES = tuple(range(17, 33)) + (53,)


def simple_arch_masks(labels):
    """Return exactly two binary crops for the SIMPLE implant route.

    The TotalSegmentator compatibility map encodes permanent FDI internally,
    but SIMPLE deliberately discards that identity at the geometry boundary:
    upper jawbone + every upper tooth become one mask; lower jawbone + every
    lower tooth become the second. Pulp and mandibular canal are excluded.
    """
    upper, upper_origin = compact_mask_for_classes(labels, UPPER_SIMPLE_CLASSES)
    lower, lower_origin = compact_mask_for_classes(labels, LOWER_SIMPLE_CLASSES)
    return upper, upper_origin, lower, lower_origin


def prepare_simple_arches_route_map(route_labels, spacing_zyx, dims_zyx, out_dir: Path, status_cb: StatusCB | None = None):
    """Create SIMPLE surfaces from a minimal 1=upper / 2=lower route map."""
    started = time.perf_counter()
    if status_cb:
        status_cb('Ruta simple · preparando arcada superior…')
    upper_mask, upper_origin = compact_mask_for_classes(route_labels, (1,))
    lower_mask, lower_origin = compact_mask_for_classes(route_labels, (2,))
    upper = _save_binary_surface(upper_mask, upper_origin, spacing_zyx, dims_zyx, out_dir, 'simple_upper', None)
    if status_cb:
        status_cb('Ruta simple · preparando arcada inferior…')
    lower = _save_binary_surface(lower_mask, lower_origin, spacing_zyx, dims_zyx, out_dir, 'simple_lower', None)
    if upper is None or lower is None:
        missing = []
        if upper is None: missing.append('superior')
        if lower is None: missing.append('inferior')
        raise RuntimeError('TotalSegmentator no devolvió la arcada ' + ' y '.join(missing))
    return {
        'upper_arch': upper,
        'lower_arch': lower,
        'simple_route': True,
        'identity_contract': 'UPPER_LOWER_ONLY',
        'contains_individual_fdi_meshes': False,
        'contains_canal_mesh': False,
        'surface_prepare_s': float(time.perf_counter() - started),
    }


def prepare_simple_arches(labels, spacing_zyx, dims_zyx, out_dir: Path, status_cb: StatusCB | None = None):
    """Create only two native-resolution surfaces; no FDI meshes and no canal."""
    started = time.perf_counter()
    if status_cb:
        status_cb('Ruta simple · preparando arcada superior…')
    upper_mask, upper_origin, lower_mask, lower_origin = simple_arch_masks(labels)
    upper = _save_binary_surface(upper_mask, upper_origin, spacing_zyx, dims_zyx, out_dir, 'simple_upper', None)
    if status_cb:
        status_cb('Ruta simple · preparando arcada inferior…')
    lower = _save_binary_surface(lower_mask, lower_origin, spacing_zyx, dims_zyx, out_dir, 'simple_lower', None)
    if upper is None or lower is None:
        missing = []
        if upper is None: missing.append('superior')
        if lower is None: missing.append('inferior')
        raise RuntimeError('TotalSegmentator no devolvió la arcada ' + ' y '.join(missing))
    return {
        'upper_arch': upper,
        'lower_arch': lower,
        'simple_route': True,
        'contains_individual_fdi_meshes': False,
        'contains_canal_mesh': False,
        'surface_prepare_s': float(time.perf_counter() - started),
    }


def run_teeth_task(req,status_cb:StatusCB|None=None):
    """Prepare meshes from the TotalSegmentator compatibility labelmap.

    TotalSegmentator already supplies permanent FDI identity. DSG therefore does
    not run the legacy arch/laterality relabeller or cross-model Tooth Path
    reconciliation here. The compatibility labels only adapt FDI to DSG's
    historical integer contract so the proven Blender mesh importer can stay
    unchanged.
    """
    started=time.perf_counter(); spacing=tuple(float(v) for v in req['spacing_zyx']); dims=tuple(int(v) for v in req['dims_zyx']); out=Path(req['output_dir']); out.mkdir(parents=True,exist_ok=True)
    # v9.5.x does not relabel/correct the TotalSegmentator FDI map here.
    # Use the memory-mapped SSOT directly instead of writing a byte-for-byte
    # duplicate full-volume `corrected` labelmap to the teeth worker folder.
    corrected_path=Path(req['universal_labels_path']).resolve()
    corrected=np.load(str(corrected_path),mmap_mode='r')
    if status_cb: status_cb('TotalSegmentator · preparando dientes FDI a resolución CBCT…')
    present=_present_teeth(corrected)
    semantic_info={'engine':'TotalSegmentator','task':'teeth','identity_authority':'FDI_FROM_MODEL','present_labels':present,'corrected':False}
    path_stats={'engine':'TotalSegmentator','task':'teeth','corrected':False,'reason':'FDI identity supplied directly by TotalSegmentator','present_tooth_count':len(present)}
    mesh=prepare_tooth_meshes(corrected,spacing,dims,out,status_cb)
    return {'task':'teeth','corrected_labels_path':str(corrected_path),'semantic_info':_json_safe(semantic_info),'path_stats':_json_safe(path_stats),'prepared_meshes':_json_safe(mesh),'elapsed_s':float(time.perf_counter()-started),'path_s':0.0}

def run_surfaces_task(req,status_cb:StatusCB|None=None):
    started=time.perf_counter(); spacing=tuple(float(v) for v in req['spacing_zyx']); dims=tuple(int(v) for v in req['dims_zyx']); out=Path(req['output_dir']); out.mkdir(parents=True,exist_ok=True)
    labels=np.load(req['universal_labels_path'],mmap_mode='r')
    if status_cb: status_cb('Superficies · localizando maxila y mandíbula…')
    max_mask,max_o=compact_mask_for_classes(labels,(54,))
    man_mask,man_o=compact_mask_for_classes(labels,(53,))
    maxilla=_save_binary_surface(max_mask,max_o,spacing,dims,out,'maxilla',54)
    if status_cb: status_cb('Superficies · mandíbula…')
    mandible=_save_binary_surface(man_mask,man_o,spacing,dims,out,'mandible',53)
    if status_cb: status_cb('Superficies · canal mandibular…')
    canal_mask,canal_o=compact_mask_for_classes(labels,(55,))
    refined_canal,refined_o,fusion=refine_single_source_canal(canal_mask,canal_o,spacing)
    canal={'status':'NOT_FOUND','faces':0,'voxels':0,'fusion':fusion}
    if refined_canal is not None and bool(refined_canal.any()):
        surf=_save_binary_surface(refined_canal,refined_o,spacing,dims,out,'canal',55)
        if surf is not None:
            canal={'status':'SEGMENTED','vertices_path':surf['vertices_path'],'faces_array_path':surf['faces_path'],'faces':int(np.load(surf['faces_path'],mmap_mode='r').shape[0]),'voxels':int(refined_canal.sum()),'origin':tuple(int(v) for v in refined_o),'fusion':fusion,'verifier':{'independent':False,'reason':'single TotalSegmentator task=teeth source'}}
    return {'task':'surfaces','prepared_surfaces':{'maxilla':maxilla,'mandible':mandible,'canal':canal,'maxilla_class':54,'maxilla_source':'TOTALSEGMENTATOR','mandible_class':53,'mandible_source':'TOTALSEGMENTATOR','surface_prepare_s':float(time.perf_counter()-started)},'elapsed_s':float(time.perf_counter()-started)}


def run_task(req,status_cb=None):
    task=str(req.get('task') or '').lower()
    if task=='teeth': return run_teeth_task(req,status_cb)
    if task=='surfaces': return run_surfaces_task(req,status_cb)
    raise RuntimeError(f'Tarea worker desconocida: {task}')
