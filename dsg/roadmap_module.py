"""DSG clinical roadmap orchestrator and local MCP bridge.

The orchestrator sequences only a closed whitelist of existing DSG operators.
It never exports STL and it never executes arbitrary Python/bpy operations.
Geometry-changing confirmations remain explicit gates and every MCP action is
written to a persistent JSON audit log stored in the Blender scene.
"""
from __future__ import annotations

import logging as _dsg_logging
_DSG_LOG = _dsg_logging.getLogger(__name__)

import hashlib
import json
import math
import queue
import secrets
import socketserver
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any

import bpy
import numpy as np
from mathutils import Vector
from bpy.props import BoolProperty, IntProperty, StringProperty, PointerProperty
from bpy.types import Operator, Panel, PropertyGroup

from . import core
from . import dicom_module
from . import cbct_dental_module
from . import dental_assets
from .dental_mapping import service as dental_mapping_service
from . import alignment_module
from . import guide_module
from . import frame_structural
from . import clinical_context
from . import evidence_context
from . import icon_manager
from . import ui_style

ROADMAP_SCHEMA = "dsg.roadmap.v1"
BRIDGE_PROTOCOL = "dsg.blender_bridge.v1"
ROADMAP_STORE_KEY = "DSG_roadmap_store_json"
ROADMAP_ACTIVE_KEY = "DSG_roadmap_active_plan_id"
DEFAULT_BRIDGE_HOST = "127.0.0.1"
DEFAULT_BRIDGE_PORT = 18765
# The capability token lives only in process memory. Scene properties are
# saved inside the .blend file, so storing it there leaked a live credential
# into every saved/shared case file (fixed in 9.7.0).
_BRIDGE_TOKEN = ""
MAX_REQUEST_BYTES = 1024 * 1024
BRIDGE_TIMEOUT_SECONDS = 90.0

VALID_STATUSES = {
    "pending", "ready", "blocked", "awaiting_review", "running", "done", "failed",
}
ALLOWED_STEP_IDS = (
    "tooth_analysis",
    "alignment_review",
    "guide_model_review",
    "virtual_extraction_review",
    "axis_from_fdi",
    "implant_preview",
    "implant_confirm",
    "contour_review",
    "frame_preview",
    "frame_confirm",
    "sleeve_preview",
    "sleeve_confirm",
    "irrigation_preview",
    "irrigation_path_confirm",
    "irrigation_apply",
)


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _case_fingerprint() -> str:
    """Session-bound non-PHI fingerprint for the loaded CBCT.

    v8.4.0 hashed path+dims+spacing.  That could theoretically collide if a
    dataset was replaced at the same path with the same matrix dimensions.
    v8.4.1 also includes the runtime load generation and hashed DICOM UIDs when
    available.  Raw paths and UIDs are never exposed through the bridge.
    Reloading even the same series deliberately invalidates an old roadmap; a
    fresh get_case_state()/submit_plan cycle is required before automation.
    """
    runtime = getattr(dicom_module, "RUNTIME", None)
    if runtime is None or not bool(getattr(runtime, "is_loaded", lambda: False)()):
        return "unloaded"
    header = getattr(runtime, "header", None)
    def _uid_digest(name):
        raw = str(getattr(header, name, "") or "") if header is not None else ""
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16] if raw else ""
    payload = {
        "source": str(getattr(runtime, "source_path", "") or ""),
        "dims": tuple(int(v) for v in (getattr(runtime, "dims_zyx", ()) or ())),
        "spacing": tuple(round(float(v), 6) for v in (getattr(runtime, "spacing_zyx_mm", ()) or ())),
        "load_generation": int(getattr(runtime, "refresh_generation", 0) or 0),
        "series_uid_hash": _uid_digest("SeriesInstanceUID"),
        "study_uid_hash": _uid_digest("StudyInstanceUID"),
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return "cbct:" + digest[:24]


def _valid_fdi(value: Any) -> bool:
    return dental_assets.valid_fdi(value, include_primary=False)


def _safe_float(value, default=None):
    if value is None:
        return default
    try:
        result = float(value)
    except Exception:
        return default
    return result if math.isfinite(result) else default


def _clean_points(points: Any) -> list[list[float]]:
    if points is None:
        return []
    if isinstance(points, str):
        try:
            points = json.loads(points)
        except Exception as exc:
            raise ValueError(f"Invalid irrigation_points JSON: {exc}") from exc
    if not isinstance(points, (list, tuple)):
        raise ValueError("irrigation_points must be a list")
    out = []
    for point in points:
        if not isinstance(point, (list, tuple)) or len(point) < 3:
            raise ValueError("Each irrigation point must contain x, y, z")
        xyz = [float(point[i]) for i in range(3)]
        if not all(math.isfinite(v) for v in xyz):
            raise ValueError("Irrigation points must be finite")
        out.append(xyz)
    if out and len(out) < 2:
        raise ValueError("At least two irrigation points are required")
    if len(out) > 64:
        raise ValueError("Too many irrigation points")
    return out


def canonical_implant_plan(
    fdi: int,
    *,
    irrigation_mode: str = "DIRECT",
    diameter: float | None = None,
    length: float | None = None,
    irrigation_points: Any = None,
    scenario: str | None = None,
    plan_id: str | None = None,
    case_id: str | None = None,
) -> dict[str, Any]:
    """Create the only accepted dsg.roadmap.v1 implant-roadmap shape."""
    fdi = int(fdi)
    if not _valid_fdi(fdi):
        raise ValueError("FDI must be 11-18, 21-28, 31-38 or 41-48")
    mode = str(irrigation_mode or "DIRECT").upper()
    if mode not in {"DIRECT", "C"}:
        raise ValueError("irrigation_mode must be DIRECT or C")
    scenario = str(scenario or "HEALED_SITE").upper()
    if scenario not in {"HEALED_SITE", "IMMEDIATE_EXTRACTION"}:
        raise ValueError("scenario must be HEALED_SITE or IMMEDIATE_EXTRACTION")
    diameter = _safe_float(diameter, None)
    length = _safe_float(length, None)
    if diameter is not None and not 2.0 <= diameter <= 7.0:
        raise ValueError("implant diameter must be 2.0-7.0 mm")
    if length is not None and not 5.0 <= length <= 18.0:
        raise ValueError("implant length must be 5.0-18.0 mm")
    points = _clean_points(irrigation_points)
    pid = str(plan_id or uuid.uuid4())
    # v9.2.1 follows the patient-first UI.  Immediate extraction preparation
    # happens on the segmented CBCT *before* IOS alignment; simple cases do not
    # require individual-tooth AI merely to enter alignment.
    steps = []
    if scenario == "IMMEDIATE_EXTRACTION":
        steps.extend([
            dict(id="tooth_analysis", title="Segmentación IA + FDI revisado", status="pending",
                 auto_executable=False, requires_confirmation=True,
                 note="DentalSegmentator + UniversalLab deben haber creado maxilar, mandíbula, canal y dientes individuales; FDI se revisa antes de seleccionar extracciones."),
            dict(id="virtual_extraction_review", title="Dientes H + modelos alveolares por arcada", status="pending",
                 auto_executable=False, requires_confirmation=True,
                 note="Selecciona dientes a extraer, ocúltalos con H y crea maxilar+dientes superiores visibles / mandíbula+dientes inferiores visibles. El nervio queda separado. Esta preparación ocurre antes del alineamiento."),
        ])
    steps.extend([
        dict(id="alignment_review", title="Revisar alineamiento IOS ↔ CBCT y entrar en DSG", status="pending",
             auto_executable=True, requires_confirmation=True,
             note="El IOS se importa desde la carpeta del paciente. El cálculo usa 3 pares/zonas para prealineamiento rígido y después ICP; este gate solo acepta una alineación ya validada."),
        dict(id="guide_model_review", title="Preparar modelo retentivo / blockout", status="pending",
             auto_executable=False, requires_confirmation=True,
             note="DSG necesita completar el modelo pasivo y su eje de inserción antes del paso de implantes."),
    ])
    steps.extend([
        dict(id="axis_from_fdi", title=f"Proponer eje desde FDI {fdi}", status="pending",
             auto_executable=True, requires_confirmation=False),
        dict(id="implant_preview", title="Crear implante en preview", status="pending",
             auto_executable=True, requires_confirmation=False),
        dict(id="implant_confirm", title="Confirmar implante", status="pending",
             auto_executable=True, requires_confirmation=True),
        # This is deliberately explicit: contour drawing is still a manual
        # clinical input and was a missing prerequisite in the original roadmap.
        dict(id="contour_review", title="Dibujar y confirmar contorno", status="pending",
             auto_executable=False, requires_confirmation=True,
             note="El contorno del frame sigue siendo una entrada manual; no se inventa por MCP."),
        dict(id="frame_preview", title="Generar frame", status="pending",
             auto_executable=True, requires_confirmation=False),
        dict(id="frame_confirm", title="Confirmar frame", status="pending",
             auto_executable=True, requires_confirmation=True),
        dict(id="sleeve_preview", title="Generar preview de sleeves", status="pending",
             auto_executable=True, requires_confirmation=False),
        dict(id="sleeve_confirm", title="Aplicar sleeves", status="pending",
             auto_executable=True, requires_confirmation=True),
        dict(id="irrigation_preview", title=f"Preparar irrigación {mode}", status="pending",
             auto_executable=bool(points), requires_confirmation=False,
             note=("Usa puntos explícitos del plan." if points else
                   "Bloqueado hasta recibir al menos dos puntos world-space; no se inventa un trayecto.")),
        dict(id="irrigation_path_confirm", title="Confirmar trayecto de irrigación", status="pending",
             auto_executable=True, requires_confirmation=True),
        dict(id="irrigation_apply", title="Aplicar irrigación a la guía", status="pending",
             auto_executable=True, requires_confirmation=True),
    ])
    return {
        "schema": ROADMAP_SCHEMA,
        "plan_id": pid,
        "case_id": str(case_id or "unbound"),
        "created_at": _now(),
        "updated_at": _now(),
        "status": "pending",
        "target": {
            "fdi": fdi,
            "scenario": scenario,
            "clinical_route": ("IMMEDIATE" if scenario == "IMMEDIATE_EXTRACTION" else "SIMPLE"),
            "family_id": dental_assets.family_id(fdi),
            "tooth_class": dental_assets.tooth_class_from_fdi(fdi),
            "arch": dental_assets.arch_from_fdi(fdi),
            "side": dental_assets.side_from_fdi(fdi),
            "irrigation_mode": mode,
            "diameter_mm": diameter,
            "length_mm": length,
            "irrigation_points": points,
        },
        "asset_contract": {
            "schema": dental_assets.schema(),
            "version": dental_assets.contract_version(),
            "sha256": dental_assets.contract_sha256(),
            "file": dental_assets.CONTRACT_FILENAME,
        },
        "steps": steps,
        "log": [],
        "policy": {
            "export_via_mcp": False,
            "arbitrary_bpy_execution": False,
            "confirmations_require_explicit_flag": True,
            "human_review_required": True,
        },
    }


def _load_store(scene) -> dict[str, Any]:
    try:
        raw = str(scene.get(ROADMAP_STORE_KEY, "{}") or "{}")
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    return {}


def _save_store(scene, store: dict[str, Any]) -> None:
    scene[ROADMAP_STORE_KEY] = json.dumps(store, separators=(",", ":"), ensure_ascii=False)


def _save_plan(scene, plan: dict[str, Any], *, active=True) -> None:
    plan["updated_at"] = _now()
    store = _load_store(scene)
    store[str(plan["plan_id"])] = plan
    _save_store(scene, store)
    if active:
        scene[ROADMAP_ACTIVE_KEY] = str(plan["plan_id"])
        props = getattr(scene, "dsg_roadmap_props", None)
        if props is not None:
            props.active_plan_id = str(plan["plan_id"])


def _get_plan(scene, plan_id: str) -> dict[str, Any] | None:
    return _load_store(scene).get(str(plan_id))


def _append_log(plan, *, step_id="", action="", actor="system", result="", parameters=None):
    plan.setdefault("log", []).append({
        "timestamp": _now(),
        "step_id": str(step_id or ""),
        "action": str(action or ""),
        "actor": str(actor or "system"),
        "result": str(result or ""),
        "parameters": parameters or {},
    })


def _step(plan, step_id):
    for item in plan.get("steps", []):
        if str(item.get("id")) == str(step_id):
            return item
    return None


def _tooth_objects():
    """Single source of truth: the current CBCT dentition builder owns tooth instances."""
    return cbct_dental_module.dentition_objects()


def _tooth_analysis_completed(scene) -> bool:
    props = getattr(scene, "dsg_cbct_dental", None)
    accepted = bool(getattr(props, "accepted", False)) if props is not None else False
    accepted = accepted or bool(scene.get(cbct_dental_module.SCENE_ACCEPTED_KEY, False))
    teeth = _tooth_objects()
    return accepted and bool(teeth) and all(bool(obj.get("DSG_label_verified", False)) for obj in teeth)


def _find_tooth_object(fdi: int):
    candidates = []
    for obj in _tooth_objects():
        try:
            if int(obj.get("DSG_fdi_number", 0) or 0) == int(fdi):
                candidates.append(obj)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda o: (
            int(bool(o.get("DSG_label_verified", False))),
            float(o.get("DSG_tooth_axis_confidence", o.get("DSG_axis_shape_confidence", 0.0)) or 0.0),
        ),
    )


