"""Readonly implant emergence references for contour/frame design."""
import bpy
from mathutils import Matrix

FLAG='DSG_frame_emergence_reference'
PREFIX='DSG_EmergenceReference_'


def sync(context,step=None):
    from .. import guide_module as g
    scene=context.scene;props=scene.dsg_props
    step=int(props.current_step) if step is None else int(step)
    show=step in {g.STEP_CONTOUR,g.STEP_FRAME}
    implants=g.get_all_implant_objects(props) if show else []
    wanted=set()
    for implant in implants:
        name=PREFIX+implant.name;wanted.add(name)
        obj=scene.objects.get(name)
        if obj is None:
            length=float(g.IMPLANT_EMERGENCE_LENGTH_MM)
            mesh=g.make_cylinder_mesh(name+'_Mesh',float(g.IMPLANT_EMERGENCE_DIAMETER_MM)*.5,length,verts=24)
            mesh.transform(Matrix.Translation((0,0,length*.5)))
            obj=bpy.data.objects.new(name,mesh);scene.collection.objects.link(obj)
            obj[FLAG]=True;obj['DSG_preview_only']=True
            obj['DSG_implant_name']=implant.name
            material=bpy.data.materials.get('DSG_EmergenceReference') or bpy.data.materials.new('DSG_EmergenceReference')
            material.diffuse_color=(.15,.75,.45,1.)
            material.use_nodes=True
            shader=material.node_tree.nodes.get('Principled BSDF')
            if shader:shader.inputs['Base Color'].default_value=(.15,.75,.45,1.)
            mesh.materials.append(material)
        centre=g.get_implant_center_world(props,implant)
        direction=g._emergence_coronal_direction_world(implant)
        obj.matrix_world=g._matrix_along_local_z(centre,direction)
        obj.hide_viewport=False;obj.hide_set(False)
        obj.hide_select=True;obj.hide_render=True;obj.show_in_front=True
        implant.hide_viewport=False;implant.hide_set(False);implant.hide_select=True;implant.show_in_front=True
    for obj in scene.objects:
        if obj.get(FLAG) and obj.name not in wanted:
            obj.hide_set(True);obj.hide_render=True;obj.hide_select=True
