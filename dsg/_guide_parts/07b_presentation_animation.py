# =============================================================================
# DSG v9 · Presentación de la animación final
# Paleta sobria (gris, negro, morado) con turquesa como acento dinámico,
# anillo de trabajo en el implante activo, destellos al asentar, férula y
# hueso translúcidos durante la cirugía, plano final y modo de vista limpio.
# Los colores se aplican con obj.color + fotogramas CONSTANT y se ven en modo
# Solid con color por objeto; los materiales y la exportación no cambian.
# =============================================================================

PRESENTATION_BACKGROUND_RGB = (0.055, 0.060, 0.070)
PRES_MODEL_RGBA = (0.52, 0.55, 0.58, 1.0)          # gris modelo
PRES_NEUTRAL_RGBA = (0.40, 0.42, 0.45, 1.0)        # resto de objetos
PRES_GUIDE_RGBA = (0.00, 0.72, 0.70, 1.0)          # turquesa férula
PRES_GUIDE_SURGERY_ALPHA = 0.42
PRES_IMPLANT_RGBA = (0.80, 0.82, 0.85, 1.0)        # titanio claro
PRES_IMPLANT_FINAL_RGBA = (0.00, 0.80, 0.78, 1.0)  # implantes en el plano final
PRES_DRILL_RGBA = (0.035, 0.040, 0.050, 1.0)       # negro
PRES_SCREW_RGBA = (0.36, 0.12, 0.56, 1.0)          # morado
PRES_TOOTH_RGBA = (0.88, 0.88, 0.86, 1.0)          # diente extraído
PRES_BONE_RGBA = (0.70, 0.72, 0.74, 1.0)           # hueso CBCT
PRES_BONE_SURGERY_ALPHA = 0.32
PRES_WATER_RGBA = (0.30, 0.90, 0.92, 0.78)         # irrigación
PRES_RING_RGBA = (0.00, 0.82, 0.80, 1.0)           # anillo de trabajo
PRES_FLASH_RGBA = (0.62, 1.00, 0.96, 1.0)          # destello al asentar
PRES_FLASH_FRAMES = 6
PRES_RING_PREFIX = 'DSG_PresentationRing_'
PRES_COLOR_TAG = 'DSG_presentation_color'
PRES_PREVIOUS_COLOR = 'DSG_presentation_previous_color'
PRES_VIEW_BACKUP_KEY = 'DSG_presentation_view_backup'


# --- colores ---------------------------------------------------------------
def _clear_color_keys(obj):
    action = obj.animation_data.action if obj.animation_data else None
    for fcurve in _action_fcurves(action):
        if fcurve.data_path == 'color':
            _remove_action_fcurve(action, fcurve)


def _key_color(obj, rgba, frame):
    obj.color = tuple(float(v) for v in rgba)
    obj.keyframe_insert(data_path='color', frame=int(frame))


def _constant_color_keys(obj):
    action = obj.animation_data.action if obj.animation_data else None
    for fcurve in _action_fcurves(action):
        if fcurve.data_path == 'color':
            for key in fcurve.keyframe_points:
                key.interpolation = 'CONSTANT'


def _with_alpha(rgba, alpha):
    return (rgba[0], rgba[1], rgba[2], float(alpha))


def _tag_presentation(obj, base_rgba):
    if not bool(obj.get(PRES_COLOR_TAG, False)):
        obj[PRES_PREVIOUS_COLOR] = [float(v) for v in obj.color]
    obj[PRES_COLOR_TAG] = True
    _clear_color_keys(obj)
    obj.color = tuple(float(v) for v in base_rgba)


def clear_presentation_animation():
    """Remove rings and colour keys; restore each object's previous colour."""
    for obj in list(bpy.data.objects):
        if obj.name.startswith(PRES_RING_PREFIX):
            safe_remove_object(obj)
            continue
        if not bool(obj.get(PRES_COLOR_TAG, False)):
            continue
        try:
            _clear_color_keys(obj)
            previous = obj.get(PRES_PREVIOUS_COLOR)
            if previous is not None and len(previous) == 4:
                obj.color = tuple(float(v) for v in previous)
            for key in (PRES_COLOR_TAG, PRES_PREVIOUS_COLOR):
                if key in obj:
                    del obj[key]
        except (ReferenceError, RuntimeError, TypeError):
            _DSG_LOG.debug("suppressed exception", exc_info=True)


def _is_cbct_object(obj):
    role = core.role_of(obj)
    return role in {core.ROLE_DICOM_BONE, core.ROLE_DICOM_TEETH,
                    core.ROLE_DICOM_ALIGNMENT_COMPOSITE, core.ROLE_DICOM_MANDIBULAR_CANAL}


