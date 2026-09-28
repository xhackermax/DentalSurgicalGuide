from __future__ import annotations

import logging as _dsg_logging
_DSG_LOG = _dsg_logging.getLogger(__name__)

import json
import os
import threading
import time
from pathlib import Path

from .version import DSG_VERSION_STR

import bpy
import bmesh
from bpy.app.handlers import persistent
from . import icon_manager
from . import ui_style
from bpy.props import BoolProperty, EnumProperty, PointerProperty, StringProperty
from bpy.types import Operator, Panel, PropertyGroup
from mathutils import Vector

SUITE_PROTOCOL_VERSION = 2
SUITE_LANGUAGE_KEY = "dental_suite_language"
SUITE_STAGE_KEY = "dental_suite_stage"
SUITE_ROLE_KEY = "dental_suite_role"
LEGACY_ROLE_KEY = "dental_role"
TOOTH_ANALYSIS_COMPLETED_KEY = "DSG_tooth_analysis_completed"
WORKFLOW_ROUTE_KEY = "DSG_clinical_route"
TARGET_FDI_KEY = "DSG_target_fdi"
ROUTE_SIMPLE = "SIMPLE"
ROUTE_IMMEDIATE = "IMMEDIATE"
VALID_ROUTES = {ROUTE_SIMPLE, ROUTE_IMMEDIATE}

# v9.2.71: hard re-entrancy + fresh-CBCT gate for expensive route launches.
# A stale runtime verification from a previous patient must NEVER arm these buttons.
_SIMPLE_ROUTE_EXECUTING = False
_IMMEDIATE_ROUTE_EXECUTING = False
IMMEDIATE_GATE_READY_AT_KEY = "DSG_immediate_gate_cbct_ready_at"
IMMEDIATE_GATE_ARMED_KEY = "DSG_immediate_gate_armed"
IMMEDIATE_GATE_MIN_IDLE_S = 1.25
PATIENT_FOLDER_KEY = "DSG_patient_folder"
ROUTE_STEP_KEY = "DSG_route_step"
IMMEDIATE_FDIS_KEY = "DSG_immediate_extraction_fdis_json"

STAGE_DICOM = "DICOM"
STAGE_ALIGNMENT = "ALIGNMENT"
STAGE_GUIDE = "DSG"
VALID_STAGES = {STAGE_DICOM, STAGE_ALIGNMENT, STAGE_GUIDE}

ROLE_DICOM_TEETH = "DICOM_TEETH"
ROLE_DICOM_BONE = "DICOM_BONE"
ROLE_DICOM_MANDIBULAR_CANAL = "DICOM_MANDIBULAR_CANAL"
ROLE_DICOM_ALIGNMENT_COMPOSITE = "DICOM_ALIGNMENT_COMPOSITE"
ROLE_IOS_SCAN = "IOS_SCAN"
ROLE_IOS_ALIGNED = "IOS_ALIGNED"
ROLE_IOS_ANTAGONIST = "IOS_ANTAGONIST"
ROLE_DSG_MODEL = "DSG_MODEL"
ROLE_DSG_GUIDE = "DSG_GUIDE"



DICOM_COLLECTION_PREFIXES = (
    "DICOM_WIZARD_PRO",
    "DICOM_RADIOGRAPHIC_DISPLAYS",
)


def _is_dicom_collection(collection) -> bool:
    name = str(getattr(collection, "name", ""))
    return any(name.startswith(prefix) for prefix in DICOM_COLLECTION_PREFIXES)


def _walk_layer_collections(layer_collection):
    yield layer_collection
    for child in getattr(layer_collection, "children", ()):
        yield from _walk_layer_collections(child)


def set_dicom_collections_hidden(context, hidden: bool) -> None:
    """Hide/reveal complete DICOM collections and their view-layer nodes."""
    context = context or bpy.context
    try:
        collections = [c for c in bpy.data.collections if _is_dicom_collection(c)]
    except Exception:
        collections = []
    for collection in collections:
        try:
            collection.hide_viewport = bool(hidden)
            collection.hide_render = bool(hidden)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    names = {c.name for c in collections}
    try:
        view_layers = list(context.scene.view_layers)
    except Exception:
        view_layers = []
    for view_layer in view_layers:
        root_layer = getattr(view_layer, "layer_collection", None)
        if root_layer is None:
            continue
        for layer_collection in _walk_layer_collections(root_layer):
            if getattr(layer_collection, "name", "") in names:
                try:
                    layer_collection.hide_viewport = bool(hidden)
                except Exception:
                    _DSG_LOG.debug("suppressed exception", exc_info=True)


CANONICAL_NAMES = {
    ROLE_DICOM_TEETH: "Dental_DICOM_Teeth",
    ROLE_DICOM_BONE: "Dental_DICOM_Bone",
    ROLE_DICOM_MANDIBULAR_CANAL: "Dental_DICOM_MandibularCanal",
    ROLE_DICOM_ALIGNMENT_COMPOSITE: "Dental_DICOM_AlignmentComposite",
    ROLE_IOS_SCAN: "Dental_IOS",
    ROLE_IOS_ALIGNED: "Dental_IOS_Aligned",
    ROLE_DSG_GUIDE: "DSG_Guide",
}


LANGUAGE_ITEMS = (
    ("ES", "Español", "Interfaz en español"),
    ("EN", "English", "English interface"),
    ("FR", "Français", "Interface française"),
    ("ZH", "中文", "中文界面"),
    ("AR", "العربية", "واجهة عربية"),
    ("DE", "Deutsch", "Deutsche Benutzeroberfläche"),
    ("PT", "Português (Brasil)", "Interface em português brasileiro"),
    ("HI", "हिन्दी", "हिन्दी इंटरफ़ेस"),
)

# The workflow labels below are intentionally short because they appear in the
# narrow Blender sidebar. Remaining technical/clinical detail falls back to
# English rather than risking an unsafe mistranslation.
_CORE_UI_TRANSLATIONS = {
    "FR": {"BACK": "RETOUR", "NEXT": "SUIVANT", "CHANGE ROUTE": "CHANGER LE FLUX", "CHANGE PATIENT": "CHANGER LE PATIENT", "INSTALL ENGINES": "INSTALLER LES MOTEURS", "IMMEDIATE IMPLANT": "IMPLANT IMMÉDIAT", "SIMPLE IMPLANT": "IMPLANT SIMPLE", "ALIGN": "ALIGNER", "CONFIRM": "CONFIRMER"},
    "ZH": {"BACK": "返回", "NEXT": "下一步", "CHANGE ROUTE": "更改流程", "CHANGE PATIENT": "更换患者", "INSTALL ENGINES": "安装引擎", "IMMEDIATE IMPLANT": "即刻种植", "SIMPLE IMPLANT": "常规种植", "ALIGN": "对齐", "CONFIRM": "确认"},
    "AR": {"BACK": "رجوع", "NEXT": "التالي", "CHANGE ROUTE": "تغيير المسار", "CHANGE PATIENT": "تغيير المريض", "INSTALL ENGINES": "تثبيت المحركات", "IMMEDIATE IMPLANT": "زرع فوري", "SIMPLE IMPLANT": "زرع بسيط", "ALIGN": "محاذاة", "CONFIRM": "تأكيد"},
    "DE": {"BACK": "ZURÜCK", "NEXT": "WEITER", "CHANGE ROUTE": "ABLAUF ÄNDERN", "CHANGE PATIENT": "PATIENT ÄNDERN", "INSTALL ENGINES": "MODULE INSTALLIEREN", "IMMEDIATE IMPLANT": "SOFORTIMPLANTAT", "SIMPLE IMPLANT": "EINFACHES IMPLANTAT", "ALIGN": "AUSRICHTEN", "CONFIRM": "BESTÄTIGEN"},
    "PT": {"BACK": "VOLTAR", "NEXT": "PRÓXIMO", "CHANGE ROUTE": "ALTERAR FLUXO", "CHANGE PATIENT": "ALTERAR PACIENTE", "INSTALL ENGINES": "INSTALAR MOTORES", "INSTALLING ENGINES…": "INSTALANDO MOTORES…", "REPAIR ENGINES": "REPARAR MOTORES", "ENGINES ✓": "MOTORES ✓", "CHOOSE PATIENT": "ESCOLHER PACIENTE", "LOAD CBCT": "CARREGAR CBCT", "OPENING CBCT…": "ABRINDO CBCT…", "IMMEDIATE IMPLANT": "IMPLANTE IMEDIATO", "SIMPLE IMPLANT": "IMPLANTE SIMPLES", "SEGMENTING…": "SEGMENTANDO…", "FDI CORRECT": "FDI CORRETO", "SWAP FDI ARCHES": "INVERTER ARCOS FDI", "CREATE ALVEOLI": "CRIAR ALVÉOLOS", "CONFIRM + ALIGN": "CONFIRMAR + ALINHAR", "CHANGE EXTRACTIONS": "ALTERAR EXTRAÇÕES", "DETECT COMMON SURFACE": "DETECTAR SUPERFÍCIE COMUM", "CONFIRM IOS POST-EXTRACTION": "CONFIRMAR IOS PÓS-EXTRAÇÃO", "RESTORE ORIGINAL IOS": "RESTAURAR IOS ORIGINAL", "REVISE IOS SELECTION": "REVISAR SELEÇÃO IOS", "ALIGN": "ALINHAR", "CONFIRM": "CONFIRMAR"},
    "HI": {"BACK": "वापस", "NEXT": "आगे", "CHANGE ROUTE": "मार्ग बदलें", "CHANGE PATIENT": "रोगी बदलें", "INSTALL ENGINES": "इंजन स्थापित करें", "IMMEDIATE IMPLANT": "तत्काल इम्प्लांट", "SIMPLE IMPLANT": "सरल इम्प्लांट", "ALIGN": "संरेखित करें", "CONFIRM": "पुष्टि करें"},
}

# Button catalogue shared by DICOM, Alignment and Guide.  Calls that already
# supply English/Spanish text now resolve here for every supported language.
# Long phrases precede their constituent words so dynamic labels remain clear.
_WORKFLOW_BUTTON_TRANSLATIONS = {
    "FR": {"IMPORT IOS": "IMPORTER IOS", "USE SELECTED IOS": "UTILISER IOS SÉLECTIONNÉ", "MARK 3 ZONES": "MARQUER 3 ZONES", "MARK ZONES AGAIN": "MARQUER À NOUVEAU", "ALIGN MODELS": "ALIGNER LES MODÈLES", "CHANGE IOS": "CHANGER IOS", "OPEN DICOM": "OUVRIR DICOM", "EXIT MPR": "QUITTER MPR", "FULL SEGMENTATION · 2 ENGINES": "SEGMENTATION COMPLÈTE · 2 MOTEURS", "CONTINUE TO ALIGNMENT": "CONTINUER VERS L’ALIGNEMENT", "CLOSE SAFE HOLES": "FERMER LES TROUS SÛRS", "GENERATE CLOSED MODEL": "GÉNÉRER LE MODÈLE FERMÉ", "USE CLOSED MODEL AND CONTINUE": "UTILISER LE MODÈLE FERMÉ", "ADD IMPLANT": "AJOUTER UN IMPLANT", "DELETE LAST IMPLANT": "SUPPRIMER LE DERNIER IMPLANT", "CREATE DRILL CHANNELS": "CRÉER LES CANAUX DE FORAGE", "APPLY IRRIGATION": "APPLIQUER L’IRRIGATION", "CONTINUE WITHOUT IRRIGATION": "CONTINUER SANS IRRIGATION", "APPLY AND CONTINUE": "APPLIQUER ET CONTINUER", "FINISH GUIDE": "TERMINER LE GUIDE", "EXPORT STL": "EXPORTER STL", "BACK": "RETOUR", "CONTINUE": "CONTINUER", "REVIEW": "VÉRIFIER", "DETECT": "DÉTECTER", "LOAD": "CHARGER", "SELECT": "SÉLECTIONNER", "CREATE": "CRÉER", "UPDATE": "METTRE À JOUR", "DELETE": "SUPPRIMER", "PREVIEW": "APERÇU"},
    "ZH": {"IMPORT IOS": "导入 IOS", "USE SELECTED IOS": "使用所选 IOS", "MARK 3 ZONES": "标记 3 个区域", "MARK ZONES AGAIN": "重新标记区域", "ALIGN MODELS": "对齐模型", "CHANGE IOS": "更换 IOS", "OPEN DICOM": "打开 DICOM", "EXIT MPR": "退出 MPR", "FULL SEGMENTATION · 2 ENGINES": "完整分割 · 2 个引擎", "CONTINUE TO ALIGNMENT": "继续到对齐", "CLOSE SAFE HOLES": "关闭安全孔洞", "GENERATE CLOSED MODEL": "生成封闭模型", "USE CLOSED MODEL AND CONTINUE": "使用封闭模型并继续", "ADD IMPLANT": "添加种植体", "DELETE LAST IMPLANT": "删除最后的种植体", "CREATE DRILL CHANNELS": "创建钻孔通道", "APPLY IRRIGATION": "应用冲洗", "CONTINUE WITHOUT IRRIGATION": "无冲洗继续", "APPLY AND CONTINUE": "应用并继续", "FINISH GUIDE": "完成导板", "EXPORT STL": "导出 STL", "BACK": "返回", "CONTINUE": "继续", "REVIEW": "复核", "DETECT": "检测", "LOAD": "加载", "SELECT": "选择", "CREATE": "创建", "UPDATE": "更新", "DELETE": "删除", "PREVIEW": "预览"},
    "AR": {"IMPORT IOS": "استيراد IOS", "USE SELECTED IOS": "استخدام IOS المحدد", "MARK 3 ZONES": "تحديد 3 مناطق", "MARK ZONES AGAIN": "تحديد المناطق مجدداً", "ALIGN MODELS": "محاذاة النماذج", "CHANGE IOS": "تغيير IOS", "OPEN DICOM": "فتح DICOM", "EXIT MPR": "الخروج من MPR", "FULL SEGMENTATION · 2 ENGINES": "تجزئة كاملة · محركان", "CONTINUE TO ALIGNMENT": "المتابعة إلى المحاذاة", "CLOSE SAFE HOLES": "إغلاق الثقوب الآمنة", "GENERATE CLOSED MODEL": "إنشاء نموذج مغلق", "USE CLOSED MODEL AND CONTINUE": "استخدام النموذج المغلق والمتابعة", "ADD IMPLANT": "إضافة زرعة", "DELETE LAST IMPLANT": "حذف آخر زرعة", "CREATE DRILL CHANNELS": "إنشاء قنوات الحفر", "APPLY IRRIGATION": "تطبيق الري", "CONTINUE WITHOUT IRRIGATION": "المتابعة دون ري", "APPLY AND CONTINUE": "تطبيق ومتابعة", "FINISH GUIDE": "إنهاء الدليل", "EXPORT STL": "تصدير STL", "BACK": "رجوع", "CONTINUE": "متابعة", "REVIEW": "مراجعة", "DETECT": "كشف", "LOAD": "تحميل", "SELECT": "اختيار", "CREATE": "إنشاء", "UPDATE": "تحديث", "DELETE": "حذف", "PREVIEW": "معاينة"},
    "DE": {"IMPORT IOS": "IOS IMPORTIEREN", "USE SELECTED IOS": "AUSGEWÄHLTES IOS VERWENDEN", "MARK 3 ZONES": "3 ZONEN MARKIEREN", "MARK ZONES AGAIN": "ZONEN ERNEUT MARKIEREN", "ALIGN MODELS": "MODELLE AUSRICHTEN", "CHANGE IOS": "IOS ÄNDERN", "OPEN DICOM": "DICOM ÖFFNEN", "EXIT MPR": "MPR SCHLIESSEN", "FULL SEGMENTATION · 2 ENGINES": "VOLLE SEGMENTIERUNG · 2 MODULE", "CONTINUE TO ALIGNMENT": "WEITER ZUR AUSRICHTUNG", "CLOSE SAFE HOLES": "SICHERE LÖCHER SCHLIESSEN", "GENERATE CLOSED MODEL": "GESCHLOSSENES MODELL ERZEUGEN", "USE CLOSED MODEL AND CONTINUE": "GESCHLOSSENES MODELL VERWENDEN", "ADD IMPLANT": "IMPLANTAT HINZUFÜGEN", "DELETE LAST IMPLANT": "LETZTES IMPLANTAT LÖSCHEN", "CREATE DRILL CHANNELS": "BOHRKANÄLE ERZEUGEN", "APPLY IRRIGATION": "SPÜLUNG ANWENDEN", "CONTINUE WITHOUT IRRIGATION": "OHNE SPÜLUNG WEITER", "APPLY AND CONTINUE": "ANWENDEN UND WEITER", "FINISH GUIDE": "SCHABLONE FERTIGSTELLEN", "EXPORT STL": "STL EXPORTIEREN", "BACK": "ZURÜCK", "CONTINUE": "WEITER", "REVIEW": "PRÜFEN", "DETECT": "ERKENNEN", "LOAD": "LADEN", "SELECT": "AUSWÄHLEN", "CREATE": "ERSTELLEN", "UPDATE": "AKTUALISIEREN", "DELETE": "LÖSCHEN", "PREVIEW": "VORSCHAU"},
    "PT": {"IMPORT IOS": "IMPORTAR IOS", "USE SELECTED IOS": "USAR IOS SELECIONADO", "MARK 3 ZONES": "MARCAR 3 ZONAS", "MARK ZONES AGAIN": "MARCAR ZONAS NOVAMENTE", "ALIGN MODELS": "ALINHAR MODELOS", "CHANGE IOS": "ALTERAR IOS", "OPEN DICOM": "ABRIR DICOM", "EXIT MPR": "SAIR DO MPR", "FULL SEGMENTATION · 2 ENGINES": "SEGMENTAÇÃO COMPLETA · 2 MOTORES", "CONTINUE TO ALIGNMENT": "CONTINUAR PARA ALINHAMENTO", "CLOSE SAFE HOLES": "FECHAR FUROS SEGUROS", "GENERATE CLOSED MODEL": "GERAR MODELO FECHADO", "USE CLOSED MODEL AND CONTINUE": "USAR MODELO FECHADO E CONTINUAR", "ADD IMPLANT": "ADICIONAR IMPLANTE", "DELETE LAST IMPLANT": "EXCLUIR ÚLTIMO IMPLANTE", "CREATE DRILL CHANNELS": "CRIAR CANAIS DE FRESAGEM", "APPLY IRRIGATION": "APLICAR IRRIGAÇÃO", "CONTINUE WITHOUT IRRIGATION": "CONTINUAR SEM IRRIGAÇÃO", "APPLY AND CONTINUE": "APLICAR E CONTINUAR", "FINISH GUIDE": "FINALIZAR GUIA", "EXPORT STL": "EXPORTAR STL", "BACK": "VOLTAR", "CONTINUE": "CONTINUAR", "REVIEW": "REVISAR", "DETECT": "DETECTAR", "LOAD": "CARREGAR", "SELECT": "SELECIONAR", "CREATE": "CRIAR", "UPDATE": "ATUALIZAR", "DELETE": "EXCLUIR", "PREVIEW": "PRÉ-VISUALIZAR"},
    "HI": {"IMPORT IOS": "IOS आयात करें", "USE SELECTED IOS": "चयनित IOS उपयोग करें", "MARK 3 ZONES": "3 क्षेत्र चिह्नित करें", "MARK ZONES AGAIN": "क्षेत्र फिर चिह्नित करें", "ALIGN MODELS": "मॉडल संरेखित करें", "CHANGE IOS": "IOS बदलें", "OPEN DICOM": "DICOM खोलें", "EXIT MPR": "MPR से बाहर निकलें", "FULL SEGMENTATION · 2 ENGINES": "पूर्ण सेगमेंटेशन · 2 इंजन", "CONTINUE TO ALIGNMENT": "संरेखण जारी रखें", "CLOSE SAFE HOLES": "सुरक्षित छेद बंद करें", "GENERATE CLOSED MODEL": "बंद मॉडल बनाएँ", "USE CLOSED MODEL AND CONTINUE": "बंद मॉडल उपयोग करें", "ADD IMPLANT": "इम्प्लांट जोड़ें", "DELETE LAST IMPLANT": "अंतिम इम्प्लांट हटाएँ", "CREATE DRILL CHANNELS": "ड्रिल चैनल बनाएँ", "APPLY IRRIGATION": "सिंचाई लागू करें", "CONTINUE WITHOUT IRRIGATION": "सिंचाई के बिना जारी रखें", "APPLY AND CONTINUE": "लागू करें और आगे बढ़ें", "FINISH GUIDE": "गाइड समाप्त करें", "EXPORT STL": "STL निर्यात करें", "BACK": "वापस", "CONTINUE": "आगे", "REVIEW": "समीक्षा", "DETECT": "पहचानें", "LOAD": "लोड करें", "SELECT": "चुनें", "CREATE": "बनाएँ", "UPDATE": "अपडेट", "DELETE": "हटाएँ", "PREVIEW": "पूर्वावलोकन"},
}


def language_code(scene=None) -> str:
    scene = scene or getattr(bpy.context, "scene", None)
    value = str(scene.get(SUITE_LANGUAGE_KEY, "ES") if scene else "ES").upper()
    return value if value in {item[0] for item in LANGUAGE_ITEMS} else "ES"


def is_spanish(scene=None) -> bool:
    return language_code(scene) == "ES"


def tr(scene, english: str, spanish: str) -> str:
    code = language_code(scene)
    if code == "ES":
        return spanish
    return translate_ui(scene, english, spanish)


def translate_ui(scene, english: str, spanish: str | None = None) -> str:
    """Translate shared UI labels; Spanish remains the complete source locale."""
    code = language_code(scene)
    if code == "ES":
        return spanish if spanish is not None else english
    if code == "EN":
        return english
    exact = _CORE_UI_TRANSLATIONS.get(code, {}).get(english)
    if exact:
        return exact
    catalogue = _WORKFLOW_BUTTON_TRANSLATIONS.get(code, {})
    if english in catalogue:
        return catalogue[english]
    # Composite controls (for example "CREATE DRILL CHANNELS") are often
    # assembled dynamically. Translate every known longest phrase so those
    # controls never silently fall back to an entirely English label.
    translated = english
    for source, target in sorted(catalogue.items(), key=lambda item: len(item[0]), reverse=True):
        if source in translated:
            translated = translated.replace(source, target)
    return translated


def role_of(obj) -> str:
    if obj is None:
        return ""
    return str(obj.get(SUITE_ROLE_KEY, obj.get(LEGACY_ROLE_KEY, ""))).upper()


def set_role(obj, role: str, *, rename: bool = False) -> None:
    if obj is None:
        return
    obj[SUITE_ROLE_KEY] = role
    obj[LEGACY_ROLE_KEY] = role
    obj["dental_suite_protocol"] = SUITE_PROTOCOL_VERSION
    if rename and role in CANONICAL_NAMES:
        obj.name = CANONICAL_NAMES[role]


def find_role(role: str):
    wanted = str(role).upper()
    matches = [obj for obj in bpy.data.objects if getattr(obj, "type", None) == "MESH" and role_of(obj) == wanted]
    if not matches:
        return None
    visible = [obj for obj in matches if not obj.hide_get() and not obj.hide_viewport]
    return (visible or matches)[-1]


def antagonist_objects(source=None) -> list:
    """Return persistent opposing-arch meshes, never inferred from visibility."""
    result = [
        obj for obj in bpy.data.objects
        if getattr(obj, "type", None) == "MESH" and role_of(obj) == ROLE_IOS_ANTAGONIST
        and obj != source
    ]
    return result


def bind_antagonists_to_source(source) -> list:
    """Parent the antagonist to the moving IOS while preserving world pose."""
    if source is None or getattr(source, "type", None) != "MESH":
        return []
    bound = []
    for antagonist in antagonist_objects(source):
        try:
            world = antagonist.matrix_world.copy()
            antagonist.parent = source
            antagonist.matrix_world = world
            antagonist["DSG_antagonist_follows_ios"] = True
            antagonist["DSG_antagonist_source"] = str(source.name)
            bound.append(antagonist)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    return bound


