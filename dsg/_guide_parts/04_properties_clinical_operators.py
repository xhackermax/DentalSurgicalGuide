class DSG_ContourPoint(PropertyGroup):
    co: FloatVectorProperty(size=3, subtype='XYZ')




def _irrigation_sleeve_channel_items(self, context):
    """Language-aware labels for the irrigation channel mode dropdown.

    The stored identifiers remain stable (C / DIRECT), but the visible menu never
    mixes English labels in Spanish mode or Spanish labels in English mode.
    """
    props = self
    try:
        if props is None and context is not None:
            props = context.scene.dsg_props
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    if _dsg_spanish(props):
        return (
            ('C', "Canal en C", "Colector interno abierto en forma de C con dos salidas opuestas"),
            ('DIRECT', "Canal directo", "Canal radial único desde el conducto externo hasta la luz del cilindro"),
        )
    return (
        ('C', "C channel", "Open C-shaped internal manifold with two opposed outlets"),
        ('DIRECT', "Direct channel", "Single direct radial channel from the external tube into the sleeve lumen"),
    )

_RETENTION_PREVIEW_REFRESH_PENDING = False
_RETENTION_PREVIEW_REFRESH_RUNNING = False

# The expensive BVH survey is computed once for a model + insertion axis and is
# shared by all three presets.  Selecting a preset only changes visibility.
_RETENTION_BVH_CACHE = {}


def _retention_cache_key(source_obj, axis):
    try:
        matrix_values = tuple(round(float(v), 6) for row in source_obj.matrix_world for v in row)
    except Exception:
        matrix_values = ()
    axis = Vector(axis).normalized()
    try:
        anatomy_limit = int(source_obj.get('DSG_anatomy_original_vertex_count', len(source_obj.data.vertices)))
    except Exception:
        anatomy_limit = len(source_obj.data.vertices)
    reference = ()
    axis_owner = get_axis_empty()
    if axis_owner is not None:
        try:
            raw = axis_owner.get(VIEW_REFERENCE_LOCATION_KEY)
            if raw is not None:
                reference = tuple(round(float(value), 5) for value in raw[:3])
        except Exception:
            reference = ()
    geometry_signature = ()
    try:
        vertices = source_obj.data.vertices
        count = len(vertices)
        if count:
            sample_count = min(12, count)
            indices = sorted({int(round(i * (count - 1) / max(1, sample_count - 1)))
                              for i in range(sample_count)})
            geometry_signature = tuple(
                round(float(component), 5)
                for index in indices
                for component in vertices[index].co
            )
    except Exception:
        geometry_signature = ()
    return (
        int(RETENTION_SURVEY_ENGINE_VERSION),
        int(source_obj.data.as_pointer()),
        len(source_obj.data.vertices),
        len(source_obj.data.polygons),
        matrix_values,
        tuple(round(float(v), 6) for v in axis),
        int(anatomy_limit),
        geometry_signature,
        reference,
    )


def _clear_retention_geometry_cache():
    _RETENTION_BVH_CACHE.clear()


def _tag_dsg_view3d_redraw():
    try:
        wm = getattr(bpy.context, 'window_manager', None)
        for window in getattr(wm, 'windows', ()):
            screen = getattr(window, 'screen', None)
            for area in getattr(screen, 'areas', ()):
                if area.type == 'VIEW_3D':
                    area.tag_redraw()
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)


def _on_retention_level_change(self, context):
    """Keep profile changes lightweight; the explicit preset buttons rebuild."""
    try:
        _tag_dsg_view3d_redraw()
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)


def _on_retention_percent_change(self, context):
    # Compatibility callback for .blend files created by v8.0.33-35.
    return None


class DSG_Props(PropertyGroup):
    current_step:        IntProperty(default=0, min=0, max=TOTAL_STEPS - 1, update=_on_current_step_update)
    mpr_target_implant: EnumProperty(
        name='Implant for MPR',
        description='Implant used to position Z and orient the vertical plane around the DICOM centre',
        items=_mpr_implant_items,
        update=_on_mpr_target_implant_change)
    precision_ortho_lock: BoolProperty(
        name="Orthographic Precision View", default=True,
        description="Internal DSG precision projection control",
        options={'HIDDEN'},
        update=_on_precision_ortho_lock_update)
    ui_language: EnumProperty(
        name="Idioma",
        items=core.LANGUAGE_ITEMS,
        get=_language_get,
        set=_language_set,
        description="Shared language for DICOM, Alignment and DSG / Idioma compartido",
    )
    drawing_active:      BoolProperty(default=False)
    organic_use_path_hooks: BoolProperty(
        name="Bezier Path + Hooks", default=True,
        description="Creates the irrigation path with a Bezier curve and fixes the contact using a Hook")
    organic_path_resolution: IntProperty(
        name="Path Resolution", default=12, min=4, max=32,
        description="Lengthinal resolution of the temporary path. 10-16 provides smoothness without creating an excessive mesh")
    organic_tcb_tension: FloatProperty(
        name="TCB Tension", default=-0.10, min=-0.60, max=0.60, precision=2,
        description="Kochanek-Bartels: negative values relax the curve; positive values pull it closer to the points")
    organic_tcb_bias: FloatProperty(
        name="TCB bias", default=0.0, min=-0.35, max=0.35, precision=2,
        description="Kochanek-Bartels: shifts influence toward the previous or next segment")
    organic_tcb_continuity: FloatProperty(
        name="TCB Continuity", default=0.0, min=-0.40, max=0.40, precision=2,
        description="Kochanek-Bartels: controls directional continuity between the anchor entry and exit")
    organic_tcb_contact_scale: FloatProperty(
        name="Contact Smoothness", default=0.70, min=0.10, max=1.80, precision=2,
        description="Relative handle length at the sleeve. Lower = shorter contact; higher = smoother transition")
    # ── Irrigation ───────────────────────────────────────────
    irr_drawing_active:  BoolProperty(default=False)
    irr_chain_count:     IntProperty(default=0)

    # ── Conectores de refuerzo Catmull-Rom ──────────────────
    reinforcement_count: IntProperty(
        name="Confirmed Connectors", default=0, min=0)
    reinforcement_preview_obj: PointerProperty(
        name="Connector Preview",
        type=bpy.types.Object,
        description="Pending Catmull-Rom reinforcement path")
    reinforcement_surface_offset: FloatProperty(
        name="Surface Offset (mm)", default=0.15, min=-0.20, max=0.60, precision=2,
        description="Path position relative to the surface. With a 1 mm radius, 0.15 mm maintains broad overlap with the guide")
    reinforcement_endpoint_embed: FloatProperty(
        name="Endpoint Embed (mm)", default=0.35, min=0.10, max=0.90, precision=2,
        description="Embeds the endpoints into the guide to ensure a strong connection")
    reinforcement_arch_height: FloatProperty(
        name="Arch Height (mm)", default=0.0, min=0.0, max=5.00, precision=2,
        description="Internal compatibility setting; reinforcement is generated with a fixed 0 mm arch height")
    reinforcement_curve_resolution: IntProperty(
        name="Lengthinal Smoothness", default=16, min=6, max=32,
        description="Samples per Catmull-Rom segment. Higher values create a smoother path")
    reinforcement_bevel_resolution: IntProperty(
        name="Circular Resolution", default=6, min=3, max=10,
        description="Circular resolution of the fixed 2.5 mm diameter tube")

    # ── Microtornillos en el frame ──────────────────────────
    microscrew_count: IntProperty(
        name="Confirmed Microscrews", default=0, min=0)
    microscrew_preview_obj: PointerProperty(
        name="Microscrew Preview",
        type=bpy.types.Object,
        description="Pending microscrew support tube and sleeve")
    microscrew_diameter: FloatProperty(
        name="Microscrew Diameter (mm)", default=MICROSCREW_DIAMETER_DEFAULT_MM,
        min=MICROSCREW_DIAMETER_MIN_MM, max=MICROSCREW_DIAMETER_MAX_MM, precision=2,
        description="Real body diameter of the planned microscrew; the guide lumen and visual screw follow this value")
    microscrew_length: FloatProperty(
        name="Microscrew Length (mm)", default=MICROSCREW_LENGTH_DEFAULT_MM,
        min=MICROSCREW_LENGTH_MIN_MM, max=MICROSCREW_LENGTH_MAX_MM, precision=1,
        description="Active length from the sleeve stop plane to the microscrew tip")
    microscrew_support_diameter: FloatProperty(
        name="Support Tube Diameter (mm)", default=3.5, min=1.0, max=6.0, precision=2,
        description="Diameter of each thick solid connector in the three-point microscrew placement")
    microscrew_segments: IntProperty(
        name="Circular Resolution", default=32, min=16, max=64,
        description="Number of circular segments in the sleeve and support tube")
    microscrew_frame_embed: FloatProperty(
        name="Frame Embed (mm)", default=0.45, min=0.10, max=1.50, precision=2,
        description="Embeds the tube start into the frame to ensure later fusion")
    microscrew_sleeve_overlap: FloatProperty(
        name="Sleeve Overlap (mm)", default=0.50, min=0.20, max=1.00, precision=2,
        description="Radial tube penetration into the 1.5 mm wall without reaching the 2 mm lumen")
    microscrew_records_json: StringProperty(
        name="Microscrew Placements", default="[]",
        description="Persistent axes and positions used to rebuild the animation after adding the sleeves to the frame")
    microscrew_animation_distance: FloatProperty(
        name="Screw Travel (mm)", default=15.0, min=3.0, max=100.0, precision=1,
        description="Initial screw distance above the sleeve, following its exact axis")
    microscrew_animation_start_frame: IntProperty(
        name="Start", default=1, min=1, max=10000,
        description="Frame where the screw starts away from the sleeve")
    microscrew_animation_end_frame: IntProperty(
        name="Stop", default=60, min=2, max=10000,
        description="Frame where the STL conical head seats on the anatomical sleeve seat")
    # ── Fresa visual animada del paso 8 ─────────────────────
    drill_animation_distance: FloatProperty(
        name="Animation Travel (mm)", default=25.0, min=5.0, max=100.0, precision=1,
        description="Initial drill distance above the sleeve, measured along the implant axis")
    drill_animation_start_frame: IntProperty(
        name="Start Frame", default=1, min=1, max=10000,
        description="Frame where the drill starts away from the sleeve")
    drill_animation_end_frame: IntProperty(
        name="Stop Frame", default=60, min=2, max=10000,
        description="Frame where the small flat face behind the guide cylinder contacts the occlusal sleeve face")
    irr_preview_obj: PointerProperty(
        name="Irrigation Preview",
        type=bpy.types.Object,
        description="Pending outer wall; the internal path is edited using a native curve")
    irr_inner_diameter:  FloatProperty(
        name="Inner Diameter (mm)", default=4.0, min=0.5, max=10.0,
        description="Inner diameter of the irrigation channel")
    irr_wall_thickness:  FloatProperty(
        name="Wall Thickness (mm)", default=IRRIGATION_SLIM_WALL_THICKNESS_DEFAULT_MM, min=0.3, max=5.0,
        description="Wall thickness of the irrigation tube; the sleeve fusion remains locally wider")
    irr_paths_json:      StringProperty(
        name="Irrigation Paths", default="[]",
        description="Confirmed internal paths; combined into one cutter at the end")
    irr_cut_overshoot: FloatProperty(
        name="Cutter Overshoot (mm)", default=1.5, min=0.2, max=6.0,
        description="How far the initial channel cutter extends to ensure a clean Boolean")
    irr_wall_exit_overshoot: FloatProperty(
        name="Sleeve Lumen Entry (mm)", default=0.18, min=0.04, max=0.60, precision=2,
        description="Small radial overshoot into the sleeve lumen to prevent membranes without extending toward the implant")
    irr_direct_sleeve_lumen_overlap: FloatProperty(
        name="Direct Sleeve Entry (mm)", default=1.0, min=0.2, max=2.0, precision=2,
        description="DIRECT channel stops this distance inside the sleeve lumen instead of advancing to the implant axis")
    irr_curve_smooth_iters: FloatProperty(
        name="Organic Smoothing", default=2.0, min=0.0, max=4.0,
        description="Compatibility: alternative smoothing if Path + Kochanek-Bartels cannot be evaluated")
    irr_bevel_resolution: IntProperty(
        name="Tube Resolution", default=8, min=2, max=16,
        description="Circular resolution of the organic tube")
    irr_terminal_depth: FloatProperty(
        name="Apical Depth (mm)", default=2.5, min=0.5, max=8.0,
        description="How far the channel advances along the implant axis beyond the sleeve center")
    irr_entry_length: FloatProperty(
        name="Extra External Length (mm)", default=1.2, min=0.2, max=6.0,
        description="Additional segment outside the cone; the actual initial segment uses at least the sleeve height")
    irr_sleeve_overlap: FloatProperty(
        name="Sleeve Overlap (mm)", default=1.2, min=0.2, max=4.0,
        description="How far the outer tube enters the sleeve to create a true fused connection")
    irr_junction_blend: FloatProperty(
        name="Junction Blend (mm)", default=0.0, min=0.0, max=2.0,
        description="Optional local blend; 0 prevents bulges around the funnel")
    irr_sequential_opening: BoolProperty(
        name="Sequential opening",
        default=True,
        description=("Linked irrigation: the initial sleeve stays open, linked sleeves get a marked "
                     "0.10 mm frangible wall and every Y throttles the trunk towards the initial "
                     "sleeve so each newly perforated sleeve takes most of the water"))
    irr_open_branch_share: FloatProperty(
        name="Water to newly opened sleeve",
        default=0.75, min=0.55, max=0.90, subtype='FACTOR',
        description="Target fraction of the flow reaching a Y that goes to the sleeve just perforated")
    irr_funnel_enabled: BoolProperty(
        name="Create Sleeve Funnel", default=True,
        description="The first irrigation point creates a cone whose length equals the sleeve height" )
    irr_sleeve_channel_mode: StringProperty(
        name="Irrigation Internal Mode",
        default='C',
        description="Internal irrigation mode stored as C or DIRECT. UI uses localized buttons instead of a Blender EnumProperty to avoid registration issues.")
    irr_funnel_outer_diameter: FloatProperty(
        name="Sleeve Outlet Ø (mm)", default=1.0, min=0.05, max=12.0,
        description="Actual outlet diameter at the sleeve wall; it can be smaller than 1 mm and is not enlarged by the internal channel")
    irr_taper_length: FloatProperty(
        name="Taper Length (mm)", default=0.0, min=0.0, max=30.0,
        description="0 = automatic: uses the sleeve height. The taper is measured along the tube curve, not as a straight cone")
    irr_funnel_depth: FloatProperty(
        name="Nozzle Depth (mm)", default=0.0, min=0.0, max=20.0,
        description="0 = automatic: the narrow nozzle crosses the sleeve wall before widening progressively")
    irr_lumen_sample_step: FloatProperty(
        name="Lumen Sampling (mm)", default=0.55, min=0.15, max=1.50,
        description="Distance between internal cutter rings. Higher = faster; lower = smoother but heavier")
    irr_lumen_subdivision: IntProperty(
        name="Lumen Subdivision", default=0, min=0, max=2,
        description="Subdivides the continuous cutter before the Boolean. 0 = recommended fast mode; 1-2 = smoother but much heavier")
    irr_flow_sim_speed: FloatProperty(
        name="Tracer Speed (mm/s)", default=10.0, min=0.5, max=80.0, precision=1,
        description="Visual filling speed for the final volumetric water preview. This does not impose a physical pump pressure")
    irr_flow_sim_count: IntProperty(
        name="Tracer Count", default=32, min=4, max=160,
        description="Legacy setting kept for compatibility with older scenes")
    irr_flow_sim_radius: FloatProperty(
        name="Tracer Radius (mm)", default=0.16, min=0.05, max=0.45, precision=2,
        description="Legacy setting kept for compatibility with older scenes")
    irr_flow_sim_start_frame: IntProperty(
        name="Simulation Start", default=1, min=1, max=10000,
        description="First frame of the irrigation tracer simulation")
    irr_flow_cfd_resolution: IntProperty(
        name="Cascade Resolution", default=48, min=32, max=96,
        description="Resolution of each small local Replay domain. 48 is recommended for a fast continuous waterfall preview")
    irr_flow_cfd_duration: IntProperty(
        name="Cascade Duration (frames)", default=120, min=24, max=600,
        description="Timeline duration of the continuous inflow waterfall preview")
    irr_flow_cfd_jet_speed: FloatProperty(
        name="Cascade Velocity", default=1.65, min=0.10, max=8.0, precision=2,
        description="Initial velocity of the continuous inflow, combining the real outlet direction with the apical sleeve direction")
    irr_flow_cfd_margin: FloatProperty(
        name="Local Domain Margin (mm)", default=1.6, min=0.8, max=5.0, precision=1,
        description="Small margin around each sleeve cascade. Lower values calculate faster")
    irr_spray_length: FloatProperty(
        name="Spray Reach (mm)", default=10.0, min=1.0, max=20.0, precision=1,
        description="Approximate external reach of each water spray leaving the sleeve outlets")
    irr_spray_spread: FloatProperty(
        name="Spray Spread (deg)", default=24.0, min=0.0, max=60.0, precision=1,
        description="Fan opening used to create the sprinkler-like water spray")
    irr_spray_streams: IntProperty(
        name="Particle Density", default=8, min=1, max=8,
        description="Density multiplier for the lightweight core droplets and fine mist at each sleeve outlet")
    irr_spray_fill_frames: IntProperty(
        name="Water Fill Frames", default=6, min=1, max=30,
        description="Frames used to visibly fill the internal water path before the external spray appears")

    show_parallel_tools: BoolProperty(
        name="Parallelization", default=False,
        description="Shows or hides optional parallelization tools")
    show_sleeve_window_options: BoolProperty(
        name="Lateral Opening Details", default=False,
        description="Shows the tertiary controls used to fine-tune the lateral sleeve opening")
    show_irrigation_channel_options: BoolProperty(
        name="Irrigation Channel Details", default=False,
        description="Shows the tertiary DIRECT/C selection and channel dimensions")
    show_reinforcement_options: BoolProperty(
        name="Reinforcement Details", default=False,
        description="Shows tertiary reinforcement dimensions")
    show_sequence_panel: BoolProperty(
        name="Insertion Animation", default=False,
        description="Shows or hides the sequential screw and drill animation controls")
    show_name_tools: BoolProperty(
        name="Name and Engraving", default=False,
        description="Shows or hides optional name placement and engraving tools")
    show_final_visibility: BoolProperty(
        name="Visibility", default=False,
        description="Shows or hides the model visibility control in the final step")
    show_reset_flow: BoolProperty(
        name="Back", default=False,
        description="Shows or hides the action used to return the current clinical step to its initial state")
    show_advanced_tools: BoolProperty(
        name="Legacy UI State", default=False,
        description="Hidden compatibility state from older DSG files",
        options={'HIDDEN'})
    model_obj:   PointerProperty(name="Model",   type=bpy.types.Object)
    implant_obj: PointerProperty(name="Active Implant", type=bpy.types.Object)
    parallel_master_implant: PointerProperty(
        name="Master Implant",
        type=bpy.types.Object,
        description="Implant whose angulation will be copied by the other implants")
    parallel_divergence_tolerance: FloatProperty(
        name="Divergence Tolerance (°)", default=5.0, min=0.0, max=20.0, precision=1,
        description="Absolute limit allowed for the individual offset stored in each DSG_Implant")
    frame_obj:   PointerProperty(name="Frame",    type=bpy.types.Object)
    guide_obj:   PointerProperty(name="Guide",     type=bpy.types.Object)

    contour_points: CollectionProperty(type=DSG_ContourPoint)

    # Parámetros guía · blockout por rayos desde la vista (núcleo v7 restaurado)
    blockout_relief: FloatProperty(
        name="Retención axial residual (mm)", default=0.10, min=0.0, max=0.30, precision=3,
        description="Separación axial que queda sin rellenar respecto al bloqueo completo; un valor mayor puede conservar más retención")
    blockout_capture_view_on_generate: BoolProperty(
        name="Usar vista actual al generar", default=True,
        description="Recaptura la dirección exacta de la Vista 3D al calcular el modelo retentivo",
        options={'HIDDEN'})
    blockout_min_hit_distance: FloatProperty(
        name="Ignorar impactos menores de (mm)", default=BLOCKOUT_MIN_HIT_DEFAULT_MM,
        min=0.002, max=1.0, precision=3,
        description="Evita autoimpactos numéricos sobre la misma superficie o triángulos vecinos",
        options={'HIDDEN'})
    blockout_max_hit_distance: FloatProperty(
        name="Alcance máximo del rayo (mm)", default=BLOCKOUT_MAX_HIT_DEFAULT_MM,
        min=1.0, max=100.0, precision=1,
        description="Evita que un rayo alcance superficies dentales demasiado alejadas",
        options={'HIDDEN'})
    blockout_last_stats: StringProperty(
        name="Último diagnóstico blockout", default="",
        description="Resumen del último cálculo de raycast",
        options={'HIDDEN'})
    blockout_seating_summary: StringProperty(
        name="Validación de asiento", default="",
        description="Resultado de la comprobación geométrica del asiento",
        options={'HIDDEN'})
    blockout_local_relief_mm: FloatProperty(
        name="Alivio local (mm)", default=0.06, min=0.01, max=0.30, precision=3,
        description="Avance axial aplicado solo a los vértices seleccionados del blockout; el IOS nunca se modifica")
    retention_level: EnumProperty(
        name="Retention profile",
        description="Evidence-informed whole-arch coronary-perimeter profile",
        items=(
            ('LOW', 'Lower retention', 'More internal clearance and less undercut engagement'),
            ('AUTO', 'Automatic', 'Adaptive whole-arch fit based on the measured coronary perimeter'),
            ('HIGH', 'Greater retention', 'Less clearance and more undercut engagement; may require a seating warning'),
        ),
        default='AUTO',
        update=_on_retention_level_change)
    retention_percent: FloatProperty(
        name="Legacy retention (%)",
        description="Compatibility value from the former continuous slider",
        default=55.0, min=10.0, max=95.0, precision=0, subtype='PERCENTAGE',
        options={'HIDDEN'}, update=_on_retention_percent_change)
    implant_diameter:  FloatProperty(name="Implant Diameter (mm)",default=4.7,  min=2.0, max=7.0)
    implant_length:    FloatProperty(name="Implant Length (mm)",default=10.0, min=5.0, max=18.0)
    implant_tooth_clearance: FloatProperty(
        name="Tooth Safety (mm)",
        default=IMPLANT_TOOTH_CLEARANCE_DEFAULT_MM, min=0.0, max=5.0, precision=2,
        description="Minimum planned clearance between the real implant surface and adjacent segmented teeth; evidence/context configurable")
    tube_radius:       FloatProperty(name="Tube Radius (mm)",       default=FRAME_RADIUS_DEFAULT_MM,  min=0.5, max=5.0)
    connector_diameter: FloatProperty(
        name="Connector Diameter (mm)", default=REINFORCEMENT_DIAMETER_MM,
        min=1.0, max=6.0, precision=2,
        description="Diameter of reinforcement connectors added between guide regions")
    frame_catmull_alpha: FloatProperty(
        name="Catmull-Rom alpha", default=0.5, min=0.0, max=1.0, precision=2,
        description="0.5 = centripetal: follows user points and reduces loops/overshoot")
    frame_catmull_spacing: FloatProperty(
        name="Frame Sampling (mm)", default=0.6, min=0.2, max=2.0, precision=2,
        description="Approximate maximum distance between samples of the frame Catmull-Rom curve")
    sleeve_segments: IntProperty(
        name="Sleeve Resolution", default=32, min=16, max=64,
        description="Cylinder segments. 24 is fast; 32 maintains very low radial error")
    sleeve_last_timing: StringProperty(
        name="Last Sleeve Time", default="",
        description="Measured time of the last sleeve preview or application")
    sleeve_inner_diameter: FloatProperty(
        name="Drill Diameter (mm)", default=4.7, min=0.5, max=12.0, precision=2,
        description="Internal sleeve diameter corresponding to the drill or guided instrument")
    sleeve_wall: FloatProperty(
        name="Sleeve Wall Thickness (mm)", default=1.5, min=0.3, max=6.0, precision=2,
        description="Radial wall thickness of the sleeve")
    sleeve_height: FloatProperty(
        name="Sleeve Height (mm)", default=7.0, min=2.0, max=20.0, precision=2,
        description="Axial height of the sleeve")
    sleeve_lateral_opening: BoolProperty(
        name="Lateral Opening", default=False,
        description="Open the sleeve laterally so the drill can be introduced from the side in limited mouth opening")
    sleeve_lateral_opening_width: FloatProperty(
        name="Opening Width (mm)", default=4.0, min=1.0, max=12.0, precision=2,
        description="Width of the lateral access measured at the external sleeve surface")
    sleeve_lateral_opening_direction: FloatVectorProperty(
        name="Lateral Opening Direction", size=3, subtype='XYZ',
        default=(1.0, 0.0, 0.0), options={'HIDDEN'})
    sleeve_lateral_opening_rotation: FloatProperty(
        name="Fine Rotation (°)", default=0.0, min=-180.0, max=180.0, precision=1,
        description="Fine angular correction relative to the safe automatic position, or relative to the captured view when irrigation is not used")
    sleeve_lateral_opening_last_mode: StringProperty(
        name="Lateral Opening Placement Mode", default='VIEW', options={'HIDDEN'})
    sleeve_lateral_opening_manual_json: StringProperty(
        name="Manual Lateral Opening Picks", default='{}', options={'HIDDEN'},
        description="Per-implant user-selected lateral sleeve window angles")
    sleeve_implant_gap: FloatProperty(
        name="Sleeve-Implant Offset (mm)", default=0.0, min=0.0, max=12.0,
        description="Additional distance between the implant head and the sleeve start")
    continuous_fusion_remesh: BoolProperty(
        name="Continuous Fusion Remesh", default=True,
        description="Applies a fine voxel remesh after each union to fuse frame, sleeves, and irrigation into one solid before step 10")
    continuous_fusion_voxel: FloatProperty(
        name="Continuous Fusion Voxel (mm)", default=0.12, min=0.04, max=0.30, precision=3,
        description="Maximum voxel size used for continuous fusion. 0.10-0.14 mm usually balances accuracy and robustness")
    sleeve_keep_flat_faces: BoolProperty(
        name="Preserve Sleeve Flat Faces", default=True,
        description="Prevents any later voxel remesh on DSG_Guide")
    sleeve_sidewall_invulnerable: BoolProperty(
        name="Validate Flat Faces", default=True,
        description="Validates irrigation geometry against the sleeve flat faces")
    sleeve_sidewall_clearance: FloatProperty(
        name="Flat-Face Radial Margin (mm)", default=0.12, min=0.01, max=0.60, precision=3,
        description="Radial margin around the protected flat ring")
    sleeve_sidewall_guard_depth: FloatProperty(
        name="Flat-Face Axial Tolerance (mm)", default=0.35, min=0.06, max=1.50, precision=2,
        description="Tolerance band used by analytic validation around each flat face")
    sleeve_sidewall_axial_margin: FloatProperty(
        name="Extra Axial Margin (mm)", default=0.08, min=0.0, max=0.80, precision=2,
        description="Additional margin on both sides of each flat face")
    # Legacy clearance retained only for old scenes; sleeve geometry now uses sleeve_inner_diameter.
    fresa_offset:      FloatProperty(name="Drill Clearance (mm)",    default=0.10, min=0.0, max=0.5)
    drill_extra_depth: FloatProperty(name="Channel Margin (mm)",     default=5.0, min=5.0, max=30.0)
    drill_cutter_segments: IntProperty(
        name="Channel Resolution", default=32, min=8, max=32,
        description="Drill cutter segments. 12-16 is fast; 24-32 is rounder but heavier")
    drill_fast_boolean: BoolProperty(
        name="Fast Boolean Compatibility (Ignored)", default=False,
        description="Legacy property; all Booleans use EXACT in this version")
    drill_force_exact: BoolProperty(
        name="Safe EXACT Boolean", default=True,
        description="Prioritizes EXACT with hole and self-intersection tolerance to prevent open faces in step 9")
    drill_pre_remesh: BoolProperty(
        name="Remesh Before Channel", default=False,
        description="Applies a transactional voxel remesh before step 9 to fuse overlapping shells; restores the original guide if the channel fails")
    drill_pre_remesh_voxel: FloatProperty(
        name="Pre-Step-9 Voxel (mm)", default=0.10, min=0.04, max=0.30, precision=3,
        description="Fine voxel used to consolidate the guide before the channel Boolean. 0.08-0.12 mm recommended")
    drill_precheck_make_manifold: BoolProperty(
        name="Check Manifold First", default=True,
        description="Checks the solid after the preliminary remesh and only attempts extra cleanup if open edges remain")
    drill_sleeve_clearance: FloatProperty(
        name="Anti-Coplanar Overshoot (mm)", default=0.02, min=0.005, max=0.10, precision=3,
        description="Slightly enlarges the cutter relative to the sleeve lumen to ensure a clean intersection and prevent T-edges")
    drill_protection_auto: BoolProperty(
        name="Protect Drill Insertion", default=True,
        description="Automatically trims any irrigation wall or shell entering the coaxial drill path")
    drill_protection_clearance: FloatProperty(
        name="Protection Clearance (mm)", default=0.0, min=0.0, max=0.50, precision=3,
        description="Added to the implant radius. At 0, the protection cylinder exactly matches the implant diameter")
    drill_protection_segments: IntProperty(
        name="Protection Resolution", default=32, min=12, max=64,
        description="Segments of the coaxial cylinder protecting the drill insertion path")
    drill_rollback_nonmanifold: BoolProperty(
        name="Restore if Non-Manifold", default=True,
        description="Automatically restores the previous mesh if the Boolean opens edges or damages the guide")


    # ── Identificación grabada en la guía ────────────────────
    engrave_patient_text: StringProperty(
        name="Patient Name", default="",
        description="Text that will be engraved into the guide",
        update=_on_engrave_setting_change)
    engrave_text_size: FloatProperty(
        name="Text Size (mm)", default=3.0, min=1.0, max=12.0,
        description="Approximate letter height for engraving",
        update=_on_engrave_setting_change)
    engrave_depth: FloatProperty(
        name="Engraving Depth (mm)", default=0.45, min=0.10, max=2.0,
        description="Depth of the Boolean letter cut")
    engrave_curve_resolution: IntProperty(
        name="Legacy Text Resolution", default=2, min=1, max=8,
        description="Legacy compatibility property. The internal low-poly glyph library has a fixed optimized resolution",
        options={'HIDDEN'})
    engrave_project_to_curvature: BoolProperty(
        name="Fit Text to Curvature", default=True,
        description="Projects text onto DSG_Guide to follow the guide curvature. Optimized with BVH and raycast caching",
        update=_on_engrave_setting_change)
    engrave_fast_boolean: BoolProperty(
        name="EXACT Engraving Boolean", default=True,
        description="Engraving directly uses the EXACT solver")
    engrave_has_position: BoolProperty(default=False)
    engrave_location: FloatVectorProperty(
        name="Engraving Position", size=3, subtype='XYZ', default=(0.0, 0.0, 0.0))
    engrave_normal: FloatVectorProperty(
        name="Engraving Normal", size=3, subtype='XYZ', default=(0.0, 0.0, 1.0))
    engrave_x_axis: FloatVectorProperty(
        name="Text X Axis", size=3, subtype='XYZ', default=(1.0, 0.0, 0.0))

    # ── DCT Herramientas de acabado (integradas) ─────────────
    dct_voxel_size:       FloatProperty(name="Voxel Size", default=0.1,
                                        min=0.001, max=2.0, step=1, precision=3)
    # Corte final simplificado: ambos objetos se convierten primero en sólidos
    # voxelizados y después se reducen antes de ejecutar una sola booleana.
    dct_final_pre_remesh: BoolProperty(
        name="Voxelize Before Cut", default=True,
        description="Enables the stable workflow: remeshes the guide and blockout model before the Boolean")
    dct_final_remesh_voxel_size: FloatProperty(
        name="Guide Voxel (mm)", default=0.12, min=0.06, max=0.35, step=1, precision=3,
        description="Fuses all guide shells into one solid. 0.10-0.14 mm recommended")
    dct_final_edge_loops: BoolProperty(
        name="Legacy Edge Loops", default=False,
        description="Compatibility with older scenes; the new workflow uses remesh and reduction")
    dct_final_cutter_voxel_size: FloatProperty(
        name="Blockout Model Voxel (mm)", default=0.18, min=0.08, max=0.45, step=1, precision=3,
        description="Converts model + blockout into a solid cutter. 0.16-0.22 mm recommended")
    dct_final_use_shrinkwrap_proxy: BoolProperty(
        name="Shrinkwrap Proxy for Open STL", default=True,
        description=(
            "Automatically builds a projected solid proxy when the intraoral STL is open/non-manifold, "
            "or retries with the proxy if the normal final Boolean fails"))
    dct_final_decimate: BoolProperty(
        name="Automatically Reduce Polygons", default=True,
        description="Uses Decimate Collapse after remesh and again after the Boolean")
    dct_final_guide_target_faces: IntProperty(
        name="Guide Faces Before Cut", default=220000, min=20000, max=1000000,
        description="Approximate maximum guide face count before the Boolean")
    dct_final_cutter_target_faces: IntProperty(
        name="Blockout Model Faces", default=260000, min=20000, max=1200000,
        description="Approximate maximum face count of the voxelized cutter")
    dct_final_result_target_faces: IntProperty(
        name="Finished Guide Faces", default=180000, min=20000, max=800000,
        description="Approximate maximum face count after the final Boolean")
    dct_final_use_local_cutter: BoolProperty(name="Local Cutter", default=False)
    dct_final_cutter_margin: FloatProperty(
        name="Local Cutter Margin (mm)", default=5.0, min=1.0, max=20.0,
        description="Reserved for local optimization; the current workflow remeshes the complete passive model")
    dct_object_being_cut: PointerProperty(name="Object Being Cut",  type=bpy.types.Object)
    dct_object_making_cut:PointerProperty(name="Object Making Cut", type=bpy.types.Object)


