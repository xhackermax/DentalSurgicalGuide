# ─────────────────────────────────────────────────────────────
# Sequential-opening irrigation network (DSG 9.7.1)
#
#   entrada Ø4 ══Y(C)══▶══Y(B)══▶══ sleeve A   (abierto, se irriga primero)
#                 ║          ║
#              sleeve C   sleeve B              (pared frangible 0,10 mm, marcada)
#
# * The main channel starts at the initial sleeve A and ends in the air (inlet).
# * The user selects which implants are Linked to that trunk ("Link selected").
# * A stays open; every Linked sleeve gets a 0.10 mm marked frangible wall.
# * Opening order = from the Y nearest to A towards the Y nearest to the inlet.
# * Each Y throttles the trunk towards A (metering throat right after the
#   split) so the sleeve just perforated takes most of the water.
#
# Hydraulic maths lives in the pure module ``irrigation_network`` (unit
# tested without Blender); this fragment only adapts Blender data to it.
# ─────────────────────────────────────────────────────────────
from . import irrigation_network as _irr_net

IRR_LINK_CANDIDATE_KEY = 'DSG_irrigation_link_candidate'
IRR_OPEN_ORDER_KEY = 'DSG_irrigation_open_order'
IRR_NETWORK_ROLE_KEY = 'DSG_irrigation_network_role'
IRR_LINK_PLACEMENT_RULES = _irr_net.PlacementRules(
    min_from_source_sleeve_mm=5.0, min_from_inlet_mm=7.5, min_split_spacing_mm=4.5)


def irrigation_sequential_enabled(props):
    return bool(getattr(props, 'irr_sequential_opening', True))


def irrigation_network_policy(props):
    share = float(getattr(props, 'irr_open_branch_share', 0.75) or 0.75)
    return _irr_net.NetworkPolicy(target_open_branch_share=max(0.55, min(0.90, share)))


def _xyz(point):
    return (float(point[0]), float(point[1]), float(point[2]))


def _entry_lumen_samples(entry, props, include_overshoot=False):
    entry_props, _parameters = _irrigation_entry_effective_props(props, entry)
    return build_irrigation_lumen_samples_from_controls(
        entry.get('points', []), entry_props, include_overshoot=include_overshoot)


def _as_network_samples(samples):
    return [(_xyz(point), float(radius)) for point, radius in samples]


def _entry_name(entry):
    name = str(entry.get('implant_name') or '')
    if not name and _valid_obj(entry.get('implant')):
        name = entry['implant'].name
    return name or f"channel_{int(entry.get('index', -1)) + 1}"


def _link_split_arclength(trunk_points, link_entry):
    meta = _midpoint_wye_metadata(link_entry)
    if meta is None:
        return None
    s, _distance = _irr_net.project_arclength(trunk_points, _xyz(meta['split']))
    return s


def order_links_along_trunk(source_entry, link_entries, props):
    """Links sorted by the position of their Y from sleeve A towards the inlet."""
    links = list(link_entries or [])
    if len(links) < 2:
        return links
    try:
        trunk = _entry_lumen_samples(source_entry, props)
        points = [_xyz(p) for p, _r in trunk]
        keyed = []
        for position, link in enumerate(links):
            s = _link_split_arclength(points, link)
            keyed.append((float('inf') if s is None else s, position, link))
        return [link for _s, _pos, link in sorted(keyed, key=lambda item: (item[0], item[1]))]
    except Exception as exc:
        _DSG_LOG.warning('could not order links along trunk: %s', exc, exc_info=True)
        return links


def design_irrigation_network(props, source_entry, link_entries):
    """Pure hydraulic design for one trunk + its Links. Returns (design, splits)."""
    trunk = _as_network_samples(_entry_lumen_samples(source_entry, props))
    points = [p for p, _r in trunk]
    branches, splits = [], {}
    for link in link_entries:
        meta = _midpoint_wye_metadata(link)
        if meta is None:
            continue
        name = _entry_name(link)
        s, _d = _irr_net.project_arclength(points, _xyz(meta['split']))
        link_samples = reshape_link_samples_into_midpoint_wye(
            _entry_lumen_samples(link, props), link)
        branches.append(_irr_net.Branch(
            name=name, split_s_mm=s,
            link_resistance=_irr_net.resistance(_as_network_samples(link_samples))))
        splits[name] = _xyz(meta['split'])
    design = _irr_net.design_sequential_network(
        _entry_name(source_entry), trunk, branches, irrigation_network_policy(props))
    return design, splits


