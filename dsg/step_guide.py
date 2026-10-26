"""Beginner guide shown at the top of the DSG panel.

Three titles (one per stage: DICOM, alignment, guide design) and, inside each,
numbered subtitles that tell a first-time user what to do now.  Where a step
has several phases (retentive model, implant planning) a third line names the
phase the case is in, read from the live scene state.
"""
import textwrap

# Every text is (spanish, english).
STAGES = {
    'DICOM': ('CBCT DEL PACIENTE', "PATIENT'S CBCT"),
    'ALIGNMENT': ('UNIR IOS Y CBCT', 'MATCH IOS AND CBCT'),
    'GUIDE': ('DISEÑO DE LA FÉRULA', 'GUIDE DESIGN'),
}
STAGE_ORDER = ('DICOM', 'ALIGNMENT', 'GUIDE')

# key: (title, hint)
DICOM_STEPS = {
    'engines': (('Prepara el programa', 'Get the program ready'),
                ('Pulsa INSTALAR MOTORES y espera a que termine. Solo se hace la primera vez.',
                 'Press INSTALL ENGINES and wait. It is only needed the first time.')),
    'patient': (('Elige el paciente', 'Choose the patient'),
                ('Pulsa ELEGIR PACIENTE y selecciona la carpeta del paciente.',
                 "Press CHOOSE PATIENT and pick the patient's folder.")),
    'load': (('Carga el CBCT', 'Load the CBCT'),
             ('Pulsa CARGAR CBCT y espera a que aparezca la imagen.',
              'Press LOAD CBCT and wait for the image to appear.')),
    'loading': (('Carga el CBCT', 'Load the CBCT'),
                ('Cargando el CBCT… espera, no hace falta pulsar nada.',
                 'Loading the CBCT… please wait, nothing to press.')),
    'route': (('Elige el tipo de caso', 'Choose the type of case'),
              ('SIMPLE si no hay que sacar dientes. INMEDIATO si vas a extraer dientes '
               'y colocar el implante en el mismo acto.',
               'SIMPLE when no tooth is extracted. IMMEDIATE when teeth are extracted '
               'and the implant is placed in the same session.')),
    'segment': (('Espera a que se separen dientes y hueso', 'Wait while teeth and bone are separated'),
                ('El programa está identificando dientes y hueso. Puede tardar unos minutos; '
                 'mira el porcentaje abajo a la izquierda.',
                 'The program is identifying teeth and bone. It can take a few minutes; '
                 'watch the percentage at the bottom left.')),
    'review_simple': (('Revisa las arcadas', 'Check the arches'),
                      ('Comprueba que las dos arcadas (arena y celeste) están bien. '
                       'MEJORAR DIENTES es opcional. Pulsa CONFIRMAR.',
                       'Check both arches (sand and light blue). IMPROVE TEETH is optional. '
                       'Press CONFIRM.')),
    'select_teeth': (('Marca los dientes a extraer', 'Mark the teeth to extract'),
                     ('Haz clic en la vista 3D sobre los dientes que vas a sacar, pulsa '
                      'FIJAR DIENTES y después CONFIRMAR.',
                      'Click the teeth you will extract in the 3D view, press FIX TEETH '
                      'and then CONFIRM.')),
    'alveoli': (('Revisa los alvéolos', 'Check the sockets'),
                ('Comprueba el hueco que dejan los dientes extraídos y pulsa CONFIRMAR. '
                 'Si te equivocaste, CAMBIAR EXTRACCIONES.',
                 'Check the sockets left by the extracted teeth and press CONFIRM. '
                 'If something is wrong, CHANGE EXTRACTIONS.')),
}
DICOM_SIMPLE = ('engines', 'patient', 'load', 'route', 'segment', 'review_simple')
DICOM_IMMEDIATE = ('engines', 'patient', 'load', 'route', 'segment', 'select_teeth', 'alveoli')

