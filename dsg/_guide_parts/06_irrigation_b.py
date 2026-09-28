def create_irrigation_preview_path_curve(context, points, name, outer_radius, implant_obj=None):
    """Curva editable cuyos puntos son el eje interno real del conducto."""
    safe_remove_by_name(name)
    curve_data = bpy.data.curves.new(name + '_Data', type='CURVE')
    curve_data.dimensions = '3D'
    curve_data.resolution_u = 8
    curve_data.bevel_depth = max(0.03, float(outer_radius))
    curve_data.bevel_resolution = 2
    curve_data.fill_mode = 'FULL'
    curve_data.use_fill_caps = True
    spline = curve_data.splines.new(type='BEZIER')
    spline.bezier_points.add(len(points) - 1)
    for index, (bezier_point, world_point) in enumerate(zip(spline.bezier_points, points)):
        bezier_point.co = Vector(world_point)
        # El tramo profundo→superficie debe permanecer radial y controlable.
        if index < 2:
            bezier_point.handle_left_type = 'VECTOR'
            bezier_point.handle_right_type = 'VECTOR'
        else:
            bezier_point.handle_left_type = 'AUTO'
            bezier_point.handle_right_type = 'AUTO'
    curve_obj = bpy.data.objects.new(name, curve_data)
    link_object(context, curve_obj)
    link_object_to_dsg_collection(curve_obj, ROLE_IRRIGATION)
    curve_obj.show_in_front = True
    curve_obj.display_type = 'WIRE'
    curve_obj['DSG_irrigation_path_preview'] = True
    curve_obj['DSG_curve_contains_internal_extension'] = True
    curve_obj['DSG_implant'] = implant_obj.name if is_valid_implant_obj(implant_obj) else ''
    return curve_obj


def get_irrigation_preview_curve(preview_obj):
    if not _valid_obj(preview_obj):
        return None
    try:
        curve_name = str(preview_obj.get('DSG_preview_curve', ''))
    except Exception:
        curve_name = ''
    curve_obj = bpy.data.objects.get(curve_name) if curve_name else None
    return curve_obj if _valid_obj(curve_obj) and curve_obj.type == 'CURVE' else None


def get_irrigation_preview_path_world(preview_obj):
    if not _valid_obj(preview_obj):
        return []
    curve_obj = get_irrigation_preview_curve(preview_obj)
    if _valid_obj(curve_obj) and curve_obj.data.splines:
        spline = curve_obj.data.splines[0]
        if spline.type == 'BEZIER':
            return [curve_obj.matrix_world @ point.co for point in spline.bezier_points]
        return [curve_obj.matrix_world @ Vector(point.co[:3]) for point in spline.points]
    try:
        raw = preview_obj.get('DSG_preview_path_local', '[]')
        values = json.loads(raw) if isinstance(raw, str) else raw
        return [preview_obj.matrix_world @ Vector(item) for item in values]
    except Exception:
        return []


class DSG_OT_SetIrrigationCylinderChannelMode(Operator):
    bl_idname = 'dsg.set_irrigation_cylinder_channel_mode'
    bl_label = 'Set cylinder channel mode'
    bl_description = 'Change the internal irrigation mode for the cylinder'
    bl_options = {'REGISTER', 'UNDO'}

    mode: StringProperty(
        name='Mode',
        default='C')

    def execute(self, context):
        props = getattr(getattr(context, 'scene', None), 'dsg_props', None)
        if props is None:
            return {'CANCELLED'}
        value = str(self.mode or 'C').upper()
        if value not in {'C', 'DIRECT'}:
            value = 'C'
        props.irr_sleeve_channel_mode = value

        # If there is a pending irrigation preview, it belongs to the previous
        # internal channel mode. Removing it avoids confirming geometry that no
        # longer matches the visible option.
        try:
            preview = get_pending_irrigation_preview(props)
            if _valid_obj(preview):
                remove_irrigation_preview_bundle(preview, remove_curve=True)
            props.irr_preview_obj = None
            remove_irrigation_lumen_diagnostics(None)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        return {'FINISHED'}


class DSG_OT_ToggleIrrigationImplantSeal(Operator):
    bl_idname = 'dsg.toggle_irrigation_implant_seal'
    bl_label = 'Open / Seal Implant Irrigation'
    bl_description = 'Alternates this implant between an open outlet and a marked frangible internal wall'
    bl_options = {'REGISTER', 'UNDO'}

    implant_name: StringProperty(default='')

    def execute(self, context):
        props = context.scene.dsg_props
        implant = bpy.data.objects.get(self.implant_name) if self.implant_name else None
        if not is_valid_implant_obj(implant):
            _dsg_report(self, {'ERROR'}, 'Implant not found', 'No se encontró el implante')
            return {'CANCELLED'}
        sealed = not irrigation_implant_is_sealed(implant)
        if not set_irrigation_implant_sealed(implant, sealed):
            _dsg_report(self, {'ERROR'}, 'Could not save irrigation state', 'No se pudo guardar el estado de irrigación')
            return {'CANCELLED'}
        guide = get_active_guide_obj(props)
        if _valid_obj(guide):
            sync_irrigation_gate_metadata(guide, props)
        if sealed:
            _dsg_report(
                self, {'WARNING'},
                f'{implant.name}: export diaphragm scheduled; bench validation is required',
                f'{implant.name}: sello programado para exportación; requiere validación de banco')
        else:
            _dsg_report(self, {'INFO'}, f'{implant.name}: irrigation outlet open', f'{implant.name}: salida de irrigación abierta')
        return {'FINISHED'}


def build_irrigation_preview_from_points(context, props, points, *, implant=None):
    """Build the same irrigation preview as the modal tool from explicit points.

    This function is deliberately UI-agnostic so MCP/roadmap callers can prepare
    deterministic geometry on Blender's main thread.  It never confirms or
    applies the irrigation channel.
    """
    raw_points = [Vector(point) for point in points]
    if len(raw_points) < 2:
        return False, 'At least 2 irrigation points are required'
    if get_pending_irrigation_preview(props):
        return False, 'Confirm or discard the pending irrigation preview first'

    if not is_valid_implant_obj(implant):
        implant = props.implant_obj
    if not is_valid_implant_obj(implant):
        implant = get_nearest_implant_to_point(props, raw_points[0])
    if not is_valid_implant_obj(implant):
        return False, 'Could not associate the channel with a sleeve'

    controls = build_irrigation_initial_control_points(raw_points, props, implant)
    if len(controls) < 3:
        return False, 'Could not extend the path to the sleeve lumen'

    preview_name = f'{IRR_PREVIEW_PREFIX}{props.irr_chain_count:02d}'
    curve_name = f'{IRR_PREVIEW_PATH_PREFIX}{props.irr_chain_count:02d}'
    parameters = capture_irrigation_parameters(props)
    preview_props = irrigation_props_overlay(props, parameters)
    lumen_radius = max(0.05, float(parameters.get('irr_inner_diameter', props.irr_inner_diameter)) * 0.5)

    preview = build_irrigation_outer_wall_object(
        context, controls, preview_props, implant_obj=implant,
        name=preview_name, show_wire=True)
    curve_obj = create_irrigation_preview_path_curve(
        context, controls, curve_name, lumen_radius, implant_obj=implant)
    if not _valid_obj(preview) or not _valid_obj(curve_obj):
        safe_remove_object(preview)
        safe_remove_object(curve_obj)
        return False, 'Could not create the channel preview'

    register_dsg_object(preview, ROLE_IRRIGATION, preview_name, {
        'DSG_implant': implant.name,
        'DSG_irrigation_preview': True,
        'DSG_preview_curve': curve_obj.name,
        'DSG_preview_path_local': json.dumps([list(point) for point in controls]),
        'DSG_irrigation_params': json.dumps(parameters),
        'DSG_preview_source': 'explicit_points',
    })
    preview.display_type = 'WIRE'
    preview.show_in_front = True
    props.implant_obj = implant
    props.irr_preview_obj = preview
    set_active(context, curve_obj)
    return True, 'Irrigation preview created from explicit points'


class DSG_OT_StartIrrigationFromPoints(Operator):
    bl_idname = 'dsg.start_irrigation_from_points'
    bl_label = 'Irrigation Preview from Points'
    bl_options = {'REGISTER', 'UNDO'}

    points_json: StringProperty(
        name='Points JSON',
        description='World-space [[x,y,z], ...] control points',
        default='[]')
    implant_name: StringProperty(name='Implant', default='')

    def execute(self, context):
        if not _require_workflow_stage(
                self, context, STEP_IRRIGATION,
                action_en='Cannot prepare an irrigation channel',
                action_es='No se puede preparar un conducto de irrigación'):
            return {'CANCELLED'}
        props = context.scene.dsg_props
        if not _valid_obj(props.guide_obj):
            _dsg_report(self, {'ERROR'}, 'Create the sleeves first', 'Genera los cilindros primero')
            return {'CANCELLED'}
        try:
            raw = json.loads(str(self.points_json or '[]'))
            points = [tuple(float(v) for v in point[:3]) for point in raw]
        except Exception as exc:
            _dsg_report(self, {'ERROR'}, f'Invalid irrigation points JSON: {exc}', f'JSON de puntos de irrigación no válido: {exc}')
            return {'CANCELLED'}
        implant = bpy.data.objects.get(str(self.implant_name or '')) if self.implant_name else None
        ok, message = build_irrigation_preview_from_points(
            context, props, points, implant=implant)
        if not ok:
            _dsg_report(self, {'ERROR'}, message, message)
            return {'CANCELLED'}
        _dsg_report(self, {'INFO'}, message, 'Vista previa de irrigación creada desde puntos explícitos')
        return {'FINISHED'}


class DSG_OT_StartIrrigation(Operator):
    bl_idname = 'dsg.start_irrigation'
    bl_label = 'Draw Irrigation Channel'
    bl_options = {'REGISTER', 'UNDO'}

    def _finish_modal(self, props):
        self._pts = []
        _draw_callback_irrigation._current_chain = []
        props.irr_drawing_active = False
        unregister_irr_draw_handler()

    def modal(self, context, event):
        if not lifecycle.is_active():
            return {'CANCELLED'}
        props = context.scene.dsg_props
        _draw_callback_irrigation._current_chain = self._pts
        if context.area:
            context.area.tag_redraw()

        if event.type in {'RIGHTMOUSE', 'ESC'} and event.value == 'PRESS':
            built = len(self._pts) >= 2 and self._build_preview(context, props)
            self._finish_modal(props)
            if built:
                _dsg_report(self, {'INFO'}, 'Preview created: curve = internal lumen; outer wire = walls.', 'Vista previa creada: curva = lumen interno; malla exterior = paredes.')
                return {'FINISHED'}
            _dsg_report(self, {'INFO'}, 'Irrigation drawing canceled', 'Dibujo de irrigación cancelado')
            return {'CANCELLED'}

        if event.type in {'RET', 'NUMPAD_ENTER', 'SPACE'} and event.value == 'PRESS':
            if len(self._pts) < 2:
                _dsg_report(self, {'WARNING'}, 'At least 2 points are required', 'Necesitas al menos 2 puntos')
                return {'RUNNING_MODAL'}
            built = self._build_preview(context, props)
            self._finish_modal(props)
            return {'FINISHED'} if built else {'CANCELLED'}

        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            if not self._pts:
                loc, _normal = raycast_sleeve_lateral_on_guide(context, event, props)
                if loc is None:
                    _dsg_report(self, {'WARNING'}, 'The first point must touch the curved sleeve wall', 'El primer punto debe tocar la pared curva del cilindro')
                    return {'RUNNING_MODAL'}
                self._active_implant = props.implant_obj if is_valid_implant_obj(props.implant_obj) else None
                self._pts.append(loc)
                _dsg_report(self, {'INFO'}, 'Contact detected. Add the internal path points toward the outside.', 'Contacto detectado. Añade los puntos del eje interno hacia el exterior.')
            else:
                air_loc = point_in_view_plane(context, event, self._pts[-1])
                if air_loc is None:
                    _dsg_report(self, {'WARNING'}, 'Could not place the point from this view', 'No se pudo colocar el punto desde esta vista')
                    return {'RUNNING_MODAL'}
                self._pts.append(air_loc)
            _draw_callback_irrigation._current_chain = self._pts
            return {'RUNNING_MODAL'}

        if event.type == 'Z' and event.ctrl and event.value == 'PRESS':
            if self._pts:
                self._pts.pop()
                _draw_callback_irrigation._current_chain = self._pts
            return {'RUNNING_MODAL'}

        if event.type in {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE',
                          'NUMPAD_0', 'NUMPAD_1', 'NUMPAD_2', 'NUMPAD_3',
                          'NUMPAD_4', 'NUMPAD_5', 'NUMPAD_6', 'NUMPAD_7',
                          'NUMPAD_8', 'NUMPAD_9'}:
            return {'PASS_THROUGH'}
        return {'RUNNING_MODAL'}

    def _build_preview(self, context, props):
        implant = getattr(self, '_active_implant', None)
        ok, message = build_irrigation_preview_from_points(
            context, props, self._pts, implant=implant)
        if not ok:
            _dsg_report(self, {'ERROR'}, message, message)
        else:
            _dsg_report(
                self, {'INFO'},
                'The thick curve represents the internal channel. Edit its points and update the walls.',
                'La curva gruesa representa el conducto interno. Edita sus puntos y actualiza las paredes.')
        return bool(ok)

    def invoke(self, context, event):
        if not _require_workflow_stage(
                self, context, STEP_IRRIGATION,
                action_en='Cannot draw an irrigation channel',
                action_es='No se puede dibujar un conducto de irrigación'):
            return {'CANCELLED'}
        props = context.scene.dsg_props
        activate_precision_orthographic(context)
        props.irr_bevel_resolution = 8
        if not _valid_obj(props.guide_obj):
            _dsg_report(self, {'ERROR'}, 'Create the sleeves first', 'Genera los cilindros primero')
            return {'CANCELLED'}
        if get_pending_irrigation_preview(props):
            _dsg_report(self, {'WARNING'}, 'Confirm or discard the pending preview', 'Confirma o descarta la vista previa pendiente')
            return {'CANCELLED'}
        if not is_valid_implant_obj(props.implant_obj):
            implants = get_all_implant_objects(props)
            props.implant_obj = implants[-1] if implants else None
        if not is_valid_implant_obj(props.implant_obj):
            _dsg_report(self, {'ERROR'}, 'Active implant/sleeve not found', 'No se encontró el implante/cilindro activo')
            return {'CANCELLED'}

        self._pts = []
        self._active_implant = props.implant_obj
        props.irr_drawing_active = True
        _draw_callback_irrigation._current_chain = []
        register_irr_draw_handler()
        context.window_manager.modal_handler_add(self)
        _dsg_report(self, {'INFO'}, 'First click on the sleeve; place the remaining path points in space; press Enter to confirm the preview', '1er clic en cilindro; resto del eje en el aire; Enter confirma la vista previa')
        return {'RUNNING_MODAL'}


