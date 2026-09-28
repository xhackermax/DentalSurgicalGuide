"""Pure policy primitives for the DSG agent runtime.

This module deliberately contains no bpy imports so tool policy, request hashes
and journal state transitions can be tested outside Blender.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
import hashlib
import json
from typing import Any

AGENT_SCHEMA = "dsg.agent_runtime.v1"


@dataclass(frozen=True)
class AgentToolSpec:
    name: str
    bridge_op: str
    kind: str = "QUERY"  # QUERY | ACTION
    risk: str = "READ_ONLY"  # READ_ONLY | VISUALIZATION | PREVIEW_MUTATION | CLINICAL_DATA
    mutates_scene: bool = False
    requires_operation_id: bool = False
    description: str = ""

    @property
    def agent_callable(self) -> bool:
        return self.risk not in {"CLINICAL_CONFIRMATION", "DESTRUCTIVE", "EXPORT"}


# Closed capability set.  Clinical confirmation, final booleans, export and the
# generic roadmap execute_step are intentionally absent.
_TOOL_SPECS = (
    AgentToolSpec("get_case_state", "get_case_state", description="Structured DSG case state."),
    AgentToolSpec("get_patient_clinical_context", "get_patient_clinical_context", description="Read de-identified structured patient context."),
    AgentToolSpec("get_clinical_source_registry", "get_clinical_source_registry"),
    AgentToolSpec("build_medication_lookup_request", "build_medication_lookup_request"),
    AgentToolSpec("build_clinical_guidance_request", "build_clinical_guidance_request", kind="ACTION", risk="CLINICAL_DATA", mutates_scene=True, requires_operation_id=True),
    AgentToolSpec("get_clinical_guidance_request", "get_clinical_guidance_request"),
    AgentToolSpec("get_clinical_guidance_result", "get_clinical_guidance_result"),
    AgentToolSpec("get_evidence_repository_summary", "get_evidence_repository_summary"),
    AgentToolSpec("get_evidence_rule", "get_evidence_rule"),
    AgentToolSpec("get_evidence_topic", "get_evidence_topic"),
    AgentToolSpec("search_offline_evidence", "search_offline_evidence"),
    AgentToolSpec("build_evidence_update_request", "build_evidence_update_request"),
    AgentToolSpec("get_dental_asset_contract", "get_dental_asset_contract"),
    AgentToolSpec("get_dental_family", "get_dental_family"),
    AgentToolSpec("get_required_landmarks", "get_required_landmarks"),
    AgentToolSpec("get_dental_landmarks", "get_dental_landmarks"),
    AgentToolSpec("get_dental_mapping_quality", "get_dental_mapping_quality"),
    AgentToolSpec("get_gold_standard", "get_gold_standard"),
    AgentToolSpec("build_implant_planning_context", "build_implant_planning_context"),
    AgentToolSpec("build_full_implant_context", "build_full_implant_context"),
    AgentToolSpec("build_preoperative_context", "build_preoperative_context"),
    AgentToolSpec("analyze_implant_bone_support", "analyze_implant_bone_support"),
    AgentToolSpec("analyze_implant_neighbor_clearance", "analyze_implant_neighbor_clearance"),
    AgentToolSpec("analyze_interdental_space", "analyze_interdental_space"),
    AgentToolSpec("analyze_implant_diameter_options", "analyze_implant_diameter_options"),
    AgentToolSpec("evaluate_implant_candidate", "evaluate_implant_candidate"),
    AgentToolSpec("get_frame_structural_contract", "get_frame_structural_contract"),
    AgentToolSpec("get_frame_context", "get_frame_context"),
    AgentToolSpec("analyze_frame_structure", "analyze_frame_structure"),
    AgentToolSpec("propose_frame_reinforcements", "propose_frame_reinforcements"),
    AgentToolSpec("analyze_frame_fem", "analyze_frame_fem"),
    AgentToolSpec("optimize_frame_fem", "optimize_frame_fem", kind="ACTION", risk="PREVIEW_MUTATION", mutates_scene=True, requires_operation_id=True),
    AgentToolSpec("map_patient_tooth", "map_patient_tooth", kind="ACTION", risk="PREVIEW_MUTATION", mutates_scene=True, requires_operation_id=True),
    AgentToolSpec("fit_crown_to_neighbors", "fit_crown_to_neighbors", kind="ACTION", risk="PREVIEW_MUTATION", mutates_scene=True, requires_operation_id=True),
    AgentToolSpec("fit_occlusion", "fit_occlusion", kind="ACTION", risk="PREVIEW_MUTATION", mutates_scene=True, requires_operation_id=True),
    AgentToolSpec("prepare_implant_axis_from_prosthetic_context", "prepare_implant_axis_from_prosthetic_context", kind="ACTION", risk="PREVIEW_MUTATION", mutates_scene=True, requires_operation_id=True),
    AgentToolSpec("apply_implant_bone_support_heatmap", "apply_implant_bone_support_heatmap", kind="ACTION", risk="VISUALIZATION", mutates_scene=True, requires_operation_id=True),
    AgentToolSpec("clear_implant_bone_support_heatmap", "clear_implant_bone_support_heatmap", kind="ACTION", risk="VISUALIZATION", mutates_scene=True, requires_operation_id=True),
    AgentToolSpec("set_frame_support_nodes", "set_frame_support_nodes", kind="ACTION", risk="PREVIEW_MUTATION", mutates_scene=True, requires_operation_id=True),
    AgentToolSpec("submit_plan", "submit_plan", kind="ACTION", risk="PREVIEW_MUTATION", mutates_scene=True, requires_operation_id=True),
)

TOOLS = {spec.name: spec for spec in _TOOL_SPECS}

FORBIDDEN_CAPABILITIES = {
    "clinical_confirmation": [
        "dsg.clinical_confirm_review",
        "dsg.confirm_model", "dsg.confirm_axis", "dsg.confirm_blockout",
        "dsg.confirm_contour", "dsg.confirm_implant",
        "dsg.confirm_microscrew_preview", "dsg.confirm_tube_frame",
        "dsg.confirm_sleeve", "dsg.confirm_drill",
        "dsg.confirm_irrigation_preview", "dsg.update_confirm_irrigation",
        "dsg.confirm_irrigation", "dsg.confirm_reinforcement_preview",
    ],
    "destructive_or_final": [
        "dsg.apply_reinforcements", "dsg.apply_patient_engrave",
        "dct.apply_cut", "dsg.export_guide_stl", "execute_step",
    ],
    "arbitrary_python": [
        "bpy.ops.dsg.*", "bpy.ops.dct.apply_cut",
        "direct import dsg from Mixar generated scripts",
    ],
}



def canonical_hash(tool_name: str, params: dict[str, Any]) -> str:
    payload = {"tool": str(tool_name), "params": params or {}}
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def capability_manifest() -> dict[str, Any]:
    return {
        "schema": AGENT_SCHEMA,
        "tools": [asdict(spec) | {"agent_callable": spec.agent_callable} for spec in _TOOL_SPECS],
        "forbidden": FORBIDDEN_CAPABILITIES,
        "policy": {
            "unknown_tool": "DENY",
            "clinical_confirmations": "USER_UI_ONLY_NOT_AGENT_FACADE",
            "mutation_idempotency": "OPERATION_ID_PLUS_CANONICAL_INPUT_HASH",
            "geometry_confirmation": "EXACT_VERIFIER_WHERE_AVAILABLE",
        },
    }


def find_journal_entry(entries: list[dict[str, Any]], operation_id: str):
    for row in reversed(entries):
        if str(row.get("operation_id", "")) == str(operation_id):
            return row
    return None


def begin_journal(entries: list[dict[str, Any]], *, operation_id: str, tool_name: str,
                  input_hash: str, started_at: str, scene_revision: int) -> tuple[str, dict[str, Any]]:
    existing = find_journal_entry(entries, operation_id)
    if existing is not None:
        if existing.get("tool") != tool_name or existing.get("input_hash") != input_hash:
            return "CONFLICT", existing
        status = str(existing.get("status", ""))
        if status == "COMMITTED": return "REPLAY", existing
        if status == "RUNNING": return "IN_PROGRESS", existing
        # FAILED may be deliberately retried with same logical operation id only
        # after caller chooses a new id; that keeps audit semantics unambiguous.
        return "FAILED_PREVIOUSLY", existing
    row = {
        "operation_id": str(operation_id), "tool": str(tool_name),
        "input_hash": str(input_hash), "status": "RUNNING",
        "started_at": started_at, "scene_revision_before": int(scene_revision),
    }
    entries.append(row)
    return "STARTED", row