def find_alignment_reference(scene=None):
    props = getattr(scene, "dicp_props", None) if scene is not None else None
    current = getattr(props, "icp_target_obj", None) if props is not None else None
    if current is not None and getattr(current, "type", None) == "MESH" and len(current.data.vertices) >= 3:
        return current
    explicit = [
        obj for obj in bpy.data.objects
        if getattr(obj, "type", None) == "MESH"
        and bool(obj.get("dental_suite_alignment_reference", False))
    ]
    if explicit:
        return explicit[-1]
    return find_role(ROLE_DICOM_ALIGNMENT_COMPOSITE) or find_role(ROLE_DICOM_TEETH) or find_role(ROLE_DICOM_BONE)


def infer_stage(scene) -> str:
    stored = str(scene.get(SUITE_STAGE_KEY, "")).upper()
    if stored in VALID_STAGES:
        return stored
    if find_role(ROLE_DSG_GUIDE) is not None or find_role(ROLE_IOS_ALIGNED) is not None:
        return STAGE_GUIDE
    if find_alignment_reference(scene) is not None:
        return STAGE_ALIGNMENT
    return STAGE_DICOM


def _workflow_mesh(scene, scene_key: str):
    """Return a live mesh referenced by a workflow Scene key, if any."""
    try:
        name = str(scene.get(scene_key, "") or "")
        obj = bpy.data.objects.get(name) if name else None
        return obj if obj is not None and obj.type == "MESH" else None
    except Exception:
        return None


def reconcile_workflow_after_undo(scene=None) -> None:
    """Repair only stale route pointers after Blender restores an undo snapshot.

    Scene custom properties, geometry and pointer properties normally undo
    together.  Older DSG transitions did not all create an undo step, though,
    so Ctrl+Z could restore a mesh while leaving ``DSG_route_step`` ahead of
    it.  This is intentionally conservative: it never advances a workflow or
    recreates clinical geometry; it merely returns an impossible screen to the
    last existing clinical state.
    """
    scene = scene or getattr(bpy.context, "scene", None)
    if scene is None:
        return
    try:
        route = clinical_route(scene)
        step = str(scene.get(ROUTE_STEP_KEY, "") or "")
    except Exception:
        return

    if route == ROUTE_SIMPLE:
        if step in {"SIMPLE_SEGMENTING", "SIMPLE_REVIEW", "ALIGNMENT"}:
            upper = bpy.data.objects.get(str(scene.get("DSG_simple_upper_object", "") or ""))
            lower = bpy.data.objects.get(str(scene.get("DSG_simple_lower_object", "") or ""))
            if upper is None or lower is None:
                scene[ROUTE_STEP_KEY] = "CBCT_READY"
                set_stage(scene, STAGE_DICOM)
        return
    if route != ROUTE_IMMEDIATE:
        return

    try:
        from . import cbct_dental_module
        teeth = list(cbct_dental_module.dentition_objects())
    except Exception:
        teeth = []

    upper = _workflow_mesh(scene, "DSG_immediate_upper_composite")
    lower = _workflow_mesh(scene, "DSG_immediate_lower_composite")
    has_arch_review = upper is not None or lower is not None
    hidden_teeth = False
    for tooth in teeth:
        try:
            hidden_teeth = hidden_teeth or bool(tooth.hide_viewport) or bool(tooth.hide_get())
        except Exception:
            hidden_teeth = hidden_teeth or bool(getattr(tooth, "hide_viewport", False))

    if step in {"IMMEDIATE_ARCH_REVIEW", "ALIGNMENT", "IMMEDIATE_IOS_SURFACE_REVIEW", "IMMEDIATE_IOS_POSTEXTRACTION_READY"} and not has_arch_review:
        # The model that made the later stage possible was undone/deleted.
        # Return to either the selected-extraction screen or FDI review.
        scene[ROUTE_STEP_KEY] = "IMMEDIATE_SELECT_TEETH" if hidden_teeth else "IMMEDIATE_FDI_REVIEW"
        set_stage(scene, STAGE_DICOM)
    elif step == "IMMEDIATE_SELECT_TEETH" and not teeth:
        # A segmentation undo cannot leave the selection screen operational.
        scene[ROUTE_STEP_KEY] = "CBCT_READY"
        set_stage(scene, STAGE_DICOM)


_WORKFLOW_UNDO_REPAIR_PENDING = False


def _run_workflow_undo_repair():
    global _WORKFLOW_UNDO_REPAIR_PENDING
    _WORKFLOW_UNDO_REPAIR_PENDING = False
    try:
        reconcile_workflow_after_undo()
    except Exception as exc:
        print(f"[DSG Workflow] undo reconciliation warning: {exc}")
    return None


@persistent
def dsg_workflow_undo_post(*_args) -> None:
    """Defer route reconciliation until Blender has finished swapping undo data."""
    global _WORKFLOW_UNDO_REPAIR_PENDING
    if _WORKFLOW_UNDO_REPAIR_PENDING:
        return
    _WORKFLOW_UNDO_REPAIR_PENDING = True
    try:
        bpy.app.timers.register(_run_workflow_undo_repair, first_interval=0.12)
    except Exception:
        _WORKFLOW_UNDO_REPAIR_PENDING = False
        _run_workflow_undo_repair()


def _register_workflow_undo_handler() -> None:
    _unregister_workflow_undo_handler()
    bpy.app.handlers.undo_post.append(dsg_workflow_undo_post)
    bpy.app.handlers.redo_post.append(dsg_workflow_undo_post)


def _unregister_workflow_undo_handler() -> None:
    for handlers in (bpy.app.handlers.undo_post, bpy.app.handlers.redo_post):
        for handler in list(handlers):
            if getattr(handler, "__name__", "") == "dsg_workflow_undo_post":
                try:
                    handlers.remove(handler)
                except ValueError:
                    pass


def _is_dicom_related_object(obj) -> bool:
    if obj is None:
        return False
    role = role_of(obj)
    name = str(getattr(obj, "name", ""))
    if role in {
        ROLE_DICOM_TEETH,
        ROLE_DICOM_BONE,
        ROLE_DICOM_MANDIBULAR_CANAL,
        ROLE_DICOM_ALIGNMENT_COMPOSITE,
    }:
        return True
    if name.startswith(("DICOM_", "SEG_", "STL_Dientes", "STL_Hueso", "Dental_DICOM_", "DICP_LM_")):
        return True
    for collection in getattr(obj, "users_collection", ()):
        if str(collection.name).startswith(("DICOM", "DICP_Landmarks")):
            return True
    return False


def prepare_guide_entry_view(context, ios=None) -> None:
    context = context or bpy.context
    scene = getattr(context, "scene", None)
    if scene is None:
        return
    set_dicom_collections_hidden(context, True)
    ios = ios or find_role(ROLE_IOS_ALIGNED)
    for obj in list(scene.objects):
        try:
            if obj == ios:
                obj.hide_viewport = False
                obj.hide_set(False)
                obj.hide_select = False
                if hasattr(obj, "display_type"):
                    obj.display_type = "SOLID"
            elif _is_dicom_related_object(obj):
                obj.hide_viewport = True
                obj.hide_set(True)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    if ios is not None:
        try:
            bpy.ops.object.select_all(action="DESELECT")
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        try:
            ios.select_set(True)
            context.view_layer.objects.active = ios
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    try:
        windows = list(context.window_manager.windows)
    except Exception:
        windows = []
    for window in windows:
        screen = getattr(window, "screen", None)
        if screen is None:
            continue
        for area in screen.areas:
            if area.type != "VIEW_3D":
                continue
            try:
                space = area.spaces.active
                space.shading.type = "SOLID"
                space.shading.color_type = "MATERIAL"
                space.shading.light = "STUDIO"
                area.tag_redraw()
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)


def set_stage(scene, stage: str) -> None:
    stage = str(stage).upper()
    if stage not in VALID_STAGES:
        stage = STAGE_DICOM
    scene[SUITE_STAGE_KEY] = stage

    # Shared handoff pointers. Roles remain the durable fallback when scenes are reopened.
    if stage == STAGE_ALIGNMENT:
        props = getattr(scene, "dicp_props", None)
        reference = find_alignment_reference(scene)
        if props is not None and reference is not None:
            props.icp_target_obj = reference
    elif stage == STAGE_GUIDE:
        props = getattr(scene, "dsg_props", None)
        ios = find_role(ROLE_IOS_ALIGNED)
        if props is not None and ios is not None and hasattr(props, "model_obj"):
            props.model_obj = ios


def stage_is(context, stage: str) -> bool:
    scene = getattr(context, "scene", None)
    return scene is not None and infer_stage(scene) == stage


def language_get(self):
    scene = getattr(self, "id_data", None)
    code = language_code(scene)
    return next((index for index, item in enumerate(LANGUAGE_ITEMS) if item[0] == code), 0)


def language_set(self, value):
    scene = getattr(self, "id_data", None)
    if scene is not None:
        try:
            code = LANGUAGE_ITEMS[int(value)][0]
        except Exception:
            code = str(value).upper()
        scene[SUITE_LANGUAGE_KEY] = code if code in {item[0] for item in LANGUAGE_ITEMS} else "ES"


def clinical_route(scene=None) -> str:
    scene = scene or getattr(bpy.context, "scene", None)
    if scene is None:
        return ROUTE_SIMPLE
    settings = getattr(scene, "dsg_suite_settings", None)
    value = str(getattr(settings, "workflow_route", "") or scene.get(WORKFLOW_ROUTE_KEY, ROUTE_SIMPLE)).upper()
    return value if value in VALID_ROUTES else ROUTE_SIMPLE


def target_fdi(scene=None) -> int:
    scene = scene or getattr(bpy.context, "scene", None)
    if scene is None:
        return 11
    settings = getattr(scene, "dsg_suite_settings", None)
    raw = getattr(settings, "target_fdi", "") if settings is not None else ""
    if not raw:
        raw = scene.get(TARGET_FDI_KEY, 11)
    try:
        value = int(raw)
    except Exception:
        value = 11
    return value


def route_requires_individual_teeth(scene=None) -> bool:
    return clinical_route(scene) == ROUTE_IMMEDIATE


def _restore_virtual_extraction_if_needed(scene) -> None:
    if scene is None:
        return
    if not (bool(scene.get("DSG_immediate_extraction_prepared", False)) or str(scene.get("DSG_immediate_extraction_tooth", "") or "")):
        return
    try:
        from . import guide_module
        restore = getattr(guide_module, "restore_immediate_extraction", None)
        if callable(restore):
            restore(scene)
            return
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    # Minimal fallback for early module initialization/reload.
    name = str(scene.get("DSG_immediate_extraction_tooth", "") or "")
    obj = bpy.data.objects.get(name) if name else None
    if obj is not None:
        try:
            obj.hide_viewport = bool(obj.get("DSG_virtual_extraction_prev_hide_viewport", False))
            obj.hide_render = bool(obj.get("DSG_virtual_extraction_prev_hide_render", False))
            obj.hide_select = bool(obj.get("DSG_virtual_extraction_prev_hide_select", False))
            try:
                obj.hide_set(bool(obj.hide_viewport))
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
            obj["DSG_virtual_extraction"] = False
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    scene["DSG_immediate_extraction_prepared"] = False
    scene["DSG_immediate_extraction_tooth"] = ""
    scene["DSG_immediate_extraction_fdi"] = 0


def _workflow_route_update(self, context):
    scene = getattr(self, "id_data", None) or getattr(context, "scene", None)
    if scene is None:
        return
    _restore_virtual_extraction_if_needed(scene)
    route = str(getattr(self, "workflow_route", ROUTE_SIMPLE) or ROUTE_SIMPLE).upper()
    if route not in VALID_ROUTES:
        route = ROUTE_SIMPLE
    scene[WORKFLOW_ROUTE_KEY] = route
    scene["DSG_restoration_scenario"] = (
        "IMMEDIATE_EXTRACTION" if route == ROUTE_IMMEDIATE else "HEALED_SITE"
    )
    # Changing the clinical route invalidates only route-specific review state;
    # already generated DICOM/IOS geometry is intentionally preserved.
    scene["DSG_immediate_extraction_prepared"] = False
    scene["DSG_route_review_required"] = True


def _target_fdi_update(self, context):
    scene = getattr(self, "id_data", None) or getattr(context, "scene", None)
    if scene is None:
        return
    _restore_virtual_extraction_if_needed(scene)
    try:
        value = int(getattr(self, "target_fdi", "11"))
    except Exception:
        value = 11
    scene[TARGET_FDI_KEY] = value
    scene["DSG_immediate_extraction_prepared"] = False
    scene["DSG_route_review_required"] = True


# Backward-compatible aliases for modules/scripts that used the private names.
_language_get = language_get
_language_set = language_set


class DSGSuiteSettings(PropertyGroup):
    language: EnumProperty(
        name="Idioma",
        items=LANGUAGE_ITEMS,
        get=language_get,
        set=language_set,
    )
    case_name: StringProperty(name="Case / Caso", default="")
    patient_folder: StringProperty(
        name="Carpeta del paciente",
        description="Carpeta maestra del caso. DSG busca aquí CBCT e IOS y la reutiliza para exportaciones",
        subtype="DIR_PATH",
        default="",
    )
    workflow_route: EnumProperty(
        name="Ruta clínica",
        description="Elige el flujo antes de segmentar: sitio cicatrizado o implante inmediato postextracción",
        items=(
            (ROUTE_SIMPLE, "Implante simple", "Sitio cicatrizado/ausente: flujo KISS con segmentación seleccionable"),
            (ROUTE_IMMEDIATE, "Implante inmediato", "Diente presente: exige individualización FDI y extracción virtual"),
        ),
        default=ROUTE_SIMPLE,
        update=_workflow_route_update,
    )
    target_fdi: EnumProperty(
        name="FDI objetivo",
        description="Diente o posición protésica objetivo del implante",
        items=tuple(
            (str(fdi), str(fdi), f"FDI {fdi}")
            for fdi in (
                11,12,13,14,15,16,17,18,
                21,22,23,24,25,26,27,28,
                31,32,33,34,35,36,37,38,
                41,42,43,44,45,46,47,48,
            )
        ),
        default="11",
        update=_target_fdi_update,
    )


def patient_folder(scene=None) -> str:
    scene = scene or getattr(bpy.context, "scene", None)
    if scene is None:
        return ""
    settings = getattr(scene, "dsg_suite_settings", None)
    value = str(getattr(settings, "patient_folder", "") or scene.get(PATIENT_FOLDER_KEY, "") or "")
    return os.path.abspath(os.path.expanduser(value)) if value else ""


def _set_patient_folder(scene, folder: str) -> str:
    folder = os.path.abspath(os.path.expanduser(str(folder or "")))
    settings = getattr(scene, "dsg_suite_settings", None)
    if settings is not None:
        settings.patient_folder = folder
        # The selected folder is the case SSOT, so changing patient must also
        # change the visible case name instead of retaining the previous one.
        settings.case_name = Path(folder).name
    scene[PATIENT_FOLDER_KEY] = folder
    scene[ROUTE_STEP_KEY] = "PATIENT"
    scene[IMMEDIATE_FDIS_KEY] = "[]"
    scene["DSG_immediate_extraction_fdis"] = ""
    scene["DSG_generated_patient_files_json"] = "[]"
    scene["DSG_ios_imported_files_json"] = "[]"
    return folder


def _iter_dicom_candidate_paths(folder: str):
    """Yield likely DICOM files without building/sorting a huge recursive list.

    CBCT exports often contain hundreds or thousands of slices. Older DSG builds
    walked the whole patient tree, materialised every candidate and sorted it
    before trying the first DICOM, which made "CARGAR CBCT" feel frozen.
    This streaming discovery stops as soon as one valid representative is found.
    """
    root = Path(folder)
    if not root.is_dir():
        return
    ignored = {".stl", ".obj", ".ply", ".blend", ".zip", ".png", ".jpg", ".jpeg", ".pdf", ".txt", ".json"}
    for dirpath, dirnames, filenames in os.walk(root):
        # Skip obvious generated/cache folders; keep vendor export folders intact.
        dirnames[:] = [d for d in dirnames if d.lower() not in {"__pycache__", ".git", "cache", "temp", "tmp"}]
        preferred = []
        fallback = []
        dicomdirs = []
        for filename in filenames:
            path = Path(dirpath) / filename
            name = filename.lower()
            suffix = path.suffix.lower()
            if suffix in ignored:
                continue
            if suffix in {".dcm", ".dicom"}:
                preferred.append(path)
            elif name == "dicomdir":
                # A real image slice is cheaper to probe than expanding DICOMDIR.
                dicomdirs.append(path)
            elif suffix in {".ima", ""}:
                fallback.append(path)
        # Deterministic only within the current directory; never sort the full study.
        yield from sorted(preferred, key=lambda x: x.name.lower())
        yield from sorted(fallback, key=lambda x: x.name.lower())
        yield from sorted(dicomdirs, key=lambda x: x.name.lower())


def _discover_patient_dicom(folder: str):
    from . import dicom_module
    errors = []
    attempted = 0
    for path in _iter_dicom_candidate_paths(folder):
        attempted += 1
        try:
            return dicom_module.probe_source(str(path))
        except Exception as exc:
            if len(errors) < 3:
                errors.append(f"{path.name}: {exc}")
        # A normal patient folder should expose a representative very quickly.
        # Bound malformed/noisy folders so discovery itself never becomes a freeze.
        if attempted >= 96:
            break
    detail = " · ".join(errors)
    raise RuntimeError(
        "No encontré una serie DICOM/DCM válida dentro de la carpeta del paciente"
        + (f" ({detail})" if detail else "")
    )


def _start_patient_cbct_from_probe(context, probe):
    from . import dicom_module
    scene = context.scene
    props = scene.dicom_wizard_pro
    props.status = "DICOM localizado · preparando serie…"
    dicom_module._LAST_PROBE = probe
    dicom_module._fill_probe_properties(props, probe)
    props.filepath = str(probe.filepath)
    try:
        dicom_module.write_header_text(probe)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    # Invalidate the immediate route before starting a new CBCT.  This prevents
    # a verification result from the previous patient/session from arming the
    # heavy dual-engine button while the new volume/MPR is still settling.
    scene[IMMEDIATE_GATE_ARMED_KEY] = False
    scene[IMMEDIATE_GATE_READY_AT_KEY] = 0.0

    # Never import Torch/nnU-Net while opening the CBCT. AI readiness is checked
    # independently at DSG startup and again when the immediate route is chosen.
    # The DICOM operator decodes pixels asynchronously and returns RUNNING_MODAL.
    result = bpy.ops.dicom_wizard_pro.next()
    if not ({"RUNNING_MODAL", "FINISHED"} & set(result)):
        raise RuntimeError(str(getattr(props, "status", "No se pudo iniciar la carga del CBCT")))
    scene[ROUTE_STEP_KEY] = "CBCT_LOADING"
    scene["DSG_patient_dicom_path"] = str(probe.filepath)
    set_stage(scene, STAGE_DICOM)
    return probe


def _load_patient_cbct(context):
    scene = context.scene
    folder = patient_folder(scene)
    if not folder:
        raise RuntimeError("Elige primero la carpeta del paciente")
    return _start_patient_cbct_from_probe(context, _discover_patient_dicom(folder))


def _ios_arch_hint(path: Path) -> str:
    name = path.stem.lower().replace("-", "_").replace(" ", "_")
    upper = ("upper", "maxilla", "maxilar", "superior", "sup_", "_sup", "arcada_sup")
    lower = ("lower", "mandible", "mandibula", "mandíbula", "inferior", "inf_", "_inf", "arcada_inf")
    if any(token in name for token in upper):
        return "MAXILLA"
    if any(token in name for token in lower):
        return "MANDIBLE"
    return ""


def _patient_ios_candidates(scene) -> list[Path]:
    folder = patient_folder(scene)
    if not folder:
        return []
    generated = set()
    try:
        generated = {os.path.abspath(v) for v in json.loads(str(scene.get("DSG_generated_patient_files_json", "[]") or "[]"))}
    except Exception:
        generated = set()
    candidates = []
    # Windows is case-insensitive, but test/install environments may not be.
    # Scan once and normalize the suffix so IOS.STL and ios.stl behave equally.
    for path in Path(folder).rglob("*"):
        if not path.is_file() or path.suffix.lower() != ".stl":
            continue
        absolute = os.path.abspath(str(path))
        if absolute in generated:
            continue
        low = path.name.lower()
        # Skip files DSG itself commonly creates.  Do NOT reject names such as
        # maxilla.stl/mandible.stl because laboratories often use those names
        # for genuine intraoral scans.
        if low.startswith("dsg_") or low.startswith("dental_dicom_"):
            continue
        if any(token in low for token in ("surgical_guide", "guia_quir", "guide_final", "cbct_")):
            continue
        candidates.append(path)
    def score(path: Path):
        low = path.name.lower()
        value = 0
        if any(k in low for k in ("ios", "intraoral", "scan")):
            value += 20
        if _ios_arch_hint(path):
            value += 10
        return (-value, len(path.parts), path.name.lower())
    return sorted(candidates, key=score)


def _auto_import_patient_ios(context):
    from . import alignment_module
    scene = context.scene
    candidates = _patient_ios_candidates(scene)
    if not candidates:
        return [], "No se encontró ningún STL intraoral en la carpeta del paciente"

    existing_by_path = {}
    for obj in scene.objects:
        source = str(obj.get("dental_suite_source_path", "") or "")
        if source:
            existing_by_path[os.path.abspath(source)] = obj

    imported = []
    for index, path in enumerate(candidates[:4], start=1):
        absolute = os.path.abspath(str(path))
        obj = existing_by_path.get(absolute)
        if obj is None or getattr(obj, "type", None) != "MESH":
            try:
                obj, _objects = alignment_module._import_stl_file(context, absolute)
            except Exception as exc:
                print(f"[DSG IOS] {path.name}: {exc}")
                continue
        hint = _ios_arch_hint(path)
        set_role(obj, ROLE_IOS_SCAN, rename=False)
        suffix = "Upper" if hint == "MAXILLA" else "Lower" if hint == "MANDIBLE" else str(index)
        try:
            obj.name = f"Dental_IOS_{suffix}"
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        obj["dental_suite_source_path"] = absolute
        obj["dental_suite_component"] = "ALIGNMENT"
        obj["dental_suite_protocol"] = SUITE_PROTOCOL_VERSION
        obj["DSG_ios_arch_hint"] = hint
        obj["DSG_dental_identity_source"] = "CBCT"
        try:
            alignment_module.ensure_ios_gray_material(obj, context=context)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        imported.append(obj)

    if not imported:
        return [], "Los STL encontrados no pudieron importarse como IOS"

    preferred_arch = str(scene.get("DSG_active_arch", "") or "").upper()
    source = next((o for o in imported if str(o.get("DSG_ios_arch_hint", "")).upper() == preferred_arch), imported[0])
    for obj in imported:
        if obj != source:
            set_role(obj, ROLE_IOS_ANTAGONIST, rename=False)
            obj["DSG_antagonist_arch_hint"] = str(obj.get("DSG_ios_arch_hint", "") or "")
    bind_antagonists_to_source(source)
    props = getattr(scene, "dicp_props", None)
    if props is not None:
        props.icp_source_obj = source
        target = find_alignment_reference(scene)
        if target is not None:
            props.icp_target_obj = target
        try:
            props.ios_source_filepath = str(source.get("dental_suite_source_path", "") or "")
            props.current_step = alignment_module.STEP_MODELS
            props.alignment_running = False
            props.alignment_progress = 0.0
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    try:
        for obj in context.selected_objects:
            obj.select_set(False)
        source.hide_set(False)
        source.select_set(True)
        context.view_layer.objects.active = source
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    scene["DSG_ios_imported_files_json"] = json.dumps([str(p) for p in candidates[:4]], ensure_ascii=False)
    return imported, f"{len(imported)} modelo(s) IOS importado(s) automáticamente"