# ─────────────────────────────────────────────────────────────
# Raycast compartido
# ─────────────────────────────────────────────────────────────

def get_view_ray(context, event):
    region = context.region
    rv3d = context.space_data.region_3d
    if not region or not rv3d:
        return None, None
    coord = (event.mouse_region_x, event.mouse_region_y)
    ray_origin_world = view3d_utils.region_2d_to_origin_3d(region, rv3d, coord)
    ray_dir_world = view3d_utils.region_2d_to_vector_3d(region, rv3d, coord)
    return ray_origin_world, ray_dir_world.normalized()


def intersect_ray_plane(ray_origin, ray_dir, plane_point, plane_normal):
    plane_normal = Vector(plane_normal)
    if plane_normal.length < 1e-8:
        return None
    denom = ray_dir.dot(plane_normal)
    if abs(denom) < 1e-8:
        return None
    t = (Vector(plane_point) - Vector(ray_origin)).dot(plane_normal) / denom
    if t < 0:
        return None
    return Vector(ray_origin) + Vector(ray_dir) * t


def point_in_view_plane(context, event, plane_point):
    ray_origin_world, ray_dir_world = get_view_ray(context, event)
    if ray_origin_world is None:
        return None
    rv3d = context.space_data.region_3d
    view_dir = (rv3d.view_rotation @ Vector((0.0, 0.0, -1.0))).normalized()
    hit = intersect_ray_plane(ray_origin_world, ray_dir_world, plane_point, view_dir)
    if hit is not None:
        return hit
    fallback_depth = max(30.0, (Vector(plane_point) - ray_origin_world).length)
    return ray_origin_world + ray_dir_world * fallback_depth


_RAYCAST_FALLBACK_WARNED = set()


def _raycast_local_safe(context, obj, ray_origin_local, ray_dir_local, distance=10000.0):
    """Raycast tolerante a objetos sin malla evaluada.

    Algunos alineadores importados, instancias o mallas con modificadores desactivados
    pueden existir como ``MESH`` pero Blender lanza ``RuntimeError: has no evaluated
    mesh data`` al llamar ``evaluated_object.ray_cast``. El selector no debe abortar
    por ese objeto: intenta cuatro rutas, de la más fiel a la más conservadora.
    """
    if not _valid_obj(obj) or obj.type != 'MESH':
        return False, None, None, -1

    direction = Vector(ray_dir_local)
    if direction.length < 1e-8:
        return False, None, None, -1
    direction.normalize()
    distance = max(0.001, float(distance))
    depsgraph = context.evaluated_depsgraph_get()
    obj_name = _safe_object_name(obj) or '<unnamed object>'
    failures = []

    # 1) Geometría evaluada: respeta modificadores y es la ruta normal.
    try:
        obj_eval = obj.evaluated_get(depsgraph)
        try:
            result = obj_eval.ray_cast(ray_origin_local, direction, distance=distance)
        except TypeError:
            result = obj_eval.ray_cast(ray_origin_local, direction)
        if result and result[0]:
            return result
        if result:
            return False, None, None, -1
    except Exception as exc:
        failures.append(f'evaluada={exc}')

    # 2) Objeto original: funciona cuando el depsgraph no expone una malla evaluada.
    try:
        try:
            result = obj.ray_cast(ray_origin_local, direction, distance=distance)
        except TypeError:
            result = obj.ray_cast(ray_origin_local, direction)
        if result and result[0]:
            if obj_name not in _RAYCAST_FALLBACK_WARNED:
                print(f'[DSG] Fallback raycast on original mesh: {obj_name}')
                _RAYCAST_FALLBACK_WARNED.add(obj_name)
            return result
        if result:
            return False, None, None, -1
    except Exception as exc:
        failures.append(f'original={exc}')

    # 3) BVH desde el objeto y depsgraph. Conserva deformaciones cuando Blender puede
    # construirlas aunque Object.ray_cast no tenga datos evaluados asociados.
    try:
        tree = BVHTree.FromObject(obj, depsgraph, deform=True, cage=False, epsilon=0.0)
        if tree is not None:
            loc, normal, face_index, _hit_distance = tree.ray_cast(
                Vector(ray_origin_local), direction, distance)
            if loc is not None:
                if obj_name not in _RAYCAST_FALLBACK_WARNED:
                    print(f'[DSG] Raycast BVH de respaldo: {obj_name}')
                    _RAYCAST_FALLBACK_WARNED.add(obj_name)
                return True, loc, normal, int(face_index) if face_index is not None else -1
            return False, None, None, -1
    except Exception as exc:
        failures.append(f'bvh_evaluado={exc}')

    # 4) Último recurso: BVH de la malla base, ignorando modificadores defectuosos.
    bm = None
    try:
        mesh = getattr(obj, 'data', None)
        if mesh is not None and len(mesh.polygons) > 0:
            bm = bmesh.new()
            bm.from_mesh(mesh)
            bm.normal_update()
            tree = BVHTree.FromBMesh(bm, epsilon=0.0)
            loc, normal, face_index, _hit_distance = tree.ray_cast(
                Vector(ray_origin_local), direction, distance)
            if loc is not None:
                if obj_name not in _RAYCAST_FALLBACK_WARNED:
                    print(f'[DSG] Raycast on base mesh without modifiers: {obj_name}')
                    _RAYCAST_FALLBACK_WARNED.add(obj_name)
                return True, loc, normal, int(face_index) if face_index is not None else -1
            return False, None, None, -1
    except Exception as exc:
        failures.append(f'bvh_base={exc}')
    finally:
        if bm is not None:
            bm.free()

    # No propaga el RuntimeError: otro candidato del modelo/blockout/frame puede
    # recibir el clic. Se informa una sola vez en consola para diagnóstico.
    warning_key = 'FAIL:' + obj_name
    if warning_key not in _RAYCAST_FALLBACK_WARNED:
        detail = ' | '.join(failures) if failures else 'no usable geometry'
        print(f'[DSG] Object skipped during raycast ({obj_name}): {detail}')
        _RAYCAST_FALLBACK_WARNED.add(warning_key)
    return False, None, None, -1


def do_raycast_detailed(context, event, obj):
    if not _valid_obj(obj) or obj.type != 'MESH':
        return None, None, None
    ray_origin_world, ray_dir_world = get_view_ray(context, event)
    if ray_origin_world is None:
        return None, None, None

    try:
        mx = obj.matrix_world.copy()
        mx_inv = mx.inverted_safe()
    except Exception:
        return None, None, None

    ray_origin_local = mx_inv @ ray_origin_world
    ray_target_local = mx_inv @ (ray_origin_world + ray_dir_world * 10000.0)
    ray_dir_local = ray_target_local - ray_origin_local
    if ray_dir_local.length < 1e-8:
        return None, None, None
    ray_dir_local.normalize()

    hit, loc, normal, face_index = _raycast_local_safe(
        context, obj, ray_origin_local, ray_dir_local, distance=10000.0)
    if not hit or loc is None:
        return None, None, None

    world_loc = mx @ Vector(loc)
    normal = Vector(normal) if normal is not None else Vector((0.0, 0.0, 0.0))
    world_normal = (mx.to_3x3() @ normal).normalized() if normal.length > 1e-8 else None
    return world_loc, world_normal, face_index


def do_raycast(context, event, obj):
    loc, _, _ = do_raycast_detailed(context, event, obj)
    return loc


# ─────────────────────────────────────────────────────────────
# Medición manual implante ↔ anatomía en revisión DICOM
# ─────────────────────────────────────────────────────────────

def _event_view_ray(context, event):
    """Return a world-space ray for the WINDOW region under the mouse.

    The button is launched from the N-panel, where ``context.region`` is the UI
    region. Using the actual region under the cursor makes the modal tool work
    reliably without requiring the user to hide the sidebar.
    """
    area = getattr(context, 'area', None)
    if area is None or area.type != 'VIEW_3D':
        return None, None
    region = None
    mouse_x = int(getattr(event, 'mouse_x', 0))
    mouse_y = int(getattr(event, 'mouse_y', 0))
    for candidate in area.regions:
        if candidate.type != 'WINDOW':
            continue
        if (candidate.x <= mouse_x < candidate.x + candidate.width
                and candidate.y <= mouse_y < candidate.y + candidate.height):
            region = candidate
            break
    if region is None:
        return None, None
    rv3d = getattr(region, 'data', None)
    if rv3d is None or not hasattr(rv3d, 'view_rotation'):
        try:
            rv3d = area.spaces.active.region_3d
        except Exception:
            rv3d = None
    if rv3d is None:
        return None, None
    coord = (float(mouse_x - region.x), float(mouse_y - region.y))
    try:
        origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, coord)
        direction = view3d_utils.region_2d_to_vector_3d(region, rv3d, coord)
    except Exception:
        return None, None
    direction = Vector(direction)
    if direction.length < 1.0e-8:
        return None, None
    return Vector(origin), direction.normalized()


def _raycast_object_from_world_ray(context, obj, ray_origin_world, ray_dir_world):
    if not _valid_obj(obj) or obj.type != 'MESH':
        return None, None, None
    try:
        matrix = obj.matrix_world.copy()
        inverse = matrix.inverted_safe()
        local_origin = inverse @ Vector(ray_origin_world)
        local_target = inverse @ (Vector(ray_origin_world) + Vector(ray_dir_world) * 10000.0)
        local_direction = local_target - local_origin
        if local_direction.length < 1.0e-8:
            return None, None, None
        local_direction.normalize()
        hit, location, normal, face_index = _raycast_local_safe(
            context, obj, local_origin, local_direction, distance=10000.0)
        if not hit or location is None:
            return None, None, None
        world_location = matrix @ Vector(location)
        world_normal = None
        if normal is not None and Vector(normal).length > 1.0e-8:
            world_normal = (matrix.to_3x3() @ Vector(normal)).normalized()
        return world_location, world_normal, face_index
    except Exception:
        return None, None, None


def _nearest_visible_raycast(context, objects, ray_origin, ray_direction):
    best = None
    best_distance = float('inf')
    for obj in objects:
        if not _valid_obj(obj) or obj.type != 'MESH':
            continue
        try:
            if obj.hide_viewport or obj.hide_get():
                continue
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        location, normal, face_index = _raycast_object_from_world_ray(
            context, obj, ray_origin, ray_direction)
        if location is None:
            continue
        distance = (Vector(location) - Vector(ray_origin)).length
        if distance < best_distance:
            best = (obj, Vector(location), normal, face_index)
            best_distance = distance
    return best


def _nearest_implant_vertex(implant, world_point):
    """Snap a clicked implant surface point to the nearest real mesh vertex."""
    if not is_valid_implant_obj(implant):
        return None, None
    try:
        inverse = implant.matrix_world.inverted_safe()
        local_point = inverse @ Vector(world_point)
        vertices = implant.data.vertices
        if not vertices:
            return None, None
        best_index = min(
            range(len(vertices)),
            key=lambda index: (vertices[index].co - local_point).length_squared,
        )
        local_vertex = vertices[best_index].co.copy()
        return int(best_index), implant.matrix_world @ local_vertex
    except Exception:
        return None, None


def _dsg_data_access_ready():
    """Return True only when Blender has restored normal blend-data access.

    During add-on enable Blender can expose ``bpy.data`` as ``_RestrictData``.
    Scene/object queries must therefore be deferred until the regular data API
    is available.
    """
    try:
        return (
            getattr(bpy.data, 'objects', None) is not None
            and getattr(bpy.data, 'scenes', None) is not None
        )
    except Exception:
        return False


def _dicom_measurement_roots():
    if not _dsg_data_access_ready():
        return []
    roots = []
    for obj in bpy.data.objects:
        try:
            if bool(obj.get('DSG_dicom_measurement_root', False)):
                roots.append(obj)
        except Exception:
            continue
    def sort_key(obj):
        try:
            return int(obj.get('DSG_dicom_measurement_index', 0))
        except Exception:
            return 0
    return sorted(roots, key=sort_key)


def _next_dicom_measurement_index():
    values = []
    for obj in _dicom_measurement_roots():
        try:
            values.append(int(obj.get('DSG_dicom_measurement_index', 0)))
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    return max(values, default=0) + 1


def _ensure_dicom_measure_material(name, rgba):
    material = bpy.data.materials.get(name)
    if material is None:
        material = bpy.data.materials.new(name)
    try:
        material.use_nodes = False
        material.diffuse_color = tuple(float(value) for value in rgba)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    return material


def _assign_single_material(obj, material):
    try:
        obj.data.materials.clear()
        obj.data.materials.append(material)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)


def _create_dicom_measure_marker(context, name, location, material):
    mesh = make_uv_sphere_mesh(name + '_Mesh', 0.42, 20, 12)
    marker = bpy.data.objects.new(name, mesh)
    link_object(context, marker)
    register_dsg_object(marker, ROLE_MEASUREMENT, extra={
        'DSG_dicom_measurement_visual': True,
    })
    marker.location = Vector(location)
    marker.show_in_front = True
    marker.hide_render = True
    marker.hide_select = True
    marker.display_type = 'SOLID'
    _assign_single_material(marker, material)
    return marker


def _create_dicom_measure_line(context, name, point_a, point_b, material):
    curve = bpy.data.curves.new(name + '_Curve', type='CURVE')
    curve.dimensions = '3D'
    curve.resolution_u = 1
    curve.bevel_depth = 0.10
    curve.bevel_resolution = 2
    spline = curve.splines.new('POLY')
    spline.points.add(1)
    spline.points[0].co = (*Vector(point_a), 1.0)
    spline.points[1].co = (*Vector(point_b), 1.0)
    line = bpy.data.objects.new(name, curve)
    link_object(context, line)
    register_dsg_object(line, ROLE_MEASUREMENT, extra={
        'DSG_dicom_measurement_root': True,
        'DSG_dicom_measurement_visual': True,
    })
    line.show_in_front = True
    line.hide_render = True
    line.hide_select = True
    _assign_single_material(line, material)
    return line


def _set_dicom_measurements_visibility(visible: bool):
    """Show or hide all DICOM two-point measurement visuals.

    Measurements remain stored in the scene so the clinician can reopen the
    MPR review and continue using them, but their markers and lines should not
    clutter the implant workflow when the DICOM viewer is closed.
    """
    if not _dsg_data_access_ready():
        return
    hidden = not bool(visible)
    names = []
    for root in _dicom_measurement_roots():
        try:
            names.append(str(root.name))
            names.append(str(root.get('DSG_measure_marker_a', '')))
            names.append(str(root.get('DSG_measure_marker_b', '')))
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    seen = set()
    for name in names:
        if not name or name in seen:
            continue
        seen.add(name)
        obj = bpy.data.objects.get(name)
        if not _valid_obj(obj):
            continue
        try:
            obj.hide_viewport = hidden
            obj.hide_set(hidden)
            if not hidden:
                obj.hide_render = True
                obj.hide_select = True
                obj.show_in_front = True
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    _tag_dicom_measurement_redraw()