def _find_implant_for_fdi(fdi: int):
    for obj in bpy.data.objects:
        try:
            if guide_module.is_valid_implant_obj(obj) and int(obj.get("DSG_target_fdi", 0) or 0) == int(fdi):
                return obj
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    return None


def _json_vec(obj, key):
    raw = obj.get(key)
    if raw is None:
        return None
    try:
        if isinstance(raw, str):
            values = json.loads(raw)
        else:
            values = raw
        values = tuple(float(v) for v in values[:3])
        if len(values) == 3 and all(math.isfinite(v) for v in values):
            return values
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    return None


def _axis_from_tooth_mesh(obj):
    """Fallback PCA for reopened/pre-8.4 objects that lack persisted axis data."""
    if obj is None or getattr(obj, "type", None) != "MESH" or obj.data is None:
        return None
    verts = obj.data.vertices
    if len(verts) < 16:
        return None
    stride = max(1, int(math.ceil(len(verts) / 60000.0)))
    points = np.asarray([
        tuple(obj.matrix_world @ verts[i].co)
        for i in range(0, len(verts), stride)
    ], dtype=np.float64)
    if points.shape[0] < 16:
        return None
    center = points.mean(axis=0)
    centered = points - center[None, :]
    cov = centered.T @ centered / max(1, points.shape[0] - 1)
    values, vectors = np.linalg.eigh(cov)
    order = np.argsort(values)
    values = np.maximum(values[order], 0.0)
    axis = vectors[:, order[-1]]
    axis /= max(float(np.linalg.norm(axis)), 1e-12)
    projection = centered @ axis
    qlo, qhi = np.quantile(projection, [0.12, 0.88])
    neg = points[projection <= qlo].mean(axis=0)
    pos = points[projection >= qhi].mean(axis=0)
    l1, l2 = float(values[-1]), float(values[-2])
    shape_conf = 0.0 if l1 <= 1e-9 else max(0.0, min(1.0, (l1 - l2) / l1))
    anchor = _json_vec(obj, "DSG_ios_anchor_world")
    arch = str(obj.get("DSG_tooth_arch", "UNKNOWN") or "UNKNOWN")
    if anchor is not None:
        da = np.linalg.norm(np.asarray(anchor) - pos)
        db = np.linalg.norm(np.asarray(anchor) - neg)
        apical = -axis if da <= db else axis
        origin = np.asarray(anchor)
        orient_conf = max(0.75, min(1.0, float(obj.get("DSG_ios_label_confidence", 0.0) or 0.0)))
        method = "mesh_pca+aligned_ios_crown"
    else:
        desired = np.asarray((0.0, 0.0, 1.0 if arch == "MAXILLA" else -1.0))
        apical = axis if float(axis @ desired) >= 0.0 else -axis
        raw_is_apical = float(apical @ axis) >= 0.0
        origin = neg if raw_is_apical else pos
        orient_conf = 0.62 if arch in {"MAXILLA", "MANDIBLE"} else 0.40
        method = "mesh_pca+arch_orientation_fallback"
    return {
        "axis": tuple(float(v) for v in apical),
        "origin": tuple(float(v) for v in origin),
        "confidence": max(0.10, min(0.99, shape_conf * orient_conf)),
        "method": method,
    }


def _tooth_axis_data(obj):
    axis = _json_vec(obj, "DSG_tooth_axis_apical_world")
    origin = _json_vec(obj, "DSG_tooth_axis_origin_world")
    if axis is not None and origin is not None:
        return {
            "axis": axis,
            "origin": origin,
            "confidence": float(obj.get("DSG_tooth_axis_confidence", 0.0) or 0.0),
            "method": str(obj.get("DSG_tooth_axis_method", "persisted_pca") or "persisted_pca"),
        }
    return _axis_from_tooth_mesh(obj)


class DSG_OT_SetAxisFromFDI(Operator):
    bl_idname = "dsg.set_axis_from_fdi"
    bl_label = "Propose Implant Axis from FDI"
    bl_options = {"REGISTER", "UNDO"}

    fdi: IntProperty(name="FDI", default=11, min=11, max=48)

    def execute(self, context):
        fdi = int(self.fdi)
        # An explicit re-proposal invalidates any older advisory axis before
        # validation. If this request fails, dsg.create_implant must not be able
        # to consume a stale axis from a previous FDI or previous confidence
        # state. The object is retained but disarmed/hidden.
        guide_module.invalidate_pending_implant_axis_empty()
        if not _valid_fdi(fdi):
            self.report({"ERROR"}, "FDI no válido")
            return {"CANCELLED"}
        if core.infer_stage(context.scene) != core.STAGE_GUIDE:
            self.report({"ERROR"}, "Entra primero en la etapa DSG")
            return {"CANCELLED"}
        props = getattr(context.scene, "dsg_props", None)
        if props is None or int(getattr(props, "current_step", -1)) != int(guide_module.STEP_IMPLANT):
            self.report({"ERROR"}, "El eje FDI solo se prepara en el paso de implantes")
            return {"CANCELLED"}
        tooth = _find_tooth_object(fdi)
        if tooth is None:
            self.report({"ERROR"}, f"FDI {fdi} no existe en la dentición revisada. Un sitio edéntulo requiere un plan específico.")
            return {"CANCELLED"}
        if not bool(tooth.get("DSG_label_verified", False)):
            self.report({"ERROR"}, f"FDI {fdi} todavía no ha sido aceptado en la revisión de dentición")
            return {"CANCELLED"}
        data = _tooth_axis_data(tooth)
        if not data:
            self.report({"ERROR"}, f"No se pudo calcular un eje longitudinal estable para FDI {fdi}")
            return {"CANCELLED"}
        axis = Vector(data["axis"])
        if axis.length < 1e-8:
            self.report({"ERROR"}, "Eje dental degenerado")
            return {"CANCELLED"}
        axis.normalize()
        confidence = float(data.get("confidence", 0.0) or 0.0)
        if confidence < 0.18:
            self.report({"ERROR"}, f"Eje FDI {fdi} demasiado ambiguo ({confidence:.2f}); requiere ajuste manual")
            return {"CANCELLED"}

        empty = bpy.data.objects.get(guide_module.IMPLANT_AXIS_EMPTY_NAME)
        if empty is None:
            empty = bpy.data.objects.new(guide_module.IMPLANT_AXIS_EMPTY_NAME, None)
            empty.empty_display_type = "SINGLE_ARROW"
            empty.empty_display_size = 8.0
            context.scene.collection.objects.link(empty)
        guide_module.orient_empty_to_vector(empty, axis)
        empty.location = Vector(data["origin"])
        empty.hide_render = True
        empty.hide_viewport = False
        empty.hide_select = False
        try:
            empty.hide_set(False)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        empty["DSG_pending_implant_axis"] = True
        empty["DSG_target_fdi"] = fdi
        empty["DSG_axis_confidence"] = confidence
        empty["DSG_axis_method"] = str(data.get("method", ""))
        empty["DSG_axis_source_tooth"] = tooth.name
        empty["DSG_axis_apical_world"] = tuple(float(v) for v in axis)
        empty["DSG_axis_origin_world"] = tuple(float(v) for v in data["origin"])
        empty["DSG_axis_clinical_review_required"] = True
        # Surgical objects are linked to a dental family, but they are not
        # themselves dental-library assets. Keep linkage metadata separate from
        # the strict dental asset-role namespace.
        empty["DSG_target_family_id"] = dental_assets.family_id(fdi)
        empty["DSG_target_tooth_class"] = dental_assets.tooth_class_from_fdi(fdi)
        empty["DSG_target_arch"] = dental_assets.arch_from_fdi(fdi)
        empty["DSG_target_side"] = dental_assets.side_from_fdi(fdi)
        empty["DSG_asset_contract_sha256"] = dental_assets.contract_sha256()
        self.report({"INFO"}, f"Eje FDI {fdi} preparado ({confidence:.0%}). Revísalo antes de confirmar el implante.")
        return {"FINISHED"}