# --- anillo de trabajo ---------------------------------------------------------
def _torus_mesh(name, major_radius, minor_radius, segments=56, sides=10):
    vertices = []
    faces = []
    for i in range(segments):
        u = math.tau * i / segments
        cu, su = math.cos(u), math.sin(u)
        for j in range(sides):
            v = math.tau * j / sides
            radius = major_radius + minor_radius * math.cos(v)
            vertices.append((radius * cu, radius * su, minor_radius * math.sin(v)))
    for i in range(segments):
        for j in range(sides):
            a = i * sides + j
            b = ((i + 1) % segments) * sides + j
            c = ((i + 1) % segments) * sides + (j + 1) % sides
            d = i * sides + (j + 1) % sides
            faces.append((a, b, c, d))
    mesh = bpy.data.meshes.new(name + '_Mesh')
    mesh.from_pydata(vertices, [], faces)
    for polygon in mesh.polygons:
        polygon.use_smooth = True
    mesh.update()
    return mesh


def _build_site_ring(context, props, implant, index, visible_from, visible_to):
    name = f'{PRES_RING_PREFIX}{index:02d}'
    safe_remove_by_name(name)
    rotation, occlusal_axis = _rotation_for_drill_on_sleeve(props, implant)
    sleeve_height = max(0.5, float(props.sleeve_height))
    inner = max(0.5, float(props.sleeve_inner_diameter))
    centre = get_sleeve_center_world(props, implant) + occlusal_axis * (sleeve_height * 0.5 + 0.35)
    obj = bpy.data.objects.new(name, _torus_mesh(name, inner * 0.5 + 1.1, 0.24))
    link_object(context, obj)
    obj['DSG_visual_only'] = True
    obj['DSG_presentation_ring'] = True
    obj.rotation_mode = 'QUATERNION'
    obj.rotation_quaternion = rotation
    obj.location = centre
    obj.hide_render = True
    obj.hide_select = True
    keys = []
    if visible_from > 1:
        keys.append((visible_from - 1, True))
    keys += [(visible_from, False), (visible_to, False), (visible_to + 1, True)]
    for frame, hidden in keys:
        obj.hide_viewport = bool(hidden)
        obj.keyframe_insert(data_path='hide_viewport', frame=int(frame))
    obj[PRES_COLOR_TAG] = True
    obj[PRES_PREVIOUS_COLOR] = [1.0, 1.0, 1.0, 1.0]
    return obj


def _flash(obj, base_rgba, frame):
    _key_color(obj, base_rgba, frame - 1)
    _key_color(obj, PRES_FLASH_RGBA, frame)
    _key_color(obj, base_rgba, frame + PRES_FLASH_FRAMES)


# --- aplicación sobre la secuencia ---------------------------------------------
def apply_presentation_animation(context, props, timeline):
    """Colour keys and work rings driven by the sequence timeline."""
    clear_presentation_animation()
    start = int(timeline['sequence_start'])
    guide = get_active_guide_obj(props)
    model = props.model_obj
    implants = get_all_implant_objects(props)
    drills = get_animated_drill_objects()
    screws = get_animated_microscrew_objects()
    teeth = get_animated_extraction_tooth_objects()
    special = set()
    for group in (implants, drills, screws, teeth):
        special.update(obj.name for obj in group if _valid_obj(obj))
    if _valid_obj(guide):
        special.add(guide.name)

    # Base colours for everything visible in the scene.
    for obj in context.scene.objects:
        if obj.type != 'MESH' or obj.name in special or obj.name.startswith(PRES_RING_PREFIX):
            continue
        if obj.name.startswith(IRR_FLOW_SIM_PREFIX):
            base = PRES_WATER_RGBA
        elif _valid_obj(model) and obj == model:
            base = PRES_MODEL_RGBA
        elif core.role_of(obj) in {core.ROLE_IOS_SCAN, core.ROLE_IOS_ALIGNED}:
            base = PRES_MODEL_RGBA
        elif _is_cbct_object(obj):
            base = PRES_BONE_RGBA
        else:
            base = PRES_NEUTRAL_RGBA
        _tag_presentation(obj, base)
        if _is_cbct_object(obj) and int(timeline.get('drill_start', 0)) < int(timeline.get('active_end', 0)):
            # Hueso translúcido mientras se fresa y se coloca el implante.
            _key_color(obj, base, start)
            _key_color(obj, _with_alpha(base, PRES_BONE_SURGERY_ALPHA), timeline['drill_start'])
            _key_color(obj, base, int(timeline['active_end']) + 1)
            _constant_color_keys(obj)

    for tooth in teeth:
        _tag_presentation(tooth, PRES_TOOTH_RGBA)
    for drill in drills:
        _tag_presentation(drill, PRES_DRILL_RGBA)

    # Férula: turquesa opaca al entrar, translúcida durante la cirugía.
    if _valid_obj(guide):
        _tag_presentation(guide, PRES_GUIDE_RGBA)
        _key_color(guide, PRES_GUIDE_RGBA, start)
        _key_color(guide, PRES_GUIDE_RGBA, timeline['guide_seat_end'])
        _key_color(guide, _with_alpha(PRES_GUIDE_RGBA, PRES_GUIDE_SURGERY_ALPHA), timeline['surgery_start'])
        _key_color(guide, PRES_GUIDE_RGBA, timeline['guide_return_start'])
        _constant_color_keys(guide)

    # Microtornillos: morado, destello turquesa al asentar.
    for index, screw in enumerate(screws):
        _tag_presentation(screw, PRES_SCREW_RGBA)
        seat = int(screw.get('DSG_animation_start_frame', timeline['screw_start'])) + int(timeline['screw_duration'])
        _key_color(screw, PRES_SCREW_RGBA, start)
        _flash(screw, PRES_SCREW_RGBA, seat)
        _constant_color_keys(screw)

    # Parejas fresa–implante: anillo turquesa en el cilindro activo, destello
    # al tocar el tope y al asentar el implante; implantes turquesa en el final.
    hold = int(ANIMATION_SEATED_HOLD_FRAMES_FIXED)
    final_frame = int(timeline['guide_hide_frame'])
    for index, implant in enumerate(implants):
        if not _valid_obj(implant):
            continue
        drill_start = int(timeline['drill_start']) + index * int(timeline['pair_stride'])
        drill = next((d for d in drills if str(d.get('DSG_implant_name', '')) == implant.name), None)
        contact = int(drill.get('DSG_animation_contact_frame', drill_start)) if drill else drill_start
        seat = int(implant.get('DSG_implant_animation_end_frame', drill_start + int(timeline['drill_duration'])))
        # (9.22.34) Sin anillo de trabajo sobre el sleeve: el usuario no lo quiere.
        _tag_presentation(implant, PRES_IMPLANT_RGBA)
        _key_color(implant, PRES_IMPLANT_RGBA, start)
        _flash(implant, PRES_IMPLANT_RGBA, seat)
        _key_color(implant, PRES_IMPLANT_FINAL_RGBA, final_frame)
        _constant_color_keys(implant)
    return True