def sequential_wye_balances(source_entry, wye_specs, props):
    design, splits = design_irrigation_network(props, source_entry, wye_specs)
    throats = [{
        'branch': j.branch,
        'split': list(splits[j.branch]),
        'diameter': float(j.throat.diameter_mm),
        'length': float(j.throat.length_mm),
    } for j in design.junctions if j.throat.active and j.branch in splits]
    for warning in design.warnings:
        _DSG_LOG.warning('sequential irrigation: %s', warning)
    return {'mode': 'SEQUENTIAL_OPENING', 'design': design.as_dict(), 'throats': throats}


def apply_sequential_trunk_throats(samples, balances):
    """Narrow the trunk just downstream of each Y (towards sleeve A)."""
    policy = (balances.get('design') or {}).get('policy') or {}
    shaped = [(Vector(point), float(radius)) for point, radius in samples]
    for throat in balances.get('throats') or []:
        shaped = apply_balancing_nozzle_after_split(
            shaped, [Vector(throat['split'])],
            throat_diameter=float(throat['diameter']),
            throat_length=float(throat['length']),
            inlet_transition=float(policy.get('inlet_transition_mm', 0.35)),
            outlet_transition=float(policy.get('outlet_transition_mm', 0.50)),
            split_clearance=float(policy.get('split_clearance_mm', 0.70)))
    return shaped


def _irrigation_networks(props):
    """[(source_entry, [link_entries…])] for every main channel with Links."""
    entries = load_irrigation_path_entries(props)
    links_by_source = {}
    for entry in entries:
        if bool(entry.get('link', False)):
            links_by_source.setdefault(int(entry.get('source_index', -1)), []).append(entry)
    return [(entry, links_by_source.get(int(entry.get('index', -1)), []))
            for entry in entries if not bool(entry.get('link', False))]


def refresh_irrigation_network_roles(props):
    """Initial sleeve OPEN (#1); Linked sleeves FRANGIBLE, numbered by opening order."""
    if not irrigation_sequential_enabled(props):
        return []
    changed = []
    summary = []
    for source, links in _irrigation_networks(props):
        if not links:
            continue
        try:
            design, _splits = design_irrigation_network(props, source, links)
            order = list(design.order)
            shares = {j.branch: j.predicted_share_at_opening for j in design.junctions}
        except Exception as exc:
            _DSG_LOG.warning('network design failed, using creation order: %s', exc, exc_info=True)
            order = [_entry_name(source)] + [_entry_name(link) for link in links]
            shares = {}
        for position, name in enumerate(order, start=1):
            implant = bpy.data.objects.get(name)
            if not is_valid_implant_obj(implant):
                continue
            sealed = position > 1
            if irrigation_implant_is_sealed(implant) != sealed:
                changed.append(implant.name)
            set_irrigation_implant_sealed(implant, sealed)
            implant[IRR_OPEN_ORDER_KEY] = int(position)
            implant[IRR_NETWORK_ROLE_KEY] = 'SOURCE_OPEN' if position == 1 else 'LINKED_FRANGIBLE'
            implant['DSG_irrigation_internal_marker'] = bool(sealed)
            if name in shares:
                implant['DSG_irrigation_predicted_share_at_opening'] = float(shares[name])
        summary.append(order)
    guide = get_active_guide_obj(props)
    if _valid_obj(guide):
        sync_irrigation_gate_metadata(guide, props)
        guide['DSG_irrigation_sequential_order'] = json.dumps(summary)
    return changed


def irrigation_network_summary(props):
    """Serializable design of every network (used by the export report and UI)."""
    out = []
    for source, links in _irrigation_networks(props):
        if not links:
            continue
        try:
            design, _splits = design_irrigation_network(props, source, links)
            out.append(design.as_dict())
        except Exception as exc:
            out.append({'source': _entry_name(source), 'error': str(exc)})
    return out


def _network_source_entry(props):
    """The trunk that 'Link selected' attaches to: the active implant's main
    channel, or the only main channel in the case."""
    sources = [entry for entry in load_irrigation_path_entries(props)
               if not bool(entry.get('link', False))]
    if len(sources) == 1:
        return sources[0], ''
    active = getattr(props, 'implant_obj', None)
    for entry in sources:
        if _valid_obj(active) and _entry_name(entry) == active.name:
            return entry, ''
    if not sources:
        return None, 'NO_MAIN_CHANNEL'
    return None, 'AMBIGUOUS_MAIN_CHANNEL'


