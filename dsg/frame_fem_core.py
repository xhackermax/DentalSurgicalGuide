"""
DSG · GenerativeFrame FEM Core v2.1
============================

Motor estructural puro NumPy/SciPy para optimización de refuerzos de guía.

Principios:
- Sin bpy: se puede testear fuera de Blender y ejecutar en un worker.
- Viga 3D Euler-Bernoulli, 12 GDL por elemento.
- Multi-load-case.
- Restricción de tensión, torsión, pandeo y desplazamiento del sleeve.
- Redimensionado por mecanismo dominante:
    axial       -> r ~ U^(1/2)
    flexión     -> r ~ U^(1/3)
    torsión     -> r ~ U^(1/3)
    pandeo      -> r ~ U^(1/4)
- Margen de diseño separado de los límites físicos.
- Poda con removal test: una barra azul no se elimina si sostiene la rigidez global.
- Refuerzo topológico local: añade triángulos locales, NO reconecta todo-contra-todo.
- Historial rico para UI/gráficas.
- Unidades: mm, N, MPa (= N/mm²).

Los valores de material/carga del demo son ilustrativos y deben validarse antes
 de cualquier uso clínico.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from typing import Callable, Sequence

import numpy as np

try:
    from scipy.sparse import lil_matrix
    from scipy.sparse.linalg import splu
    _HAVE_SCIPY = True
except Exception:  # pragma: no cover
    _HAVE_SCIPY = False


class StructuralSolveError(RuntimeError):
    pass


@dataclass
class Node:
    xyz: np.ndarray
    fixed: np.ndarray
    role: str = "FREE"  # KEEP_IN_SUPPORT | LOAD | FREE

    def __post_init__(self):
        self.xyz = np.asarray(self.xyz, dtype=float).reshape(3)
        self.fixed = np.asarray(self.fixed, dtype=bool).reshape(6)


@dataclass
class BeamElement:
    i: int
    j: int
    radius_mm: float
    E: float = 2500.0
    G: float = 900.0
    allow_stress_mpa: float | None = None
    material_strength_mpa: float = 80.0
    material_safety_factor: float = 1.25
    process_safety_factor: float = 1.15
    buckling_safety: float = 2.0
    effective_length_factor: float = 1.0
    up_hint: np.ndarray | None = None
    active: bool = True
    tag: str = ""
    render: bool = True
    locked_radius: bool = False
    prunable: bool = True
    virtual: bool = False

    @property
    def area(self) -> float:
        return math.pi * self.radius_mm**2

    @property
    def I(self) -> float:
        return math.pi * self.radius_mm**4 / 4.0

    @property
    def J(self) -> float:
        return math.pi * self.radius_mm**4 / 2.0

    @property
    def working_stress_mpa(self) -> float:
        if self.allow_stress_mpa is not None:
            return float(self.allow_stress_mpa)
        den = max(self.material_safety_factor * self.process_safety_factor, 1e-12)
        return float(self.material_strength_mpa / den)


@dataclass
class LoadCase:
    name: str = "LC"
    forces: dict[int, np.ndarray] = field(default_factory=dict)
    moments: dict[int, np.ndarray] = field(default_factory=dict)

    def __post_init__(self):
        self.forces = {int(k): np.asarray(v, dtype=float).reshape(3) for k, v in self.forces.items()}
        self.moments = {int(k): np.asarray(v, dtype=float).reshape(3) for k, v in self.moments.items()}


@dataclass
class OptimizationConfig:
    iterations: int = 18
    radius_min_mm: float = 0.55
    radius_max_mm: float = 2.20
    prune_below_mm: float = 0.65
    relaxation: float = 0.60

    design_utilization_target: float = 0.75
    displacement_limit_mm: float = 0.20
    displacement_design_target_mm: float = 0.15

    prune_utilization_threshold: float = 0.15
    max_prune_tests_per_iteration: int = 8
    prune_requires_recommended: bool = True

    enable_topology_growth: bool = True
    growth_trigger_utilization: float = 0.95
    growth_trigger_displacement_ratio: float = 1.05
    growth_every_n_iterations: int = 2
    max_growth_elements_per_round: int = 3
    max_growth_rounds: int = 4
    triangle_height_factor: float = 0.22
    triangle_height_min_mm: float = 1.5
    triangle_height_max_mm: float = 5.0
    growth_radius_mm: float = 0.75
    node_merge_distance_mm: float = 0.50

    volume_rel_tol: float = 0.01
    min_iterations_before_convergence: int = 4
    numerical_tol: float = 5e-4


@dataclass
class SolveBundle:
    displacements: list[np.ndarray]
    per_case_results: list[list[dict | None]]
    worst_results: list[dict | None]
    max_monitor_displacement_mm: float
    max_monitor_node: int | None
    max_monitor_case: int | None


@dataclass
class OptimizationResult:
    history: list[dict]
    final_bundle: SolveBundle
    hard_safe: bool
    recommended: bool
    active_elements: list[int]
    total_volume_mm3: float


def _local_stiffness(L: float, E: float, G: float, A: float, Iy: float, Iz: float, J: float) -> np.ndarray:
    if L <= 0:
        raise ValueError("Longitud de elemento inválida")
    k = np.zeros((12, 12), dtype=float)
    EA_L = E * A / L
    GJ_L = G * J / L

    k[0, 0] = k[6, 6] = EA_L
    k[0, 6] = k[6, 0] = -EA_L

    k[3, 3] = k[9, 9] = GJ_L
    k[3, 9] = k[9, 3] = -GJ_L

    c = E * Iz / L**3
    k[1, 1] = k[7, 7] = 12 * c
    k[1, 7] = k[7, 1] = -12 * c
    k[1, 5] = k[5, 1] = 6 * c * L
    k[1, 11] = k[11, 1] = 6 * c * L
    k[7, 5] = k[5, 7] = -6 * c * L
    k[7, 11] = k[11, 7] = -6 * c * L
    k[5, 5] = k[11, 11] = 4 * c * L**2
    k[5, 11] = k[11, 5] = 2 * c * L**2

    c = E * Iy / L**3
    k[2, 2] = k[8, 8] = 12 * c
    k[2, 8] = k[8, 2] = -12 * c
    k[2, 4] = k[4, 2] = -6 * c * L
    k[2, 10] = k[10, 2] = -6 * c * L
    k[8, 4] = k[4, 8] = 6 * c * L
    k[8, 10] = k[10, 8] = 6 * c * L
    k[4, 4] = k[10, 10] = 4 * c * L**2
    k[4, 10] = k[10, 4] = 2 * c * L**2
    return k


def _transformation(node_i: np.ndarray, node_j: np.ndarray, up_hint: np.ndarray | None) -> tuple[np.ndarray, float]:
    d = np.asarray(node_j, dtype=float) - np.asarray(node_i, dtype=float)
    L = float(np.linalg.norm(d))
    if L < 1e-9:
        raise ValueError("Elemento de longitud ~0")

    ex = d / L
    ref = np.array([0.0, 0.0, 1.0]) if up_hint is None else np.asarray(up_hint, dtype=float)
    if np.linalg.norm(ref) < 1e-12:
        ref = np.array([0.0, 0.0, 1.0])
    ref = ref / np.linalg.norm(ref)

    if abs(float(np.dot(ref, ex))) > 0.98:
        candidates = (
            np.array([1.0, 0.0, 0.0]),
            np.array([0.0, 1.0, 0.0]),
            np.array([0.0, 0.0, 1.0]),
        )
        ref = min(candidates, key=lambda a: abs(float(np.dot(a, ex))))

    ey = ref - np.dot(ref, ex) * ex
    n = np.linalg.norm(ey)
    if n < 1e-12:
        raise ValueError("No se pudo construir base local de la viga")
    ey /= n
    ez = np.cross(ex, ey)
    ez /= max(np.linalg.norm(ez), 1e-12)

    R = np.vstack([ex, ey, ez])
    T = np.zeros((12, 12), dtype=float)
    for block in range(4):
        T[block*3:block*3+3, block*3:block*3+3] = R
    return T, L


def _dof(node_idx: int, local: int) -> int:
    return node_idx * 6 + local


def _active_element_indices(elements: list[BeamElement]) -> list[int]:
    return [i for i, e in enumerate(elements) if e.active]


def assemble_stiffness(nodes: list[Node], elements: list[BeamElement]):
    """Assemble K; SciPy sparse when available, NumPy dense otherwise."""
    n_dof = len(nodes) * 6
    K = lil_matrix((n_dof, n_dof), dtype=float) if _HAVE_SCIPY else np.zeros((n_dof, n_dof), dtype=float)

    for e in elements:
        if not e.active:
            continue
        ni, nj = nodes[e.i], nodes[e.j]
        T, L = _transformation(ni.xyz, nj.xyz, e.up_hint)
        kl = _local_stiffness(L, e.E, e.G, e.area, e.I, e.I, e.J)
        kg = T.T @ kl @ T
        dofs = [_dof(e.i, a) for a in range(6)] + [_dof(e.j, a) for a in range(6)]
        for a in range(12):
            da = dofs[a]
            for b in range(12):
                val = kg[a, b]
                if val:
                    K[da, dofs[b]] += val

    fixed_mask = np.zeros(n_dof, dtype=bool)
    for idx, node in enumerate(nodes):
        fixed_mask[idx*6:idx*6+6] = node.fixed
    free = np.where(~fixed_mask)[0]
    return (K.tocsr(), free, True) if _HAVE_SCIPY else (K, free, False)

def _build_load_vector(nodes: list[Node], load: LoadCase) -> np.ndarray:
    F = np.zeros(len(nodes) * 6, dtype=float)
    for node_idx, f in load.forces.items():
        if node_idx < 0 or node_idx >= len(nodes):
            raise IndexError(f"LoadCase {load.name}: nodo de fuerza fuera de rango: {node_idx}")
        F[_dof(node_idx, 0):_dof(node_idx, 0)+3] += f
    for node_idx, m in load.moments.items():
        if node_idx < 0 or node_idx >= len(nodes):
            raise IndexError(f"LoadCase {load.name}: nodo de momento fuera de rango: {node_idx}")
        F[_dof(node_idx, 3):_dof(node_idx, 3)+3] += m
    return F


def _element_result(nodes: list[Node], e: BeamElement, u: np.ndarray) -> dict:
    ni, nj = nodes[e.i], nodes[e.j]
    T, L = _transformation(ni.xyz, nj.xyz, e.up_hint)
    dofs = [_dof(e.i, a) for a in range(6)] + [_dof(e.j, a) for a in range(6)]
    u_local = T @ u[dofs]
    kl = _local_stiffness(L, e.E, e.G, e.area, e.I, e.I, e.J)
    f_local = kl @ u_local

    N = float(f_local[6])
    My1, Mz1 = float(f_local[4]), float(f_local[5])
    My2, Mz2 = float(f_local[10]), float(f_local[11])
    M_bend_max = max(math.hypot(My1, Mz1), math.hypot(My2, Mz2))
    Tq = max(abs(float(f_local[3])), abs(float(f_local[9])))

    c = e.radius_mm
    sigma_axial = N / max(e.area, 1e-12)
    sigma_bend = M_bend_max * c / max(e.I, 1e-12)
    tau_torsion = Tq * c / max(e.J, 1e-12)
    sigma_normal = abs(sigma_axial) + sigma_bend
    sigma_vm = math.sqrt(sigma_normal**2 + 3.0 * tau_torsion**2)

    allow = max(e.working_stress_mpa, 1e-9)
    stress_ratio = sigma_vm / allow
    axial_ratio = abs(sigma_axial) / allow
    bending_ratio = sigma_bend / allow
    torsion_ratio = (math.sqrt(3.0) * tau_torsion) / allow

    if N < 0.0:
        Le = max(e.effective_length_factor * L, 1e-9)
        Pcr = (math.pi**2 * e.E * e.I) / (Le**2)
        buckling_ratio = (abs(N) * e.buckling_safety) / max(Pcr, 1e-12)
    else:
        Pcr = float("inf")
        buckling_ratio = 0.0

    strain_energy = max(0.0, 0.5 * float(u_local @ (kl @ u_local)))
    mechanism_ratios = {
        "axial": axial_ratio,
        "bending": bending_ratio,
        "torsion": torsion_ratio,
        "buckling": buckling_ratio,
    }
    governing = max(mechanism_ratios, key=mechanism_ratios.get)
    utilization = max(stress_ratio, buckling_ratio)

    return dict(
        N=N,
        sigma_axial=sigma_axial,
        sigma_bend=sigma_bend,
        tau_torsion=tau_torsion,
        sigma_vm=sigma_vm,
        stress_ratio=stress_ratio,
        axial_ratio=axial_ratio,
        bending_ratio=bending_ratio,
        torsion_ratio=torsion_ratio,
        buckling_ratio=buckling_ratio,
        utilization=utilization,
        governing=governing,
        strain_energy=strain_energy,
        length_mm=L,
        Pcr_N=Pcr,
    )


def solve_load_cases(
    nodes: list[Node],
    elements: list[BeamElement],
    load_cases: Sequence[LoadCase],
    *,
    monitor_nodes: Sequence[int] | None = None,
) -> SolveBundle:
    if not load_cases:
        raise ValueError("Se requiere al menos un LoadCase")

    K, free, sparse_backend = assemble_stiffness(nodes, elements)
    n_dof = len(nodes) * 6

    if monitor_nodes is None:
        monitor_nodes = [i for i, n in enumerate(nodes) if n.role == "LOAD"]

    if len(free):
        try:
            if sparse_backend:
                Kff = K[free][:, free].tocsc()
                lu = splu(Kff)
            else:
                Kff = K[np.ix_(free, free)]
                lu = None
        except Exception as exc:
            raise StructuralSolveError(
                "Matriz de rigidez singular o mal condicionada. Revisa apoyos, conectividad y barras activas."
            ) from exc
    else:
        Kff = None
        lu = None

    displacements: list[np.ndarray] = []
    per_case_results: list[list[dict | None]] = []
    max_disp = 0.0
    max_disp_node = None
    max_disp_case = None

    for case_idx, load in enumerate(load_cases):
        F = _build_load_vector(nodes, load)
        u = np.zeros(n_dof, dtype=float)
        if len(free):
            try:
                u[free] = lu.solve(F[free]) if sparse_backend else np.linalg.solve(Kff, F[free])
            except Exception as exc:
                raise StructuralSolveError(f"Fallo al resolver {load.name}") from exc

        displacements.append(u)
        case_results = [_element_result(nodes, e, u) if e.active else None for e in elements]
        per_case_results.append(case_results)

        for node_idx in monitor_nodes:
            d = float(np.linalg.norm(u[node_idx*6:node_idx*6+3]))
            if d > max_disp:
                max_disp = d
                max_disp_node = int(node_idx)
                max_disp_case = int(case_idx)

    worst_results: list[dict | None] = []
    for e_idx, e in enumerate(elements):
        if not e.active:
            worst_results.append(None)
            continue
        rows = [case[e_idx] for case in per_case_results if case[e_idx] is not None]
        if not rows:
            worst_results.append(None)
            continue
        worst = max(rows, key=lambda r: r["utilization"]).copy()
        for key in ("stress_ratio", "axial_ratio", "bending_ratio", "torsion_ratio", "buckling_ratio", "utilization", "strain_energy"):
            worst[key] = max(r[key] for r in rows)
        mechanism_ratios = {
            "axial": worst["axial_ratio"],
            "bending": worst["bending_ratio"],
            "torsion": worst["torsion_ratio"],
            "buckling": worst["buckling_ratio"],
        }
        worst["governing"] = max(mechanism_ratios, key=mechanism_ratios.get)
        worst_results.append(worst)

    return SolveBundle(
        displacements=displacements,
        per_case_results=per_case_results,
        worst_results=worst_results,
        max_monitor_displacement_mm=max_disp,
        max_monitor_node=max_disp_node,
        max_monitor_case=max_disp_case,
    )


def assemble_and_solve(nodes: list[Node], elements: list[BeamElement], load: LoadCase):
    bundle = solve_load_cases(nodes, elements, [load])
    return bundle.displacements[0], bundle.per_case_results[0]


def build_ground_structure(
    nodes: list[Node],
    *,
    max_length_mm: float,
    keep_out_check: Callable[[np.ndarray, np.ndarray], bool] | None = None,
    default_radius_mm: float = 1.2,
    beam_template: BeamElement | None = None,
) -> list[BeamElement]:
    elements: list[BeamElement] = []
    for a in range(len(nodes)):
        for b in range(a + 1, len(nodes)):
            d = float(np.linalg.norm(nodes[a].xyz - nodes[b].xyz))
            if d > max_length_mm or d < 1e-6:
                continue
            if keep_out_check is not None and keep_out_check(nodes[a].xyz, nodes[b].xyz):
                continue
            if beam_template is None:
                e = BeamElement(i=a, j=b, radius_mm=default_radius_mm)
            else:
                e = replace(beam_template, i=a, j=b, radius_mm=default_radius_mm, active=True)
            elements.append(e)
    return elements


def _system_metrics(nodes, elements, bundle, config):
    design_rows = [r for e, r in zip(elements, bundle.worst_results)
                   if e.active and not e.virtual and r is not None]
    max_stress = max((r["stress_ratio"] for r in design_rows), default=0.0)
    max_buckling = max((r["buckling_ratio"] for r in design_rows), default=0.0)
    max_util = max((r["utilization"] for r in design_rows), default=0.0)
    disp = bundle.max_monitor_displacement_mm
    active_indices = _active_element_indices(elements)
    total_volume = sum(
        elements[i].area * bundle.worst_results[i]["length_mm"]
        for i in active_indices
        if bundle.worst_results[i] is not None and elements[i].render and not elements[i].virtual
    )
    tol = config.numerical_tol
    hard_safe = (
        max_stress <= 1.0 + tol
        and max_buckling <= 1.0 + tol
        and disp <= config.displacement_limit_mm + tol
    )
    recommended = (
        max_stress <= config.design_utilization_target + tol
        and max_buckling <= config.design_utilization_target + tol
        and disp <= config.displacement_design_target_mm + tol
    )
    return dict(
        total_volume_mm3=float(total_volume),
        max_stress_ratio=float(max_stress),
        max_buckling_ratio=float(max_buckling),
        max_utilization=float(max_util),
        max_monitor_displacement_mm=float(disp),
        hard_safe=bool(hard_safe),
        recommended=bool(recommended),
        active_elements=sum(1 for i in active_indices if elements[i].render and not elements[i].virtual),
    )


_MECHANISM_EXPONENT = {
    "axial": 1.0 / 2.0,
    "bending": 1.0 / 3.0,
    "torsion": 1.0 / 3.0,
    "buckling": 1.0 / 4.0,
}


def _resize_elements(elements, bundle, config):
    active = [(i, e, bundle.worst_results[i]) for i, e in enumerate(elements)
              if e.active and not e.locked_radius and not e.virtual and bundle.worst_results[i] is not None]
    if not active:
        return

    energies = np.array([max(r["strain_energy"], 0.0) for _, _, r in active], dtype=float)
    participation = energies / energies.max() if energies.size and energies.max() > 0 else np.zeros_like(energies)

    disp_ratio = bundle.max_monitor_displacement_mm / max(config.displacement_design_target_mm, 1e-12)
    disp_factor = disp_ratio ** 0.25 if disp_ratio > 1.0 else 1.0

    for idx, (_, e, r) in enumerate(active):
        exponent = _MECHANISM_EXPONENT.get(r["governing"], 1.0 / 3.0)
        effective_util = max(r["utilization"] / max(config.design_utilization_target, 1e-9), 1e-9)
        structural_factor = effective_util ** exponent
        stiffness_factor = 1.0 + float(participation[idx]) * (disp_factor - 1.0) if disp_factor > 1.0 else 1.0
        target_radius = e.radius_mm * max(structural_factor, stiffness_factor)
        new_radius = e.radius_mm + config.relaxation * (target_radius - e.radius_mm)
        e.radius_mm = float(np.clip(new_radius, config.radius_min_mm, config.radius_max_mm))


def _candidate_prune_indices(elements, bundle, config):
    candidates = []
    for i, e in enumerate(elements):
        r = bundle.worst_results[i]
        if not e.active or r is None or not e.prunable or e.virtual:
            continue
        if e.radius_mm <= max(config.prune_below_mm, config.radius_min_mm) + 1e-9 and r["utilization"] < config.prune_utilization_threshold:
            candidates.append((r["strain_energy"], r["utilization"], i))
    candidates.sort()
    return [i for _, _, i in candidates[:config.max_prune_tests_per_iteration]]


def _try_prune_candidates(nodes, elements, load_cases, monitor_nodes, current_bundle, config):
    pruned = 0
    bundle = current_bundle
    for idx in _candidate_prune_indices(elements, bundle, config):
        e = elements[idx]
        e.active = False
        try:
            trial = solve_load_cases(nodes, elements, load_cases, monitor_nodes=monitor_nodes)
            metrics = _system_metrics(nodes, elements, trial, config)
            keep_removed = metrics["recommended"] if config.prune_requires_recommended else metrics["hard_safe"]
        except StructuralSolveError:
            keep_removed = False
            trial = None
        if keep_removed and trial is not None:
            pruned += 1
            bundle = trial
        else:
            e.active = True
    return pruned, bundle


def _fallback_perpendicular(ex: np.ndarray) -> np.ndarray:
    candidates = (
        np.array([1.0, 0.0, 0.0]),
        np.array([0.0, 1.0, 0.0]),
        np.array([0.0, 0.0, 1.0]),
    )
    ref = min(candidates, key=lambda a: abs(float(np.dot(a, ex))))
    v = np.cross(ex, ref)
    return v / max(np.linalg.norm(v), 1e-12)


def _reinforcement_direction(nodes, e, bundle):
    pi, pj = nodes[e.i].xyz, nodes[e.j].xyz
    axis = pj - pi
    ex = axis / max(np.linalg.norm(axis), 1e-12)
    best_vec, best_norm = None, 0.0
    for u in bundle.displacements:
        ui = u[e.i*6:e.i*6+3]
        uj = u[e.j*6:e.j*6+3]
        rel = uj - ui
        transverse = rel - np.dot(rel, ex) * ex
        n = float(np.linalg.norm(transverse))
        if n > best_norm:
            best_vec, best_norm = transverse, n
    return _fallback_perpendicular(ex) if best_vec is None or best_norm < 1e-9 else best_vec / best_norm


def _node_too_close(nodes, p, tol_mm):
    if not nodes:
        return False
    pts = np.vstack([n.xyz for n in nodes])
    d2 = np.sum((pts - p[None, :])**2, axis=1)
    return bool(np.any(d2 < tol_mm**2))


def _clone_beam_for_growth(base, i, j, radius_mm, tag):
    return replace(base, i=i, j=j, radius_mm=radius_mm, active=True, tag=tag,
                   render=True, locked_radius=False, prunable=True, virtual=False)


def add_local_triangle_reinforcements(
    nodes,
    elements,
    bundle,
    config,
    *,
    keep_out_check: Callable[[np.ndarray, np.ndarray], bool] | None = None,
):
    candidates = []
    for i, e in enumerate(elements):
        r = bundle.worst_results[i]
        if e.active and r is not None and e.render and not e.virtual:
            candidates.append((r["utilization"], r["strain_energy"], i))
    candidates.sort(reverse=True)
    candidates = candidates[:config.max_growth_elements_per_round]

    new_nodes = 0
    new_elements = 0
    for _, _, e_idx in candidates:
        e = elements[e_idx]
        r = bundle.worst_results[e_idx]
        disp_ratio = bundle.max_monitor_displacement_mm / max(config.displacement_design_target_mm, 1e-12)
        if r["utilization"] < config.growth_trigger_utilization and disp_ratio < config.growth_trigger_displacement_ratio:
            continue

        pa, pb = nodes[e.i].xyz, nodes[e.j].xyz
        mid = 0.5 * (pa + pb)
        L = float(np.linalg.norm(pb - pa))
        if L < 1e-6:
            continue

        h = float(np.clip(config.triangle_height_factor * L, config.triangle_height_min_mm, config.triangle_height_max_mm))
        direction = _reinforcement_direction(nodes, e, bundle)
        signs = (+1.0, -1.0) if r["governing"] == "torsion" else (+1.0,)

        for sgn in signs:
            p = mid + sgn * h * direction
            if _node_too_close(nodes, p, config.node_merge_distance_mm):
                continue
            if keep_out_check is not None and (keep_out_check(pa, p) or keep_out_check(p, pb)):
                continue

            new_idx = len(nodes)
            nodes.append(Node(xyz=p, fixed=np.array([False] * 6), role="FREE"))
            elements.extend([
                _clone_beam_for_growth(e, e.i, new_idx, config.growth_radius_mm, f"GROW_{e_idx}_A"),
                _clone_beam_for_growth(e, new_idx, e.j, config.growth_radius_mm, f"GROW_{e_idx}_B"),
            ])
            new_nodes += 1
            new_elements += 2

    return new_nodes, new_elements


def optimize_reinforcement(
    nodes: list[Node],
    elements: list[BeamElement],
    load_cases: LoadCase | Sequence[LoadCase],
    *,
    monitor_nodes: Sequence[int] | None = None,
    config: OptimizationConfig | None = None,
    keep_out_check: Callable[[np.ndarray, np.ndarray], bool] | None = None,
) -> OptimizationResult:
    config = config or OptimizationConfig()
    load_cases = [load_cases] if isinstance(load_cases, LoadCase) else list(load_cases)
    if not load_cases:
        raise ValueError("load_cases está vacío")

    history = []
    growth_rounds = 0
    bundle = solve_load_cases(nodes, elements, load_cases, monitor_nodes=monitor_nodes)

    for it in range(config.iterations):
        _resize_elements(elements, bundle, config)
        bundle = solve_load_cases(nodes, elements, load_cases, monitor_nodes=monitor_nodes)

        pruned, bundle = _try_prune_candidates(nodes, elements, load_cases, monitor_nodes, bundle, config)

        new_nodes = new_elements = 0
        current = _system_metrics(nodes, elements, bundle, config)
        should_grow = (
            config.enable_topology_growth
            and growth_rounds < config.max_growth_rounds
            and it % max(config.growth_every_n_iterations, 1) == 0
            and (
                current["max_utilization"] > config.growth_trigger_utilization
                or current["max_monitor_displacement_mm"] > config.displacement_design_target_mm * config.growth_trigger_displacement_ratio
            )
        )

        if should_grow:
            new_nodes, new_elements = add_local_triangle_reinforcements(
                nodes, elements, bundle, config, keep_out_check=keep_out_check
            )
            if new_elements:
                growth_rounds += 1
                bundle = solve_load_cases(nodes, elements, load_cases, monitor_nodes=monitor_nodes)

        metrics = _system_metrics(nodes, elements, bundle, config)
        history.append(dict(
            iteration=it,
            volume_mm3=metrics["total_volume_mm3"],
            max_stress_ratio=metrics["max_stress_ratio"],
            max_buckling_ratio=metrics["max_buckling_ratio"],
            max_utilization=metrics["max_utilization"],
            sleeve_displacement_mm=metrics["max_monitor_displacement_mm"],
            hard_safe=metrics["hard_safe"],
            recommended=metrics["recommended"],
            active_elements=metrics["active_elements"],
            total_nodes=len(nodes),
            new_nodes=new_nodes,
            new_elements=new_elements,
            pruned_elements=pruned,
        ))

        if (
            it >= config.min_iterations_before_convergence
            and metrics["recommended"]
            and len(history) >= 2
            and new_elements == 0
            and pruned == 0
        ):
            v0, v1 = history[-2]["volume_mm3"], history[-1]["volume_mm3"]
            if abs(v1 - v0) / max(abs(v1), 1e-9) < config.volume_rel_tol:
                break

    final_metrics = _system_metrics(nodes, elements, bundle, config)
    return OptimizationResult(
        history=history,
        final_bundle=bundle,
        hard_safe=final_metrics["hard_safe"],
        recommended=final_metrics["recommended"],
        active_elements=[i for i in _active_element_indices(elements) if elements[i].render and not elements[i].virtual],
        total_volume_mm3=final_metrics["total_volume_mm3"],
    )


def make_sleeve_load_cases(
    sleeve_node: int,
    *,
    axial_N: float = 40.0,
    lateral_N: float = 15.0,
    torque_Nmm: float = 25.0,
    axial_axis=(0.0, 0.0, -1.0),
    lateral_x_axis=(1.0, 0.0, 0.0),
    lateral_y_axis=(0.0, 1.0, 0.0),
    torque_axis=(0.0, 0.0, 1.0),
) -> list[LoadCase]:
    def unit(v):
        a = np.asarray(v, dtype=float)
        n = np.linalg.norm(a)
        if n < 1e-12:
            raise ValueError("Eje de carga nulo")
        return a / n

    az, ax, ay, at = map(unit, (axial_axis, lateral_x_axis, lateral_y_axis, torque_axis))
    cases = [
        LoadCase("AXIAL", forces={sleeve_node: axial_N * az}),
        LoadCase("LAT_X+", forces={sleeve_node: axial_N * az + lateral_N * ax}),
        LoadCase("LAT_X-", forces={sleeve_node: axial_N * az - lateral_N * ax}),
        LoadCase("LAT_Y+", forces={sleeve_node: axial_N * az + lateral_N * ay}),
        LoadCase("LAT_Y-", forces={sleeve_node: axial_N * az - lateral_N * ay}),
    ]
    if abs(torque_Nmm) > 0:
        cases += [
            LoadCase("TORQUE+", forces={sleeve_node: axial_N * az}, moments={sleeve_node: torque_Nmm * at}),
            LoadCase("TORQUE-", forces={sleeve_node: axial_N * az}, moments={sleeve_node: -torque_Nmm * at}),
        ]
    return cases


if __name__ == "__main__":
    nodes = [
        Node(np.array([0.0, 0.0, 0.0]), np.array([True] * 6), "KEEP_IN_SUPPORT"),
        Node(np.array([30.0, 0.0, 0.0]), np.array([True] * 6), "KEEP_IN_SUPPORT"),
        Node(np.array([15.0, 0.0, 6.0]), np.array([False] * 6), "LOAD"),
        Node(np.array([15.0, 0.0, 0.0]), np.array([False] * 6), "FREE"),
    ]

    template = BeamElement(
        0, 1, 1.0,
        E=2500.0, G=900.0,
        material_strength_mpa=80.0,
        material_safety_factor=1.25,
        process_safety_factor=1.15,
    )

    elements = build_ground_structure(
        nodes, max_length_mm=40.0,
        default_radius_mm=1.0,
        beam_template=template,
    )

    loads = make_sleeve_load_cases(
        sleeve_node=2,
        axial_N=40.0,
        lateral_N=15.0,
        torque_Nmm=20.0,
    )

    cfg = OptimizationConfig(
        iterations=16,
        design_utilization_target=0.75,
        displacement_limit_mm=0.20,
        displacement_design_target_mm=0.15,
        enable_topology_growth=True,
    )

    result = optimize_reinforcement(
        nodes,
        elements,
        loads,
        monitor_nodes=[2],
        config=cfg,
    )

    for row in result.history:
        print(
            f"it={row['iteration']:2d} "
            f"vol={row['volume_mm3']:8.1f} mm3 "
            f"U={row['max_utilization']:.3f} "
            f"disp={row['sleeve_displacement_mm']:.4f} mm "
            f"bars={row['active_elements']:3d} "
            f"+nodes={row['new_nodes']:2d} "
            f"pruned={row['pruned_elements']:2d} "
            f"recommended={row['recommended']}"
        )

    print("\nResultado:")
    print("  hard_safe   =", result.hard_safe)
    print("  recommended =", result.recommended)
    print("  volume_mm3  =", round(result.total_volume_mm3, 2))
