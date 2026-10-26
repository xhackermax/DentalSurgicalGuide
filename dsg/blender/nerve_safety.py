"""Independent 3D clearance from implant surface to segmented mandibular canal."""
import json
import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from .surface_clearance_bounds import classify

MISSING='DSG_NERVE_SEGMENTATION_MISSING'
REPORT='DSG_nerve_safety_report'
_WORLD={}
_SOLIDS={}


def capture_arch(scene,implant):
    from .. import core
    fdi=int(implant.get('DSG_target_fdi',0))
    lower=30<=fdi<=48 if fdi else str(scene.get('DSG_active_arch','')).upper()=='MANDIBLE' or 30<=core.target_fdi(scene)<=48
    implant['DSG_nerve_arch']='MANDIBLE' if lower else 'MAXILLA'
    return lower


def required(scene,implant):
    fdi=int(implant.get('DSG_target_fdi',0))
    if fdi:return 30<=fdi<=48
    arch=implant.get('DSG_nerve_arch')
    return arch=='MANDIBLE' if arch in {'MANDIBLE','MAXILLA'} else capture_arch(scene,implant)


def margin(scene,override=None):
    configured=float(scene.dsg_nerve_margin_mm) if 'dsg_nerve_margin_mm' in scene.bl_rna.properties else float(scene.get('dsg_nerve_margin_mm',2.))
    value=max(2.,configured,float(override or 0.))
    if not np.isfinite(value):raise ValueError('Margen del nervio inválido.')
    return value


def changed(_scene,context):
    from . import safety_volume as safety
    safety.STATE['checked'].clear()
    safety.update(context.scene,context.evaluated_depsgraph_get())


def register():
    if 'dsg_nerve_margin_mm' not in bpy.types.Scene.bl_rna.properties:
        bpy.types.Scene.dsg_nerve_margin_mm=bpy.props.FloatProperty(name='Margen del nervio',default=2.,min=2.,max=10.,precision=2,update=changed,
            description='Separación 3D mínima respecto a la superficie del canal mandibular segmentado; independiente del margen dental')


def unregister():
    clear()
    if 'dsg_nerve_margin_mm' in bpy.types.Scene.bl_rna.properties:del bpy.types.Scene.dsg_nerve_margin_mm


def clear():
    _WORLD.clear()
    _SOLIDS.clear()


def _convex_proxy(vertices):
    """Closed conservative outer envelope, without modifying the source mesh."""
    import bmesh
    bm=bmesh.new()
    try:
        for point in vertices:bm.verts.new(point)
        bmesh.ops.convex_hull(bm,input=list(bm.verts),use_existing_faces=False)
        bmesh.ops.triangulate(bm,faces=list(bm.faces))
        bm.verts.index_update()
        points=np.asarray([tuple(vertex.co) for vertex in bm.verts])
        triangles=np.asarray([[vertex.index for vertex in face.verts] for face in bm.faces],dtype=int)
        return points,triangles
    finally:bm.free()


def _geometry(context,obj,allow_proxy=False):
    from . import safety_volume as safety
    from ..guide_export.mesh_checks import connected_components,manifold_report
    local,triangles,_tree=safety._local_geometry(obj,context.evaluated_depsgraph_get())
    key=(id(local),tuple(map(tuple,obj.matrix_world)),allow_proxy)
    cached=_WORLD.get(obj.name)
    if cached is not None and cached[0]==key:return cached[2]
    if not len(triangles):raise ValueError(obj.name+': malla vacía.')
    solid=_SOLIDS.get(obj.name)
    if solid is None or solid[0]!=(id(local),allow_proxy):
        points=local;proxy=False
        if manifold_report(local,triangles).blocking:
            if not allow_proxy:raise ValueError(obj.name+': la estructura protegida debe tener una malla cerrada para verificar su distancia.')
            points,triangles=_convex_proxy(local);proxy=True
            if manifold_report(points,triangles).blocking:raise ValueError(obj.name+': envolvente del implante no verificable.')
        labels=connected_components(len(points),triangles)
        witnesses=np.unique(labels[triangles.ravel()])
        solid=((id(local),allow_proxy),local,points,triangles,witnesses,proxy)
        _SOLIDS[obj.name]=solid
    points,triangles,witness_indices,proxy=solid[2:]
    matrix=np.asarray(obj.matrix_world,dtype=float)
    if abs(np.linalg.det(matrix[:3,:3]))<1e-12:raise ValueError(obj.name+': escala inválida.')
    vertices=points@matrix[:3,:3].T+matrix[:3,3]
    tree=BVHTree.FromPolygons(vertices.tolist(),triangles.tolist(),all_triangles=True)
    witnesses=vertices[witness_indices]
    geometry=(vertices,triangles,tree,witnesses,proxy)
    _WORLD[obj.name]=(key,local,geometry)
    return geometry