ALIGN_STEPS = {
    'import': (('Importa el escaneo intraoral (IOS)', 'Import the intraoral scan (IOS)'),
               ('Pulsa IMPORTAR IOS y elige el archivo STL del escáner.',
                "Press IMPORT IOS and choose the scanner's STL file.")),
    'points': (('Marca 3 puntos iguales', 'Mark 3 matching points'),
               ('Pulsa MARCAR 3 PUNTOS. Marca 3 puntos en el IOS y los mismos 3 puntos '
                'en el CBCT (por ejemplo puntas de dientes bien separados).',
                'Press MARK 3 POINTS. Mark 3 points on the IOS and the same 3 on the CBCT '
                '(for example tips of well separated teeth).')),
    'align': (('Une los dos modelos', 'Join both models'),
              ('Pulsa ALINEAR. Si un punto quedó mal, REDIBUJAR PUNTOS.',
               'Press ALIGN. If a point is wrong, REDRAW POINTS.')),
    'review': (('Comprueba el ajuste', 'Check the fit'),
               ('Mira que el IOS encaje sobre el CBCT. Si encaja, pulsa SIGUIENTE; '
                'si no, MARCAR PUNTOS DE NUEVO.',
                'Check that the IOS sits on the CBCT. If it fits, press NEXT; '
                'otherwise MARK POINTS AGAIN.')),
}
ALIGN_ORDER = ('import', 'points', 'align', 'review')

# Guide design: one entry per DSG step (current_step 0..9).
GUIDE_STEPS = (
    (('Prepara el modelo donde apoya la férula', 'Prepare the model the guide sits on'),
     ('Sigue las indicaciones de abajo.', 'Follow the instructions below.')),
    (('Planifica el implante', 'Plan the implant'),
     ('Sigue las indicaciones de abajo.', 'Follow the instructions below.')),
    (('Dibuja el borde de la férula', 'Draw the edge of the guide'),
     ('Pulsa MARCAR CONTORNO y haz clic alrededor de la arcada. Pulsa TERMINAR EDICIÓN '
      'DE PUNTOS y después SIGUIENTE.',
      'Press MARK CONTOUR and click around the arch. Press FINISH POINT EDITING and then NEXT.')),
    (('Crea el cuerpo de la férula', 'Build the body of the guide'),
     ('Ajusta el grosor y pulsa CREAR ESTRUCTURA. Añadir un microtornillo es opcional. '
      'Después pulsa SIGUIENTE.',
      'Set the thickness and press CREATE FRAME. Adding a microscrew is optional. '
      'Then press NEXT.')),
    (('Crea los cilindros guía de la fresa', 'Create the drill guide sleeves'),
     ('Revisa el diámetro de la fresa, la pared y la altura y pulsa CREAR CILINDROS. '
      'Después pulsa SIGUIENTE.',
      'Check drill diameter, wall and height and press CREATE SLEEVES. Then press NEXT.')),
    (('Añade irrigación (opcional)', 'Add irrigation (optional)'),
     ('Dibuja un conducto de agua y pulsa APLICAR IRRIGACIÓN, o pulsa SIGUIENTE para '
      'saltarlo. La apertura lateral también es opcional.',
      'Draw a water channel and press APPLY IRRIGATION, or press NEXT to skip it. '
      'The lateral opening is optional too.')),
    (('Refuerza la férula (opcional)', 'Reinforce the guide (optional)'),
     ('Pulsa OPTIMIZAR FRAME para un refuerzo automático y USAR REFUERZO, o pulsa '
      'SIGUIENTE para saltarlo.',
      'Press OPTIMIZE FRAME for an automatic reinforcement and USE REINFORCEMENT, '
      'or press NEXT to skip it.')),
    (('Abre el paso de la fresa', 'Open the drill path'),
     ('Pulsa CREAR CANALES DE FRESADO y después SIGUIENTE.',
      'Press CREATE DRILL CHANNELS and then NEXT.')),
    (('Termina la férula', 'Finish the guide'),
     ('Pulsa FINALIZAR GUÍA y espera al corte final. Después pulsa SIGUIENTE.',
      'Press FINISH GUIDE and wait for the final cut. Then press NEXT.')),
    (('Guarda la férula para imprimir', 'Save the guide for printing'),
     ('Pulsa EXPORTAR STL. Grabar el nombre y ver la animación son opcionales.',
      'Press EXPORT STL. Engraving the name and the animation are optional.')),
)

