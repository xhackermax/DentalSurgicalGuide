"""Blender-facing UI and MCP persistence for the DSG offline Evidence Engine."""
from __future__ import annotations

import logging as _dsg_logging
_DSG_LOG = _dsg_logging.getLogger(__name__)

import json
from typing import Any

import bpy
from bpy.props import PointerProperty, StringProperty
from bpy.types import Operator, Panel, PropertyGroup

from . import evidence_core

UPDATE_REQUEST_KEY = "DSG_evidence_update_request_json"
UPDATE_PROPOSAL_KEY = "DSG_evidence_update_proposal_json"

_REPO = None


def repository() -> dict[str, Any]:
    global _REPO
    if _REPO is None:
        _REPO = evidence_core.load_repository()
    return _REPO


def repository_summary() -> dict[str, Any]:
    return evidence_core.repository_summary(repository())


def get_evidence_rule(rule_id: str) -> dict[str, Any]:
    return evidence_core.get_rule(rule_id, repo=repository())


def get_evidence_topic(topic: str) -> dict[str, Any]:
    return evidence_core.get_topic_context(topic, repo=repository())


def search_offline_evidence(query: str, limit: int = 30) -> dict[str, Any]:
    return evidence_core.search_offline_evidence(query, limit=limit, repo=repository())


def _store(scene, key: str, payload: dict[str, Any]):
    scene[key] = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _load(scene, key: str) -> dict[str, Any] | None:
    raw = str(scene.get(key, "") or "")
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def build_evidence_update_request(topics=None, *, country_code="INT", scene=None) -> dict[str, Any]:
    scene = scene or bpy.context.scene
    request = evidence_core.build_update_request(topics, country_code=country_code, repo=repository())
    _store(scene, UPDATE_REQUEST_KEY, request)
    return request


def get_evidence_update_request(*, scene=None):
    return _load(scene or bpy.context.scene, UPDATE_REQUEST_KEY)


def store_evidence_update_proposal(payload: dict[str, Any], *, scene=None) -> dict[str, Any]:
    scene = scene or bpy.context.scene
    request = get_evidence_update_request(scene=scene)
    if not request:
        raise RuntimeError("Build an evidence update request before storing a proposal")
    validated = evidence_core.validate_update_proposal(
        payload, expected_request_sha256=str(request.get("request_sha256", "") or ""))
    _store(scene, UPDATE_PROPOSAL_KEY, validated)
    return validated


def get_evidence_update_proposal(*, scene=None):
    return _load(scene or bpy.context.scene, UPDATE_PROPOSAL_KEY)


def evidence_status(*, scene=None) -> dict[str, Any]:
    scene = scene or bpy.context.scene
    summary = repository_summary()
    req = get_evidence_update_request(scene=scene)
    proposal = get_evidence_update_proposal(scene=scene)
    return {
        "schema": "dsg.evidence_status.v1",
        **summary,
        "review_due_rule_ids": [x.get("id") for x in evidence_core.due_for_review(repo=repository())],
        "update_request_ready": bool(req),
        "update_proposal_ready": bool(proposal),
        "update_proposal_activation_status": str((proposal or {}).get("activation_status", "NONE")),
        "active_rules_runtime_mutable": False,
    }


class DSGEvidenceProperties(PropertyGroup):
    query: StringProperty(name="Buscar", default="")
    rule_id: StringProperty(name="Rule ID", default="IMPLANT_TOOTH_CLEARANCE")
    update_topics: StringProperty(name="Temas", default="", description="IDs de tema separados por comas; vacío = todos")


class DSG_OT_EvidenceCopySummary(Operator):
    bl_idname = "dsg.evidence_copy_summary"
    bl_label = "Copiar resumen científico"
    def execute(self, context):
        context.window_manager.clipboard = json.dumps(evidence_status(scene=context.scene), ensure_ascii=False, indent=2)
        self.report({"INFO"}, "Resumen de evidencia copiado")
        return {"FINISHED"}