class DSG_OT_UpdateIrrigationPreview(Operator):
    bl_idname = 'dsg.update_irrigation_preview'
    bl_label = 'Update Walls from Path'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.dsg_props
        props.irr_bevel_resolution = 8
        preview = get_pending_irrigation_preview(props)
        if not _valid_obj(preview):
            _dsg_report(self, {'ERROR'}, 'There is no pending preview', 'No hay vista previa pendiente')
            return {'CANCELLED'}

        controls = get_irrigation_preview_path_world(preview)
        if len(controls) < 3:
            _dsg_report(self, {'ERROR'}, 'The path requires at least an internal point, a contact point, and an outlet', 'El eje necesita al menos punto profundo, contacto y salida')
            return {'CANCELLED'}
        implant = bpy.data.objects.get(str(preview.get('DSG_implant', '')))
        if not is_valid_implant_obj(implant):
            implant = get_nearest_implant_to_point(props, controls[1])
        if not is_valid_implant_obj(implant):
            _dsg_report(self, {'ERROR'}, 'Associated sleeve not found', 'No se encontró el cilindro asociado')
            return {'CANCELLED'}

        curve_obj = get_irrigation_preview_curve(preview)
        name = preview.name
        parameters = capture_irrigation_parameters(props)
        preview_props = irrigation_props_overlay(props, parameters)
        safe_remove_object(preview)
        rebuilt = build_irrigation_outer_wall_object(
            context, controls, preview_props, implant_obj=implant,
            name=name, show_wire=True)
        if not _valid_obj(rebuilt):
            _dsg_report(self, {'ERROR'}, 'Could not rebuild the walls', 'No se pudieron regenerar las paredes')
            return {'CANCELLED'}
        register_dsg_object(rebuilt, ROLE_IRRIGATION, name, {
            'DSG_implant': implant.name,
            'DSG_irrigation_preview': True,
            'DSG_preview_curve': curve_obj.name if _valid_obj(curve_obj) else '',
            'DSG_irrigation_params': json.dumps(parameters),
        })
        rebuilt.display_type = 'WIRE'
        rebuilt.show_in_front = True
        props.irr_preview_obj = rebuilt
        set_active(context, curve_obj or rebuilt)
        _dsg_report(self, {'INFO'}, 'Walls updated around the internal path', 'Paredes actualizadas alrededor del eje interno')
        return {'FINISHED'}


class DSG_OT_ShowExactIrrigationLumenDiagnostic(Operator):
    bl_idname = 'dsg.show_exact_irrigation_lumen_diagnostic'
    bl_label = 'Show Checked Water Lumen'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.dsg_props
        preview = get_pending_irrigation_preview(props)
        if not _valid_obj(preview):
            _dsg_report(self, {'ERROR'}, 'There is no pending irrigation preview', 'No hay vista previa pendiente de irrigación')
            return {'CANCELLED'}

        controls = get_irrigation_preview_path_world(preview)
        if len(controls) < 3:
            _dsg_report(self, {'ERROR'}, 'The internal path is invalid', 'El eje interno no es válido')
            return {'CANCELLED'}

        implant = bpy.data.objects.get(str(preview.get('DSG_implant', '')))
        if not is_valid_implant_obj(implant):
            implant = get_nearest_implant_to_point(props, controls[1])
        parameters = irrigation_parameters_from_object(preview, props)
        preview_entry = {
            'points': [Vector(point) for point in controls],
            'implant': implant if is_valid_implant_obj(implant) else None,
            'implant_name': _safe_object_name(implant),
            'parameters': parameters,
            'index': int(getattr(props, 'irr_chain_count', 0)),
            'link': False,
        }
        safe_model, model_message, _model_data = irrigation_model_cut_preflight(
            context, preview_entry, props, get_passive_model_obj(),
            label=f'conducto {props.irr_chain_count + 1}')
        obj, error = create_irrigation_lumen_diagnostic_object(
            context, preview_entry, props, blocked=not safe_model,
            name=IRR_LUMEN_DIAGNOSTIC_NAME)
        if not _valid_obj(obj):
            _dsg_report(self, {'ERROR'}, error or 'Could not create the checked lumen', error or 'No se pudo crear el lumen comprobado')
            return {'CANCELLED'}
        try:
            preview['DSG_lumen_diagnostic'] = obj.name
            obj['DSG_preview_source'] = preview.name
            obj['DSG_model_channel_preflight'] = model_message
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        if safe_model:
            _dsg_report(
                self, {'INFO'},
                'Checked water lumen shown in yellow: no model invasion detected.',
                'Lumen real comprobado visible en amarillo: no se detecta invasión del modelo.')
        else:
            _dsg_report(
                self, {'WARNING'},
                'Checked water lumen shown in red: it is the exact geometry that triggered the block.',
                'Lumen real comprobado visible en rojo: esta es la geometría exacta que produjo el bloqueo.')
        return {'FINISHED'}


class DSG_OT_ConfirmIrrigationPreview(Operator):
    bl_idname = 'dsg.confirm_irrigation_preview'
    bl_label = 'Confirm'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if not _require_workflow_stage(
                self, context, STEP_IRRIGATION,
                action_en='Cannot confirm the irrigation channel',
                action_es='No se puede confirmar el conducto de irrigación'):
            return {'CANCELLED'}
        props = context.scene.dsg_props
        props.irr_bevel_resolution = 8
        preview = get_pending_irrigation_preview(props)
        if not _valid_obj(preview):
            _dsg_report(self, {'ERROR'}, 'There is no pending preview', 'No hay vista previa pendiente')
            return {'CANCELLED'}

        controls = get_irrigation_preview_path_world(preview)
        if len(controls) < 3:
            _dsg_report(self, {'ERROR'}, 'The internal path is invalid', 'El eje interno no es válido')
            return {'CANCELLED'}
        implant = bpy.data.objects.get(str(preview.get('DSG_implant', '')))
        if not is_valid_implant_obj(implant):
            implant = get_nearest_implant_to_point(props, controls[1])
        if not is_valid_implant_obj(implant):
            _dsg_report(self, {'ERROR'}, 'Associated sleeve not found', 'No se encontró el cilindro asociado')
            return {'CANCELLED'}

        wall_name = f'{IRR_WALL_PREFIX}{props.irr_chain_count:02d}'
        safe_remove_by_name(wall_name)
        parameters = irrigation_parameters_from_object(preview, props)

        preview_entry = {
            'points': [Vector(point) for point in controls],
            'implant': implant,
            'implant_name': _safe_object_name(implant),
            'parameters': parameters,
            'index': int(props.irr_chain_count),
            'link': False,
        }
        safe_model, model_message, model_data = irrigation_model_cut_preflight(
            context, preview_entry, props, get_passive_model_obj(),
            label=f'conducto {props.irr_chain_count + 1}')
        if not safe_model:
            # Mostrar automáticamente la geometría exacta que ha usado el cálculo.
            # Si este objeto rojo toca el diente/modelo, el bloqueo es correcto;
            # si no lo toca, el cálculo está reconstruyendo otro trayecto.
            try:
                obj, _error = create_irrigation_lumen_diagnostic_object(
                    context, preview_entry, props, blocked=True,
                    name=IRR_LUMEN_DIAGNOSTIC_NAME)
                if _valid_obj(obj):
                    preview['DSG_lumen_diagnostic'] = obj.name
                    obj['DSG_preview_source'] = preview.name
                    obj['DSG_model_channel_preflight'] = model_message
            except Exception as diag_exc:
                print(f'[DSG] Could not show checked irrigation lumen diagnostic: {diag_exc}')
            _dsg_report(
                self, {'ERROR'},
                'This irrigation path is not possible here: ' + model_message,
                'No es posible usar esta irrigación aquí: ' + model_message)
            return {'CANCELLED'}

        wall_props = irrigation_props_overlay(props, parameters)
        wall = build_irrigation_outer_wall_object(
            context, controls, wall_props, implant_obj=implant,
            name=wall_name, show_wire=False)
        if not _valid_obj(wall):
            _dsg_report(self, {'ERROR'}, 'Could not create the final wall', 'No se pudo generar la pared definitiva')
            return {'CANCELLED'}

        register_dsg_object(wall, ROLE_IRRIGATION, wall_name, {
            'DSG_implant': implant.name,
            'DSG_irrigation_wall_confirmed': True,
            'DSG_centerline_controls': json.dumps([list(Vector(point)) for point in controls]),
            'DSG_irrigation_params': json.dumps(parameters),
            'DSG_irrigation_index': int(props.irr_chain_count),
            'DSG_model_channel_preflight': model_message,
            'DSG_model_channel_preflight_data': json.dumps(model_data),
        })
        wall.display_type = 'SOLID'
        wall.show_in_front = False
        store_irrigation_path(props, controls, implant, parameters=parameters)

        remove_irrigation_preview_bundle(preview, remove_curve=True)
        props.irr_preview_obj = None
        props.irr_chain_count += 1
        set_active(context, wall)
        _dsg_report(self, {'INFO'}, 'Wall confirmed without a Boolean. The lumen will be cut once at the end.', 'Pared confirmada sin Boolean. El corte del lumen se hará una sola vez al final.')
        return {'FINISHED'}


class DSG_OT_UpdateConfirmIrrigation(Operator):
    bl_idname = 'dsg.update_confirm_irrigation'
    bl_label = 'Confirm'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if core.reject_external_agent_for_user_gate(self, action=self.bl_idname):
            return {'CANCELLED'}
        props = context.scene.dsg_props
        props.irr_bevel_resolution = 8

        result = bpy.ops.dsg.update_irrigation_preview('EXEC_DEFAULT')
        if 'FINISHED' not in result:
            _dsg_report(self, {'ERROR'}, 'Could not update the walls', 'No se pudieron actualizar las paredes')
            return {'CANCELLED'}

        result = bpy.ops.dsg.confirm_irrigation_preview('EXEC_DEFAULT')
        if 'FINISHED' not in result:
            _dsg_report(self, {'ERROR'}, 'Walls were updated but could not be confirmed', 'Las paredes se actualizaron, pero no pudieron confirmarse')
            return {'CANCELLED'}

        _dsg_report(self, {'INFO'}, 'Walls updated and confirmed', 'Paredes actualizadas y confirmadas')
        return {'FINISHED'}


def _closest_point_on_segment(point, start, end):
    point = Vector(point)
    start = Vector(start)
    end = Vector(end)
    segment = end - start
    length_sq = segment.length_squared
    if length_sq < 1e-12:
        return start.copy(), 0.0
    factor = max(0.0, min(1.0, (point - start).dot(segment) / length_sq))
    return start + segment * factor, factor


def _closest_point_tangent_on_irrigation_entry(point, entry, props):
    points = [Vector(p) for p in entry.get('points', [])]
    if not points:
        return None, None, float('inf')
    entry_props = irrigation_props_overlay(props, entry.get('parameters', {}))
    centerline = smooth_irrigation_centerline_controls(points, entry_props)
    if len(centerline) < 2:
        centerline = points
    if len(centerline) == 1:
        return centerline[0].copy(), Vector((0.0, 0.0, 1.0)), (Vector(point) - centerline[0]).length

    best_point = None
    best_tangent = None
    best_distance = float('inf')
    for start, end in zip(centerline[:-1], centerline[1:]):
        candidate, _factor = _closest_point_on_segment(point, start, end)
        segment = Vector(end) - Vector(start)
        if segment.length < 1e-8:
            continue
        distance = (Vector(point) - candidate).length
        if distance < best_distance:
            best_point = candidate
            best_tangent = segment.normalized()  # sleeve -> external water inlet
            best_distance = distance
    return best_point, best_tangent, best_distance


def _closest_point_on_irrigation_entry(point, entry):
    points = [Vector(p) for p in entry.get('points', [])]
    if not points:
        return None, float('inf')
    if len(points) == 1:
        return points[0].copy(), (Vector(point) - points[0]).length
    best_point = None
    best_distance = float('inf')
    for start, end in zip(points[:-1], points[1:]):
        candidate, _factor = _closest_point_on_segment(point, start, end)
        distance = (Vector(point) - candidate).length
        if distance < best_distance:
            best_point = candidate
            best_distance = distance
    return best_point, best_distance


def _find_irrigation_entry_by_index(entries, source_index):
    try:
        source_index = int(source_index)
    except Exception:
        return None
    for entry in entries:
        try:
            if int(entry.get('index', -1)) == source_index:
                return entry
        except Exception:
            continue
    return None


def _implant_has_irrigation_entry(entries, implant_obj):
    if not is_valid_implant_obj(implant_obj):
        return False
    for entry in entries:
        source = entry.get('implant')
        source_name = entry.get('implant_name')
        if source is implant_obj or source_name == implant_obj.name:
            return True
    return False


def _remove_irrigation_link_markers():
    for obj in list(bpy.data.objects):
        try:
            if obj.name.startswith(IRR_LINK_MARKER_PREFIX):
                safe_remove_object(obj)
        except (ReferenceError, RuntimeError):
            continue


def _create_irrigation_link_marker(context, location, index):
    name = f'{IRR_LINK_MARKER_PREFIX}{int(index):02d}'
    safe_remove_by_name(name)
    mesh = make_uv_sphere_mesh(name + '_Mesh', 0.48, 16, 8)
    marker = bpy.data.objects.new(name, mesh)
    marker.location = Vector(location)
    link_object(context, marker)
    register_dsg_object(marker, ROLE_IRRIGATION, name, {
        'DSG_irrigation_link_marker': True,
        'DSG_irrigation_link_marker_index': int(index),
    })
    marker.display_type = 'WIRE'
    marker.show_in_front = True
    marker.hide_render = True
    return marker


def _raycast_confirmed_irrigation_wall(context, event):
    """Returns the confirmed irrigation wall directly clicked by the user."""
    walls = get_confirmed_irrigation_walls()
    if not walls or context.region is None or context.region_data is None:
        return None, None, None

    try:
        coord = (event.mouse_region_x, event.mouse_region_y)
        ray_origin = view3d_utils.region_2d_to_origin_3d(
            context.region, context.region_data, coord)
    except Exception:
        ray_origin = None

    best = None
    best_distance = float('inf')
    for wall in walls:
        try:
            if wall.hide_viewport or wall.hide_get():
                continue
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        location, normal, _face = do_raycast_detailed(context, event, wall)
        if location is None:
            continue
        distance = (Vector(location) - Vector(ray_origin)).length if ray_origin is not None else 0.0
        if best is None or distance < best_distance:
            best = (Vector(location), Vector(normal) if normal is not None else None, wall)
            best_distance = distance
    return best if best is not None else (None, None, None)