def auto_irrigation_link_points(props, source_entry, target_implant, occupied_s=()):
    """Sleeve point + trunk point for an automatic Link.

    The Y is placed at the trunk point closest to the target sleeve, shifted if
    needed to stay clear of sleeve A, of the Ø4 inlet and of the other Ys.
    Returns ``((sleeve_point, channel_point, tangent), s, error)``.
    """
    entry_props = irrigation_props_overlay(props, source_entry.get('parameters', {}))
    centerline = smooth_irrigation_centerline_controls(
        [Vector(p) for p in source_entry.get('points', [])], entry_props)
    points = [_xyz(p) for p in centerline]
    if len(points) < 2:
        return None, None, 'main channel has no path'
    total = _irr_net.arclengths(points)[-1]
    center = get_sleeve_center_world(props, target_implant)
    axis = get_sleeve_axis_world(props, target_implant)
    s_wanted, _d = _irr_net.project_arclength(points, _xyz(center))
    s = _irr_net.choose_split_arclength(s_wanted, occupied_s, total, IRR_LINK_PLACEMENT_RULES)
    if s is None:
        return None, None, 'the main channel has no free segment for another Y'
    channel_point, tangent = _irr_net.point_at_arclength(points, s)
    channel_point, tangent = Vector(channel_point), Vector(tangent)

    radial = channel_point - center
    radial -= axis * radial.dot(axis)
    if radial.length < 1e-6:
        basis_u, _basis_v, _axis = build_axis_basis(axis)
        radial = basis_u
    radial.normalize()
    _inner_r, outer_r, _wall = _sleeve_radii_from_props(props)
    sleeve_point = center + radial * outer_r
    if sleeve_sidewall_guard_enabled(props):
        outer_tube = float(props.irr_inner_diameter) * 0.5 + float(props.irr_wall_thickness)
        port = get_sleeve_apical_port_geometry(
            sleeve_point, props, target_implant, outer_tube_radius=outer_tube)
        if port is None:
            return None, None, 'no safe lateral port on the sleeve'
        sleeve_point = Vector(port['external_anchor'])
    return (sleeve_point, channel_point, tangent), s, ''


def link_irrigation_implants(context, props, implants):
    """Link several implants to the main channel. Returns (linked, failures)."""
    source, reason = _network_source_entry(props)
    if source is None:
        raise RuntimeError(reason)
    source_name = _entry_name(source)
    entries = load_irrigation_path_entries(props)
    entry_props = irrigation_props_overlay(props, source.get('parameters', {}))
    trunk_points = [_xyz(p) for p in smooth_irrigation_centerline_controls(
        [Vector(p) for p in source.get('points', [])], entry_props)]
    occupied = []
    for entry in entries:
        if bool(entry.get('link', False)) and int(entry.get('source_index', -1)) == int(source.get('index', -1)):
            s = _link_split_arclength(trunk_points, entry)
            if s is not None:
                occupied.append(s)

    # Place candidates in trunk order so each Y lands next to its own sleeve.
    todo = []
    for implant in implants:
        if not is_valid_implant_obj(implant) or implant.name == source_name:
            continue
        if _implant_has_irrigation_entry(entries, implant):
            continue
        s_wanted, _d = _irr_net.project_arclength(trunk_points, _xyz(get_sleeve_center_world(props, implant)))
        todo.append((s_wanted, implant))

    linked, failures = [], []
    for _s, implant in sorted(todo, key=lambda item: item[0]):
        points, s, error = auto_irrigation_link_points(props, source, implant, occupied)
        if points is None:
            failures.append((implant.name, error))
            continue
        sleeve_point, channel_point, tangent = points
        source_entry = dict(source)
        source_entry['link_source_tangent'] = Vector(tangent)
        ok, message_en, _message_es = commit_irrigation_link(
            context, props, implant, sleeve_point, source_entry, channel_point)
        if ok:
            linked.append(implant.name)
            occupied.append(s)
        else:
            failures.append((implant.name, message_en))
    auto_assign_irrigation_gate_defaults(props)
    return linked, failures