def _export_object_to_patient(context, obj, filename: str) -> str:
    folder = patient_folder(context.scene)
    if not folder or obj is None or getattr(obj, "type", None) != "MESH":
        return ""
    output = os.path.join(folder, filename)
    previous_active = context.view_layer.objects.active
    previous_selection = list(context.selected_objects)
    try:
        bpy.ops.object.select_all(action="DESELECT")
        obj.hide_set(False)
        obj.select_set(True)
        context.view_layer.objects.active = obj
        bpy.ops.wm.stl_export(filepath=output, export_selected_objects=True, apply_modifiers=True)
        try:
            files = json.loads(str(context.scene.get("DSG_generated_patient_files_json", "[]") or "[]"))
        except Exception:
            files = []
        absolute = os.path.abspath(output)
        if absolute not in files:
            files.append(absolute)
        context.scene["DSG_generated_patient_files_json"] = json.dumps(files, ensure_ascii=False)
        return output
    except Exception as exc:
        print(f"[DSG export patient] {filename}: {exc}")
        return ""
    finally:
        try:
            bpy.ops.object.select_all(action="DESELECT")
            for selected in previous_selection:
                if selected.name in bpy.data.objects:
                    selected.select_set(True)
            if previous_active is not None and previous_active.name in bpy.data.objects:
                context.view_layer.objects.active = previous_active
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)


def _hidden_immediate_teeth(context):
    from . import cbct_dental_module
    hidden = []
    for tooth in cbct_dental_module.dentition_objects(context):
        is_hidden = bool(getattr(tooth, "hide_viewport", False))
        try:
            is_hidden = is_hidden or bool(tooth.hide_get())
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        if is_hidden:
            hidden.append(tooth)
    hidden.sort(key=lambda obj: int(obj.get("DSG_fdi_number", 0) or 0))
    return hidden


class DSG_SUITE_OT_ChoosePatientFolder(Operator):
    bl_idname = "dsg_suite.choose_patient_folder"
    bl_label = "Elegir paciente"
    bl_description = "Selecciona la carpeta maestra del paciente; DSG la reutiliza para DICOM, IOS y exportaciones"

    directory: StringProperty(subtype="DIR_PATH")
    filter_folder: BoolProperty(default=True, options={"HIDDEN"})

    _timer = None
    _thread = None
    _probe = None
    _error = ""
    _done = False

    def invoke(self, context, event):
        current = patient_folder(context.scene)
        if current:
            self.directory = current
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        folder = str(self.directory or "")
        if not folder or not os.path.isdir(folder):
            self.report({"ERROR"}, "Selecciona una carpeta válida del paciente")
            return {"CANCELLED"}
        _set_patient_folder(context.scene, folder)
        self._probe = None
        self._error = ""
        self._done = False
        props = getattr(context.scene, "dicom_wizard_pro", None)
        if props is not None:
            props.status = "Paciente seleccionado · buscando CBCT…"

        def discover():
            try:
                self._probe = _discover_patient_dicom(folder)
            except Exception as exc:
                self._error = f"{type(exc).__name__}: {exc}"
            finally:
                self._done = True

        try:
            self._thread = threading.Thread(
                target=discover,
                daemon=True,
                name="DSG-Patient-DICOM-Discovery",
            )
            self._thread.start()
            self._timer = context.window_manager.event_timer_add(0.10, window=context.window)
            context.window_manager.modal_handler_add(self)
            self.report({"INFO"}, f"Paciente: {Path(folder).name} · buscando CBCT en segundo plano")
            return {"RUNNING_MODAL"}
        except Exception as exc:
            self._finish(context)
            self.report({"WARNING"}, f"Paciente seleccionado. CBCT pendiente: {exc}")
            return {"FINISHED"}

    def _finish(self, context):
        if self._timer is not None:
            try:
                context.window_manager.event_timer_remove(self._timer)
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
        self._timer = None

    def modal(self, context, event):
        if event.type != "TIMER":
            return {"PASS_THROUGH"}
        if not self._done:
            return {"RUNNING_MODAL"}
        self._finish(context)
        props = getattr(context.scene, "dicom_wizard_pro", None)
        if self._error or self._probe is None:
            detail = self._error or "No se encontró una serie DICOM"
            if props is not None:
                props.status = f"Paciente seleccionado · CBCT pendiente: {detail}"
            self.report({"WARNING"}, f"Paciente seleccionado. CBCT pendiente: {detail}")
            return {"FINISHED"}
        try:
            probe = _start_patient_cbct_from_probe(context, self._probe)
            self.report({"INFO"}, f"Abriendo CBCT: {Path(probe.filepath).name}")
        except Exception as exc:
            if props is not None:
                props.status = f"Paciente seleccionado · CBCT pendiente: {exc}"
            self.report({"WARNING"}, f"Paciente seleccionado. CBCT pendiente: {exc}")
        return {"FINISHED"}

    def cancel(self, context):
        self._finish(context)


class DSG_SUITE_OT_LoadPatientCBCT(Operator):
    bl_idname = "dsg_suite.load_patient_cbct"
    bl_label = "Cargar CBCT del paciente"

    def execute(self, context):
        try:
            probe = _load_patient_cbct(context)
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        self.report({"INFO"}, f"Abriendo CBCT: {Path(probe.filepath).name}")
        return {"FINISHED"}


class DSG_SUITE_OT_ChangeRoute(Operator):
    bl_idname = "dsg_suite.change_route"
    bl_label = "Cambiar ruta"
    bl_description = "Vuelve a la elección SIMPLE / INMEDIATO sin cambiar de paciente ni recargar el CBCT"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scene = context.scene
        try:
            from . import dicom_module
            if bool(dicom_module.semantic_workflow_busy()):
                self.report({"WARNING"}, "Espera a que termine la segmentación antes de cambiar de ruta")
                return {"CANCELLED"}
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)

        _restore_virtual_extraction_if_needed(scene)

        # Remove only route-review composites. Source DICOM, segmentation and
        # the patient's folder remain intact so changing route is inexpensive.
        for key in ("DSG_immediate_upper_composite", "DSG_immediate_lower_composite"):
            name = str(scene.get(key, "") or "")
            obj = bpy.data.objects.get(name) if name else None
            if obj is not None:
                mesh = obj.data if getattr(obj, "type", None) == "MESH" else None
                try:
                    bpy.data.objects.remove(obj, do_unlink=True)
                    if mesh is not None and mesh.users == 0:
                        bpy.data.meshes.remove(mesh)
                except Exception:
                    _DSG_LOG.debug("suppressed exception", exc_info=True)
            scene[key] = ""

        try:
            from . import cbct_dental_module
            for tooth in cbct_dental_module.dentition_objects(context):
                try:
                    tooth.hide_viewport = False
                    tooth.hide_select = False
                    tooth.hide_set(False)
                except Exception:
                    _DSG_LOG.debug("suppressed exception", exc_info=True)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)

        scene[IMMEDIATE_FDIS_KEY] = "[]"
        scene["DSG_immediate_extraction_fdis"] = ""
        scene["DSG_immediate_extraction_prepared"] = False
        scene["DSG_route_review_required"] = False
        scene[ROUTE_STEP_KEY] = "CBCT_READY"
        set_stage(scene, STAGE_DICOM)
        self.report({"INFO"}, "Elige una sola ruta clínica para continuar")
        return {"FINISHED"}


DICOM_ROUTE_CHECKPOINT_COLLECTION = "__DSG_DICOM_RouteCheckpoint"
DICOM_ROUTE_CHECKPOINT_STATE = "DSG_dicom_route_checkpoint_state"
DICOM_ROUTE_CHECKPOINT_SOURCE = "DSG_checkpoint_source_name"
DICOM_ROUTE_CHECKPOINT_COLLECTIONS = "DSG_checkpoint_source_collections"


def _clear_dicom_route_checkpoint(scene=None):
    scene = scene or getattr(bpy.context, "scene", None)
    col = bpy.data.collections.get(DICOM_ROUTE_CHECKPOINT_COLLECTION)
    if col is not None:
        for obj in list(col.objects):
            data = obj.data if getattr(obj, "type", None) == "MESH" else None
            bpy.data.objects.remove(obj, do_unlink=True)
            if data is not None and data.users == 0:
                bpy.data.meshes.remove(data)
        bpy.data.collections.remove(col)
    if scene is not None:
        try: del scene[DICOM_ROUTE_CHECKPOINT_STATE]
        except Exception: _DSG_LOG.debug("suppressed exception", exc_info=True)


def capture_dicom_route_checkpoint(context):
    """Snapshot generated DICOM geometry + UI state before a route starts."""
    scene = context.scene
    _clear_dicom_route_checkpoint(scene)
    col = bpy.data.collections.new(DICOM_ROUTE_CHECKPOINT_COLLECTION)
    scene.collection.children.link(col)
    col.hide_viewport = True; col.hide_render = True
    copied = 0
    for obj in list(scene.objects):
        if not _is_dicom_related_object(obj) or getattr(obj, "type", None) != "MESH":
            continue
        # Viewer/volume helpers are reproducible from RUNTIME and may be huge;
        # checkpoint only generated clinical meshes.
        role = role_of(obj)
        if role not in {ROLE_DICOM_TEETH, ROLE_DICOM_BONE, ROLE_DICOM_MANDIBULAR_CANAL, ROLE_DICOM_ALIGNMENT_COMPOSITE}:
            continue
        clone = obj.copy(); clone.data = obj.data.copy()
        clone[DICOM_ROUTE_CHECKPOINT_SOURCE] = str(obj.name)
        clone[DICOM_ROUTE_CHECKPOINT_COLLECTIONS] = json.dumps([c.name for c in obj.users_collection])
        col.objects.link(clone); copied += 1
    props = getattr(scene, "dicom_wizard_pro", None)
    state = {
        "stage": str(scene.get(SUITE_STAGE_KEY, STAGE_DICOM)),
        "route_step": str(scene.get(ROUTE_STEP_KEY, "CBCT_READY")),
        "route": str(scene.get(WORKFLOW_ROUTE_KEY, ROUTE_SIMPLE)),
        "generated_surface_name": str(getattr(props, "generated_surface_name", "") or "") if props else "",
        "surface_ready": bool(getattr(props, "surface_ready", False)) if props else False,
        "segmentation_ready": bool(getattr(props, "segmentation_ready", False)) if props else False,
        "step": int(getattr(props, "step", 2) or 2) if props else 2,
        "show_volume": bool(getattr(props, "show_volume", True)) if props else True,
        "show_planes": bool(getattr(props, "show_planes", True)) if props else True,
        "show_all_planes": bool(getattr(props, "show_all_planes", False)) if props else False,
        "show_box": bool(getattr(props, "show_box", False)) if props else False,
        "copied": copied,
    }
    scene[DICOM_ROUTE_CHECKPOINT_STATE] = json.dumps(state, separators=(",", ":"))
    try: bpy.ops.ed.undo_push(message="DSG · Estado previo a segmentación")
    except Exception: _DSG_LOG.debug("suppressed exception", exc_info=True)
    return state


def restore_dicom_route_checkpoint(context):
    """Restore the exact generated-DICOM state captured before segmentation."""
    scene = context.scene
    raw = str(scene.get(DICOM_ROUTE_CHECKPOINT_STATE, "") or "")
    if not raw: return False
    try: state = json.loads(raw)
    except Exception: return False
    # Remove only generated DICOM meshes, never raw CBCT/IOS and never the
    # hidden checkpoint copies themselves (they are also members of scene.objects).
    for obj in list(scene.objects):
        if any(getattr(col, "name", "") == DICOM_ROUTE_CHECKPOINT_COLLECTION for col in getattr(obj, "users_collection", ())):
            continue
        if getattr(obj, "type", None) == "MESH" and role_of(obj) in {ROLE_DICOM_TEETH, ROLE_DICOM_BONE, ROLE_DICOM_MANDIBULAR_CANAL, ROLE_DICOM_ALIGNMENT_COMPOSITE}:
            _remove_object_and_data(obj)
    col = bpy.data.collections.get(DICOM_ROUTE_CHECKPOINT_COLLECTION)
    if col is not None:
        for saved in list(col.objects):
            clone = saved.copy(); clone.data = saved.data.copy()
            clone.name = str(saved.get(DICOM_ROUTE_CHECKPOINT_SOURCE, saved.name) or saved.name)
            try: names = json.loads(str(saved.get(DICOM_ROUTE_CHECKPOINT_COLLECTIONS, "[]") or "[]"))
            except Exception: names = []
            target = bpy.data.collections.get(names[0]) if names else None
            (target or scene.collection).objects.link(clone)
    props = getattr(scene, "dicom_wizard_pro", None)
    if props is not None:
        for key in ("generated_surface_name", "surface_ready", "segmentation_ready", "step", "show_volume", "show_planes", "show_all_planes", "show_box"):
            if key in state:
                try: setattr(props, key, state[key])
                except Exception: _DSG_LOG.debug("suppressed exception", exc_info=True)
    scene[SUITE_STAGE_KEY] = str(state.get("stage") or STAGE_DICOM)
    scene[ROUTE_STEP_KEY] = str(state.get("route_step") or "CBCT_READY")
    restored_route = str(state.get("route") or ROUTE_SIMPLE)
    scene[WORKFLOW_ROUTE_KEY] = restored_route
    try:
        scene.dsg_suite_settings.workflow_route = restored_route
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    for key in ("DSG_simple_upper_object", "DSG_simple_lower_object", "DSG_simple_alignment_object"):
        scene[key] = ""
    try:
        from . import dicom_module
        dicom_module.update_visibility(context)
    except Exception: _DSG_LOG.debug("suppressed exception", exc_info=True)
    _clear_dicom_route_checkpoint(scene)
    return True


class DSG_SUITE_OT_StartSimpleRoute(Operator):
    bl_idname = "dsg_suite.start_simple_route"
    bl_label = "Implante simple"
    bl_description = "Segmenta en segundo plano exactamente dos arcadas: superior e inferior, sin FDI ni canal"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        global _SIMPLE_ROUTE_EXECUTING
        if _SIMPLE_ROUTE_EXECUTING:
            try: cls.poll_message_set("Implante simple ya se esta iniciando")
            except Exception: _DSG_LOG.debug("suppressed exception", exc_info=True)
            return False
        ready, reason = _immediate_route_readiness(context)
        if not ready:
            try: cls.poll_message_set(reason)
            except Exception: _DSG_LOG.debug("suppressed exception", exc_info=True)
        return bool(ready)

    def execute(self, context):
        global _SIMPLE_ROUTE_EXECUTING
        scene = context.scene
        ready, reason = _immediate_route_readiness(context)
        if not ready:
            self.report({"WARNING"}, reason)
            return {"CANCELLED"}
        if _SIMPLE_ROUTE_EXECUTING:
            self.report({"WARNING"}, "Implante simple ya se esta iniciando")
            return {"CANCELLED"}
        if False:
            self.report({"WARNING"}, "Ya hay una segmentación CBCT en curso")
            return {"CANCELLED"}
        capture_dicom_route_checkpoint(context)
        _SIMPLE_ROUTE_EXECUTING = True
        scene.dsg_suite_settings.workflow_route = ROUTE_SIMPLE
        scene[ROUTE_STEP_KEY] = "SIMPLE_SEGMENTING"
        props = scene.dicom_wizard_pro
        props.step = 3
        props.status = "Implante simple · preparando dos arcadas…"
        try:
            if context.screen:
                for area in context.screen.areas:
                    area.tag_redraw()
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)

        scene_name = str(scene.name)

        def _deferred_launch():
            global _SIMPLE_ROUTE_EXECUTING
            target_scene = bpy.data.scenes.get(scene_name)
            if target_scene is None:
                _SIMPLE_ROUTE_EXECUTING = False
                return None
            try:
                from . import dicom_module
                if not bool(dicom_module.RUNTIME.is_loaded()):
                    raise RuntimeError("El CBCT ya no esta cargado")
                if bool(getattr(dicom_module.RUNTIME, "update_lock", False)):
                    return 0.20
                if bool(dicom_module.semantic_workflow_busy()):
                    raise RuntimeError("Ya hay una segmentacion CBCT en curso")
                result = bpy.ops.dicom_wizard_pro.segment_all(
                    "EXEC_DEFAULT", route_mode="SIMPLE_ARCHES")
                if "FINISHED" not in result:
                    raise RuntimeError("No se pudo iniciar la segmentacion simple")
                target_scene[ROUTE_STEP_KEY] = "SIMPLE_SEGMENTING"
                try:
                    target_scene.dicom_wizard_pro.status = (
                        "Segmentacion simple iniciada en segundo plano")
                except Exception:
                    _DSG_LOG.debug("suppressed exception", exc_info=True)
            except Exception as exc:
                try:
                    target_context = bpy.context.copy()
                    target_context["scene"] = target_scene
                    restore_dicom_route_checkpoint(target_context)
                except Exception:
                    target_scene[ROUTE_STEP_KEY] = "CBCT_READY"
                    try:
                        target_scene.dsg_suite_settings.workflow_route = ROUTE_SIMPLE
                    except Exception:
                        _DSG_LOG.debug("suppressed exception", exc_info=True)
                try:
                    target_scene.dicom_wizard_pro.status = f"Error: {exc}"
                except Exception:
                    _DSG_LOG.debug("suppressed exception", exc_info=True)
                print(f"[DSG] Simple launch cancelled: {exc}")
            finally:
                _SIMPLE_ROUTE_EXECUTING = False
                try:
                    for window in bpy.context.window_manager.windows:
                        if window.screen:
                            for area in window.screen.areas:
                                area.tag_redraw()
                except Exception:
                    _DSG_LOG.debug("suppressed exception", exc_info=True)
            return None

        props.status = "Implante simple - preparando dos arcadas..."
        bpy.app.timers.register(_deferred_launch, first_interval=0.25)
        self.report({"INFO"}, "Implante simple - arranque seguro programado")
        return {"FINISHED"}

        try:
            result = bpy.ops.dicom_wizard_pro.segment_all("EXEC_DEFAULT", route_mode="SIMPLE_ARCHES")
            if "FINISHED" not in result:
                raise RuntimeError("No se pudo iniciar la segmentación simple")
        except Exception as exc:
            restore_dicom_route_checkpoint(context)
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        self.report({"INFO"}, "Ruta simple iniciada · sólo superior + inferior")
        return {"FINISHED"}


class DSG_SUITE_OT_ConfirmSimpleSTL(Operator):
    bl_idname = "dsg_suite.confirm_simple_stl"
    bl_label = "Confirmar arcadas y alinear"
    bl_description = "Confirma las dos arcadas coloreadas e inicia el alineamiento IOS"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scene = context.scene
        upper = bpy.data.objects.get(str(scene.get("DSG_simple_upper_object", "") or ""))
        lower = bpy.data.objects.get(str(scene.get("DSG_simple_lower_object", "") or ""))
        reference = bpy.data.objects.get(str(scene.get("DSG_simple_alignment_object", "") or ""))
        if upper is None or lower is None or reference is None:
            self.report({"ERROR"}, "Faltan las dos arcadas simples; vuelve a segmentar")
            return {"CANCELLED"}
        imported, message = _auto_import_patient_ios(context)
        props = getattr(scene, "dicp_props", None)
        if props is not None:
            props.icp_target_obj = reference
        set_stage(scene, STAGE_ALIGNMENT)
        scene[ROUTE_STEP_KEY] = "ALIGNMENT"
        try: bpy.ops.ed.undo_push(message="DSG · Arcadas confirmadas · alineamiento")
        except Exception: _DSG_LOG.debug("suppressed exception", exc_info=True)
        self.report({"INFO" if imported else "WARNING"}, f"Arcadas confirmadas · {message}")
        return {"FINISHED"}


def _immediate_route_readiness(context):
    """Cheap route gate. Never imports Torch/nnU-Net in foreground Blender.

    v9.2.75 intentionally removes the deep verifier from the route-choice screen.
    The button is enabled as soon as the CBCT is genuinely committed and the
    required files/checkpoints exist structurally. Heavy import/model validation
    occurs only inside the isolated AI worker after the clinician chooses the
    immediate route.
    """
    scene = getattr(context, "scene", None)
    if scene is None:
        return False, "Escena no disponible"
    try:
        from . import dicom_module, runtime_bootstrap, totalseg_runtime
    except Exception:
        return False, "DSG todavía está cargando sus módulos"

    step = str(scene.get(ROUTE_STEP_KEY, "") or "")
    props = getattr(scene, "dicom_wizard_pro", None)

    if step == "CBCT_LOADING":
        return False, "Espera a que termine de abrir el CBCT"
    if not bool(dicom_module.RUNTIME.is_loaded()):
        return False, "Carga primero el CBCT"
    if props is None or not bool(getattr(props, "volume_loaded", False)):
        return False, "Finalizando el volumen DICOM"
    if step != "CBCT_READY":
        if step.startswith("IMMEDIATE_"):
            return False, "La ruta inmediata ya está iniciada"
        return False, "Finalizando la preparación del CBCT"
    if bool(dicom_module.semantic_workflow_busy()):
        return False, "Ya hay una segmentación CBCT en curso"
    if bool(getattr(dicom_module.RUNTIME, "update_lock", False)):
        return False, "Finalizando el visor DICOM"

    try:
        remote = runtime_bootstrap.remote_install_state()
        if bool(remote.get("running")):
            return False, "Instalando motores IA"
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)

    try:
        install = totalseg_runtime.install_state()
        if bool(install.get("running")):
            return False, "Preparando motores IA"
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)

    # Cheap structural probe only. quick_status() checks files/checkpoints and
    # Python module availability without importing Torch or initializing CUDA.
    try:
        status = totalseg_runtime.quick_status()
        if not status.dependencies_ready:
            return False, "Runtime IA no instalado"
        if not status.model_ready:
            return False, "Falta TotalSegmentator task=teeth"
    except Exception as exc:
        return False, f"Motores IA no listos: {exc}"[:180]

    return True, "CBCT listo · TotalSegmentator se ejecutará en proceso aislado"




class DSG_SUITE_OT_StartImmediateRoute(Operator):
    bl_idname = "dsg_suite.start_immediate_route"
    bl_label = "Implante inmediato"
    bl_description = "Inicia TotalSegmentator task=teeth cuando CBCT y motor están listos"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        global _IMMEDIATE_ROUTE_EXECUTING
        if _IMMEDIATE_ROUTE_EXECUTING:
            try:
                cls.poll_message_set("Implante inmediato ya se está iniciando")
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
            return False
        ready, reason = _immediate_route_readiness(context)
        if not ready:
            try:
                cls.poll_message_set(reason)
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
        return bool(ready)

    def execute(self, context):
        global _IMMEDIATE_ROUTE_EXECUTING
        scene = context.scene

        ready, reason = _immediate_route_readiness(context)
        if not ready:
            self.report({"WARNING"}, reason)
            return {"CANCELLED"}
        if _IMMEDIATE_ROUTE_EXECUTING:
            self.report({"WARNING"}, "Implante inmediato ya se está iniciando")
            return {"CANCELLED"}

        capture_dicom_route_checkpoint(context)

        # Lock synchronously, but DO NOT enter the heavy segmentation operator
        # from the same mouse event. Returning control to Blender first gives it
        # a chance to paint the disabled button and process the event queue.
        _IMMEDIATE_ROUTE_EXECUTING = True
        _restore_virtual_extraction_if_needed(scene)
        scene[IMMEDIATE_FDIS_KEY] = "[]"
        scene["DSG_immediate_extraction_fdis"] = ""
        scene[IMMEDIATE_GATE_ARMED_KEY] = False
        scene.dsg_suite_settings.workflow_route = ROUTE_IMMEDIATE
        props = scene.dicom_wizard_pro
        props.step = 3
        scene[ROUTE_STEP_KEY] = "IMMEDIATE_LAUNCHING"
        props.status = "Iniciando segmentación inmediata…"

        try:
            if context.screen:
                for area in context.screen.areas:
                    area.tag_redraw()
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)

        scene_name = str(scene.name)

        def _deferred_launch():
            global _IMMEDIATE_ROUTE_EXECUTING
            target_scene = bpy.data.scenes.get(scene_name)
            if target_scene is None:
                _IMMEDIATE_ROUTE_EXECUTING = False
                return None
            try:
                # Revalidate the volume immediately before the expensive call.
                from . import dicom_module
                if not bool(dicom_module.RUNTIME.is_loaded()):
                    raise RuntimeError("El CBCT ya no está cargado")
                if bool(getattr(dicom_module.RUNTIME, "update_lock", False)):
                    # One more UI tick rather than competing with DICOM updates.
                    return 0.20
                if bool(dicom_module.semantic_workflow_busy()):
                    raise RuntimeError("Ya hay una segmentación CBCT en curso")

                result = bpy.ops.dicom_wizard_pro.segment_all("EXEC_DEFAULT")
                if "FINISHED" not in result:
                    raise RuntimeError("No se pudo iniciar la segmentación inmediata")
                target_scene[ROUTE_STEP_KEY] = "IMMEDIATE_SEGMENTING"
                try:
                    target_scene.dicom_wizard_pro.status = (
                        "Segmentación inmediata iniciada en segundo plano"
                    )
                except Exception:
                    _DSG_LOG.debug("suppressed exception", exc_info=True)
            except Exception as exc:
                target_scene[ROUTE_STEP_KEY] = "CBCT_READY"
                target_scene[IMMEDIATE_GATE_ARMED_KEY] = False
                try:
                    target_scene.dsg_suite_settings.workflow_route = ROUTE_SIMPLE
                    target_scene.dicom_wizard_pro.status = f"Error: {exc}"
                except Exception:
                    _DSG_LOG.debug("suppressed exception", exc_info=True)
                print(f"[DSG 9.2.71] Immediate launch cancelled: {exc}")
            finally:
                _IMMEDIATE_ROUTE_EXECUTING = False
                try:
                    for window in bpy.context.window_manager.windows:
                        if window.screen:
                            for area in window.screen.areas:
                                area.tag_redraw()
                except Exception:
                    _DSG_LOG.debug("suppressed exception", exc_info=True)
            return None

        # Deliberate short defer: the click handler returns immediately.
        bpy.app.timers.register(_deferred_launch, first_interval=0.25)
        self.report({"INFO"}, "Implante inmediato · arranque seguro programado")
        return {"FINISHED"}


