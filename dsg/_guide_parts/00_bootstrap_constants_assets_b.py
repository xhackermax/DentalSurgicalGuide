ANIMATED_DRILL_PREFIX = "DSG_AnimatedFresa_"
ANIMATED_DRILL_MATERIAL = "DSG_AnimatedFresa_Mat"

# Plantilla derivada del STL aportado por el usuario. El eje longitudinal
# original Y se orientó sobre Z local: punta hacia -Z y vástago hacia +Z.
#
# Calibración clínica:
# · DRILL_TEMPLATE_GUIDE_DIAMETER representa el diámetro máximo del cilindro
#   guía que debe entrar dentro del lumen del sleeve.
# · DRILL_TEMPLATE_STOP_Z representa la pequeña superficie plana situada justo
#   DESPUÉS de ese cilindro. En el fotograma final esa superficie se apoya sobre
#   la cara oclusal del sleeve, mientras el cilindro queda introducido en él.
DRILL_TEMPLATE_SOURCE = "Hitem3d-1782319587894.stl"
DRILL_TEMPLATE_VERTS = 8996
DRILL_TEMPLATE_FACES = 17988
DRILL_TEMPLATE_GUIDE_DIAMETER = 0.13860
# El cilindro guía de esta fresa es una pieza física fija de 4,70 mm.
# No debe escalarse con el diámetro del implante ni con la holgura del sleeve.
DRILL_FIXED_GUIDE_DIAMETER_MM = 4.70
# Start real del hombro/tope inmediatamente posterior al cilindro guía.
# El valor anterior (0.10900) correspondía a la cara posterior del reborde y
# enterraba el tope dentro del sleeve aproximadamente 1 mm.
DRILL_TEMPLATE_STOP_Z = 0.07595
# Start del cilindro guía en la plantilla, justo donde termina la zona activa.
# La geometría comprendida entre este plano y DRILL_TEMPLATE_STOP_Z se remapea
# para que mida exactamente lo mismo que el sleeve de cada caso.
DRILL_TEMPLATE_GUIDE_BOTTOM_Z = -0.10600
# Extremo apical de la parte activa en la plantilla integrada.
DRILL_TEMPLATE_ACTIVE_TIP_Z = -0.50000
DRILL_STOP_CONTACT_OFFSET_MM = 0.0
_DRILL_VISUAL_TEMPLATE_CACHE = None
_DRILL_VISUAL_TEMPLATE_B85 = _load_guide_asset("drill_visual_template.b85")


# Plantilla visual de implante derivada del STL aportado por el usuario.
# La malla fue orientada con su eje principal sobre Z, normalizada a longitud 1
# y diámetro transversal 1, y reducida a 15 000 caras para mantener detalle sin
# cargar los dos millones de triángulos del STL original en cada creación.
IMPLANT_TEMPLATE_SOURCE = "Hitem3d-1782316158506(1).stl"
IMPLANT_TEMPLATE_VERTS = 7502
IMPLANT_TEMPLATE_FACES = 15000
_IMPLANT_TEMPLATE_CACHE = None
_IMPLANT_TEMPLATE_B85 = _load_guide_asset("implant_template.b85")

# Registro interno de objetos. No depende solo de punteros de Blender;
# también permite recuperar objetos por nombre fijo o por rol si el puntero se pierde.
# Shared workflow protocol: core.py is the single source of truth.
SUITE_PROTOCOL_VERSION = core.SUITE_PROTOCOL_VERSION
SUITE_LANGUAGE_KEY = core.SUITE_LANGUAGE_KEY
SUITE_STAGE_KEY = core.SUITE_STAGE_KEY
SUITE_ROLE_KEY = core.SUITE_ROLE_KEY
LEGACY_ROLE_KEY = core.LEGACY_ROLE_KEY
ROLE_DICOM_TEETH_SUITE = core.ROLE_DICOM_TEETH
ROLE_DICOM_BONE_SUITE = core.ROLE_DICOM_BONE
ROLE_IOS_SCAN_SUITE = core.ROLE_IOS_SCAN
ROLE_IOS_ALIGNED_SUITE = core.ROLE_IOS_ALIGNED
ROLE_DSG_MODEL_SUITE = core.ROLE_DSG_MODEL
ROLE_DSG_GUIDE_SUITE = core.ROLE_DSG_GUIDE

ROLE_MODEL = "model"
ROLE_BLOCKOUT = "blockout"
ROLE_BLOCKOUT_VISUAL = "blockout_visual"
ROLE_RETENTION_BOUNDARY = "retention_boundary"
ROLE_PASSIVE = "passive_blockout"
ROLE_FRAME = "frame"
ROLE_GUIDE = "guide"
ROLE_IMPLANT = "implant"
ROLE_SLEEVE = "sleeve"
ROLE_CUTTER = "cutter"
ROLE_IRRIGATION = "irrigation"
ROLE_REINFORCEMENT = "reinforcement"
ROLE_MICROSCREW = "microscrew"
ROLE_MICROSCREW_VISUAL = "microscrew_visual"
ROLE_DRILL_CUTTER = "drill_cutter"
ROLE_DRILL_VISUAL = "drill_visual"
ROLE_ENGRAVE = "engrave"
ROLE_MEASUREMENT = "dicom_measurement"

DSG_ROOT_COLLECTION_NAME = "DSG"
DSG_COLLECTION_MODEL = "01_Model_Blockout"
DSG_COLLECTION_IMPLANTS = "03_Implants_Sleeves"
DSG_COLLECTION_GUIDE = "04_Guide"
DSG_COLLECTION_IRRIGATION = "05_Irrigation"
DSG_COLLECTION_CUTTERS = "90_Cutters_Internal"

ROLE_TO_COLLECTION = {
    ROLE_MODEL: DSG_COLLECTION_MODEL,
    ROLE_BLOCKOUT: DSG_COLLECTION_MODEL,
    ROLE_BLOCKOUT_VISUAL: DSG_COLLECTION_MODEL,
    ROLE_RETENTION_BOUNDARY: DSG_COLLECTION_MODEL,
    ROLE_PASSIVE: DSG_COLLECTION_MODEL,
    ROLE_IMPLANT: DSG_COLLECTION_IMPLANTS,
    ROLE_SLEEVE: DSG_COLLECTION_IMPLANTS,
    ROLE_FRAME: DSG_COLLECTION_GUIDE,
    ROLE_GUIDE: DSG_COLLECTION_GUIDE,
    ROLE_IRRIGATION: DSG_COLLECTION_IRRIGATION,
    ROLE_REINFORCEMENT: DSG_COLLECTION_GUIDE,
    ROLE_MICROSCREW: DSG_COLLECTION_GUIDE,
    ROLE_MICROSCREW_VISUAL: DSG_COLLECTION_IMPLANTS,
    ROLE_CUTTER: DSG_COLLECTION_CUTTERS,
    ROLE_DRILL_CUTTER: DSG_COLLECTION_CUTTERS,
    ROLE_DRILL_VISUAL: DSG_COLLECTION_IMPLANTS,
    ROLE_ENGRAVE: DSG_COLLECTION_GUIDE,
    ROLE_MEASUREMENT: DSG_COLLECTION_IMPLANTS,
}

# Flujo clínico de 10 pasos. Primero se captura el eje de inserción y se
# prepara el modelo retentivo. La planificación implantaria ocupa el paso 2,
# de modo que los controles de emergencia parten de una orientación clínica
# ya definida. El contorno permanece en el paso 3 y los pasos 4-10 conservan
# sus índices históricos para no alterar frame, cilindros, irrigación ni animación.