def _dicom_measurement_points(root):
    if not _valid_obj(root):
        return None, None
    try:
        mode = str(root.get('DSG_measure_mode', 'IMPLANT')).upper()
        point_b = Vector(root.get('DSG_measure_point_b', (0.0, 0.0, 0.0)))
    except Exception:
        return None, None
    if mode == 'MPR':
        try:
            point_a = Vector(root.get('DSG_measure_point_a_world', (0.0, 0.0, 0.0)))
            return point_a, point_b
        except Exception:
            return None, point_b
    try:
        implant = bpy.data.objects.get(str(root.get('DSG_measure_implant', '')))
        vertex_index = int(root.get('DSG_measure_vertex_index', -1))
    except Exception:
        return None, None
    if not is_valid_implant_obj(implant):
        return None, point_b
    try:
        if vertex_index < 0 or vertex_index >= len(implant.data.vertices):
            return None, point_b
        point_a = implant.matrix_world @ implant.data.vertices[vertex_index].co
        return Vector(point_a), point_b
    except Exception:
        return None, point_b


def _update_one_dicom_measurement(root):
    point_a, point_b = _dicom_measurement_points(root)
    if point_a is None or point_b is None:
        return False
    changed = False
    try:
        marker_a = bpy.data.objects.get(str(root.get('DSG_measure_marker_a', '')))
        marker_b = bpy.data.objects.get(str(root.get('DSG_measure_marker_b', '')))
        if _valid_obj(marker_a) and (marker_a.location - point_a).length_squared > 1.0e-12:
            marker_a.location = point_a
            changed = True
        if _valid_obj(marker_b) and (marker_b.location - point_b).length_squared > 1.0e-12:
            marker_b.location = point_b
            changed = True
        if root.type == 'CURVE' and root.data.splines and len(root.data.splines[0].points) >= 2:
            points = root.data.splines[0].points
            current_a = Vector(points[0].co[:3])
            current_b = Vector(points[1].co[:3])
            if (current_a - point_a).length_squared > 1.0e-12:
                points[0].co = (*point_a, 1.0)
                changed = True
            if (current_b - point_b).length_squared > 1.0e-12:
                points[1].co = (*point_b, 1.0)
                changed = True
        distance = (point_b - point_a).length
        old_distance = float(root.get('DSG_measure_distance_mm', -1.0))
        if abs(old_distance - distance) > 1.0e-7:
            root['DSG_measure_distance_mm'] = float(distance)
            root['DSG_measure_point_a_world'] = [float(v) for v in point_a]
            changed = True
        return changed
    except Exception:
        return False


def _tag_dicom_measurement_redraw():
    try:
        for window in bpy.context.window_manager.windows:
            screen = getattr(window, 'screen', None)
            if screen is None:
                continue
            for area in screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)


def _update_all_dicom_measurements(scene=None):
    global _DICOM_MEASURE_UPDATE_LOCK
    if not _dsg_data_access_ready():
        return
    if _DICOM_MEASURE_UPDATE_LOCK:
        return
    _DICOM_MEASURE_UPDATE_LOCK = True
    changed = False
    try:
        for root in _dicom_measurement_roots():
            changed = _update_one_dicom_measurement(root) or changed
    finally:
        _DICOM_MEASURE_UPDATE_LOCK = False
    if changed:
        _tag_dicom_measurement_redraw()


def _dsg_dicom_measurement_update_timer():
    global _DICOM_MEASURE_UPDATE_PENDING
    _DICOM_MEASURE_UPDATE_PENDING = False
    if not _dsg_data_access_ready():
        return None
    _update_all_dicom_measurements(getattr(bpy.context, 'scene', None))
    return None


@persistent
def _dsg_update_dicom_measurements_handler(scene, depsgraph=None):
    if not _dsg_data_access_ready():
        return
    # Never edit object/curve datablocks directly from depsgraph_update_post.
    # Schedule one coalesced timer update instead; this avoids recursive graph
    # evaluation while the user drags or rotates an implant.
    global _DICOM_MEASURE_UPDATE_PENDING
    if _DICOM_MEASURE_UPDATE_PENDING or not _dicom_measurement_roots():
        return
    _DICOM_MEASURE_UPDATE_PENDING = True
    try:
        lifecycle.unregister_timer(_dsg_dicom_measurement_update_timer)
        lifecycle.register_timer(
            _dsg_dicom_measurement_update_timer,
            first_interval=0.02,
        )
    except Exception:
        _DICOM_MEASURE_UPDATE_PENDING = False


def _remove_dicom_measure_handler():
    global _DICOM_MEASURE_UPDATE_PENDING
    try:
        lifecycle.unregister_timer(_dsg_dicom_measurement_update_timer)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    _DICOM_MEASURE_UPDATE_PENDING = False
    try:
        for handler in list(bpy.app.handlers.depsgraph_update_post):
            if getattr(handler, '__name__', '') == '_dsg_update_dicom_measurements_handler':
                bpy.app.handlers.depsgraph_update_post.remove(handler)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)


def _register_dicom_measure_handler():
    _remove_dicom_measure_handler()
    try:
        bpy.app.handlers.depsgraph_update_post.append(
            _dsg_update_dicom_measurements_handler)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)


def _remove_dicom_measurement_root(root):
    if not _valid_obj(root):
        return False
    names = []
    try:
        names.extend([
            str(root.get('DSG_measure_marker_a', '')),
            str(root.get('DSG_measure_marker_b', '')),
        ])
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    for name in names:
        obj = bpy.data.objects.get(name) if name else None
        if _valid_obj(obj):
            safe_remove_object_with_data(obj)
    return safe_remove_object_with_data(root)


def _clear_all_dicom_measurements():
    removed = 0
    for root in list(_dicom_measurement_roots()):
        removed += int(_remove_dicom_measurement_root(root))
    # Defensive cleanup for interrupted modal operations or legacy duplicates.
    for obj in list(bpy.data.objects):
        try:
            is_visual = bool(obj.get('DSG_dicom_measurement_visual', False))
            by_name = obj.name.startswith((
                DICOM_MEASURE_PREFIX,
                DICOM_MEASURE_POINT_A_PREFIX,
                DICOM_MEASURE_POINT_B_PREFIX,
            ))
        except Exception:
            is_visual = False
            by_name = False
        if (is_visual or by_name) and _valid_obj(obj):
            safe_remove_object_with_data(obj)
    return removed


def _remove_dicom_measurements_for_implant(implant_name):
    removed = 0
    for root in list(_dicom_measurement_roots()):
        try:
            matches = str(root.get('DSG_measure_implant', '')) == str(implant_name)
        except Exception:
            matches = False
        if matches:
            removed += int(_remove_dicom_measurement_root(root))
    return removed


def _create_dicom_measurement(context, implant, vertex_index, point_a, point_b, plane_name):
    index = _next_dicom_measurement_index()
    root_name = f'{DICOM_MEASURE_PREFIX}{index:03d}'
    line_material = _ensure_dicom_measure_material(
        DICOM_MEASURE_LINE_MATERIAL, (0.02, 0.82, 0.82, 1.0))
    implant_material = _ensure_dicom_measure_material(
        DICOM_MEASURE_POINT_A_MATERIAL, (0.02, 0.82, 0.82, 1.0))
    anatomy_material = _ensure_dicom_measure_material(
        DICOM_MEASURE_POINT_B_MATERIAL, (1.0, 0.58, 0.08, 1.0))

    marker_a = _create_dicom_measure_marker(
        context, f'{DICOM_MEASURE_POINT_A_PREFIX}{index:03d}', point_a,
        implant_material)
    marker_b = _create_dicom_measure_marker(
        context, f'{DICOM_MEASURE_POINT_B_PREFIX}{index:03d}', point_b,
        anatomy_material)
    root = _create_dicom_measure_line(
        context, root_name, point_a, point_b, line_material)
    root['DSG_dicom_measurement_index'] = int(index)
    root['DSG_measure_implant'] = str(implant.name)
    root['DSG_measure_vertex_index'] = int(vertex_index)
    root['DSG_measure_point_b'] = [float(value) for value in Vector(point_b)]
    root['DSG_measure_plane'] = str(plane_name)
    root['DSG_measure_marker_a'] = str(marker_a.name)
    root['DSG_measure_marker_b'] = str(marker_b.name)
    root['DSG_measure_units'] = 'mm'
    _update_one_dicom_measurement(root)
    return root


def _create_dicom_mpr_measurement(context, point_a, point_b, plane_a_name, plane_b_name):
    index = _next_dicom_measurement_index()
    root_name = f'{DICOM_MEASURE_PREFIX}{index:03d}'
    line_material = _ensure_dicom_measure_material(
        DICOM_MEASURE_LINE_MATERIAL, (0.02, 0.82, 0.82, 1.0))
    point_a_material = _ensure_dicom_measure_material(
        DICOM_MEASURE_POINT_A_MATERIAL, (0.02, 0.82, 0.82, 1.0))
    point_b_material = _ensure_dicom_measure_material(
        DICOM_MEASURE_POINT_B_MATERIAL, (1.0, 0.58, 0.08, 1.0))

    marker_a = _create_dicom_measure_marker(
        context, f'{DICOM_MEASURE_POINT_A_PREFIX}{index:03d}', point_a,
        point_a_material)
    marker_b = _create_dicom_measure_marker(
        context, f'{DICOM_MEASURE_POINT_B_PREFIX}{index:03d}', point_b,
        point_b_material)
    root = _create_dicom_measure_line(
        context, root_name, point_a, point_b, line_material)
    root['DSG_dicom_measurement_index'] = int(index)
    root['DSG_measure_mode'] = 'MPR'
    root['DSG_measure_implant'] = ''
    root['DSG_measure_vertex_index'] = -1
    root['DSG_measure_point_a_world'] = [float(value) for value in Vector(point_a)]
    root['DSG_measure_point_b'] = [float(value) for value in Vector(point_b)]
    root['DSG_measure_plane_a'] = str(plane_a_name)
    root['DSG_measure_plane_b'] = str(plane_b_name)
    root['DSG_measure_plane'] = str(plane_b_name)
    root['DSG_measure_marker_a'] = str(marker_a.name)
    root['DSG_measure_marker_b'] = str(marker_b.name)
    root['DSG_measure_units'] = 'mm'
    _update_one_dicom_measurement(root)
    return root


class DSG_OT_MeasureImplantToDICOM(Operator):
    bl_idname = 'dsg.measure_implant_to_dicom'
    bl_label = 'Measure Implant to DICOM'
    bl_description = (
        'First click an implant; DSG snaps to its nearest vertex. '
        'Then click the anatomy on a visible DICOM plane')
    bl_options = {'REGISTER', 'UNDO', 'BLOCKING'}

    _implant_name = ''
    _vertex_index = -1
    _point_a = None

    @classmethod
    def poll(cls, context):
        scene = getattr(context, 'scene', None)
        props = getattr(scene, 'dsg_props', None) if scene is not None else None
        return (
            props is not None
            and int(getattr(props, 'current_step', -1)) == STEP_IMPLANT
            and _dicom_review_is_active(context)
            and bool(get_all_implant_objects(props))
        )

    def invoke(self, context, event):
        self._implant_name = ''
        self._vertex_index = -1
        self._point_a = None
        try:
            context.window.cursor_modal_set('CROSSHAIR')
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        context.window_manager.modal_handler_add(self)
        _dsg_report(
            self, {'INFO'},
            'Point 1/2: click the implant vertex from which you want to measure',
            'Punto 1/2: haz clic en el vértice del implante desde el que quieres medir')
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if not lifecycle.is_active() or not _dicom_review_is_active(context):
            self._finish_cursor(context)
            return {'CANCELLED'}

        if event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            self._finish_cursor(context)
            _dsg_report(self, {'INFO'}, 'Measurement cancelled', 'Medición cancelada')
            return {'CANCELLED'}

        if event.type in {
            'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE',
            'NUMPAD_0', 'NUMPAD_1', 'NUMPAD_2', 'NUMPAD_3',
            'NUMPAD_4', 'NUMPAD_5', 'NUMPAD_6', 'NUMPAD_7',
            'NUMPAD_8', 'NUMPAD_9',
        }:
            return {'PASS_THROUGH'}

        if event.type != 'LEFTMOUSE' or event.value != 'PRESS':
            return {'RUNNING_MODAL'}

        ray_origin, ray_direction = _event_view_ray(context, event)
        if ray_origin is None:
            return {'RUNNING_MODAL'}

        props = context.scene.dsg_props
        if self._point_a is None:
            hit = _nearest_visible_raycast(
                context, get_all_implant_objects(props), ray_origin, ray_direction)
            if hit is None:
                _dsg_report(
                    self, {'WARNING'},
                    'Point 1 must be clicked directly on an implant',
                    'El punto 1 debe marcarse directamente sobre un implante')
                return {'RUNNING_MODAL'}
            implant, hit_point, _normal, _face = hit
            vertex_index, vertex_world = _nearest_implant_vertex(implant, hit_point)
            if vertex_index is None or vertex_world is None:
                _dsg_report(
                    self, {'ERROR'},
                    'The nearest implant vertex could not be determined',
                    'No se pudo determinar el vértice más cercano del implante')
                self._finish_cursor(context)
                return {'CANCELLED'}
            self._implant_name = implant.name
            self._vertex_index = int(vertex_index)
            self._point_a = Vector(vertex_world)
            _dsg_report(
                self, {'INFO'},
                'Point 2/2: click the anatomical location on a visible DICOM plane',
                'Punto 2/2: haz clic en la zona anatómica sobre un plano DICOM visible')
            return {'RUNNING_MODAL'}

        planes = []
        for name in DICOM_MEASURE_PLANE_NAMES:
            plane = bpy.data.objects.get(name)
            if _valid_obj(plane) and plane.type == 'MESH':
                planes.append(plane)
        plane_hit = _nearest_visible_raycast(
            context, planes, ray_origin, ray_direction)
        if plane_hit is None:
            _dsg_report(
                self, {'WARNING'},
                'Point 2 must be clicked on the radiographic image plane',
                'El punto 2 debe marcarse sobre la imagen del plano radiográfico')
            return {'RUNNING_MODAL'}

        plane, point_b, _normal, _face = plane_hit
        implant = bpy.data.objects.get(self._implant_name)
        if not is_valid_implant_obj(implant):
            self._finish_cursor(context)
            _dsg_report(
                self, {'ERROR'},
                'The selected implant no longer exists',
                'El implante seleccionado ya no existe')
            return {'CANCELLED'}

        root = _create_dicom_measurement(
            context, implant, self._vertex_index, self._point_a,
            point_b, plane.name)
        _set_dicom_measurements_visibility(True)
        distance = float(root.get('DSG_measure_distance_mm', 0.0))
        self._finish_cursor(context)
        _dsg_report(
            self, {'INFO'},
            f'Measurement created: {distance:.2f} mm',
            f'Medición creada: {distance:.2f} mm')
        _tag_dicom_measurement_redraw()
        return {'FINISHED'}

    @staticmethod
    def _finish_cursor(context):
        try:
            context.window.cursor_modal_restore()
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)




class DSG_OT_MeasureDICOMTwoPoints(Operator):
    bl_idname = 'dsg.measure_dicom_two_points'
    bl_label = 'Measure Two Points in DICOM MPR'
    bl_description = (
        'Click two anatomical points directly on visible DICOM planes to measure '
        'bone width, cortical thickness or root size')
    bl_options = {'REGISTER', 'UNDO', 'BLOCKING'}

    _point_a = None
    _plane_a_name = ''

    @classmethod
    def poll(cls, context):
        scene = getattr(context, 'scene', None)
        props = getattr(scene, 'dsg_props', None) if scene is not None else None
        return (
            props is not None
            and int(getattr(props, 'current_step', -1)) == STEP_IMPLANT
            and _dicom_review_is_active(context)
        )

    def invoke(self, context, event):
        self._point_a = None
        self._plane_a_name = ''
        try:
            context.window.cursor_modal_set('CROSSHAIR')
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        context.window_manager.modal_handler_add(self)
        _dsg_report(
            self, {'INFO'},
            'Point 1/2: click the first anatomical point on a visible DICOM plane',
            'Punto 1/2: haz clic en el primer punto anatómico sobre un plano DICOM visible')
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if not lifecycle.is_active() or not _dicom_review_is_active(context):
            self._finish_cursor(context)
            return {'CANCELLED'}

        if event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            self._finish_cursor(context)
            _dsg_report(self, {'INFO'}, 'Measurement cancelled', 'Medición cancelada')
            return {'CANCELLED'}

        if event.type in {
            'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE',
            'NUMPAD_0', 'NUMPAD_1', 'NUMPAD_2', 'NUMPAD_3',
            'NUMPAD_4', 'NUMPAD_5', 'NUMPAD_6', 'NUMPAD_7',
            'NUMPAD_8', 'NUMPAD_9',
        }:
            return {'PASS_THROUGH'}

        if event.type != 'LEFTMOUSE' or event.value != 'PRESS':
            return {'RUNNING_MODAL'}

        ray_origin, ray_direction = _event_view_ray(context, event)
        if ray_origin is None:
            return {'RUNNING_MODAL'}

        planes = []
        for name in DICOM_MEASURE_PLANE_NAMES:
            plane = bpy.data.objects.get(name)
            if _valid_obj(plane) and plane.type == 'MESH':
                planes.append(plane)
        plane_hit = _nearest_visible_raycast(context, planes, ray_origin, ray_direction)
        if plane_hit is None:
            _dsg_report(
                self, {'WARNING'},
                'Each point must be clicked on the radiographic image plane',
                'Cada punto debe marcarse sobre la imagen del plano radiográfico')
            return {'RUNNING_MODAL'}

        plane, point_hit, _normal, _face = plane_hit
        point_hit = Vector(point_hit)

        if self._point_a is None:
            self._point_a = point_hit
            self._plane_a_name = str(plane.name)
            _dsg_report(
                self, {'INFO'},
                'Point 2/2: click the second anatomical point on a visible DICOM plane',
                'Punto 2/2: haz clic en el segundo punto anatómico sobre un plano DICOM visible')
            return {'RUNNING_MODAL'}

        root = _create_dicom_mpr_measurement(
            context, self._point_a, point_hit, self._plane_a_name, plane.name)
        _set_dicom_measurements_visibility(True)
        distance = float(root.get('DSG_measure_distance_mm', 0.0))
        self._finish_cursor(context)
        _dsg_report(
            self, {'INFO'},
            f'MPR measurement created: {distance:.2f} mm',
            f'Medición MPR creada: {distance:.2f} mm')
        _tag_dicom_measurement_redraw()
        return {'FINISHED'}

    @staticmethod
    def _finish_cursor(context):
        try:
            context.window.cursor_modal_restore()
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)


class DSG_OT_RemoveLastDICOMMeasurement(Operator):
    bl_idname = 'dsg.remove_last_dicom_measurement'
    bl_label = 'Delete Last DICOM Measurement'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        roots = _dicom_measurement_roots()
        if not roots:
            _dsg_report(self, {'WARNING'}, 'There are no measurements', 'No hay mediciones')
            return {'CANCELLED'}
        _remove_dicom_measurement_root(roots[-1])
        _tag_dicom_measurement_redraw()
        return {'FINISHED'}


class DSG_OT_ClearDICOMMeasurements(Operator):
    bl_idname = 'dsg.clear_dicom_measurements'
    bl_label = 'Clear DICOM Measurements'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        removed = _clear_all_dicom_measurements()
        _dsg_report(
            self, {'INFO'},
            f'{removed} measurement(s) removed',
            f'{removed} medición(es) eliminadas')
        _tag_dicom_measurement_redraw()
        return {'FINISHED'}


# ─────────────────────────────────────────────────────────────
# Grabado de identificación de paciente
# ─────────────────────────────────────────────────────────────

def get_active_guide_obj(props):
    """Recupera la guía de forma estrictamente read-only.

    IMPORTANTE: esta función se usa desde ``Panel.draw()``. Blender prohíbe
    modificar propiedades de Scene/Object durante el dibujado del panel, por lo
    que aquí nunca se llama a ``repair_core_object_pointers`` ni se reescriben
    PointerProperty. El nombre canónico DSG_Guide es la fuente principal.
    """
    return get_primary_dsg_object(
        props,
        'guide_obj',
        role=ROLE_GUIDE,
        exact_name=GUIDE_NAME,
        obj_type='MESH',
    )


def _normalized_or_fallback(vec, fallback):
    v = Vector(vec)
    if v.length < 1e-8:
        return Vector(fallback).normalized()
    return v.normalized()


def build_engrave_orientation_matrix(location, normal, x_axis=None):
    """Crea una matriz mundo para colocar texto tangente a la superficie.

    IMPORTANTE v5.0.20:
    El eje local Z del texto apunta hacia fuera de la guía, es decir, en el
    sentido de la normal externa de la superficie. Esto evita que el texto se
    vea desde la cara trasera, que era la causa de que saliera como espejo.

    El cutter sólido se remapea después de convertir el texto to mesh para que
    atraviese desde un pequeño margen exterior hacia dentro de la guía.
    """
    n = _normalized_or_fallback(normal, (0, 0, 1))
    z_axis = n.normalized()

    if x_axis is None or Vector(x_axis).length < 1e-8:
        ref = Vector((1.0, 0.0, 0.0))
        if abs(ref.dot(z_axis)) > 0.92:
            ref = Vector((0.0, 1.0, 0.0))
        x = ref - z_axis * ref.dot(z_axis)
    else:
        x = Vector(x_axis) - z_axis * Vector(x_axis).dot(z_axis)
        if x.length < 1e-8:
            ref = Vector((1.0, 0.0, 0.0))
            if abs(ref.dot(z_axis)) > 0.92:
                ref = Vector((0.0, 1.0, 0.0))
            x = ref - z_axis * ref.dot(z_axis)
    x_axis = x.normalized()
    y_axis = z_axis.cross(x_axis).normalized()
    x_axis = y_axis.cross(z_axis).normalized()

    rot = Matrix((x_axis, y_axis, z_axis)).transposed().to_quaternion()
    return Matrix.LocRotScale(Vector(location), rot, Vector((1.0, 1.0, 1.0)))


def _get_view_right_axis(context, normal):
    """Usa el eje horizontal de la vista como fallback de orientación."""
    try:
        rv3d = context.space_data.region_3d
        view_right = (rv3d.view_rotation @ Vector((1.0, 0.0, 0.0))).normalized()
    except Exception:
        view_right = Vector((1.0, 0.0, 0.0))
    n = _normalized_or_fallback(normal, (0, 0, 1))
    tangent = view_right - n * view_right.dot(n)
    if tangent.length < 1e-8:
        tangent = n.cross(Vector((0.0, 0.0, 1.0)))
        if tangent.length < 1e-8:
            tangent = n.cross(Vector((0.0, 1.0, 0.0)))
    return tangent.normalized()


def _get_view_up_axis(context, normal):
    """Devuelve el eje vertical de la vista proyectado sobre la superficie."""
    try:
        rv3d = context.space_data.region_3d
        view_up = (rv3d.view_rotation @ Vector((0.0, 1.0, 0.0))).normalized()
    except Exception:
        view_up = Vector((0.0, 0.0, 1.0))
    n = _normalized_or_fallback(normal, (0, 0, 1))
    tangent = view_up - n * view_up.dot(n)
    if tangent.length < 1e-8:
        return _get_view_right_axis(context, normal)
    return tangent.normalized()


def get_nearest_implant_to_world_point(props, point):
    """Implant cuyo sleeve clínico queda más cerca de un punto del grabado."""
    implants = get_all_implant_objects(props)
    if not implants:
        return None
    p = Vector(point)
    best = None
    best_dist = float('inf')
    for implant in implants:
        if not is_valid_implant_obj(implant):
            continue
        try:
            sleeve_center = get_sleeve_center_world(props, implant)
        except Exception:
            sleeve_center = implant.matrix_world.to_translation()
        dist = (sleeve_center - p).length
        if dist < best_dist:
            best_dist = dist
            best = implant
    return best