class DSG_SUITE_OT_AcceptFDIAndSelectTeeth(Operator):
    bl_idname = "dsg_suite.accept_fdi_select_teeth"
    bl_label = "FDI correcto · elegir dientes"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        from . import cbct_dental_module, dicom_module
        scene = context.scene
        teeth = cbct_dental_module.dentition_objects(context)
        if not teeth:
            self.report({"ERROR"}, "La segmentación todavía no ha creado dientes individuales")
            return {"CANCELLED"}
        if not bool(scene.get(cbct_dental_module.SCENE_ACCEPTED_KEY, False)):
            result = bpy.ops.dsg.cbct_accept_fdi()
            if "FINISHED" not in result:
                self.report({"ERROR"}, "Revisa la numeración o usa INVERTIR MAXILAR/MANDÍBULA")
                return {"CANCELLED"}
        # Remove an older socket-review result if the clinician comes back to
        # change the extraction selection. Source segmentation stays untouched.
        for key in ("DSG_immediate_upper_composite", "DSG_immediate_lower_composite"):
            name = str(scene.get(key, "") or "")
            obj = bpy.data.objects.get(name) if name else None
            if obj is not None:
                mesh = obj.data if obj.type == "MESH" else None
                bpy.data.objects.remove(obj, do_unlink=True)
                if mesh is not None and mesh.users == 0:
                    bpy.data.meshes.remove(mesh)
            scene[key] = ""

        # Start from a deterministic visible dentition.  The selected Blender
        # objects are only a temporary input; the explicit FDI list written by
        # ``FixImmediateExtractionSelection`` is the single source of truth.
        for tooth in teeth:
            try:
                tooth.hide_viewport = False
                tooth.hide_select = False
                tooth.hide_set(False)
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
        # Keep jaws and canal visible while choosing extractions; the canal is
        # display-only and is never passed to the Ctrl+J source list.
        jaw_names = (
            str(scene.get("DSG_maxilla_object", "") or ""),
            str(scene.get("DSG_mandible_object", "") or ""),
            dicom_module.NAME_DICOM_MANDIBULAR_CANAL,
        )
        for name in jaw_names:
            obj = bpy.data.objects.get(name) if name else None
            if obj is not None:
                try:
                    obj.hide_viewport = False
                    obj.hide_set(False)
                except Exception:
                    _DSG_LOG.debug("suppressed exception", exc_info=True)
        scene[IMMEDIATE_FDIS_KEY] = "[]"
        scene["DSG_immediate_extraction_fdis"] = ""
        scene["DSG_immediate_selection_source"] = ""
        scene[ROUTE_STEP_KEY] = "IMMEDIATE_SELECT_TEETH"
        try:
            cbct_dental_module.labels_visible(False)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        self.report({"INFO"}, "Selecciona los dientes CBCT y pulsa FIJAR DIENTES")
        return {"FINISHED"}


class DSG_SUITE_OT_FixImmediateExtractionSelection(Operator):
    """Persist the clinician's selected CBCT teeth as the immediate FDI SSOT."""

    bl_idname = "dsg_suite.fix_immediate_extraction_selection"
    bl_label = "Fijar dientes de extracción"
    bl_description = "Guarda los dientes CBCT actualmente seleccionados como los únicos dientes a extraer"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        from . import cbct_dental_module
        scene = context.scene
        teeth = cbct_dental_module.dentition_objects(context)
        selected = [
            obj for obj in teeth
            if bool(getattr(obj, "select_get", lambda: False)())
        ]
        if not selected:
            self.report({"ERROR"}, "Selecciona al menos un diente CBCT antes de fijar la extracción")
            return {"CANCELLED"}
        fdis = sorted({int(obj.get("DSG_fdi_number", 0) or 0) for obj in selected})
        fdis = [value for value in fdis if value > 0]
        if not fdis:
            self.report({"ERROR"}, "Los objetos seleccionados no tienen una FDI CBCT válida")
            return {"CANCELLED"}
        scene[IMMEDIATE_FDIS_KEY] = json.dumps(fdis)
        scene["DSG_immediate_extraction_fdis"] = ",".join(str(value) for value in fdis)
        scene["DSG_immediate_selection_source"] = "EXPLICIT_CBCT_OBJECT_SELECTION"
        try:
            scene.dsg_suite_settings.target_fdi = str(fdis[0])
        except Exception:
            scene[TARGET_FDI_KEY] = int(fdis[0])
        self.report({"INFO"}, "Dientes fijados para extracción: FDI " + ", ".join(map(str, fdis)))
        return {"FINISHED"}


class DSG_SUITE_OT_BuildImmediateArchModels(Operator):
    bl_idname = "dsg_suite.build_immediate_arch_models"
    bl_label = "Siguiente · crear modelos alveolares"
    bl_description = "Usa la FDI fijada para crear los alvéolos y los modelos por arcada, sin el nervio"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        from . import cbct_dental_module, tooth_analysis
        scene = context.scene
        # New workflow: the explicit FDI list is authoritative.  Keep the
        # hidden-H fallback only for files created by older DSG releases.
        fdis = _immediate_extraction_fdis(scene)
        if not fdis:
            hidden = _hidden_immediate_teeth(context)
            fdis = sorted({int(obj.get("DSG_fdi_number", 0) or 0) for obj in hidden if int(obj.get("DSG_fdi_number", 0) or 0) > 0})
        if not fdis:
            self.report({"ERROR"}, "Selecciona dientes CBCT y pulsa FIJAR DIENTES antes de crear alvéolos")
            return {"CANCELLED"}
        scene[IMMEDIATE_FDIS_KEY] = json.dumps(fdis)
        scene["DSG_immediate_extraction_fdis"] = ",".join(str(v) for v in fdis)
        # Compatibility with the older single-target planning helpers: the first
        # extraction is the active target, while the full list remains SSOT here.
        try:
            scene.dsg_suite_settings.target_fdi = str(fdis[0])
        except Exception:
            scene[TARGET_FDI_KEY] = int(fdis[0])
        # Preserve the familiar visual extraction result after fixing the FDI;
        # it is no longer used as the workflow's hidden state.
        for tooth in cbct_dental_module.dentition_objects(context):
            if int(tooth.get("DSG_fdi_number", 0) or 0) in fdis:
                try:
                    tooth.hide_viewport = True
                    tooth.hide_set(True)
                except Exception:
                    _DSG_LOG.debug("suppressed exception", exc_info=True)
        # v9.2.64 already materializes every FDI at native CBCT resolution in a
        # single multi-label pass. This call therefore performs only the optional
        # sub-voxel CBCT constraint on the few extraction teeth; it never promotes
        # a low-resolution preview or changes the source labelmap.
        try:
            detail = cbct_dental_module.upgrade_teeth_to_full_resolution(context, fdis)
            scene["DSG_immediate_selected_tooth_refine_s"] = float(detail.get("elapsed_s", 0.0) or 0.0)
        except Exception as exc:
            self.report({"ERROR"}, f"No se pudo recuperar el detalle CBCT de los dientes seleccionados: {exc}")
            return {"CANCELLED"}
        arches = {str(tooth_analysis.arch_from_fdi(fdi) or "") for fdi in fdis}
        arches.discard("")
        active_arch = next(iter(arches)) if len(arches) == 1 else ("MAXILLA" if any(fdi < 30 for fdi in fdis) else "MANDIBLE")
        scene["DSG_active_arch"] = active_arch
        try:
            summary = cbct_dental_module.build_immediate_arch_composites(context, excluded_fdis=fdis)
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        upper = summary.get("upper") if isinstance(summary, dict) else None
        lower = summary.get("lower") if isinstance(summary, dict) else None
        if upper is not None:
            _export_object_to_patient(context, upper, "DSG_IMMEDIATE_MAXILLA.stl")
        if lower is not None:
            _export_object_to_patient(context, lower, "DSG_IMMEDIATE_MANDIBLE.stl")
        scene[ROUTE_STEP_KEY] = "IMMEDIATE_ARCH_REVIEW"
        self.report({"INFO"}, f"Alvéolos preparados · extracciones FDI {', '.join(map(str, fdis))}")
        return {"FINISHED"}


class DSG_SUITE_OT_ConfirmImmediateModels(Operator):
    bl_idname = "dsg_suite.confirm_immediate_models"
    bl_label = "Confirmar y alinear"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scene = context.scene
        upper_name = str(scene.get("DSG_immediate_upper_composite", "") or "")
        lower_name = str(scene.get("DSG_immediate_lower_composite", "") or "")
        upper = bpy.data.objects.get(upper_name) if upper_name else None
        lower = bpy.data.objects.get(lower_name) if lower_name else None
        if upper is None and lower is None:
            self.report({"ERROR"}, "Primero crea los modelos maxilar+dientes y mandíbula+dientes")
            return {"CANCELLED"}
        arch = str(scene.get("DSG_active_arch", "MAXILLA") or "MAXILLA").upper()
        target = upper if arch == "MAXILLA" and upper is not None else lower if lower is not None else upper
        for obj in (upper, lower):
            if obj is not None:
                obj["dental_suite_alignment_reference"] = bool(obj == target)
        if target is not None:
            target[SUITE_ROLE_KEY] = ROLE_DICOM_ALIGNMENT_COMPOSITE
            target[LEGACY_ROLE_KEY] = ROLE_DICOM_ALIGNMENT_COMPOSITE
            target["dental_suite_alignment_reference_quality"] = "IMMEDIATE_ARCH_COMPOSITE"
            target["DSG_immediate_alignment_target"] = True
        # FDI labels are useful while choosing/examining teeth but become visual
        # noise during IOS alignment.  Keep only the labels of the actual CBCT
        # reference arch; never leave the unused maxilla/mandible over the IOS.
        try:
            from . import cbct_dental_module
            cbct_dental_module.labels_visible_for_arch(arch)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        props = getattr(scene, "dicp_props", None)
        if props is not None:
            props.icp_target_obj = target
        set_stage(scene, STAGE_ALIGNMENT)
        imported, message = _auto_import_patient_ios(context)
        scene[ROUTE_STEP_KEY] = "ALIGNMENT"
        self.report({"INFO" if imported else "WARNING"}, f"Modelos inmediatos confirmados · {message}")
        return {"FINISHED"}


def _immediate_extraction_fdis(scene) -> list[int]:
    """Return the clinician-selected immediate-extraction FDI values."""
    try:
        values = json.loads(str(scene.get(IMMEDIATE_FDIS_KEY, "[]") or "[]"))
        return sorted({int(value) for value in values if int(value) > 0})
    except Exception:
        return []


def _immediate_cbct_teeth(context, fdis: list[int]) -> list:
    from . import cbct_dental_module
    wanted = {int(value) for value in fdis}
    return [
        obj for obj in cbct_dental_module.dentition_objects(context)
        if int(obj.get("DSG_fdi_number", 0) or 0) in wanted
    ]


def _immediate_neighbour_teeth(context, selected_teeth: list, limit_per_tooth=2) -> list:
    """Return only the external FDI neighbours of each extraction block.

    For contiguous extractions such as 12+11, 11 is not a competitor of 12
    and 12 is not a competitor of 11.  The true anatomical boundaries are the
    teeth immediately outside the selected block (13 and 21 in that example).
    This avoids over-constraining GeoMatch with clinically irrelevant negative
    references.  Geometric fallback is restricted to the same arch and only
    used when an expected external FDI is absent.
    """
    from . import cbct_dental_module
    all_teeth = [obj for obj in cbct_dental_module.dentition_objects(context)
                 if obj.type == "MESH"]
    selected_set = set(selected_teeth)
    by_fdi = {
        int(obj.get("DSG_fdi_number", 0) or 0): obj for obj in all_teeth
        if int(obj.get("DSG_fdi_number", 0) or 0) > 0
    }
    selected_fdis = {
        int(obj.get("DSG_fdi_number", 0) or 0) for obj in selected_teeth
        if int(obj.get("DSG_fdi_number", 0) or 0) > 0
    }
    upper = [18,17,16,15,14,13,12,11,21,22,23,24,25,26,27,28]
    lower = [48,47,46,45,44,43,42,41,31,32,33,34,35,36,37,38]
    competitors = []
    expected_missing = []

    def add(candidate):
        if candidate is not None and candidate not in selected_set and candidate not in competitors:
            competitors.append(candidate)

    for arch in (upper, lower):
        indices = [i for i, fdi in enumerate(arch) if fdi in selected_fdis]
        if not indices:
            continue
        # Split selected teeth into contiguous blocks along the dental arch.
        runs = []
        run = [indices[0]]
        for idx in indices[1:]:
            if idx == run[-1] + 1:
                run.append(idx)
            else:
                runs.append(run)
                run = [idx]
        runs.append(run)
        for run in runs:
            left_idx = run[0] - 1
            right_idx = run[-1] + 1
            for idx in (left_idx, right_idx):
                if 0 <= idx < len(arch):
                    fdi = arch[idx]
                    candidate = by_fdi.get(fdi)
                    if candidate is not None:
                        add(candidate)
                    else:
                        expected_missing.append((fdi, arch))

    # If an expected external neighbour is missing from segmentation, use at
    # most one labelled tooth on the same arch near that expected position.
    # Never fill an arbitrary quota from the opposite arch or a distant tooth.
    for missing_fdi, arch in expected_missing:
        try:
            expected_index = arch.index(missing_fdi)
        except ValueError:
            continue
        candidates = []
        for fdi, candidate in by_fdi.items():
            if candidate in selected_set or candidate in competitors or fdi not in arch:
                continue
            try:
                pos_delta = abs(arch.index(fdi) - expected_index)
            except ValueError:
                continue
            if pos_delta > 2:
                continue
            candidates.append((pos_delta, candidate))
        if candidates:
            candidates.sort(key=lambda item: item[0])
            add(candidates[0][1])

    return competitors



def _immediate_active_jaw_bone(context, fdis):
    """Return the separate CBCT jaw surface used as buccal/lingual negative evidence."""
    from . import dicom_module
    scene = context.scene
    upper = any(int(fdi) < 30 for fdi in fdis)
    lower = any(int(fdi) >= 30 for fdi in fdis)
    if upper and lower:
        return None
    key = "DSG_maxilla_object" if upper else "DSG_mandible_object"
    fallback = dicom_module.NAME_DICOM_MAXILLA if upper else dicom_module.NAME_DICOM_MANDIBLE
    name = str(scene.get(key, "") or "")
    obj = bpy.data.objects.get(name) if name else None
    if obj is None:
        obj = bpy.data.objects.get(fallback)
    return obj if obj is not None and getattr(obj, "type", None) == "MESH" else None


def _simple_split_two_large_jaw_islands(context, surface):
    """Create maxilla/mandible display copies from the two largest loose islands.

    This is intentionally not semantic segmentation.  It uses Blender's native
    loose-part separation on the threshold STL and keeps only the two dominant
    connected components.  The original combined STL remains untouched as the
    alignment reference.
    """
    if surface is None or getattr(surface, "type", None) != "MESH":
        return {}
    scene = context.scene

    # Remove previous display split.
    for key in ("DSG_simple_maxilla_object", "DSG_simple_mandible_object"):
        old_name = str(scene.get(key, "") or "")
        old = bpy.data.objects.get(old_name) if old_name else None
        if old is not None:
            mesh = old.data if old.type == "MESH" else None
            bpy.data.objects.remove(old, do_unlink=True)
            if mesh is not None and mesh.users == 0:
                bpy.data.meshes.remove(mesh)
        scene[key] = ""

    before = set(bpy.data.objects)
    work = surface.copy()
    work.data = surface.data.copy()
    work.name = "DSG_Simple_Jaw_Split_Work"
    for collection in surface.users_collection:
        collection.objects.link(work)
    work.matrix_world = surface.matrix_world.copy()

    try:
        bpy.ops.object.mode_set(mode="OBJECT") if context.object and context.object.mode != "OBJECT" else None
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    bpy.ops.object.select_all(action="DESELECT")
    work.select_set(True)
    context.view_layer.objects.active = work
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.separate(type="LOOSE")
    bpy.ops.object.mode_set(mode="OBJECT")

    parts = [obj for obj in bpy.data.objects if obj not in before and obj.type == "MESH"]
    if work not in parts and work.name in bpy.data.objects:
        parts.append(work)
    # Rank by actual mesh size first, then physical extent.
    def rank(obj):
        verts = len(obj.data.vertices)
        dims = obj.dimensions
        extent = float(max(dims.x, dims.y, dims.z))
        return (verts, extent)
    parts = sorted({obj for obj in parts if obj is not None}, key=rank, reverse=True)

    if len(parts) < 2:
        for obj in parts:
            if obj is not work:
                bpy.data.objects.remove(obj, do_unlink=True)
        if work is not None and work.name in bpy.data.objects:
            bpy.data.objects.remove(work, do_unlink=True)
        scene["DSG_simple_jaw_split_status"] = "ONE_LARGE_ISLAND"
        return {}

    largest = parts[:2]
    for obj in parts[2:]:
        mesh = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        if mesh is not None and mesh.users == 0:
            bpy.data.meshes.remove(mesh)

    # DICOM surfaces are created in patient/world coordinates; superior is +Z.
    largest.sort(key=lambda obj: float((obj.matrix_world @ obj.data.vertices[0].co).z) if len(obj.data.vertices) else float(obj.location.z), reverse=True)
    # Use robust mean vertex Z rather than one vertex.
    def mean_world_z(obj):
        if not len(obj.data.vertices):
            return float(obj.location.z)
        step = max(1, len(obj.data.vertices) // 4000)
        vals = [(obj.matrix_world @ obj.data.vertices[i].co).z for i in range(0, len(obj.data.vertices), step)]
        return sum(vals) / max(1, len(vals))
    largest.sort(key=mean_world_z, reverse=True)
    upper, lower = largest[0], largest[1]

    upper.name = "DSG_CBCT_Simple_Maxilla"
    lower.name = "DSG_CBCT_Simple_Mandible"
    for obj, arch in ((upper, "MAXILLA"), (lower, "MANDIBLE")):
        obj["DSG_simple_jaw_island"] = True
        obj["DSG_simple_jaw_arch"] = arch
        obj["dental_suite_alignment_reference"] = False
        try:
            obj.hide_viewport = True
            obj.hide_render = True
            obj.hide_set(True)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)

    scene["DSG_simple_maxilla_object"] = upper.name
    scene["DSG_simple_mandible_object"] = lower.name
    scene["DSG_simple_jaw_split_status"] = "TWO_LARGEST_LOOSE_ISLANDS"
    scene["DSG_simple_jaw_split_vertices"] = json.dumps([len(upper.data.vertices), len(lower.data.vertices)])
    return {"upper": upper, "lower": lower}


