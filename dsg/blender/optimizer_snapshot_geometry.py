"""Immutable arrays for raw meshes and DSG's measured display offsets.

Replay the known same-topology offset graph directly, so hidden anatomy is
identical to visible anatomy without toggling visibility or applying modifiers.
Other active modifier stacks remain unverified and are rejected.
"""
import hashlib
import numpy as np

def _measured_modifier(obj,active):
    from .. import cbct_dental_module as dental,surface_smoothing as smooth
    if len(active)!=1 or active[0].name!=dental.ALIGNMENT_VISUAL_SMOOTH_MODIFIER or active[0].type!='NODES':
        raise ValueError(obj.name+': aplica o desactiva sus modificadores antes de evaluar.')
    modifier=active[0];group=modifier.node_group
    expected={'NodeGroupInput','GeometryNodeInputNamedAttribute','GeometryNodeSetPosition','NodeGroupOutput'}
    if group is None or group.name!=smooth.DISPLAY_NODE_GROUP or len(group.nodes)!=4 or {n.bl_idname for n in group.nodes}!=expected:
        raise ValueError(obj.name+': el modificador de suavizado no coincide con el formato DSG verificable.')
    nodes={n.bl_idname:n for n in group.nodes}
    links={(l.from_node.bl_idname,l.from_socket.name,l.to_node.bl_idname,l.to_socket.name) for l in group.links}
    wanted={('NodeGroupInput','Geometry','GeometryNodeSetPosition','Geometry'),('GeometryNodeInputNamedAttribute','Attribute','GeometryNodeSetPosition','Offset'),('GeometryNodeSetPosition','Geometry','NodeGroupOutput','Geometry')}
    attribute=nodes['GeometryNodeInputNamedAttribute'];position=nodes['GeometryNodeSetPosition']
    expected_sockets={(nodes['NodeGroupInput'].outputs['Geometry'].as_pointer(),position.inputs['Geometry'].as_pointer()),
                      (attribute.outputs['Attribute'].as_pointer(),position.inputs['Offset'].as_pointer()),
                      (position.outputs['Geometry'].as_pointer(),nodes['NodeGroupOutput'].inputs['Geometry'].as_pointer())}
    actual_sockets={(link.from_socket.as_pointer(),link.to_socket.as_pointer()) for link in group.links}
    if actual_sockets!=expected_sockets or attribute.outputs['Attribute'].type!='VECTOR' or any(not link.is_valid for link in group.links) or not nodes['NodeGroupOutput'].is_active_output:
        raise ValueError(obj.name+': conexiones del suavizado no verificables.')
    if len(group.links)!=3 or links!=wanted or any(n.mute for n in group.nodes) or any(l.is_muted for l in group.links) or group.animation_data is not None:
        raise ValueError(obj.name+': el grafo de suavizado ha cambiado; requiere revisión.')
    if attribute.data_type!='FLOAT_VECTOR' or attribute.inputs['Name'].default_value!=smooth.OFFSET_ATTRIBUTE or not position.inputs['Selection'].default_value or np.any(np.asarray(position.inputs['Position'].default_value)!=0):
        raise ValueError(obj.name+': parámetros de suavizado no verificables.')
    return smooth

def mesh_arrays(obj,*,allow_measured=True):
    active=[m for m in obj.modifiers if m.show_viewport]
    if active and not allow_measured:
        raise ValueError(obj.name+': aplica o desactiva sus modificadores antes de evaluar.')
    smooth=_measured_modifier(obj,active) if active else None
    mesh=obj.data;mesh.calc_loop_triangles()
    vertices=np.empty(len(mesh.vertices)*3,np.float64);mesh.vertices.foreach_get('co',vertices);vertices=vertices.reshape(-1,3)
    faces=np.empty(len(mesh.loop_triangles)*3,np.int64);mesh.loop_triangles.foreach_get('vertices',faces);faces=faces.reshape(-1,3)
    if smooth is not None:
        attribute=mesh.attributes.get(smooth.OFFSET_ATTRIBUTE)
        if attribute is None or attribute.data_type!='FLOAT_VECTOR' or attribute.domain!='POINT' or len(attribute.data)!=len(vertices):
            raise ValueError(obj.name+': faltan desplazamientos de suavizado válidos.')
        offsets=np.empty(len(vertices)*3,np.float64);attribute.data.foreach_get('vector',offsets);offsets=offsets.reshape(-1,3)
        if not np.isfinite(offsets).all() or np.max(np.linalg.norm(offsets,axis=1),initial=0)>.25001:
            raise ValueError(obj.name+': desplazamiento del suavizado fuera de su límite medido.')
        vertices=(vertices.astype(np.float32)+offsets.astype(np.float32)).astype(np.float64)
    return vertices,faces

def display_signature(obj):
    if not any(m.show_viewport for m in obj.modifiers):return ''
    try:vertices,faces=mesh_arrays(obj)
    except ValueError as exc:return 'UNVERIFIABLE:'+str(exc)
    return hashlib.sha256(vertices.tobytes()+faces.tobytes()).hexdigest()