def get_engrave_x_axis_perpendicular_to_sleeve_base(context, props, location, normal):
    """Orienta el texto con el eje de inserción capturado desde la vista.

    En el flujo clínico del addon, el eje de inserción se define en los primeros
    pasos desde la cámara/vista del usuario y se guarda en DSG_Axis. Para que el
    grabado mantenga esa misma referencia, usamos ese eje como dirección vertical
    del texto proyectada sobre la tangente de la superficie. La normal del
    grabado sigue siendo la normal real de la férula, de modo que el texto queda
    apoyado sobre la cara externa y después se proyecta a curvatura.
    """
    z_axis = _normalized_or_fallback(normal, (0, 0, 1))  # local Z: exterior de la férula

    try:
        insertion_axis = get_insertion_axis().normalized()
    except Exception:
        insertion_axis = Vector((0.0, 0.0, 1.0))

    # El eje de inserción funciona como eje vertical clínico del texto.
    # Lo proyectamos en la tangente de la superficie para no perder contacto.
    y_axis = insertion_axis - z_axis * insertion_axis.dot(z_axis)

    # Si la normal local es casi paralela al eje de inserción, la proyección se
    # vuelve degenerada. En ese caso usamos una base estable generada desde el
    # mismo eje de inserción, y solo como último recurso la vista actual.
    if y_axis.length < 1e-8:
        try:
            u, v, _ = build_axis_basis(insertion_axis)
            y_axis = v - z_axis * v.dot(z_axis)
            if y_axis.length < 1e-8:
                y_axis = u - z_axis * u.dot(z_axis)
        except Exception:
            y_axis = Vector((0.0, 0.0, 0.0))

    if y_axis.length < 1e-8:
        y_axis = _get_view_up_axis(context, normal)
    else:
        y_axis.normalize()

    # Mantener lectura natural respecto a la vista solamente para elegir el
    # signo, sin cambiar la referencia principal del eje de inserción.
    view_up = _get_view_up_axis(context, normal)
    if view_up.length > 1e-8 and y_axis.dot(view_up) < 0.0:
        y_axis.negate()

    x_axis = y_axis.cross(z_axis)
    if x_axis.length < 1e-8:
        x_axis = _get_view_right_axis(context, normal)
    else:
        x_axis.normalize()

    view_right = _get_view_right_axis(context, normal)
    if view_right.length > 1e-8 and x_axis.dot(view_right) < 0.0:
        x_axis.negate()

    return x_axis.normalized()

def update_engrave_axis_from_sleeve_base(context, props):
    """Recalcula y guarda la orientación del grabado según el eje de inserción."""
    loc = Vector(props.engrave_location)
    normal = _normalized_or_fallback(props.engrave_normal, (0, 0, 1))
    x_axis = get_engrave_x_axis_perpendicular_to_sleeve_base(context, props, loc, normal)
    props.engrave_x_axis = (float(x_axis.x), float(x_axis.y), float(x_axis.z))
    return x_axis


def create_or_update_engrave_anchor(context, props):
    loc = Vector(props.engrave_location)
    normal = _normalized_or_fallback(props.engrave_normal, (0, 0, 1))
    anchor = bpy.data.objects.get(ENGRAVE_ANCHOR_NAME)
    if anchor is None:
        anchor = bpy.data.objects.new(ENGRAVE_ANCHOR_NAME, None)
        anchor.empty_display_type = 'PLAIN_AXES'
        anchor.empty_display_size = 3.0
        link_object(context, anchor)
    anchor.location = loc + normal * 0.25
    anchor.show_in_front = True
    register_dsg_object(anchor, ROLE_ENGRAVE, ENGRAVE_ANCHOR_NAME)
    return anchor


def get_engrave_basis(location, normal, x_axis=None):
    """Devuelve ejes ortonormales del grabado: X lectura, Y alto, Z exterior."""
    n = _normalized_or_fallback(normal, (0, 0, 1))
    z_axis = n.normalized()
    if x_axis is None or Vector(x_axis).length < 1e-8:
        ref = Vector((1.0, 0.0, 0.0))
        if abs(ref.dot(z_axis)) > 0.92:
            ref = Vector((0.0, 1.0, 0.0))
        x = ref - z_axis * ref.dot(z_axis)
    else:
        x = Vector(x_axis) - z_axis * Vector(x_axis).dot(z_axis)
        if x.length < 1e-8:
            ref = Vector((1.0, 0.0, 0.0))
            if abs(ref.dot(z_axis)) > 0.92:
                ref = Vector((0.0, 1.0, 0.0))
            x = ref - z_axis * ref.dot(z_axis)
    x_axis = x.normalized()
    y_axis = z_axis.cross(x_axis).normalized()
    x_axis = y_axis.cross(z_axis).normalized()
    return x_axis, y_axis, z_axis


def raycast_object_along_world(context, obj, origin_world, direction_world, distance=80.0):
    """Raycast mundo→objeto usando el mismo fallback seguro del selector modal."""
    if not _valid_obj(obj) or obj.type != 'MESH':
        return None, None, None
    direction = Vector(direction_world)
    if direction.length < 1e-8:
        return None, None, None
    direction.normalize()

    try:
        mx = obj.matrix_world.copy()
        mx_inv = mx.inverted_safe()
    except Exception:
        return None, None, None

    origin_local = mx_inv @ Vector(origin_world)
    target_local = mx_inv @ (Vector(origin_world) + direction * float(distance))
    direction_local = target_local - origin_local
    if direction_local.length < 1e-8:
        return None, None, None
    direction_local.normalize()

    hit, loc, normal, face_index = _raycast_local_safe(
        context, obj, origin_local, direction_local, distance=float(distance))
    if not hit or loc is None:
        return None, None, None

    world_loc = mx @ Vector(loc)
    normal = Vector(normal) if normal is not None else Vector((0.0, 0.0, 0.0))
    world_normal = (mx.to_3x3() @ normal).normalized() if normal.length > 1e-8 else None
    return world_loc, world_normal, face_index


def project_flat_engrave_mesh_to_plane(context, props, text_obj, depth=0.45, preview=False):
    """Remapea el texto a un cutter plano rápido, sin raycast por vértice.

    Es el modo recomendado para evitar bloqueos en Blender: conserva la lectura
    y orientación clínica del nombre, pero no obliga a proyectar cada vértice
    sobre la guía antes del boolean. El texto atraviesa la guía desde un pequeño
    margen exterior hacia dentro.
    """
    if text_obj is None or text_obj.type != 'MESH':
        return False

    loc = Vector(props.engrave_location)
    base_normal = _normalized_or_fallback(props.engrave_normal, (0, 0, 1))
    x_axis = _normalized_or_fallback(props.engrave_x_axis, (1, 0, 0))
    x_axis, y_axis, z_axis = get_engrave_basis(loc, base_normal, x_axis)

    verts = list(text_obj.data.vertices)
    if not verts:
        return False

    z_values = [float(v.co.z) for v in verts]
    z_min = min(z_values)
    z_max = max(z_values)
    z_span = max(1e-6, z_max - z_min)

    if preview:
        outside_margin = 0.20
        inside_depth = 0.0
    else:
        outside_margin = 0.22
        inside_depth = max(0.05, float(depth)) + 0.22

    mw_inv = text_obj.matrix_world.inverted()
    for v in verts:
        local = Vector(v.co)
        flat_world = loc + x_axis * local.x + y_axis * local.y
        if preview:
            offset = outside_margin
        else:
            t = (float(local.z) - z_min) / z_span
            offset = -inside_depth + t * (inside_depth + outside_margin)
        v.co = mw_inv @ (flat_world + z_axis * offset)

    text_obj.data.update()
    return True


def _engrave_raycast_bvh(tree, guide_matrix, guide_inv, origin_world, direction_world, distance):
    """Raycast rápido con un BVHTree ya construido para no evaluar la guía por vértice."""
    if tree is None:
        return None, None
    direction = Vector(direction_world)
    if direction.length < 1e-8:
        return None, None
    direction.normalize()

    origin_local = guide_inv @ Vector(origin_world)
    target_local = guide_inv @ (Vector(origin_world) + direction * float(distance))
    direction_local = target_local - origin_local
    local_distance = direction_local.length
    if direction_local.length < 1e-8:
        return None, None
    direction_local.normalize()

    try:
        loc_local, normal_local, face_index, dist = tree.ray_cast(origin_local, direction_local, local_distance)
    except Exception:
        return None, None
    if loc_local is None:
        return None, None
    world_loc = guide_matrix @ loc_local
    if normal_local is None or normal_local.length < 1e-8:
        world_normal = None
    else:
        world_normal = (guide_matrix.to_3x3() @ normal_local).normalized()
    return world_loc, world_normal


def _engrave_projection_signature(guide, props):
    """Stable key for reusing the preview's curved surface projection."""
    if not _valid_obj(guide) or getattr(guide, 'data', None) is None:
        return None
    try:
        data_ptr = int(guide.data.as_pointer())
    except Exception:
        data_ptr = id(guide.data)
    try:
        matrix_key = tuple(round(float(value), 6) for row in guide.matrix_world for value in row)
    except Exception:
        matrix_key = ()
    return (
        data_ptr,
        int(len(guide.data.vertices)),
        int(len(guide.data.polygons)),
        matrix_key,
        str((getattr(props, 'engrave_patient_text', '') or '').strip().upper()),
        round(float(getattr(props, 'engrave_text_size', 3.0)), 5),
        tuple(round(float(v), 5) for v in getattr(props, 'engrave_location', (0.0, 0.0, 0.0))),
        tuple(round(float(v), 6) for v in getattr(props, 'engrave_normal', (0.0, 0.0, 1.0))),
        tuple(round(float(v), 6) for v in getattr(props, 'engrave_x_axis', (1.0, 0.0, 0.0))),
    )


def _store_engrave_projection_cache(signature, ray_cache):
    if signature is None or not ray_cache:
        return
    payload = {}
    for key, (surface, normal, hit_ok) in ray_cache.items():
        payload[key] = (
            tuple(float(v) for v in surface),
            tuple(float(v) for v in normal),
            bool(hit_ok),
        )
    _ENGRAVE_PROJECTION_CACHE[signature] = payload
    while len(_ENGRAVE_PROJECTION_CACHE) > _ENGRAVE_PROJECTION_CACHE_MAX_ENTRIES:
        try:
            _ENGRAVE_PROJECTION_CACHE.pop(next(iter(_ENGRAVE_PROJECTION_CACHE)))
        except Exception:
            break


def _load_engrave_projection_cache(signature):
    raw = _ENGRAVE_PROJECTION_CACHE.get(signature) if signature is not None else None
    if not raw:
        return None
    return {
        key: (Vector(surface), Vector(normal), bool(hit_ok))
        for key, (surface, normal, hit_ok) in raw.items()
    }


def project_engrave_mesh_to_guide_curvature(context, props, text_obj, depth=0.45, preview=False):
    """Adapta una malla de texto a la curvatura local de DSG_Guide.

    Versión eficiente:
    · Construye un BVHTree una sola vez.
    · Proyecta sobre la guía en la dirección del grabado.
    · Cachea los raycasts por coordenada XY local del texto, porque el texto
      extruido suele tener varios vértices con la misma posición XY y distinta Z.
    · Mantiene un fallback plano si la zona elegida no permite raycast fiable.
    """
    if text_obj is None or text_obj.type != 'MESH':
        return False

    guide = get_active_guide_obj(props)
    if not _valid_obj(guide):
        return False

    loc = Vector(props.engrave_location)
    base_normal = _normalized_or_fallback(props.engrave_normal, (0, 0, 1))
    x_axis = _normalized_or_fallback(props.engrave_x_axis, (1, 0, 0))
    x_axis, y_axis, z_axis = get_engrave_basis(loc, base_normal, x_axis)

    verts = list(text_obj.data.vertices)
    if not verts:
        return False

    projection_signature = _engrave_projection_signature(guide, props)
    cached_projection = None if preview else _load_engrave_projection_cache(projection_signature)

    tree = None
    guide_matrix = guide.matrix_world.copy()
    guide_inv = guide_matrix.inverted_safe()
    if cached_projection is None:
        try:
            depsgraph = context.evaluated_depsgraph_get()
            guide_eval = guide.evaluated_get(depsgraph)
            guide_matrix = guide_eval.matrix_world.copy()
            guide_inv = guide_matrix.inverted_safe()
            tree = BVHTree.FromObject(guide_eval, depsgraph)
        except Exception as e:
            print(f"[DSG] Engraving BVH unavailable; using fast flat engraving: {e}")
            return project_flat_engrave_mesh_to_plane(context, props, text_obj, depth=depth, preview=preview)

        if tree is None:
            return project_flat_engrave_mesh_to_plane(context, props, text_obj, depth=depth, preview=preview)

    z_values = [float(v.co.z) for v in verts]
    z_min = min(z_values)
    z_max = max(z_values)
    z_span = max(1e-6, z_max - z_min)

    if preview:
        outside_margin = 0.20
        inside_depth = 0.0
    else:
        outside_margin = 0.22
        inside_depth = max(0.05, float(depth)) + 0.22

    ray_back = max(8.0, float(getattr(props, 'engrave_text_size', 3.0)) * 3.0 + inside_depth + 4.0)
    ray_forward = max(16.0, float(getattr(props, 'engrave_text_size', 3.0)) * 5.0 + inside_depth + 8.0)
    total_ray_distance = ray_back + ray_forward

    mw_inv = text_obj.matrix_world.inverted_safe()
    projected_count = 0
    ray_cache = cached_projection if cached_projection is not None else {}

    # Cuantización muy fina solo para agrupar vértices duplicados del texto
    # extruido. No debe mover clínicamente el texto ni borrar la curvatura.
    cache_precision = 10000.0  # 0.0001 mm en coordenadas locales del texto

    for v in verts:
        local = Vector(v.co)
        cache_key = (round(float(local.x) * cache_precision), round(float(local.y) * cache_precision))

        cached = ray_cache.get(cache_key)
        if cached is None:
            flat_world = loc + x_axis * local.x + y_axis * local.y
            ray_origin = flat_world + z_axis * ray_back
            surf, surf_normal = _engrave_raycast_bvh(
                tree, guide_matrix, guide_inv, ray_origin, -z_axis, total_ray_distance
            )
            if surf is None:
                ray_origin = flat_world - z_axis * ray_back
                surf, surf_normal = _engrave_raycast_bvh(
                    tree, guide_matrix, guide_inv, ray_origin, z_axis, total_ray_distance
                )

            if surf is None:
                surf = flat_world
                surf_normal = z_axis
                hit_ok = False
            else:
                hit_ok = True
                if surf_normal is None or surf_normal.length < 1e-8:
                    surf_normal = z_axis
                elif surf_normal.dot(z_axis) < 0.0:
                    surf_normal.negate()
                surf_normal.normalize()

            cached = (surf, surf_normal, hit_ok)
            ray_cache[cache_key] = cached

        surf, surf_normal, hit_ok = cached
        if hit_ok:
            projected_count += 1

        if preview:
            offset = outside_margin
        else:
            t = (float(local.z) - z_min) / z_span
            offset = -inside_depth + t * (inside_depth + outside_margin)

        world_pos = surf + surf_normal * offset
        v.co = mw_inv @ world_pos

    text_obj.data.update()
    if preview and projected_count > 0:
        _store_engrave_projection_cache(projection_signature, ray_cache)
    try:
        text_obj['DSG_engrave_projection_cache_reused'] = bool(cached_projection is not None)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    return projected_count > 0

def create_engrave_text_mesh_object(context, name, body, size, extrude, matrix_world, resolution_u=2):
    """Crea el grabado con la biblioteca interna low-poly de DSG.

    ``resolution_u`` se conserva en la firma para compatibilidad con archivos y
    operadores anteriores, pero ya no interviene: no se crean curvas FONT ni se
    ejecuta ``bpy.ops.object.convert``. El resultado es una sola malla ligera,
    determinista y sin dependencias externas.
    """
    try:
        mesh_obj = glyph_library.create_glyph_mesh_object(
            context=context,
            name=name,
            body=body,
            size=max(0.5, float(size)),
            extrude=max(0.0, float(extrude)),
            matrix_world=matrix_world,
        )
    except Exception as exc:
        print(f"[DSG] Could not create internal glyph mesh: {type(exc).__name__}: {exc}")
        return None

    if mesh_obj is None:
        return None
    mesh_obj.name = name
    if getattr(mesh_obj, 'data', None) is not None:
        mesh_obj.data.name = name + '_Mesh'
    return mesh_obj


def create_or_update_engrave_preview(context, props):
    """Muestra una previsualización curva no destructiva del texto en la superficie."""
    if not getattr(props, 'engrave_has_position', False):
        return None

    body = (props.engrave_patient_text or "NAME").strip() or "NAME"
    loc = Vector(props.engrave_location)
    normal = _normalized_or_fallback(props.engrave_normal, (0, 0, 1))
    x_axis = update_engrave_axis_from_sleeve_base(context, props)

    safe_remove_engrave_object(ENGRAVE_PREVIEW_NAME)
    preview = create_engrave_text_mesh_object(
        context,
        ENGRAVE_PREVIEW_NAME,
        body,
        max(0.5, float(props.engrave_text_size)),
        0.0,
        build_engrave_orientation_matrix(loc + normal * 0.18, normal, x_axis),
        max(1, int(getattr(props, 'engrave_curve_resolution', 2))),
    )
    if preview is None:
        return None

    # Vista previa curva por defecto: conserva la curvatura real de la férula.
    if bool(getattr(props, 'engrave_project_to_curvature', True)):
        project_engrave_mesh_to_guide_curvature(context, props, preview, depth=0.0, preview=True)
    else:
        project_flat_engrave_mesh_to_plane(context, props, preview, depth=0.0, preview=True)
    preview.display_type = 'SOLID'
    preview.show_wire = False
    preview.color = (0.12, 0.62, 0.52, 1.0)
    preview.show_in_front = True
    register_dsg_object(preview, ROLE_ENGRAVE, ENGRAVE_PREVIEW_NAME)
    return preview

def create_engrave_text_cutter(context, props):
    """Crea un texto sólido para recortar la guía con Boolean Difference."""
    body = (props.engrave_patient_text or '').strip()
    if not body:
        return None
    if not getattr(props, 'engrave_has_position', False):
        return None

    safe_remove_engrave_object(ENGRAVE_CUTTER_NAME)

    loc = Vector(props.engrave_location)
    normal = _normalized_or_fallback(props.engrave_normal, (0, 0, 1))
    x_axis = update_engrave_axis_from_sleeve_base(context, props)
    depth = max(0.05, float(props.engrave_depth))
    # El texto se crea con su cara frontal hacia fuera, se convierte to mesh
    # y se proyecta por raycast sobre DSG_Guide para que el cutter siga
    # la curvatura local antes del boolean.
    cutter = create_engrave_text_mesh_object(
        context,
        ENGRAVE_CUTTER_NAME,
        body,
        max(0.5, float(props.engrave_text_size)),
        depth + 0.25,
        build_engrave_orientation_matrix(loc, normal, x_axis),
        max(1, int(getattr(props, 'engrave_curve_resolution', 2))),
    )
    if cutter is None:
        return None

    if bool(getattr(props, 'engrave_project_to_curvature', True)):
        ok = project_engrave_mesh_to_guide_curvature(context, props, cutter, depth=depth, preview=False)
        engrave_mode = "CURVED_BVH"
        if not ok:
            print('[DSG] Warning: not all text could be projected onto the guide; fast flat fallback was used')
            ok = project_flat_engrave_mesh_to_plane(context, props, cutter, depth=depth, preview=False)
            engrave_mode = "FAST_PLANAR_FALLBACK"
    else:
        ok = project_flat_engrave_mesh_to_plane(context, props, cutter, depth=depth, preview=False)
        engrave_mode = "FAST_PLANAR"

    if not ok:
        print('[DSG] Aviso: no se pudo preparar el cutter de grabado')

    register_dsg_object(cutter, ROLE_CUTTER, ENGRAVE_CUTTER_NAME, {"DSG_cut_type": "patient_engrave", "DSG_engrave_mode": engrave_mode})
    cutter.display_type = 'WIRE'
    cutter.show_in_front = True
    return cutter


def _remove_modifier_if_present(obj, name):
    try:
        modifier = obj.modifiers.get(name) if _valid_obj(obj) else None
        if modifier is not None:
            obj.modifiers.remove(modifier)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)


def _engrave_boolean_result_plausible(guide, before_counts):
    """Cheap validation for a shallow local engraving cut."""
    if not _valid_obj(guide) or guide.type != 'MESH' or guide.data is None:
        return False, 'invalid result'
    after_counts = (len(guide.data.vertices), len(guide.data.edges), len(guide.data.polygons))
    if after_counts[0] <= 0 or after_counts[2] <= 0:
        return False, 'empty result'
    if tuple(after_counts) == tuple(before_counts):
        return False, 'Boolean did not change the guide'
    # For ordinary guide sizes this audit is fast and catches the main FAST
    # solver failure mode. Very dense guides skip it instead of becoming the
    # new bottleneck; the original mesh remains available for fallback.
    report = get_mesh_solid_report(guide, max_polygons=420000)
    if report.get('checked') and not report.get('solid'):
        return False, (
            f'non-manifold result: edges={report.get("bad_edges")}, '
            f'faces={report.get("degenerate_faces")}')
    return True, 'solid result' if report.get('checked') else 'large result accepted'


def apply_patient_engrave_transactional(context, guide, cutter):
    """FAST-first local engraving with exact transactional fallbacks.

    Patient text is a small, shallow, manifold cutter. Running hole-tolerant
    EXACT on the complete high-resolution guide was the dominant delay. This
    routine first uses Blender's FAST solver, validates the result, then falls
    back to standard EXACT and finally robust EXACT only when required. The
    untouched source mesh is restored before every retry.
    """
    if not _valid_obj(guide) or not _valid_obj(cutter):
        return False, None, 'invalid objects', 0.0

    started = time.perf_counter()
    clean_boolean_cutter_mesh(cutter)
    original_mesh = guide.data.copy()
    before_counts = (len(guide.data.vertices), len(guide.data.edges), len(guide.data.polygons))
    attempts = (
        ('FAST', False),
        ('EXACT', False),
        ('EXACT_ROBUST', True),
    )
    last_reason = 'Boolean failed'

    for attempt_index, (solver_name, robust) in enumerate(attempts):
        if attempt_index:
            _restore_object_mesh_copy(guide, original_mesh.copy())
            try:
                context.view_layer.update()
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)

        modifier_name = f'DSG_PatientName_{solver_name}'
        _remove_modifier_if_present(guide, modifier_name)
        mod = guide.modifiers.new(modifier_name, 'BOOLEAN')
        mod.operation = 'DIFFERENCE'
        mod.object = cutter
        try:
            mod.solver = 'FAST' if solver_name == 'FAST' else 'EXACT'
            if hasattr(mod, 'double_threshold'):
                mod.double_threshold = 0.00001
            set_boolean_exact_options(mod, robust=bool(robust))
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)

        ok = apply_modifier_direct(context, guide, mod.name)
        if not ok:
            _remove_modifier_if_present(guide, modifier_name)
            last_reason = f'{solver_name} could not be applied'
            continue

        plausible, reason = _engrave_boolean_result_plausible(guide, before_counts)
        if plausible:
            try:
                if original_mesh.users == 0:
                    bpy.data.meshes.remove(original_mesh)
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
            elapsed = time.perf_counter() - started
            try:
                guide['DSG_engrave_solver'] = str(solver_name)
                guide['DSG_engrave_elapsed_seconds'] = float(elapsed)
                guide['DSG_engrave_fast_pipeline'] = True
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
            return True, solver_name, reason, elapsed

        last_reason = f'{solver_name}: {reason}'

    _restore_object_mesh_copy(guide, original_mesh)
    elapsed = time.perf_counter() - started
    return False, None, last_reason, elapsed