class DSG_SUITE_OT_PrepareIOSPostExtraction(Operator):
    """Create a reversible IOS copy and seed its common CBCT crown surface."""

    bl_idname = "dsg_suite.prepare_ios_postextraction"
    bl_label = "Preparar selección IOS postextracción"
    bl_description = "Crea una copia IOS y selecciona la superficie común con el diente CBCT; refina con Ctrl+"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scene = context.scene
        fdis = _immediate_extraction_fdis(scene)
        props = getattr(scene, "dicp_props", None)
        source = getattr(props, "icp_source_obj", None) if props is not None else None
        if not fdis:
            self.report({"ERROR"}, "Primero elige el/los FDI a extraer")
            return {"CANCELLED"}
        if source is None or source.type != "MESH" or not bool(getattr(props, "aligned", False)):
            self.report({"ERROR"}, "Alinea y revisa el IOS con el CBCT antes de crear el IOS postextracción")
            return {"CANCELLED"}
        if not bool(getattr(props, "alignment_quality_approved", False)):
            self.report({"ERROR"}, "La alineación todavía no está validada; repite el alineamiento automático o usa el plan B de 3 zonas antes de buscar la superficie común")
            return {"CANCELLED"}
        teeth = _immediate_cbct_teeth(context, fdis)
        if len(teeth) != len(fdis):
            self.report({"ERROR"}, "Falta algún diente CBCT seleccionado; vuelve a revisar la segmentación FDI")
            return {"CANCELLED"}

        old_name = str(scene.get("DSG_ios_postextraction_preview_name", "") or "")
        old = bpy.data.objects.get(old_name) if old_name else None
        if old is not None:
            bpy.data.objects.remove(old, do_unlink=True)

        preview = source.copy()
        preview.data = source.data.copy()
        preview.name = "Dental_IOS_PostExtraction_Selection"
        for collection in source.users_collection:
            collection.objects.link(preview)
        preview.matrix_world = source.matrix_world.copy()
        preview["DSG_ios_postextraction_preview"] = True
        preview["DSG_ios_postextraction_fdis"] = json.dumps(fdis)
        preview["DSG_ios_postextraction_source"] = source.name
        preview["DSG_ios_postextraction_state"] = "SURFACE_SELECTION"

        # The selected CBCT tooth is positive evidence; its nearest mesial and
        # distal teeth are negative evidence.  This ownership pass runs first,
        # so crowded contact surfaces never receive an arbitrary broad seed.
        try:
            from . import common_surface_match
            neighbours = _immediate_neighbour_teeth(context, teeth)
            jaw_bone = _immediate_active_jaw_bone(context, fdis)
            p95 = max(0.0, float(getattr(props, "icp_p95", 0.0) or 0.0))
            distance_mm = max(0.68, min(1.10, 0.60 + 0.55 * p95))
            neighbour_fdis = [
                int(obj.get("DSG_fdi_number", 0) or 0) for obj in neighbours
                if int(obj.get("DSG_fdi_number", 0) or 0) > 0
            ]
            try:
                common_result = common_surface_match.select_anatomy_locked_ios_seed(
                    preview, teeth,
                    distance_mm=max(common_surface_match.LEGACY_COMPATIBLE_DISTANCE_MM, distance_mm),
                    max_components=len(fdis), competitor_teeth=neighbours,
                    bone_guard=jaw_bone,
                )
                if int(common_result.get("selected_count", 0) or 0) < common_surface_match.MIN_SELECTED_FACES:
                    raise RuntimeError("la frontera anatómica mesial/distal es insuficiente")
                common_result["selection_mode"] = "ANATOMY_LOCKED_MESIAL_DISTAL"
            except Exception as anatomy_exc:
                # Preserve the mesial/distal ownership test under crowding.
                # This relaxed pass accepts more aligned surface support but
                # still rejects faces won by the selected FDI neighbours.
                try:
                    common_result = common_surface_match.select_anatomy_locked_ios_seed(
                        preview, teeth,
                        distance_mm=min(1.34, max(1.02, distance_mm * 1.18)),
                        max_components=len(fdis), competitor_teeth=neighbours,
                        bone_guard=jaw_bone,
                        contact_margin_mm=0.10, minimum_normal_angle_deg=80.0,
                        sample_coverage=0.50, curvature_tie_limit=0.055,
                    )
                    common_result["selection_mode"] = "ANATOMY_LOCKED_CONTACT_REVIEW"
                    common_result["anatomy_boundary_review_required"] = True
                    common_result["anatomy_locked_initial_failure"] = str(anatomy_exc)
                except Exception as relaxed_exc:
                    # Third pass remains competitor-aware.  It widens only the
                    # surface support and normal tolerance; it never forgets
                    # mesial/distal ownership.
                    try:
                        common_result = common_surface_match.select_anatomy_locked_ios_seed(
                            preview, teeth,
                            distance_mm=min(1.48, max(1.16, distance_mm * 1.32)),
                            max_components=len(fdis), competitor_teeth=neighbours,
                            bone_guard=jaw_bone,
                            contact_margin_mm=0.08, minimum_normal_angle_deg=86.0,
                            sample_coverage=0.40, curvature_tie_limit=0.075,
                        )
                        common_result["selection_mode"] = "ANATOMY_LOCKED_SAFE_RECOVERY"
                        common_result["anatomy_boundary_review_required"] = True
                        common_result["anatomy_locked_initial_failure"] = str(anatomy_exc)
                        common_result["anatomy_locked_relaxed_failure"] = str(relaxed_exc)
                    except Exception as safe_exc:
                        # Absolute last-resort visual review.  Even this generic
                        # matcher receives competitor teeth and is forbidden from
                        # re-growing into a neighbouring crown.
                        common_result = common_surface_match.select_common_ios_surface(
                            preview, teeth,
                            distance_mm=min(1.22, max(1.00, distance_mm * 1.12)),
                            normal_angle_deg=min(66.0, common_surface_match.DEFAULT_NORMAL_ANGLE_DEG + 9.0),
                            score_threshold=max(0.52, common_surface_match.DEFAULT_SCORE_THRESHOLD - 0.08),
                            max_components=len(fdis), competitor_teeth=neighbours,
                            competitor_margin_mm=0.08,
                            bone_guard=jaw_bone,
                        )
                        common_result["anatomy_locked_safe_failure"] = str(safe_exc)
                        common_result["anatomy_locked_relaxed_failure"] = str(relaxed_exc)
                        common_result["selection_mode"] = "TARGET_GEOMETRY_NEIGHBOR_PROTECTED_REVIEW"
                        common_result["anatomy_boundary_review_required"] = True
                        common_result["anatomy_locked_failure"] = str(anatomy_exc)
                if int(common_result.get("selected_count", 0) or 0) < common_surface_match.MIN_SELECTED_FACES:
                    raise RuntimeError("frontera anatómica insuficiente; recuperación de revisión también insuficiente: " + str(anatomy_exc))
            common_result["competitor_fdis"] = neighbour_fdis
            common_result["competitor_names"] = [obj.name for obj in neighbours]
            common_result["bone_guard_name"] = str(jaw_bone.name) if jaw_bone is not None else ""
            selected_faces, selected_vertices = common_surface_match.apply_common_surface_selection(
                preview, common_result)
        except Exception as exc:
            bpy.data.objects.remove(preview, do_unlink=True)
            self.report({"ERROR"}, "No se detectó una superficie común IOS–CBCT fiable; revisa primero el alineamiento: " + str(exc))
            return {"CANCELLED"}

        source.hide_set(True)
        source.hide_render = True
        scene["DSG_ios_postextraction_source_name"] = source.name
        scene["DSG_ios_postextraction_preview_name"] = preview.name
        scene["DSG_ios_postextraction_confirmed"] = False
        scene["DSG_ios_postextraction_boolean_retry_available"] = False
        scene["DSG_ios_postextraction_closure_retry_available"] = False
        scene["DSG_ios_common_surface_stats"] = str(preview.get("DSG_common_surface_stats", ""))
        scene["DSG_ios_competitor_fdis"] = json.dumps(common_result.get("competitor_fdis", []))
        scene[ROUTE_STEP_KEY] = "IMMEDIATE_IOS_SURFACE_REVIEW"
        bpy.ops.object.select_all(action="DESELECT")
        preview.select_set(True)
        context.view_layer.objects.active = preview
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_mode(type="FACE")
        selection_mode = str(common_result.get("selection_mode", "PRECISE_GEOMATCH"))
        self.report({"INFO"}, (
            f"Superficie IOS detectada ({selection_mode}): {selected_faces} caras / {selected_vertices} vértices · "
            f"p95 {float(common_result.get('p95_distance_mm', 0.0)):.2f} mm. "
            "Revisa el límite cervical/contactos; Ctrl+ queda disponible solo si necesitas ajustar."
        ))
        return {"FINISHED"}


def _clean_postextraction_boolean_debris(obj) -> tuple[bool, dict]:
    """Remove disconnected Boolean debris before the anatomy-safe base closure.

    A segmented tooth can contain a pulp chamber or small closed shells.  An
    Exact Boolean may retain those shells as disconnected islands inside the
    IOS after subtraction.  They are clinically useless and make subsequent
    sleeve/guide Boolean work unreliable.  Keep only the external anatomical
    component and remove loose topology.  The separate closed-model pipeline
    then closes secondary holes and builds the basal wall; it is deliberately
    not replaced by a flat cap over the main IOS boundary.
    """
    diagnostics = {
        "islands_removed": 0,
        "island_faces_removed": 0,
        "loose_edges_removed": 0,
        "loose_vertices_removed": 0,
        "boundary_edges_remaining": 0,
        "non_manifold_edges_remaining": 0,
    }
    if obj is None or obj.type != "MESH" or obj.data is None:
        return False, {**diagnostics, "reason": "IOS postextracción no válido"}

    try:
        # Reuse DSG's tested disconnected-shell cleaner.  The IOS is one
        # clinical scan, so after an extraction Boolean only its main external
        # component is a valid planning surface.
        from . import guide_module
        ok, message, faces_removed, components_removed = (
            guide_module.remove_disconnected_islands_keep_largest(
                obj, reason="ios_postextraction_boolean", max_vertices=3_500_000
            )
        )
        diagnostics["islands_removed"] = int(components_removed)
        diagnostics["island_faces_removed"] = int(faces_removed)
        diagnostics["island_cleanup"] = str(message)
        if not ok:
            return False, {**diagnostics, "reason": str(message)}
    except Exception as exc:
        return False, {**diagnostics, "reason": f"limpieza de islas falló: {exc}"}

    bm = bmesh.new()
    try:
        bm.from_mesh(obj.data)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()

        loose_edges = [edge for edge in bm.edges if not edge.link_faces]
        if loose_edges:
            diagnostics["loose_edges_removed"] = len(loose_edges)
            bmesh.ops.delete(bm, geom=loose_edges, context="EDGES")
        loose_vertices = [vert for vert in bm.verts if not vert.link_edges]
        if loose_vertices:
            diagnostics["loose_vertices_removed"] = len(loose_vertices)
            bmesh.ops.delete(bm, geom=loose_vertices, context="VERTS")

        if bm.faces:
            bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        bm.to_mesh(obj.data)
    except Exception as exc:
        return False, {**diagnostics, "reason": f"limpieza topológica falló: {exc}"}
    finally:
        bm.free()

    obj.data.validate(clean_customdata=False)
    obj.data.update(calc_edges=True)
    verify = bmesh.new()
    try:
        verify.from_mesh(obj.data)
        boundary_count = sum(1 for edge in verify.edges if len(edge.link_faces) == 1)
        non_manifold_count = sum(1 for edge in verify.edges if len(edge.link_faces) != 2)
    finally:
        verify.free()
    diagnostics["boundary_edges_remaining"] = int(boundary_count)
    diagnostics["non_manifold_edges_remaining"] = int(non_manifold_count)
    diagnostics["closed_before_base"] = not boundary_count and not non_manifold_count
    obj["DSG_postextraction_boolean_cleanup"] = json.dumps(diagnostics, ensure_ascii=False)
    obj["DSG_postextraction_boolean_islands_removed"] = int(diagnostics["islands_removed"])
    return True, diagnostics


def _edge_components_for_local_closure(edges):
    """Return connected boundary-edge components without touching coordinates."""
    remaining = set(edges)
    components = []
    while remaining:
        start = remaining.pop()
        component = {start}
        frontier = [start]
        while frontier:
            edge = frontier.pop()
            linked = {other for vert in edge.verts for other in vert.link_edges if other in remaining}
            if linked:
                remaining.difference_update(linked)
                component.update(linked)
                frontier.extend(linked)
        components.append(component)
    return components




def _bmesh_face_neighbours(face):
    return {
        other
        for edge in face.edges
        for other in edge.link_faces
        if other is not face
    }


def _solidify_local_extraction_selection_bmesh(bm, chosen, *, max_majority_passes=3):
    """Fill internal selection voids before deleting the IOS crown.

    This is the safe equivalent of repeatedly pressing Ctrl+ / Fill Selection:
    enclosed black islands and narrow one/two-face cracks are absorbed, but the
    operation does not blindly grow the entire cervical perimeter outwards.
    """
    selected = set(chosen)
    requested = len(selected)
    majority_added = 0
    enclosed_added = 0
    enclosed_components = 0

    # First close obvious pinholes/narrow cracks.  Faces fully surrounded by the
    # selection are always safe.  A 2/3 bridge is accepted only when most of its
    # vertices already belong to the selected patch, which avoids a global grow.
    for _ in range(max(0, int(max_majority_passes))):
        selected_vertices = {vert for face in selected for vert in face.verts}
        frontier = {
            neighbour
            for face in selected
            for neighbour in _bmesh_face_neighbours(face)
            if neighbour not in selected
        }
        add = set()
        for face in frontier:
            neighbours = _bmesh_face_neighbours(face)
            if not neighbours:
                continue
            inside = sum(1 for neighbour in neighbours if neighbour in selected)
            degree = len(neighbours)
            selected_vertex_ratio = (
                sum(1 for vert in face.verts if vert in selected_vertices)
                / float(max(len(face.verts), 1))
            )
            fully_surrounded = degree >= 2 and inside == degree
            narrow_gap = (
                inside >= 2
                and inside / float(degree) >= 0.66
                and selected_vertex_ratio >= 0.75
            )
            if fully_surrounded or narrow_gap:
                add.add(face)
        if not add:
            break
        selected.update(add)
        majority_added += len(add)

    # Then fill true unselected islands enclosed by the reviewed crown patch.
    # The huge exterior component is rejected by the adaptive cap; components
    # touching a pre-existing open IOS border are never consumed.
    boundary_faces = {
        face for face in bm.faces
        if any(len(edge.link_faces) == 1 for edge in face.edges)
    }
    cap = max(512, min(16000, int(round(max(len(selected), 1) * 0.55))))
    seeds = {
        neighbour
        for face in selected
        for neighbour in _bmesh_face_neighbours(face)
        if neighbour not in selected
    }
    visited = set()
    fill = set()
    for seed in list(seeds):
        if seed in visited or seed in selected:
            continue
        component = {seed}
        frontier = [seed]
        visited.add(seed)
        touches_open = seed in boundary_faces
        escaped = False
        while frontier:
            current = frontier.pop()
            for neighbour in _bmesh_face_neighbours(current):
                if neighbour in selected or neighbour in visited:
                    continue
                visited.add(neighbour)
                component.add(neighbour)
                if neighbour in boundary_faces:
                    touches_open = True
                if len(component) > cap:
                    escaped = True
                    frontier.clear()
                    break
                frontier.append(neighbour)
        if escaped or touches_open or len(component) > cap:
            continue
        if any(_bmesh_face_neighbours(face) & selected for face in component):
            fill.update(component)
            enclosed_components += 1

    if fill:
        selected.update(fill)
        enclosed_added = len(fill)

    # One last conservative pinhole pass after filling enclosed islands.
    selected_vertices = {vert for face in selected for vert in face.verts}
    frontier = {
        neighbour
        for face in selected
        for neighbour in _bmesh_face_neighbours(face)
        if neighbour not in selected
    }
    final_add = set()
    for face in frontier:
        neighbours = _bmesh_face_neighbours(face)
        if not neighbours:
            continue
        inside = sum(1 for neighbour in neighbours if neighbour in selected)
        if inside == len(neighbours) and len(neighbours) >= 2:
            final_add.add(face)
        elif inside >= 2:
            ratio = sum(1 for vert in face.verts if vert in selected_vertices) / float(max(len(face.verts), 1))
            if ratio >= 0.90:
                final_add.add(face)
    if final_add:
        selected.update(final_add)
        majority_added += len(final_add)

    return selected, {
        "selection_faces_before_fill": int(requested),
        "selection_pinhole_faces_added": int(majority_added),
        "selection_enclosed_faces_added": int(enclosed_added),
        "selection_enclosed_components_added": int(enclosed_components),
        "selection_faces_after_fill": int(len(selected)),
    }


def _ordered_cycle_vertices_for_local_closure(component):
    """Return an ordered simple cycle for a degree-2 boundary component."""
    component = set(component)
    if len(component) < 3:
        return None
    linked = {}
    for edge in component:
        for vert in edge.verts:
            linked.setdefault(vert, []).append(edge)
    if any(len(edges) != 2 for edges in linked.values()):
        return None

    start_edge = next(iter(component))
    start_vert = start_edge.verts[0]
    current_vert = start_edge.verts[1]
    ordered = [start_vert, current_vert]
    previous_edge = start_edge
    used_edges = {start_edge}

    while current_vert is not start_vert:
        candidates = [edge for edge in linked[current_vert] if edge is not previous_edge]
        if len(candidates) != 1:
            return None
        edge = candidates[0]
        if edge in used_edges:
            # The only legal repeated edge would be the starting edge, but that
            # is excluded above by previous_edge on the closing vertex.
            return None
        next_vert = edge.other_vert(current_vert)
        used_edges.add(edge)
        if next_vert is start_vert:
            break
        if next_vert in ordered:
            return None
        ordered.append(next_vert)
        previous_edge = edge
        current_vert = next_vert
        if len(used_edges) > len(component):
            return None

    if len(used_edges) != len(component) or len(ordered) != len(component):
        return None
    return ordered


def _exact_close_simple_edge_loop(bm, component):
    """Close a simple boundary cycle deterministically, preserving every edge."""
    component = set(component)
    ordered = _ordered_cycle_vertices_for_local_closure(component)
    if not ordered:
        return False, 0, ""
    before = len(bm.faces)
    created_face = None
    try:
        created_face = bm.faces.new(ordered)
        bm.normal_update()
        # A single n-gon created from the ordered loop must immediately give
        # every original perimeter edge its second linked face.  Verify that
        # invariant *before* optional triangulation so no partial triangulation
        # can obscure the transaction boundary.
        if all(getattr(edge, "is_valid", False) and len(edge.link_faces) >= 2 for edge in component):
            method = "exact_ngon"
            try:
                bmesh.ops.triangulate(
                    bm, faces=[created_face], quad_method="BEAUTY", ngon_method="BEAUTY")
                method = "exact_ngon_triangulated"
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
            return True, max(1, len(bm.faces) - before), method
        if getattr(created_face, "is_valid", False):
            bmesh.ops.delete(bm, geom=[created_face], context="FACES")
    except Exception:
        if created_face is not None and getattr(created_face, "is_valid", False):
            try:
                bmesh.ops.delete(bm, geom=[created_face], context="FACES")
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)

    # Last deterministic fallback: a centre fan.  It guarantees that every edge
    # in a simple cycle receives its second linked face.  This cap is temporary
    # geometry used only to make the subsequent tooth Boolean well-defined.
    centre_vert = None
    made_faces = []
    try:
        centre = Vector((0.0, 0.0, 0.0))
        for vert in ordered:
            centre += vert.co
        centre /= float(len(ordered))
        centre_vert = bm.verts.new(centre)
        for edge in component:
            first, second = edge.verts
            face = None
            try:
                face = bm.faces.new((first, second, centre_vert))
            except ValueError:
                try:
                    face = bm.faces.new((second, first, centre_vert))
                except Exception:
                    face = None
            except Exception:
                face = None
            if face is not None:
                made_faces.append(face)
        bm.normal_update()
        if made_faces and all(getattr(edge, "is_valid", False) and len(edge.link_faces) >= 2 for edge in component):
            return True, max(len(made_faces), len(bm.faces) - before), "exact_center_fan"
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)

    # Roll back an incomplete fan so later fallbacks see the original boundary.
    valid_faces = [face for face in made_faces if getattr(face, "is_valid", False)]
    if valid_faces:
        try:
            bmesh.ops.delete(bm, geom=valid_faces, context="FACES")
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    if centre_vert is not None and getattr(centre_vert, "is_valid", False) and not centre_vert.link_faces:
        try:
            bmesh.ops.delete(bm, geom=[centre_vert], context="VERTS")
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    return False, max(0, len(bm.faces) - before), ""


def _local_open_components_from_seeds(bm, seed_edges, excluded_edges):
    """Find actual residual local hole loops, including fill-created edges."""
    boundary = {
        edge for edge in bm.edges
        if getattr(edge, "is_valid", False)
        and len(edge.link_faces) == 1
        and edge not in excluded_edges
    }
    seeds = {edge for edge in seed_edges if edge in boundary}
    if not seeds:
        return []
    all_components = _edge_components_for_local_closure(boundary)
    return [component for component in all_components if component & seeds]


def _regularize_local_extraction_faces(bm, chosen, *, max_passes=8):
    """Trim only unsafe boundary faces until the extraction perimeter is cyclic.

    The common-surface detector can legitimately reach a pre-existing open IOS
    border or create a small T-junction around contacts.  Deleting such a region
    produces an open/branched perimeter that no local hole filler can close
    reliably.  Instead of failing after destruction, regularise the reviewed
    region *before* deletion by eroding only faces responsible for those unsafe
    boundary conditions.  Interior selected faces are never grown here.
    """
    selected = set(chosen)
    requested = len(selected)
    passes = 0
    removed_total = 0
    last_reason = ""

    for _ in range(max(1, int(max_passes))):
        if len(selected) < 4:
            break
        passes += 1
        bad_faces = set()

        # A local crown cut must not terminate on an opening that already existed
        # in the IOS.  Erode the selected side away from those scan boundaries.
        for face in selected:
            if any(len(edge.link_faces) == 1 for edge in face.edges):
                bad_faces.add(face)
        if bad_faces:
            last_reason = "preexisting_open_border"

        perimeter = []
        for edge in bm.edges:
            linked_selected = [face for face in edge.link_faces if face in selected]
            if not linked_selected:
                continue
            linked_unselected = [face for face in edge.link_faces if face not in selected]
            if linked_unselected:
                perimeter.append(edge)

        degree = {}
        for edge in perimeter:
            for vert in edge.verts:
                degree[vert] = degree.get(vert, 0) + 1
        bad_vertices = {vert for vert, value in degree.items() if value != 2}
        if bad_vertices:
            last_reason = "branched_or_open_interface"
            for edge in perimeter:
                if any(vert in bad_vertices for vert in edge.verts):
                    bad_faces.update(face for face in edge.link_faces if face in selected)

        if not bad_faces and perimeter and all(value == 2 for value in degree.values()):
            return selected, {
                "selection_faces_requested": int(requested),
                "selection_faces_trimmed": int(removed_total),
                "selection_regularization_passes": int(max(0, passes - 1)),
                "selection_regularization_reason": "closed_cycle",
            }

        if not bad_faces:
            last_reason = last_reason or "no_closed_interface"
            break

        # One conservative erosion ring per pass.  If the detector touched a
        # basal/open edge, this usually removes only a narrow strip of faces.
        removable = {face for face in bad_faces if face in selected}
        if not removable or len(selected) - len(removable) < 4:
            break
        selected.difference_update(removable)
        removed_total += len(removable)

    return selected, {
        "selection_faces_requested": int(requested),
        "selection_faces_trimmed": int(removed_total),
        "selection_regularization_passes": int(passes),
        "selection_regularization_reason": str(last_reason or "unable_to_regularize"),
    }