def _build_irrigation_link_controls_from_points(
        props, target_implant, sleeve_point, source_point, source_tangent, entry_props):
    """Creates an adaptive Y from scratch around the selected source region.

    A pair of symmetric daughter shoulders is generated first.  Their midpoint
    defines the hydraulic center; the split is moved slightly upstream from that
    midpoint so both daughters retain a forward component.  The common inlet is
    then bent into this center.  This is a genuine Y, never a preserved straight
    channel with a side attachment.
    """
    anchor_world = Vector(sleeve_point)
    source_center = Vector(source_point)
    trunk_dir = Vector(source_tangent) if source_tangent is not None else Vector((0.0, 0.0, 1.0))
    if trunk_dir.length < 1e-8:
        return [], {}, 'Could not determine the source channel direction', 'No se pudo determinar la dirección del canal principal'
    trunk_dir.normalize()                         # source sleeve -> inlet
    flow_out = -trunk_dir                         # inlet -> source sleeve

    bridge = anchor_world - source_center
    bridge_length = bridge.length
    if bridge_length < 1.20:
        return [], {}, 'The selected sleeve is too close to build a stable Y', 'El sleeve seleccionado está demasiado cerca para construir una Y estable'
    to_link = bridge.normalized()

    lateral = to_link - trunk_dir * to_link.dot(trunk_dir)
    if lateral.length < 1e-8:
        basis_u, _basis_v, _axis = build_axis_basis(trunk_dir)
        lateral = basis_u
    lateral.normalize()

    # Adapt the daughter angle to the actual target position.  Shallow links get
    # a compact Y; lateral targets get a wider but still printable manifold.
    dot_value = max(-1.0, min(1.0, flow_out.dot(to_link)))
    raw_angle = math.degrees(math.acos(dot_value))
    branch_angle_deg = max(24.0, min(38.0, raw_angle * 0.55 + 14.0))
    angle = math.radians(branch_angle_deg)

    daughter_run = max(1.45, min(2.40, 1.35 + bridge_length * 0.10))
    common_run = max(0.90, min(1.55, 0.82 + bridge_length * 0.055))
    main_dir = (flow_out * math.cos(angle) - lateral * math.sin(angle)).normalized()
    link_dir = (flow_out * math.cos(angle) + lateral * math.sin(angle)).normalized()

    main_shoulder = source_center + main_dir * daughter_run
    link_shoulder = source_center + link_dir * daughter_run
    branch_midpoint = (main_shoulder + link_shoulder) * 0.5
    bisector = main_dir + link_dir
    if bisector.length < 1e-8:
        bisector = flow_out
    bisector.normalize()

    # Moving upstream from the exact shoulder midpoint keeps both branches
    # directed forward instead of creating a transverse T.
    split_backoff = daughter_run * 0.72
    split_center = branch_midpoint - bisector * split_backoff
    common_anchor = source_center + trunk_dir * common_run
    main_rejoin = source_center + flow_out * max(2.00, daughter_run * 1.35)

    # The linked path is generated from the sleeve to its new daughter shoulder
    # and terminates exactly at the shared split center.
    remote_mid = anchor_world.lerp(link_shoulder, 0.52)
    pre_shoulder = anchor_world.lerp(link_shoulder, 0.82)
    raw_points = [
        anchor_world,
        remote_mid,
        pre_shoulder,
        link_shoulder,
        split_center,
    ]
    controls = build_irrigation_initial_control_points(
        raw_points, entry_props, target_implant)
    if len(controls) < 5:
        return [], {}, 'Could not build the adaptive midpoint Y path', 'No se pudo construir la trayectoria adaptativa en Y'

    connection = {
        'geometry_mode': 'ADAPTIVE_MIDPOINT_MANIFOLD',
        'manifold_center': split_center,
        'split_center': split_center,
        'source_channel_point': source_center,
        'trunk_direction': trunk_dir,
        'source_tangent': trunk_dir,
        'lateral': lateral,
        'branch_direction': link_dir,
        'branch_angle_deg': branch_angle_deg,
        'approach_point': common_anchor,
        'common_anchor': common_anchor,
        'main_rejoin': main_rejoin,
        'main_shoulder': main_shoulder,
        'link_shoulder': link_shoulder,
        'link_rejoin': link_shoulder,
        'branch_midpoint': branch_midpoint,
        'manifold_radius': 0.55,
    }
    return controls, connection, '', ''



def build_irrigation_link_y_parts(context, entry, name_prefix='DSG_IrrLinkY'):
    """Builds the explicit curved three-leg lumen used for diagnostics/fallback."""
    if not bool(entry.get('link', False)):
        return []
    meta = _midpoint_wye_metadata(entry)
    if meta is None:
        return []

    parts = []
    sphere_mesh = make_uv_sphere_mesh(
        name_prefix + '_Plenum_Mesh', meta['plenum_radius'], 24, 12)
    sphere = bpy.data.objects.new(name_prefix + '_Plenum', sphere_mesh)
    sphere.location = meta['split']
    link_object(context, sphere)
    sphere.display_type = 'WIRE'
    sphere.show_in_front = True
    parts.append(sphere)

    paths = {
        'Common': _sample_cubic_bezier_segment(
            meta['split'],
            meta['split'].lerp(meta['common_anchor'], 0.28),
            meta['split'].lerp(meta['common_anchor'], 0.72),
            meta['common_anchor'], max_step=0.14),
        'Main': _sample_cubic_bezier_segment(
            meta['split'], meta['main_shoulder'],
            meta['main_shoulder'].lerp(meta['main_rejoin'], 0.55),
            meta['main_rejoin'], max_step=0.14),
        'Link': _sample_cubic_bezier_segment(
            meta['split'], meta['link_shoulder'],
            meta['link_shoulder'].lerp(meta['link_rejoin'], 0.55),
            meta['link_rejoin'], max_step=0.14),
    }
    for suffix, path in paths.items():
        samples = [(Vector(point), 0.53) for point in path]
        obj = build_variable_radius_tube_object(
            context, f'{name_prefix}_{suffix}', samples,
            bevel_resolution=8, show_wire=True, subdiv_levels=0)
        if _valid_obj(obj):
            obj.show_in_front = True
            parts.append(obj)
    return parts


def commit_irrigation_link(context, props, target_implant, sleeve_point,
                           source_entry, source_point):
    """Create one Link branch (UI-agnostic).

    Returns ``(ok, message_en, message_es)``. Used by the two-click Link tool
    and by "Link selected" (automatic placement).
    """
    parameters = dict(
        source_entry.get('parameters') or capture_irrigation_parameters(props))
    # A linked implant has no independent external 4 mm inlet.  Keep its
    # daughter branch continuously at 1.00 mm and let the common source
    # channel provide the external inlet.  Expanding the Link branch to the
    # source inlet diameter can invade the sleeve C manifold and produce a
    # false wall/obstruction after the final assembly.
    parameters['irr_inner_diameter'] = 1.0
    parameters['irr_funnel_outer_diameter'] = 1.0
    parameters['irr_taper_length'] = 0.0
    parameters['irr_funnel_enabled'] = True
    parameters['irr_link_continuous_1mm'] = True
    parameters['irr_link_preserve_full_lumen'] = False
    entry_props = irrigation_props_overlay(props, parameters)
    controls, y_geometry, error_en, error_es = _build_irrigation_link_controls_from_points(
        props, target_implant, sleeve_point, source_point, source_entry.get('link_source_tangent'), entry_props)
    if not controls:
        return False, error_en, error_es

    link_index = int(props.irr_chain_count)
    wall_name = f'{IRR_WALL_PREFIX}{link_index:02d}'
    safe_remove_by_name(wall_name)
    wall = build_irrigation_outer_wall_object(
        context,
        controls,
        entry_props,
        implant_obj=target_implant,
        name=wall_name,
        show_wire=False,
    )
    if not _valid_obj(wall):
        return False, 'Could not create the irrigation link', 'No se pudo crear la conexión de irrigación'

    try:
        data = json.loads(props.irr_paths_json or '[]')
        if not isinstance(data, list):
            data = []
    except Exception:
        data = []

    source_index = int(source_entry.get('index', 0))
    data.append({
        'implant': target_implant.name,
        'points': [[float(p.x), float(p.y), float(p.z)] for p in controls],
        'parameters': parameters,
        'index': link_index,
        'link': True,
        'source_index': source_index,
        'link_sleeve_point': [float(v) for v in Vector(sleeve_point)],
        'link_channel_point': [float(v) for v in Vector(source_point)],
        'link_manifold_center': [float(v) for v in y_geometry['manifold_center']],
        'link_elbow_center': [float(v) for v in y_geometry['split_center']],
        'link_split_center': [float(v) for v in y_geometry['split_center']],
        'link_side_chamber_center': [float(v) for v in y_geometry['split_center']],
        'link_channel_point': [float(v) for v in y_geometry['source_channel_point']],
        'link_source_tangent': [float(v) for v in y_geometry['source_tangent']],
        'link_trunk_direction': [float(v) for v in y_geometry['trunk_direction']],
        'link_lateral': [float(v) for v in y_geometry['lateral']],
        'link_geometry_mode': str(y_geometry.get('geometry_mode', 'ADAPTIVE_MIDPOINT_MANIFOLD')),
        'link_branch_angle_deg': float(y_geometry.get('branch_angle_deg', 30.0)),
        'link_split_point': [float(v) for v in y_geometry['split_center']],
        'link_trunk_point': [float(v) for v in y_geometry['common_anchor']],
        'link_source_shoulder': [float(v) for v in y_geometry['main_shoulder']],
        'link_source_rejoin': [float(v) for v in y_geometry['main_rejoin']],
        'link_common_anchor': [float(v) for v in y_geometry['common_anchor']],
        'link_main_rejoin': [float(v) for v in y_geometry['main_rejoin']],
        'link_main_shoulder': [float(v) for v in y_geometry['main_shoulder']],
        'link_link_shoulder': [float(v) for v in y_geometry['link_shoulder']],
        'link_link_rejoin': [float(v) for v in y_geometry['link_rejoin']],
        'link_branch_midpoint': [float(v) for v in y_geometry['branch_midpoint']],
        'link_plenum_radius': float(y_geometry.get('manifold_radius', 0.55)),
    })
    props.irr_paths_json = json.dumps(data)

    register_dsg_object(wall, ROLE_IRRIGATION, wall_name, {
        'DSG_implant': target_implant.name,
        'DSG_irrigation_wall_confirmed': True,
        'DSG_centerline_controls': json.dumps(
            [list(Vector(point)) for point in controls]),
        'DSG_irrigation_params': json.dumps(parameters),
        'DSG_irrigation_index': link_index,
        'DSG_irrigation_link': True,
        'DSG_irrigation_source_index': source_index,
        'DSG_irrigation_link_sleeve_point': json.dumps(
            list(Vector(sleeve_point))),
        'DSG_irrigation_link_channel_point': json.dumps(
            list(Vector(source_point))),
        'DSG_irrigation_link_y': True,
        'DSG_irrigation_link_diameter': float(parameters.get('irr_inner_diameter', 1.0)),
        'DSG_irrigation_link_split_point': json.dumps(list(y_geometry['split_center'])),
        'DSG_irrigation_link_trunk_point': json.dumps(list(y_geometry['approach_point'])),
        'DSG_irrigation_link_source_shoulder': json.dumps(list(y_geometry['source_channel_point'])),
        'DSG_irrigation_link_source_rejoin': json.dumps(list(y_geometry['source_channel_point'])),
        'DSG_irrigation_link_manifold_center': json.dumps(list(y_geometry['manifold_center'])),
        'DSG_irrigation_link_elbow_center': json.dumps(list(y_geometry['split_center'])),
        'DSG_irrigation_link_split_center': json.dumps(list(y_geometry['split_center'])),
        'DSG_irrigation_link_side_chamber_center': json.dumps(list(y_geometry['split_center'])),
        'DSG_irrigation_link_channel_point': json.dumps(list(y_geometry['source_channel_point'])),
        'DSG_irrigation_link_source_tangent': json.dumps(list(y_geometry['source_tangent'])),
        'DSG_irrigation_link_trunk_direction': json.dumps(list(y_geometry['trunk_direction'])),
        'DSG_irrigation_link_lateral': json.dumps(list(y_geometry['lateral'])),
        'DSG_irrigation_link_geometry_mode': str(y_geometry.get('geometry_mode', 'ADAPTIVE_MIDPOINT_MANIFOLD')),
        'DSG_irrigation_link_branch_angle_deg': float(y_geometry.get('branch_angle_deg', 30.0)),
        'DSG_irrigation_link_common_anchor': json.dumps(list(y_geometry['common_anchor'])),
        'DSG_irrigation_link_main_rejoin': json.dumps(list(y_geometry['main_rejoin'])),
        'DSG_irrigation_link_main_shoulder': json.dumps(list(y_geometry['main_shoulder'])),
        'DSG_irrigation_link_link_shoulder': json.dumps(list(y_geometry['link_shoulder'])),
        'DSG_irrigation_link_link_rejoin': json.dumps(list(y_geometry['link_rejoin'])),
        'DSG_irrigation_link_branch_midpoint': json.dumps(list(y_geometry['branch_midpoint'])),
        'DSG_irrigation_link_plenum_radius': float(y_geometry.get('manifold_radius', 0.55)),
    })
    wall.display_type = 'SOLID'
    wall.show_in_front = False
    props.irr_chain_count = len(data)
    set_active(context, wall)

    # Sequential opening: initial sleeve open, linked sleeves frangible + ordered.
    auto_assign_irrigation_gate_defaults(props)
    return (True,
            f'Sleeve linked to irrigation channel {source_index + 1}',
            f'Cilindro conectado al canal de irrigación {source_index + 1}')