# Phases inside "Prepara el modelo" and "Planifica el implante": (title, hint)
PHASES = {
    'align_first': (('Termina primero el alineamiento', 'Finish the alignment first'),
                    ('Vuelve a ALINEAR y completa la etapa 2.',
                     'Go back to ALIGN and complete stage 2.')),
    'close_holes': (('Cierra los agujeros del escaneo', 'Close the holes of the scan'),
                    ('Pulsa CERRAR AGUJEROS SEGUROS.', 'Press CLOSE SAFE HOLES.')),
    'closed_model': (('Crea el modelo cerrado', 'Create the closed model'),
                     ('Pulsa CREAR MODELO CERRADO; revisa los agujeros seguros y después cierra la base.',
                      'Press CREATE CLOSED MODEL; safe scan holes are checked before base closure.')),
    'accept_closed': (('Acepta el modelo cerrado', 'Accept the closed model'),
                      ('Pulsa USAR MODELO CERRADO Y CONTINUAR.',
                       'Press USE CLOSED MODEL AND CONTINUE.')),
    'tooth_editing': (('Quita el diente del escaneo', 'Remove the tooth from the scan'),
                      ('Pasa el círculo sobre el diente (AÑADIR / QUITAR) y pulsa '
                       '2 · CERRAR HUECO HACIA DENTRO.',
                       'Brush the circle over the tooth (ADD / REMOVE) and press '
                       '2 · CLOSE SOCKET INWARDS.')),
    'remove_tooth': (('Quita el diente que se va a extraer', 'Remove the tooth to be extracted'),
                     ('Pulsa 1 · SELECCIONAR DIENTE para borrarlo del escaneo, '
                      'o SIGUIENTE para saltar este paso.',
                      'Press 1 · SELECT TOOTH to remove it from the scan, '
                      'or NEXT to skip this step.')),
    'prepare': (('Elige por dónde entra la férula', 'Choose how the guide goes in'),
                ('Gira la vista para mirar los dientes desde donde entrará la férula y '
                 'pulsa PREPARAR MODELO RETENTIVO.',
                 'Turn the view to look at the teeth from where the guide will go in and '
                 'press PREPARE RETENTIVE MODEL.')),
    'checking': (('Comprobando el asiento', 'Checking the seating'),
                 ('Espera un momento, el programa comprueba que la férula asienta.',
                  'Please wait while the program checks that the guide seats.')),
    'confirm': (('Confirma el modelo retentivo', 'Confirm the retentive model'),
                ('La zona turquesa es el relleno añadido. Si está bien, pulsa '
                 'CONFIRMAR MODELO RETENTIVO.',
                 'The teal area is the added fill. If it looks right, press '
                 'CONFIRM RETENTIVE MODEL.')),
    'review_seat': (('Revisa el asiento', 'Review the seating'),
                    ('Cambia la vista o la retención y vuelve a pulsar PREPARAR. '
                     'Si lo has revisado y está bien, CONTINUAR TRAS REVISIÓN.',
                     'Change the view or the retention and press PREPARE again. '
                     'If you checked it and it is fine, CONTINUE AFTER REVIEW.')),
    'extraction': (('Haz la extracción virtual', 'Do the virtual extraction'),
                   ('Ajusta la extensión coronal, pulsa REALIZAR OPERACIÓN BOOLEANA y '
                    'después SIGUIENTE.',
                    'Set the coronal extension, press PERFORM BOOLEAN OPERATION and then NEXT.')),
    'neighbors': (('Elige los dientes vecinos', 'Choose the neighbouring teeth'),
                  ('Marca qué dientes quieres ver al colocar el implante y pulsa '
                   'CONFIRMAR SELECCIÓN.',
                   'Mark the teeth you want to see while placing the implant and press '
                   'CONFIRM SELECTION.')),
    'add_implant': (('Añade el implante', 'Add the implant'),
                    ('Elige diámetro y longitud y pulsa AÑADIR IMPLANTE.',
                     'Choose diameter and length and press ADD IMPLANT.')),
    'place_implant': (('Coloca y revisa el implante', 'Position and check the implant'),
                      ('Muévelo con G y gíralo con R. Revísalo en el CBCT con Revisar '
                       'implante seleccionado. BUSCAR PROPUESTA te sugiere un tamaño. '
                       'Cuando esté bien, pulsa SIGUIENTE.',
                       'Move it with G and rotate it with R. Check it in the CBCT with '
                       'Review selected implant. FIND PROPOSAL suggests a size. '
                       'When it is right, press NEXT.')),
}