def raycast_sleeve_lateral_on_guide(context, event, props):
    """
    Identifica el sleeve mediante raycast, pero no permite usar su caras planas.

    El clic solo define qué sleeve y qué dirección radial usar. Cuando la pared
    invulnerable está activa, el punto se traslada automáticamente a un puerto
    seguro en la pared lateral. Así ningún tubo exterior ni canal interno altera la
    caras anulares planas del sleeve.
    """
    guide = props.guide_obj
    if guide is None or guide.type != 'MESH':
        return None, None

    loc, normal, _ = do_raycast_detailed(context, event, guide)
    if loc is None or normal is None:
        return None, None

    implants = get_all_implant_objects(props)
    if not implants:
        return None, None

    inner_r = _sleeve_inner_radius_from_props(props)
    outer_r = inner_r + props.sleeve_wall
    half_h = props.sleeve_height * 0.5

    best_implant = None
    best_radial_world = None
    best_score = float('inf')

    for implant in implants:
        try:
            sleeve_mx = get_sleeve_matrix_world(props, implant)
            local = sleeve_mx.inverted() @ loc
        except Exception:
            continue

        radial = math.hypot(local.x, local.y)
        radial_tol = max(0.8, props.irr_inner_diameter * 0.35)
        z_tol = max(0.6, props.irr_inner_diameter * 0.25)

        on_cyl_band = abs(radial - outer_r) <= radial_tol
        within_height = abs(local.z) <= (half_h + z_tol)

        axis_world = (sleeve_mx.to_3x3() @ Vector((0, 0, 1))).normalized()
        lateral_score = abs(normal.normalized().dot(axis_world))
        lateral_enough = lateral_score < 0.45

        if not (on_cyl_band and within_height and lateral_enough):
            continue

        radial_local = Vector((local.x, local.y, 0.0))
        if radial_local.length < 1e-6:
            radial_local = Vector((1.0, 0.0, 0.0))
        radial_local.normalize()
        radial_world = (sleeve_mx.to_3x3() @ radial_local).normalized()

        radial_error = abs(radial - outer_r)
        z_error = max(0.0, abs(local.z) - half_h)
        score = radial_error + z_error + lateral_score * 0.5
        if score < best_score:
            best_score = score
            best_implant = implant
            best_radial_world = radial_world

    if not is_valid_implant_obj(best_implant):
        return None, None

    props.implant_obj = best_implant
    if sleeve_sidewall_guard_enabled(props):
        outer_r_tube = props.irr_inner_diameter * 0.5 + props.irr_wall_thickness
        port = get_sleeve_apical_port_geometry(loc, props, best_implant, outer_tube_radius=outer_r_tube)
        if port is None:
            return None, None
        return port['external_anchor'].copy(), port['radial'].copy()
    return loc, best_radial_world

# ─────────────────────────────────────────────────────────────
# Preflight manual de booleanas críticas
# ─────────────────────────────────────────────────────────────

class DSG_OT_RunBooleanPreflight(Operator):
    bl_idname = 'dsg.run_boolean_preflight'
    bl_label = 'Check / Repair Meshes'
    bl_options = {'REGISTER', 'UNDO'}

    target: StringProperty(default='drill')

    def execute(self, context):
        props = context.scene.dsg_props
        target = str(self.target or 'drill')

        if target == 'sleeve':
            frame = _workflow_frame_candidate(props)
            previews = get_sleeve_preview_objects()
            if not _valid_obj(frame) or not previews:
                _dsg_report(self, {'ERROR'}, 'Generate the frame and sleeve preview first', 'Genera primero la estructura y la vista previa de cilindros')
                return {'CANCELLED'}
            results = [run_boolean_preflight(
                context, frame, 'sleeve_union_frame', try_repair=True,
                max_polygons=800000, merge_dist=0.001)]
            for idx, sleeve in enumerate(previews, start=1):
                results.append(run_boolean_preflight(
                    context, sleeve, f'sleeve_union_part_{idx}', try_repair=True,
                    max_polygons=300000, merge_dist=0.0005))
            result = combine_boolean_preflights(
                frame, 'sleeve_union', results, label='UNION frame + sleeves')

        elif target == 'final':
            guide = props.dct_object_being_cut or props.guide_obj
            if not _valid_obj(guide):
                _dsg_report(self, {'ERROR'}, 'DSG_Guide not found', 'No se encontró DSG_Guide')
                return {'CANCELLED'}
            result = run_boolean_preflight(
                context, guide, 'final_cut_guide', try_repair=True,
                max_polygons=900000, merge_dist=0.0005)
            store_boolean_preflight(guide, 'final_cut', result)

        elif target == 'irrigation':
            guide = props.guide_obj
            preview = get_pending_irrigation_preview(props)
            if not _valid_obj(guide) or not _valid_obj(preview):
                _dsg_report(self, {'ERROR'}, 'No guide and irrigation preview are available', 'No hay guía y vista previa de irrigación')
                return {'CANCELLED'}
            path_world = get_irrigation_preview_path_world(preview)
            implant = bpy.data.objects.get(str(preview.get('DSG_implant', '')))
            outer_radius = props.irr_inner_diameter * 0.5 + props.irr_wall_thickness
            temp = build_blended_irrigation_outer_tube_mesh(
                context, path_world, outer_radius, props, implant_obj=implant,
                name=preview.name + '_PreflightImperativeTube',
                bevel_resolution=props.irr_bevel_resolution,
                smooth_iters=props.irr_curve_smooth_iters,
                entry_mode='full')
            if not _valid_obj(temp):
                _dsg_report(self, {'ERROR'}, 'Could not create the mandatory tube for preflight', 'No se pudo construir el tubo imperativo para el preflight')
                return {'CANCELLED'}
            results = [
                run_boolean_preflight(context, guide, 'irrigation_union_guide', True, 800000),
                run_boolean_preflight(context, temp, 'irrigation_union_tube', True, 500000),
            ]
            result = combine_boolean_preflights(
                guide, 'irrigation_union', results,
                label='Mandatory irrigation: guide + deep tube')
            safe_remove_object(temp)

        else:
            guide = props.guide_obj
            if not _valid_obj(guide):
                _dsg_report(self, {'ERROR'}, 'DSG_Guide not found', 'No se encontró DSG_Guide')
                return {'CANCELLED'}
            result = run_boolean_preflight(
                context, guide, 'drill_guide',
                try_repair=bool(getattr(props, 'drill_precheck_make_manifold', True)),
                max_polygons=800000,
                merge_dist=max(0.0005, float(getattr(props, 'drill_pre_remesh_voxel', 0.10)) * 0.01))

        level = {'green': 'INFO', 'orange': 'WARNING', 'red': 'ERROR'}.get(result.get('status'), 'WARNING')
        _dsg_report(self, {level}, result.get('message', 'Preflight completed'), result.get('message', 'Preflight completado'))
        return {'CANCELLED'} if result.get('status') == 'red' else {'FINISHED'}


# ─────────────────────────────────────────────────────────────
# Operadores — Pasos 1-5
# ─────────────────────────────────────────────────────────────

class DSG_OT_ForceOrthographicView(Operator):
    bl_idname = "dsg.force_orthographic_view"
    bl_label = "Restore Orthographic Precision View"
    bl_description = "Removes perspective distortion without changing the current viewing direction"
    bl_options = {'REGISTER'}

    def execute(self, context):
        props = context.scene.dsg_props
        props.precision_ortho_lock = True
        changed = activate_precision_orthographic(context, force=True)
        _dsg_report(
            self, {'INFO'},
            f'Orthographic precision view active ({changed} viewport(s) updated)',
            f'Vista ortográfica de precisión activa ({changed} vista(s) actualizadas)')
        return {'FINISHED'}


class DSG_OT_Reset(Operator):
    bl_idname = "dsg.reset"
    bl_label  = "Reset Workflow"
    bl_description = "Deletes all addon-generated work and preserves only the initial model"
    bl_options = {'REGISTER', 'UNDO'}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        props = context.scene.dsg_props
        # A guide reset must never leave an immediate-extraction target hidden.
        if bool(context.scene.get("DSG_immediate_extraction_prepared", False)) or str(context.scene.get("DSG_immediate_extraction_tooth", "") or ""):
            try:
                restore_immediate_extraction(context.scene)
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
        _clear_all_workflow_checkpoints(context.scene)
        _PREFLIGHT_UI_CACHE.clear()

        preserved_model = props.model_obj if _valid_obj(getattr(props, 'model_obj', None)) else None
        if not _valid_obj(preserved_model):
            _dsg_report(self, {'ERROR'}, "No initial model has been confirmed", "No hay un modelo inicial confirmado")
            return {'CANCELLED'}

        # Stop cualquier modo modal antes de retirar sus objetos de apoyo.
        props.drawing_active = False
        props.irr_drawing_active = False
        unregister_contour_draw_handler()
        unregister_irr_draw_handler()
        _draw_callback_irrigation._current_chain = []
        _clear_all_dicom_measurements()

        # El modelo inicial puede estar enlazado a una colección DSG, pero debe
        # sobrevivir al vaciado completo del flujo.
        unlink_object_from_dsg_collections(preserved_model)

        # Delete todos los objetos contenidos en la jerarquía DSG, excepto el
        # modelo inicial. Esto cubre también objetos temporales cuyo nombre haya
        # cambiado o cuyos punteros se hayan perdido.
        root = bpy.data.collections.get(DSG_ROOT_COLLECTION_NAME)
        objects_to_remove = []
        visited_collections = set()

        def collect_collection_objects(collection):
            if collection is None:
                return
            try:
                key = collection.as_pointer()
            except Exception:
                key = id(collection)
            if key in visited_collections:
                return
            visited_collections.add(key)
            try:
                for obj in list(collection.objects):
                    if _valid_obj(obj) and obj != preserved_model and obj not in objects_to_remove:
                        objects_to_remove.append(obj)
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
            try:
                for child in list(collection.children):
                    collect_collection_objects(child)
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)

        collect_collection_objects(root)


        for obj in objects_to_remove:
            safe_remove_object(obj)

        # Limpieza de respaldo para temporales antiguos o no registrados.
        exact_names = [
            AXIS_EMPTY_NAME, BASE_PERIMETER_CURVE_NAME, HOLE_REPAIRED_MODEL_NAME, CLOSED_MODEL_NAME, BLOCKOUT_NAME, BLOCKOUT_CANDIDATE_NAME, BLOCKOUT_VISUAL_NAME, *RETENTION_PREVIEW_NAMES.values(), *RETENTION_BOUNDARY_PREVIEW_NAMES.values(), RETENTION_BOUNDARY_NAME, COMBINED_NAME, COMBINED_CANDIDATE_NAME, FRAME_NAME, GUIDE_NAME,
            DRILL_BATCH_CUTTER_NAME, DRILL_PROTECTION_RESULT_NAME,
            ENGRAVE_ANCHOR_NAME, ENGRAVE_PREVIEW_NAME, ENGRAVE_CUTTER_NAME,
            REINFORCEMENT_PREVIEW_NAME, REINFORCEMENT_MARKER_NAME,
            REINFORCEMENT_COMBINED_TMP_NAME, MICROSCREW_PREVIEW_NAME,
            MICROSCREW_MARKER_NAME, MICROSCREW_FRAME_COMBINED_TMP_NAME,
            "DSG_Orig_Copy", "DSG_Blockout_Copy",
        ]
        for name in exact_names:
            obj = bpy.data.objects.get(name)
            if _valid_obj(obj) and obj != preserved_model:
                safe_remove_object(obj)

        prefixes = [
            IMPLANT_PREFIX, IMPLANT_SAFETY_PREFIX, SLEEVE_PREFIX, DRILL_PREFIX,
            ANIMATED_DRILL_PREFIX, ANIMATED_MICROSCREW_PREFIX,
            IRR_PREVIEW_PREFIX, IRR_PREVIEW_PATH_PREFIX, IRR_WALL_PREFIX,
            "DSG_Irr_", "DSG_IrrCut_", REINFORCEMENT_PREFIX, REINFORCEMENT_MARKER_PREFIX, MICROSCREW_PREFIX,
            DRILL_PROTECTION_PREFIX, "DSG_SleeveApplyTmp_",
            "DSG_FinalSolidCutter", "DSG_FinalCut_", "DSG_FinalGuide_Work",
        ]
        for prefix in prefixes:
            for obj in list(bpy.data.objects):
                try:
                    matches = obj.name.startswith(prefix)
                except Exception:
                    matches = False
                if matches and obj != preserved_model:
                    safe_remove_object(obj)

        # Reset el estado del flujo, conservando el puntero al modelo inicial.
        _IMPLANT_STEP_RETURN_STATE.pop(str(context.scene.name), None)
        _IMPLANT_STEP_RESTORE_PENDING.discard(str(context.scene.name))
        if GUIDE_HOME_SCENE_KEY in context.scene:
            del context.scene[GUIDE_HOME_SCENE_KEY]
        for key in (
                WORKFLOW_LAST_VALID_STEP_KEY, WORKFLOW_GATE_MESSAGE_KEY,
                WORKFLOW_GATE_TARGET_KEY, WORKFLOW_GATE_FALLBACK_KEY,
                WORKFLOW_IRRIGATION_RESOLVED_KEY,
                WORKFLOW_REINFORCEMENT_RESOLVED_KEY,
                WORKFLOW_IMPLANTS_CONFIRMED_KEY,
                'DSG_workflow_contour_confirmed',
                'DSG_workflow_contour_point_count'):
            try:
                del context.scene[key]
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
        props.current_step = STEP_MODEL
        context.scene[GUIDE_FLOW_ORDER_KEY] = GUIDE_FLOW_ORDER_MODEL_IMPLANT
        props.irr_chain_count = 0
        props.irr_paths_json = "[]"
        props.reinforcement_count = 0
        props.microscrew_count = 0
        props.microscrew_records_json = "[]"
        props.contour_points.clear()
        props.implant_obj = None
        props.parallel_master_implant = None
        props.frame_obj = None
        props.guide_obj = None
        props.dct_object_being_cut = None
        props.dct_object_making_cut = None
        props.irr_preview_obj = None
        props.reinforcement_preview_obj = None
        props.microscrew_preview_obj = None
        props.engrave_has_position = False
        props.show_parallel_tools = False
        props.show_sleeve_window_options = False
        props.show_irrigation_channel_options = False
        props.show_reinforcement_options = False
        props.show_sequence_panel = False
        props.show_name_tools = False
        props.show_final_visibility = False
        props.show_reset_flow = False
        props.model_obj = preserved_model

        try:
            preserved_model.hide_viewport = False
            preserved_model.hide_render = False
            preserved_model.hide_select = False
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        try:
            context.scene.frame_set(1)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        _isolate_ios_for_guide(context, preserved_model)
        set_active(context, preserved_model)

        removed_collections = cleanup_empty_dsg_collections(remove_root_if_empty=True)
        _dsg_report(self, {'INFO'}, f"Workflow reset; model preserved ({removed_collections} collections cleared)", f"Flujo reiniciado; modelo conservado ({removed_collections} colecciones limpiadas)")
        return {'FINISHED'}


class DSG_OT_ResetCurrentStep(Operator):
    bl_idname = "dsg.reset_current_step"
    bl_label = "Back One Clinical Step"
    bl_description = "Restores the previous clinical DSG step and its saved geometry"
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls, context):
        props = getattr(getattr(context, 'scene', None), 'dsg_props', None)
        return bool(props is not None and int(getattr(props, 'current_step', STEP_MODEL)) >= STEP_MODEL)

    def _return_to_alignment(self, context, props):
        """Restore the alignment review without deleting DSG geometry."""
        try:
            from . import alignment_module as alignment
        except Exception as exc:
            _dsg_report(
                self, {'ERROR'},
                f'Alignment module is unavailable: {exc}',
                f'El módulo de alineamiento no está disponible: {exc}')
            return {'CANCELLED'}

        alignment_props = getattr(context.scene, 'dicp_props', None)
        if alignment_props is None:
            _dsg_report(
                self, {'ERROR'},
                'Alignment state is unavailable',
                'El estado del alineamiento no está disponible')
            return {'CANCELLED'}

        source = getattr(alignment_props, 'icp_source_obj', None)
        target = getattr(alignment_props, 'icp_target_obj', None)
        source_valid = source is not None and source.name in bpy.data.objects
        target_valid = target is not None and target.name in bpy.data.objects
        if not source_valid or not target_valid:
            _dsg_report(
                self, {'WARNING'},
                'The alignment input models are no longer available',
                'Los modelos utilizados en el alineamiento ya no están disponibles')
            return {'CANCELLED'}

        props.drawing_active = False
        props.irr_drawing_active = False
        unregister_contour_draw_handler()
        unregister_irr_draw_handler()
        _draw_callback_irrigation._current_chain = []

        context.scene[SUITE_STAGE_KEY] = 'ALIGNMENT'
        if bool(getattr(alignment_props, 'aligned', False)):
            alignment_props.current_step = alignment.STEP_DONE
        elif int(getattr(alignment_props, 'source_point_count', 0)) == 3 and int(getattr(alignment_props, 'target_point_count', 0)) == 3:
            alignment_props.current_step = alignment.STEP_READY
        else:
            alignment_props.current_step = alignment.STEP_MODELS

        try:
            source.hide_viewport = False
            source.hide_render = False
            source.hide_select = False
            target.hide_viewport = False
            target.hide_render = False
            target.hide_select = False
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)

        try:
            if bool(getattr(alignment_props, 'aligned', False)):
                alignment._prepare_alignment_review_view(context, source, target)
                alignment._set_markers_hidden(True)
            else:
                alignment._set_markers_hidden(False)
                context.view_layer.objects.active = source
                source.select_set(True)
        except Exception as exc:
            # The stage change remains valid even when a particular viewport
            # cannot be framed (for example, a non-3D context during redraw).
            print(f'[DSG] Alignment review framing warning: {exc}')

        try:
            if context.area:
                context.area.tag_redraw()
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)

        _dsg_report(
            self, {'INFO'},
            'Returned to IOS/DICOM alignment review',
            'Se ha vuelto a la revisión del alineamiento IOS–DICOM')
        return {'FINISHED'}

    def execute(self, context):
        global _STEP_GATE_ROLLBACK_ACTIVE
        props = getattr(context.scene, 'dsg_props', None)
        if props is None:
            return {'CANCELLED'}
        current = int(getattr(props, 'current_step', STEP_MODEL))
        if current <= STEP_MODEL:
            # This is only the first stage inside the guide module. Globally it
            # is clinical step 3, so its previous step is IOS–DICOM alignment.
            return self._return_to_alignment(context, props)

        # Back is explicit DSG restoration, not Blender Undo. It returns one
        # stage and restores the checkpoint saved before the current stage began.
        props.drawing_active = False
        props.irr_drawing_active = False
        unregister_contour_draw_handler()
        unregister_irr_draw_handler()
        _draw_callback_irrigation._current_chain = []
        try:
            if getattr(context, 'object', None) is not None and context.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)

        target = max(STEP_MODEL, current - 1)
        restored_geometry = _restore_workflow_checkpoint(context, target)
        if not restored_geometry:
            # Older scenes have no stored checkpoint yet. At minimum remove
            # downstream outputs instead of changing only the visible menu.
            if target == STEP_MODEL:
                for obj in list(bpy.data.objects):
                    try:
                        role = str(obj.get('dental_suite_dsg_role', '') or '')
                    except Exception:
                        role = ''
                    if role in {ROLE_IMPLANT, ROLE_SLEEVE, ROLE_FRAME, ROLE_GUIDE,
                                ROLE_IRRIGATION, ROLE_REINFORCEMENT, ROLE_MICROSCREW,
                                ROLE_MICROSCREW_VISUAL, ROLE_DRILL_CUTTER,
                                ROLE_DRILL_VISUAL, ROLE_ENGRAVE}:
                        safe_remove_object(obj)
                props.implant_obj = None
                props.parallel_master_implant = None
            _invalidate_workflow_after(context, target, reason='back_without_checkpoint')
            _clear_workflow_checkpoints_after(context.scene, target)

        _STEP_GATE_ROLLBACK_ACTIVE = True
        try:
            props.current_step = target
        finally:
            _STEP_GATE_ROLLBACK_ACTIVE = False

        actual = int(getattr(props, 'current_step', STEP_MODEL))
        if actual != target:
            _dsg_report(
                self, {'WARNING'},
                'The previous stage could not be restored',
                'No se pudo restaurar el paso anterior')
            return {'CANCELLED'}

        _set_workflow_gate(context.scene, {'ok': True})
        context.scene[WORKFLOW_LAST_VALID_STEP_KEY] = int(target)
        context.scene['DSG_next_step_gate_blocked'] = False
        try:
            del context.scene['DSG_next_step_gate_message']
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        _schedule_workflow_stage_restore(context.scene, target, delay=0.02)
        if restored_geometry:
            _dsg_report(
                self, {'INFO'},
                f'Restored previous geometry: {_step_text(props, target)}',
                f'Geometría anterior restaurada: {_step_text(props, target)}')
        else:
            _dsg_report(
                self, {'WARNING'},
                f'Previous stage opened and downstream outputs removed; this older scene had no geometric checkpoint yet: {_step_text(props, target)}',
                f'Paso anterior abierto y resultados posteriores retirados; esta escena antigua aún no tenía punto de restauración geométrico: {_step_text(props, target)}')
        return {'FINISHED'}


class DSG_OT_UseSelectedIOSModel(Operator):
    bl_idname = 'dsg.use_selected_ios_model'
    bl_label = 'Use Selected IOS Model'
    bl_description = 'Uses the selected aligned IOS as the master model and clears only geometry derived from the previous model'
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        props = getattr(getattr(context, 'scene', None), 'dsg_props', None)
        candidate = getattr(context, 'active_object', None)
        return bool(
            props is not None
            and int(getattr(props, 'current_step', STEP_MODEL)) == STEP_MODEL
            and _is_strict_ios_blockout_source(candidate)
        )

    def execute(self, context):
        props = getattr(context.scene, 'dsg_props', None)
        candidate = getattr(context, 'active_object', None)
        if props is None or not _is_strict_ios_blockout_source(candidate):
            _dsg_report(
                self, {'ERROR'},
                'Select a valid aligned IOS mesh first',
                'Selecciona primero una malla IOS alineada válida')
            return {'CANCELLED'}

        previous = getattr(props, 'model_obj', None)
        if previous == candidate:
            _isolate_ios_for_guide(context, candidate)
            set_active(context, candidate)
            _dsg_report(self, {'INFO'}, 'This IOS is already the active model', 'Este IOS ya es el modelo activo')
            return {'FINISHED'}

        _clear_guide_outputs_for_model_change(context, keep_model=candidate)
        props.model_obj = register_dsg_object(candidate, ROLE_MODEL, candidate.name)
        context.scene[SUITE_STAGE_KEY] = 'DSG'
        context.scene[GUIDE_FLOW_ORDER_KEY] = GUIDE_FLOW_ORDER_MODEL_IMPLANT
        context.scene[WORKFLOW_LAST_VALID_STEP_KEY] = int(STEP_MODEL)
        _isolate_ios_for_guide(context, candidate)
        set_active(context, candidate)
        _schedule_workflow_stage_restore(context.scene, STEP_MODEL, delay=0.02)
        _dsg_report(
            self, {'INFO'},
            f'Master IOS changed to {candidate.name}; dependent guide geometry was cleared',
            f'Modelo IOS cambiado a {candidate.name}; se eliminó solo la geometría dependiente')
        return {'FINISHED'}