class DSG_OT_LinkIrrigation(Operator):
    bl_idname = 'dsg.link_irrigation'
    bl_label = 'Link'
    bl_description = (
        'Select two points: first on the source sleeve and second on the existing '
        'irrigation channel / Selecciona dos puntos: primero sobre el sleeve de '
        'origen y después sobre el canal de irrigación existente'
    )
    bl_options = {'REGISTER', 'UNDO'}

    def _finish(self, context):
        _remove_irrigation_link_markers()
        self._stage = 0
        self._sleeve_point = None
        self._target_implant = None
        if context.area:
            context.area.tag_redraw()

    def _cancel(self, context, message_en=None, message_es=None):
        self._finish(context)
        if message_en:
            _dsg_report(self, {'INFO'}, message_en, message_es or message_en)
        return {'CANCELLED'}

    def _commit_link(self, context, props, target_implant, sleeve_point,
                     source_entry, source_point):
        ok, message_en, message_es = commit_irrigation_link(
            context, props, target_implant, sleeve_point, source_entry, source_point)
        _dsg_report(self, {'INFO'} if ok else {'ERROR'}, message_en, message_es)
        return ok

    def modal(self, context, event):
        if not lifecycle.is_active():
            return {'CANCELLED'}
        props = context.scene.dsg_props
        if context.area:
            context.area.tag_redraw()

        if event.type in {'RIGHTMOUSE', 'ESC'} and event.value == 'PRESS':
            return self._cancel(
                context,
                'Irrigation link canceled',
                'Conexión de irrigación cancelada')

        if event.type == 'Z' and event.ctrl and event.value == 'PRESS':
            if self._stage == 1:
                _remove_irrigation_link_markers()
                self._stage = 0
                self._sleeve_point = None
                self._target_implant = None
                _dsg_report(
                    self, {'INFO'},
                    'First point removed. Select the sleeve again.',
                    'Primer punto eliminado. Selecciona de nuevo el sleeve.')
            return {'RUNNING_MODAL'}

        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            entries = load_irrigation_path_entries(props)

            if self._stage == 0:
                location, _normal = raycast_sleeve_lateral_on_guide(
                    context, event, props)
                target_implant = props.implant_obj
                if location is None or not is_valid_implant_obj(target_implant):
                    _dsg_report(
                        self, {'WARNING'},
                        'The first point must be placed on the curved wall of a sleeve',
                        'El primer punto debe colocarse sobre la pared curva de un sleeve')
                    return {'RUNNING_MODAL'}
                if _implant_has_irrigation_entry(entries, target_implant):
                    _dsg_report(
                        self, {'WARNING'},
                        'This sleeve already has an irrigation channel or link',
                        'Este sleeve ya tiene un canal o una conexión de irrigación')
                    return {'RUNNING_MODAL'}

                self._sleeve_point = Vector(location)
                self._target_implant = target_implant
                self._stage = 1
                _create_irrigation_link_marker(context, self._sleeve_point, 1)
                _dsg_report(
                    self, {'INFO'},
                    'Sleeve selected. Now click the existing irrigation channel.',
                    'Cilindro seleccionado. Ahora haz clic sobre el canal de irrigación existente.')
                return {'RUNNING_MODAL'}

            hit_location, _normal, source_wall = _raycast_confirmed_irrigation_wall(
                context, event)
            if hit_location is None or not _valid_obj(source_wall):
                _dsg_report(
                    self, {'WARNING'},
                    'The second point must be placed on a confirmed irrigation channel',
                    'El segundo punto debe colocarse sobre un canal de irrigación confirmado')
                return {'RUNNING_MODAL'}

            source_index = int(source_wall.get('DSG_irrigation_index', -1))
            source_entry = _find_irrigation_entry_by_index(entries, source_index)
            if source_entry is None:
                _dsg_report(
                    self, {'ERROR'},
                    'The selected irrigation channel has no saved path',
                    'El canal de irrigación seleccionado no tiene una trayectoria guardada')
                return {'RUNNING_MODAL'}

            if bool(source_entry.get('link', False)):
                # A Link of a Link is never assembled by Apply Irrigation (only
                # links whose source is a main channel form a Y network), so the
                # branch would silently disappear. Attach to the main trunk.
                trunk_entry = _find_irrigation_entry_by_index(
                    entries, int(source_entry.get('source_index', -1)))
                if trunk_entry is None or bool(trunk_entry.get('link', False)):
                    _dsg_report(
                        self, {'WARNING'},
                        'Click the main irrigation channel',
                        'Haz clic sobre el conducto principal de irrigación')
                    return {'RUNNING_MODAL'}
                source_entry = trunk_entry
                _dsg_report(
                    self, {'INFO'},
                    'Linked to the main channel (branches always join the main trunk)',
                    'Vinculado al conducto principal (las ramas siempre se unen al tronco)')

            source_implant = source_entry.get('implant')
            if source_implant is self._target_implant:
                _dsg_report(
                    self, {'WARNING'},
                    'Select an irrigation channel belonging to another sleeve',
                    'Selecciona un canal de irrigación perteneciente a otro sleeve')
                return {'RUNNING_MODAL'}

            # The click identifies the exact channel. The actual junction is
            # projected to that channel's saved centerline so both lumens meet.
            source_point, source_tangent, distance = _closest_point_tangent_on_irrigation_entry(
                hit_location, source_entry, props)
            if source_point is None or source_tangent is None:
                _dsg_report(
                    self, {'ERROR'},
                    'Could not locate the selected point on the irrigation channel',
                    'No se pudo localizar el punto seleccionado en el canal de irrigación')
                return {'RUNNING_MODAL'}

            source_entry = dict(source_entry)
            source_entry['link_source_tangent'] = Vector(source_tangent)
            _create_irrigation_link_marker(context, source_point, 2)
            created = self._commit_link(
                context, props, self._target_implant, self._sleeve_point,
                source_entry, source_point)
            self._finish(context)
            return {'FINISHED'} if created else {'CANCELLED'}

        if event.type in {
                'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE',
                'NUMPAD_0', 'NUMPAD_1', 'NUMPAD_2', 'NUMPAD_3',
                'NUMPAD_4', 'NUMPAD_5', 'NUMPAD_6', 'NUMPAD_7',
                'NUMPAD_8', 'NUMPAD_9'}:
            return {'PASS_THROUGH'}
        return {'RUNNING_MODAL'}

    def invoke(self, context, event):
        props = context.scene.dsg_props
        if get_pending_irrigation_preview(props):
            _dsg_report(
                self, {'ERROR'},
                'Confirm the pending channel first',
                'Confirma primero el conducto pendiente')
            return {'CANCELLED'}

        entries = load_irrigation_path_entries(props)
        walls = get_confirmed_irrigation_walls()
        if not entries or not walls:
            _dsg_report(
                self, {'ERROR'},
                'Create and confirm an irrigation channel first',
                'Crea y confirma primero un canal de irrigación')
            return {'CANCELLED'}

        _remove_irrigation_link_markers()
        self._stage = 0
        self._sleeve_point = None
        self._target_implant = None
        context.window_manager.modal_handler_add(self)
        _dsg_report(
            self, {'INFO'},
            'Select 2 points: first click a sleeve, then click the existing irrigation channel. Esc cancels.',
            'Selecciona 2 puntos: primero haz clic sobre un sleeve y después sobre el canal de irrigación existente. Esc cancela.')
        return {'RUNNING_MODAL'}


class DSG_OT_RemoveLastIrrigation(Operator):
    bl_idname = 'dsg.remove_last_irrigation'
    bl_label = 'Delete'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.dsg_props

        # Si existe un conducto pendiente, ese es el elemento más reciente.
        pending = get_pending_irrigation_preview(props)
        if _valid_obj(pending):
            remove_irrigation_preview_bundle(pending, remove_curve=True)
            props.irr_preview_obj = None
            _dsg_report(self, {'INFO'}, 'Pending irrigation channel deleted', 'Irrigación pendiente eliminada')
            return {'FINISHED'}

        walls = get_confirmed_irrigation_walls()
        try:
            data = json.loads(props.irr_paths_json or '[]')
            if not isinstance(data, list):
                data = []
        except Exception:
            data = []

        if not walls and not data:
            _dsg_report(self, {'WARNING'}, 'There are no irrigation channels to delete', 'No hay irrigaciones para eliminar')
            return {'CANCELLED'}

        last_wall = None
        if walls:
            last_wall = max(
                walls,
                key=lambda obj: int(obj.get('DSG_irrigation_index', -1)))
            safe_remove_object(last_wall)

        if data:
            data.pop()
            for index, entry in enumerate(data):
                if isinstance(entry, dict):
                    entry['index'] = index
            props.irr_paths_json = json.dumps(data)
        else:
            props.irr_paths_json = '[]'

        props.irr_chain_count = len(data)
        auto_assign_irrigation_gate_defaults(props)
        remaining = get_confirmed_irrigation_walls()
        if remaining:
            set_active(context, remaining[-1])
        elif _valid_obj(props.guide_obj):
            set_active(context, props.guide_obj)

        _dsg_report(self, {'INFO'}, 'Last irrigation channel deleted', 'Última irrigación eliminada')
        return {'FINISHED'}


class DSG_OT_CancelIrrigationPreview(Operator):
    bl_idname = 'dsg.cancel_irrigation_preview'
    bl_label = 'Discard Preview'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.dsg_props
        preview = get_pending_irrigation_preview(props)
        if not _valid_obj(preview):
            _dsg_report(self, {'WARNING'}, 'There is no pending preview', 'No hay vista previa pendiente')
            return {'CANCELLED'}
        remove_irrigation_preview_bundle(preview, remove_curve=True)
        props.irr_preview_obj = None
        _dsg_report(self, {'INFO'}, 'Preview discarded', 'Vista previa descartada')
        return {'FINISHED'}


class DSG_OT_SkipIrrigation(Operator):
    bl_idname = 'dsg.skip_irrigation'
    bl_label = 'Skip Irrigation'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if not _require_workflow_stage(
                self, context, STEP_IRRIGATION,
                action_en='Cannot resolve irrigation',
                action_es='No se puede resolver la irrigación'):
            return {'CANCELLED'}
        props = context.scene.dsg_props
        stage_guide = _workflow_guide_candidate(props)
        if not (_valid_obj(stage_guide) and bool(stage_guide.get('DSG_sleeves_applied', False))):
            _dsg_report(self, {'ERROR'}, 'Apply the sleeves before resolving irrigation', 'Aplica los cilindros antes de resolver la irrigación')
            return {'CANCELLED'}

        pending = get_pending_irrigation_preview(props)
        if _valid_obj(pending):
            remove_irrigation_preview_bundle(pending, remove_curve=True)

        for wall in get_confirmed_irrigation_walls():
            safe_remove_object(wall)

        safe_remove_by_prefix('DSG_IrrSingleCut_')
        safe_remove_by_prefix('DSG_IrrWallCut_')
        safe_remove_by_prefix('DSG_IrrWallHollow_')
        safe_remove_by_name(IRR_COMBINED_TMP_NAME)

        props.irr_preview_obj = None
        props.irr_paths_json = '[]'
        props.irr_chain_count = 0
        props.irr_drawing_active = False
        _draw_callback_irrigation._current_chain = []
        unregister_irr_draw_handler()

        guide = _workflow_guide_candidate(props)
        if _valid_obj(guide):
            guide['DSG_irrigation_skipped'] = True
            guide['DSG_irrigation_resolution'] = 'SKIPPED'
        context.scene[WORKFLOW_IRRIGATION_RESOLVED_KEY] = True
        irrigation_signature = _workflow_object_signature(guide)
        if _workflow_signature_changed(context.scene, WORKFLOW_IRRIGATION_SIGNATURE_KEY, irrigation_signature):
            _invalidate_workflow_after(context, STEP_IRRIGATION, reason='irrigation_decision_changed')
        _workflow_store_signature(context.scene, WORKFLOW_IRRIGATION_SIGNATURE_KEY, irrigation_signature)
        prepare_final_cut_references(context, props, show_passive=False)
        props.current_step = STEP_IRRIGATION
        _dsg_report(self, {'INFO'}, 'Irrigation resolved. Lateral access can now be applied before continuing.', 'Irrigación resuelta. Ahora puedes aplicar la apertura lateral antes de continuar.')
        return {'FINISHED'}


def repair_irrigation_open_component(part, max_bad_edges=256):
    """Cierra únicamente bucles abiertos simples antes del Boolean de irrigación.

    Está pensado especialmente para conectores Bézier antiguos creados sin
    tapas. Solo actúa si todas las edges defectuosas son bordes de contorno,
    no hay caras degeneradas y los contornos forman bucles cerrados sin ramas.
    """
    before = get_mesh_solid_report(part, max_polygons=900000)
    if before.get('checked') and before.get('solid'):
        return True, 'the component was already solid', before, 0
    if not before.get('checked'):
        return False, 'component demasiado grande para reparación local', before, 0

    bad_count = int(before.get('bad_edges') or 0)
    degenerate = int(before.get('degenerate_faces') or 0)
    if degenerate or bad_count <= 0 or bad_count > int(max_bad_edges):
        return False, (
            f'repair not applicable: edges={bad_count}, '
            f'degeneradas={degenerate}'), before, 0

    bm = None
    try:
        bm = bmesh.new()
        bm.from_mesh(part.data)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()

        bad_edges = [edge for edge in bm.edges if len(edge.link_faces) != 2]
        boundary = [edge for edge in bad_edges if len(edge.link_faces) == 1]
        if len(boundary) != len(bad_edges) or len(boundary) != bad_count:
            return False, 'there are loose edges or edges with more than two faces', before, 0

        degree = {}
        for edge in boundary:
            for vert in edge.verts:
                degree[vert] = degree.get(vert, 0) + 1
        if not degree or any(value != 2 for value in degree.values()):
            return False, 'los bordes abiertos no forman bucles simples', before, 0

        # Cuenta bucles para el diagnóstico.
        adjacency = {}
        for edge in boundary:
            a, b = edge.verts
            adjacency.setdefault(a, []).append(b)
            adjacency.setdefault(b, []).append(a)
        unvisited = set(adjacency)
        loop_count = 0
        while unvisited:
            loop_count += 1
            stack = [unvisited.pop()]
            while stack:
                vert = stack.pop()
                for neighbour in adjacency.get(vert, ()):
                    if neighbour in unvisited:
                        unvisited.remove(neighbour)
                        stack.append(neighbour)

        result = bmesh.ops.holes_fill(bm, edges=boundary, sides=0)
        new_faces = list(result.get('faces', [])) if isinstance(result, dict) else []
        if not new_faces:
            return False, 'Blender no pudo cerrar los bucles abiertos', before, 0

        if bm.faces:
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
        bm.to_mesh(part.data)
        part.data.validate(clean_customdata=False)
        part.data.update(calc_edges=True)
    except Exception as exc:
        return False, f'local repair failed: {exc}', before, 0
    finally:
        if bm is not None:
            try:
                bm.free()
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)

    after = get_mesh_solid_report(part, max_polygons=900000)
    if after.get('checked') and after.get('solid'):
        try:
            part['DSG_irrigation_preflight_repaired_edges'] = bad_count
            part['DSG_irrigation_preflight_repaired_loops'] = loop_count
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        return True, (
            f'{loop_count} bucle(s) cerrado(s), {bad_count} repaired edges'), after, bad_count
    return False, (
        f'la reparación no dejó el component sólido: '
        f'aristas={after.get("bad_edges", "?")}, '
        f'degeneradas={after.get("degenerate_faces", "?")}'), after, 0




def _irrigation_flow_simulation_objects():
    return [
        obj for obj in list(bpy.data.objects)
        if obj is not None and obj.name.startswith(IRR_FLOW_SIM_PREFIX)
    ]



def clear_irrigation_flow_simulation():
    count = 0
    # Remove old Fluid modifiers from scenes created with previous addon versions.
    for obj in list(bpy.data.objects):
        if obj is None:
            continue
        try:
            for modifier in list(obj.modifiers):
                if modifier.name.startswith(IRR_FLOW_CFD_MOD_PREFIX):
                    obj.modifiers.remove(modifier)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)

    for obj in _irrigation_flow_simulation_objects():
        if safe_remove_object(obj):
            count += 1

    # Remove the shared viewport-particle mesh only when no preview object uses it.
    try:
        mesh = bpy.data.meshes.get(IRR_FLOW_SIM_PREFIX + 'ViewportParticleMesh')
        if mesh is not None and mesh.users == 0:
            bpy.data.meshes.remove(mesh)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    cleanup_empty_dsg_collections(remove_root_if_empty=False)
    return count


def _ensure_irrigation_flow_material():
    material = bpy.data.materials.get(IRR_FLOW_SIM_MATERIAL)
    if material is None:
        material = bpy.data.materials.new(IRR_FLOW_SIM_MATERIAL)
    try:
        material.use_nodes = True
        nodes = material.node_tree.nodes
        links = material.node_tree.links
        for node in list(nodes):
            nodes.remove(node)
        output = nodes.new('ShaderNodeOutputMaterial')
        output.location = (260, 0)
        principled = nodes.new('ShaderNodeBsdfPrincipled')
        principled.location = (0, 0)
        principled.inputs['Base Color'].default_value = (0.50, 0.88, 1.0, 1.0)
        for socket_name in ('Transmission', 'Transmission Weight'):
            try:
                if socket_name in principled.inputs:
                    principled.inputs[socket_name].default_value = 0.42
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
        try:
            principled.inputs['IOR'].default_value = 1.333
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        principled.inputs['Roughness'].default_value = 0.045
        try:
            if 'Specular IOR Level' in principled.inputs:
                principled.inputs['Specular IOR Level'].default_value = 0.82
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        try:
            principled.inputs['Alpha'].default_value = 0.74
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        links.new(principled.outputs[0], output.inputs[0])
        material.blend_method = 'BLEND'
        material.shadow_method = 'NONE'
        material.use_backface_culling = False
        try:
            material.use_screen_refraction = True
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    except Exception:
        try:
            material.diffuse_color = (0.50, 0.88, 1.0, 0.74)
            material.roughness = 0.045
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    return material