def get_case_state(context) -> dict[str, Any]:
    scene = context.scene
    stage = core.infer_stage(scene)
    dprops = getattr(scene, "dsg_props", None)
    aprops = getattr(scene, "dicp_props", None)
    teeth_payload = cbct_dental_module.current_payload(scene)
    teeth_payload["analysis_completed"] = bool(_tooth_analysis_completed(scene))
    implants = []
    if dprops is not None:
        for obj in guide_module.get_all_implant_objects(dprops):
            target_fdi = int(obj.get("DSG_target_fdi", 0) or 0)
            implants.append({
                "name": obj.name,
                "target_fdi": target_fdi,
                "family_id": dental_assets.family_id(target_fdi) if _valid_fdi(target_fdi) else "",
                "diameter_mm": float(obj.get("DSG_implant_diameter", 0.0) or 0.0),
                "length_mm": float(obj.get("DSG_implant_length", 0.0) or 0.0),
                "axis_source": str(obj.get("DSG_implant_axis_source", "") or ""),
            })
    frame = getattr(dprops, "frame_obj", None) if dprops else None
    guide = guide_module.get_active_guide_obj(dprops) if dprops else None
    pending_irr = guide_module.get_pending_irrigation_preview(dprops) if dprops else None
    return {
        "schema": "dsg.case_state.v1",
        "asset_contract": {
            "schema": dental_assets.schema(),
            "version": dental_assets.contract_version(),
            "sha256": dental_assets.contract_sha256(),
            "file": dental_assets.CONTRACT_FILENAME,
        },
        "timestamp": _now(),
        "case_id": _case_fingerprint(),
        "clinical_route": core.clinical_route(scene),
        "restoration_scenario": str(scene.get("DSG_restoration_scenario", "HEALED_SITE") or "HEALED_SITE"),
        "target_fdi": int(core.target_fdi(scene)),
        "immediate_extraction_prepared": bool(scene.get("DSG_immediate_extraction_prepared", False)),
        "stage": stage,
        "dsg_step": int(getattr(dprops, "current_step", -1)) if dprops else -1,
        "alignment": {
            "aligned": bool(getattr(aprops, "aligned", False)) if aprops else False,
            "quality_approved": bool(getattr(aprops, "alignment_quality_approved", False)) if aprops else False,
            "error_mm": float(getattr(aprops, "icp_error", 0.0) or 0.0) if aprops else 0.0,
            "p95_mm": float(getattr(aprops, "icp_p95", 0.0) or 0.0) if aprops else 0.0,
        },
        "tooth_analysis": teeth_payload,
        "implants": implants,
        "frame_ready": bool(guide_module._valid_obj(frame)),
        "sleeves_applied": bool(guide_module._valid_obj(guide) and guide.get("DSG_sleeves_applied", False)),
        "irrigation": {
            "confirmed_paths": int(getattr(dprops, "irr_chain_count", 0) or 0) if dprops else 0,
            "pending_preview": bool(guide_module._valid_obj(pending_irr)),
            "mode": str(getattr(dprops, "irr_sleeve_channel_mode", "C") or "C") if dprops else "C",
        },
        "clinical": clinical_context.clinical_summary(scene=scene),
        "evidence": evidence_context.evidence_status(scene=scene),
        "bridge": {"export_allowed": False, "arbitrary_bpy_allowed": False},
    }


def _mark_external_completion(plan, step_id, actor="clinician_ui", result="observed_done"):
    step = _step(plan, step_id)
    if step and step.get("status") != "done":
        step["status"] = "done"
        step["confirmed_by"] = actor
        _append_log(plan, step_id=step_id, action="reconcile", actor=actor, result=result)