class DSG_OT_PrepareAlignedModel(Operator):
    bl_idname = "dsg.prepare_aligned_model"
    bl_label = "Choose Insertion Axis from View"
    bl_description = "Captures the exact current 3D view and calculates the v7-style parallel-ray blockout"
    bl_options = {'REGISTER'}

    def execute(self, context):
        if not _require_workflow_stage(
                self, context, STEP_IMPLANT,
                action_en='Cannot prepare the insertion axis',
                action_es='No se puede preparar el eje de inserción'):
            return {'CANCELLED'}
        props = context.scene.dsg_props
        props.blockout_capture_view_on_generate = True
        entry_step = int(getattr(props, 'current_step', STEP_MODEL))
        requested_obj = props.model_obj if _valid_obj(getattr(props, 'model_obj', None)) else None
        try:
            obj = _resolve_blockout_source_model(context, requested_obj)
        except Exception:
            obj = None
        if not _valid_obj(obj):
            _dsg_report(self, {'ERROR'}, 'No aligned IOS was found. Complete Dental Alignment first.', 'No se encontró un IOS alineado. Completa primero Dental Alignment.')
            return {'CANCELLED'}
        if not context.area or context.area.type != 'VIEW_3D':
            _dsg_report(self, {'ERROR'}, 'Run this from a 3D View', 'Ejecuta esta acción desde una Vista 3D')
            return {'CANCELLED'}

        _quiesce_blockout_boolean_modifiers()
        props.model_obj = register_dsg_object(obj, ROLE_MODEL, obj.name)
        _isolate_ios_for_guide(context, obj)
        _hide_ios_antagonists_for_insertion_axis(context, obj)
        _show_simple_active_cbct_jaw(context, obj)
        set_active(context, obj)
        try:
            _empty, axis, _target, _surface_hit = capture_insertion_view_reference(context, obj)
        except Exception as exc:
            _dsg_report(self, {'ERROR'}, f'Could not capture the insertion view: {exc}', f'No se pudo capturar la vista de inserción: {exc}')
            return {'CANCELLED'}

        context.scene[SUITE_STAGE_KEY] = 'DSG'
        if GUIDE_HOME_SCENE_KEY in context.scene:
            del context.scene[GUIDE_HOME_SCENE_KEY]
        _remove_retention_previews(remove_blockout=False)
        _clear_retention_geometry_cache()
        _remove_retention_boundary()
        _set_blockout_ui_busy(context, True, 'Calculando blockout por rayos…')
        try:
            blockout = _generate_view_raycast_blockout_transaction(
                context, props, props.model_obj, axis)
        except Exception as exc:
            _dsg_report(self, {'ERROR'}, f'Could not generate the blockout: {exc}', f'No se pudo generar el modelo retentivo: {exc}')
            return {'CANCELLED'}
        finally:
            _set_blockout_ui_busy(context, False)

        props.current_step = STEP_IMPLANT if entry_step >= STEP_IMPLANT else STEP_MODEL
        _dsg_report(self, {'INFO'}, f'Insertion view captured; raycast blockout generated: {props.blockout_last_stats}', f'Vista de inserción capturada; modelo retentivo por rayos generado: {props.blockout_last_stats}')
        return {'FINISHED'}


class DSG_OT_ConfirmModel(Operator):
    bl_idname = "dsg.confirm_model"
    bl_label  = "Confirm Model"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if core.reject_external_agent_for_user_gate(self, action=self.bl_idname):
            return {'CANCELLED'}
        props = context.scene.dsg_props
        obj = _find_aligned_ios(context)
        if not _valid_obj(obj):
            _dsg_report(self, {'ERROR'}, "No aligned intraoral scan was found", "No se encontró un escaneado intraoral alineado")
            return {'CANCELLED'}
        props.model_obj = register_dsg_object(obj, ROLE_MODEL, obj.name)
        context.scene[SUITE_STAGE_KEY] = 'DSG'
        props.current_step = STEP_AXIS
        _isolate_ios_for_guide(context, obj)
        _hide_ios_antagonists_for_insertion_axis(context, obj)
        _show_simple_active_cbct_jaw(context, obj)
        set_active(context, obj)
        _dsg_report(self, {'INFO'}, f"Model: {obj.name}", f"Modelo: {obj.name}")
        return {'FINISHED'}


class DSG_OT_CaptureAxis(Operator):
    bl_idname = "dsg.capture_axis"
    bl_label  = "Capture Axis from View"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        # Capture the current view exactly, matching the proven v7.0.47 flow.
        area = context.area
        if not area or area.type != 'VIEW_3D':
            _dsg_report(self, {'ERROR'}, "Run this from a 3D View", "Ejecuta desde una Vista 3D")
            return {'CANCELLED'}
        props = context.scene.dsg_props
        model = props.model_obj if _valid_obj(getattr(props, 'model_obj', None)) else _find_aligned_ios(context)
        if not _valid_obj(model):
            _dsg_report(self, {'ERROR'}, "No aligned IOS was found", "No se encontró un IOS alineado")
            return {'CANCELLED'}
        _hide_ios_antagonists_for_insertion_axis(context, model)
        _show_simple_active_cbct_jaw(context, model)
        try:
            _empty, _axis, _target, surface_hit = capture_insertion_view_reference(
                context, model)
        except Exception as exc:
            _dsg_report(
                self, {'ERROR'},
                f"Could not capture the insertion view: {exc}",
                f"No se pudo capturar el punto de vista de inserción: {exc}")
            return {'CANCELLED'}
        if surface_hit:
            _dsg_report(
                self, {'INFO'},
                "Insertion direction and panned surface point captured",
                "Dirección de inserción y punto paneado sobre el modelo capturados")
        else:
            _dsg_report(
                self, {'INFO'},
                "Insertion direction and viewport pivot captured",
                "Dirección de inserción y pivote de la vista capturados")
        return {'FINISHED'}


class DSG_OT_SelectAxis(Operator):
    bl_idname = "dsg.select_axis"
    bl_label  = "Select Axis"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        set_active(context, ensure_axis_empty(context))
        _dsg_report(self, {'INFO'}, "R = rotate | G = move", "R = rotar | G = mover")
        return {'FINISHED'}


class DSG_OT_ConfirmAxis(Operator):
    bl_idname = "dsg.confirm_axis"
    bl_label  = "Confirm Axis"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if core.reject_external_agent_for_user_gate(self, action=self.bl_idname):
            return {'CANCELLED'}
        if get_axis_empty() is None:
            _dsg_report(self, {'ERROR'}, "Capture the axis first", "Captura el eje primero")
            return {'CANCELLED'}
        context.scene.dsg_props.current_step = STEP_BLOCKOUT
        return {'FINISHED'}


class DSG_OT_SelectRetentionPreset(Operator):
    bl_idname = "dsg.select_retention_preset"
    bl_label = "Select Retention Profile"
    bl_description = "Recalculates the single visible blockout using the selected scientific profile"
    bl_options = {'REGISTER'}

    level: EnumProperty(
        items=(('LOW', 'Lower retention', ''), ('AUTO', 'Automatic', ''), ('HIGH', 'Greater retention', '')),
        default='AUTO')

    def execute(self, context):
        if not _require_workflow_stage(
                self, context, STEP_IMPLANT,
                action_en='Cannot change the retention profile',
                action_es='No se puede cambiar el perfil de retención'):
            return {'CANCELLED'}
        props = context.scene.dsg_props
        level = str(self.level or 'AUTO').upper()
        if level == 'MEDIUM':
            level = 'AUTO'
        if level not in RETENTION_LEVEL_ENGAGEMENT_MM:
            return {'CANCELLED'}
        props.retention_level = level
        model = props.model_obj if _valid_obj(getattr(props, 'model_obj', None)) else _find_aligned_ios(context)
        if not _valid_obj(model) or get_axis_empty() is None:
            _dsg_report(self, {'INFO'}, 'Profile selected; now choose the insertion axis from the view', 'Perfil seleccionado; ahora elige el eje de inserción desde la vista')
            return {'FINISHED'}
        result = bpy.ops.dsg.generate_blockout('EXEC_DEFAULT')
        if 'FINISHED' not in result:
            return {'CANCELLED'}
        labels = {
            'LOW': ('Lower retention', 'Menor retención'),
            'AUTO': ('Automatic', 'Automático'),
            'HIGH': ('Greater retention', 'Mayor retención'),
        }
        en, es = labels[level]
        _dsg_report(self, {'INFO'}, f'{en} profile applied', f'Perfil {es.lower()} aplicado')
        return {'FINISHED'}



def _set_blockout_ui_busy(context, busy, status=""):
    """Show immediate visual feedback while the synchronous geometry stage runs."""
    try:
        context.scene['DSG_blockout_runtime_status'] = str(status if busy else '')
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    try:
        if context.window is not None:
            context.window.cursor_set('WAIT' if busy else 'DEFAULT')
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    try:
        if context.area is not None:
            context.area.tag_redraw()
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)


def _blockout_stats_summary(blockout):
    if not _valid_obj(blockout):
        return ''
    moved = int(blockout.get('DSG_vertices_moved', 0))
    total = int(blockout.get('DSG_vertices_total', 0))
    mean_move = float(blockout.get('DSG_mean_move_mm', 0.0))
    max_move = float(blockout.get('DSG_max_move_mm', 0.0))
    no_hit = int(blockout.get('DSG_rays_without_hit', 0))
    too_near = int(blockout.get('DSG_hits_too_near', 0))
    too_far = int(blockout.get('DSG_hits_too_far', 0))
    elapsed = float(blockout.get('DSG_elapsed_seconds', 0.0))
    return (
        f'Movidos {moved}/{total} · media {mean_move:.3f} mm · '
        f'máx. {max_move:.3f} mm · sin impacto {no_hit} · '
        f'cercanos {too_near} · lejanos {too_far} · {elapsed:.2f} s')


def _blockout_percentile(values, percentile):
    """Small dependency-free percentile helper for blockout diagnostics."""
    if not values:
        return 0.0
    ordered = sorted(float(value) for value in values)
    position = max(0.0, min(100.0, float(percentile))) * (len(ordered) - 1) / 100.0
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return float(ordered[lower])
    fraction = position - lower
    return float(ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction)


def _validate_blockout_seating(context, source_obj, blockout_obj):
    """Audit a view-raycast blockout before it can become a cutter.

    A surgical guide cannot be certified by software alone.  This check is
    narrower and useful: it proves that DSG's generated candidate still matches
    the evaluated IOS topology, has only axial displacement, and has no sampled
    residual axial lock materially deeper than the configured blockout relief.
    The retained report is part of the scene so a later operator can audit what
    was checked instead of relying on a transient console message.
    """
    report = {
        'status': 'FAILED', 'reason': '', 'sampled_vertices': 0,
        'residual_hits': 0, 'lateral_excess_vertices': 0,
        'p90_residual_mm': 0.0, 'max_residual_mm': 0.0,
        'max_lateral_mm': 0.0, 'relief_mm': 0.0,
    }
    if not _valid_obj(source_obj) or not _valid_obj(blockout_obj):
        report['reason'] = 'source or blockout object is unavailable'
        return report
    if source_obj.type != 'MESH' or blockout_obj.type != 'MESH':
        report['reason'] = 'source or blockout is not a mesh'
        return report

    axis_values = blockout_obj.get(BLOCKOUT_AXIS_WORLD_KEY, blockout_obj.get('DSG_axis'))
    try:
        axis = Vector(axis_values)
    except Exception:
        axis = Vector((0.0, 0.0, 0.0))
    if axis.length <= 1.0e-10:
        report['reason'] = 'insertion axis is unavailable'
        return report
    axis.normalize()

    evaluated = None
    evaluated_mesh = None
    bm = None
    try:
        evaluated, evaluated_mesh = _evaluated_mesh_for_blockout(context, source_obj)
        if (len(evaluated_mesh.vertices) != len(blockout_obj.data.vertices)
                or len(evaluated_mesh.polygons) != len(blockout_obj.data.polygons)):
            report['reason'] = 'IOS and blockout topology do not match'
            return report

        source_world = [evaluated.matrix_world @ vertex.co
                        for vertex in evaluated_mesh.vertices]
        blockout_world = [blockout_obj.matrix_world @ vertex.co
                          for vertex in blockout_obj.data.vertices]
        vertex_count = len(blockout_world)
        if not vertex_count:
            report['reason'] = 'blockout has no vertices'
            return report

        relief_mm = max(0.0, float(blockout_obj.get('DSG_relief_mm', 0.0)))
        report['relief_mm'] = relief_mm
        step = max(1, int(math.ceil(vertex_count / float(BLOCKOUT_SEATING_SAMPLE_LIMIT))))
        sampled_indices = range(0, vertex_count, step)
        lateral_limit = float(BLOCKOUT_SEATING_LATERAL_LIMIT_MM)
        laterals = []
        lateral_excess = 0
        for index in sampled_indices:
            delta = blockout_world[index] - source_world[index]
            axial = delta.dot(axis)
            lateral = (delta - axis * axial).length
            laterals.append(float(lateral))
            if lateral > lateral_limit:
                lateral_excess += 1
        report['sampled_vertices'] = len(laterals)
        report['lateral_excess_vertices'] = int(lateral_excess)
        report['max_lateral_mm'] = float(max(laterals) if laterals else 0.0)
        if lateral_excess:
            report['reason'] = 'candidate contains non-axial displacement'
            return report

        bm = bmesh.new()
        bm.from_mesh(blockout_obj.data)
        bm.transform(blockout_obj.matrix_world)
        bm.verts.ensure_lookup_table()
        tree = BVHTree.FromBMesh(bm)
        if tree is None:
            report['reason'] = 'could not build candidate BVH'
            return report

        min_hit = max(float(BLOCKOUT_RAY_OFFSET_MM),
                      float(blockout_obj.get('DSG_min_hit_mm', BLOCKOUT_MIN_HIT_DEFAULT_MM)))
        residuals = []
        for index in range(0, len(bm.verts), step):
            vertex = bm.verts[index]
            origin = vertex.co + axis * float(BLOCKOUT_RAY_OFFSET_MM)
            hit_loc, _normal, _face_index, _distance = tree.ray_cast(origin, axis)
            if hit_loc is None:
                continue
            residual = float((hit_loc - vertex.co).dot(axis))
            if residual > min_hit:
                residuals.append(residual)

        report['residual_hits'] = int(len(residuals))
        report['p90_residual_mm'] = _blockout_percentile(residuals, 90.0)
        report['max_residual_mm'] = float(max(residuals) if residuals else 0.0)
        p90_limit = relief_mm + float(BLOCKOUT_SEATING_RESIDUAL_TOLERANCE_MM)
        max_limit = p90_limit + float(BLOCKOUT_SEATING_MAX_RESIDUAL_EXTRA_MM)
        report['p90_limit_mm'] = p90_limit
        report['max_limit_mm'] = max_limit

        if report['p90_residual_mm'] > p90_limit or report['max_residual_mm'] > max_limit:
            report['status'] = 'REVIEW'
            report['reason'] = 'residual axial obstruction requires a different insertion view or local relief review'
        else:
            report['status'] = 'PASSED'
        return report
    except Exception as exc:
        report['reason'] = str(exc)
        return report
    finally:
        if bm is not None:
            bm.free()
        if evaluated is not None and evaluated_mesh is not None:
            try:
                evaluated.to_mesh_clear()
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)


def _store_blockout_seating_report(props, blockout, report):
    """Persist a concise audit result on both the candidate and scene props."""
    status = str(report.get('status', 'FAILED')).upper()
    summary = (
        f"{status} · p90 {float(report.get('p90_residual_mm', 0.0)):.3f} mm · "
        f"máx. {float(report.get('max_residual_mm', 0.0)):.3f} mm · "
        f"muestra {int(report.get('sampled_vertices', 0))}")
    try:
        props.blockout_seating_summary = summary
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    if not _valid_obj(blockout):
        return
    blockout['DSG_seating_validation_status'] = status
    blockout['DSG_seating_validation_summary'] = summary
    blockout['DSG_seating_validation_reason'] = str(report.get('reason', ''))
    blockout['DSG_seating_validation_version'] = 'V1_VIEW_PARALLEL_AUDIT'
    for key in (
            'sampled_vertices', 'residual_hits', 'lateral_excess_vertices',
            'p90_residual_mm', 'max_residual_mm', 'max_lateral_mm',
            'p90_limit_mm', 'max_limit_mm', 'relief_mm'):
        try:
            blockout['DSG_seating_' + key] = report[key]
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)


def _generate_view_raycast_blockout_transaction(context, props, model, axis):
    """Build a candidate first and replace the valid blockout only after success."""
    safe_remove_by_name(BLOCKOUT_CANDIDATE_NAME)
    candidate = None
    old_blockout = bpy.data.objects.get(BLOCKOUT_NAME)
    old_combined = bpy.data.objects.get(COMBINED_NAME)
    backup_name = None
    backup_mesh_name = None
    try:
        candidate = build_blockout_bvh(
            context,
            model,
            axis,
            relief_mm=float(getattr(props, 'blockout_relief', 0.10)),
            min_hit_mm=float(getattr(props, 'blockout_min_hit_distance', BLOCKOUT_MIN_HIT_DEFAULT_MM)),
            max_hit_mm=float(getattr(props, 'blockout_max_hit_distance', BLOCKOUT_MAX_HIT_DEFAULT_MM)),
            output_name=BLOCKOUT_CANDIDATE_NAME)
        if not _valid_obj(candidate):
            raise RuntimeError('No se creó el candidato de blockout')
        if len(candidate.data.vertices) <= 0 or len(candidate.data.polygons) <= 0:
            raise RuntimeError('El candidato de blockout no contiene geometría')

        candidate['DSG_blockout_method'] = 'VIEW_PARALLEL_RAYCAST_V7'
        candidate['DSG_retention_analysis_ready'] = True
        candidate['DSG_blockout_final_quality'] = True
        candidate['DSG_source_ios_name'] = str(model.name)
        candidate['DSG_contains_blockout'] = True
        candidate['DSG_contains_original_envelope'] = False
        candidate['DSG_retention_level'] = 'CUSTOM_AXIAL_RESIDUAL'
        candidate['DSG_retention_engagement_mm'] = float(getattr(props, 'blockout_relief', 0.10))
        candidate['DSG_passive_clearance_mm'] = 0.0
        candidate['DSG_insertion_validation_status'] = 'RAYCAST_READY'
        candidate[BLOCKOUT_AXIS_WORLD_KEY] = [float(axis.x), float(axis.y), float(axis.z)]
        candidate[BLOCKOUT_AXIS_SOURCE_KEY] = 'CURRENT_VIEW_V7_RAYCAST'
        candidate[BLOCKOUT_AXIS_CONVENTION_KEY] = BLOCKOUT_AXIS_CONVENTION_V7

        if _valid_obj(old_blockout):
            backup_name = old_blockout.name
            backup_mesh_name = old_blockout.data.name
            old_blockout.name = BLOCKOUT_NAME + '_Previous'
            old_blockout.data.name = BLOCKOUT_NAME + '_PreviousMesh'

        try:
            candidate.name = BLOCKOUT_NAME
            candidate.data.name = BLOCKOUT_NAME + '_Mesh'
            register_dsg_object(candidate, ROLE_BLOCKOUT, BLOCKOUT_NAME)
            _set_obj_hidden(candidate, False, selectable_when_visible=True)
        except Exception:
            if _valid_obj(candidate):
                safe_remove_object(candidate)
            if _valid_obj(old_blockout):
                old_blockout.name = backup_name or BLOCKOUT_NAME
                old_blockout.data.name = backup_mesh_name or (BLOCKOUT_NAME + '_Mesh')
                register_dsg_object(old_blockout, ROLE_BLOCKOUT, BLOCKOUT_NAME)
            raise

        if _valid_obj(old_combined):
            safe_remove_object(old_combined)
        if _valid_obj(old_blockout):
            safe_remove_object(old_blockout)
        safe_remove_by_name(BLOCKOUT_VISUAL_NAME)

        props.blockout_last_stats = _blockout_stats_summary(candidate)
        seating_report = _validate_blockout_seating(context, model, candidate)
        _store_blockout_seating_report(props, candidate, seating_report)
        # The teal overlay makes the added surface inspectable before it can be
        # accepted as the guide's fitting reference. It is display-only and is
        # explicitly excluded from Boolean/export operations.
        try:
            visual = _ensure_blockout_zone_visual(
                context, model, candidate, force_rebuild=True)
            if _valid_obj(visual):
                _set_obj_hidden(visual, False, selectable_when_visible=False)
        except Exception as exc:
            print(f'[DSG] Could not create blockout review overlay: {exc}')
        return candidate
    except Exception:
        if _valid_obj(candidate):
            safe_remove_object(candidate)
        safe_remove_by_name(BLOCKOUT_CANDIDATE_NAME)
        if _valid_obj(old_blockout) and old_blockout.name != BLOCKOUT_NAME:
            old_blockout.name = backup_name or BLOCKOUT_NAME
            old_blockout.data.name = backup_mesh_name or (BLOCKOUT_NAME + '_Mesh')
            register_dsg_object(old_blockout, ROLE_BLOCKOUT, BLOCKOUT_NAME)
        raise


def build_blockout_simple_fast(context, source_obj, axis_vec,
                               passive_clearance_mm=None,
                               retention_engagement_mm=None,
                               retention_level='AUTO', final_quality=False,
                               **_unused):
    """Compatibility entry point: the only active blockout is the view-parallel BVH raycast."""
    props = context.scene.dsg_props
    return _generate_view_raycast_blockout_transaction(
        context, props, _resolve_blockout_source_model(context, source_obj),
        Vector(axis_vec).normalized())

class DSG_OT_GenerateBlockout(Operator):
    bl_idname = "dsg.generate_blockout"
    bl_label = "Generate Blockout"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if not _require_workflow_stage(
                self, context, STEP_IMPLANT,
                action_en='Cannot generate the blockout',
                action_es='No se puede generar el blockout'):
            return {'CANCELLED'}
        props = context.scene.dsg_props
        requested_model = props.model_obj if _valid_obj(getattr(props, 'model_obj', None)) else None
        try:
            model = _resolve_blockout_source_model(context, requested_model)
        except Exception as exc:
            _dsg_report(self, {'ERROR'}, f'Confirm the aligned IOS first: {exc}', f'Confirma primero el IOS alineado: {exc}')
            return {'CANCELLED'}
        if not _valid_obj(model):
            _dsg_report(self, {'ERROR'}, 'Confirm the aligned IOS first', 'Confirma primero el IOS alineado')
            return {'CANCELLED'}
        if not context.area or context.area.type != 'VIEW_3D':
            _dsg_report(self, {'ERROR'}, 'Run this from a 3D View', 'Ejecuta esta acción desde una Vista 3D')
            return {'CANCELLED'}

        try:
            if bool(getattr(props, 'blockout_capture_view_on_generate', True)):
                _empty, axis, _target, _surface_hit = capture_insertion_view_reference(context, model)
            else:
                axis = _read_stored_world_axis(model, BLOCKOUT_AXIS_WORLD_KEY)
                if axis is None:
                    axis = _read_stored_world_axis(context.scene, BLOCKOUT_AXIS_WORLD_KEY)
                if axis is None:
                    axis = get_insertion_axis()
            _quiesce_blockout_boolean_modifiers()
            _remove_retention_previews(remove_blockout=False)
            _clear_retention_geometry_cache()
            _remove_retention_boundary()
            _set_blockout_ui_busy(context, True, 'Actualizando blockout por rayos…')
            blockout = _generate_view_raycast_blockout_transaction(
                context, props, model, axis)
            _set_obj_hidden(blockout, False, selectable_when_visible=True)
        except Exception as exc:
            _dsg_report(self, {'ERROR'}, f'Blockout error: {exc}', f'No se pudo generar el modelo retentivo: {exc}')
            return {'CANCELLED'}
        finally:
            _set_blockout_ui_busy(context, False)

        seating = str(blockout.get('DSG_seating_validation_status', 'FAILED')).upper()
        if seating == 'PASSED':
            _dsg_report(
                self, {'INFO'},
                f'Blockout generated and seating audit passed: {props.blockout_last_stats}',
                f'Modelo retentivo generado y auditoría de asiento superada: {props.blockout_last_stats}')
        elif seating == 'REVIEW':
            _dsg_report(
                self, {'WARNING'},
                'Blockout generated, but review the teal relief surface and choose a different insertion view if needed',
                'Modelo retentivo generado, pero revisa la superficie turquesa de alivio y elige otra vista de inserción si es necesario')
        else:
            _dsg_report(
                self, {'ERROR'},
                'Blockout was generated but its seating audit could not be completed',
                'Se generó el modelo retentivo, pero no se pudo completar su auditoría de asiento')
        return {'FINISHED'}


class DSG_OT_AnalyzeRetention(Operator):
    bl_idname = "dsg.analyze_retention"
    bl_label = "Analyze Coronary Perimeter"
    bl_description = "Compatibility action: recalculates the single scientific whole-arch blockout"
    bl_options = {'REGISTER'}

    def execute(self, context):
        return bpy.ops.dsg.generate_blockout('EXEC_DEFAULT')