def _polyline_length(points):
    pts = [Vector(point) for point in points]
    return sum((pts[index + 1] - pts[index]).length for index in range(len(pts) - 1))



def _remove_near_duplicate_samples(samples, epsilon=0.015):
    out = []
    last = None
    for point, radius in list(samples or []):
        point = Vector(point)
        radius = float(radius)
        if last is None or (point - last).length > epsilon:
            out.append((point, radius))
            last = point
        elif out:
            out[-1] = (point, max(float(out[-1][1]), radius))
            last = point
    return out



def _flow_samples_from_samples(samples):
    flow = [(Vector(point), float(radius)) for point, radius in list(samples or [])]
    flow.reverse()  # stored paths run sleeve -> inlet; water runs inlet -> sleeve
    return _remove_near_duplicate_samples(flow, epsilon=0.015)



def _build_c_outlet_samples_for_simulation(entry, entry_props):
    controls = entry.get('points', [])
    if len(controls) < 2:
        return []
    ring = get_irrigation_internal_ring_geometry(
        controls[1], entry_props, entry.get('implant'))
    if not ring:
        return []

    result = []
    branch_radius = max(0.14, float(ring.get('branch_tube_r', ring.get('ring_tube_r', 0.18))))
    outlet_radius = min(max(float(ring['side_hole_r']), branch_radius * 0.82), branch_radius * 0.98)
    specs = (
        (ring['upper_arc'], ring['upper_attach_point'], ring['upper_lumen_point']),
        (ring['lower_arc'], ring['lower_attach_point'], ring['lower_lumen_point']),
    )
    for arc_path, start, end in specs:
        arc = [(Vector(point), branch_radius) for point in arc_path]
        if len(arc) < 2:
            continue
        start_direction = Vector(arc_path[-1]) - Vector(arc_path[-2])
        end_direction = Vector(ring['center']) - Vector(end)
        elbow_points = _sample_plumbing_elbow_curve(
            start, end, start_direction, end_direction,
            min_turn_radius=max(float(ring['side_hole_r']) * 1.35, branch_radius * 1.10),
            max_step=0.07,
        )
        elbow = [(Vector(point), outlet_radius) for point in elbow_points[1:]]
        result.append(_remove_near_duplicate_samples(arc + elbow, epsilon=0.012))
    return result



def _append_terminal_c_paths(base_samples, terminal_entry, entry_props, flow_weight):
    base = [(Vector(point), float(radius)) for point, radius in base_samples]
    if len(base) < 2:
        return []
    c_paths = _build_c_outlet_samples_for_simulation(terminal_entry, entry_props)
    if not c_paths:
        return [{'samples': base, 'weight': max(0.0, float(flow_weight)), 'entry': terminal_entry}]

    split = Vector(c_paths[0][0][0])
    nearest = min(range(len(base)), key=lambda index: (Vector(base[index][0]) - split).length)
    if nearest >= max(1, len(base) // 2):
        base = base[:nearest + 1]
    if (Vector(base[-1][0]) - split).length > 0.01:
        base.append((split, float(c_paths[0][0][1])))
    else:
        base[-1] = (split, max(float(base[-1][1]), float(c_paths[0][0][1])))

    outlet_weight = max(0.0, float(flow_weight)) * 0.5
    routes = []
    for c_path in c_paths:
        complete = _remove_near_duplicate_samples(base + c_path[1:], epsilon=0.012)
        routes.append({'samples': complete, 'weight': outlet_weight, 'entry': terminal_entry})
    return routes



def build_irrigation_flow_simulation_routes(props):
    """Builds inlet-to-outlet sample paths for the final water-volume preview.

    The preview is not a CFD solver.  It reconstructs the real centerlines and
    local radii, then creates animated water volumes that occupy the irrigation
    lumen from the inlet through the Y splitters and either the open C manifold
    or the direct sleeve channel selected by the user.
    """
    entries = load_irrigation_path_entries(props)
    if not entries:
        return [], 'No confirmed irrigation paths'

    sources = [entry for entry in entries if not bool(entry.get('link', False))]
    links_by_source = {}
    for entry in entries:
        if bool(entry.get('link', False)):
            links_by_source.setdefault(int(entry.get('source_index', -1)), []).append(entry)

    routes = []
    for source in sources:
        source_index = int(source.get('index', -1))
        links = links_by_source.get(source_index, [])
        source_props, _ = _irrigation_entry_effective_props(props, source)
        source_samples = build_irrigation_lumen_samples_from_controls(
            source.get('points', []), source_props, include_overshoot=False)
        if len(source_samples) < 2:
            continue

        balances = _calculate_midpoint_wye_balances(source, links, props) if links else {}
        source_samples = _apply_entry_midpoint_geometry(source_samples, source, links)
        source_samples = _apply_entry_balancing(source_samples, source, links, balances)
        source_flow = _flow_samples_from_samples(source_samples)
        if len(source_flow) < 2:
            continue

        sequential_shares = {}
        if isinstance(balances, dict) and balances.get('mode') == 'SEQUENTIAL_OPENING':
            stages = (balances.get('design') or {}).get('stages') or []
            sequential_shares = dict(stages[-1].get('shares', {})) if stages else {}
        if sequential_shares:
            source_weight = float(sequential_shares.get(str(source.get('implant_name') or ''), 0.0))
        elif len(links) == 1:
            record = balances.get(int(links[0].get('index', -1)), {})
            source_weight = float(record.get('predicted_source_flow_fraction', 0.5))
        elif links:
            source_weight = 1.0 / float(len(links) + 1)
        else:
            source_weight = 1.0

        routes.extend(_append_terminal_c_paths(
            source_flow, source, source_props, source_weight))

        for link in links:
            link_props, _ = _irrigation_entry_effective_props(props, link)
            link_samples = build_irrigation_lumen_samples_from_controls(
                link.get('points', []), link_props, include_overshoot=False)
            link_samples = _apply_entry_midpoint_geometry(link_samples, link, links)
            link_samples = _apply_entry_balancing(link_samples, link, links, balances)
            link_flow = _flow_samples_from_samples(link_samples)
            meta = _midpoint_wye_metadata(link)
            if len(link_flow) < 2 or meta is None:
                continue

            split = Vector(meta['split'])
            source_split_index = min(
                range(len(source_flow)), key=lambda index: (Vector(source_flow[index][0]) - split).length)
            link_split_index = min(
                range(len(link_flow)), key=lambda index: (Vector(link_flow[index][0]) - split).length)
            common = source_flow[:source_split_index + 1]
            daughter = link_flow[link_split_index:]
            if common:
                common[-1] = (split, float(common[-1][1]))
            if daughter:
                daughter[0] = (split, max(float(daughter[0][1]), float(common[-1][1]) if common else float(daughter[0][1])))
            complete = _remove_near_duplicate_samples(common + daughter[1:], epsilon=0.012)

            if sequential_shares:
                link_weight = float(sequential_shares.get(str(link.get('implant_name') or ''), 0.0))
            elif len(links) == 1:
                record = balances.get(int(link.get('index', -1)), {})
                link_weight = float(record.get('predicted_link_flow_fraction', 0.5))
            else:
                link_weight = 1.0 / float(len(links) + 1)
            routes.extend(_append_terminal_c_paths(
                complete, link, link_props, link_weight))

    routes = [route for route in routes if len(route.get('samples', [])) >= 2]
    total_weight = sum(max(0.0, float(route.get('weight', 0.0))) for route in routes)
    if total_weight <= 1e-9 and routes:
        equal = 1.0 / len(routes)
        for route in routes:
            route['weight'] = equal
    elif total_weight > 1e-9:
        for route in routes:
            route['weight'] = max(0.0, float(route.get('weight', 0.0))) / total_weight
    return routes, ''



def _route_length_from_samples(samples):
    return sum((Vector(samples[index + 1][0]) - Vector(samples[index][0])).length for index in range(len(samples) - 1))



def _normalize_dsg_object_name(value):
    """Normalizes Blender duplicate suffixes and harmless name variations."""
    name = str(value or '').strip().lower()
    if len(name) > 4 and name[-4] == '.' and name[-3:].isdigit():
        name = name[:-4]
    return ''.join(character for character in name if character.isalnum())


def _animation_windows_for_drills(props=None):
    """Returns rich drill windows instead of relying only on an exact name key."""
    records = []
    for order, obj in enumerate(get_animated_drill_objects()):
        implant_name = str(obj.get('DSG_implant_name', '') or '')
        implant_obj = bpy.data.objects.get(implant_name) if implant_name else None
        center = None
        if _valid_obj(implant_obj):
            try:
                center = Vector(get_sleeve_center_world(props, implant_obj)) if props is not None else implant_obj.matrix_world.to_translation()
            except Exception:
                center = implant_obj.matrix_world.to_translation()
        if center is None:
            try:
                raw_contact = obj.get('DSG_stop_contact_world')
                if raw_contact is not None:
                    center = Vector(raw_contact)
            except Exception:
                center = None
        if center is None:
            center = obj.matrix_world.to_translation()
        records.append({
            'order': int(order),
            'drill': obj,
            'implant': implant_obj,
            'implant_name': implant_name,
            'normalized_name': _normalize_dsg_object_name(implant_name),
            'center': Vector(center),
            'start': int(obj.get('DSG_animation_start_frame', 1)),
            'contact': int(obj.get('DSG_animation_contact_frame', obj.get('DSG_animation_start_frame', 1))),
            'end': int(obj.get('DSG_animation_end_frame', 2)),
        })
    return records


def _resolve_drill_window_for_route(route, drill_windows, route_index=0):
    """Matches one irrigation route to its drill with several safe fallbacks."""
    if not drill_windows:
        return None, 'no_drills'
    entry = route.get('entry') if isinstance(route, dict) else None
    raw_implant = entry.get('implant') if isinstance(entry, dict) else None
    raw_name = raw_implant.name if _valid_obj(raw_implant) else str(raw_implant or '')
    normalized = _normalize_dsg_object_name(raw_name)

    if raw_name:
        for record in drill_windows:
            if record['implant_name'] == raw_name:
                return record, 'exact_name'

    if normalized:
        matches = [record for record in drill_windows if record['normalized_name'] == normalized]
        if len(matches) == 1:
            return matches[0], 'normalized_name'

    implant_obj = _resolve_irrigation_entry_implant(entry)
    if _valid_obj(implant_obj):
        for record in drill_windows:
            if record.get('implant') == implant_obj:
                return record, 'object_identity'

    samples = route.get('samples', []) if isinstance(route, dict) else []
    if samples:
        endpoint = Vector(samples[-1][0])
        nearest = min(drill_windows, key=lambda record: (Vector(record['center']) - endpoint).length)
        distance = (Vector(nearest['center']) - endpoint).length
        if distance <= 15.0 or len(drill_windows) == 1:
            return nearest, f'nearest_{distance:.3f}mm'

    if len(drill_windows) == 1:
        return drill_windows[0], 'single_drill'
    return drill_windows[int(route_index) % len(drill_windows)], 'ordered_fallback'


def _set_linear_animation_on_id(id_data):
    try:
        action = id_data.animation_data.action if getattr(id_data, 'animation_data', None) else None
        if action:
            for fcurve in action.fcurves:
                for keyframe in fcurve.keyframe_points:
                    keyframe.interpolation = 'LINEAR'
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)



def _create_irrigation_flow_curve_object(context, name, samples, material):
    """Creates the animated internal water volume along one irrigation route.

    This is only the lightweight water geometry inside the channel.  It does
    not create a camera, lights, a black background or any render stage.  The
    external outlet effect remains a particle system.
    """
    if not samples or len(samples) < 2:
        return None

    safe_remove_by_name(name)
    curve_data_name = name + '_Curve'
    old_curve = bpy.data.curves.get(curve_data_name)
    if old_curve is not None and old_curve.users == 0:
        try:
            bpy.data.curves.remove(old_curve)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)

    curve = bpy.data.curves.new(curve_data_name, type='CURVE')
    curve.dimensions = '3D'
    curve.resolution_u = 10
    curve.render_resolution_u = 14
    curve.fill_mode = 'FULL'
    curve.use_fill_caps = True
    curve.bevel_depth = 1.0
    curve.bevel_resolution = 4
    try:
        curve.bevel_factor_mapping_start = 'SPLINE'
        curve.bevel_factor_mapping_end = 'SPLINE'
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)

    spline = curve.splines.new('POLY')
    spline.points.add(len(samples) - 1)
    for index, sample in enumerate(samples):
        try:
            point, radius = sample
        except Exception:
            continue
        point = Vector(point)
        spline.points[index].co = (
            float(point.x), float(point.y), float(point.z), 1.0)
        spline.points[index].radius = max(0.015, float(radius))
        spline.points[index].tilt = 0.0

    obj = bpy.data.objects.new(name, curve)
    link_object(context, obj)
    link_object_to_dsg_collection(obj, ROLE_IRRIGATION)
    obj.display_type = 'SOLID'
    obj.show_in_front = True
    obj.hide_render = True
    obj['DSG_irrigation_flow_simulation'] = True
    obj['DSG_irrigation_internal_flow'] = True
    obj['DSG_viewport_only'] = True

    if material is not None:
        curve.materials.clear()
        curve.materials.append(material)
    return obj


def _animate_flow_curve_object(obj, start_frame, end_frame, fill_frames=6):
    if not _valid_obj(obj):
        return
    start_frame = int(start_frame)
    end_frame = max(start_frame + 1, int(end_frame))
    fill_frames = max(1, int(fill_frames))
    obj.scale = (0.0, 0.0, 0.0)
    obj.keyframe_insert(data_path='scale', frame=max(1, start_frame - 1))
    obj.scale = (1.0, 1.0, 1.0)
    obj.keyframe_insert(data_path='scale', frame=start_frame)
    obj.scale = (1.0, 1.0, 1.0)
    obj.keyframe_insert(data_path='scale', frame=end_frame)
    obj.scale = (0.0, 0.0, 0.0)
    obj.keyframe_insert(data_path='scale', frame=end_frame + 1)
    try:
        curve = obj.data
        curve.bevel_factor_start = 0.0
        curve.bevel_factor_end = 0.0
        curve.keyframe_insert(data_path='bevel_factor_end', frame=max(1, start_frame - 1))
        curve.keyframe_insert(data_path='bevel_factor_end', frame=start_frame)
        curve.bevel_factor_end = 1.0
        curve.keyframe_insert(data_path='bevel_factor_end', frame=min(end_frame, start_frame + fill_frames))
        curve.keyframe_insert(data_path='bevel_factor_end', frame=end_frame)
        _set_linear_animation_on_id(curve)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    _set_linear_animation_on_id(obj)



def _ensure_viewport_particle_material():
    """Blue viewport-only material, slightly darker than the internal water."""
    material = bpy.data.materials.get(IRR_FLOW_VIEWPORT_PARTICLE_MATERIAL)
    if material is None:
        material = bpy.data.materials.new(IRR_FLOW_VIEWPORT_PARTICLE_MATERIAL)
    try:
        material.use_nodes = False
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    try:
        material.diffuse_color = (0.16, 0.48, 0.78, 1.0)
        material.roughness = 0.58
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    return material