def reconcile_plan(context, plan: dict[str, Any]) -> dict[str, Any]:
    """Update plan status from scene truth without fabricating completed work."""
    scene = context.scene
    plan_case = str(plan.get("case_id", "unbound") or "unbound")
    current_case = _case_fingerprint()
    if plan_case not in {"unbound", current_case}:
        plan["status"] = "blocked"
        plan["stale_case"] = True
        plan["blocked_reason"] = "El CBCT activo no coincide con el caso para el que se creó este roadmap."
        for item in plan.get("steps", []):
            if str(item.get("status", "pending")) not in {"done", "failed"}:
                item["status"] = "blocked"
                item["blocked_reason"] = "Case fingerprint mismatch"
        return plan
    plan.pop("stale_case", None)
    plan.pop("blocked_reason", None)
    failed_snapshot = {
        str(step.get("id")): (str(step.get("error", "")), str(step.get("status", "")))
        for step in plan.get("steps", []) if str(step.get("status", "")) == "failed"
    }
    target = plan.get("target") or {}
    fdi = int(target.get("fdi", 0) or 0)
    dprops = getattr(scene, "dsg_props", None)
    aprops = getattr(scene, "dicp_props", None)
    stage = core.infer_stage(scene)
    current_step = int(getattr(dprops, "current_step", -1)) if dprops else -1

    tooth = _find_tooth_object(fdi)
    if _tooth_analysis_completed(scene):
        _mark_external_completion(plan, "tooth_analysis", result="tooth_analysis_completed")
    else:
        st = _step(plan, "tooth_analysis")
        if st and st.get("status") not in {"running", "failed", "done"}:
            st["status"] = "ready"

    align = _step(plan, "alignment_review")
    if stage == core.STAGE_GUIDE:
        _mark_external_completion(plan, "alignment_review")
    elif aprops and bool(getattr(aprops, "aligned", False)) and bool(getattr(aprops, "alignment_quality_approved", False)):
        if align and align.get("status") != "done":
            align["status"] = "awaiting_review"
            align["blocked_reason"] = "Revisa la superposición; el gate puede aceptar y entrar en DSG solo con confirmación explícita."
    elif align and align.get("status") != "done":
        align["status"] = "blocked"
        align["blocked_reason"] = "Requiere landmarks/zonas y alineamiento clínico en Blender."

    model_gate = _step(plan, "guide_model_review")
    if current_step >= guide_module.STEP_IMPLANT:
        _mark_external_completion(plan, "guide_model_review")
    elif model_gate and stage == core.STAGE_GUIDE:
        model_gate["status"] = "awaiting_review"
        model_gate["blocked_reason"] = "Completa el modelo retentivo/blockout y confirma su eje de inserción en Blender."
    elif model_gate:
        model_gate["status"] = "blocked"

    extraction_gate = _step(plan, "virtual_extraction_review")
    if extraction_gate is not None:
        target_scenario = str(target.get("scenario", "HEALED_SITE") or "HEALED_SITE").upper()
        if target_scenario != "IMMEDIATE_EXTRACTION":
            extraction_gate["status"] = "done"
        elif guide_module._immediate_extraction_ready(scene):
            _mark_external_completion(plan, "virtual_extraction_review", result="prealignment_socket_models_prepared")
        else:
            extraction_gate["status"] = "awaiting_review" if stage == core.STAGE_DICOM else "blocked"
            extraction_gate["blocked_reason"] = (
                "Antes de alinear: confirma FDI, selecciona uno o varios dientes, pulsa H, "
                "crea los dos modelos por arcada y confirma que el nervio sigue separado."
            )

    axis_step = _step(plan, "axis_from_fdi")
    axis_obj = guide_module.get_pending_implant_axis_empty()
    implant = _find_implant_for_fdi(fdi)
    if axis_obj is not None and int(axis_obj.get("DSG_target_fdi", 0) or 0) == fdi:
        _mark_external_completion(plan, "axis_from_fdi", result="axis_preview_ready")
    elif implant is not None and str(implant.get("DSG_implant_axis_source", "")) == "fdi_tooth_axis":
        _mark_external_completion(plan, "axis_from_fdi", result="axis_consumed_by_existing_implant")
    elif axis_step and stage == core.STAGE_GUIDE and tooth is not None and dprops and int(dprops.current_step) == guide_module.STEP_IMPLANT:
        extraction_ok = extraction_gate is None or extraction_gate.get("status") == "done"
        axis_step["status"] = "ready" if extraction_ok else "blocked"
    elif axis_step and axis_step.get("status") != "done":
        axis_step["status"] = "blocked"

    if implant is not None:
        _mark_external_completion(plan, "implant_preview", result="implant_preview_exists")
    imp_preview = _step(plan, "implant_preview")
    if imp_preview and imp_preview.get("status") != "done":
        imp_preview["status"] = "ready" if axis_step and axis_step.get("status") == "done" else "blocked"

    imp_confirm = _step(plan, "implant_confirm")
    if implant is not None and current_step >= guide_module.STEP_CONTOUR:
        _mark_external_completion(plan, "implant_confirm")
    elif imp_confirm and implant is not None:
        imp_confirm["status"] = "awaiting_review"
    elif imp_confirm:
        imp_confirm["status"] = "blocked"

    contour = _step(plan, "contour_review")
    if current_step >= guide_module.STEP_FRAME:
        _mark_external_completion(plan, "contour_review")
    elif contour:
        contour["status"] = "awaiting_review" if current_step == guide_module.STEP_CONTOUR else "blocked"

    frame = getattr(dprops, "frame_obj", None) if dprops else None
    if guide_module._valid_obj(frame) or current_step >= guide_module.STEP_SLEEVE:
        _mark_external_completion(plan, "frame_preview", result="frame_exists_or_stage_advanced")
    fp = _step(plan, "frame_preview")
    if fp and fp.get("status") != "done":
        fp["status"] = "ready" if current_step == guide_module.STEP_FRAME else "blocked"
    fc = _step(plan, "frame_confirm")
    if current_step >= guide_module.STEP_SLEEVE:
        _mark_external_completion(plan, "frame_confirm")
    elif fc and guide_module._valid_obj(frame):
        fc["status"] = "awaiting_review"
    elif fc:
        fc["status"] = "blocked"

    previews = guide_module.get_sleeve_preview_objects() if dprops else []
    if previews:
        _mark_external_completion(plan, "sleeve_preview", result="sleeve_preview_exists")
    sp = _step(plan, "sleeve_preview")
    if sp and sp.get("status") != "done":
        sp["status"] = "ready" if current_step == guide_module.STEP_SLEEVE else "blocked"
    guide = guide_module.get_active_guide_obj(dprops) if dprops else None
    sleeves_applied = bool(guide_module._valid_obj(guide) and guide.get("DSG_sleeves_applied", False))
    if sleeves_applied:
        _mark_external_completion(plan, "sleeve_preview", result="sleeves_already_applied")
        _mark_external_completion(plan, "sleeve_confirm", result="sleeves_applied")
    sc = _step(plan, "sleeve_confirm")
    if sc and sc.get("status") != "done":
        sc["status"] = "awaiting_review" if previews else "blocked"

    pending = guide_module.get_pending_irrigation_preview(dprops) if dprops else None
    if guide_module._valid_obj(pending):
        _mark_external_completion(plan, "irrigation_preview", result="irrigation_preview_exists")
    ip = _step(plan, "irrigation_preview")
    if ip and ip.get("status") != "done":
        points = target.get("irrigation_points") or []
        ip["status"] = "ready" if sleeves_applied and len(points) >= 2 and current_step == guide_module.STEP_IRRIGATION else "blocked"
        if not points:
            ip["blocked_reason"] = "Faltan puntos explícitos para el trayecto de irrigación."

    confirmed_paths = int(getattr(dprops, "irr_chain_count", 0) or 0) if dprops else 0
    ipc = _step(plan, "irrigation_path_confirm")
    if confirmed_paths > 0 and not guide_module._valid_obj(pending):
        _mark_external_completion(plan, "irrigation_path_confirm", result="irrigation_path_confirmed")
    elif ipc and guide_module._valid_obj(pending):
        ipc["status"] = "awaiting_review"
    elif ipc:
        ipc["status"] = "blocked"

    ia = _step(plan, "irrigation_apply")
    if current_step > guide_module.STEP_IRRIGATION and confirmed_paths > 0:
        _mark_external_completion(plan, "irrigation_apply", result="irrigation_applied")
    elif ia and confirmed_paths > 0:
        ia["status"] = "awaiting_review"
    elif ia:
        ia["status"] = "blocked"

    for failed_id, (error, _status) in failed_snapshot.items():
        failed_step = _step(plan, failed_id)
        if failed_step is not None:
            failed_step["status"] = "failed"
            if error:
                failed_step["error"] = error

    statuses = [str(s.get("status", "pending")) for s in plan.get("steps", [])]
    if statuses and all(v == "done" for v in statuses):
        plan["status"] = "done"
    elif any(v == "failed" for v in statuses):
        plan["status"] = "failed"
    elif any(v == "awaiting_review" for v in statuses):
        plan["status"] = "awaiting_review"
    elif any(v == "ready" for v in statuses):
        plan["status"] = "ready"
    else:
        plan["status"] = "blocked"
    return plan


def _view3d_override():
    """Return a valid VIEW_3D override for timer/MCP initiated operators.

    bpy.app.timers callbacks do not inherit the area/region that a sidebar
    button normally has.  Several legacy DSG execute() operators are mostly
    context-independent but still touch view-layer or View3D helpers.  Using a
    real window/area/region when one exists makes MCP execution match the UI
    path instead of depending on whichever editor happens to be active.
    """
    wm = getattr(bpy.context, "window_manager", None)
    if wm is None:
        return None
    for window in list(getattr(wm, "windows", []) or []):
        screen = getattr(window, "screen", None)
        if screen is None:
            continue
        for area in list(getattr(screen, "areas", []) or []):
            if getattr(area, "type", None) != "VIEW_3D":
                continue
            region = next((r for r in area.regions if r.type == "WINDOW"), None)
            if region is None:
                continue
            return {"window": window, "screen": screen, "area": area, "region": region}
    return None


def _call_operator(idname: str, **kwargs):
    namespace, op = idname.split(".", 1)
    proxy = getattr(getattr(bpy.ops, namespace), op)
    override = _view3d_override()
    if override:
        with bpy.context.temp_override(**override):
            result = proxy("EXEC_DEFAULT", **kwargs)
    else:
        result = proxy("EXEC_DEFAULT", **kwargs)
    return "FINISHED" in result


def _audit_parameters_for_step(plan: dict[str, Any], step_id: str, allow_auto_confirm: bool) -> dict[str, Any]:
    target = plan.get("target") or {}
    params = {
        "fdi": int(target.get("fdi", 0) or 0),
        "allow_auto_confirm": bool(allow_auto_confirm),
    }
    if step_id in {"implant_preview", "implant_confirm", "sleeve_preview", "sleeve_confirm"}:
        params["diameter_mm"] = target.get("diameter_mm")
        params["length_mm"] = target.get("length_mm")
    if step_id.startswith("irrigation_"):
        points = target.get("irrigation_points") or []
        params["irrigation_mode"] = str(target.get("irrigation_mode", "DIRECT"))
        params["irrigation_points"] = points if step_id == "irrigation_preview" else None
        params["irrigation_point_count"] = len(points)
    return params