class DSG_OT_ValidateBlockoutSeating(Operator):
    """Repeat the non-destructive quality audit after visual review."""
    bl_idname = 'dsg.validate_blockout_seating'
    bl_label = 'Validate Guide Seating'
    bl_description = 'Checks residual axial locks and verifies that the fitting envelope remains axial'
    bl_options = {'REGISTER'}

    def execute(self, context):
        props = context.scene.dsg_props
        requested = props.model_obj if _valid_obj(getattr(props, 'model_obj', None)) else None
        try:
            model = _resolve_blockout_source_model(context, requested)
        except Exception:
            model = None
        blockout = bpy.data.objects.get(BLOCKOUT_NAME)
        if not _valid_obj(model) or not _valid_obj(blockout):
            _dsg_report(self, {'ERROR'}, 'Generate a blockout before validating seating', 'Genera el modelo retentivo antes de validar el asiento')
            return {'CANCELLED'}
        report = _validate_blockout_seating(context, model, blockout)
        _store_blockout_seating_report(props, blockout, report)
        status = str(report.get('status', 'FAILED')).upper()
        if status == 'PASSED':
            _dsg_report(
                self, {'INFO'},
                'Algorithmic seating audit passed. Perform the clinical fit review before surgery.',
                'Auditoría algorítmica de asiento superada. Realiza la revisión clínica del ajuste antes de la cirugía.')
            return {'FINISHED'}
        if status == 'REVIEW':
            _dsg_report(
                self, {'WARNING'},
                'Residual axial lock remains. Change the insertion view or review local relief before confirming.',
                'Persisten retenciones axiales. Cambia la vista de inserción o revisa el alivio local antes de confirmar.')
            return {'CANCELLED'}
        _dsg_report(
            self, {'ERROR'},
            f"Seating audit failed: {report.get('reason', 'unknown error')}",
            f"Falló la auditoría de asiento: {report.get('reason', 'error desconocido')}")
        return {'CANCELLED'}


class DSG_OT_ApplySelectedBlockoutRelief(Operator):
    """Add conservative, user-selected relief without ever editing the IOS."""
    bl_idname = 'dsg.apply_selected_blockout_relief'
    bl_label = 'Apply Selected Local Relief'
    bl_description = 'Advances selected blockout vertices along the insertion axis, then repeats the seating audit'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        blockout = bpy.data.objects.get(BLOCKOUT_NAME)
        return bool(
            _valid_obj(blockout)
            and context.mode == 'EDIT_MESH'
            and context.edit_object == blockout)

    def execute(self, context):
        props = context.scene.dsg_props
        blockout = bpy.data.objects.get(BLOCKOUT_NAME)
        if not _valid_obj(blockout) or blockout.type != 'MESH':
            _dsg_report(self, {'ERROR'}, 'Generate the blockout first', 'Genera primero el modelo retentivo')
            return {'CANCELLED'}
        if context.mode != 'EDIT_MESH' or context.edit_object != blockout:
            _dsg_report(
                self, {'ERROR'},
                'Select the teal blockout vertices in Edit Mode first',
                'Selecciona primero los vértices turquesa del blockout en Modo Edición')
            return {'CANCELLED'}
        axis_values = blockout.get(BLOCKOUT_AXIS_WORLD_KEY, blockout.get('DSG_axis'))
        try:
            axis_world = Vector(axis_values)
        except Exception:
            axis_world = Vector((0.0, 0.0, 0.0))
        if axis_world.length <= 1.0e-10:
            _dsg_report(self, {'ERROR'}, 'Insertion axis is unavailable', 'El eje de inserción no está disponible')
            return {'CANCELLED'}
        axis_world.normalize()
        try:
            axis_local = blockout.matrix_world.inverted().to_3x3() @ axis_world
        except Exception:
            axis_local = axis_world.copy()
        if axis_local.length <= 1.0e-10:
            _dsg_report(self, {'ERROR'}, 'Could not transform the insertion axis', 'No se pudo transformar el eje de inserción')
            return {'CANCELLED'}
        axis_local.normalize()

        bm = bmesh.from_edit_mesh(blockout.data)
        bm.verts.ensure_lookup_table()
        selected = [vertex for vertex in bm.verts if vertex.select]
        if not selected:
            _dsg_report(self, {'ERROR'}, 'Select at least one blockout vertex', 'Selecciona al menos un vértice del blockout')
            return {'CANCELLED'}
        amount = float(getattr(props, 'blockout_local_relief_mm', 0.06))
        # A one-ring half-strength transition avoids a sharp, printable step at
        # the edge of a clinician-selected contact relief zone.  The correction
        # remains strictly in the insertion direction.
        weights = {int(vertex.index): 1.0 for vertex in selected}
        for vertex in selected:
            for edge in vertex.link_edges:
                neighbour = edge.other_vert(vertex)
                if not neighbour.select:
                    weights[int(neighbour.index)] = max(weights.get(int(neighbour.index), 0.0), 0.5)
        for index, weight in weights.items():
            bm.verts[index].co += axis_local * amount * float(weight)
        bmesh.update_edit_mesh(blockout.data, loop_triangles=False, destructive=False)
        blockout['DSG_local_relief_last_mm'] = amount
        blockout['DSG_local_relief_last_vertices'] = int(len(weights))
        blockout['DSG_local_relief_edits'] = int(blockout.get('DSG_local_relief_edits', 0)) + 1

        requested = props.model_obj if _valid_obj(getattr(props, 'model_obj', None)) else None
        try:
            model = _resolve_blockout_source_model(context, requested)
        except Exception:
            model = None
        if _valid_obj(model):
            report = _validate_blockout_seating(context, model, blockout)
            _store_blockout_seating_report(props, blockout, report)
            try:
                visual = _ensure_blockout_zone_visual(context, model, blockout, force_rebuild=True)
                if _valid_obj(visual):
                    _set_obj_hidden(visual, False, selectable_when_visible=False)
            except Exception as exc:
                print(f'[DSG] Could not refresh blockout review overlay: {exc}')
        _dsg_report(
            self, {'INFO'},
            f'Local axial relief applied to {len(weights)} vertices; seating was rechecked',
            f'Alivio axial local aplicado a {len(weights)} vértices; el asiento se ha vuelto a comprobar')
        return {'FINISHED'}


class DSG_OT_AutoPrepareRetention(Operator):
    bl_idname = "dsg.auto_prepare_retention"
    bl_label = "Prepare Model"
    bl_description = "Captures the view-defined insertion axis and calculates the automatic coronary fit"
    bl_options = {'REGISTER'}

    force_rebuild: BoolProperty(default=False, options={'HIDDEN'})

    def execute(self, context):
        return bpy.ops.dsg.prepare_aligned_model('EXEC_DEFAULT')


class DSG_OT_ConfirmBlockout(Operator):
    bl_idname = "dsg.confirm_blockout"
    bl_label = "Confirm Blockout"
    bl_options = {'REGISTER', 'UNDO'}

    manual_override: BoolProperty(
        default=False,
        options={'HIDDEN'},
        description='Continue only after an explicit manual seating review')

    def execute(self, context):
        if not _require_workflow_stage(
                self, context, STEP_IMPLANT,
                action_en='Cannot confirm the retentive model',
                action_es='No se puede confirmar el modelo retentivo'):
            return {'CANCELLED'}
        props = context.scene.dsg_props
        requested = props.model_obj if _valid_obj(getattr(props, 'model_obj', None)) else None
        try:
            model = _resolve_blockout_source_model(context, requested)
        except Exception:
            model = None
        blockout = bpy.data.objects.get(BLOCKOUT_NAME)
        if not _valid_obj(model) or not _valid_obj(blockout):
            _dsg_report(self, {'ERROR'}, 'Generate the blockout first', 'Genera primero el modelo retentivo')
            return {'CANCELLED'}

        # Old scenes do not have the persisted audit keys. Recreate them once
        # rather than making an existing patient file impossible to continue.
        seating_status = str(blockout.get('DSG_seating_validation_status', '')).upper()
        if not seating_status:
            _store_blockout_seating_report(
                props, blockout, _validate_blockout_seating(context, model, blockout))
            seating_status = str(blockout.get('DSG_seating_validation_status', '')).upper()
        if seating_status != 'PASSED' and not self.manual_override:
            reason = str(blockout.get('DSG_seating_validation_reason', '')).strip()
            suffix_en = f' ({reason})' if reason else ''
            suffix_es = f' ({reason})' if reason else ''
            _dsg_report(
                self, {'WARNING'},
                'Review guide seating before confirming: choose the insertion view again or adjust the local relief' + suffix_en,
                'Revisa el asiento de la guía antes de confirmar: vuelve a elegir la vista de inserción o ajusta el alivio local' + suffix_es)
            return {'CANCELLED'}

        # An automated failure is never silently represented as a pass.  This
        # supports an explicit, auditable recovery for clinician-reviewed
        # scans whose topology the audit cannot assess reliably.
        manual_override_used = seating_status != 'PASSED'

        old_combined = bpy.data.objects.get(COMBINED_NAME)
        safe_remove_by_name(COMBINED_CANDIDATE_NAME)
        combined = None
        _set_blockout_ui_busy(context, True, 'Confirmando modelo retentivo…')
        try:
            combined = build_joined_passive_model(
                context, model, blockout,
                output_name=COMBINED_CANDIDATE_NAME)
            if not _valid_obj(combined):
                raise RuntimeError('No se pudo construir el modelo combinado')
            if len(combined.data.vertices) <= 0 or len(combined.data.polygons) <= 0:
                raise RuntimeError('El modelo combinado quedó vacío')

            previous_name = None
            previous_mesh_name = None
            if _valid_obj(old_combined):
                previous_name = old_combined.name
                previous_mesh_name = old_combined.data.name
                old_combined.name = COMBINED_NAME + '_Previous'
                old_combined.data.name = COMBINED_NAME + '_PreviousMesh'
            try:
                combined.name = COMBINED_NAME
                combined.data.name = COMBINED_NAME + '_Mesh'
                register_dsg_object(combined, ROLE_PASSIVE, COMBINED_NAME)
            except Exception:
                if _valid_obj(combined):
                    safe_remove_object(combined)
                if _valid_obj(old_combined):
                    old_combined.name = previous_name or COMBINED_NAME
                    old_combined.data.name = previous_mesh_name or (COMBINED_NAME + '_Mesh')
                    register_dsg_object(old_combined, ROLE_PASSIVE, COMBINED_NAME)
                raise
            if _valid_obj(old_combined):
                safe_remove_object(old_combined)
        except Exception as exc:
            if _valid_obj(combined):
                safe_remove_object(combined)
            safe_remove_by_name(COMBINED_CANDIDATE_NAME)
            _dsg_report(self, {'ERROR'}, f'Could not confirm the blockout: {exc}', f'No se pudo confirmar el modelo retentivo: {exc}')
            return {'CANCELLED'}
        finally:
            _set_blockout_ui_busy(context, False)

        combined['DSG_retentive_model_confirmed'] = True
        combined['DSG_confirmation_state'] = (
            'CONFIRMED_MANUAL_SEATING_REVIEW' if manual_override_used else 'CONFIRMED')
        combined['DSG_confirmation_version'] = '9.2.46'
        combined['DSG_seating_validation_status'] = seating_status
        combined['DSG_seating_validation_summary'] = str(
            blockout.get('DSG_seating_validation_summary', ''))
        try:
            blockout_visual = _ensure_blockout_zone_visual(
                context, model, blockout, force_rebuild=True)
            if _valid_obj(blockout_visual):
                _set_obj_hidden(blockout_visual, True, selectable_when_visible=False)
        except Exception as exc:
            print(f'[DSG] Could not create blockout visual overlay: {exc}')
        combined['DSG_next_step_gate_passed'] = True
        combined['DSG_seating_manual_override'] = bool(manual_override_used)
        combined['DSG_seating_manual_override_note'] = (
            'Operator continued after explicit manual seating review.'
            if manual_override_used else '')
        combined['DSG_next_step_gate_requirement'] = 'V7_RAYCAST_CONFIRMED__FINAL_SOLIDIFICATION_AT_BOOLEAN'
        for key in (
                BLOCKOUT_AXIS_WORLD_KEY, BLOCKOUT_AXIS_SOURCE_KEY,
                BLOCKOUT_AXIS_CONVENTION_KEY, 'DSG_blockout_engine',
                'DSG_relief_mm', 'DSG_vertices_moved', 'DSG_vertices_total',
                'DSG_mean_move_mm', 'DSG_max_move_mm'):
            try:
                if key in blockout:
                    combined[key] = blockout[key]
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)

        passive_signature = _workflow_object_signature(combined)
        if _workflow_signature_changed(context.scene, WORKFLOW_PASSIVE_SIGNATURE_KEY, passive_signature):
            _invalidate_workflow_after(context, STEP_MODEL, reason='retentive_model_changed')
        _workflow_store_signature(context.scene, WORKFLOW_PASSIVE_SIGNATURE_KEY, passive_signature)

        _set_obj_hidden(model, True)
        _set_obj_hidden(blockout, True)
        try:
            blockout.hide_render = True
            blockout['DSG_confirmed'] = True
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        _set_obj_hidden(combined, False, selectable_when_visible=True)
        props.dct_object_making_cut = combined
        props.current_step = STEP_IMPLANT
        context.scene[GUIDE_FLOW_ORDER_KEY] = GUIDE_FLOW_ORDER_MODEL_IMPLANT
        _remove_retention_previews(remove_blockout=False)
        _clear_retention_geometry_cache()
        _remove_retention_boundary()
        if manual_override_used:
            _dsg_report(self, {'WARNING'}, 'Retentive model continued after manual seating review; verify physical fit before surgery', 'Modelo retentivo continuado tras revisión manual del asiento; verifica el ajuste físico antes de la cirugía')
        else:
            _dsg_report(self, {'INFO'}, 'View-raycast retentive model confirmed; final voxel solidification remains in the final Boolean step', 'Modelo retentivo por rayos confirmado; la solidificación voxel se mantiene en la booleana final')
        return {'FINISHED'}


class DSG_OT_ForceConfirmBlockout(Operator):
    """Explicit, auditable recovery path when the automated seating audit blocks."""
    bl_idname = 'dsg.force_confirm_blockout'
    bl_label = 'Continue After Manual Seating Review'
    bl_description = 'Confirms the current blockout while recording that automated seating validation was not passed'
    bl_options = {'REGISTER', 'UNDO'}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(
            self, event,
            title='Confirmar tras revisión manual',
            message='La auditoría automática no ha sido superada. Solo continúa si has revisado el asiento.',
            confirm_text='CONTINUAR')

    def execute(self, context):
        return bpy.ops.dsg.confirm_blockout('EXEC_DEFAULT', manual_override=True)


class DSG_OT_StartDrawing(Operator):
    bl_idname = "dsg.start_drawing"
    bl_label  = "Draw / Continue Outline"
    bl_description = "Place frame points while keeping Blender orbit, pan and zoom available"
    bl_options = {'REGISTER', 'UNDO'}

    @staticmethod
    def _is_view_navigation_event(event):
        """Let Blender's native viewport navigation run during point placement.

        A modal operator must pass not only the middle-mouse press but also the
        subsequent mouse-move/release events.  Passing only ``MIDDLEMOUSE`` made
        orbit start but prevented Shift+MMB panning because DSG swallowed the
        drag motion.  Trackpads, wheels, NDOF devices and emulated three-button
        navigation are handled here as well.
        """
        event_type = str(getattr(event, 'type', ''))
        if event_type in {
                'MIDDLEMOUSE', 'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE',
                'WHEELUPMOUSE', 'WHEELDOWNMOUSE',
                'WHEELINMOUSE', 'WHEELOUTMOUSE',
                'TRACKPADPAN', 'TRACKPADZOOM',
                'MOUSEROTATE', 'MOUSESMARTZOOM'}:
            return True
        if event_type.startswith('NDOF_'):
            return True
        # Blender's "Emulate 3 Button Mouse" uses Alt+LMB.  Do not interpret
        # that gesture as a new contour point.
        if event_type == 'LEFTMOUSE' and bool(getattr(event, 'alt', False)):
            return True
        return False

    def modal(self, context, event):
        if not lifecycle.is_active():
            return {'CANCELLED'}
        props = context.scene.dsg_props
        points_now = get_contour_curve_points()
        _draw_callback_contour._current_chain = points_now
        if context.area:
            context.area.tag_redraw()

        # Navigation must be evaluated before point placement.  Shift+MMB pans,
        # MMB orbits and Ctrl+MMB zooms without suspending the drawing session.
        if self._is_view_navigation_event(event):
            return {'PASS_THROUGH'}

        if event.type in {'RIGHTMOUSE', 'ESC'} and event.value == 'PRESS':
            props.drawing_active = False
            points = get_contour_curve_points()
            set_contour_curve_points(context, points, cyclic=len(points) >= 3)
            sync_legacy_contour_points(props, points)
            unregister_contour_draw_handler()
            _dsg_report(self, {'INFO'}, f"{len(points)} points in DSG_ContourCurve. Use Edit points to move them individually.", f"{len(points)} puntos en DSG_ContourCurve. Usa Editar puntos para moverlos individualmente.")
            return {'FINISHED'}

        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            target = choose_raycast_target(props)
            loc = do_raycast(context, event, target)
            if loc is None:
                _dsg_report(self, {'WARNING'}, "Click the passive model", "Haz clic sobre el modelo pasivo")
                return {'RUNNING_MODAL'}
            points = get_contour_curve_points()
            points.append(Vector(loc))
            set_contour_curve_points(context, points, cyclic=len(points) >= 3)
            sync_legacy_contour_points(props, points)
            _draw_callback_contour._current_chain = points
            return {'RUNNING_MODAL'}

        if event.type == 'Z' and event.ctrl and event.value == 'PRESS':
            points = get_contour_curve_points()
            if points:
                points.pop()
                set_contour_curve_points(context, points, cyclic=len(points) >= 3)
                sync_legacy_contour_points(props, points)
                _draw_callback_contour._current_chain = points
            return {'RUNNING_MODAL'}

        if event.type in {'NUMPAD_0','NUMPAD_1','NUMPAD_2','NUMPAD_3',
                          'NUMPAD_4','NUMPAD_5','NUMPAD_6','NUMPAD_7',
                          'NUMPAD_8','NUMPAD_9','HOME'}:
            return {'PASS_THROUGH'}
        return {'RUNNING_MODAL'}

    def invoke(self, context, event):
        if not _require_workflow_stage(
                self, context, STEP_CONTOUR,
                action_en='Cannot draw the outline',
                action_es='No se puede dibujar el contorno'):
            return {'CANCELLED'}
        activate_precision_orthographic(context)
        if not _valid_obj(get_confirmed_passive_model_obj()):
            props = context.scene.dsg_props
            props.current_step = STEP_IMPLANT
            _schedule_implant_planning_state_restore(
                context.scene, require_armed=False, delay=0.02)
            _dsg_report(
                self, {'ERROR'},
                'The retentive model was not confirmed. DSG returned to implant planning so it can be confirmed safely.',
                'El modelo retentivo no estaba confirmado. DSG ha vuelto a planificación de implantes para que puedas confirmarlo de forma segura.')
            return {'CANCELLED'}
        ensure_object_mode(context)
        props = context.scene.dsg_props
        if get_contour_curve() is None and len(props.contour_points) > 0:
            set_contour_curve_points(context, [Vector(item.co) for item in props.contour_points], cyclic=len(props.contour_points) >= 3)
        else:
            ensure_contour_curve(context)
        props.drawing_active = True
        _set_retention_boundary_visible(True)
        _draw_callback_contour._current_chain = get_contour_curve_points()
        register_contour_draw_handler()
        context.window_manager.modal_handler_add(self)
        _dsg_report(
            self, {'INFO'},
            "LMB = point | Shift+MMB = pan | MMB = orbit | wheel = zoom | Ctrl+Z = undo | RMB = finish",
            "LMB = punto | Shift+MMB = panear | MMB = rotar | rueda = zoom | Ctrl+Z = deshacer | RMB = terminar")
        return {'RUNNING_MODAL'}


class DSG_OT_ToggleContourPointEdit(Operator):
    bl_idname = "dsg.toggle_contour_point_edit"
    bl_label = "Edit Frame Points"
    bl_description = "Edit each frame point individually; select one point and move it with G"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.dsg_props
        obj = get_contour_curve()
        if not _valid_obj(obj) or not obj.data.splines:
            _dsg_report(self, {'ERROR'}, 'Mark the contour first', 'Marca primero el contorno')
            return {'CANCELLED'}

        editing = context.mode == 'EDIT_CURVE' and context.view_layer.objects.active == obj
        if editing:
            try:
                bpy.ops.object.mode_set(mode='OBJECT')
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
            points = get_contour_curve_points()
            sync_legacy_contour_points(props, points)
            _set_retention_boundary_visible(True)
            _dsg_report(self, {'INFO'}, 'Point editing finished', 'Edición de puntos terminada')
            return {'FINISHED'}

        ensure_object_mode(context)
        deselect_all_objects()
        obj.hide_select = False
        obj.select_set(True)
        context.view_layer.objects.active = obj
        try:
            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.curve.select_all(action='DESELECT')
        except Exception as exc:
            ensure_object_mode(context)
            _dsg_report(self, {'ERROR'}, f'Could not edit contour points: {exc}', f'No se pudieron editar los puntos: {exc}')
            return {'CANCELLED'}
        _set_retention_boundary_visible(True)
        _dsg_report(
            self, {'INFO'},
            'Select one point and press G to move it; use the panel button to finish.',
            'Selecciona un punto y pulsa G para moverlo; termina desde el botón del panel.')
        return {'FINISHED'}


class DSG_OT_ClearContour(Operator):
    bl_idname = "dsg.clear_contour"
    bl_label  = "Clear Outline"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.dsg_props
        clear_contour_curve()
        props.contour_points.clear()
        props.drawing_active = False
        unregister_contour_draw_handler()
        return {'FINISHED'}


class DSG_OT_ConfirmContour(Operator):
    bl_idname = "dsg.confirm_contour"
    bl_label  = "Confirm Outline"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if not _require_workflow_stage(
                self, context, STEP_CONTOUR,
                action_en='Cannot confirm the outline',
                action_es='No se puede confirmar el contorno'):
            return {'CANCELLED'}
        props = context.scene.dsg_props
        ensure_object_mode(context)
        points = get_contour_curve_points()
        if len(points) < 4 and len(props.contour_points) >= 4:
            points = [Vector(item.co) for item in props.contour_points]
            set_contour_curve_points(context, points, cyclic=True)
        if len(points) < 4:
            _dsg_report(self, {'ERROR'}, "At least 4 points are required in DSG_ContourCurve", "Necesitas al menos 4 puntos en DSG_ContourCurve")
            return {'CANCELLED'}
        sync_legacy_contour_points(props, points)
        contour_signature = _workflow_contour_signature(props)
        if _workflow_signature_changed(context.scene, WORKFLOW_CONTOUR_SIGNATURE_KEY, contour_signature):
            _invalidate_workflow_after(context, STEP_CONTOUR, reason='contour_changed')
        _workflow_store_signature(context.scene, WORKFLOW_CONTOUR_SIGNATURE_KEY, contour_signature)
        props.drawing_active = False
        unregister_contour_draw_handler()
        _set_retention_boundary_visible(False)
        context.scene['DSG_workflow_contour_confirmed'] = True
        context.scene['DSG_workflow_contour_point_count'] = int(len(points))
        props.current_step = STEP_FRAME
        context.scene[GUIDE_FLOW_ORDER_KEY] = GUIDE_FLOW_ORDER_MODEL_IMPLANT
        return {'FINISHED'}



