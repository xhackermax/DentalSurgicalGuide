"""Measured, reversible CBCT surface finishing with the source topology intact.

Uses the Windowed Sinc filter also used by 3D Slicer's closed-surface converter.
Adds two guards absent from ordinary display modifiers: a physical displacement
limit and per-connected-component volume compensation. No remeshing, hole filling,
decimation, learned anatomy or changes to the segmentation labelmap occur here.
"""
from __future__ import annotations

import time

ALGORITHM_VERSION = 'WINDOWED_SINC_VOLUME_CAGED_2'
VOLUME_RELATIVE_TOLERANCE = 1e-6


def _signed_volume(np, vertices, faces):
    centred = vertices - vertices.mean(axis=0)
    tri = centred[faces]
    return float(np.einsum('ij,ij->i',tri[:,0],np.cross(tri[:,1],tri[:,2])).sum()/6.0)


def _cap(np, delta, limit):
    length = np.linalg.norm(delta,axis=1)
    return delta * np.minimum(1.0,limit/np.maximum(length,1e-20))[:,None]


def _compensate_volume(np, source, faces, proposal, limit):
    signed_source_volume = _signed_volume(np,source,faces)
    source_volume = abs(signed_source_volume)
    if source_volume <= 1e-12:
        raise ValueError('La componente no tiene un volumen cerrado medible')
    tri = source[faces]
    face_normals = np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0])
    normals = np.zeros_like(source)
    for corner in range(3):
        np.add.at(normals,faces[:,corner],face_normals)
    normals /= np.maximum(np.linalg.norm(normals,axis=1)[:,None],1e-20)
    if signed_source_volume < 0:
        normals *= -1
    delta = _cap(np,proposal-source,limit)

    def candidate(offset):
        return source + _cap(np,delta + offset*normals,limit)

    lo, hi = -limit, limit
    if abs(_signed_volume(np,candidate(lo),faces)) > source_volume or abs(_signed_volume(np,candidate(hi),faces)) < source_volume:
        raise ValueError('No se puede conservar el volumen dentro del límite de movimiento')
    result = source.copy()
    for _ in range(28):
        mid = (lo+hi)*.5
        result = candidate(mid)
        current = abs(_signed_volume(np,result,faces))
        if abs(current/source_volume-1.0) < 2e-9:
            break
        if current < source_volume:
            lo = mid
        else:
            hi = mid
    # Validate the actual precision stored by Blender's mesh fields.
    result = result.astype(np.float32).astype(np.float64)
    ratio = abs(_signed_volume(np,result,faces))/source_volume
    if abs(ratio-1.0) > VOLUME_RELATIVE_TOLERANCE:
        raise ValueError('El volumen suavizado queda fuera de la tolerancia numérica')
    out_tri = result[faces]
    out_normals = np.cross(out_tri[:,1]-out_tri[:,0],out_tri[:,2]-out_tri[:,0])
    if np.any(np.einsum('ij,ij->i',face_normals,out_normals) <= 0):
        raise ValueError('El suavizado invertiría o colapsaría alguna cara')
    return result,source_volume,ratio