def execute_step(context, plan: dict[str, Any], step_id: str, *, allow_auto_confirm=False, actor="mcp_orchestrator"):
    reconcile_plan(context, plan)
    if bool(plan.get("stale_case", False)):
        _append_log(plan, step_id=step_id, action="execute", actor=actor, result="blocked_case_mismatch")
        _save_plan(context.scene, plan)
        return {
            "ok": False, "status": "blocked",
            "message": "The active CBCT does not match this roadmap case_id",
        }
    step = _step(plan, step_id)
    if step is None:
        raise ValueError(f"Unknown step_id: {step_id}")
    ordered = list(plan.get("steps", []))
    step_index = ordered.index(step)
    unfinished_before = [
        prior for prior in ordered[:step_index]
        if str(prior.get("status", "pending")) != "done"
    ]
    if unfinished_before:
        blocker = unfinished_before[0]
        return {
            "ok": False, "status": "blocked",
            "message": f"Complete first: {blocker.get('title', blocker.get('id'))}",
            "blocked_by": blocker.get("id"),
        }
    if step.get("status") == "done":
        return {"ok": True, "status": "done", "message": "Step already complete"}
    if not bool(step.get("auto_executable", False)):
        step["status"] = "awaiting_review"
        _append_log(plan, step_id=step_id, action="manual_gate", actor=actor, result="awaiting_review")
        _save_plan(context.scene, plan)
        return {"ok": False, "status": "awaiting_review", "message": step.get("note") or "Manual clinical action required"}
    if bool(step.get("requires_confirmation", False)) and not bool(allow_auto_confirm):
        step["status"] = "awaiting_review"
        _append_log(plan, step_id=step_id, action="confirmation_gate", actor=actor, result="awaiting_review")
        _save_plan(context.scene, plan)
        return {"ok": False, "status": "awaiting_review", "message": "Explicit confirmation required"}

    target = plan.get("target") or {}
    fdi = int(target.get("fdi", 0) or 0)
    step["status"] = "running"
    audit_parameters = _audit_parameters_for_step(plan, step_id, bool(allow_auto_confirm))
    _append_log(plan, step_id=step_id, action="execute", actor=actor, result="started",
                parameters=audit_parameters)
    _save_plan(context.scene, plan)

    try:
        ok = False
        if step_id == "tooth_analysis":
            raise RuntimeError("La dentición IA es asíncrona y requiere revisión humana en Alineamiento")
        elif step_id == "alignment_review":
            aprops = context.scene.dicp_props
            if not bool(getattr(aprops, "aligned", False)) or not bool(getattr(aprops, "alignment_quality_approved", False)):
                raise RuntimeError("Alignment has not passed the three-zone validation")
            ok = _call_operator("dicp.send_to_dsg")
        elif step_id == "virtual_extraction_review":
            if str(target.get("scenario", "HEALED_SITE") or "HEALED_SITE").upper() != "IMMEDIATE_EXTRACTION":
                ok = True
            else:
                raise RuntimeError(
                    "La preparación alveolar de implante inmediato es un paso clínico manual previo al alineamiento: "
                    "FDI → seleccionar dientes → H → unir por arcada → confirmar."
                )
        elif step_id == "axis_from_fdi":
            ok = _call_operator("dsg.set_axis_from_fdi", fdi=fdi)
        elif step_id == "implant_preview":
            dprops = context.scene.dsg_props
            if target.get("diameter_mm") is not None:
                dprops.implant_diameter = float(target["diameter_mm"])
            if target.get("length_mm") is not None:
                dprops.implant_length = float(target["length_mm"])
            ok = _call_operator("dsg.create_implant")
        elif step_id == "implant_confirm":
            ok = _call_operator("dsg.confirm_implant")
        elif step_id == "frame_preview":
            ok = _call_operator("dsg.build_tube_frame")
        elif step_id == "frame_confirm":
            ok = _call_operator("dsg.confirm_tube_frame")
        elif step_id == "sleeve_preview":
            ok = _call_operator("dsg.add_sleeve")
        elif step_id == "sleeve_confirm":
            ok = _call_operator("dsg.apply_sleeves")
        elif step_id == "irrigation_preview":
            points = target.get("irrigation_points") or []
            if len(points) < 2:
                raise RuntimeError("Explicit irrigation points are required")
            dprops = context.scene.dsg_props
            dprops.irr_sleeve_channel_mode = str(target.get("irrigation_mode", "DIRECT"))
            implant = _find_implant_for_fdi(fdi)
            ok, message = guide_module.build_irrigation_preview_from_points(
                context, dprops, points, implant=implant)
            if not ok:
                raise RuntimeError(message)
        elif step_id == "irrigation_path_confirm":
            ok = _call_operator("dsg.confirm_irrigation_preview")
        elif step_id == "irrigation_apply":
            ok = _call_operator("dsg.confirm_irrigation")
        else:
            raise RuntimeError("This step is intentionally not executable")
        if not ok:
            raise RuntimeError("Blender operator returned CANCELLED")
    except Exception as exc:
        step["status"] = "failed"
        step["error"] = f"{type(exc).__name__}: {exc}"
        failed_parameters = dict(audit_parameters)
        failed_parameters["error"] = step["error"]
        _append_log(plan, step_id=step_id, action="execute", actor=actor, result="failed",
                    parameters=failed_parameters)
        reconcile_plan(context, plan)
        _save_plan(context.scene, plan)
        return {"ok": False, "status": "failed", "message": step["error"]}

    step["status"] = "done"
    step["completed_at"] = _now()
    step["confirmed_by"] = actor if step.get("requires_confirmation") else "deterministic_operator"
    done_parameters = dict(audit_parameters)
    done_parameters["confirmed_by"] = step["confirmed_by"]
    _append_log(plan, step_id=step_id, action="execute", actor=actor, result="done",
                parameters=done_parameters)
    reconcile_plan(context, plan)
    _save_plan(context.scene, plan)
    return {"ok": True, "status": step["status"], "message": "Step completed"}


@dataclass
class _BridgeEnvelope:
    request: dict[str, Any]
    event: threading.Event
    result: dict[str, Any] | None = None


_REQUEST_QUEUE: queue.Queue[_BridgeEnvelope] = queue.Queue()
_BRIDGE_SERVER = None
_BRIDGE_THREAD = None
_BRIDGE_TIMER_REGISTERED = False


class _ThreadingLocalServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


class _BridgeHandler(socketserver.StreamRequestHandler):
    def handle(self):
        try:
            raw = self.rfile.readline(MAX_REQUEST_BYTES + 1)
            if len(raw) > MAX_REQUEST_BYTES:
                raise ValueError("Request too large")
            request = json.loads(raw.decode("utf-8"))
            envelope = _BridgeEnvelope(request=request, event=threading.Event())
            _REQUEST_QUEUE.put(envelope)
            if not envelope.event.wait(BRIDGE_TIMEOUT_SECONDS):
                response = {"ok": False, "error": "Blender main-thread timeout"}
            else:
                response = envelope.result or {"ok": False, "error": "Empty response"}
        except Exception as exc:
            response = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        self.wfile.write((json.dumps(response, ensure_ascii=False) + "\n").encode("utf-8"))


