"""Persist the pose/proposal on which a manual MPR measurement was made."""
import hashlib
import json
import bpy

DESCRIPTOR='DSG_measure_context'
SIGNATURE='DSG_measure_context_signature'


def _object_pose(obj):
    if obj is None:
        return None
    return dict(name=obj.name,matrix=[round(float(v),6) for row in obj.matrix_world for v in row],
                mesh=getattr(obj.data,'name',''),vertices=len(obj.data.vertices) if obj.type=='MESH' else 0,
                diameter=obj.get('DSG_implant_diameter'),length=obj.get('DSG_implant_length'),
                proposal=obj.get('DSG_measure_context_id',''))


def signature(scene,descriptor):
    implants=[]
    for name in descriptor['implants']:
        obj=scene.objects.get(name)
        proposals=[_object_pose(o) for o in scene.objects if o.get('DSG_optimizer_preview')
                   and str(o.get('DSG_optimizer_original',''))==name]
        implants.append(dict(source=_object_pose(obj),proposals=sorted(proposals,key=lambda r:r['name'])))
    planes=[_object_pose(scene.objects.get(name)) for name in descriptor['planes']]
    data=json.dumps(dict(implants=implants,planes=planes),sort_keys=True)
    return hashlib.sha256(data.encode()).hexdigest()


def bind(context,root):
    scene=context.scene
    names={str(root.get(key,'')) for key in ('DSG_measure_plane','DSG_measure_plane_a','DSG_measure_plane_b')}
    names.discard('')
    sources={str(root.get('DSG_measure_implant',''))};sources.discard('')
    for name in names:
        plane=scene.objects.get(name)
        if plane is not None and plane.get('DSG_inclination_plane_implant'):
            sources.add(str(plane['DSG_inclination_plane_implant']))
    if not sources:
        from .implant_plane import selected_implant
        implant=selected_implant(context)
        if implant is not None:sources.add(implant.name)
    descriptor=dict(scene=scene.name,implants=sorted(sources),planes=sorted(names))
    root[DESCRIPTOR]=json.dumps(descriptor,sort_keys=True)
    root[SIGNATURE]=signature(scene,descriptor)


def stale(root):
    # Legacy annotations have no verifiable creation pose: never silently adopt one.
    if DESCRIPTOR not in root or SIGNATURE not in root:
        return True
    try:
        descriptor=json.loads(str(root[DESCRIPTOR]))
        scene=bpy.data.scenes.get(descriptor['scene'])
        return scene is None or signature(scene,descriptor)!=root[SIGNATURE]
    except (KeyError,ValueError,ReferenceError,TypeError):
        return True