def _ensure_solid_material_coloring(context):
    """Make the active Solid view use material colors so blue particles are visible."""
    try:
        screen = context.screen
        if screen is None:
            return
        for area in screen.areas:
            if area.type != 'VIEW_3D':
                continue
            for space in area.spaces:
                if space.type == 'VIEW_3D' and space.shading.type == 'SOLID':
                    space.shading.color_type = 'MATERIAL'
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)



def _create_shared_viewport_particle_mesh():
    name = IRR_FLOW_SIM_PREFIX + 'ViewportParticleMesh'
    mesh = bpy.data.meshes.get(name)
    if mesh is not None:
        return mesh
    # Very low-poly sphere shared by every animated point.
    return make_uv_sphere_mesh(name, 1.0, u_segments=8, v_segments=4)



def _particle_outlet_basis(event, props):
    vectors = _cascade_vectors_for_event(event, props)
    if vectors is None:
        return None
    endpoint, outlet_dir, apical_dir, cascade_dir = vectors
    face_u = outlet_dir.cross(apical_dir)
    if face_u.length < 1e-8:
        face_u = cascade_dir.cross(outlet_dir)
    if face_u.length < 1e-8:
        face_u, _unused_v, _unused_w = build_axis_basis(outlet_dir)
    face_u.normalize()
    face_v = face_u.cross(outlet_dir)
    if face_v.length < 1e-8:
        _unused_u, face_v, _unused_w = build_axis_basis(face_u)
    face_v.normalize()
    return endpoint, outlet_dir, apical_dir, cascade_dir, face_u, face_v



def _animate_viewport_particle(obj, seed_point, initial_velocity, gravity_dir,
                               spawn_frame, life_frames, radius, rng, mist=False):
    """Keyframes one ballistic flight; no particle system or emitter is used."""
    spawn_frame = int(spawn_frame)
    life_frames = max(3, int(life_frames))
    end_frame = spawn_frame + life_frames
    gravity_dir = _normalized_or_fallback(gravity_dir, (0.0, 0.0, -1.0))
    velocity = Vector(initial_velocity)
    lateral_u, lateral_v, _forward = build_axis_basis(
        velocity if velocity.length > 1e-8 else Vector((0.0, 0.0, -1.0)))
    gravity_strength = max(0.001, velocity.length / max(4.0, life_frames) * (0.12 if mist else 0.18))
    turbulence_phase = rng.uniform(0.0, math.tau)
    turbulence_amount = radius * (1.8 if mist else 0.85)

    obj.location = Vector(seed_point)
    obj.scale = (0.0, 0.0, 0.0)
    obj.keyframe_insert(data_path='location', frame=max(1, spawn_frame - 1))
    obj.keyframe_insert(data_path='scale', frame=max(1, spawn_frame - 1))

    steps = 6 if mist else 7
    for step in range(steps):
        fraction = step / max(1, steps - 1)
        t = life_frames * fraction
        frame = spawn_frame + int(round(t))
        turbulence = (
            lateral_u * math.sin(turbulence_phase + fraction * math.tau * 1.7)
            + lateral_v * math.cos(turbulence_phase * 0.73 + fraction * math.tau * 1.15)
        ) * turbulence_amount * fraction
        position = (
            Vector(seed_point)
            + velocity * t
            + gravity_dir * (0.5 * gravity_strength * t * t)
            + turbulence
        )
        shrink = 1.0 - fraction * (0.48 if mist else 0.28)
        current_radius = max(radius * 0.42, radius * shrink)
        obj.location = position
        obj.scale = (current_radius, current_radius, current_radius)
        obj.keyframe_insert(data_path='location', frame=frame)
        obj.keyframe_insert(data_path='scale', frame=frame)

    obj.scale = (0.0, 0.0, 0.0)
    obj.keyframe_insert(data_path='scale', frame=end_frame + 1)
    _set_linear_animation_on_id(obj)



