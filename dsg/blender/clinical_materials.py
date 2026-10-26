"""Fixed clinical display policy. Object-slot overrides never change source meshes."""
import bpy

PALETTE = {'IOS': (0.28, 0.68, 0.90),
           'IMPLANT': (0.025, 0.16, 0.50), 'GUIDE': (0.88, 0.90, 0.93)}


def configure(material, color):
    material.use_nodes = True
    material.diffuse_color = color
    material.surface_render_method = 'BLENDED'
    material.use_backface_culling = True
    material.use_transparency_overlap = False
    material.use_transparent_shadow = False
    node = next((n for n in material.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)
    if node:
        for name, value in {'Base Color': color, 'Alpha': color[3], 'Thin Wall': True,
                            'IOR': 1.0, 'Transmission Weight': 0.0,
                            'Subsurface Weight': 0.0, 'Roughness': 0.48}.items():
            if name in node.inputs:
                node.inputs[name].default_value = value
    return material


def apply(obj, kind, thin=False):
    if obj is None or obj.type != 'MESH':
        return
    color = (*PALETTE[kind], 0.35 if thin else 1.0)
    name = 'DSG_Clinical_' + kind + ('_ThinWall' if thin else '_Solid')
    material = bpy.data.materials.get(name)
    if material is None:
        material = configure(bpy.data.materials.new(name), color)
    if not obj.material_slots:
        obj.data.materials.append(material)
    for slot in obj.material_slots:
        if slot.link != 'OBJECT':
            slot.link = 'OBJECT'
        if slot.material != material:
            slot.material = material
    if any(abs(a-b)>1e-6 for a,b in zip(obj.color,color)):
        obj.color = color


def anatomy(obj):
    """Keep every anatomical label's current RGB and separate material slots."""
    if obj is None or obj.type != 'MESH':
        return
    if not obj.material_slots:
        obj.data.materials.append(None)
    for slot in obj.material_slots:
        source = slot.material
        if source and source.get('DSG_clinical_anatomy'):
            continue
        rgb = tuple(source.diffuse_color[:3]) if source else tuple(obj.color[:3])
        name = 'DSG_Clinical_Anatomy_' + '_'.join(str(round(v*10000)) for v in rgb)
        material = bpy.data.materials.get(name)
        if material is None:
            material = configure(bpy.data.materials.new(name), (*rgb, 0.35))
            material['DSG_clinical_anatomy'] = True
        slot.link = 'OBJECT'
        slot.material = material


def sync(context):
    from .. import core, guide_module as g
    scene = context.scene
    if context.mode != 'OBJECT' or core.infer_stage(scene) != core.STAGE_GUIDE:
        return
    props = scene.dsg_props
    step = int(props.current_step)
    model = g._workflow_model_candidate(props, context)
    passive = g.get_confirmed_passive_model_obj()
    blockout = bpy.data.objects.get(g.BLOCKOUT_NAME)
    guide = g._workflow_guide_candidate(props)
    # The contour reference uses the same thin shell as frame planning. The guide becomes a thin shell
    # while inspecting bores or its final seating on the opaque IOS.
    visual = bpy.data.objects.get(g.BLOCKOUT_VISUAL_NAME)
    if visual is not None and visual.get('DSG_blockout_visual_source') != 'UNITED_MODEL':
        visual = None
    for obj in (model, passive, visual):
        if obj is not None and obj.visible_get():
            thin = step in {g.STEP_IMPLANT, g.STEP_CONTOUR, g.STEP_FRAME, g.STEP_SLEEVE, g.STEP_IRRIGATION, g.STEP_REINFORCEMENT}
            thin = thin or (step == g.STEP_MODEL and blockout is not None and blockout.visible_get() and obj != blockout)
            apply(obj, 'IOS', thin)
    if guide is not None and guide.visible_get():
        thin_guide = step in {g.STEP_IRRIGATION, g.STEP_REINFORCEMENT, g.STEP_DRILL, g.STEP_FINAL_CUT}
        if step == g.STEP_IRRIGATION and props.irr_drawing_active:
            thin_guide = False
        apply(guide, 'GUIDE', thin_guide)
    for implant in g.get_all_implant_objects(props):
        if implant.visible_get():
            apply(implant, 'IMPLANT')
    if step == g.STEP_IMPLANT:
        from . import virtual_extraction, mpr_view
        # Both routes: the bone reference stays thin; teeth, canals and warning
        # overlays retain their own opaque clinical/safety colours.
        for bone in mpr_view._bones(scene):
            if bone.visible_get():
                anatomy(bone)
        if virtual_extraction.required(scene):
            for bone in virtual_extraction.bones_for(scene, virtual_extraction.targets(scene)):
                if bone.visible_get():
                    anatomy(bone)


def _tick():
    try:
        if bpy.context.scene is not None:
            sync(bpy.context)
    except (ReferenceError, AttributeError, RuntimeError):
        pass
    return 0.5


def register():
    from .. import lifecycle
    lifecycle.unregister_timer(_tick)
    lifecycle.register_timer(_tick, first_interval=0.1, persistent=True)


def unregister():
    from .. import lifecycle
    lifecycle.unregister_timer(_tick)
