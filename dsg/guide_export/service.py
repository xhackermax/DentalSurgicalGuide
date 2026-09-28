"""Export quality-gate orchestration used by ``DSG_OT_ExportGuideSTL``.

The service depends on *abstractions*: a geometry source (``ArraysFn``), a
ray-caster factory and a clearance function. Blender implementations are
injected by default from ``blender_adapter``; tests inject pure ones.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from typing import Callable, Iterable

import numpy as np

from . import mesh_checks
from .mesh_checks import CheckResult
from .policy import ExportPolicy

LOG = logging.getLogger("dsg.guide_export")

ArraysFn = Callable[[object], tuple[np.ndarray, np.ndarray]]
CasterFactory = Callable[[np.ndarray, np.ndarray], mesh_checks.RayCaster]
ClearanceFn = Callable[[object, object], tuple[float | None, bool, str]]


@dataclass(frozen=True)
class ExportOptions:
    """User decisions taken in the export dialog."""

    allow_non_manifold: bool = False
    confirm_island_removal: bool = False
    check_wall_thickness: bool = True
    write_report: bool = True


@dataclass
class GateResult:
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def blocking(self) -> list[CheckResult]:
        return [c for c in self.checks if c.blocking]

    @property
    def warnings(self) -> list[CheckResult]:
        return [c for c in self.checks if c.status in ("WARN", "FAIL") and not c.blocking]

    def extend(self, more: Iterable[CheckResult]) -> None:
        self.checks.extend(more)


def _default_arrays(obj):
    from .blender_adapter import mesh_arrays
    return mesh_arrays(obj)


def _default_caster(vertices, triangles):
    from .blender_adapter import BVHRayCaster
    return BVHRayCaster(vertices, triangles)


def _default_clearance(a, b):
    from .blender_adapter import object_clearance_mm
    return object_clearance_mm(a, b)


class ExportGate:
    """Runs the checks in the order the operator needs them."""

    def __init__(self, policy: ExportPolicy, options: ExportOptions, *,
                 arrays: ArraysFn = _default_arrays,
                 caster_factory: CasterFactory = _default_caster,
                 clearance: ClearanceFn = _default_clearance):
        self.policy = policy
        self.options = options
        self._arrays = arrays
        self._caster_factory = caster_factory
        self._clearance = clearance

    # Step 1 – before the existing island cleanup mutates the working copy.
    def check_islands(self, obj) -> CheckResult:
        v, t = self._arrays(obj)
        result = mesh_checks.island_removal_decision(mesh_checks.islands(v, t), self.policy)
        if result.blocking and self.options.confirm_island_removal:
            return replace(result, status="WARN", blocking=False,
                           message=result.message.split(";")[0] + " — removed after explicit user confirmation")
        return result

    # Step 2 – on the final export object (after seals are fused).
    def check_solid(self, obj) -> list[CheckResult]:
        v, t = self._arrays(obj)
        results = []
        solid = mesh_checks.manifold_report(v, t, self.policy)
        if solid.blocking and self.options.allow_non_manifold:
            solid = replace(solid, blocking=False, message=solid.message + " — exported by explicit user override")
        results.append(solid)
        if self.options.check_wall_thickness:
            try:
                results.append(mesh_checks.wall_thickness_report(v, t, self._caster_factory(v, t), self.policy))
            except Exception as exc:  # noqa: BLE001 - measurement failure must be visible, not fatal
                LOG.exception("wall thickness check failed")
                results.append(CheckResult("wall_thickness", "SKIPPED", f"Measurement failed: {exc}"))
        results.append(CheckResult("geometry", "PASS", "Summary",
                                   metrics={"triangles": int(len(t)),
                                            "volume_mm3": mesh_checks.signed_volume_mm3(v, t),
                                            "bbox_min_mm": v.min(axis=0).tolist() if len(v) else None,
                                            "bbox_max_mm": v.max(axis=0).tolist() if len(v) else None}))
        return results

    # Step 3 – anatomical clearance (informative; never blocks).
    def check_anatomy(self, implants: Iterable[object], canal) -> list[CheckResult]:
        out = []
        for implant in implants:
            name = f"canal_clearance:{getattr(implant, 'name', '?')}"
            if canal is None:
                out.append(CheckResult(name, "SKIPPED", "No mandibular canal segmented in this case"))
                continue
            try:
                dist, hits, method = self._clearance(implant, canal)
            except Exception as exc:  # noqa: BLE001
                LOG.exception("canal clearance failed for %s", getattr(implant, "name", "?"))
                out.append(CheckResult(name, "SKIPPED", f"Measurement failed: {exc}"))
                continue
            out.append(mesh_checks.clearance_status(name, dist, self.policy.min_canal_distance_mm,
                                                    intersects=hits, method=method))
        return out


def summarize(checks: Iterable[CheckResult], limit: int = 3) -> str:
    """One-line human summary for ``Operator.report``."""
    bad = [c for c in checks if c.status in ("WARN", "FAIL")]
    if not bad:
        return "quality gate PASS"
    head = "; ".join(f"{c.name}: {c.message}" for c in bad[:limit])
    more = f" (+{len(bad) - limit} more)" if len(bad) > limit else ""
    return f"{len(bad)} warning(s): {head}{more}"