def _delete_selected_ios_region_and_close_local_openings(context, preview) -> dict:
    """Delete reviewed IOS crown faces and close only the newly created opening.

    The key invariant is that only the *actual interface edges* of the reviewed
    selection are audited after filling.  Previous code re-detected every open
    edge whose endpoints happened to belong to perimeter vertices, which could
    report unrelated edges as a failed local closure (the observed "18 edges"
    false failure).  This version tracks the exact BMEdge objects transactionally
    and applies several local-only fill strategies before giving up.
    """
    if preview is None or preview.type != "MESH" or preview.data is None:
        raise RuntimeError("IOS postextracción no válido")
    if context.mode != "EDIT_MESH" or context.edit_object is not preview:
        raise RuntimeError("Revisa la selección sobre el IOS postextracción en modo Edición")

    edit_bm = bmesh.from_edit_mesh(preview.data)
    edit_bm.faces.ensure_lookup_table()
    selected_indices = [int(face.index) for face in edit_bm.faces if face.select]
    if len(selected_indices) < 4:
        raise RuntimeError("La selección IOS es demasiado pequeña; expándela/refínala antes de confirmar")

    bmesh.update_edit_mesh(preview.data, loop_triangles=False, destructive=False)
    bpy.ops.object.mode_set(mode="OBJECT")

    bm = bmesh.new()
    diagnostics = {
        "selected_faces_requested": int(len(selected_indices)),
        "selected_faces_deleted": 0,
        "selection_faces_before_fill": int(len(selected_indices)),
        "selection_pinhole_faces_added": 0,
        "selection_enclosed_faces_added": 0,
        "selection_enclosed_components_added": 0,
        "selection_faces_after_fill": int(len(selected_indices)),
        "selection_faces_trimmed": 0,
        "selection_regularization_passes": 0,
        "selection_regularization_reason": "",
        "local_boundary_components": 0,
        "local_boundary_edges": 0,
        "local_fill_faces_created": 0,
        "remaining_local_boundary_edges": 0,
        "local_fill_passes": 0,
        "local_fill_method": [],
        "residual_local_components_repaired": 0,
        "residual_local_edges_repaired": 0,
    }
    try:
        bm.from_mesh(preview.data)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        chosen = [bm.faces[index] for index in selected_indices if 0 <= index < len(bm.faces)]
        if len(chosen) != len(selected_indices):
            raise RuntimeError("La topología IOS cambió durante la revisión; vuelve a detectar la superficie común")

        # The reviewed selection must be a solid tooth patch.  Automatically fill
        # internal black islands and narrow cracks before deriving the cervical
        # perimeter.  This reproduces the useful inward effect of Ctrl+/Fill
        # Selection without globally expanding the outer border.
        chosen_set, fill_selection_diag = _solidify_local_extraction_selection_bmesh(
            bm, chosen, max_majority_passes=3)
        diagnostics.update(fill_selection_diag)

        chosen_set, regularization = _regularize_local_extraction_faces(bm, chosen_set, max_passes=8)
        diagnostics.update(regularization)
        diagnostics["selected_faces_deleted"] = int(len(chosen_set))
        if len(chosen_set) < 4:
            raise RuntimeError(
                "La selección común alcanza un borde abierto del IOS y no puede formar un ciclo cervical seguro; "
                "vuelve a detectar/refinar la superficie"
            )

        perimeter_edges = set()
        for face in chosen_set:
            for edge in face.edges:
                if any(linked not in chosen_set for linked in edge.link_faces):
                    perimeter_edges.add(edge)
        if not perimeter_edges:
            raise RuntimeError("No se encontró un contorno cervical/contacto cerrado para la selección IOS")

        # Keep exact edge references. Deleting faces leaves these interface edges
        # alive; a successful fill simply gives them a second linked face.  Also
        # remember every boundary that existed *before* extraction so residual
        # repair can never accidentally cap the basal/open scan boundary.
        tracked_perimeter = set(perimeter_edges)
        preexisting_open_edges = {edge for edge in bm.edges if len(edge.link_faces) == 1}
        bmesh.ops.delete(bm, geom=list(chosen_set), context="FACES")
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()

        def open_tracked_edges():
            return [
                edge for edge in tracked_perimeter
                if getattr(edge, 'is_valid', False) and len(edge.link_faces) == 1
            ]

        local_boundary = open_tracked_edges()
        if not local_boundary:
            # Deletion can exceptionally remove/dissolve all interface edges; if
            # there is no new tracked boundary, the local region is already closed.
            diagnostics["local_boundary_components"] = 0
            diagnostics["local_boundary_edges"] = 0
        else:
            components = _edge_components_for_local_closure(local_boundary)
            diagnostics["local_boundary_components"] = int(len(components))
            diagnostics["local_boundary_edges"] = int(len(local_boundary))

            created_total = 0
            for component in components:
                degree = {}
                for edge in component:
                    for vert in edge.verts:
                        degree[vert] = degree.get(vert, 0) + 1
                if any(value != 2 for value in degree.values()):
                    raise RuntimeError(
                        "El contorno IOS seleccionado está abierto o ramificado; revisa solo el límite cervical/contactos")

                # First use an exact ordered-loop cap.  Unlike triangle_fill, this
                # cannot leave a handful of original perimeter edges unlinked when
                # Blender partially triangulates a difficult non-planar loop.
                exact_ok, exact_created, exact_method = _exact_close_simple_edge_loop(bm, component)
                if exact_ok:
                    created_total += int(exact_created)
                    diagnostics["local_fill_method"].append(exact_method)
                    continue

                before = len(bm.faces)
                created = []
                try:
                    result = bmesh.ops.triangle_fill(
                        bm, edges=list(component), use_beauty=True, use_dissolve=False)
                    created = [geom for geom in result.get("geom", ()) if isinstance(geom, bmesh.types.BMFace)]
                    if created:
                        diagnostics["local_fill_method"].append("triangle_fill")
                except Exception:
                    created = []
                if not created:
                    try:
                        result = bmesh.ops.holes_fill(bm, edges=list(component), sides=0)
                        created = list(result.get("faces", ()))
                        if created:
                            diagnostics["local_fill_method"].append("holes_fill")
                    except Exception:
                        created = []
                if not created:
                    try:
                        op = getattr(bmesh.ops, "edgenet_fill", None)
                        if op is not None:
                            result = op(bm, edges=list(component), mat_nr=0, use_smooth=False, sides=0)
                            created = list(result.get("faces", ()))
                            if created:
                                diagnostics["local_fill_method"].append("edgenet_fill")
                    except Exception:
                        created = []
                if not created:
                    try:
                        result = bmesh.ops.contextual_create(bm, geom=list(component))
                        created = [geom for geom in result.get("geom", ()) if isinstance(geom, bmesh.types.BMFace)]
                        if created:
                            diagnostics["local_fill_method"].append("contextual_create")
                    except Exception:
                        created = []
                created_total += max(len(created), len(bm.faces) - before)

            # Retry only the still-open tracked perimeter, never the basal IOS
            # boundary or any unrelated pre-existing scan opening.
            for retry in range(2):
                remaining = open_tracked_edges()
                if not remaining:
                    break
                diagnostics["local_fill_passes"] += 1
                retry_components = _edge_components_for_local_closure(remaining)
                progress = False
                for component in retry_components:
                    degree = {}
                    for edge in component:
                        for vert in edge.verts:
                            degree[vert] = degree.get(vert, 0) + 1
                    if any(value != 2 for value in degree.values()):
                        continue
                    before = len(bm.faces)
                    try:
                        result = bmesh.ops.holes_fill(bm, edges=list(component), sides=0)
                        made = list(result.get("faces", ()))
                    except Exception:
                        made = []
                    if made or len(bm.faces) > before:
                        progress = True
                        created_total += max(len(made), len(bm.faces) - before)
                        diagnostics["local_fill_method"].append("retry_holes_fill")
                if not progress:
                    break

            # A partial Blender fill can close most of the original loop while
            # leaving a tiny residual hole whose boundary now includes newly
            # created internal edges.  Looking only at tracked_perimeter then sees
            # chains such as the reported 8 edges.  Reconstruct the *actual* local
            # residual boundary, excluding every open edge that pre-dated the
            # extraction, and close those simple cycles deterministically.
            remaining = open_tracked_edges()
            if remaining:
                residual_components = _local_open_components_from_seeds(
                    bm, remaining, preexisting_open_edges)
                for component in residual_components:
                    repaired_edges = len(component)
                    ok, made, method = _exact_close_simple_edge_loop(bm, component)
                    if ok:
                        diagnostics["residual_local_components_repaired"] += 1
                        diagnostics["residual_local_edges_repaired"] += int(repaired_edges)
                        diagnostics["local_fill_method"].append("residual_" + method)
                        created_total += int(made)

            diagnostics["local_fill_faces_created"] = int(created_total)

        try:
            if bm.faces:
                bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        bm.normal_update()
        remaining = open_tracked_edges()
        diagnostics["remaining_local_boundary_edges"] = int(len(remaining))
        if remaining:
            raise RuntimeError(
                f"El cierre local conserva {len(remaining)} aristas después del cierre exacto de loops. "
                "Esto indica un contorno no cíclico/no-manifold real; vuelve a detectar la superficie común antes de continuar")

        bm.to_mesh(preview.data)
        preview.data.validate(clean_customdata=False)
        preview.data.update(calc_edges=True)
    finally:
        bm.free()

    preview["DSG_ios_postextraction_state"] = "LOCAL_CROWN_CLOSED"
    preview["DSG_ios_local_closure_diagnostics"] = json.dumps(diagnostics, ensure_ascii=False)
    return diagnostics


class DSG_SUITE_OT_ConfirmIOSPostExtraction(Operator):
    """Delete the reviewed IOS crown region, close it, then subtract CBCT teeth."""

    bl_idname = "dsg_suite.confirm_ios_postextraction"
    bl_label = "Confirmar IOS postextracción"
    bl_description = "Elimina la selección IOS, cierra el contorno y aplica la booleana alveolar CBCT"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scene = context.scene
        fdis = _immediate_extraction_fdis(scene)
        name = str(scene.get("DSG_ios_postextraction_preview_name", "") or "")
        preview = bpy.data.objects.get(name) if name else None
        if preview is None or preview.type != "MESH":
            self.report({"ERROR"}, "Primero prepara y revisa la selección de superficie IOS")
            return {"CANCELLED"}
        teeth = _immediate_cbct_teeth(context, fdis)
        if not teeth:
            self.report({"ERROR"}, "No hay dientes CBCT para la booleana alveolar")
            return {"CANCELLED"}

        # A failed Boolean or final closure must be retryable without repeating
        # already completed destructive work.  The preview is a disposable IOS
        # copy, but each transition is still explicit and idempotent.
        closure_retry = bool(preview.get("DSG_ios_postextraction_boolean_ready", False))
        state = str(preview.get("DSG_ios_postextraction_state", "SURFACE_SELECTION") or "SURFACE_SELECTION")
        cleanup = {}
        if not closure_retry:
            if state not in {"LOCAL_CROWN_CLOSED", "BOOLEAN_APPLIED"}:
                try:
                    local_closure = _delete_selected_ios_region_and_close_local_openings(context, preview)
                except Exception as exc:
                    try:
                        bpy.ops.object.select_all(action="DESELECT")
                        preview.select_set(True)
                        context.view_layer.objects.active = preview
                        bpy.ops.object.mode_set(mode="EDIT")
                        bpy.ops.mesh.select_mode(type="FACE")
                    except Exception:
                        _DSG_LOG.debug("suppressed exception", exc_info=True)
                    self.report({"ERROR"}, f"No se pudo preparar la extracción virtual: {exc}")
                    return {"CANCELLED"}
                preview["DSG_ios_postextraction_state"] = "LOCAL_CROWN_CLOSED"
                preview["DSG_ios_local_closure_diagnostics"] = json.dumps(local_closure, ensure_ascii=False)
                state = "LOCAL_CROWN_CLOSED"
            elif context.mode == "EDIT_MESH":
                bpy.ops.object.mode_set(mode="OBJECT")

            bpy.ops.object.select_all(action="DESELECT")
            preview.select_set(True)
            context.view_layer.objects.active = preview
            try:
                applied_fdis = {
                    int(value) for value in json.loads(
                        str(preview.get("DSG_ios_postextraction_boolean_fdis_json", "[]") or "[]"))
                }
            except Exception:
                applied_fdis = set()

            for tooth in teeth:
                fdi = int(tooth.get("DSG_fdi_number", 0) or 0)
                if fdi in applied_fdis:
                    continue
                modifier = preview.modifiers.new(name=f"DSG_Alveolo_CBCT_FDI_{fdi}", type="BOOLEAN")
                modifier.operation = "DIFFERENCE"
                modifier.solver = "EXACT"
                modifier.object = tooth
                try:
                    bpy.ops.object.modifier_apply(modifier=modifier.name)
                except Exception as exc:
                    try:
                        preview.modifiers.remove(modifier)
                    except Exception:
                        _DSG_LOG.debug("suppressed exception", exc_info=True)
                    preview["DSG_ios_postextraction_state"] = "LOCAL_CROWN_CLOSED"
                    preview["DSG_ios_postextraction_boolean_fdis_json"] = json.dumps(sorted(applied_fdis))
                    scene["DSG_ios_postextraction_boolean_retry_available"] = True
                    self.report({"ERROR"}, f"Falló la booleana alveolar FDI {fdi}: {exc}. Pulsa REINTENTAR EXTRACCIÓN.")
                    return {"CANCELLED"}
                applied_fdis.add(fdi)
                preview["DSG_ios_postextraction_boolean_fdis_json"] = json.dumps(sorted(applied_fdis))

            preview["DSG_ios_postextraction_state"] = "BOOLEAN_APPLIED"
            cleaned, cleanup = _clean_postextraction_boolean_debris(preview)
            if not cleaned:
                scene["DSG_ios_postextraction_boolean_retry_available"] = True
                self.report({"ERROR"}, "La booleana terminó, pero no se pudo limpiar el IOS: " + str(cleanup.get("reason", "error topológico")) + ". Pulsa REINTENTAR EXTRACCIÓN.")
                return {"CANCELLED"}
            preview["DSG_ios_postextraction_boolean_ready"] = True
            preview["DSG_ios_postextraction_state"] = "BOOLEAN_READY"
            preview["DSG_postextraction_boolean_cleanup"] = json.dumps(cleanup, ensure_ascii=False)
            scene["DSG_ios_postextraction_boolean_retry_available"] = False
        else:
            try:
                cleanup = json.loads(str(preview.get("DSG_postextraction_boolean_cleanup", "{}") or "{}"))
            except Exception:
                cleanup = {"reused_boolean": True}

        # Boolean cleanup and model closure have distinct responsibilities:
        # this call protects the dental anatomy, preserves the principal basal
        # opening while closing safe secondary holes, then creates the proper
        # DSG closed-model base.  It replaces the previous manual red button
        # for this specific immediate post-extraction route.
        try:
            from . import guide_module
            repaired, hole_diagnostics = guide_module.close_scanned_model_holes(context, preview)
            closed_model, topology = guide_module.close_open_dental_model_base(context, repaired)
        except Exception as exc:
            preview["DSG_ios_postextraction_state"] = "BOOLEAN_READY"
            scene["DSG_ios_postextraction_closure_retry_available"] = True
            self.report({"ERROR"}, f"La extracción virtual está aplicada, pero falló el cierre automático del modelo: {exc}. Pulsa REINTENTAR CIERRE.")
            return {"CANCELLED"}
        if not bool(topology.get("solid", False)):
            self.report({"ERROR"}, "El cierre del modelo postextracción no pudo verificarse como manifold")
            return {"CANCELLED"}
        preview = closed_model
        preview.name = "Dental_IOS_PostExtraction_Closed"
        preview["DSG_postextraction_boolean_cleanup"] = json.dumps(cleanup, ensure_ascii=False)
        preview["DSG_postextraction_boolean_islands_removed"] = int(cleanup.get("islands_removed", 0))
        preview["DSG_postextraction_closed_model"] = True
        preview["DSG_postextraction_closure_topology"] = json.dumps({
            "boundary_edges": int(topology.get("boundary_edges", 0) or 0),
            "branch_edges": int(topology.get("branch_edges", 0) or 0),
            "wire_edges": int(topology.get("wire_edges", 0) or 0),
            "solid": bool(topology.get("solid", False)),
        }, ensure_ascii=False)

        preview.data.validate(verbose=False)
        preview.data.update()
        preview["DSG_ios_postextraction_state"] = "CLOSED_REVIEW_REQUIRED"
        preview["DSG_ios_postextraction_confirmed"] = True
        preview["DSG_ios_postextraction_support_exclusion_fdis"] = json.dumps(fdis)
        set_role(preview, ROLE_IOS_ALIGNED, rename=False)
        props = getattr(scene, "dicp_props", None)
        if props is not None:
            props.icp_source_obj = preview
        scene["DSG_ios_postextraction_preview_name"] = preview.name
        scene["DSG_ios_postextraction_confirmed"] = True
        scene["DSG_ios_postextraction_boolean_retry_available"] = False
        scene["DSG_ios_postextraction_closure_retry_available"] = False
        scene[ROUTE_STEP_KEY] = "IMMEDIATE_IOS_POSTEXTRACTION_READY"
        self.report({"WARNING"}, f"IOS postextracción cerrado. Se eliminaron {int(cleanup.get('islands_removed', 0))} islas; revisa el alvéolo virtual antes de continuar al diseño de la guía.")
        return {"FINISHED"}


class DSG_SUITE_OT_RestoreIOSPreExtraction(Operator):
    bl_idname = "dsg_suite.restore_ios_preextraction"
    bl_label = "Restaurar IOS preextracción"
    bl_description = "Descarta el resultado virtual y recupera el IOS alineado original"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scene = context.scene
        preview = bpy.data.objects.get(str(scene.get("DSG_ios_postextraction_preview_name", "") or ""))
        source = bpy.data.objects.get(str(scene.get("DSG_ios_postextraction_source_name", "") or ""))
        if preview is not None:
            bpy.data.objects.remove(preview, do_unlink=True)
        if source is not None:
            source.hide_set(False)
            source.hide_render = False
            props = getattr(scene, "dicp_props", None)
            if props is not None:
                props.icp_source_obj = source
        scene["DSG_ios_postextraction_preview_name"] = ""
        scene["DSG_ios_postextraction_confirmed"] = False
        scene["DSG_ios_postextraction_boolean_retry_available"] = False
        scene["DSG_ios_postextraction_closure_retry_available"] = False
        scene[ROUTE_STEP_KEY] = "ALIGNMENT"
        self.report({"INFO"}, "IOS preextracción restaurado")
        return {"FINISHED"}



# =============================================================================
# DSG 9.2.5 · DICOM laterality fix + deterministic navigation + stage-scoped restart
# =============================================================================

def _remove_object_and_data(obj) -> None:
    """Remove one generated Blender object and orphaned local datablock safely."""
    if obj is None:
        return
    data = getattr(obj, "data", None)
    kind = str(getattr(obj, "type", "") or "")
    try:
        bpy.data.objects.remove(obj, do_unlink=True)
    except Exception:
        return
    if data is not None and getattr(data, "users", 1) == 0:
        try:
            if kind == "MESH":
                bpy.data.meshes.remove(data)
            elif kind in {"FONT", "CURVE"}:
                bpy.data.curves.remove(data)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)


def _clear_immediate_review_geometry(context, *, restore_teeth: bool = True) -> None:
    """Clear only immediate-route review composites, never the raw CBCT volume."""
    scene = context.scene
    for key in ("DSG_immediate_upper_composite", "DSG_immediate_lower_composite"):
        name = str(scene.get(key, "") or "")
        obj = bpy.data.objects.get(name) if name else None
        _remove_object_and_data(obj)
        scene[key] = ""
    if restore_teeth:
        try:
            from . import cbct_dental_module
            for tooth in cbct_dental_module.dentition_objects(context):
                try:
                    tooth.hide_viewport = False
                    tooth.hide_render = False
                    tooth.hide_select = False
                    tooth.hide_set(False)
                except Exception:
                    _DSG_LOG.debug("suppressed exception", exc_info=True)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    scene[IMMEDIATE_FDIS_KEY] = "[]"
    scene["DSG_immediate_extraction_fdis"] = ""
    scene["DSG_immediate_extraction_prepared"] = False
    scene["DSG_route_review_required"] = False


class DSG_SUITE_OT_RecoverImmediateInputs(Operator):
    """Recover from an interrupted immediate case without repeating CBCT AI."""

    bl_idname = "dsg_suite.recover_immediate_inputs"
    bl_label = "Recover Immediate Inputs"
    bl_description = "Clears stale alignment references and returns to tooth selection without resegmenting CBCT"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scene = context.scene
        _clear_immediate_review_geometry(context, restore_teeth=True)
        props = getattr(scene, "dicp_props", None)
        if props is not None:
            for name, value in (("aligned", False), ("alignment_quality_approved", False)):
                try:
                    setattr(props, name, value)
                except Exception:
                    _DSG_LOG.debug("suppressed exception", exc_info=True)
            for name in ("icp_source_obj", "icp_target_obj"):
                try:
                    setattr(props, name, None)
                except Exception:
                    _DSG_LOG.debug("suppressed exception", exc_info=True)
        scene[ROUTE_STEP_KEY] = "IMMEDIATE_FDI_REVIEW"
        set_stage(scene, STAGE_DICOM)
        self.report({"INFO"}, "Se recuperó el flujo inmediato: elige de nuevo las extracciones; no se repetirá la segmentación")
        return {"FINISHED"}


def _reset_guide_stage_internal(context) -> bool:
    """Reset only DSG guide outputs while preserving the aligned IOS input."""
    props = getattr(context.scene, "dsg_props", None)
    model = getattr(props, "model_obj", None) if props is not None else None
    valid_model = model is not None and getattr(model, "name", "") in bpy.data.objects
    if not valid_model:
        return False
    try:
        result = bpy.ops.dsg.reset("EXEC_DEFAULT")
        return "FINISHED" in result
    except Exception as exc:
        print(f"[DSG 9.2.5] Guide restart warning: {exc}")
        return False


def _reset_alignment_stage_internal(context) -> bool:
    """Reset alignment-generated state, preserving CBCT reference and IOS input."""
    props = getattr(context.scene, "dicp_props", None)
    if props is None:
        return False
    if bool(getattr(props, "alignment_running", False)):
        raise RuntimeError("Cancela con Esc el alineamiento en curso antes de reiniciar")
    try:
        result = bpy.ops.dicp.reset("EXEC_DEFAULT")
        ok = "FINISHED" in result
        if ok:
            source = getattr(props, "icp_source_obj", None)
            target = getattr(props, "icp_target_obj", None)
            if source is not None:
                set_role(source, ROLE_IOS_SCAN, rename=False)
            if target is not None:
                if clinical_route(context.scene) == ROUTE_IMMEDIATE:
                    set_role(target, ROLE_DICOM_ALIGNMENT_COMPOSITE, rename=False)
                else:
                    set_role(target, ROLE_DICOM_BONE, rename=False)
                target["dental_suite_alignment_reference"] = True
        return ok
    except Exception as exc:
        print(f"[DSG 9.2.5] Alignment restart warning: {exc}")
        return False


def _clear_dicom_route_outputs(context, *, clear_semantic: bool) -> None:
    """Return DICOM to a clean route-choice state while preserving loaded volume."""
    scene = context.scene
    _restore_virtual_extraction_if_needed(scene)
    _clear_immediate_review_geometry(context, restore_teeth=True)

    try:
        from . import dicom_module, cbct_dental_module
        props = scene.dicom_wizard_pro
        if clear_semantic:
            cbct_dental_module.clear_dentition(keep_alignment_reference=False)
            cbct_dental_module.reset_scene_state(scene)
            names = (
                dicom_module.NAME_DICOM_TEETH,
                dicom_module.NAME_DICOM_BONE,
                dicom_module.NAME_DICOM_MAXILLA,
                dicom_module.NAME_DICOM_MANDIBLE,
                dicom_module.NAME_DICOM_MANDIBULAR_CANAL,
                dicom_module.NAME_DICOM_COMBINED,
                "Dental_DICOM_AlignmentRef",
                "Dental_DICOM_AlignmentComposite",
            )
            for name in names:
                _remove_object_and_data(bpy.data.objects.get(str(name)))
            try:
                dicom_module.clear_segmentation_states()
            except Exception:
                # Older builds keep the state internally; object cleanup is the
                # clinical SSOT and is enough to force a fresh segmentation.
                _DSG_LOG.debug("suppressed exception", exc_info=True)
        else:
            # SIMPLE-route final STL is generated from the DICOM threshold and
            # must not survive a DICOM restart. Never delete raw viewer objects.
            name = str(getattr(props, "generated_surface_name", "") or "")
            candidate = bpy.data.objects.get(name) if name else None
            if candidate is not None and bool(candidate.get("DSG_segmentation_skipped", False)):
                _remove_object_and_data(candidate)

        props.generated_surface_name = ""
        props.surface_ready = False
        props.segmentation_ready = False
        props.segmentation_progress = 0.0
        props.segmentation_progress_phase = ""
        props.segmentation_progress_detail = ""
        props.segmentation_structure = "BONE"
        props.step = 2
        props.show_volume = True
        props.show_planes = True
        props.show_all_planes = False
        props.show_box = False
        try:
            dicom_module.restore_clinical_preview_view(context)
            dicom_module.refresh_volume_material(context)
            dicom_module.update_visibility(context)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    except Exception as exc:
        print(f"[DSG 9.2.5] DICOM route cleanup warning: {exc}")

    scene["DSG_cbct_segmentation_mode"] = ""
    scene["DSG_cbct_segmentation_skipped"] = False
    scene[ROUTE_STEP_KEY] = "CBCT_READY"
    set_stage(scene, STAGE_DICOM)


def _back_from_dicom(context, operator):
    """Deterministic clinical Back for the DICOM branch, never Blender Undo."""
    scene = context.scene
    step = str(scene.get(ROUTE_STEP_KEY, "CBCT_READY") or "CBCT_READY")
    try:
        from . import dicom_module
        if bool(dicom_module.semantic_workflow_busy()):
            if step in {"SIMPLE_SEGMENTING", "IMMEDIATE_SEGMENTING", "IMMEDIATE_LAUNCHING"}:
                if dicom_module.cancel_semantic_workflow(context, "Segmentación cancelada por Atrás"):
                    operator.report({"INFO"}, "Atrás · segmentación cancelada y estado anterior restaurado")
                    return {"FINISHED"}
            operator.report({"WARNING"}, "Hay una operación DICOM activa que aún no puede revertirse")
            return {"CANCELLED"}
    except Exception as exc:
        operator.report({"WARNING"}, f"No se pudo cancelar la operación DICOM: {exc}")
        return {"CANCELLED"}

    if step in {"SIMPLE_SEGMENTING", "SIMPLE_REVIEW"}:
        if restore_dicom_route_checkpoint(context):
            operator.report({"INFO"}, "Atrás · restaurado el estado anterior a la segmentación simple")
            return {"FINISHED"}
        scene[ROUTE_STEP_KEY] = "CBCT_READY"; set_stage(scene, STAGE_DICOM)
        return {"FINISHED"}

    if step == "IMMEDIATE_FDI_REVIEW":
        if restore_dicom_route_checkpoint(context):
            operator.report({"INFO"}, "Atrás · restaurado el estado anterior a la segmentación inmediata")
            return {"FINISHED"}

    if step == "IMMEDIATE_ARCH_REVIEW":
        _clear_immediate_review_geometry(context, restore_teeth=False)
        scene[ROUTE_STEP_KEY] = "IMMEDIATE_SELECT_TEETH"
        operator.report({"INFO"}, "Atrás · vuelve a elegir los dientes a extraer")
        return {"FINISHED"}

    if step == "IMMEDIATE_SELECT_TEETH":
        _clear_immediate_review_geometry(context, restore_teeth=True)
        scene[ROUTE_STEP_KEY] = "IMMEDIATE_FDI_REVIEW"
        try:
            from . import cbct_dental_module
            cbct_dental_module.labels_visible(True)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        operator.report({"INFO"}, "Atrás · revisión FDI")
        return {"FINISHED"}

    if step in {"SIMPLE_DENSITY", "IMMEDIATE_SEGMENTING"}:
        # Return to route choice. Keep a completed semantic segmentation cached
        # when merely navigating back; a dedicated DICOM restart clears it.
        _restore_virtual_extraction_if_needed(scene)
        _clear_immediate_review_geometry(context, restore_teeth=True)
        scene[ROUTE_STEP_KEY] = "CBCT_READY"
        set_stage(scene, STAGE_DICOM)
        operator.report({"INFO"}, "Atrás · elige Implante simple o Implante inmediato")
        return {"FINISHED"}

    operator.report({"INFO"}, "Ya estás al inicio de la etapa DICOM")
    return {"CANCELLED"}