class DSG_OT_EvidenceCopyRule(Operator):
    bl_idname = "dsg.evidence_copy_rule"
    bl_label = "Copiar regla + bibliografía"
    def execute(self, context):
        try:
            data = get_evidence_rule(context.scene.dsg_evidence_props.rule_id)
        except Exception as exc:
            self.report({"ERROR"}, str(exc)); return {"CANCELLED"}
        context.window_manager.clipboard = json.dumps(data, ensure_ascii=False, indent=2)
        self.report({"INFO"}, "Regla y bibliografía copiadas")
        return {"FINISHED"}


class DSG_OT_EvidenceCopySearch(Operator):
    bl_idname = "dsg.evidence_copy_search"
    bl_label = "Buscar offline y copiar"
    def execute(self, context):
        try:
            data = search_offline_evidence(context.scene.dsg_evidence_props.query)
        except Exception as exc:
            self.report({"ERROR"}, str(exc)); return {"CANCELLED"}
        context.window_manager.clipboard = json.dumps(data, ensure_ascii=False, indent=2)
        self.report({"INFO"}, "Resultados offline copiados")
        return {"FINISHED"}


class DSG_OT_EvidenceCopyUpdateRequest(Operator):
    bl_idname = "dsg.evidence_copy_update_request"
    bl_label = "Preparar actualización MCP"
    def execute(self, context):
        props = context.scene.dsg_evidence_props
        topics = [x.strip() for x in props.update_topics.split(",") if x.strip()] or None
        country = "INT"
        try:
            from . import clinical_context
            country = clinical_context.get_patient_clinical_context(context.scene).get("country_code", "INT")
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        data = build_evidence_update_request(topics, country_code=country, scene=context.scene)
        context.window_manager.clipboard = json.dumps(data, ensure_ascii=False, indent=2)
        self.report({"INFO"}, "Petición de actualización científica copiada")
        return {"FINISHED"}


class DSG_PT_EvidenceRepository(Panel):
    bl_idname = "DSG_PT_evidence_repository"
    bl_label = "Evidencia científica · Offline"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "DSG MCP"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        props = context.scene.dsg_evidence_props
        status = evidence_status(scene=context.scene)
        box = layout.box()
        box.label(text=f"Base {status['repository_version']}")
        box.label(text=f"{status['reference_count']} refs · {status['rule_count']} reglas · {status['journal_count']} revistas")
        box.label(text=f"Última búsqueda: {status['last_literature_search']}")
        box.label(text="Funciona sin Internet · sin artículos completos")
        box.operator("dsg.evidence_copy_summary", icon="COPYDOWN")

        rule = layout.box()
        rule.label(text="Regla clínica trazable")
        rule.prop(props, "rule_id")
        rule.operator("dsg.evidence_copy_rule", icon="COPYDOWN")

        search = layout.box()
        search.label(text="Buscar en repositorio local")
        search.prop(props, "query")
        search.operator("dsg.evidence_copy_search", icon="VIEWZOOM")

        update = layout.box()
        update.label(text="Radar científico MCP")
        update.prop(props, "update_topics")
        update.operator("dsg.evidence_copy_update_request", icon="FILE_REFRESH")
        update.label(text="Las novedades NO cambian reglas automáticamente")


_CLASSES = (
    DSGEvidenceProperties,
    DSG_OT_EvidenceCopySummary,
    DSG_OT_EvidenceCopyRule,
    DSG_OT_EvidenceCopySearch,
    DSG_OT_EvidenceCopyUpdateRequest,
    DSG_PT_EvidenceRepository,
)


def register():
    # Fail fast here rather than discovering a corrupted repository during surgery.
    repository()
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.dsg_evidence_props = PointerProperty(type=DSGEvidenceProperties)


def unregister():
    if hasattr(bpy.types.Scene, "dsg_evidence_props"):
        del bpy.types.Scene.dsg_evidence_props
    for cls in reversed(_CLASSES):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