class DSG_OT_CreateImplant(Operator):
    bl_idname = "dsg.create_implant"
    bl_label  = "Create Implant"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if not _require_workflow_stage(
                self, context, STEP_IMPLANT,
                action_en='Cannot create an implant',
                action_es='No se puede crear un implante'):
            return {'CANCELLED'}
        if core.clinical_route(context.scene) == core.ROUTE_IMMEDIATE and not _immediate_extraction_ready(context.scene):
            _dsg_report(
                self, {'ERROR'},
                'Prepare the reversible virtual extraction of the target FDI before creating the immediate implant',
                'Prepara la extracción virtual reversible del FDI objetivo antes de crear el implante inmediato')
            return {'CANCELLED'}
        props = context.scene.dsg_props
        activate_precision_orthographic(context)

        obj_name = get_next_implant_name()
        try:
            mesh = make_embedded_implant_mesh(
                obj_name + "_Mesh",
                props.implant_diameter,
                props.implant_length,
            )
            implant_source = 'embedded_stl'
        except Exception as exc:
            # Fallback defensivo: el flujo clínico no queda bloqueado si los datos
            # integrados fueran dañados al copiar o editar el archivo Python.
            print(f"[DSG] Could not create the embedded STL implant: {exc}")
            mesh = make_cylinder_mesh(
                obj_name + "_Mesh",
                props.implant_diameter * 0.5,
                props.implant_length,
                verts=32,
            )
            implant_source = 'cylinder_fallback'
        obj = bpy.data.objects.new(obj_name, mesh)
        link_object(context, obj)

        # El implante debe nacer a partir de la referencia clínica aprobada en
        # el paso de inserción, no desde los ejes globales ni desde la vista que
        # esté activa en este momento. ``DSG_Axis`` guarda dos datos distintos:
        #   - su +Z world es la trayectoria de inserción hacia apical;
        #   - su localización es el punto 3D centrado por el usuario al confirmar.
        #
        # La plantilla del implante tiene la plataforma en +Z local y el ápice en
        # -Z local. Por eso alineamos -Z local con la trayectoria de inserción.
        # A roadmap/FDI proposal uses a separate one-shot axis so implant
        # automation never overwrites DSG_Axis, which remains the approved guide
        # insertion/blockout reference used by later frame and engraving logic.
        axis_empty = get_pending_implant_axis_empty()
        axis_source = 'fdi_tooth_axis' if _valid_obj(axis_empty) else 'guide_insertion_axis'
        if not _valid_obj(axis_empty):
            axis_empty = get_axis_empty()
        if not _valid_obj(axis_empty):
            safe_remove_object(obj)
            _dsg_report(
                self, {'ERROR'},
                'Confirm the insertion direction before creating an implant',
                'Confirma la dirección de inserción antes de crear un implante')
            return {'CANCELLED'}

        insertion_axis = axis_empty.matrix_world.to_3x3() @ Vector((0.0, 0.0, 1.0))
        if insertion_axis.length < 1.0e-8:
            safe_remove_object(obj)
            _dsg_report(
                self, {'ERROR'},
                'The saved insertion axis is invalid',
                'El eje de inserción guardado no es válido')
            return {'CANCELLED'}
        insertion_axis.normalize()
        coronal_axis = -insertion_axis

        # Utilizamos el punto capturado con paneo como plataforma inicial. Como
        # la malla del implante está centrada axialmente, desplazamos su origen
        # media longitud hacia apical para que la plataforma nazca sobre dicho
        # punto y el ápice avance siguiendo el eje confirmado.
        platform_world = axis_empty.matrix_world.to_translation().copy()
        implant_center = platform_world + insertion_axis * (
            max(0.10, float(props.implant_length)) * 0.5)

        # Preservar también la base completa del eje (incluido su roll) evita que
        # futuras funciones dependientes de la orientación reciban una matriz
        # reconstruida de forma distinta. El giro de 180° convierte el +Z del
        # eje guardado en el +Z coronal de la plantilla del implante.
        try:
            axis_rotation = axis_empty.matrix_world.to_3x3().normalized().to_4x4()
            flip_to_coronal = Matrix.Rotation(math.pi, 4, 'X')
            implant_matrix = Matrix.Translation(implant_center) @ axis_rotation @ flip_to_coronal
            obj.matrix_world = implant_matrix
        except Exception:
            obj.matrix_world = _matrix_along_local_z(implant_center, coronal_axis)

        # Verificación geométrica: el eje apical real del objeto debe coincidir
        # con el eje de inserción. Si la matriz heredada tuviera escala/reflexión,
        # reconstruimos una base ortonormal segura.
        actual_apical = obj.matrix_world.to_3x3() @ Vector((0.0, 0.0, -1.0))
        if actual_apical.length < 1.0e-8 or actual_apical.normalized().dot(insertion_axis) < 0.999:
            obj.matrix_world = _matrix_along_local_z(implant_center, coronal_axis)

        register_dsg_object(obj, ROLE_IMPLANT, obj.name, {
            'DSG_implant_source': implant_source,
            'DSG_implant_template': IMPLANT_TEMPLATE_SOURCE,
            'DSG_implant_diameter': float(props.implant_diameter),
            'DSG_implant_length': float(props.implant_length),
            'DSG_created_from_insertion_axis': True,
            'DSG_insertion_axis_world': tuple(float(v) for v in insertion_axis),
            'DSG_coronal_axis_world': tuple(float(v) for v in coronal_axis),
            'DSG_insertion_reference_world': tuple(float(v) for v in platform_world),
            'DSG_initial_platform_world': tuple(float(v) for v in platform_world),
            'DSG_implant_axis_source': str(axis_source),
            'DSG_target_fdi': int(axis_empty.get('DSG_target_fdi', 0) or 0) if axis_source == 'fdi_tooth_axis' else 0,
            'DSG_axis_confidence': float(axis_empty.get('DSG_axis_confidence', 0.0) or 0.0) if axis_source == 'fdi_tooth_axis' else 0.0,
            'DSG_axis_method': str(axis_empty.get('DSG_axis_method', '') or '') if axis_source == 'fdi_tooth_axis' else 'manual_guide_axis',
        })
        target_fdi = int(obj.get('DSG_target_fdi', 0) or 0)
        if dental_assets.valid_fdi(target_fdi, include_primary=False):
            obj['DSG_target_family_id'] = dental_assets.family_id(target_fdi)
            obj['DSG_target_tooth_class'] = dental_assets.tooth_class_from_fdi(target_fdi)
            obj['DSG_target_arch'] = dental_assets.arch_from_fdi(target_fdi)
            obj['DSG_target_side'] = dental_assets.side_from_fdi(target_fdi)
            obj['DSG_asset_contract_sha256'] = dental_assets.contract_sha256()
        if axis_source == 'fdi_tooth_axis':
            consume_pending_implant_axis_empty()
        ensure_implant_divergence_property(obj)
        set_implant_parallel_locked(obj, False)
        # Implant 1 remains open. Implant 2 and later are born with a closed
        # frangible irrigation outlet and an internal opening marker.
        implant_order = count_implants(props)
        set_irrigation_implant_sealed(obj, implant_order > 1)
        try:
            obj['DSG_irrigation_gate_auto_index'] = int(implant_order)
            obj['DSG_irrigation_gate_auto_default'] = True
            obj['DSG_irrigation_internal_marker'] = bool(implant_order > 1)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        obj.display_type  = 'WIRE'
        obj.show_in_front = True
        obj.hide_select   = False
        props.implant_obj = obj
        set_active(context, obj)
        rebuild_implant_safety_halos(context, props)

        # Restaurar la ayuda visual original: cada implante recibe de inmediato
        # un control de emergencia orientado por el eje de inserción. La función
        # es idempotente y reutiliza el mismo Object ID en pulsaciones repetidas.
        controller = create_implant_emergence_tube(
            context, props, obj, index=max(1, count_implants(props)))
        set_active(context, controller if _valid_obj(controller) else obj)
        _dsg_report(
            self, {'INFO'},
            f"{obj.name} created from the confirmed insertion axis. Move or rotate its emergence control; keep the 1.5 mm safety halos from overlapping.",
            f"{obj.name} creado desde el eje de inserción confirmado. Mueve o rota su control de emergencia y evita que se solapen los halos de seguridad de 1,5 mm.")
        return {'FINISHED'}


class DSG_OT_RemoveLastImplant(Operator):
    bl_idname = "dsg.remove_last_implant"
    bl_label  = "Delete Last Implant"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if not _require_workflow_stage(
                self, context, STEP_IMPLANT,
                action_en='Cannot delete an implant from this stage',
                action_es='No se puede eliminar un implante desde este paso'):
            return {'CANCELLED'}
        props = context.scene.dsg_props
        implants = get_all_implant_objects(props)
        if not implants:
            _dsg_report(self, {'WARNING'}, "There are no implants to delete", "No hay implantes que eliminar")
            return {'CANCELLED'}

        victim = implants[-1]
        _remove_dicom_measurements_for_implant(victim.name)
        was_master = (_valid_obj(props.parallel_master_implant)
                      and _safe_object_name(props.parallel_master_implant) == _safe_object_name(victim))

        # Delete the provisional emergence controller together with its implant.
        # This prevents the visible tube from remaining orphaned in step 4.
        remove_implant_emergence_tubes_for_implant(victim)
        clear_implant_safety_halos(victim)
        safe_remove_object(victim)
        remaining = get_all_implant_objects(props)
        props.implant_obj = remaining[-1] if remaining else None
        if was_master:
            props.parallel_master_implant = props.implant_obj
        if props.implant_obj:
            set_active(context, props.implant_obj)
        _dsg_report(self, {'INFO'}, "Last implant and its emergence control deleted", "Último implante y su control de emergencia eliminados")
        return {'FINISHED'}


class DSG_OT_ToggleImplantParallelLock(Operator):
    bl_idname = "dsg.toggle_implant_parallel_lock"
    bl_label = "Lock Implant for Parallelization"
    bl_description = (
        "Locks or unlocks the selected implant so DSG parallelization cannot change "
        "its current position or angulation")
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.dsg_props
        implant = get_implant_for_parallel_lock(context, props)
        if not is_valid_implant_obj(implant):
            _dsg_report(
                self, {'ERROR'},
                "Select a DSG implant to lock or unlock",
                "Selecciona un implante DSG para bloquearlo o desbloquearlo")
            return {'CANCELLED'}

        new_state = not is_implant_parallel_locked(implant)
        set_implant_parallel_locked(implant, new_state)
        props.implant_obj = implant
        set_active(context, implant)

        if new_state:
            _dsg_report(
                self, {'INFO'},
                f"{implant.name} locked: parallelization will preserve its pose",
                f"{implant.name} bloqueado: la paralelización conservará su posición y angulación")
        else:
            _dsg_report(
                self, {'INFO'},
                f"{implant.name} unlocked: it can be parallelized again",
                f"{implant.name} desbloqueado: puede volver a paralelizarse")
        return {'FINISHED'}


class DSG_OT_SetParallelMaster(Operator):
    bl_idname = "dsg.set_parallel_master"
    bl_label  = "Use Selected as Master"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.dsg_props
        active = context.view_layer.objects.active

        if not is_valid_implant_obj(active):
            _dsg_report(self, {'ERROR'}, "Select a DSG implant in the scene", "Selecciona un implante DSG en la escena")
            return {'CANCELLED'}

        props.parallel_master_implant = active
        props.implant_obj = active
        active.show_in_front = True
        _dsg_report(self, {'INFO'}, f"Master implant: {active.name}", f"Implante maestro: {active.name}")
        return {'FINISHED'}


class DSG_OT_ParallelizeImplants(Operator):
    bl_idname = "dsg.parallelize_implants"
    bl_label  = "Parallelize Implants to Master"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if not _require_workflow_stage(
                self, context, STEP_IMPLANT,
                action_en='Cannot parallelize implants from this stage',
                action_es='No se pueden paralelizar implantes desde este paso'):
            return {'CANCELLED'}
        props = context.scene.dsg_props
        implants = get_all_implant_objects(props)
        if len(implants) < 2:
            _dsg_report(self, {'ERROR'}, "At least 2 implants are required", "Necesitas al menos 2 implantes")
            return {'CANCELLED'}

        master = get_parallel_master_implant(context, props)
        if not is_valid_implant_obj(master):
            _dsg_report(self, {'ERROR'}, "Choose or select a master implant", "Elige o selecciona un implante maestro")
            return {'CANCELLED'}

        changed = 0
        locked_skipped = []
        tolerance = max(0.0, float(getattr(props, 'parallel_divergence_tolerance', 0.0)))
        applied_offsets = []
        for implant in implants:
            ensure_implant_divergence_property(implant)
            if implant.name == master.name:
                implant['DSG_divergence_applied_deg'] = 0.0
                continue
            if is_implant_parallel_locked(implant):
                locked_skipped.append(implant.name)
                continue
            requested = float(implant.get('DSG_divergence_deg', 0.0))
            offset = max(-tolerance, min(tolerance, requested))
            if copy_implant_world_rotation_keep_position(implant, master, divergence_deg=offset):
                implant.show_in_front = True
                applied_offsets.append(offset)
                changed += 1

        props.parallel_master_implant = master
        props.implant_obj = master
        set_active(context, master)

        offsets_txt = ', '.join(f'{value:+.1f}°' for value in applied_offsets) if applied_offsets else '0°'
        msg_en = f"{changed} implant(s) aligned to {master.name}; applied offsets: {offsets_txt}"
        msg_es = f"{changed} implante(s) alineados con {master.name}; offsets aplicados: {offsets_txt}"
        if locked_skipped:
            locked_txt = ', '.join(locked_skipped)
            msg_en += f" — {len(locked_skipped)} locked implant(s) preserved: {locked_txt}"
            msg_es += f" — {len(locked_skipped)} implante(s) bloqueados conservados: {locked_txt}"
        if _valid_obj(props.guide_obj):
            msg_en += " — regenerate sleeves/channels to update the guide"
            msg_es += " — regenera cilindros/canales para actualizar la guía"
        _dsg_report(self, {'INFO'}, msg_en, msg_es)
        return {'FINISHED'}



class DSG_OT_CreateImplantEmergenceTubes(Operator):
    bl_idname = 'dsg.create_implant_emergence_tubes'
    bl_label = 'Create Implant Emergence Tubes'
    bl_description = (
        'Creates a 15 mm long, 2.0 mm diameter tube from the central axis of each implant '
        'towards the future sleeve direction. Moving or rotating the tube temporarily moves the associated implant')
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if not _require_workflow_stage(
                self, context, STEP_IMPLANT,
                action_en='Cannot create emergence controls from this stage',
                action_es='No se pueden crear controles de emergencia desde este paso'):
            return {'CANCELLED'}
        props = context.scene.dsg_props
        implants = get_all_implant_objects(props)
        if not implants:
            _dsg_report(self, {'ERROR'}, 'No implants available', 'No hay implantes disponibles')
            return {'CANCELLED'}

        # Idempotent controller creation: repeated clicks must reuse the same
        # Object IDs instead of deleting/recreating them while the Outliner is
        # drawing. This directly avoids stale AnimData/ID pointers in Blender 5.0.
        valid_implant_names = {_safe_object_name(implant) for implant in implants}
        seen = set()
        for tube in list(get_implant_emergence_tubes()):
            linked_name = str(tube.get('DSG_implant_name', '') or '')
            if linked_name not in valid_implant_names or linked_name in seen:
                _detach_implant_from_emergence_tube(tube)
                try:
                    tube['DSG_implant_emergence_tube'] = False
                    tube['DSG_implant_emergence_controller'] = False
                except Exception:
                    _DSG_LOG.debug("suppressed exception", exc_info=True)
                _archive_transient_dsg_object(
                    tube, reason='duplicate_emergence_controller',
                    prefix='DSG_ArchivedEmergence_')
                continue
            seen.add(linked_name)

        rebuild_implant_safety_halos(context, props)
        controller_objects = []
        reused = 0
        created = 0
        for index, implant in enumerate(implants, start=1):
            previous = _get_emergence_controller_for_implant(implant)
            tube = create_implant_emergence_tube(context, props, implant, index=index)
            if _valid_obj(tube):
                controller_objects.append(tube)
                if _valid_obj(previous):
                    reused += 1
                else:
                    created += 1

        if not controller_objects:
            _dsg_report(
                self, {'ERROR'},
                'No implant emergence tubes could be created',
                'No se pudieron crear los tubos de emergencia de los implantes')
            return {'CANCELLED'}

        set_active(context, controller_objects[0])
        if created == 0:
            _dsg_report(
                self, {'INFO'},
                f'{reused} existing emergence controller(s) reused; implant positions were preserved.',
                f'Se reutilizaron {reused} control(es) de emergencia; se conservaron las posiciones de los implantes.')
        else:
            _dsg_report(
                self, {'INFO'},
                f'Emergence controllers ready: {created} created, {reused} reused.',
                f'Controles de emergencia listos: {created} creados y {reused} reutilizados.')
        return {'FINISHED'}


class DSG_OT_ConfirmImplant(Operator):
    bl_idname = "dsg.confirm_implant"
    bl_label  = "Confirm Implants"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if not _require_workflow_stage(
                self, context, STEP_IMPLANT,
                action_en='Cannot confirm the implant plan',
                action_es='No se puede confirmar la planificación de implantes'):
            return {'CANCELLED'}
        if core.clinical_route(context.scene) == core.ROUTE_IMMEDIATE and not _immediate_extraction_ready(context.scene):
            _dsg_report(
                self, {'ERROR'},
                'The immediate implant cannot be confirmed before the target FDI virtual extraction is prepared',
                'No se puede confirmar el implante inmediato antes de preparar la extracción virtual del FDI objetivo')
            return {'CANCELLED'}
        props = context.scene.dsg_props
        implants = get_all_implant_objects(props)
        if not implants:
            _dsg_report(self, {'ERROR'}, "Create at least one implant first", "Crea al menos un implante primero")
            return {'CANCELLED'}

        if not is_valid_implant_obj(props.implant_obj):
            props.implant_obj = implants[-1]

        passive = get_confirmed_passive_model_obj()
        if not _valid_obj(passive):
            blockout = bpy.data.objects.get(BLOCKOUT_NAME)
            props.current_step = STEP_IMPLANT
            _schedule_implant_planning_state_restore(
                context.scene, require_armed=False, delay=0.02)
            if _valid_obj(blockout):
                _dsg_report(
                    self, {'ERROR'},
                    'The retentive model is calculated but not confirmed. Use the large CONFIRM RETENTIVE MODEL button before continuing.',
                    'El modelo retentivo está calculado pero no confirmado. Pulsa el botón grande CONFIRMAR MODELO RETENTIVO antes de continuar.')
            else:
                _dsg_report(
                    self, {'ERROR'},
                    'Calculate and confirm the retentive model before continuing to the guide contour',
                    'Calcula y confirma el modelo retentivo antes de continuar al contorno de la guía')
            return {'CANCELLED'}

        violations = get_interimplant_spacing_violations(props)
        if violations:
            rebuild_implant_safety_halos(context, props)
            mark_implant_safety_halos(violations)
            worst = violations[0]
            select_interimplant_violation(context, props, worst)
            implant_a = _safe_object_name(worst['implant_a']) or 'Implant A'
            implant_b = _safe_object_name(worst['implant_b']) or 'Implant B'
            clearance = float(worst['clearance_mm'])
            deficit = float(worst['deficit_mm'])
            _dsg_report(
                self, {'ERROR'},
                f"Unsafe implant spacing: {implant_a} ↔ {implant_b} has {clearance:.2f} mm free; "
                f"minimum is {INTERIMPLANT_MIN_CLEARANCE_MM:.2f} mm. Separate them by at least {deficit:.2f} mm.",
                f"Separación insegura: {implant_a} ↔ {implant_b} tiene {clearance:.2f} mm libres; "
                f"el mínimo es {INTERIMPLANT_MIN_CLEARANCE_MM:.2f} mm. Sepáralos al menos {deficit:.2f} mm.")
            return {'CANCELLED'}

        # A fast BVH approximation is sufficient for live feedback but is not
        # allowed to act as the clinical confirmation gate.  Confirmation uses
        # the triangle↔triangle verifier and fails closed when verification is
        # incomplete or an expected segmented neighbour is missing.
        tooth_gate_results = get_implant_tooth_safety_results(props, verification_mode='EXACT')
        tooth_indeterminate = [r for r in tooth_gate_results if r.get('safe') is None]
        if tooth_indeterminate:
            rebuild_implant_safety_halos(context, props)
            mark_implant_safety_halos(
                [], additional_implant_names=[r.get('implant') for r in tooth_indeterminate])
            first = tooth_indeterminate[0]
            reason = str(first.get('error', '') or '')
            missing = first.get('unverified_neighbors') or []
            if missing:
                reason = ', '.join(str(x.get('reason', 'UNVERIFIED')) for x in missing)
            _dsg_report(
                self, {'ERROR'},
                f"Implant-tooth clearance could not be verified exactly for {first.get('implant', 'Implant')}. Confirmation is blocked ({reason or 'exact verification incomplete'}).",
                f"No se pudo verificar de forma exacta la distancia implante-diente para {first.get('implant', 'Implante')}. La confirmación queda bloqueada ({reason or 'verificación exacta incompleta'}).")
            return {'CANCELLED'}

        tooth_violations = [r for r in tooth_gate_results if r.get('safe') is False]
        if tooth_violations:
            rebuild_implant_safety_halos(context, props)
            mark_implant_safety_halos(
                [], additional_implant_names=[r.get('implant') for r in tooth_violations])
            worst = min(
                tooth_violations,
                key=lambda r: float(r.get('minimum_neighbor_clearance_mm', 1.0e9)))
            clearance = float(worst.get('minimum_neighbor_clearance_mm', 0.0))
            required = float(worst.get('required_clearance_mm', getattr(
                props, 'implant_tooth_clearance', IMPLANT_TOOTH_CLEARANCE_DEFAULT_MM)))
            deficit = max(0.0, required - clearance)
            _dsg_report(
                self, {'ERROR'},
                f"Unsafe implant-tooth clearance (exact surface verification): {worst.get('implant', 'Implant')} has {clearance:.2f} mm; required is {required:.2f} mm. Recover at least {deficit:.2f} mm or explicitly change the evidence/context clearance.",
                f"Distancia implante-diente insegura (verificación exacta de superficies): {worst.get('implant', 'Implante')} tiene {clearance:.2f} mm; se requieren {required:.2f} mm. Recupera al menos {deficit:.2f} mm o cambia explícitamente la distancia según evidencia/contexto.")
            return {'CANCELLED'}

        # Compare the edited clinical plan before changing any temporary
        # controller state.  The final signature is stored only after the
        # emergence controllers have been detached and Blender has stabilised
        # the world matrices.
        implant_signature_before_finalize = _workflow_implants_signature(props)
        if _workflow_signature_changed(
                context.scene, WORKFLOW_IMPLANT_SIGNATURE_KEY,
                implant_signature_before_finalize):
            _invalidate_workflow_after(context, STEP_IMPLANT, reason='implant_plan_changed')

        # Save a runtime snapshot before any controller, DICOM or viewport state
        # is changed. It survives Blender undo and is used by both Atrás and
        # Ctrl+Z to reconstruct the exact implant-planning workspace.
        _capture_implant_step_return_state(context, props)

        for implant in implants:
            implant.hide_select = True
            implant.show_in_front = True

        # El tubo de emergencia es exclusivamente una ayuda visual de la planificación implantaria.
        # Se elimina junto con su malla antes de continuar al frame y no vuelve
        # a aparecer en ninguno de los pasos posteriores.
        clear_implant_emergence_tubes()
        for implant in implants:
            try:
                if 'DSG_temporarily_controlled_by_emergence' in implant:
                    del implant['DSG_temporarily_controlled_by_emergence']
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)

        clear_implant_safety_halos()
        _close_dicom_review_for_guide(context)
        _set_retention_boundary_visible(True)
        context.scene[WORKFLOW_IMPLANTS_CONFIRMED_KEY] = True
        for implant in implants:
            try:
                implant['DSG_implant_confirmed'] = True
                implant['DSG_implant_confirmed_version'] = '8.2.8'
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)

        # Re-evaluate after controller detachment.  This is the canonical pose
        # used by the contour gate and by geometric Back checkpoints.
        try:
            context.view_layer.update()
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        implant_signature_final = _workflow_implants_signature(props)
        _workflow_store_signature(
            context.scene, WORKFLOW_IMPLANT_SIGNATURE_KEY,
            implant_signature_final)
        context.scene[WORKFLOW_IMPLANT_SIGNATURE_SCHEMA_KEY] = WORKFLOW_IMPLANT_SIGNATURE_SCHEMA

        props.current_step = STEP_CONTOUR
        context.scene[GUIDE_FLOW_ORDER_KEY] = GUIDE_FLOW_ORDER_MODEL_IMPLANT
        _dsg_report(self, {'INFO'}, f"{len(implants)} implant(s) confirmed with ≥ {INTERIMPLANT_MIN_CLEARANCE_MM:.1f} mm interimplant spacing", f"{len(implants)} implante(s) confirmados con separación interimplantaria ≥ {INTERIMPLANT_MIN_CLEARANCE_MM:.1f} mm")
        return {'FINISHED'}


# ─────────────────────────────────────────────────────────────
# Paso 6 — Frame tubular (usa Bevel Joints)
# ─────────────────────────────────────────────────────────────