def _dispatch_operation(scene, op: str, args: dict[str, Any]) -> dict[str, Any]:
    # Agent-runtime meta operations are safe wrappers around a second, smaller
    # capability manifest.  Generic execute_step remains outside that facade.
    if op in {"get_agent_capabilities", "get_dsg_scene_graph", "get_agent_operation_history",
              "get_agent_operation_status", "agent_run_tool"}:
        from . import agent_facade, agent_scene_graph
        if op == "get_agent_capabilities":
            return {"ok": True, "result": agent_facade.get_capabilities(scene)}
        if op == "get_dsg_scene_graph":
            return {"ok": True, "result": agent_scene_graph.get_scene_graph(scene)}
        if op == "get_agent_operation_history":
            return {"ok": True, "result": agent_facade.get_operation_history(scene, int(args.get("limit", 50) or 50))}
        if op == "get_agent_operation_status":
            return {"ok": True, "result": agent_facade.get_operation_status(str(args.get("operation_id", "") or ""), scene)}
        return {"ok": True, "result": agent_facade.run_agent_tool(
            str(args.get("tool", "") or ""),
            args.get("params") or {},
            operation_id=args.get("operation_id"),
            scene=scene,
        )}

    # Closed whitelist. export_guide_stl and arbitrary operator names are absent.
    if op == "get_case_state":
        return {"ok": True, "result": get_case_state(bpy.context)}
    if op == "get_segmentation_status":
        import importlib
        cbct_ai_runtime = importlib.import_module(f"{__package__}.cbct_ai_runtime")
        snapshot = dict(dicom_module.segmentation_progress_snapshot(bpy.context))
        job = dict(cbct_ai_runtime.prediction_job_state())
        started_at = float(job.get("started_at", 0.0) or 0.0)
        finished_at = float(job.get("finished_at", 0.0) or 0.0)
        job["elapsed_s"] = max(
            0.0,
            (finished_at if finished_at > 0.0 else time.time()) - started_at,
        ) if started_at > 0.0 else 0.0
        props = getattr(scene, "dicom_wizard_pro", None)
        return {"ok": True, "result": {
            "schema": "dsg.segmentation_status.v1",
            "active": bool(snapshot.get("active") or job.get("running")),
            "progress": snapshot,
            "prediction_job": job,
            "performance_plan": cbct_ai_runtime.last_performance_plan(),
            "ui_status": str(getattr(props, "status", "") or "") if props else "",
            "volume_loaded": bool(getattr(props, "volume_loaded", False)) if props else False,
            "surface_ready": bool(getattr(props, "surface_ready", False)) if props else False,
            "last_error": str(scene.get("DSG_last_segmentation_error", "") or ""),
            "last_error_phase": str(scene.get("DSG_last_segmentation_error_phase", "") or ""),
            "last_elapsed_s": float(scene.get("DSG_last_segmentation_elapsed_s", 0.0) or 0.0),
            "last_finished_at": float(scene.get("DSG_last_segmentation_finished_at", 0.0) or 0.0),
            "last_success": bool(scene.get("DSG_last_segmentation_success", False)),
            "route": str(scene.get("DSG_cbct_requested_engine_route", "") or ""),
        }}
    if op == "start_full_segmentation":
        allow_write = args.get("allow_segmentation_write", False)
        if not isinstance(allow_write, bool) or not allow_write:
            raise PermissionError("start_full_segmentation requires allow_segmentation_write=true")
        props = getattr(scene, "dicom_wizard_pro", None)
        if props is None or not bool(getattr(props, "volume_loaded", False)):
            raise RuntimeError("No hay un CBCT cargado para segmentar")
        if dicom_module.semantic_workflow_busy():
            raise RuntimeError("Ya hay una segmentación CBCT en curso")
        ok, message = dicom_module._close_mpr_before_workflow_action(bpy.context)
        if not ok:
            raise RuntimeError(message)
        if not dicom_module._start_async_full_segmentation(bpy.context, structure="ALL"):
            raise RuntimeError("No se pudo iniciar la segmentación completa")
        scene["DSG_cbct_requested_engine_route"] = "DENTALSEGMENTATOR+UNIVERSALLAB"
        scene["DSG_segmentation_started_by"] = "MCP"
        return _dispatch_operation(scene, "get_segmentation_status", {})
    if op == "get_patient_clinical_context":
        return {"ok": True, "result": clinical_context.get_patient_clinical_context(scene)}
    if op == "set_patient_clinical_context":
        allow_write = args.get("allow_clinical_write", False)
        if not isinstance(allow_write, bool) or not allow_write:
            raise PermissionError("set_patient_clinical_context requires allow_clinical_write=true")
        payload = args.get("context") or {}
        if not isinstance(payload, dict):
            raise ValueError("context must be an object")
        result = clinical_context.set_patient_clinical_context(
            payload, scene=scene, replace=bool(args.get("replace", True))
        )
        result = dict(result)
        result["context_sha256"] = clinical_context.clinical_summary(scene=scene)["context_sha256"]
        return {"ok": True, "result": result}
    if op == "clear_patient_clinical_context":
        allow_write = args.get("allow_clinical_write", False)
        if not isinstance(allow_write, bool) or not allow_write:
            raise PermissionError("clear_patient_clinical_context requires allow_clinical_write=true")
        return {"ok": True, "result": clinical_context.clear_patient_clinical_context(
            scene=scene, country_code=str(args.get("country_code", "ES") or "ES")
        )}
    if op == "get_clinical_source_registry":
        country = str(args.get("country_code", "") or clinical_context.get_patient_clinical_context(scene).get("country_code", "XX"))
        return {"ok": True, "result": clinical_context.get_country_source_registry(country)}
    if op == "build_medication_lookup_request":
        country = str(args.get("country_code", "") or clinical_context.get_patient_clinical_context(scene).get("country_code", "XX"))
        return {"ok": True, "result": clinical_context.build_medication_lookup_request(
            str(args.get("term", "") or ""), country, scene=scene
        )}
    if op == "build_clinical_guidance_request":
        procedure = args.get("procedure") or {}
        if not isinstance(procedure, dict):
            raise ValueError("procedure must be an object")
        return {"ok": True, "result": clinical_context.build_clinical_guidance_request(procedure, scene=scene)}
    if op == "get_clinical_guidance_request":
        return {"ok": True, "result": clinical_context.get_clinical_guidance_request(scene=scene)}
    if op == "apply_clinical_guidance_result":
        allow_write = args.get("allow_clinical_write", False)
        if not isinstance(allow_write, bool) or not allow_write:
            raise PermissionError("apply_clinical_guidance_result requires allow_clinical_write=true")
        payload = args.get("result") or {}
        if not isinstance(payload, dict):
            raise ValueError("result must be an object")
        return {"ok": True, "result": clinical_context.apply_clinical_guidance_result(payload, scene=scene)}
    if op == "get_clinical_guidance_result":
        return {"ok": True, "result": clinical_context.get_clinical_guidance_result(scene=scene)}
    if op == "get_evidence_repository_summary":
        return {"ok": True, "result": evidence_context.evidence_status(scene=scene)}
    if op == "get_evidence_rule":
        return {"ok": True, "result": evidence_context.get_evidence_rule(str(args.get("rule_id", "") or ""))}
    if op == "get_evidence_topic":
        return {"ok": True, "result": evidence_context.get_evidence_topic(str(args.get("topic", "") or ""))}
    if op == "search_offline_evidence":
        return {"ok": True, "result": evidence_context.search_offline_evidence(
            str(args.get("query", "") or ""), int(args.get("limit", 30) or 30))}
    if op == "build_evidence_update_request":
        topics = args.get("topics")
        if topics is not None and not isinstance(topics, (list, tuple)):
            raise ValueError("topics must be an array or null")
        country = str(args.get("country_code", "") or clinical_context.get_patient_clinical_context(scene).get("country_code", "INT"))
        return {"ok": True, "result": evidence_context.build_evidence_update_request(
            topics, country_code=country, scene=scene)}
    if op == "get_evidence_update_request":
        return {"ok": True, "result": evidence_context.get_evidence_update_request(scene=scene)}
    if op == "store_evidence_update_proposal":
        allow_write = args.get("allow_evidence_write", False)
        if not isinstance(allow_write, bool) or not allow_write:
            raise PermissionError("store_evidence_update_proposal requires allow_evidence_write=true")
        payload = args.get("proposal") or {}
        if not isinstance(payload, dict):
            raise ValueError("proposal must be an object")
        return {"ok": True, "result": evidence_context.store_evidence_update_proposal(payload, scene=scene)}
    if op == "get_evidence_update_proposal":
        return {"ok": True, "result": evidence_context.get_evidence_update_proposal(scene=scene)}
    if op == "get_dental_asset_contract":
        return {"ok": True, "result": dental_mapping_service.get_dental_asset_contract()}
    if op == "get_dental_family":
        fdi = int(args.get("fdi", 0) or 0)
        return {"ok": True, "result": dental_mapping_service.family_descriptor(fdi)}
    if op == "get_required_landmarks":
        fdi = int(args.get("fdi", 0) or 0)
        return {"ok": True, "result": {"fdi": fdi, "landmarks": list(dental_mapping_service.required_landmarks(fdi))}}
    if op == "get_dental_landmarks":
        fdi = int(args.get("fdi", 0) or 0)
        return {"ok": True, "result": {"fdi": fdi, "landmarks": dental_mapping_service.get_landmarks(fdi)}}
    if op == "get_dental_mapping_quality":
        fdi = int(args.get("fdi", 0) or 0)
        return {"ok": True, "result": dental_mapping_service.get_mapping_quality(fdi)}
    if op == "get_gold_standard":
        fdi = int(args.get("fdi", 0) or 0)
        return {"ok": True, "result": dental_mapping_service.get_gold_standard(fdi)}
    if op == "build_implant_planning_context":
        fdi = int(args.get("fdi", 0) or 0)
        return {"ok": True, "result": dental_mapping_service.build_implant_planning_context(fdi)}
    if op in {"map_patient_crown", "map_patient_tooth"}:
        fdi = int(args.get("fdi", 0) or 0)
        allow_write = args.get("allow_mapping_write", False)
        if not isinstance(allow_write, bool) or not allow_write:
            raise PermissionError(f"{op} requires JSON boolean allow_mapping_write=true")
        result = dental_mapping_service.map_patient_crown(fdi)
        if op == "map_patient_tooth":
            result["compatibility_alias"] = "map_patient_tooth->map_patient_crown"
        return {"ok": bool(result.get("ok")), "result": result}
    if op == "fit_crown_to_neighbors":
        fdi = int(args.get("fdi", 0) or 0)
        allow_write = args.get("allow_geometry_write", False)
        if not isinstance(allow_write, bool) or not allow_write:
            raise PermissionError("fit_crown_to_neighbors requires JSON boolean allow_geometry_write=true")
        context = args.get("context") or {}
        if not isinstance(context, dict):
            raise ValueError("context must be an object")
        result = dental_mapping_service.fit_crown_to_neighbors(fdi, context)
        return {"ok": True, "result": result}
    if op == "fit_occlusion":
        fdi = int(args.get("fdi", 0) or 0)
        allow_write = args.get("allow_geometry_write", False)
        if not isinstance(allow_write, bool) or not allow_write:
            raise PermissionError("fit_occlusion requires JSON boolean allow_geometry_write=true")
        antagonist_name = str(args.get("antagonist_object", "") or "")
        antagonist = bpy.data.objects.get(antagonist_name)
        if antagonist is None:
            raise ValueError("antagonist_object not found")
        return {"ok": True, "result": dental_mapping_service.fit_occlusion(fdi, antagonist)}
    if op == "analyze_implant_bone_support":
        fdi = int(args.get("fdi", 0) or 0)
        return {"ok": True, "result": dental_mapping_service.analyze_implant_bone_support(
            fdi, args.get("implant_name"),
            radial_offset_mm=float(args.get("radial_offset_mm", 0.75)),
            axial_samples=int(args.get("axial_samples", 18)),
            angular_samples=int(args.get("angular_samples", 16)),
            include_samples=bool(args.get("include_samples", False)),
        )}
    if op == "analyze_implant_neighbor_clearance":
        fdi = int(args.get("fdi", 0) or 0)
        required = args.get("required_clearance_mm")
        verification_mode = str(args.get("verification_mode", "FAST") or "FAST")
        return {"ok": True, "result": dental_mapping_service.analyze_implant_neighbor_clearance(
            fdi, args.get("implant_name"),
            None if required is None else float(required),
            verification_mode=verification_mode,
        )}
    if op == "analyze_interdental_space":
        fdi = int(args.get("fdi", 0) or 0)
        return {"ok": True, "result": dental_mapping_service.analyze_interdental_space(
            fdi, args.get("implant_name")
        )}
    if op == "analyze_implant_diameter_options":
        fdi = int(args.get("fdi", 0) or 0)
        diameters = args.get("diameters_mm", [])
        if not isinstance(diameters, (list, tuple)):
            raise ValueError("diameters_mm must be an array of catalog diameters")
        return {"ok": True, "result": dental_mapping_service.analyze_implant_diameter_options(
            fdi, args.get("implant_name"),
            diameters_mm=[float(v) for v in diameters],
            clearance_mm=float(args.get("clearance_mm", 1.5)),
            verification_mode=str(args.get("verification_mode", "FAST") or "FAST"),
        )}
    if op == "apply_implant_bone_support_heatmap":
        fdi = int(args.get("fdi", 0) or 0)
        allow_write = args.get("allow_visualization_write", False)
        if not isinstance(allow_write, bool) or not allow_write:
            raise PermissionError("apply_implant_bone_support_heatmap requires allow_visualization_write=true")
        ring_offsets = args.get("ring_offsets_mm", [0.25, 0.50, 1.00])
        if not isinstance(ring_offsets, (list, tuple)):
            raise ValueError("ring_offsets_mm must be an array")
        return {"ok": True, "result": dental_mapping_service.apply_implant_bone_support_heatmap(
            fdi, args.get("implant_name"),
            radial_offset_mm=float(args.get("radial_offset_mm", 0.75)),
            sampling_mode=str(args.get("sampling_mode", "SURFACE_NORMAL_AVERAGE")),
            ring_offsets_mm=tuple(float(x) for x in ring_offsets),
            emission_strength=float(args.get("emission_strength", 0.25)),
        )}
    if op == "clear_implant_bone_support_heatmap":
        allow_write = args.get("allow_visualization_write", False)
        if not isinstance(allow_write, bool) or not allow_write:
            raise PermissionError("clear_implant_bone_support_heatmap requires allow_visualization_write=true")
        return {"ok": True, "result": dental_mapping_service.clear_implant_bone_support_heatmap(
            args.get("implant_name")
        )}
    if op == "build_full_implant_context":
        fdi = int(args.get("fdi", 0) or 0)
        result = dental_mapping_service.build_full_implant_context(fdi, args.get("implant_name"))
        result["clinical"] = clinical_context.clinical_summary(scene=scene)
        result["evidence"] = evidence_context.evidence_status(scene=scene)
        return {"ok": True, "result": result}
    if op == "build_preoperative_context":
        fdi = int(args.get("fdi", 0) or 0)
        procedure = args.get("procedure") or {}
        if not isinstance(procedure, dict):
            raise ValueError("procedure must be an object")
        procedure = dict(procedure)
        procedure.setdefault("fdi", fdi)
        procedure.setdefault("procedure", "implant_surgery")
        surgical = dental_mapping_service.build_full_implant_context(fdi, args.get("implant_name"))
        request = clinical_context.build_clinical_guidance_request(procedure, scene=scene)
        guidance = clinical_context.get_clinical_guidance_result(scene=scene)
        if guidance and str(guidance.get("request_sha256", "") or "") != str(request.get("request_sha256", "") or ""):
            guidance = None
        return {"ok": True, "result": {
            "schema": "dsg.preoperative_context.v1",
            "fdi": fdi,
            "surgical_context": surgical,
            "patient_clinical_context": clinical_context.get_patient_clinical_context(scene),
            "clinical_guidance_request": request,
            "clinical_guidance_result": guidance,
            "clinical": clinical_context.clinical_summary(scene=scene),
            "evidence": evidence_context.evidence_status(scene=scene),
            "status": "READY" if guidance else "LIVE_CLINICAL_GUIDANCE_REQUIRED",
        }}
    if op == "prepare_implant_axis_from_prosthetic_context":
        fdi = int(args.get("fdi", 0) or 0)
        allow_write = args.get("allow_geometry_write", False)
        if not isinstance(allow_write, bool) or not allow_write:
            raise PermissionError("prepare_implant_axis_from_prosthetic_context requires allow_geometry_write=true")
        return {"ok": True, "result": dental_mapping_service.prepare_implant_axis_from_prosthetic_context(fdi)}
    if op == "evaluate_implant_candidate":
        fdi = int(args.get("fdi", 0) or 0)
        constraints = args.get("constraints") or {}
        if not isinstance(constraints, dict):
            raise ValueError("constraints must be an object")
        return {"ok": True, "result": dental_mapping_service.evaluate_implant_candidate(
            fdi, args.get("implant_name"), constraints
        )}
    if op == "get_frame_structural_contract":
        return {"ok": True, "result": frame_structural.get_contract()}
    if op == "get_frame_context":
        return {"ok": True, "result": frame_structural.get_frame_context(bpy.context)}
    if op == "set_frame_support_nodes":
        allow_write = args.get("allow_geometry_write", False)
        if not isinstance(allow_write, bool) or not allow_write:
            raise PermissionError("set_frame_support_nodes requires allow_geometry_write=true")
        points = args.get("points") or []
        if not isinstance(points, (list, tuple)):
            raise ValueError("points must be an array of exactly four XYZ points")
        return {"ok": True, "result": frame_structural.persist_support_nodes(
            bpy.context, list(points), authority=str(args.get("authority", "USER") or "USER"))}
    if op == "analyze_frame_structure":
        thresholds = args.get("thresholds") or {}
        if not isinstance(thresholds, dict):
            raise ValueError("thresholds must be an object")
        return {"ok": True, "result": frame_structural.analyze_frame_structure(
            bpy.context, thresholds=thresholds)}
    if op == "propose_frame_reinforcements":
        thresholds = args.get("thresholds") or {}
        if not isinstance(thresholds, dict):
            raise ValueError("thresholds must be an object")
        return {"ok": True, "result": frame_structural.propose_frame_reinforcements(
            bpy.context, max_candidates=int(args.get("max_candidates", 4) or 4),
            thresholds=thresholds)}
    if op == "analyze_frame_fem":
        return {"ok": True, "result": frame_structural.analyze_frame_fem(bpy.context)}
    if op == "optimize_frame_fem":
        allow_write = args.get("allow_geometry_write", False)
        if not isinstance(allow_write, bool) or not allow_write:
            raise PermissionError("optimize_frame_fem requires allow_geometry_write=true")
        return {"ok": True, "result": frame_structural.create_fem_reinforcements(
            bpy.context, replace_existing=bool(args.get("replace_existing", True)))}
    if op == "submit_plan":
        raw_plan = args.get("plan")
        if isinstance(raw_plan, str):
            raw_plan = json.loads(raw_plan)
        if not isinstance(raw_plan, dict) or raw_plan.get("schema") != ROADMAP_SCHEMA:
            raise ValueError("Unsupported roadmap schema")
        current_case = _case_fingerprint()
        proposed_case = str(raw_plan.get("case_id", "unbound") or "unbound")
        if proposed_case not in {"unbound", current_case}:
            raise RuntimeError("Stale roadmap: call get_case_state() again before submitting this plan")
        target = raw_plan.get("target") or {}
        # Rebuild from canonical fields; never trust client-supplied operator/action data.
        plan = canonical_implant_plan(
            int(target.get("fdi", 0) or 0),
            irrigation_mode=str(target.get("irrigation_mode", "DIRECT")),
            diameter=target.get("diameter_mm"),
            length=target.get("length_mm"),
            irrigation_points=target.get("irrigation_points"),
            scenario=str(target.get("scenario") or bpy.context.scene.get("DSG_restoration_scenario", "HEALED_SITE")),
            plan_id=str(raw_plan.get("plan_id") or uuid.uuid4()),
            case_id=current_case,
        )
        reconcile_plan(bpy.context, plan)
        _append_log(
            plan, action="submit_plan", actor="mcp_orchestrator", result="accepted",
            parameters={
                "case_id": current_case,
                "fdi": int(target.get("fdi", 0) or 0),
                "irrigation_mode": str(target.get("irrigation_mode", "DIRECT")),
                "diameter_mm": target.get("diameter_mm"),
                "length_mm": target.get("length_mm"),
                "irrigation_point_count": len(target.get("irrigation_points") or []),
            })
        _save_plan(scene, plan)
        return {"ok": True, "result": plan}
    if op == "execute_step":
        plan_id = str(args.get("plan_id", "") or "")
        step_id = str(args.get("step_id", "") or "")
        if step_id not in ALLOWED_STEP_IDS:
            raise ValueError("Unknown or non-whitelisted step")
        # Clinical confirmation is capability-sensitive: only a real JSON
        # boolean true may enable it. Strings such as "false" must never be
        # truthy-coerced by Python and accidentally cross a review gate.
        raw_auto_confirm = args.get("allow_auto_confirm", False)
        if not isinstance(raw_auto_confirm, bool):
            raise ValueError("allow_auto_confirm must be a JSON boolean")
        plan = _get_plan(scene, plan_id)
        if plan is None:
            raise KeyError("Plan not found")
        result = execute_step(
            bpy.context, plan, step_id,
            allow_auto_confirm=raw_auto_confirm,
            actor="mcp_orchestrator")
        return {"ok": bool(result.get("ok")), "result": result, "plan": plan}
    if op == "get_plan_status":
        plan = _get_plan(scene, str(args.get("plan_id", "") or ""))
        if plan is None:
            raise KeyError("Plan not found")
        reconcile_plan(bpy.context, plan)
        _save_plan(scene, plan)
        return {"ok": True, "result": plan}
    if op == "cancel_plan":
        plan = _get_plan(scene, str(args.get("plan_id", "") or ""))
        if plan is None:
            raise KeyError("Plan not found")
        # Cancelling a roadmap never undoes Blender geometry.  Pre-existing or
        # clinician-confirmed scene state must therefore not make a freshly
        # submitted roadmap impossible to cancel.  We only refuse cancellation
        # after MCP itself has used the explicit auto-confirm gate on a clinical
        # confirmation step; in that case the audit trail stays active.
        mcp_confirmed = [
            str(step.get("id", "")) for step in plan.get("steps", [])
            if step.get("status") == "done"
            and bool(step.get("requires_confirmation", False))
            and str(step.get("confirmed_by", "")) == "mcp_orchestrator"
        ]
        if mcp_confirmed:
            raise RuntimeError(
                "Plan contains MCP-confirmed clinical steps and cannot be cancelled: "
                + ", ".join(mcp_confirmed)
            )
        plan["status"] = "cancelled"
        _append_log(
            plan, action="cancel_plan", actor="mcp_orchestrator", result="cancelled",
            parameters={"scene_geometry_unchanged": True})
        _save_plan(scene, plan)
        return {"ok": True, "result": plan}
    raise ValueError("Operation is not whitelisted")