def _t(scene, pair):
    from . import core
    return core.translate_ui(scene, pair[1], pair[0])


# ── state ──────────────────────────────────────────────────────────────────
def _dicom_key(scene):
    from . import core
    try:
        from . import runtime_bootstrap
        if not bool(runtime_bootstrap.ui_engines_ready()):
            return 'engines'
    except Exception:
        pass
    if not core.patient_folder(scene):
        return 'patient'
    step = str(scene.get(core.ROUTE_STEP_KEY, '') or '')
    if step == 'CBCT_LOADING':
        return 'loading'
    if step in {'', 'PATIENT'}:
        return 'load'
    if step in {'SIMPLE_SEGMENTING', 'IMMEDIATE_LAUNCHING', 'IMMEDIATE_SEGMENTING'}:
        return 'segment'
    if step == 'SIMPLE_REVIEW':
        return 'review_simple'
    if step in {'IMMEDIATE_FDI_REVIEW', 'IMMEDIATE_SELECT_TEETH'}:
        return 'select_teeth'
    if step == 'IMMEDIATE_ARCH_REVIEW':
        return 'alveoli'
    return 'route'


def _dicom_order(scene):
    from . import core
    try:
        if core.clinical_route(scene) == core.ROUTE_IMMEDIATE:
            return DICOM_IMMEDIATE
    except Exception:
        pass
    step = str(scene.get(core.ROUTE_STEP_KEY, '') or '')
    return DICOM_IMMEDIATE if step.startswith('IMMEDIATE') else DICOM_SIMPLE


def _align_key(scene):
    props = getattr(scene, 'dicp_props', None)
    if props is None:
        return 'import'
    source = getattr(props, 'icp_source_obj', None)
    if source is None or getattr(source, 'type', '') != 'MESH':
        return 'import'
    if bool(getattr(props, 'aligned', False)):
        return 'review'
    if int(getattr(props, 'source_point_count', 0)) == 3 and int(getattr(props, 'target_point_count', 0)) == 3:
        return 'align'
    return 'points'


def _model_phase(context):
    from . import guide_module as g
    from . import core
    from .blender import ios_tooth_edit
    props = context.scene.dsg_props
    if ios_tooth_edit.editing(context):
        return 'tooth_editing'
    model = getattr(props, 'model_obj', None)
    detected = (g._closed_counterpart(model) or model) if g._valid_obj(model) else g._find_aligned_ios(context)
    if not g._valid_obj(detected):
        return 'align_first'
    topology = g.get_model_topology_report_cached(detected)
    closed = bool(topology.get('checked') and g._workflow_closed_boundary_passes(topology))
    if topology.get('checked') and not closed:
        return 'closed_model'
    if closed and core.clinical_route(context.scene) == core.ROUTE_IMMEDIATE:
        from .blender import ios_socket_boolean
        from .blender.ios_skip_removal import SKIPPED
        if not ios_socket_boolean.prepared(detected) and not detected.get(SKIPPED):
            return 'remove_tooth'
    accepted = bool(detected.get(g.CLOSED_MODEL_ACCEPTED_FLAG, False)
                    or detected.get('DSG_base_closed_manifold', False)
                    or str(detected.get('DSG_base_closure_status', '')).startswith(
                        ('direct_', 'already_solid', 'external_')))
    if closed and not accepted:
        return 'accept_closed'
    import bpy
    blockout = bpy.data.objects.get(g.BLOCKOUT_NAME)
    if not g._valid_obj(blockout):
        return 'prepare'
    status = str(blockout.get('DSG_seating_validation_status', 'PENDING')).upper()
    if status == 'PENDING':
        return 'checking'
    return 'confirm' if status == 'PASSED' else 'review_seat'