def smooth_surface_preserving_volume(vertices, faces, *, max_distance_mm, vtk_module):
    """Return same-index positions and measured guards; never modify inputs.

    The caller supplies coordinates in millimetres. Matching vertices and faces
    also bounds displacement at every barycentric point of every triangle.
    Each closed connected component preserves its own volume, so a larger jaw
    cannot hide volume loss in a smaller tooth of an alignment composite.
    """
    import numpy as np
    from vtk.util.numpy_support import numpy_to_vtk,numpy_to_vtkIdTypeArray,vtk_to_numpy
    started = time.perf_counter()
    v = np.array(vertices,dtype=np.float64,copy=True)
    f = np.array(faces,dtype=np.int64,copy=True)
    requested_limit = float(max_distance_mm)
    if v.ndim != 2 or v.shape[1:] != (3,) or f.ndim != 2 or f.shape[1:] != (3,) or len(v)<4 or len(f)<4:
        raise ValueError('La superficie debe ser una malla triangular cerrada')
    if not np.all(np.isfinite(v)) or not np.isfinite(requested_limit) or requested_limit<=0 or f.min()<0 or f.max()>=len(v):
        raise ValueError('Coordenadas, índices o límite de suavizado inválidos')
    if vtk_module is None:
        raise RuntimeError('Falta VTK para el suavizado medido de la superficie')
    vtk = vtk_module
    pd = vtk.vtkPolyData()
    pts = vtk.vtkPoints(); pts.SetData(numpy_to_vtk(v,deep=True)); pd.SetPoints(pts)
    cells = vtk.vtkCellArray()
    cells.SetData(numpy_to_vtkIdTypeArray(np.arange(0,len(f)*3+1,3,dtype=np.int64),deep=True),numpy_to_vtkIdTypeArray(f.ravel(),deep=True))
    pd.SetPolys(cells)
    ids = numpy_to_vtkIdTypeArray(np.arange(len(v),dtype=np.int64),deep=True)
    ids.SetName('DSG_OriginalVertexId'); pd.GetPointData().AddArray(ids)
    edges = vtk.vtkFeatureEdges(); edges.SetInputData(pd)
    edges.BoundaryEdgesOn(); edges.NonManifoldEdgesOn(); edges.FeatureEdgesOff(); edges.ManifoldEdgesOff(); edges.Update()
    if edges.GetOutput().GetNumberOfCells():
        raise ValueError('La malla no es cerrada/manifold; no se puede garantizar su volumen')
    connectivity = vtk.vtkPolyDataConnectivityFilter(); connectivity.SetInputData(pd)
    connectivity.SetExtractionModeToAllRegions(); connectivity.ColorRegionsOn(); connectivity.Update()
    connected = connectivity.GetOutput()
    original_ids = vtk_to_numpy(connected.GetPointData().GetArray('DSG_OriginalVertexId')).astype(np.int64)
    region_values = vtk_to_numpy(connected.GetPointData().GetArray('RegionId')).astype(np.int64)
    regions = np.full(len(v),-1,dtype=np.int64)
    regions[original_ids] = region_values
    if np.any(regions<0):
        raise ValueError('La malla contiene vértices sin una superficie cerrada')
    filt = vtk.vtkWindowedSincPolyDataFilter(); filt.SetInputData(pd)
    filt.SetNumberOfIterations(40); filt.SetPassBand(.02)
    filt.BoundarySmoothingOff(); filt.FeatureEdgeSmoothingOff(); filt.NonManifoldSmoothingOn(); filt.NormalizeCoordinatesOn()
    if hasattr(filt,'SetWindowFunctionToNuttall'):
        filt.SetWindowFunctionToNuttall()
    filt.Update()
    proposal = np.array(vtk_to_numpy(filt.GetOutput().GetPoints().GetData()),dtype=np.float64)
    if proposal.shape != v.shape or not np.all(np.isfinite(proposal)):
        raise ValueError('El filtro cambió el número de puntos o produjo coordenadas inválidas')
    # Leave room for float32 offset addition in Blender's evaluated node mesh.
    rounding_margin = 8*np.finfo(np.float32).eps*max(1.0,float(np.max(np.abs(v))))
    limit = requested_limit-rounding_margin
    if limit<=0:
        raise ValueError('El límite es menor que la precisión disponible para esta malla')
    result = v.copy()
    source_total = 0.0
    errors = []
    conservative_components=0
    unchanged_components=0
    face_regions = regions[f[:,0]]
    # Group once: scanning an entire jaw per small island would dominate runtime.
    vertex_order=np.argsort(regions,kind='stable')
    vertex_counts=np.bincount(regions)
    vertex_bounds=np.concatenate(([0],np.cumsum(vertex_counts)))
    face_order=np.argsort(face_regions,kind='stable')
    face_counts=np.bincount(face_regions,minlength=len(vertex_counts))
    face_bounds=np.concatenate(([0],np.cumsum(face_counts)))
    remap=np.empty(len(v),dtype=np.int64)
    for region in np.unique(regions):
        indices = vertex_order[vertex_bounds[region]:vertex_bounds[region+1]]
        selected_faces = f[face_order[face_bounds[region]:face_bounds[region+1]]]
        remap[indices] = np.arange(len(indices))
        local_faces = remap[selected_faces]
        local_source=v[indices]
        for weight in (1.0,.5,.25,.125):
            try:
                local_proposal=local_source+weight*(proposal[indices]-local_source)
                local_result,source_volume,ratio = _compensate_volume(np,local_source,local_faces,local_proposal,limit)
                if weight<1:
                    conservative_components+=1
                break
            except ValueError:
                continue
        else:
            # Tiny/thin islands may not support smoothing in float32. Preserve
            # their real source, instead of filling, dropping or distorting them.
            local_result=local_source.astype(np.float32).astype(np.float64)
            source_volume=abs(_signed_volume(np,local_source,local_faces))
            if source_volume<=1e-12:
                raise ValueError('La componente no tiene un volumen cerrado medible')
            ratio=abs(_signed_volume(np,local_result,local_faces))/source_volume
            if abs(ratio-1)>VOLUME_RELATIVE_TOLERANCE:
                raise ValueError('La precisión original de la componente no permite conservar su volumen')
            unchanged_components+=1
        result[indices] = local_result
        source_total += source_volume
        errors.append(abs(ratio-1.0))
    displacement = np.linalg.norm(result-v,axis=1)
    if displacement.max() > requested_limit:
        raise ValueError('El resultado supera el movimiento permitido por el CBCT')
    return result.astype(np.float32),{
        'status':'READY','algorithm':ALGORITHM_VERSION,'point_count':len(v),'triangle_count':len(f),
        'component_count':len(errors),'source_volume_mm3':source_total,
        'conservative_component_count':conservative_components,'unchanged_component_count':unchanged_components,
        'max_component_volume_relative_error':max(errors),
        'max_displacement_mm':float(displacement.max()),'mean_displacement_mm':float(displacement.mean()),
        'displacement_limit_mm':requested_limit,'elapsed_s':time.perf_counter()-started,
    }