def irrigation_link_candidates(props):
    """Implants that can still be Linked to the main channel."""
    source, _reason = _network_source_entry(props)
    entries = load_irrigation_path_entries(props)
    source_name = _entry_name(source) if source else ''
    return [implant for implant in get_all_implant_objects(props)
            if implant.name != source_name and not _implant_has_irrigation_entry(entries, implant)]


class DSG_OT_ToggleIrrigationLinkCandidate(Operator):
    bl_idname = 'dsg.toggle_irrigation_link_candidate'
    bl_label = 'Select Implant for Link'
    bl_description = 'Mark / unmark this implant to be linked to the main irrigation channel'
    bl_options = {'REGISTER', 'UNDO'}

    implant_name: StringProperty(default='')

    def execute(self, context):
        implant = bpy.data.objects.get(self.implant_name) if self.implant_name else None
        if not is_valid_implant_obj(implant):
            _dsg_report(self, {'ERROR'}, 'Implant not found', 'No se encontró el implante')
            return {'CANCELLED'}
        implant[IRR_LINK_CANDIDATE_KEY] = not bool(implant.get(IRR_LINK_CANDIDATE_KEY, False))
        return {'FINISHED'}


class DSG_OT_LinkSelectedIrrigation(Operator):
    bl_idname = 'dsg.link_selected_irrigation'
    bl_label = 'Link Selected Implants'
    bl_description = ('Link every selected implant to the main channel. The initial sleeve stays open; '
                      'linked sleeves get a marked 0.10 mm frangible wall, numbered by opening order')
    bl_options = {'REGISTER', 'UNDO'}

    implant_names: StringProperty(
        name='Implants', default='',
        description='Optional comma-separated implant names (default: implants marked in the panel)')

    def execute(self, context):
        if not _require_workflow_stage(
                self, context, STEP_IRRIGATION,
                action_en='Cannot link irrigation',
                action_es='No se puede vincular la irrigación'):
            return {'CANCELLED'}
        props = context.scene.dsg_props
        if get_pending_irrigation_preview(props):
            _dsg_report(self, {'ERROR'}, 'Confirm the pending channel first',
                        'Confirma primero el conducto pendiente')
            return {'CANCELLED'}
        if self.implant_names.strip():
            implants = [bpy.data.objects.get(name.strip())
                        for name in self.implant_names.split(',') if name.strip()]
        else:
            implants = [obj for obj in irrigation_link_candidates(props)
                        if bool(obj.get(IRR_LINK_CANDIDATE_KEY, False))]
        implants = [obj for obj in implants if is_valid_implant_obj(obj)]
        if not implants:
            _dsg_report(self, {'WARNING'}, 'Select at least one implant to link',
                        'Selecciona al menos un implante para vincular')
            return {'CANCELLED'}
        try:
            linked, failures = link_irrigation_implants(context, props, implants)
        except RuntimeError as exc:
            reason = str(exc)
            if reason == 'AMBIGUOUS_MAIN_CHANNEL':
                _dsg_report(self, {'ERROR'},
                            'Several main channels: choose the initial implant as active implant',
                            'Hay varios conductos principales: elige el implante inicial como implante activo')
            else:
                _dsg_report(self, {'ERROR'}, 'Draw the main channel first (sleeve → air)',
                            'Dibuja primero el conducto principal (cilindro → aire)')
            return {'CANCELLED'}
        for implant in implants:
            try:
                implant[IRR_LINK_CANDIDATE_KEY] = False
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
        if failures:
            detail = '; '.join(f'{name}: {why}' for name, why in failures)
            _dsg_report(self, {'WARNING'},
                        f'Linked {len(linked)} · not linked: {detail}',
                        f'Vinculados {len(linked)} · sin vincular: {detail}')
        if not linked:
            return {'CANCELLED'}
        order = []
        for name in linked:
            obj = bpy.data.objects.get(name)
            order.append(f"{int(obj.get(IRR_OPEN_ORDER_KEY, 0))}º {name}" if obj else name)
        _dsg_report(self, {'INFO'},
                    'Linked · opening order: ' + ', '.join(sorted(order)),
                    'Vinculados · orden de apertura: ' + ', '.join(sorted(order)))
        return {'FINISHED'}


SEQUENTIAL_IRRIGATION_CLASSES = (
    DSG_OT_ToggleIrrigationLinkCandidate,
    DSG_OT_LinkSelectedIrrigation,
)