def _implant_phase(context):
    from . import guide_module as g
    from .blender import virtual_extraction, protected_neighbors
    scene = context.scene
    if not virtual_extraction.confirmed(scene):
        return 'extraction'
    if not protected_neighbors.confirmed(scene):
        return 'neighbors'
    return 'place_implant' if g.count_implants(scene.dsg_props) > 0 else 'add_implant'


def _current_v1(context):
    """(stage_key, sub_index, sub_total, (title, hint), phase_or_None)."""
    from . import core
    scene = context.scene
    try:
        stage = core.infer_stage(scene)
    except Exception:
        return None
    if stage == core.STAGE_DICOM:
        order = _dicom_order(scene)
        key = _dicom_key(scene)
        index = order.index('load' if key == 'loading' else key) if ('load' if key == 'loading' else key) in order else 0
        return 'DICOM', index + 1, len(order), DICOM_STEPS[key], None
    if stage == core.STAGE_ALIGNMENT:
        key = _align_key(scene)
        return 'ALIGNMENT', ALIGN_ORDER.index(key) + 1, len(ALIGN_ORDER), ALIGN_STEPS[key], None
    if stage == core.STAGE_GUIDE:
        try:
            step = int(getattr(scene.dsg_props, 'current_step', 0))
        except Exception:
            step = 0
        step = max(0, min(len(GUIDE_STEPS) - 1, step))
        phase = None
        try:
            if step == 0:
                phase = _model_phase(context)
            elif step == 1:
                phase = _implant_phase(context)
        except Exception:
            phase = None
        return 'GUIDE', step + 1, len(GUIDE_STEPS), GUIDE_STEPS[step], phase
    return None