class DSG_SUITE_OT_BackWorkflow(Operator):
    bl_idname = "dsg_suite.back_workflow"
    bl_label = "Atrás"
    bl_description = "Vuelve exactamente un paso clínico sin usar Ctrl+Z ni mezclar rutas"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scene = context.scene
        stage = infer_stage(scene)

        if stage == STAGE_GUIDE:
            try:
                result = bpy.ops.dsg.reset_current_step("EXEC_DEFAULT")
                return {"FINISHED"} if "FINISHED" in result else {"CANCELLED"}
            except Exception as exc:
                self.report({"ERROR"}, f"No se pudo volver al paso anterior de DSG: {exc}")
                return {"CANCELLED"}

        if stage == STAGE_ALIGNMENT:
            props = getattr(scene, "dicp_props", None)
            if props is None:
                self.report({"ERROR"}, "El estado de alineamiento no está disponible")
                return {"CANCELLED"}
            if bool(getattr(props, "alignment_running", False)):
                # A second operator must not tear down another modal timer. Ask
                # the alignment modal to roll itself back on its next TIMER.
                scene["DSG_alignment_cancel_requested"] = True
                self.report({"INFO"}, "Atrás · cancelando el alineamiento y restaurando su estado previo")
                return {"FINISHED"}
            try:
                from . import alignment_module
                current_step = int(getattr(props, "current_step", alignment_module.STEP_MODELS))
                if bool(getattr(props, "aligned", False)) or current_step >= alignment_module.STEP_DONE:
                    result = bpy.ops.dicp.restore_source("EXEC_DEFAULT")
                    if "FINISHED" in result:
                        self.report({"INFO"}, "Atrás · vuelve a los puntos de alineamiento")
                        return {"FINISHED"}
                if current_step >= alignment_module.STEP_LANDMARKS or int(getattr(props, "source_point_count", 0)) or int(getattr(props, "target_point_count", 0)):
                    result = bpy.ops.dicp.clear_landmarks("EXEC_DEFAULT")
                    if "FINISHED" in result:
                        self.report({"INFO"}, "Atrás · inicio del alineamiento")
                        return {"FINISHED"}
            except Exception as exc:
                self.report({"WARNING"}, f"No se pudo restaurar el paso interno: {exc}")
                return {"CANCELLED"}

            # At the first alignment screen, Back returns to the exact DICOM
            # review that generated the alignment target.
            route = clinical_route(scene)
            set_stage(scene, STAGE_DICOM)
            if route == ROUTE_IMMEDIATE:
                scene[ROUTE_STEP_KEY] = "IMMEDIATE_ARCH_REVIEW"
            else:
                scene[ROUTE_STEP_KEY] = "SIMPLE_REVIEW"
            set_dicom_collections_hidden(context, False)
            self.report({"INFO"}, "Atrás · DICOM")
            return {"FINISHED"}

        return _back_from_dicom(context, self)


class DSG_SUITE_OT_RestartDICOM(Operator):
    bl_idname = "dsg_suite.restart_dicom"
    bl_label = "Reiniciar DICOM"
    bl_description = "Reinicia DICOM y sus resultados dependientes; conserva paciente y CBCT cargado"
    bl_options = {"REGISTER", "UNDO"}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        try:
            from . import dicom_module
            if bool(dicom_module.semantic_workflow_busy()):
                self.report({"WARNING"}, "Espera a que termine la segmentación antes de reiniciar DICOM")
                return {"CANCELLED"}
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)

        # Dependency direction is explicit: resetting an upstream stage clears
        # only later-stage work. Patient folder and raw loaded CBCT survive.
        _reset_guide_stage_internal(context)
        try:
            _reset_alignment_stage_internal(context)
        except RuntimeError as exc:
            self.report({"WARNING"}, str(exc))
            return {"CANCELLED"}
        _clear_dicom_route_outputs(context, clear_semantic=True)
        self.report({"INFO"}, "DICOM reiniciado · paciente y CBCT conservados · elige una ruta")
        return {"FINISHED"}


class DSG_SUITE_OT_RestartAlignment(Operator):
    bl_idname = "dsg_suite.restart_alignment"
    bl_label = "Reiniciar alineamiento"
    bl_description = "Conserva el resultado DICOM y los modelos IOS; borra puntos, ICP y DSG posterior"
    bl_options = {"REGISTER", "UNDO"}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        _reset_guide_stage_internal(context)
        try:
            ok = _reset_alignment_stage_internal(context)
        except RuntimeError as exc:
            self.report({"WARNING"}, str(exc))
            return {"CANCELLED"}
        if not ok:
            self.report({"WARNING"}, "Todavía no hay una etapa de alineamiento que reiniciar")
            return {"CANCELLED"}
        context.scene[ROUTE_STEP_KEY] = "ALIGNMENT"
        set_stage(context.scene, STAGE_ALIGNMENT)
        self.report({"INFO"}, "Alineamiento reiniciado · DICOM e IOS conservados")
        return {"FINISHED"}


class DSG_SUITE_OT_RestartDSG(Operator):
    bl_idname = "dsg_suite.restart_dsg"
    bl_label = "Reiniciar DSG"
    bl_description = "Conserva DICOM y alineamiento; elimina solo el trabajo generado en la guía DSG"
    bl_options = {"REGISTER", "UNDO"}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        if not _reset_guide_stage_internal(context):
            self.report({"WARNING"}, "Todavía no hay una etapa DSG que reiniciar")
            return {"CANCELLED"}
        context.scene[ROUTE_STEP_KEY] = "DSG"
        # DSG reset itself stays inside the guide module and preserves the IOS.
        # Keep the user in DSG so the first guide button is immediately visible.
        set_stage(context.scene, STAGE_GUIDE)
        self.report({"INFO"}, "DSG reiniciado · DICOM y alineamiento conservados")
        return {"FINISHED"}




def set_status_bar(context, text: str = "") -> None:
    """Send contextual guidance/data to Blender's bottom status bar.

    DSG 9.2.16 keeps the N-panel visual hierarchy deliberately minimal.
    Explanations, progress details and validation data belong here instead of
    consuming permanent panel space.
    """
    workspace = getattr(context, "workspace", None)
    setter = getattr(workspace, "status_text_set", None) if workspace is not None else None
    if callable(setter):
        try:
            setter(str(text or ""))
            return
        except Exception:
            try:
                setter(text=str(text or ""))
                return
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)


def _stage_available(scene, stage: str) -> bool:
    stage = str(stage).upper()
    if stage == STAGE_DICOM:
        return True
    current = infer_stage(scene)
    if stage == STAGE_ALIGNMENT:
        return bool(
            current in {STAGE_ALIGNMENT, STAGE_GUIDE}
            or str(scene.get(ROUTE_STEP_KEY, "") or "") in {"ALIGNMENT", "DSG"}
            or find_alignment_reference(scene) is not None
        )
    if stage == STAGE_GUIDE:
        return bool(
            current == STAGE_GUIDE
            or find_role(ROLE_IOS_ALIGNED) is not None
            or str(scene.get(ROUTE_STEP_KEY, "") or "") == "DSG"
        )
    return False


def _draw_vertical_stage_rail(container, scene) -> None:
    """Three permanent stage buttons, stacked vertically on the left."""
    current = infer_stage(scene)
    labels = (
        (STAGE_DICOM, "DICOM", "IMPORT"),
        (STAGE_ALIGNMENT, tr(scene, "ALIGN", "ALINEAR"), "MOD_DATA_TRANSFER"),
        (STAGE_GUIDE, "DSG", "MODIFIER"),
    )
    for stage, label, icon in labels:
        active = current == stage
        row = (
            ui_style.primary_action(container, enabled=True)
            if active else
            ui_style.tertiary_action(container, enabled=_stage_available(scene, stage), align=False)
        )
        try:
            op = row.operator(DSG_SUITE_OT_SetStage.bl_idname, text=label, icon=icon, depress=active)
        except TypeError:
            op = row.operator(DSG_SUITE_OT_SetStage.bl_idname, text=label, icon=icon)
        op.stage = stage


class DSG_SUITE_PT_WorkflowControls(Panel):
    """Legacy shell retained for RNA compatibility; 9.2.16 rail lives in main."""
    bl_label = "Control del flujo"
    bl_idname = "DSG_SUITE_PT_workflow_controls"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "DSG"
    bl_order = 1

    @classmethod
    def poll(cls, context):
        return False

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        folder = patient_folder(scene)
        if not folder:
            layout.label(text=tr(scene, "Choose a patient first", "Elige primero un paciente"), icon="INFO")
            return

        stage = infer_stage(scene)
        stage_label = {
            STAGE_DICOM: tr(scene, "DICOM", "DICOM"),
            STAGE_ALIGNMENT: tr(scene, "ALIGNMENT", "ALINEAMIENTO"),
            STAGE_GUIDE: tr(scene, "DSG", "DSG"),
        }.get(stage, stage)
        layout.label(text=tr(scene, f"Current stage · {stage_label}", f"Etapa actual · {stage_label}"), icon="FORWARD")

        back = ui_style.secondary_action(layout)
        back.operator(
            DSG_SUITE_OT_BackWorkflow.bl_idname,
            text=tr(scene, "BACK", "ATRÁS"),
            icon_value=icon_manager.icon_id("back"),
        )

        box = layout.box()
        box.label(text=tr(scene, "RESTART ONE STAGE", "REINICIAR UNA ETAPA"), icon="FILE_REFRESH")
        # Exactly three restart buttons. All are deliberately tertiary because
        # reset is never the normal next clinical action.
        row = ui_style.destructive_action(box, compact=True, align=True)
        row.operator(DSG_SUITE_OT_RestartDICOM.bl_idname, text="DICOM")
        row.operator(DSG_SUITE_OT_RestartAlignment.bl_idname, text=tr(scene, "ALIGN", "ALINEAR"))
        row.operator(DSG_SUITE_OT_RestartDSG.bl_idname, text="DSG")
        box.label(
            text=tr(scene, "A restart preserves earlier stages and clears only dependent later work.", "Cada reinicio conserva las etapas anteriores y limpia solo el trabajo posterior dependiente."),
            icon="INFO",
        )

class DSG_SUITE_OT_SetStage(Operator):
    bl_idname = "dsg_suite.set_stage"
    bl_label = "Open module"
    bl_options = {"REGISTER", "UNDO"}

    stage: StringProperty(default=STAGE_DICOM)

    def execute(self, context):
        requested = str(self.stage).upper()
        previous = infer_stage(context.scene)
        if previous == STAGE_GUIDE and requested != STAGE_GUIDE:
            try:
                from . import guide_module
                guide_module.restore_precision_projection(context)
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
        set_stage(context.scene, requested)
        if requested == STAGE_GUIDE:
            prepare_guide_entry_view(context)
            try:
                from . import guide_module
                guide_module.activate_precision_orthographic(context)
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
        else:
            set_dicom_collections_hidden(context, False)
            if requested == STAGE_DICOM:
                try:
                    from . import cbct_dental_module
                    cbct_dental_module.clear_alignment_working_composite(
                        context, restore_sources=True
                    )
                except Exception as exc:
                    print(f"[DSG Alignment] DICOM restore warning: {exc}")
        if context.area is not None:
            context.area.tag_redraw()
        return {"FINISHED"}


class DSG_SUITE_OT_UseSelectedIOS(Operator):
    bl_idname = "dsg_suite.use_selected_ios"
    bl_label = "Use selected IOS"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        obj = context.view_layer.objects.active
        if obj is None or obj.type != "MESH":
            self.report({"ERROR"}, tr(context.scene, "Select an intraoral mesh.", "Selecciona una malla intraoral."))
            return {"CANCELLED"}
        props = getattr(context.scene, "dicp_props", None)
        previous = getattr(props, "icp_source_obj", None) if props is not None else None
        set_role(obj, ROLE_IOS_SCAN, rename=False)
        if props is not None:
            props.icp_source_obj = obj
            reference = find_alignment_reference(context.scene)
            if reference is not None:
                props.icp_target_obj = reference
        try:
            from . import alignment_module
            alignment_module.ensure_ios_gray_material(obj, context=context)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        if previous is not obj:
            # DSG 8.8: IOS is the moving geometry only. FDI remains owned by the
            # reviewed UniversalLab CBCT dentition.
            obj["DSG_dental_identity_source"] = "CBCT"
        bind_antagonists_to_source(obj)
        set_stage(context.scene, STAGE_ALIGNMENT)
        return {"FINISHED"}


class DSG_SUITE_OT_ToggleAntagonist(Operator):
    bl_idname = "dsg_suite.toggle_antagonist"
    bl_label = "Toggle Antagonist"
    bl_description = "Muestra u oculta el antagonista sin desvincularlo del IOS"
    bl_options = {"REGISTER"}

    def execute(self, context):
        props = getattr(context.scene, "dicp_props", None)
        source = getattr(props, "icp_source_obj", None) if props is not None else None
        antagonists = antagonist_objects(source)
        if not antagonists:
            self.report({"WARNING"}, "No hay un antagonista IOS registrado")
            return {"CANCELLED"}
        show = any(bool(obj.hide_get() or obj.hide_viewport) for obj in antagonists)
        for obj in antagonists:
            try:
                obj.hide_viewport = not show
                obj.hide_set(not show)
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
        self.report({"INFO"}, "Antagonista mostrado" if show else "Antagonista oculto")
        return {"FINISHED"}


