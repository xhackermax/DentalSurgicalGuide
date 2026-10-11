"""Research-only group-aware topology pruning for surface-geodesic FEM.

Remove or keep *whole* geodesic paths, never their individual subsegments.
Each candidate is evaluated on a compacted FEM graph: deleting a route also
removes its now-orphaned free nodes, preventing artificial singular stiffness.
No Blender imports and no patient/guide geometry mutation.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import math

import numpy as np

from . import frame_fem_core as fem


@dataclass(frozen=True)
class GroupPruningResult:
    active_groups: tuple[str, ...]
    removed_groups: tuple[str, ...]
    material_volume_mm3: float
    compliance_Nmm: float
    balanced_objective: float
    max_utilization: float
    max_displacement_mm: float
    iterations: tuple[dict, ...]
    experimental: bool = True


class InvalidGeodesicGroups(ValueError):
    pass


def _compact(nodes, beams, loads, monitors, active_ids):
    selected = [beams[i] for i in active_ids if beams[i].active]
    used = set()
    for element in selected:
        used.update((element.i, element.j))
    for load in loads:
        for index, force in load.forces.items():
            if np.linalg.norm(force) > 1e-12:
                used.add(index)
        for index, moment in load.moments.items():
            if np.linalg.norm(moment) > 1e-12:
                used.add(index)
    used.update(monitors)
    # If a nonfixed loaded/monitored node becomes isolated, it must not be
    # omitted and silently treated as a zero-displacement/load condition.
    degree = {index: 0 for index in used}
    for element in selected:
        degree[element.i] = degree.get(element.i, 0) + 1
        degree[element.j] = degree.get(element.j, 0) + 1
    for index in used:
        if degree[index] == 0 and not np.all(nodes[index].fixed):
            raise fem.StructuralSolveError("DISCONNECTED_GEODESIC_FEM_LOAD_OR_MONITOR")
    order = sorted(used)
    remap = {i: new for new, i in enumerate(order)}
    new_nodes = [
        fem.Node(xyz=np.array(nodes[i].xyz, dtype=float),
                 fixed=np.array(nodes[i].fixed, dtype=bool),
                 role=str(nodes[i].role))
        for i in order
    ]
    new_elements = [replace(b, i=remap[b.i], j=remap[b.j])
                    for b in selected]
    new_loads = [
        fem.LoadCase(load.name,
            forces={remap[i]: value for i, value in load.forces.items() if i in remap},
            moments={remap[i]: value for i, value in load.moments.items() if i in remap},
        )
        for load in loads
    ]
    return new_nodes, new_elements, new_loads, [remap[i] for i in monitors]


def _evaluate(nodes, elements, loads, monitors, ids, config):
    subnodes, beams, subloads, submonitors = _compact(
        nodes, elements, loads, monitors, ids)
    result = fem.solve_load_cases(
        subnodes, beams, subloads, monitor_nodes=submonitors)
    max_stress = max((res["stress_ratio"] for beam, res in zip(beams, result.worst_results)
                      if not beam.virtual and res is not None), default=0.0)
    max_buckling = max((res["buckling_ratio"] for beam, res in zip(beams, result.worst_results)
                        if not beam.virtual and res is not None), default=0.0)
    displacement = float(result.max_monitor_displacement_mm)
    volume = sum(
        beam.area * float(row["length_mm"])
        for beam, row in zip(beams, result.worst_results)
        if row is not None and beam.render and not beam.virtual
    )
    compliance = 0.0
    for load, u in zip(subloads, result.displacements):
        for i, force in load.forces.items():
            compliance += float(force @ u[6 * i: 6 * i + 3])
        for i, moment in load.moments.items():
            compliance += float(moment @ u[6 * i + 3: 6 * i + 6])
    compliance /= max(1, len(subloads))
    tol = config.numerical_tol
    hard_safe = (
        max_stress <= 1 + tol and max_buckling <= 1 + tol
        and displacement <= config.displacement_limit_mm + tol
    )
    recommended = (
        max_stress <= config.design_utilization_target + tol
        and max_buckling <= config.design_utilization_target + tol
        and displacement <= config.displacement_design_target_mm + tol
    )
    return {
        "volume": float(volume),
        "compliance": float(compliance),
        "max_utilization": float(max(max_stress, max_buckling)),
        "displacement": displacement,
        "hard_safe": bool(hard_safe),
        "recommended": bool(recommended),
    }


def prune_geodesic_groups(nodes, elements, load_cases, monitor_nodes,
                          groups: dict[str, list[int] | tuple[int, ...]],
                          *, config: fem.OptimizationConfig,
                          stiffness_weight: float = 0.5,
                          max_groups: int = 24,
                          min_remaining_groups: int = 1) -> GroupPruningResult:
    """Greedily minimize balanced volume + compliance, subject to hard limits.

    Nominal circular-beam FEM only. This is NOT validated post-Boolean FEM,
    nor does it prove contact/retention or structural reliability in vivo.
    Results describe candidate path groups, not irreversible scene changes.
    """
    if not groups or len(groups) > max_groups:
        raise InvalidGeodesicGroups("invalid candidate-group count")
    if not (math.isfinite(stiffness_weight) and 0 <= stiffness_weight <= 1):
        raise ValueError("stiffness_weight must be in [0,1]")
    if not (1 <= min_remaining_groups <= len(groups)):
        raise ValueError("invalid remaining-group minimum")
    names = sorted(groups)
    seen = set()
    for name in names:
        indices = list(groups[name])
        if not name or not indices:
            raise InvalidGeodesicGroups("empty geodesic group")
        if any(not isinstance(i, int) or i < 0 or i >= len(elements) for i in indices):
            raise InvalidGeodesicGroups("invalid beam index")
        if set(indices) & seen or len(set(indices)) != len(indices):
            raise InvalidGeodesicGroups("beam segment assigned to multiple groups")
        for index in indices:
            if elements[index].virtual or not elements[index].render or not elements[index].active:
                raise InvalidGeodesicGroups("geodesic group must contain active visible beams")
        seen.update(indices)
    fixed_ids = {i for i, b in enumerate(elements) if i not in seen and b.active}
    if any(b.active and b.render and not b.virtual and i not in seen for i,b in enumerate(elements)):
        raise InvalidGeodesicGroups("unclassified renderable FEM beam")
    loads = [load_cases] if isinstance(load_cases, fem.LoadCase) else list(load_cases)
    if not loads:
        raise InvalidGeodesicGroups("missing load cases")
    monitor_nodes = tuple(int(i) for i in monitor_nodes)

    def evaluate(active):
        ids = sorted(fixed_ids | {
            i for name in active for i in groups[name]
        })
        return _evaluate(nodes, elements, loads, monitor_nodes, ids, config)

    baseline = evaluate(names)
    if not baseline["hard_safe"]:
        raise InvalidGeodesicGroups("BASELINE_FEM_UNSAFE: refuse to prune")
    v0 = max(baseline["volume"], 1e-12)
    c0 = max(baseline["compliance"], 1e-12)
    def objective(metrics):
        return ((1.0 - stiffness_weight) * metrics["volume"] / v0
                + stiffness_weight * metrics["compliance"] / c0)
    active = list(names)
    history = []
    current = baseline
    while len(active) > min_remaining_groups:
        best = None
        for name in active:
            remaining = [n for n in active if n != name]
            try:
                trial = evaluate(remaining)
            except (fem.StructuralSolveError, ValueError, np.linalg.LinAlgError):
                continue
            if not trial["hard_safe"] or not trial["recommended"]:
                continue
            score = objective(trial)
            if score >= objective(current) - 1e-9:
                continue
            if best is None or (score, name) < (best[0], best[1]):
                best = (score, name, trial)
        if best is None:
            break
        score, name, metrics = best
        active.remove(name)
        history.append({
            "removed_group": name,
            "material_volume_mm3": metrics["volume"],
            "compliance_Nmm": metrics["compliance"],
            "balanced_objective": score,
        })
        current = metrics
    return GroupPruningResult(
        active_groups=tuple(active),
        removed_groups=tuple(n for n in names if n not in active),
        material_volume_mm3=current["volume"],
        compliance_Nmm=current["compliance"],
        balanced_objective=objective(current),
        max_utilization=current["max_utilization"],
        max_displacement_mm=current["displacement"],
        iterations=tuple(history),
    )