def measure(context,implant,canal,minimum):
    from .safety_volume import _inside
    a,ta,tree_a,witness_a,proxy=_geometry(context,implant,allow_proxy=True)
    b,tb,tree_b,witness_b,_proxy=_geometry(context,canal)
    metadata={'method':'EUCLIDEAN_SURFACE_BOUNDS','conservative_envelope':proxy}
    gap=np.maximum(0.,np.maximum(a.min(axis=0)-b.max(axis=0),b.min(axis=0)-a.max(axis=0)))
    lower=float(np.linalg.norm(gap))
    if lower>minimum+.02:
        return {'lower_mm':lower,'upper_mm':None,'status':'SAFE',**metadata}
    direction=Vector((1,.371,.219)).normalized()
    if tree_a.overlap(tree_b) or any(_inside(tree_b,Vector(p),direction) for p in witness_a) or any(_inside(tree_a,Vector(p),direction) for p in witness_b):
        return {'lower_mm':0.,'upper_mm':0.,'status':'ENVELOPE_CONTACT' if proxy else 'CONTACT',**metadata}
    def nearest(point):
        hit=tree_b.find_nearest(Vector(point))
        if hit[0] is None:raise ValueError('No se pudo medir el canal mandibular.')
        return hit[3]
    return {**classify(a[ta],nearest,minimum),**metadata}


def failures(context,implant,override=None):
    from .protected_neighbors import canals
    minimum=margin(context.scene,override)
    nerves=canals()
    if not nerves:
        if not required(context.scene,implant):
            implant[REPORT]='[]'
            return []
        implant[REPORT]=json.dumps([{'name':MISSING,'margin_mm':minimum,'status':'MISSING'}])
        return [MISSING]
    reports=[]
    for canal in nerves:
        try:
            result=measure(context,implant,canal,minimum)
        except (ValueError,RuntimeError) as exc:
            result={'lower_mm':None,'upper_mm':None,'status':'UNVERIFIED','reason':str(exc)}
        reports.append({'name':canal.name,'margin_mm':minimum,**result})
    implant[REPORT]=json.dumps(reports)
    return [item['name'] for item in reports if item['status']!='SAFE']


def description(implant,name):
    if name==MISSING:return 'Falta segmentación del nervio dentario: no se puede verificar su margen.'
    for item in json.loads(str(implant.get(REPORT,'[]'))):
        if item['name']!=name:continue
        if item['status']=='UNVERIFIED':return 'Margen del nervio no verificable: '+item['reason']
        if item['status']=='ENVELOPE_CONTACT':return 'Nervio dentario: la envolvente conservadora del implante invade el canal.'
        if item['status']=='CONTACT':distance='contacto físico'
        elif item['status']=='LIMIT':distance='distancia en el límite numérico'
        else:distance=f"distancia ≤ {item['upper_mm']:.2f} mm"
        subject='envolvente conservadora · ' if item.get('conservative_envelope') else ''
        return f"Nervio dentario · {subject}{distance} · margen requerido {item['margin_mm']:.2f} mm"
    return name


def draw(layout,context):
    from .protected_neighbors import lower,canals
    if not lower(context.scene):return
    from .implant_plane import selected_implant
    box=layout.box()
    box.label(text='ZONAS DE PELIGRO · mandíbula',icon='ERROR')
    box.label(text='Nervio dentario inferior (canal mandibular)',icon='ERROR')
    box.prop(context.scene,'dsg_nerve_margin_mm',text='Margen nervio · mm')
    nerves=canals()
    if not nerves:
        line=box.row();line.alert=True
        line.label(text='Falta segmentación del nervio: confirmación bloqueada.',icon='ERROR')
        return
    implant=selected_implant(context)
    try:reports=json.loads(str(implant.get(REPORT,'[]'))) if implant is not None else []
    except ValueError:reports=[]
    by_name={item['name']:item for item in reports}
    for canal in nerves:
        item=by_name.get(canal.name)
        line=box.row()
        if item is None:
            line.label(text=canal.name+' · pendiente de comprobación',icon='INFO')
        elif item.get('status')=='SAFE':
            bound=item.get('lower_mm')
            text=f"separación ≥ {bound:.2f} mm" if bound is not None else 'margen verificado'
            line.label(text=canal.name+' · '+text,icon='CHECKMARK')
        else:
            line.alert=True
            line.label(text=description(implant,canal.name),icon='ERROR')