OFFSET_ATTRIBUTE = 'DSG_CBCT_SmoothOffset'
DISPLAY_NODE_GROUP = 'DSG_CBCT_ConstrainedSurfaceDisplay'


def _display_nodes(bpy):
    group = bpy.data.node_groups.get(DISPLAY_NODE_GROUP)
    if group is not None:
        return group
    group = bpy.data.node_groups.new(DISPLAY_NODE_GROUP,'GeometryNodeTree')
    group.interface.new_socket(name='Geometry',in_out='INPUT',socket_type='NodeSocketGeometry')
    group.interface.new_socket(name='Geometry',in_out='OUTPUT',socket_type='NodeSocketGeometry')
    source = group.nodes.new('NodeGroupInput')
    attribute = group.nodes.new('GeometryNodeInputNamedAttribute'); attribute.data_type='FLOAT_VECTOR'
    attribute.inputs['Name'].default_value=OFFSET_ATTRIBUTE
    position = group.nodes.new('GeometryNodeSetPosition')
    output = group.nodes.new('NodeGroupOutput')
    group.links.new(source.outputs['Geometry'],position.inputs['Geometry'])
    group.links.new(attribute.outputs['Attribute'],position.inputs['Offset'])
    group.links.new(position.outputs['Geometry'],output.inputs['Geometry'])
    return group


def set_measured_display_smoothing(obj, enabled, *, modifier_name, spacing_zyx_mm):
    """Cache offsets once; display them with a reversible same-topology modifier."""
    import hashlib
    import json
    import bpy
    import numpy as np
    from . import dicom_module
    mod = obj.modifiers.get(modifier_name)
    if not enabled:
        if mod is not None:
            mod.show_viewport=False
        return
    mesh = obj.data
    mesh.calc_loop_triangles()
    coordinates = np.empty(len(mesh.vertices)*3,dtype=np.float32); mesh.vertices.foreach_get('co',coordinates)
    vertices = coordinates.reshape(-1,3)
    indices = np.empty(len(mesh.loop_triangles)*3,dtype=np.int32); mesh.loop_triangles.foreach_get('vertices',indices)
    faces = indices.reshape(-1,3)
    spacing = np.asarray(spacing_zyx_mm,dtype=np.float64)
    if spacing.shape!=(3,) or not np.all(np.isfinite(spacing)) or np.any(spacing<=0):
        raise ValueError('Falta una escala física CBCT válida para limitar el suavizado')
    signature = hashlib.sha256(coordinates.tobytes()+indices.tobytes()+spacing.tobytes()+ALGORITHM_VERSION.encode()).hexdigest()
    attribute = mesh.attributes.get(OFFSET_ATTRIBUTE)
    if attribute is None or obj.get('DSG_surface_smoothing_source_sha256') != signature:
        refined,stats = smooth_surface_preserving_volume(vertices,faces,max_distance_mm=min(.25,1.25*float(spacing.min())),vtk_module=dicom_module.load_vtk())
        if attribute is None:
            attribute = mesh.attributes.new(OFFSET_ATTRIBUTE,'FLOAT_VECTOR','POINT')
        attribute.data.foreach_set('vector',(refined-vertices).ravel())
        obj['DSG_surface_smoothing_source_sha256']=signature
        obj['DSG_surface_smoothing_stats_json']=json.dumps(stats)
    if mod is not None and mod.type!='NODES':
        obj.modifiers.remove(mod); mod=None
    if mod is None:
        mod=obj.modifiers.new(modifier_name,'NODES')
    mod.node_group=_display_nodes(bpy)
    mod.show_render=False
    mod.show_viewport=True
    obj['DSG_alignment_visual_smoothing']=ALGORITHM_VERSION
    mesh.polygons.foreach_set('use_smooth',np.ones(len(mesh.polygons),dtype=np.bool_))
    mesh.update()