def _dispatch_main(request: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(request, dict):
        raise ValueError("Request must be an object")
    protocol = str(request.get("protocol", "") or "")
    if protocol != BRIDGE_PROTOCOL:
        raise ValueError(f"Unsupported bridge protocol: {protocol or 'missing'}")
    scene = bpy.context.scene
    props = getattr(scene, "dsg_roadmap_props", None)
    expected = _BRIDGE_TOKEN if props is not None else ""
    token = str(request.get("token", "") or "")
    if not expected or not secrets.compare_digest(expected, token):
        raise PermissionError("Invalid bridge token")
    op = str(request.get("op", "") or "")
    args = request.get("args") or {}
    if not isinstance(args, dict):
        raise ValueError("args must be an object")
    return _dispatch_operation(scene, op, args)


def _bridge_timer():
    global _BRIDGE_TIMER_REGISTERED
    processed = 0
    while processed < 4:
        try:
            envelope = _REQUEST_QUEUE.get_nowait()
        except queue.Empty:
            break
        try:
            envelope.result = _dispatch_main(envelope.request)
        except Exception as exc:
            envelope.result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        finally:
            envelope.event.set()
        processed += 1
    if _BRIDGE_SERVER is None:
        _BRIDGE_TIMER_REGISTERED = False
        return None
    return 0.05


def start_bridge(context):
    global _BRIDGE_SERVER, _BRIDGE_THREAD, _BRIDGE_TIMER_REGISTERED, _BRIDGE_TOKEN
    if _BRIDGE_SERVER is not None:
        return True, "Bridge already running"
    props = context.scene.dsg_roadmap_props
    host = DEFAULT_BRIDGE_HOST
    port = int(props.bridge_port)
    # Rotate the capability token on every new listener activation.
    _BRIDGE_TOKEN = secrets.token_urlsafe(24)
    try:
        server = _ThreadingLocalServer((host, port), _BridgeHandler)
    except Exception as exc:
        _BRIDGE_TOKEN = ""
        props.bridge_running = False
        props.bridge_status = "Detenido"
        return False, f"Could not bind {host}:{port}: {exc}"

    thread = threading.Thread(target=server.serve_forever, name="DSG-MCP-Bridge", daemon=True)
    thread_started = False
    try:
        thread.start()
        thread_started = True
        if not _BRIDGE_TIMER_REGISTERED:
            bpy.app.timers.register(_bridge_timer, first_interval=0.05, persistent=False)
            _BRIDGE_TIMER_REGISTERED = True
    except Exception as exc:
        try:
            if thread_started:
                server.shutdown()
            server.server_close()
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        _BRIDGE_TOKEN = ""
        props.bridge_running = False
        props.bridge_status = "Detenido"
        return False, f"Could not start MCP bridge dispatcher: {exc}"

    _BRIDGE_SERVER = server
    _BRIDGE_THREAD = thread
    props.bridge_running = True
    props.bridge_status = f"127.0.0.1:{port} · activo"
    return True, props.bridge_status


def stop_bridge(context=None):
    global _BRIDGE_SERVER, _BRIDGE_THREAD, _BRIDGE_TIMER_REGISTERED, _BRIDGE_TOKEN
    server = _BRIDGE_SERVER
    _BRIDGE_TOKEN = ""
    _BRIDGE_SERVER = None
    if server is not None:
        try:
            server.shutdown()
            server.server_close()
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    _BRIDGE_THREAD = None
    try:
        if bpy.app.timers.is_registered(_bridge_timer):
            bpy.app.timers.unregister(_bridge_timer)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    _BRIDGE_TIMER_REGISTERED = False
    # Do not leave socket-handler threads waiting for the full timeout when the
    # clinician explicitly switches the bridge off.
    while True:
        try:
            envelope = _REQUEST_QUEUE.get_nowait()
        except queue.Empty:
            break
        envelope.result = {"ok": False, "error": "DSG MCP bridge stopped"}
        envelope.event.set()
    if context is not None:
        scene = getattr(context, "scene", None)
        props = getattr(scene, "dsg_roadmap_props", None) if scene is not None else None
        if props:
            props.bridge_running = False
            props.bridge_status = "Detenido"


class DSGRoadmapProperties(PropertyGroup):
    bridge_port: IntProperty(name="Puerto", default=DEFAULT_BRIDGE_PORT, min=1024, max=65535)
    bridge_running: BoolProperty(default=False, options={"HIDDEN"})
    bridge_status: StringProperty(default="Detenido", options={"HIDDEN"})
    active_plan_id: StringProperty(default="", options={"HIDDEN"})


class DSG_OT_StartMCPBridge(Operator):
    bl_idname = "dsg.start_mcp_bridge"
    bl_label = "Start MCP Bridge"

    def execute(self, context):
        ok, message = start_bridge(context)
        self.report({"INFO" if ok else "ERROR"}, message)
        return {"FINISHED"} if ok else {"CANCELLED"}


class DSG_OT_StopMCPBridge(Operator):
    bl_idname = "dsg.stop_mcp_bridge"
    bl_label = "Stop MCP Bridge"

    def execute(self, context):
        stop_bridge(context)
        self.report({"INFO"}, "MCP bridge detenido")
        return {"FINISHED"}


class DSG_OT_CopyMCPBridgeConfig(Operator):
    bl_idname = "dsg.copy_mcp_bridge_config"
    bl_label = "Copy MCP Bridge Config"

    def execute(self, context):
        props = context.scene.dsg_roadmap_props
        payload = {
            "host": DEFAULT_BRIDGE_HOST,
            "port": int(props.bridge_port),
            "token": _BRIDGE_TOKEN,
            "protocol": BRIDGE_PROTOCOL,
        }
        context.window_manager.clipboard = json.dumps(payload, separators=(",", ":"))
        self.report({"INFO"}, "Configuración MCP copiada")
        return {"FINISHED"}


class DSG_OT_RefreshRoadmapStatus(Operator):
    bl_idname = "dsg.refresh_roadmap_status"
    bl_label = "Refresh Roadmap"

    def execute(self, context):
        pid = str(context.scene.get(ROADMAP_ACTIVE_KEY, "") or "")
        plan = _get_plan(context.scene, pid) if pid else None
        if plan:
            reconcile_plan(context, plan)
            _save_plan(context.scene, plan)
        return {"FINISHED"}


class DSG_PT_MCPRoadmap(Panel):
    """Single, stage-independent MCP entry point.

    MCP deliberately lives outside the clinical DICOM -> Alignment -> DSG panel
    tree.  It used to be a child of the DSG guide panel, which made it reappear
    under every guide sub-step and visually duplicated an accessory integration
    throughout the clinical workflow.  Keeping it in its own sidebar category
    provides exactly one UI location while preserving the bridge/roadmap backend.
    """
    bl_idname = "DSG_PT_MCPRoadmap"
    bl_label = "MCP · Roadmap clínico"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "DSG MCP"
    bl_order = 0
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, context):
        return getattr(context, "scene", None) is not None

    def draw(self, context):
        layout = self.layout
        props = context.scene.dsg_roadmap_props
        box = layout.box()
        row = box.row(align=True)
        running = _BRIDGE_SERVER is not None
        if running:
            row.label(text="Bridge local activo", icon_value=icon_manager.icon_id("status_ok"))
            row.operator("dsg.stop_mcp_bridge", text="Detener")
        else:
            row.label(text="Bridge MCP desactivado", icon_value=icon_manager.icon_id("status_empty"))
            row.operator("dsg.start_mcp_bridge", text="Activar")
        port_row = box.row()
        port_row.enabled = not running
        port_row.prop(props, "bridge_port")
        config = ui_style.tertiary_action(box, enabled=running) if hasattr(ui_style, "tertiary_action") else box.row()
        config.enabled = bool(running)
        config.operator("dsg.copy_mcp_bridge_config", text="Copiar conexión MCP", icon_value=icon_manager.icon_id("link"))
        box.label(text="Solo 127.0.0.1 · whitelist cerrada · exportación STL excluida", icon_value=icon_manager.icon_id("status_info"))

        # Local agent runtime (Mixar or another in-process client).  This is
        # intentionally read-only UI: capabilities are enforced by agent_facade.
        try:
            from . import agent_facade, agent_scene_graph
            agent_box = layout.box()
            summary = agent_scene_graph.get_scene_graph_summary(context.scene)
            history = agent_facade.get_operation_history(context.scene, 1)
            agent_box.label(text="Agent Runtime · DSG 9.1.7", icon_value=icon_manager.icon_id("status_ok"))
            agent_box.label(text=f"Scene Graph rev {summary.get('revision', 0)} · {summary.get('node_count', 0)} nodos")
            agent_box.label(text=f"Journal: {history.get('count', 0)} operaciones · confirmaciones clínicas excluidas")
        except Exception as exc:
            agent_box = layout.box()
            agent_box.label(text=f"Agent Runtime no disponible: {type(exc).__name__}", icon_value=icon_manager.icon_id("status_warning"))

        pid = str(context.scene.get(ROADMAP_ACTIVE_KEY, "") or props.active_plan_id or "")
        plan = _get_plan(context.scene, pid) if pid else None
        if not plan:
            layout.label(text="Sin roadmap activo", icon_value=icon_manager.icon_id("status_empty"))
            return
        # draw() is read-only: reconciliation happens via bridge calls or the
        # explicit Refresh operator, never by mutating Scene during UI drawing.
        target = plan.get("target") or {}
        summary = layout.box()
        summary.label(text=f"Plan {str(pid)[:8]} · FDI {target.get('fdi', '?')}", icon_value=icon_manager.icon_id("select_implant"))
        summary.label(text=f"Estado: {plan.get('status', 'pending')}")
        for step in plan.get("steps", []):
            status = str(step.get("status", "pending"))
            icon = {
                "done": "status_ok", "failed": "status_error", "blocked": "status_warning",
                "awaiting_review": "status_pending", "ready": "status_info", "running": "status_info",
            }.get(status, "status_empty")
            row = summary.row(align=True)
            row.label(text=str(step.get("title", step.get("id", "")))[:42], icon_value=icon_manager.icon_id(icon))
            who = str(step.get("confirmed_by", "") or "")
            if who:
                badge = {
                    "mcp_orchestrator": "MCP",
                    "clinician_ui": "UI",
                    "deterministic_operator": "DSG",
                }.get(who, "SYS")
                row.label(text=badge)
        ui_style.tertiary_action(summary).operator("dsg.refresh_roadmap_status", text="Actualizar estado")


CLASSES = (
    DSGRoadmapProperties,
    DSG_OT_SetAxisFromFDI,
    DSG_OT_StartMCPBridge,
    DSG_OT_StopMCPBridge,
    DSG_OT_CopyMCPBridgeConfig,
    DSG_OT_RefreshRoadmapStatus,
    DSG_PT_MCPRoadmap,
)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.dsg_roadmap_props = PointerProperty(type=DSGRoadmapProperties)


def unregister():
    try:
        stop_bridge(bpy.context if getattr(bpy.context, "scene", None) else None)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    if hasattr(bpy.types.Scene, "dsg_roadmap_props"):
        del bpy.types.Scene.dsg_roadmap_props
    for cls in reversed(CLASSES):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