# --- modo de vista ----------------------------------------------------------------
_VIEW_FIELDS = ('type', 'color_type', 'light', 'show_shadows', 'show_cavity',
                'cavity_type', 'show_specular_highlight', 'background_type',
                'background_color', 'show_xray', 'show_object_outline')


def _iter_view3d_spaces(context):
    for window in context.window_manager.windows:
        screen = window.screen
        if screen is None:
            continue
        for area_index, area in enumerate(screen.areas):
            if area.type != 'VIEW_3D':
                continue
            for space in area.spaces:
                if space.type == 'VIEW_3D':
                    yield f'{screen.name}|{area_index}', area, space


def enter_presentation_view(context, speed=1.0):
    scene = context.scene
    if PRES_VIEW_BACKUP_KEY not in scene:
        backup = {'fps_base': float(scene.render.fps_base), 'spaces': {}}
        for key, _area, space in _iter_view3d_spaces(context):
            shading = space.shading
            saved = {}
            for field in _VIEW_FIELDS:
                value = getattr(shading, field)
                saved[field] = list(value) if field == 'background_color' else value
            saved['show_overlays'] = bool(space.overlay.show_overlays)
            backup['spaces'][key] = saved
        scene[PRES_VIEW_BACKUP_KEY] = json.dumps(backup)
    for _key, area, space in _iter_view3d_spaces(context):
        shading = space.shading
        shading.type = 'SOLID'
        shading.color_type = 'OBJECT'
        shading.light = 'STUDIO'
        shading.show_shadows = True
        shading.show_cavity = True
        shading.cavity_type = 'BOTH'
        shading.show_specular_highlight = True
        shading.background_type = 'VIEWPORT'
        shading.background_color = PRESENTATION_BACKGROUND_RGB
        shading.show_xray = False
        shading.show_object_outline = False
        space.overlay.show_overlays = False
        area.tag_redraw()
    scene.render.fps_base = 1.0 / max(0.25, float(speed))


def exit_presentation_view(context):
    scene = context.scene
    raw = scene.get(PRES_VIEW_BACKUP_KEY)
    if not raw:
        return False
    try:
        backup = json.loads(str(raw))
    except ValueError:
        del scene[PRES_VIEW_BACKUP_KEY]
        return False
    for key, area, space in _iter_view3d_spaces(context):
        saved = backup.get('spaces', {}).get(key)
        if not saved:
            continue
        for field in _VIEW_FIELDS:
            if field in saved:
                try:
                    setattr(space.shading, field, tuple(saved[field]) if field == 'background_color' else saved[field])
                except (TypeError, ValueError, AttributeError):
                    _DSG_LOG.debug("suppressed exception", exc_info=True)
        space.overlay.show_overlays = bool(saved.get('show_overlays', True))
        area.tag_redraw()
    scene.render.fps_base = float(backup.get('fps_base', 1.0))
    del scene[PRES_VIEW_BACKUP_KEY]
    return True