# ── drawing ────────────────────────────────────────────────────────────────
# Short noun names, like the wizard steps of exocad / 3Shape (es, en).
SHORT = {
    'DICOM': {
        'engines': ('Motores', 'Engines'), 'patient': ('Paciente', 'Patient'),
        'load': ('CBCT', 'CBCT'), 'loading': ('CBCT', 'CBCT'),
        'route': ('Tipo de caso', 'Case type'), 'segment': ('Segmentación', 'Segmentation'),
        'review_simple': ('Revisión de arcadas', 'Arch review'),
        'select_teeth': ('Dientes a extraer', 'Teeth to extract'),
        'alveoli': ('Alvéolos', 'Sockets'),
    },
    'ALIGNMENT': {
        'import': ('Importar IOS', 'Import IOS'), 'points': ('3 puntos', '3 points'),
        'align': ('Alinear', 'Align'), 'review': ('Revisión del ajuste', 'Fit review'),
    },
    'GUIDE': (
        ('Modelo retentivo', 'Retentive model'), ('Implantes', 'Implants'),
        ('Contorno', 'Contour'), ('Estructura', 'Frame'), ('Cilindros', 'Sleeves'),
        ('Irrigación', 'Irrigation'), ('Refuerzos', 'Reinforcement'),
        ('Canales de fresado', 'Drill channels'), ('Corte final', 'Final cut'),
        ('Exportar', 'Export'),
    ),
}
PHASE_SHORT = {
    'align_first': ('Alineamiento pendiente', 'Alignment pending'),
    'close_holes': ('Cerrar agujeros', 'Close holes'),
    'closed_model': ('Crear modelo cerrado', 'Create closed model'),
    'accept_closed': ('Aceptar modelo cerrado', 'Accept closed model'),
    'tooth_editing': ('Quitar diente del IOS', 'Remove IOS tooth'),
    'remove_tooth': ('Quitar diente del IOS', 'Remove IOS tooth'),
    'prepare': ('Eje de inserción', 'Insertion axis'),
    'checking': ('Comprobando asiento', 'Checking seating'),
    'confirm': ('Confirmar', 'Confirm'),
    'review_seat': ('Revisar asiento', 'Review seating'),
    'extraction': ('Extracción virtual', 'Virtual extraction'),
    'neighbors': ('Dientes vecinos', 'Neighbour teeth'),
    'add_implant': ('Añadir implante', 'Add implant'),
    'place_implant': ('Posición y revisión', 'Position and review'),
}
# One short instruction per state (es, en).
TIP = {
    ('DICOM', 'engines'): ('Pulsa INSTALAR MOTORES (solo la primera vez).', 'Press INSTALL ENGINES (first time only).'),
    ('DICOM', 'patient'): ('Pulsa ELEGIR PACIENTE.', 'Press CHOOSE PATIENT.'),
    ('DICOM', 'load'): ('Pulsa CARGAR CBCT.', 'Press LOAD CBCT.'),
    ('DICOM', 'loading'): ('Cargando… espera.', 'Loading… please wait.'),
    ('DICOM', 'route'): ('SIMPLE sin extracciones · INMEDIATO con extracciones.', 'SIMPLE without extractions · IMMEDIATE with extractions.'),
    ('DICOM', 'segment'): ('Espera; el progreso sale abajo a la izquierda.', 'Wait; progress is shown at the bottom left.'),
    ('DICOM', 'review_simple'): ('Revisa las dos arcadas y pulsa CONFIRMAR.', 'Check both arches and press CONFIRM.'),
    ('DICOM', 'select_teeth'): ('Clic en los dientes, FIJAR DIENTES y CONFIRMAR.', 'Click the teeth, FIX TEETH and CONFIRM.'),
    ('DICOM', 'alveoli'): ('Revisa los alvéolos y pulsa CONFIRMAR.', 'Check the sockets and press CONFIRM.'),
    ('ALIGNMENT', 'import'): ('Pulsa IMPORTAR IOS.', 'Press IMPORT IOS.'),
    ('ALIGNMENT', 'points'): ('Marca los mismos 3 puntos en IOS y CBCT.', 'Mark the same 3 points on IOS and CBCT.'),
    ('ALIGNMENT', 'align'): ('Pulsa ALINEAR.', 'Press ALIGN.'),
    ('ALIGNMENT', 'review'): ('Si encaja, pulsa SIGUIENTE.', 'If it fits, press NEXT.'),
    ('GUIDE', 2): ('Marca el contorno alrededor de la arcada.', 'Mark the contour around the arch.'),
    ('GUIDE', 3): ('Ajusta el grosor y pulsa CREAR ESTRUCTURA.', 'Set thickness and press CREATE FRAME.'),
    ('GUIDE', 4): ('Pulsa CREAR CILINDROS.', 'Press CREATE SLEEVES.'),
    ('GUIDE', 5): ('Opcional · dibuja un conducto o pulsa SIGUIENTE.', 'Optional · draw a channel or press NEXT.'),
    ('GUIDE', 6): ('Opcional · OPTIMIZAR FRAME o SIGUIENTE.', 'Optional · OPTIMIZE FRAME or NEXT.'),
    ('GUIDE', 7): ('Pulsa CREAR CANALES DE FRESADO.', 'Press CREATE DRILL CHANNELS.'),
    ('GUIDE', 8): ('Pulsa FINALIZAR GUÍA.', 'Press FINISH GUIDE.'),
    ('GUIDE', 9): ('Pulsa EXPORTAR STL.', 'Press EXPORT STL.'),
    'align_first': ('Completa primero el alineamiento.', 'Complete the alignment first.'),
    'close_holes': ('Pulsa CERRAR AGUJEROS SEGUROS.', 'Press CLOSE SAFE HOLES.'),
    'closed_model': ('Pulsa CREAR MODELO CERRADO.', 'Press CREATE CLOSED MODEL.'),
    'accept_closed': ('Pulsa USAR MODELO CERRADO Y CONTINUAR.', 'Press USE CLOSED MODEL AND CONTINUE.'),
    'tooth_editing': ('Selecciona el diente y pulsa CERRAR HUECO.', 'Select the tooth and press CLOSE SOCKET.'),
    'remove_tooth': ('SELECCIONAR DIENTE, o SIGUIENTE para omitir.', 'SELECT TOOTH, or NEXT to skip.'),
    'prepare': ('Mira desde la entrada de la férula y pulsa PREPARAR.', 'View from the insertion side and press PREPARE.'),
    'checking': ('Espera un momento.', 'Please wait.'),
    'confirm': ('Pulsa CONFIRMAR MODELO RETENTIVO.', 'Press CONFIRM RETENTIVE MODEL.'),
    'review_seat': ('Cambia la vista o la retención y PREPARA de nuevo.', 'Change view or retention and PREPARE again.'),
    'extraction': ('Pulsa REALIZAR OPERACIÓN BOOLEANA.', 'Press PERFORM BOOLEAN OPERATION.'),
    'neighbors': ('Elige los vecinos y CONFIRMAR SELECCIÓN.', 'Pick neighbours and CONFIRM SELECTION.'),
    'add_implant': ('Pulsa AÑADIR IMPLANTE.', 'Press ADD IMPLANT.'),
    'place_implant': ('G mueve · R gira · revisa en MPR.', 'G moves · R rotates · review in MPR.'),
}