class DSG_SUITE_PT_Main(Panel):
    bl_label = "DSG"
    bl_idname = "DSG_SUITE_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "DSG"
    bl_order = 0

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        current = infer_stage(scene)
        step = str(scene.get(ROUTE_STEP_KEY, "") or "")

        # Compact masthead: language is always reachable, while the workflow
        # remains the visual focus below it.
        masthead = layout.box()
        top = ui_style.header_row(masthead, align=True)
        top.label(text="DSG · Dental Surgical Guide", icon="MOD_SIMPLEDEFORM")
        settings = getattr(scene, "dsg_suite_settings", None)
        if settings is not None:
            top.prop(settings, "language", text="")

        # Persistent left rail: DICOM / ALIGNMENT / DSG, one above another.
        split = layout.split(factor=0.31)
        rail = split.column(align=True)
        body = split.column(align=True)
        _draw_vertical_stage_rail(rail, scene)

        # Keep deterministic navigation and the three independent stage resets,
        # but as buttons only. No explanatory blocks in the N-panel.
        can_back = (current != STAGE_DICOM) or step not in {"", "PATIENT", "CBCT_READY", "CBCT_LOADING"}
        back = ui_style.tertiary_action(rail, enabled=can_back, align=False)
        back.operator(DSG_SUITE_OT_BackWorkflow.bl_idname, text=tr(scene, "BACK", "ATRÁS"), icon_value=icon_manager.icon_id("back"))
        reset = ui_style.compact_action(body, align=True)
        reset.operator(DSG_SUITE_OT_RestartDICOM.bl_idname, text="↻ DICOM")
        reset.operator(DSG_SUITE_OT_RestartAlignment.bl_idname, text=tr(scene, "↻ ALIGN", "↻ ALINEAR"))
        reset.operator(DSG_SUITE_OT_RestartDSG.bl_idname, text="↻ DSG")

        # v9.2.18: one repository-driven engine button. No dependency prose in
        # the panel; progress/errors are sent to Blender's status bar.
        if current == STAGE_DICOM:
            try:
                from . import runtime_bootstrap
                remote = runtime_bootstrap.remote_install_state()
                engines_ready = bool(runtime_bootstrap.ui_engines_ready())
                if bool(remote.get("running")):
                    row = ui_style.primary_action(body, enabled=False)
                    row.operator(DSG_SUITE_OT_InstallEnginesCore.bl_idname, text=tr(scene, "INSTALLING ENGINES…", "INSTALANDO MOTORES…"), icon="IMPORT")
                    factor = max(0.0, min(1.0, float(remote.get("progress", 0.0) or 0.0)))
                    pct = int(round(factor * 100.0))
                    phase = str(remote.get("phase") or "PREPARANDO")
                    msg = str(remote.get("message") or tr(scene, "Installing engines…", "Instalando motores…"))

                    # v9.6.8: progress must be visible inside DSG itself, not only
                    # in Blender's bottom status bar. This remains visible during
                    # downloads, extraction and verification.
                    progress_box = body.box()
                    progress_box.label(text=f"{pct}% · {phase}", icon="TIME")
                    try:
                        progress_box.progress(factor=factor, type='BAR', text=f"{pct}%")
                    except Exception:
                        # Fallback for any Blender build without UILayout.progress.
                        fallback = progress_box.row(align=True)
                        fallback.label(text=("█" * max(1, int(round(factor * 20)))) + ("░" * max(0, 20 - int(round(factor * 20)))))
                    progress_box.label(text=msg[:110])
                    progress_box.label(text=tr(scene, "You can keep Blender open while installation continues.", "Puedes mantener Blender abierto mientras continúa la instalación."), icon="INFO")
                    set_status_bar(context, f"{pct}% · {phase} · {msg}")
                    return
                else:
                    row = ui_style.tertiary_action(body) if engines_ready else ui_style.primary_action(body)
                    verified = runtime_bootstrap.verification_state()
                    repair = bool(verified.get("done") and not verified.get("ready"))
                    row.operator(
                        DSG_SUITE_OT_InstallEnginesCore.bl_idname,
                        text=(tr(scene, "ENGINES ✓", "MOTORES ✓") if engines_ready else (tr(scene, "REPAIR ENGINES", "REPARAR MOTORES") if repair else tr(scene, "INSTALL ENGINES", "INSTALAR MOTORES"))),
                        icon="CHECKMARK" if engines_ready else "IMPORT",
                    )
                    if repair:
                        set_status_bar(context, str(verified.get("error") or tr(scene, "Engine verification failed.", "Falló la verificación de motores.")))
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)

        folder = patient_folder(scene)
        if not folder:
            set_status_bar(context, tr(scene, "Choose the patient folder.", "Elige la carpeta del paciente."))
            choose = ui_style.primary_action(body)
            choose.operator(DSG_SUITE_OT_ChoosePatientFolder.bl_idname, text=tr(scene, "CHOOSE PATIENT", "ELEGIR PACIENTE"), icon_value=icon_manager.icon_id("open_folder"), depress=True)
            return

        try:
            from . import dicom_module, cbct_dental_module
            cbct_loaded = bool(dicom_module.RUNTIME.is_loaded())
        except Exception:
            cbct_loaded = False
            cbct_dental_module = None

        # v9.2.78: repair only clearly stale non-clinical route state after a
        # successful CBCT load. This prevents the route selector from vanishing
        # because an old PATIENT/empty marker survived a UI refresh.
        if cbct_loaded and current == STAGE_DICOM and step in {"", "PATIENT"}:
            props = getattr(scene, "dicom_wizard_pro", None)
            if props is not None and bool(getattr(props, "volume_loaded", False)):
                scene[ROUTE_STEP_KEY] = "CBCT_READY"
                step = "CBCT_READY"

        # v9.2.68: RUNTIME.is_loaded() can become True before the modal has
        # finished creating MPR and publishing CBCT_READY. Never expose route
        # buttons during that small but dangerous window.
        if step == "CBCT_LOADING":
            status = str(getattr(getattr(scene, "dicom_wizard_pro", None), "status", "") or "")
            set_status_bar(context, status or tr(scene, "Opening CBCT in background…", "Abriendo CBCT en segundo plano…"))
            busy = ui_style.primary_action(body, enabled=False)
            busy.operator(DSG_SUITE_OT_LoadPatientCBCT.bl_idname, text=tr(scene, "OPENING CBCT…", "ABRIENDO CBCT…"), icon_value=icon_manager.icon_id("cbct"), depress=True)
            return

        if not cbct_loaded:
            set_status_bar(context, f"{Path(folder).name} · " + tr(scene, "load the CBCT.", "carga el CBCT."))
            load = ui_style.primary_action(body)
            load.operator(DSG_SUITE_OT_LoadPatientCBCT.bl_idname, text=tr(scene, "LOAD CBCT", "CARGAR CBCT"), icon_value=icon_manager.icon_id("cbct"), depress=True)
            change = ui_style.tertiary_action(body)
            change.operator(DSG_SUITE_OT_ChoosePatientFolder.bl_idname, text=tr(scene, "CHANGE PATIENT", "CAMBIAR PACIENTE"), icon="FILE_FOLDER")
            return

        route_locked = bool(
            step.startswith("SIMPLE_")
            or step.startswith("IMMEDIATE_")
            or step == "ALIGNMENT"
            or current == STAGE_GUIDE
        )

        # v9.2.78 — route selector is a persistent, deterministic screen.
        # If CBCT_READY has been published, always render BOTH clinical routes,
        # even if another non-clinical state drifts temporarily. A transient
        # engine/readiness condition may disable IMPLANTE INMEDIATO, but it must
        # never make that option disappear from the UI.
        show_route_selector = (
            bool(cbct_loaded)
            and step == "CBCT_READY"
        ) or (
            current == STAGE_DICOM and not route_locked
        )
        if show_route_selector:
            set_status_bar(context, tr(scene, "Choose one clinical route.", "Elige una ruta clínica."))

            route_card = body.box()
            route_card.label(text=tr(scene, "PLANNING ROUTE", "RUTA DE PLANIFICACIÓN"), icon="NODETREE")
            routes = ui_style.primary_action(route_card, align=False)
            routes.operator(
                DSG_SUITE_OT_StartSimpleRoute.bl_idname,
                text=tr(scene, "SIMPLE · 2 ARCHES", "SIMPLE · 2 ARCADAS"),
                icon_value=icon_manager.icon_id("implant_tea"),
                depress=True,
            )

            immediate_ready, immediate_reason = _immediate_route_readiness(context)
            routes2 = ui_style.secondary_action(route_card, align=False, enabled=immediate_ready)
            routes2.operator(
                DSG_SUITE_OT_StartImmediateRoute.bl_idname,
                text=tr(scene, "IMMEDIATE · FDI + SOCKET", "INMEDIATO · FDI + ALVÉOLO"),
                icon_value=icon_manager.icon_id("implant_tea"),
            )

            # Never replace or remove the route button. If it is temporarily
            # unavailable, explain why in a compact status line underneath it.
            if not immediate_ready:
                wait_box = body.box()
                wait_box.alert = False
                wait_box.label(
                    text=tr(scene, "Immediate route waiting:", "Implante inmediato esperando:"),
                    icon="INFO",
                )
                wait_box.label(text=str(immediate_reason)[:120])

            change = ui_style.tertiary_action(body)
            change.operator(
                DSG_SUITE_OT_ChoosePatientFolder.bl_idname,
                text=tr(scene, "CHANGE PATIENT", "CAMBIAR PACIENTE"),
                icon="FILE_FOLDER",
            )
            return

        active_route = clinical_route(scene)
        if active_route == ROUTE_SIMPLE and current == STAGE_DICOM:
            if step == "SIMPLE_SEGMENTING":
                try:
                    snap = dicom_module.segmentation_progress_snapshot(context)
                    factor = float(snap.get("factor", 0.0) or 0.0)
                    phase = str(snap.get("phase", "Segmentando") or "Segmentando")
                    set_status_bar(context, f"{factor*100:.0f}% · {phase}")
                except Exception:
                    set_status_bar(context, tr(scene, "Building two arches…", "Creando dos arcadas…"))
                busy = ui_style.primary_action(body, enabled=False)
                busy.operator(DSG_SUITE_OT_StartSimpleRoute.bl_idname, text=tr(scene, "SEGMENTING 2 ARCHES…", "SEGMENTANDO 2 ARCADAS…"), icon_value=icon_manager.icon_id("status_pending"), depress=True)
                return
            if step == "SIMPLE_REVIEW":
                set_status_bar(context, tr(scene, "Review both colored arches, then continue.", "Revisa las dos arcadas por color y continúa."))
                legend = body.box()
                r1 = ui_style.secondary_action(legend, align=False); r1.label(text=tr(scene, "SAND", "ARENA"), icon_value=icon_manager.icon_id("tone_sand"))
                r2 = ui_style.secondary_action_alt(legend, align=False); r2.label(text=tr(scene, "SKY BLUE", "CELESTE"), icon_value=icon_manager.icon_id("tone_sky"))
                confirm = ui_style.primary_action(body)
                confirm.operator(DSG_SUITE_OT_ConfirmSimpleSTL.bl_idname, text=tr(scene, "CONFIRM + ALIGN", "CONFIRMAR + ALINEAR"), icon_value=icon_manager.icon_id("continue"), depress=True)
                back = ui_style.tertiary_action(body)
                back.operator(DSG_SUITE_OT_BackWorkflow.bl_idname, text=tr(scene, "BACK", "ATRÁS"), icon_value=icon_manager.icon_id("back"))
                return
            route = ui_style.tertiary_action(body)
            route.operator(DSG_SUITE_OT_ChangeRoute.bl_idname, text=tr(scene, "CHANGE ROUTE", "CAMBIAR RUTA"), icon_value=icon_manager.icon_id("back"))
            return

        if active_route == ROUTE_IMMEDIATE and current == STAGE_DICOM:
            teeth = cbct_dental_module.dentition_objects(context) if cbct_dental_module is not None else []
            if step in {"IMMEDIATE_LAUNCHING", "IMMEDIATE_SEGMENTING"}:
                try:
                    snap = dicom_module.segmentation_progress_snapshot(context)
                    factor = float(snap.get("factor", 0.0) or 0.0)
                    phase = str(snap.get("phase", "Segmentando") or "Segmentando")
                    detail = str(snap.get("detail", "") or "")
                    set_status_bar(context, f"{factor*100:.0f}% · {phase}" + (f" · {detail}" if detail else ""))
                except Exception:
                    set_status_bar(context, tr(scene, "Segmenting CBCT…", "Segmentando CBCT…"))
                busy = ui_style.primary_action(body, enabled=False)
                busy_text = (
                    tr(scene, "STARTING…", "INICIANDO…")
                    if step == "IMMEDIATE_LAUNCHING"
                    else tr(scene, "SEGMENTING…", "SEGMENTANDO…")
                )
                busy.operator(DSG_SUITE_OT_StartImmediateRoute.bl_idname, text=busy_text, icon_value=icon_manager.icon_id("status_pending"), depress=True)
                return

            if step == "IMMEDIATE_FDI_REVIEW":
                set_status_bar(context, f"{len(teeth)} " + tr(scene, "teeth segmented · verify FDI visually.", "dientes segmentados · verifica FDI visualmente."))
                accept = ui_style.primary_action(body)
                accept.operator(DSG_SUITE_OT_AcceptFDIAndSelectTeeth.bl_idname, text=tr(scene, "FDI CORRECT", "FDI CORRECTO"), icon_value=icon_manager.icon_id("validate"), depress=True)
                correction = ui_style.secondary_action_alt(body)
                correction.operator("dsg.cbct_swap_arches", text=tr(scene, "SWAP FDI ARCHES", "INVERTIR FDI"), icon_value=icon_manager.icon_id("reset"))

            elif step == "IMMEDIATE_SELECT_TEETH":
                selected = [obj for obj in teeth if bool(getattr(obj, "select_get", lambda: False)())]
                selected_fdis = sorted({int(obj.get("DSG_fdi_number", 0) or 0) for obj in selected if int(obj.get("DSG_fdi_number", 0) or 0) > 0})
                fixed_fdis = _immediate_extraction_fdis(scene)
                set_status_bar(context, tr(scene, "Select CBCT teeth, then fix the selection.", "Selecciona dientes CBCT y fija la selección.") + ((" · FDI " + ", ".join(map(str, fixed_fdis))) if fixed_fdis else ""))
                choice = body.box()
                choice.label(text=tr(scene, "1 · CBCT teeth", "1 · Dientes CBCT"), icon="RESTRICT_SELECT_OFF")
                choice.label(text=(tr(scene, "Selected", "Seleccionados") + ": " + (", ".join(map(str, selected_fdis)) if selected_fdis else tr(scene, "none", "ninguno"))) )
                fix = ui_style.primary_action(choice, enabled=bool(selected_fdis))
                fix.operator(DSG_SUITE_OT_FixImmediateExtractionSelection.bl_idname, text=tr(scene, "FIX TEETH", "FIJAR DIENTES"), icon="CHECKMARK", depress=True)
                fixed = body.box()
                fixed.label(text=tr(scene, "2 · Extraction FDI", "2 · FDI de extracción"), icon="PINNED")
                fixed.label(text=("FDI " + ", ".join(map(str, fixed_fdis))) if fixed_fdis else tr(scene, "Not fixed", "Sin fijar"))
                next_step = ui_style.primary_action(fixed, enabled=bool(fixed_fdis))
                next_step.operator(DSG_SUITE_OT_BuildImmediateArchModels.bl_idname, text=tr(scene, "CREATE ALVEOLI", "CREAR ALVÉOLOS"), icon_value=icon_manager.icon_id("model"), depress=True)

            elif step == "IMMEDIATE_ARCH_REVIEW":
                fdis = str(scene.get("DSG_immediate_extraction_fdis", "") or "")
                set_status_bar(context, tr(scene, "Review the two alveolar models.", "Revisa los dos modelos alveolares.") + (f" · FDI {fdis}" if fdis else ""))
                confirm = ui_style.primary_action(body)
                confirm.operator(DSG_SUITE_OT_ConfirmImmediateModels.bl_idname, text=tr(scene, "CONFIRM + ALIGN", "CONFIRMAR + ALINEAR"), icon_value=icon_manager.icon_id("continue"), depress=True)
                revise = ui_style.secondary_action_soft(body)
                revise.operator(DSG_SUITE_OT_AcceptFDIAndSelectTeeth.bl_idname, text=tr(scene, "CHANGE EXTRACTIONS", "CAMBIAR EXTRACCIONES"), icon="RESTRICT_VIEW_OFF")

            if step != "IMMEDIATE_SEGMENTING":
                route = ui_style.tertiary_action(body)
                route.operator(DSG_SUITE_OT_ChangeRoute.bl_idname, text=tr(scene, "CHANGE ROUTE", "CAMBIAR RUTA"), icon_value=icon_manager.icon_id("back"))
            return

        if current == STAGE_ALIGNMENT:
            ios = find_role(ROLE_IOS_SCAN) or find_role(ROLE_IOS_ALIGNED)
            reference = find_alignment_reference(scene)
            set_status_bar(context, f"IOS: {getattr(ios, 'name', '-')} · CBCT: {getattr(reference, 'name', '-')}")
            antagonists = antagonist_objects(ios)
            if antagonists:
                is_hidden = all(bool(obj.hide_get() or obj.hide_viewport) for obj in antagonists)
                antagonist_action = ui_style.tertiary_action(body)
                antagonist_action.operator(
                    DSG_SUITE_OT_ToggleAntagonist.bl_idname,
                    text=tr(scene, "SHOW ANTAGONIST" if is_hidden else "HIDE ANTAGONIST", "MOSTRAR ANTAGONISTA" if is_hidden else "OCULTAR ANTAGONISTA"),
                    icon="HIDE_OFF" if is_hidden else "HIDE_ON")
            if active_route == ROUTE_IMMEDIATE:
                ready = bool(getattr(getattr(scene, "dicp_props", None), "aligned", False))
                confirmed = bool(scene.get("DSG_ios_postextraction_confirmed", False))
                step = str(scene.get(ROUTE_STEP_KEY, "") or "")
                ios_valid = bool(ios is not None and getattr(ios, "type", "") == "MESH" and getattr(ios, "name", "") in bpy.data.objects)
                reference_valid = bool(reference is not None and getattr(reference, "type", "") == "MESH" and getattr(reference, "name", "") in bpy.data.objects)
                if ready and (not ios_valid or not reference_valid):
                    box = body.box()
                    box.alert = True
                    box.label(text=tr(scene, "ALIGNMENT INPUT MISSING", "FALTA UNA ENTRADA DE ALINEAMIENTO"), icon="ERROR")
                    box.label(text=tr(scene, "The saved alignment no longer has its IOS or CBCT reference.", "El alineamiento guardado ya no tiene su IOS o referencia CBCT."))
                    recover = ui_style.primary_action(box)
                    recover.operator(DSG_SUITE_OT_RecoverImmediateInputs.bl_idname, text=tr(scene, "RECOVER WITHOUT RESEGMENTING", "RECUPERAR SIN RESEGMENTAR"), icon="LOOP_BACK", depress=True)
                elif ready and not confirmed:
                    box = body.box()
                    # The action is intentionally wider than the compact state
                    # summary.  This reads as a clear “next” step even in the
                    # narrow N-panel, while the current stage stays visible on
                    # its right without duplicating controls elsewhere.
                    content = box.split(factor=0.62, align=True)
                    actions = content.column(align=True)
                    status = content.column(align=True)
                    status.label(text=tr(scene, "4 · IOS", "4 · IOS"), icon="DISCLOSURE_TRI_RIGHT")
                    status.label(text=tr(scene, "IOS → CBCT socket", "IOS → alvéolo CBCT"))
                    retry_boolean = bool(scene.get("DSG_ios_postextraction_boolean_retry_available", False))
                    retry_closure = bool(scene.get("DSG_ios_postextraction_closure_retry_available", False))
                    if retry_closure:
                        status.label(text=tr(scene, "Close pending", "Cierre pendiente"), icon="ERROR")
                        confirm = ui_style.primary_action(actions)
                        confirm.operator(DSG_SUITE_OT_ConfirmIOSPostExtraction.bl_idname, text=tr(scene, "RETRY CLOSE", "REINTENTAR CIERRE"), icon_value=icon_manager.icon_id("validate"), depress=True)
                    elif retry_boolean:
                        status.label(text=tr(scene, "Retry extraction", "Reintentar extracción"), icon="ERROR")
                        confirm = ui_style.primary_action(actions)
                        confirm.operator(DSG_SUITE_OT_ConfirmIOSPostExtraction.bl_idname, text=tr(scene, "RETRY", "REINTENTAR"), icon_value=icon_manager.icon_id("validate"), depress=True)
                    elif step == "IMMEDIATE_IOS_SURFACE_REVIEW":
                        try:
                            match_stats = json.loads(str(scene.get("DSG_ios_common_surface_stats", "") or "{}"))
                        except Exception:
                            match_stats = {}
                        if match_stats:
                            status.label(
                                text=(
                                    f"Match · {int(match_stats.get('selected_count', 0))} caras · "
                                    f"p95 {float(match_stats.get('p95_distance_mm', 0.0)):.2f} mm"
                                ),
                                icon="CHECKMARK")
                            competitor_fdis = match_stats.get("competitor_fdis", [])
                            if competitor_fdis:
                                status.label(text="Vecinos FDI · " + ", ".join(str(value) for value in competitor_fdis), icon="MOD_VERTEX_WEIGHT")
                            valley_faces = int(match_stats.get("negative_curvature_barrier_faces", 0) or 0)
                            if bool(match_stats.get("negative_curvature_refinement", False)) and valley_faces:
                                status.label(text=f"Valle proximal · {valley_faces} caras", icon="MOD_SMOOTH")
                            if bool(match_stats.get("anatomy_boundary_review_required", False)):
                                status.label(text=tr(scene, "Review contacts", "Revisa contactos"), icon="ERROR")
                        confirm = ui_style.primary_action(actions)
                        confirm.operator(DSG_SUITE_OT_ConfirmIOSPostExtraction.bl_idname, text=tr(scene, "APPLY + CLOSE", "APLICAR + CERRAR"), icon_value=icon_manager.icon_id("validate"), depress=True)
                    else:
                        prepare = ui_style.primary_action(actions)
                        prepare.operator(DSG_SUITE_OT_PrepareIOSPostExtraction.bl_idname, text=tr(scene, "FIND SURFACE", "BUSCAR SUPERFICIE"), icon_value=icon_manager.icon_id("model_visibility"), depress=True)
                    restore = ui_style.tertiary_action(actions)
                    restore.operator(DSG_SUITE_OT_RestoreIOSPreExtraction.bl_idname, text=tr(scene, "RESTORE", "RESTAURAR"), icon="LOOP_BACK")
                elif ready and confirmed:
                    box = body.box()
                    box.label(text=tr(scene, "Closed post-extraction IOS ready · review virtual socket before Next", "IOS postextracción cerrado · revisa el alvéolo virtual antes de Siguiente"), icon="CHECKMARK")
                    restore = ui_style.secondary_action_alt(box)
                    restore.operator(DSG_SUITE_OT_RestoreIOSPreExtraction.bl_idname, text=tr(scene, "REVISE IOS SELECTION", "REVISAR SELECCIÓN IOS"), icon="LOOP_BACK")
            return

        if current == STAGE_GUIDE:
            set_status_bar(context, tr(scene, "DSG surgical guide workflow.", "Flujo de guía quirúrgica DSG."))
            return


class DSG_SUITE_OT_InstallEnginesCore(Operator):
    """Core-registered motor installer.

    This operator deliberately lives in core.py, which is registered before
    runtime_bootstrap and the DICOM child module.  Therefore the visible
    INSTALL ENGINES button always has a live RNA target even if a later
    runtime module has a registration/cache problem.
    """
    bl_idname = "dsg_suite.install_engines_core"
    bl_label = f"Instalar motores DSG {DSG_VERSION_STR}"
    bl_description = "Inicia la instalación de motores desde el núcleo de DSG y muestra diagnóstico desde el primer clic"
    bl_options = {"REGISTER"}

    def execute(self, context):
        stamp = f"{time.time():.6f}"
        scene = getattr(context, "scene", None)
        if scene is not None:
            try:
                scene["DSG_engine_install_click_v966"] = stamp
                scene["DSG_engine_install_status_v968"] = "CLIC RECIBIDO"
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
        try:
            set_status_bar(context, f"DSG {DSG_VERSION_STR} · clic recibido · iniciando motores…")
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        try:
            self.report({"INFO"}, f"DSG {DSG_VERSION_STR} · clic INSTALAR MOTORES recibido")
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)

        # Import lazily. The operator itself is already registered even if
        # runtime_bootstrap failed to register its own classes.
        try:
            from . import totalseg_runtime
        except Exception as exc:
            msg = f"No se puede cargar el runtime de motores: {type(exc).__name__}: {exc}"
            if scene is not None:
                try: scene["DSG_engine_install_status_v968"] = msg
                except Exception: _DSG_LOG.debug("suppressed exception", exc_info=True)
            try: set_status_bar(context, msg)
            except Exception: _DSG_LOG.debug("suppressed exception", exc_info=True)
            self.report({"ERROR"}, msg[:240])
            return {"CANCELLED"}

        try:
            totalseg_runtime.record_install_click(
                click_id=stamp,
                operator_id=self.bl_idname,
            )
        except Exception as exc:
            # A diagnostic write must never prevent the actual installer.
            print(f"[DSG {DSG_VERSION_STR}] click diagnostic warning: {type(exc).__name__}: {exc}")

        try:
            status = totalseg_runtime.quick_status()
            if status.dependencies_ready and status.model_ready:
                msg = f"Motores ya listos · TotalSegmentator {status.version} · {status.device}"
                if scene is not None:
                    try: scene["DSG_engine_install_status_v968"] = msg
                    except Exception: _DSG_LOG.debug("suppressed exception", exc_info=True)
                try: set_status_bar(context, msg)
                except Exception: _DSG_LOG.debug("suppressed exception", exc_info=True)
                self.report({"INFO"}, msg[:240])
                return {"FINISHED"}
        except Exception as exc:
            print(f"[DSG {DSG_VERSION_STR}] quick_status warning: {type(exc).__name__}: {exc}")

        try:
            totalseg_runtime.mark_install_requested(f"DSG {DSG_VERSION_STR} · preparando instalación…")
            started = totalseg_runtime.start_install()
            state = totalseg_runtime.install_state()
        except Exception as exc:
            msg = f"INSTALAR MOTORES falló: {type(exc).__name__}: {exc}"
            try: totalseg_runtime.mark_install_error(msg)
            except Exception: _DSG_LOG.debug("suppressed exception", exc_info=True)
            if scene is not None:
                try: scene["DSG_engine_install_status_v968"] = msg
                except Exception: _DSG_LOG.debug("suppressed exception", exc_info=True)
            try: set_status_bar(context, msg)
            except Exception: _DSG_LOG.debug("suppressed exception", exc_info=True)
            self.report({"ERROR"}, msg[:240])
            return {"CANCELLED"}

        err = str(state.get("error") or "")
        if err:
            msg = f"Motor: {err}"
            if scene is not None:
                try: scene["DSG_engine_install_status_v968"] = msg
                except Exception: _DSG_LOG.debug("suppressed exception", exc_info=True)
            try: set_status_bar(context, msg)
            except Exception: _DSG_LOG.debug("suppressed exception", exc_info=True)
            self.report({"ERROR"}, msg[:240])
            return {"CANCELLED"}

        msg = "Instalación de motores iniciada" if started else "La instalación de motores ya estaba en curso"
        if scene is not None:
            try: scene["DSG_engine_install_status_v968"] = msg
            except Exception: _DSG_LOG.debug("suppressed exception", exc_info=True)
        try: set_status_bar(context, msg)
        except Exception: _DSG_LOG.debug("suppressed exception", exc_info=True)
        self.report({"INFO"}, msg)

        # Keep the UI responsive/progress-visible without depending on the
        # runtime_bootstrap operator class itself.
        try:
            from . import runtime_bootstrap
            runtime_bootstrap._ensure_install_ui_timer()
        except Exception as exc:
            print(f"[DSG {DSG_VERSION_STR}] UI timer warning: {type(exc).__name__}: {exc}")
        return {"FINISHED"}


CLASSES = (
    DSGSuiteSettings,
    DSG_SUITE_OT_ChoosePatientFolder,
    DSG_SUITE_OT_LoadPatientCBCT,
    DSG_SUITE_OT_ChangeRoute,
    DSG_SUITE_OT_StartSimpleRoute,
    DSG_SUITE_OT_ConfirmSimpleSTL,
    DSG_SUITE_OT_StartImmediateRoute,
    DSG_SUITE_OT_AcceptFDIAndSelectTeeth,
    DSG_SUITE_OT_FixImmediateExtractionSelection,
    DSG_SUITE_OT_BuildImmediateArchModels,
    DSG_SUITE_OT_ConfirmImmediateModels,
    DSG_SUITE_OT_RecoverImmediateInputs,
    DSG_SUITE_OT_PrepareIOSPostExtraction,
    DSG_SUITE_OT_ConfirmIOSPostExtraction,
    DSG_SUITE_OT_RestoreIOSPreExtraction,
    DSG_SUITE_OT_BackWorkflow,
    DSG_SUITE_OT_RestartDICOM,
    DSG_SUITE_OT_RestartAlignment,
    DSG_SUITE_OT_RestartDSG,
    DSG_SUITE_OT_SetStage,
    DSG_SUITE_OT_UseSelectedIOS,
    DSG_SUITE_OT_ToggleAntagonist,
    DSG_SUITE_OT_InstallEnginesCore,
    DSG_SUITE_PT_Main,
    DSG_SUITE_PT_WorkflowControls,
)


_CORE_REGISTERED_CLASSES = []
_CORE_SCENE_POINTER_OWNED = False


def _core_unregister_class_object(class_object):
    if class_object is None:
        return False
    try:
        bpy.utils.unregister_class(class_object)
        return True
    except Exception:
        return False


def _core_unregister_stale_classes():
    """Release RNA classes left by an older DSG core before an in-place update."""
    removed = 0
    for cls in reversed(CLASSES):
        existing = getattr(bpy.types, cls.__name__, None)
        if existing is not None and _core_unregister_class_object(existing):
            removed += 1
            continue
        if _core_unregister_class_object(cls):
            removed += 1
    if removed:
        print(f"[DSG] Removed {removed} stale core class(es) from an older version")
    return removed


def _core_remove_stale_scene_pointer():
    if not hasattr(bpy.types.Scene, "dsg_suite_settings"):
        return False
    try:
        del bpy.types.Scene.dsg_suite_settings
        print("[DSG] Removed stale Scene.dsg_suite_settings from older DSG version")
        return True
    except Exception as exc:
        raise RuntimeError(
            f"Could not replace stale Scene.dsg_suite_settings from a previous DSG add-on: {exc}"
        )


def external_agent_execution_context():
    """Return the active Mixar agent context, if this call is running inside it.

    Mixar's official main-thread executor sets a process-local agent execution
    marker while an agent-generated script is running.  DSG treats that marker
    as a *negative* capability signal: it can prove that a call came from the
    Mixar agent path, but its absence is NOT proof that a human is present.
    This keeps clinical/final user gates out of the normal Mixar execution path
    without claiming that Blender's Python runtime is a hostile-code sandbox.
    """
    try:
        from mixar.modules.common.agent_execution_context import get_agent_execution_context
        payload = get_agent_execution_context()
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    if str(payload.get('source', '') or '').strip().lower() != 'agent':
        return None
    return dict(payload)


def reject_external_agent_for_user_gate(operator, *, action='this user-only operation'):
    """Fail closed when a protected DSG operation is invoked by Mixar's agent.

    Returns True when the operation must be rejected.  This is defence in depth
    in addition to the closed DSG Agent Facade and Mixar AST policy.
    """
    payload = external_agent_execution_context()
    if payload is None:
        return False
    session_id = str(payload.get('session_id', '') or '')
    suffix = f' (session {session_id})' if session_id else ''
    message = (
        f'Blocked agent execution of {action}{suffix}. '
        'Use the DSG user interface for this confirmation/final action.'
    )
    try:
        operator.report({'ERROR'}, message)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    return True


def register():
    # Registration is transactional: a failure cannot leave half of the RNA
    # classes installed, which otherwise makes the next enable attempt fail.
    global _CORE_REGISTERED_CLASSES, _CORE_SCENE_POINTER_OWNED
    if _CORE_REGISTERED_CLASSES:
        return
    # Blender can retain RNA from the previous ZIP during an in-place update.
    # Replace that stale registration instead of failing before the UI appears.
    _core_remove_stale_scene_pointer()
    _core_unregister_stale_classes()
    registered = []
    try:
        for cls in CLASSES:
            bpy.utils.register_class(cls)
            registered.append(cls)
        bpy.types.Scene.dsg_suite_settings = PointerProperty(type=DSGSuiteSettings)
        _CORE_SCENE_POINTER_OWNED = True
        _register_workflow_undo_handler()
        _CORE_REGISTERED_CLASSES = registered
    except Exception:
        _unregister_workflow_undo_handler()
        if _CORE_SCENE_POINTER_OWNED and hasattr(bpy.types.Scene, "dsg_suite_settings"):
            del bpy.types.Scene.dsg_suite_settings
        _CORE_SCENE_POINTER_OWNED = False
        for cls in reversed(registered):
            try:
                bpy.utils.unregister_class(cls)
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
        _CORE_REGISTERED_CLASSES = []
        raise


def unregister():
    global _CORE_REGISTERED_CLASSES, _CORE_SCENE_POINTER_OWNED
    _unregister_workflow_undo_handler()
    if _CORE_SCENE_POINTER_OWNED and hasattr(bpy.types.Scene, "dsg_suite_settings"):
        del bpy.types.Scene.dsg_suite_settings
    _CORE_SCENE_POINTER_OWNED = False
    for cls in reversed(list(_CORE_REGISTERED_CLASSES)):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    _CORE_REGISTERED_CLASSES = []