def _create_viewport_water_particles(context, name_prefix, event, props,
                                     start_frame, end_frame):
    """Creates blue animated viewport particles directly, with no emitter objects."""
    basis = _particle_outlet_basis(event, props)
    if basis is None:
        return []
    endpoint, outlet_dir, apical_dir, cascade_dir, face_u, face_v = basis
    reach = max(1.0, float(getattr(props, 'irr_spray_length', 4.2)))
    density = max(1, int(getattr(props, 'irr_spray_streams', 4)))
    spread_deg = max(0.0, float(getattr(props, 'irr_spray_spread', 20.0)))
    start_frame = int(start_frame)
    end_frame = max(start_frame + 4, int(end_frame))
    active_span = max(4, end_frame - start_frame)

    outlet_radius = 0.08
    try:
        outlet_radius = max(0.04, float(event.get('samples', [])[-1][1]) * 0.95)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    try:
        contact_frame = int(event.get('contact_frame', start_frame + active_span // 2))
    except Exception:
        contact_frame = start_frame + active_span // 2

    material = _ensure_viewport_particle_material()
    mesh = _create_shared_viewport_particle_mesh()
    _ensure_solid_material_coloring(context)

    # Four times the previous density. The base formula is preserved so the
    # panel density control still has the same meaning, but every outlet now
    # produces four times as many viewport droplets and mist particles.
    base_core_count = min(86, max(18, active_span // 2 + density * 4))
    base_mist_count = min(110, max(24, (active_span * 2) // 3 + density * 5))
    core_count = base_core_count * 4
    mist_count = base_mist_count * 4
    spread = math.tan(math.radians(spread_deg))
    created = []

    for mist, count in ((False, core_count), (True, mist_count)):
        layer_name = 'Mist' if mist else 'Drop'
        for index in range(count):
            seed = sum((i + 11) * ord(ch) for i, ch in enumerate(name_prefix + layer_name)) + index * 7919
            rng = random.Random(seed)
            distribution = (index + rng.random()) / max(1.0, float(count))
            spawn = start_frame + min(active_span - 3, int(distribution * max(1, active_span - 3)))
            remaining = end_frame - spawn
            if remaining < 3:
                continue
            life = min(remaining, rng.randint(6, 11) if mist else rng.randint(8, 15))

            # Uniform area sampling across the entire circular outlet face.
            disk_r = outlet_radius * math.sqrt(rng.random())
            theta = rng.uniform(0.0, math.tau)
            seed_point = (
                endpoint
                + face_u * (math.cos(theta) * disk_r)
                + face_v * (math.sin(theta) * disk_r)
                + outlet_dir * max(0.008, outlet_radius * 0.04)
            )
            u_push = math.cos(theta) * (disk_r / max(1e-6, outlet_radius))
            v_push = math.sin(theta) * (disk_r / max(1e-6, outlet_radius))
            local_spread = spread * (1.30 if mist else 0.78)
            direction = (
                cascade_dir
                + face_u * (u_push * local_spread + rng.uniform(-0.18, 0.18) * local_spread)
                + face_v * (v_push * local_spread * 0.72 + rng.uniform(-0.14, 0.14) * local_spread)
                + outlet_dir * rng.uniform(0.02, 0.12)
            )
            if direction.length < 1e-8:
                direction = cascade_dir.copy()
            direction.normalize()

            pulse_distance = abs(spawn - contact_frame) / max(1.0, active_span * 0.34)
            pulse = 1.0 + max(0.0, 1.0 - pulse_distance) * (0.20 if mist else 0.14)
            speed = (reach / max(4.0, life)) * rng.uniform(
                0.78 if mist else 0.68,
                1.18 if mist else 1.04) * pulse
            velocity = direction * speed
            # Wider, weighted size distribution. This avoids the artificial
            # look of every particle having almost the same diameter.
            size_roll = rng.random()
            if mist:
                if size_roll < 0.58:
                    size_class = 'MICRO'
                    radius_factor = rng.uniform(0.035, 0.075)
                elif size_roll < 0.90:
                    size_class = 'FINE'
                    radius_factor = rng.uniform(0.075, 0.145)
                else:
                    size_class = 'MEDIUM'
                    radius_factor = rng.uniform(0.145, 0.235)
                radius = max(0.0035, min(0.020, outlet_radius * radius_factor))
            else:
                if size_roll < 0.26:
                    size_class = 'SMALL'
                    radius_factor = rng.uniform(0.095, 0.175)
                elif size_roll < 0.76:
                    size_class = 'MEDIUM'
                    radius_factor = rng.uniform(0.175, 0.325)
                elif size_roll < 0.96:
                    size_class = 'LARGE'
                    radius_factor = rng.uniform(0.325, 0.520)
                else:
                    size_class = 'SPLASH'
                    radius_factor = rng.uniform(0.520, 0.720)
                radius = max(0.008, min(0.058, outlet_radius * radius_factor))

            obj = bpy.data.objects.new(
                f'{name_prefix}_{layer_name}_{index:03d}', mesh)
            link_object(context, obj)
            link_object_to_dsg_collection(obj, ROLE_IRRIGATION)
            obj.display_type = 'SOLID'
            obj.show_in_front = True
            obj.hide_select = True
            obj.hide_render = True
            obj.color = (0.16, 0.48, 0.78, 1.0)
            obj.data.materials.clear()
            obj.data.materials.append(material)
            obj['DSG_irrigation_flow_simulation'] = True
            obj['DSG_irrigation_viewport_particle'] = True
            obj['DSG_viewport_only'] = True
            obj['DSG_particle_layer'] = layer_name
            obj['DSG_particle_size_class'] = size_class
            obj['DSG_particle_radius_mm'] = float(radius)
            obj['DSG_particle_density_multiplier'] = 4
            obj['DSG_no_emitter_object'] = True
            _animate_viewport_particle(
                obj, seed_point, velocity, apical_dir,
                spawn, life, radius, rng, mist=mist)
            created.append(obj)
    return created



def _set_rna_if_present(target, name, value):
    try:
        if target is not None and hasattr(target, name):
            setattr(target, name, value)
            return True
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    return False



def _make_world_box_mesh(name, minimum, maximum):
    """Creates an axis-aligned closed box using actual world coordinates."""
    minimum = Vector(minimum)
    maximum = Vector(maximum)
    x0, y0, z0 = minimum
    x1, y1, z1 = maximum
    vertices = [
        (x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
        (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1),
    ]
    faces = [
        (0, 3, 2, 1), (4, 5, 6, 7),
        (0, 1, 5, 4), (1, 2, 6, 5),
        (2, 3, 7, 6), (3, 0, 4, 7),
    ]
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.validate(clean_customdata=False)
    mesh.update(calc_edges=True)
    return mesh



def _ensure_fluid_effector(obj, modifier_name, surface_distance=0.0015):
    if not _valid_obj(obj) or obj.type != 'MESH':
        return None
    try:
        modifier = obj.modifiers.get(modifier_name)
        if modifier is None:
            modifier = obj.modifiers.new(modifier_name, 'FLUID')
        modifier.fluid_type = 'EFFECTOR'
        bpy.context.view_layer.update()
        settings = modifier.effector_settings
        if settings is not None:
            _set_rna_if_present(settings, 'effector_type', 'COLLISION')
            _set_rna_if_present(settings, 'surface_distance', float(surface_distance))
            _set_rna_if_present(settings, 'use_plane_init', False)
            _set_rna_if_present(settings, 'use_effector', True)
        return modifier
    except Exception as exc:
        print(f'[DSG] Could not configure fluid effector on {getattr(obj, "name", "?")}: {exc}')
        return None



def _resolve_irrigation_entry_implant(entry):
    if not isinstance(entry, dict):
        return None
    raw = entry.get('implant')
    if _valid_obj(raw):
        return raw
    try:
        return bpy.data.objects.get(str(raw)) if raw else None
    except Exception:
        return None



def _cascade_vectors_for_event(event, props):
    samples = event.get('samples', []) if isinstance(event, dict) else []
    if len(samples) < 2:
        return None
    endpoint = Vector(samples[-1][0])
    previous = Vector(samples[-2][0])
    outlet_dir = endpoint - previous
    if outlet_dir.length < 1e-8:
        return None
    outlet_dir.normalize()

    entry = event.get('entry') if isinstance(event, dict) else None
    implant = _resolve_irrigation_entry_implant(entry)
    axis = get_implant_axis_world(props, implant)
    if axis.length < 1e-8:
        axis = Vector((0.0, 0.0, 1.0))
    axis.normalize()
    sign = get_sleeve_occlusal_sign(props, implant)
    apical_dir = -(axis * float(sign))
    if apical_dir.length < 1e-8:
        apical_dir = Vector((0.0, 0.0, -1.0))
    apical_dir.normalize()

    # The stream first leaves the rounded side outlet and immediately bends
    # apically, producing a waterfall-like sheet without requiring guide collision.
    cascade_dir = outlet_dir * 0.42 + apical_dir * 0.91
    if cascade_dir.length < 1e-8:
        cascade_dir = apical_dir
    cascade_dir.normalize()
    return endpoint, outlet_dir, apical_dir, cascade_dir



class DSG_OT_SimulateIrrigationFlow(Operator):
    bl_idname = 'dsg.simulate_irrigation_flow'
    bl_label = 'Update Solid Water Flow'
    bl_description = (
        'Creates or updates the full internal water-flow preview and blue viewport-only particles at the outlets. '
        'No emitters, particle systems, render instances, camera, lights or render stage are created')
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.dsg_props
        guide = get_active_guide_obj(props)
        if not _valid_obj(guide):
            _dsg_report(self, {'ERROR'}, 'Finish the guide first', 'Termina primero la guía')
            return {'CANCELLED'}

        drill_windows = _animation_windows_for_drills(props)
        if not drill_windows:
            _dsg_report(
                self, {'ERROR'},
                'Create the sequential drill animation first; the water particles are synchronized to the drills',
                'Crea antes la animación secuencial de las fresas; las partículas de agua se sincronizan con ellas')
            return {'CANCELLED'}

        clear_irrigation_flow_simulation()
        routes, error = build_irrigation_flow_simulation_routes(props)
        if not routes:
            _dsg_report(
                self, {'ERROR'},
                error or 'No continuous irrigation routes could be generated',
                'No se pudieron generar trayectorias continuas de irrigación')
            return {'CANCELLED'}

        material = _ensure_irrigation_flow_material()
        created_particle_objects = 0
        created_particle_groups = 0
        created_internal_flows = 0
        matched_routes = 0
        particle_failures = 0
        global_start = None
        global_end = None
        fill_frames = max(1, int(getattr(props, 'irr_spray_fill_frames', 6)))

        for route_index, route in enumerate(routes):
            samples = route.get('samples', [])
            if len(samples) < 2 or _route_length_from_samples(samples) < 0.05:
                continue

            entry = route.get('entry')
            implant = _resolve_irrigation_entry_implant(entry)
            implant_name = (
                implant.name if _valid_obj(implant)
                else str(entry.get('implant', '') if isinstance(entry, dict) else '')
            )
            window, match_mode = _resolve_drill_window_for_route(
                route, drill_windows, route_index)
            if not window:
                print(f'[DSG] Water route {route_index} could not be matched to a drill')
                continue

            start_frame = int(window['start'])
            end_frame = int(window['end'])
            contact_frame = int(window.get(
                'contact', start_frame + max(1, (end_frame - start_frame) // 2)))
            implant_name = window.get('implant_name') or implant_name
            matched_routes += 1
            global_start = start_frame if global_start is None else min(global_start, start_frame)
            global_end = end_frame if global_end is None else max(global_end, end_frame)

            fill_name = f'{IRR_FLOW_SIM_PREFIX}Flow_{route_index:02d}'
            fill_obj = _create_irrigation_flow_curve_object(context, fill_name, samples, material)
            if _valid_obj(fill_obj):
                fill_obj['DSG_irrigation_flow_simulation'] = True
                fill_obj['DSG_irrigation_internal_flow'] = True
                fill_obj['DSG_implant_name'] = implant_name
                fill_obj['DSG_drill_match_mode'] = str(match_mode)
                fill_obj['DSG_render_stage_created'] = False
                fill_obj['DSG_filled_channel_created'] = True
                # Fill the whole route quickly, keep it visible while the drill moves,
                # and let the outlet spray start shortly after the internal water arrives.
                _animate_flow_curve_object(
                    fill_obj,
                    start_frame,
                    end_frame,
                    fill_frames=min(fill_frames, max(1, contact_frame - start_frame if contact_frame > start_frame else fill_frames)),
                )
                created_internal_flows += 1

            event = {
                'samples': samples,
                'entry': entry,
                'weight': route.get('weight', 1.0),
                'contact_frame': contact_frame,
            }
            particle_name = f'{IRR_FLOW_SIM_PREFIX}Particles_{route_index:02d}'
            particle_objects = _create_viewport_water_particles(
                context,
                particle_name,
                event,
                props,
                start_frame + max(1, min(fill_frames, 3)),
                end_frame,
            )
            if particle_objects:
                for particle_obj in particle_objects:
                    particle_obj['DSG_irrigation_outlet_spray'] = True
                    particle_obj['DSG_implant_name'] = implant_name
                    particle_obj['DSG_drill_match_mode'] = str(match_mode)
                    particle_obj['DSG_render_stage_created'] = False
                    particle_obj['DSG_filled_channel_created'] = True
                created_particle_objects += len(particle_objects)
                created_particle_groups += 1
            else:
                particle_failures += 1

        if created_particle_groups == 0 and created_internal_flows == 0:
            clear_irrigation_flow_simulation()
            detail = (
                f'routes={len(routes)}, drills={len(drill_windows)}, '
                f'matched={matched_routes}, internal_flows={created_internal_flows}, particle_groups={created_particle_groups}, '
                f'particle_objects={created_particle_objects}, particle_failures={particle_failures}')
            if matched_routes == 0:
                message_en = 'The irrigation routes could not be matched to the animated drills. ' + detail
                message_es = 'No se pudieron emparejar las rutas de irrigación con las fresas animadas. ' + detail
            else:
                message_en = 'The routes were synchronized, but Blender could not create the internal flow preview or the viewport particles. ' + detail
                message_es = 'Las rutas se sincronizaron, pero Blender no pudo crear el flujo interno ni las partículas del viewport. ' + detail
            _dsg_report(self, {'ERROR'}, message_en, message_es)
            return {'CANCELLED'}

        if global_start is None or global_end is None:
            global_start, global_end = get_sequential_insertion_bounds(props)
        context.scene.frame_start = int(global_start)
        context.scene.frame_end = max(int(global_end), int(global_start) + 1)
        context.scene.frame_set(int(global_start))
        _dsg_report(
            self, {'INFO'},
            f'Water flow preview created: {created_internal_flows} internal routes and {created_particle_objects} blue viewport particles in {created_particle_groups} outlet groups.',
            f'Previsualización creada: {created_internal_flows} rutas internas y {created_particle_objects} partículas azules del viewport en {created_particle_groups} grupos de salida.')
        return {'FINISHED'}


class DSG_OT_ClearIrrigationFlowSimulation(Operator):
    bl_idname = 'dsg.clear_irrigation_flow_simulation'
    bl_label = 'Clear Irrigation Simulation'
    bl_description = 'Deletes the internal water preview and all viewport-only outlet particles'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        removed = clear_irrigation_flow_simulation()
        _dsg_report(
            self, {'INFO'},
            f'Water preview cleared ({removed} viewport objects)',
            f'Previsualización de agua eliminada ({removed} objetos del viewport)')
        return {'FINISHED'}



class DSG_OT_ConfirmIrrigation(Operator):
    bl_idname = 'dsg.confirm_irrigation'
    bl_label = 'Apply Irrigation and Continue'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if not _require_workflow_stage(
                self, context, STEP_IRRIGATION,
                action_en='Cannot apply irrigation',
                action_es='No se puede aplicar la irrigación'):
            return {'CANCELLED'}
        props = context.scene.dsg_props
        if get_pending_irrigation_preview(props):
            _dsg_report(self, {'ERROR'}, 'Confirm or discard the pending preview', 'Confirma o descarta la vista previa pendiente')
            return {'CANCELLED'}

        guide = get_active_guide_obj(props)
        # v8.4.3: lateral access is intentionally AFTER irrigation. Do not
        # rebuild or modify sleeves before the irrigation Boolean.

        original_walls = get_confirmed_irrigation_walls()
        entries = sort_irrigation_entries_for_boolean(
            load_irrigation_path_entries(props))
        if not _valid_obj(guide):
            _dsg_report(self, {'ERROR'}, 'DSG_Guide is missing', 'Falta DSG_Guide')
            return {'CANCELLED'}
        if not entries:
            _dsg_report(self, {'ERROR'}, 'There are no saved irrigation paths', 'No hay ejes de irrigación guardados')
            return {'CANCELLED'}

        # Confirmed wall objects are only viewport previews. Linked irrigation can
        # legitimately store two clinical paths (source + Link) while displaying
        # one combined wall, and a preview can also be deleted independently. The
        # final operation rebuilds all walls from the saved paths, so a mismatch
        # is reconciled instead of blocking the clinical workflow.
        irrigation_state_reconciled = len(original_walls) != len(entries)
        irrigation_preview_wall_count = len(original_walls)

        temp_objects = []
        cutters = []
        c_only_cutters = {}
        processed_walls = []
        guide_parts = []
        failure = None
        preflight_repaired_components = 0
        preflight_repaired_edges = 0
        sleeve_guard_skips = 0
        sleeve_raycast_passes = 0
        sleeve_boolean_operations = 0
        sleeve_leak_rejections = 0
        sleeve_continuity_repairs = 0
        sleeve_continuity_failures = 0
        irrigation_wall_c_openings = 0
        irrigation_wall_c_repairs = 0
        sleeve_guard_implants = get_all_implant_objects(props)
        model_cut_preflight_passes = 0
        model_cut_preflight_rejections = 0
        model_cut_preflight_skips = 0
        model_cut_preflight_records = []

        try:
            # 1) Build cutters with the same geometry as the final walls.
            # A linked source is rebuilt as one manifold cutter; no obsolete
            # straight source/link cutters are retained.
            links_by_source_for_cut = {}
            for candidate in entries:
                if bool(candidate.get('link', False)):
                    links_by_source_for_cut.setdefault(
                        int(candidate.get('source_index', -1)), []).append(candidate)
            processed_cut_indices = set()
            for index, entry in enumerate(entries):
                entry_index = int(entry.get('index', index))
                if entry_index in processed_cut_indices or bool(entry.get('link', False)):
                    continue
                linked_for_cut = links_by_source_for_cut.get(entry_index, [])
                if linked_for_cut:
                    cutter = build_irrigation_y_network_lumen_cutter(
                        context, entry, linked_for_cut, props,
                        name=f'DSG_IrrYNetworkCut_{entry_index:02d}')
                    processed_cut_indices.add(entry_index)
                    processed_cut_indices.update(
                        int(item.get('index', -1)) for item in linked_for_cut)
                else:
                    cutter = build_irrigation_single_lumen_cutter(
                        context, entry, props, f'DSG_IrrSingleCut_{index:02d}')
                    processed_cut_indices.add(entry_index)
                if not _valid_obj(cutter):
                    failure = f'No se pudo construir el cutter de irrigación {entry_index + 1}'
                    break
                cutters.append(cutter)
                temp_objects.append(cutter)

            if failure:
                raise RuntimeError(failure)

            # 1b) Build one compact C-only cutter per sleeve.  Linked implants
            # share only the external Y lumen; every sleeve is cut and validated
            # independently with its own continuous C cutter.  The same cutter is
            # also subtracted from the irrigation wall shell so that the wall
            # cannot re-block the manifold during final assembly.
            for c_index, c_entry in enumerate(entries):
                entry_index = int(c_entry.get('index', c_index))
                c_props, _c_parameters = _irrigation_entry_effective_props(
                    props, c_entry)
                c_mode = str(
                    getattr(c_props, 'irr_sleeve_channel_mode', 'C') or 'C').upper()
                if c_mode == 'DIRECT':
                    continue
                c_controls = c_entry.get('points', [])
                if len(c_controls) < 2:
                    failure = f'El conducto {entry_index + 1} no tiene controles válidos para el canal en C'
                    break
                c_implant = c_entry.get('implant')
                if not is_valid_implant_obj(c_implant):
                    c_implant = get_nearest_implant_to_point(
                        props, c_controls[1] if len(c_controls) > 1 else c_controls[0])
                c_cutter = build_irrigation_c_only_cutter(
                    context,
                    c_controls,
                    c_props,
                    implant_obj=c_implant,
                    name=f'DSG_IrrCOnlyCut_{entry_index:02d}',
                    extra_radius=0.045,
                )
                if not _valid_obj(c_cutter):
                    failure = f'No se pudo construir el cutter continuo en C del conducto {entry_index + 1}'
                    break
                c_only_cutters[entry_index] = c_cutter
                # Apply this dedicated cutter to the corresponding sleeve after
                # the shared external/Y lumen.  It carries its own implant name
                # and continuity samples, so the post-Boolean audit can repair or
                # reject an interrupted C instead of silently accepting it.
                cutters.append(c_cutter)
                temp_objects.append(c_cutter)

            if failure:
                raise RuntimeError(failure)

            # 2) Build irrigation walls. A source channel with one or more Links
            # is rebuilt as ONE continuous hollow Y network. This removes the
            # internal end caps that previously blocked some branches.
            entries_by_index = {
                int(item.get('index', idx)): item
                for idx, item in enumerate(entries)
            }
            links_by_source = {}
            for candidate in entries:
                if bool(candidate.get('link', False)):
                    links_by_source.setdefault(
                        int(candidate.get('source_index', -1)), []).append(candidate)

            processed_entry_indices = set()
            wall_by_entry_index = {}
            for index, entry in enumerate(entries):
                entry_index = int(entry.get('index', index))
                if entry_index in processed_entry_indices:
                    continue
                if bool(entry.get('link', False)):
                    # Links are processed together with their source channel.
                    continue

                linked_entries = links_by_source.get(entry_index, [])
                if linked_entries:
                    wall_copy = build_irrigation_y_network_hollow_wall(
                        context, entry, linked_entries, props,
                        name=f'DSG_IrrYNetworkWall_{entry_index:02d}')
                    if not _valid_obj(wall_copy):
                        failure = (
                            f'Could not build the continuous Y irrigation wall '
                            f'for source channel {entry_index + 1}')
                        break
                    temp_objects.append(wall_copy)
                    processed_walls.append(wall_copy)
                    wall_by_entry_index[entry_index] = wall_copy
                    processed_entry_indices.add(entry_index)
                    for link_entry in linked_entries:
                        link_index = int(link_entry.get('index', -1))
                        wall_by_entry_index[link_index] = wall_copy
                        processed_entry_indices.add(link_index)
                    continue

                parameters = entry.get('parameters', {})
                entry_props = irrigation_props_overlay(props, parameters)
                implant = entry.get('implant')
                wall_copy = build_irrigation_hollow_wall_object(
                    context, entry.get('points', []), entry_props,
                    implant_obj=implant,
                    name=f'DSG_IrrWallHollow_{index:02d}',
                    show_wire=False,
                    cap_end=True,
                    venturi_specs=[])
                if not _valid_obj(wall_copy):
                    failure = f'Could not build the hollow channel wall {index + 1}'
                    break
                report = get_mesh_solid_report(wall_copy, max_polygons=500000)
                if report.get('checked') and not report.get('solid'):
                    failure = (
                        f'Hollow wall {index + 1} is not solid: '
                        f'edges={report.get("bad_edges", 0)}, '
                        f'degenerate faces={report.get("degenerate_faces", 0)}')
                    break
                temp_objects.append(wall_copy)
                processed_walls.append(wall_copy)
                wall_by_entry_index[entry_index] = wall_copy
                processed_entry_indices.add(entry_index)

            if failure:
                raise RuntimeError(failure)

            # 2a) Open the C manifold through the overlapping irrigation wall
            # shells. The sleeve cut alone is insufficient because the hollow
            # external tube is assembled afterwards and can occupy the branch
            # junctions inside the sleeve.
            for entry_index, c_cutter in sorted(c_only_cutters.items()):
                wall_target = wall_by_entry_index.get(entry_index)
                if not _valid_obj(wall_target):
                    failure = (
                        f'No se encontró la pared de irrigación asociada al canal en C '
                        f'{entry_index + 1}')
                    break
                wall_ok, wall_message = apply_difference_exact_checked(
                    context,
                    wall_target,
                    c_cutter,
                    f'DSG_IrrWallCOpening_{entry_index:02d}',
                    robust_retry=True,
                    allow_manifold_fallback=True,
                    retry_offsets=(0.01, 0.02, 0.04, 0.06),
                )
                if not wall_ok:
                    failure = (
                        f'No se pudo abrir el canal en C a través de la pared de '
                        f'irrigación {entry_index + 1}: {wall_message}')
                    break
                irrigation_wall_c_openings += 1

                blocked_wall = _blocked_irrigation_c_samples(
                    wall_target, c_cutter)
                if blocked_wall:
                    rescue = make_offset_boolean_cutter(
                        context,
                        c_cutter,
                        f'DSG_IrrWallCRescue_{entry_index:02d}',
                        0.035,
                    )
                    if _valid_obj(rescue):
                        temp_objects.append(rescue)
                        rescue_ok, rescue_message = apply_difference_exact_checked(
                            context,
                            wall_target,
                            rescue,
                            f'DSG_IrrWallCRescueDifference_{entry_index:02d}',
                            robust_retry=True,
                            allow_manifold_fallback=True,
                            retry_offsets=(0.01, 0.02, 0.04),
                        )
                        if rescue_ok:
                            blocked_wall = _blocked_irrigation_c_samples(
                                wall_target, c_cutter)
                            if not blocked_wall:
                                irrigation_wall_c_repairs += 1
                        else:
                            print(
                                f'[DSG] Wall C continuity rescue failed for '
                                f'channel {entry_index + 1}: {rescue_message}')
                if blocked_wall:
                    failure = (
                        f'La pared del conducto {entry_index + 1} sigue bloqueando '
                        f'{len(blocked_wall)} tramo(s) del canal en C. La operación '
                        f'se cancela para no producir una irrigación interrumpida.')
                    break

            if failure:
                raise RuntimeError(failure)

            # 2b) Preflight correcto: luz real de irrigación contra modelo pasivo.
            # El riesgo real aparece en el corte final modelo/blockout → guía: si
            # el modelo invade la luz del agua, o deja una pared prácticamente
            # inexistente junto a esa luz, la booleana final abre una fuga.
            passive_model_for_irrigation = get_passive_model_obj()
            for check_index, entry in enumerate(entries):
                safe_model, model_message, model_data = irrigation_model_cut_preflight(
                    context, entry, props, passive_model_for_irrigation,
                    label=f'conducto {int(entry.get("index", check_index)) + 1}')
                model_cut_preflight_records.append(model_data)
                if str(model_data.get('status', '')).lower() == 'skipped':
                    model_cut_preflight_skips += 1
                elif safe_model:
                    model_cut_preflight_passes += 1
                else:
                    model_cut_preflight_rejections += 1
                    failure = (
                        f'No es posible usar esta irrigación antes del corte final: '
                        f'{model_message}. Mueve el trazado del canal fuera del diente/modelo '
                        f'o cambia la posición de salida para conservar pared alrededor de la luz.')
                    break

            if failure:
                raise RuntimeError(failure)

            # No separate junction boolean is needed. The common trunk and every
            # daughter branch were already fused before the lumen was subtracted.
            junction_operations = 0

            # 3) La guía instantánea contiene frame y sleeves como shells cerrados.
            # Se separan por conectividad para que EXACT nunca opere sobre shells
            # solapados simultáneamente.
            guide_parts = split_mesh_object_loose_parts(
                context, guide, prefix='DSG_IrrGuidePart')
            temp_objects.extend(guide_parts)
            if not guide_parts:
                failure = 'Could not split the guide into closed components'
                raise RuntimeError(failure)

            cutter_aabbs = [object_world_aabb(cutter) for cutter in cutters]
            cut_operations = 0
            for part_index, part in enumerate(guide_parts):
                initial_report = get_mesh_solid_report(part, max_polygons=900000)
                if initial_report.get('checked') and not initial_report.get('solid'):
                    repaired, repair_message, repaired_report, repaired_edges = (
                        repair_irrigation_open_component(part, max_bad_edges=256))
                    if not repaired:
                        failure = (
                            f'Component {part_index + 1} de la guía ya era no sólido: '
                            f'aristas={initial_report.get("bad_edges", 0)}; '
                            f'{repair_message}')
                        break
                    initial_report = repaired_report
                    preflight_repaired_components += 1
                    preflight_repaired_edges += int(repaired_edges)
                    print(
                        f'[DSG] Irrigation preflight: component {part_index + 1} '
                        f'reparado ({repair_message})')

                # Identify sleeve components unconditionally. The C-lumen
                # continuity audit is independent from the optional legacy guard.
                sleeve_implant = find_sleeve_shell_implant(
                    part, props, implants=sleeve_guard_implants)

                part_aabb = object_world_aabb(part)
                for cutter_index, (cutter, cutter_aabb) in enumerate(zip(cutters, cutter_aabbs)):
                    if not aabb_overlap(part_aabb, cutter_aabb, margin=0.05):
                        continue

                    # v7.0.17: no se valida canal contra sleeve.  La comprobación
                    # clínica relevante ya se hizo arriba: canal de irrigación
                    # contra modelo pasivo antes del corte final.
                    ok, message = apply_difference_exact_checked(
                        context, part, cutter,
                        f'DSG_IrrGuideDifference_{part_index:02d}_{cutter_index:02d}',
                        robust_retry=True,
                        allow_manifold_fallback=True,
                        retry_offsets=(0.01, 0.02, 0.04, 0.08))
                    if not ok:
                        failure = (
                            f'Corte de sleeve/frame falló en component {part_index + 1}, '
                            f'conducto {cutter_index + 1}: {message}')
                        break
                    cut_operations += 1
                    if sleeve_implant is not None:
                        sleeve_boolean_operations += 1

                    # Verify the actual water path after Blender's Boolean, not
                    # merely the cutter topology. Every sampled point along the
                    # internal C must lie in void. If Blender left a small solid
                    # bridge, retry transactionally with a minimally enlarged
                    # cutter; otherwise reject the operation instead of exporting
                    # an interrupted channel.
                    is_matching_c_sleeve = False
                    if sleeve_implant is not None:
                        cutter_implant_name = str(cutter.get('DSG_implant_name', '') or '')
                        sleeve_name = _safe_object_name(sleeve_implant) or ''
                        is_matching_c_sleeve = bool(
                            cutter_implant_name
                            and cutter_implant_name == sleeve_name
                            and bool(cutter.get('DSG_irrigation_internal_c_manifold', False)))
                    if is_matching_c_sleeve:
                        blocked = _blocked_irrigation_c_samples(part, cutter)
                        if blocked:
                            repaired = False
                            for rescue_index, rescue_offset in enumerate((0.035, 0.060), start=1):
                                rescue_name = (
                                    f'DSG_IrrCContinuityRescue_{part_index:02d}_'
                                    f'{cutter_index:02d}_{rescue_index:02d}')
                                rescue = make_offset_boolean_cutter(
                                    context, cutter, rescue_name, rescue_offset)
                                if not _valid_obj(rescue):
                                    continue
                                temp_objects.append(rescue)
                                rescue_ok, rescue_message = apply_difference_exact_checked(
                                    context, part, rescue,
                                    f'DSG_IrrCContinuityDifference_{part_index:02d}_'
                                    f'{cutter_index:02d}_{rescue_index:02d}',
                                    robust_retry=True,
                                    allow_manifold_fallback=True,
                                    retry_offsets=(0.01, 0.02, 0.04))
                                if not rescue_ok:
                                    print(
                                        f'[DSG] C continuity rescue {rescue_index} failed: '
                                        f'{rescue_message}')
                                    continue
                                blocked = _blocked_irrigation_c_samples(part, cutter)
                                if not blocked:
                                    repaired = True
                                    sleeve_continuity_repairs += 1
                                    break
                            if not repaired:
                                sleeve_continuity_failures += 1
                                failure = (
                                    f'El canal en C del sleeve asociado a '
                                    f'{_safe_object_name(sleeve_implant) or "el implante"} '
                                    f'quedó interrumpido en {len(blocked)} punto(s) '
                                    f'después del corte. La guía original se conserva.')
                                break
                    part_aabb = object_world_aabb(part)
                if failure:
                    break

            if failure:
                raise RuntimeError(failure)

            # 4) Solo se copian shells que ya han sido verificados individualmente.
            # La limpieza del eje de la fresa se ejecuta después de los conectores
            # de refuerzo, en el paso de canales.
            safe_remove_by_name(IRR_COMBINED_TMP_NAME)
            final_temp = build_combined_mesh_object_world(
                context, guide_parts + processed_walls, IRR_COMBINED_TMP_NAME)
            if not _valid_obj(final_temp):
                failure = 'Could not assemble the cut guide and hollow walls'
                raise RuntimeError(failure)
            temp_objects.append(final_temp)

            final_report = get_mesh_solid_report(final_temp, max_polygons=1200000)
            if final_report.get('checked') and not final_report.get('solid'):
                failure = (
                    f'Non-solid final assembly: edges={final_report.get("bad_edges", 0)}, '
                    f'caras degeneradas={final_report.get("degenerate_faces", 0)}')
                raise RuntimeError(failure)

            # 5) Commit: originales solo se eliminan después de superar todo.
            old_guide_name = _safe_object_name(guide)
            wall_names = [_safe_object_name(wall) for wall in original_walls]
            if old_guide_name:
                _archive_current_guide_for_sleeve_rebuild(
                    props, reason='irrigation_commit')
            for wall_name in wall_names:
                if wall_name:
                    safe_remove_by_name(wall_name)

            # Elimina temporales salvo el resultado final.
            for obj in list(temp_objects):
                if obj is final_temp:
                    continue
                safe_remove_object(obj)

            final_temp.name = GUIDE_NAME
            final_temp.data.name = GUIDE_NAME + '_Mesh'
            _inherit_dsg_custom_properties(guide, final_temp)
            try:
                final_temp['DSG_irrigation_mode'] = 'ANALYTIC_HOLLOW_WALLS_GUIDE_DIFFERENCE'
                final_temp['DSG_irrigation_saved_path_count'] = int(len(entries))
                final_temp['DSG_irrigation_preview_wall_count'] = int(irrigation_preview_wall_count)
                final_temp['DSG_irrigation_state_reconciled'] = bool(irrigation_state_reconciled)
                final_temp['DSG_irrigation_cut_count'] = int(len(entries))
                final_temp['DSG_irrigation_component_operations'] = int(cut_operations)
                final_temp['DSG_irrigation_sleeve_boolean_guard_enabled'] = bool(irrigation_sleeve_guard_enabled(props))
                final_temp['DSG_irrigation_sleeve_components_protected'] = int(sleeve_guard_skips)
                final_temp['DSG_irrigation_sleeve_raycast_passes'] = 0
                final_temp['DSG_irrigation_model_cut_preflight_passes'] = int(model_cut_preflight_passes)
                final_temp['DSG_irrigation_model_cut_preflight_skips'] = int(model_cut_preflight_skips)
                final_temp['DSG_irrigation_model_cut_preflight_rejections'] = int(model_cut_preflight_rejections)
                final_temp['DSG_irrigation_model_cut_preflight_records'] = json.dumps(model_cut_preflight_records)
                final_temp['DSG_irrigation_sleeve_boolean_operations'] = int(sleeve_boolean_operations)
                final_temp['DSG_irrigation_sleeve_leak_rejections'] = int(sleeve_leak_rejections)
                final_temp['DSG_irrigation_c_continuity_repairs'] = int(sleeve_continuity_repairs)
                final_temp['DSG_irrigation_c_continuity_failures'] = int(sleeve_continuity_failures)
                final_temp['DSG_irrigation_wall_c_openings'] = int(irrigation_wall_c_openings)
                final_temp['DSG_irrigation_wall_c_repairs'] = int(irrigation_wall_c_repairs)
                final_temp['DSG_irrigation_c_manifold_sleeve_logic_safe'] = True
                final_temp['DSG_irrigation_c_manifold_preserved'] = True
                final_temp['DSG_irrigation_sleeve_boolean_policy'] = 'SLEEVE_NOT_THE_PREFLIGHT_TARGET'
                final_temp['DSG_irrigation_channel_model_policy'] = 'MODEL_CHANNEL_RAY_PREFLIGHT_BEFORE_FINAL_BOOLEAN'
                final_temp['DSG_irrigation_preflight_repaired_components'] = int(preflight_repaired_components)
                final_temp['DSG_irrigation_preflight_repaired_edges'] = int(preflight_repaired_edges)
                final_temp['DSG_irrigation_walls_preserved'] = True
                final_temp['DSG_irrigation_wall_boolean_used'] = bool(junction_operations)
                final_temp['DSG_irrigation_link_junction_operations'] = int(junction_operations)
                final_temp['DSG_irrigation_venturi_enabled'] = False
                final_temp['DSG_irrigation_venturi_throat_diameter'] = 0.0
                final_temp['DSG_irrigation_forced_balanced_wye'] = bool(links_by_source)
                final_temp['DSG_irrigation_balancing_nozzle_min_diameter'] = 0.72 if links_by_source else 0.0
                final_temp['DSG_irrigation_balancing_nozzle_max_diameter'] = 0.86 if links_by_source else 0.0
                final_temp['DSG_irrigation_balancing_mode'] = 'LENGTH_COMPENSATED_FIXED_ORIFICES' if links_by_source else 'NONE'
                final_temp['DSG_multishell_guide'] = True
                final_temp['DSG_needs_final_consolidation'] = True
                final_temp['DSG_drill_insertion_protected'] = False
                final_temp['DSG_drill_protection_operations'] = 0
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
            props.guide_obj = register_dsg_object(final_temp, ROLE_GUIDE, GUIDE_NAME)
            sealed_names = sync_irrigation_gate_metadata(props.guide_obj, props)
            if irrigation_sequential_enabled(props):
                refresh_irrigation_network_roles(props)
                network_note_en = ('sequential opening: initial sleeve open, linked sleeves '
                                   '0.10 mm frangible, trunk throats towards the initial sleeve')
                network_note_es = ('apertura secuencial: cilindro inicial abierto, vinculados con '
                                   'pared frangible 0,10 mm, estrechamientos del tronco hacia el inicial')
                try:
                    props.guide_obj['DSG_irrigation_network_json'] = json.dumps(
                        irrigation_network_summary(props))
                except Exception:
                    _DSG_LOG.debug("suppressed exception", exc_info=True)
            else:
                network_note_en = 'forced Y, full Ø1 mm lumen'
                network_note_es = 'Y forzada, lumen Ø1 mm completo'
            set_active(context, props.guide_obj)
            _dsg_report(self, {'INFO'}, f'Irrigation applied: {len(entries)} channel(s), '
                        f'{cut_operations} irrigation cut(s), '
                        f'{sleeve_boolean_operations} sleeve C-manifold cut(s); '
                        f'{sleeve_continuity_repairs} C-continuity repair(s); '
                        f'{irrigation_wall_c_openings} wall C-opening(s), '
                        f'{irrigation_wall_c_repairs} wall rescue(s); '
                        f'{model_cut_preflight_passes} model/channel preflight(s) passed; '
                        f'{preflight_repaired_components} component(s) repaired during preflight; '
                        f'{junction_operations} Link-wall opening operation(s); '
                        f'{network_note_en}; hollow walls preserved; '
                        f'{len(sealed_names)} export diaphragm(s) scheduled.', f'Irrigación aplicada: {len(entries)} conducto(s), '
                        f'{cut_operations} corte(s) de irrigación, '
                        f'{sleeve_boolean_operations} corte(s) de manifold en C sobre sleeve; '
                        f'{sleeve_continuity_repairs} reparación(es) de continuidad en C; '
                        f'{irrigation_wall_c_openings} apertura(s) en C sobre pared, '
                        f'{irrigation_wall_c_repairs} rescate(s) de pared; '
                        f'{model_cut_preflight_passes} verificación(es) modelo/canal superadas; '
                        f'{preflight_repaired_components} componente(s) reparado(s) en preflight; '
                        f'{junction_operations} apertura(s) de pared Link; '
                        f'{network_note_es}; paredes huecas preservadas; '
                        f'{len(sealed_names)} sello(s) programado(s) para la copia de exportación.')

            context.scene[WORKFLOW_IRRIGATION_RESOLVED_KEY] = True
            irrigation_signature = _workflow_object_signature(props.guide_obj)
            if _workflow_signature_changed(context.scene, WORKFLOW_IRRIGATION_SIGNATURE_KEY, irrigation_signature):
                _invalidate_workflow_after(context, STEP_IRRIGATION, reason='irrigation_geometry_changed')
            _workflow_store_signature(context.scene, WORKFLOW_IRRIGATION_SIGNATURE_KEY, irrigation_signature)
            try:
                props.guide_obj['DSG_irrigation_resolution'] = 'APPLIED'
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
            prepare_final_cut_references(context, props, show_passive=False)
            # Stay in Irrigation: the next sub-stage is the optional lateral
            # opening, now correctly applied to the already-irrigated guide.
            props.current_step = STEP_IRRIGATION
            return {'FINISHED'}

        except Exception as exc:
            for obj in list(temp_objects):
                safe_remove_object(obj)
            _dsg_report(self, {'ERROR'}, f'Irrigation canceled: {failure or str(exc)}. '
                        'The original guide and walls were preserved.', f'Irrigación cancelada: {failure or str(exc)}. '
                        'La guía y las paredes originales se conservaron.')
            return {'CANCELLED'}



# ─────────────────────────────────────────────────────────────
# Cadenas de refuerzo segmentadas de Ø2,5 mm con blends Coons
# ─────────────────────────────────────────────────────────────