def _wrap_width(context):
    region = getattr(context, 'region', None)
    width = int(getattr(region, 'width', 300) or 300)
    try:
        import bpy
        scale = float(bpy.context.preferences.system.ui_scale or 1.0)
    except Exception:
        scale = 1.0
    return max(18, int(width / (7.0 * scale)) - 4)


def _state(context):
    """(stage, index0, names[], phase_key_or_None, tip_pair)."""
    from . import core
    scene = context.scene
    try:
        stage = core.infer_stage(scene)
    except Exception:
        return None
    if stage == core.STAGE_DICOM:
        order = _dicom_order(scene)
        key = _dicom_key(scene)
        base = 'load' if key == 'loading' else key
        names = [SHORT['DICOM'][k] for k in order]
        return 'DICOM', order.index(base) if base in order else 0, names, None, TIP[('DICOM', key)]
    if stage == core.STAGE_ALIGNMENT:
        key = _align_key(scene)
        names = [SHORT['ALIGNMENT'][k] for k in ALIGN_ORDER]
        return 'ALIGNMENT', ALIGN_ORDER.index(key), names, None, TIP[('ALIGNMENT', key)]
    if stage == core.STAGE_GUIDE:
        try:
            step = int(getattr(scene.dsg_props, 'current_step', 0))
        except Exception:
            step = 0
        step = max(0, min(len(SHORT['GUIDE']) - 1, step))
        phase = None
        try:
            if step == 0:
                phase = _model_phase(context)
            elif step == 1:
                phase = _implant_phase(context)
        except Exception:
            phase = None
        tip = TIP.get(phase) if phase else TIP.get(('GUIDE', step))
        if tip is None:
            tip = ('Sigue los botones de abajo.', 'Follow the buttons below.')
        return 'GUIDE', step, list(SHORT['GUIDE']), phase, tip
    return None


def draw(layout, context):
    state = _state(context)
    if not state:
        return
    scene = context.scene
    stage, index, names, phase, tip = state
    box = layout.box()

    # Progress row: done ✓ · current ● · pending ○ (like a wizard step bar).
    track = box.row(align=True)
    track.alignment = 'CENTER'
    for i in range(len(names)):
        icon = 'CHECKMARK' if i < index else ('RADIOBUT_ON' if i == index else 'RADIOBUT_OFF')
        cell = track.row(align=True)
        cell.active = i <= index
        cell.label(text='', icon=icon)

    # Current step: number + short name, then the phase (if any) and one tip.
    title = box.row(align=True)
    title.label(text=f'{index + 1} · {_t(scene, names[index])}')
    if phase in PHASE_SHORT:
        sub = box.row(align=True)
        sub.label(text=_t(scene, PHASE_SHORT[phase]), icon='RIGHTARROW_THIN')
    tip_col = box.column(align=True)
    tip_col.scale_y = 0.8
    tip_col.active = False
    text = _t(scene, tip)
    for i, line in enumerate(textwrap.wrap(text, _wrap_width(context) - 3)):
        tip_col.label(text=line, icon='INFO' if i == 0 else 'BLANK1')


def current(context):
    return _state(context)


def route_number(scene):
    import bpy
    state = _state(bpy.context)
    return None if not state else (state[0], state[1] + 1)
