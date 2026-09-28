"""Traceability report written next to every exported guide STL.

Pure module (no ``bpy``). The report answers, for any printed guide: which
DSG build produced it, from which inputs, with which implant/sleeve plan, and
which quality checks it passed. Schema: ``dsg.guide_export_report.v1``.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .mesh_checks import CheckResult

SCHEMA = "dsg.guide_export_report.v1"
REPORT_SUFFIX = ".dsg-report.json"


def sha256_file(path: str | os.PathLike, chunk: int = 4 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def report_path_for(stl_path: str | os.PathLike) -> Path:
    p = Path(stl_path)
    return p.with_name(p.stem + REPORT_SUFFIX)


@dataclass
class ImplantRecord:
    name: str
    fdi: int | None = None
    diameter_mm: float | None = None
    length_mm: float | None = None
    platform_world_mm: list[float] | None = None
    axis_world: list[float] | None = None
    sleeve: dict = field(default_factory=dict)
    clearances: list[dict] = field(default_factory=list)


@dataclass
class ExportContext:
    """Everything the report needs, gathered by the Blender adapter."""

    dsg_version: str
    blender_version: str
    case_name: str = ""
    patient_folder: str = ""
    inputs: dict = field(default_factory=dict)          # role -> {"path":…, "sha256":…}
    plan_parameters: dict = field(default_factory=dict)  # sleeve/drill/offset settings
    implants: list[ImplantRecord] = field(default_factory=list)
    geometry: dict = field(default_factory=dict)          # triangles, volume, bbox…
    operator_options: dict = field(default_factory=dict)
    irrigation_network: list = field(default_factory=list)  # sequential-opening designs


def build_report(ctx: ExportContext, checks: Iterable[CheckResult], stl_path: str | os.PathLike,
                 *, stl_sha256: str | None = None, now: datetime | None = None) -> dict:
    checks = list(checks)
    statuses = [c.status for c in checks]
    overall = "FAIL" if "FAIL" in statuses else "WARN" if "WARN" in statuses else "PASS"
    return {
        "schema": SCHEMA,
        "created_utc": (now or datetime.now(timezone.utc)).isoformat(timespec="seconds"),
        "software": {"dsg_version": ctx.dsg_version, "blender_version": ctx.blender_version,
                     "python": platform.python_version(), "platform": platform.platform()},
        "case": {"name": ctx.case_name, "patient_folder": ctx.patient_folder},
        "output": {"stl_file": Path(stl_path).name, "stl_sha256": stl_sha256, "units": "mm"},
        "inputs": ctx.inputs,
        "plan_parameters": ctx.plan_parameters,
        "implants": [vars(i) for i in ctx.implants],
        "geometry": ctx.geometry,
        "irrigation_network": ctx.irrigation_network,
        "quality": {"overall": overall, "checks": [c.as_dict() for c in checks]},
        "operator_options": ctx.operator_options,
        "disclaimer": ("Planning aid. The clinician is responsible for reviewing the plan, "
                       "the printed guide fit and every safety margin before surgery."),
    }


def write_report(report: dict, stl_path: str | os.PathLike) -> Path:
    """Atomically write the JSON sidecar next to ``stl_path``."""
    target = report_path_for(stl_path)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    os.replace(tmp, target)
    return target
