"""Sequential-opening irrigation network: pure hydraulic design (no ``bpy``).

Clinical intent (DSG 9.7.1)
---------------------------
One main channel runs from the *initial* sleeve **A** to an external inlet in
the air. Other sleeves (B, C, …) are Linked to that trunk with Y junctions.

* A is open; every Linked sleeve starts closed by a marked 0.10 mm frangible
  wall. Water therefore reaches A (the sleeve farthest from the inlet) first.
* The surgeon then perforates the Linked sleeves in order, from the one whose
  junction is closest to A towards the one closest to the inlet.
* Every Y junction therefore has to *favour the daughter branch* and make it
  harder for water to keep going towards A. This is achieved with a smooth
  metering throat on the trunk **immediately downstream of each split**
  (towards A) — the inverse of the former symmetric/"balanced" Y.

The throat of each junction is sized so that, at the moment its branch is
opened (all branches nearer to A already open, all nearer to the inlet still
sealed), the newly opened branch receives at least ``target_open_branch_share``
of the flow reaching that junction.

Hydraulics: laminar Hagen–Poiseuille, resistance ∝ ∫ ds / D(s)⁴. All values
are *relative* (mm⁻³); viscosity and π/128 cancel in every ratio used here.

Conventions: trunk samples are ordered **sleeve A → inlet** (as DSG stores
irrigation paths); arclength ``s`` is measured from sleeve A along the trunk.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Iterable, Sequence

Point = Sequence[float]
Sample = tuple[Point, float]          # (xyz in mm, lumen radius in mm)


# ── Configuration ───────────────────────────────────────────────────────────
@dataclass(frozen=True)
class NetworkPolicy:
    target_open_branch_share: float = 0.75
    lumen_diameter_mm: float = 1.00
    min_throat_diameter_mm: float = 0.72      # printable lower bound (SLA resin)
    max_throat_diameter_mm: float = 0.94      # above this a throat is not worth printing
    nominal_throat_length_mm: float = 0.90
    min_throat_length_mm: float = 0.20
    split_clearance_mm: float = 0.70          # keep the Y plenum untouched
    inlet_transition_mm: float = 0.35
    outlet_transition_mm: float = 0.50
    end_clearance_mm: float = 1.20            # keep away from the next Y / sleeve C-port

    def __post_init__(self):
        if not 0.5 <= self.target_open_branch_share < 1.0:
            raise ValueError("target_open_branch_share must be in [0.5, 1)")
        if not 0.0 < self.min_throat_diameter_mm < self.max_throat_diameter_mm < self.lumen_diameter_mm:
            raise ValueError("require 0 < min throat < max throat < lumen diameter")

    @property
    def reserved_length_mm(self) -> float:
        return (self.split_clearance_mm + self.inlet_transition_mm
                + self.outlet_transition_mm + self.end_clearance_mm)


# ── Geometry / resistance primitives ────────────────────────────────────────
def _dist(a: Point, b: Point) -> float:
    return math.sqrt(sum((float(x) - float(y)) ** 2 for x, y in zip(a, b)))


def arclengths(points: Sequence[Point]) -> list[float]:
    out = [0.0]
    for a, b in zip(points[:-1], points[1:]):
        out.append(out[-1] + _dist(a, b))
    return out


def project_arclength(points: Sequence[Point], query: Point) -> tuple[float, float]:
    """Arclength of the closest point of the polyline to ``query`` and the distance."""
    if len(points) < 2:
        raise ValueError("polyline needs at least two points")
    s_acc = arclengths(points)
    best = (float("inf"), 0.0)
    for i, (a, b) in enumerate(zip(points[:-1], points[1:])):
        ab = [float(y) - float(x) for x, y in zip(a, b)]
        aq = [float(y) - float(x) for x, y in zip(a, query)]
        L2 = sum(v * v for v in ab)
        t = 0.0 if L2 <= 1e-18 else max(0.0, min(1.0, sum(u * v for u, v in zip(ab, aq)) / L2))
        c = [float(x) + v * t for x, v in zip(a, ab)]
        d = _dist(c, query)
        if d < best[0]:
            best = (d, s_acc[i] + t * math.sqrt(L2))
    return best[1], best[0]


def resistance(samples: Sequence[Sample], s0: float | None = None, s1: float | None = None,
               min_diameter_mm: float = 0.20) -> float:
    """Relative Poiseuille resistance ∫ ds / D⁴ of the samples between arclengths."""
    if len(samples) < 2:
        return 0.0
    pts = [p for p, _r in samples]
    s = arclengths(pts)
    lo = s[0] if s0 is None else float(s0)
    hi = s[-1] if s1 is None else float(s1)
    if hi <= lo:
        return 0.0
    total = 0.0
    for i in range(len(samples) - 1):
        a, b = max(lo, s[i]), min(hi, s[i + 1])
        if b <= a:
            continue
        d = max(min_diameter_mm, float(samples[i][1]) + float(samples[i + 1][1]))  # mean diameter
        total += (b - a) / d ** 4
    return total


# ── Throat sizing ───────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Throat:
    diameter_mm: float
    length_mm: float
    added_resistance: float
    exact: bool
    limited_by: str = ""

    @property
    def active(self) -> bool:
        return self.length_mm > 0.0


NO_THROAT = Throat(diameter_mm=0.0, length_mm=0.0, added_resistance=0.0, exact=True)


def solve_throat(delta_resistance: float, room_mm: float, policy: NetworkPolicy) -> Throat:
    """Smallest-loss printable throat adding at least ``delta_resistance``."""
    D = policy.lumen_diameter_mm

    def coef(d):
        return 1.0 / d ** 4 - 1.0 / D ** 4

    if delta_resistance <= 0.0:
        return NO_THROAT
    if room_mm < policy.min_throat_length_mm:
        return Throat(0.0, 0.0, 0.0, False, "NO_PRINTABLE_SPACE")
    length = min(policy.nominal_throat_length_mm, room_mm)
    d = (delta_resistance / length + 1.0 / D ** 4) ** -0.25
    if d > policy.max_throat_diameter_mm:
        d = policy.max_throat_diameter_mm
        length = delta_resistance / coef(d)
        if length < policy.min_throat_length_mm:
            length = policy.min_throat_length_mm            # tiny need: short mild throat
        if length > room_mm:
            return Throat(d, room_mm, room_mm * coef(d), False, "AVAILABLE_LENGTH")
        return Throat(d, length, length * coef(d), True)
    if d < policy.min_throat_diameter_mm:
        d = policy.min_throat_diameter_mm
        length = delta_resistance / coef(d)
        if length > room_mm:
            return Throat(d, room_mm, room_mm * coef(d), False, "MIN_DIAMETER_AND_AVAILABLE_LENGTH")
        return Throat(d, length, length * coef(d), True, "THROAT_LENGTH_EXTENDED_AT_MIN_DIAMETER")
    return Throat(d, length, length * coef(d), True)


# ── Network design ──────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Branch:
    name: str
    split_s_mm: float            # arclength of the Y split from sleeve A along the trunk
    link_resistance: float       # branch resistance split → its sleeve


@dataclass
class Junction:
    order: int                   # perforation order (A = 1, first Linked sleeve = 2 …)
    branch: str
    split_s_mm: float
    room_mm: float
    link_resistance: float
    downstream_resistance: float
    required_extra_resistance: float
    throat: Throat
    predicted_share_at_opening: float


@dataclass
class NetworkDesign:
    source: str
    order: list[str]
    junctions: list[Junction]
    stages: list[dict]           # [{"open": [...], "shares": {name: fraction}}]
    policy: NetworkPolicy
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "schema": "dsg.irrigation_sequential_network.v1",
            "source": self.source,
            "perforation_order": list(self.order),
            "junctions": [dict(asdict(j), throat=asdict(j.throat)) for j in self.junctions],
            "stages": self.stages,
            "policy": asdict(self.policy),
            "warnings": list(self.warnings),
        }


def _parallel(*resistances: float) -> float:
    g = sum(1.0 / r for r in resistances if r is not None and math.isfinite(r) and r > 0.0)
    return math.inf if g <= 0.0 else 1.0 / g


def _stage_shares(source: str, ordered: list[Branch], trunk: Sequence[Sample],
                  throats: list[Throat], open_names: set[str]) -> dict[str, float]:
    """Flow fraction reaching each open outlet (normalised to the trunk flow)."""
    # Bottom-up equivalent resistance seen just above each split (node k).
    r_a = resistance(trunk, 0.0, ordered[0].split_s_mm if ordered else None)
    eq_below = r_a                                     # equivalent from node k downwards (trunk side)
    node_parts = []                                    # (R_trunk_side_incl_throat, R_link or inf)
    for k, br in enumerate(ordered):
        r_trunk_side = eq_below + throats[k].added_resistance
        r_link = br.link_resistance if br.name in open_names else math.inf
        node_parts.append((r_trunk_side, r_link))
        eq_node = _parallel(r_trunk_side, r_link)
        nxt = ordered[k + 1].split_s_mm if k + 1 < len(ordered) else None
        if nxt is not None:
            eq_below = eq_node + resistance(trunk, br.split_s_mm, nxt)
    shares: dict[str, float] = {}
    flow = 1.0
    for k in range(len(ordered) - 1, -1, -1):          # from the inlet side down to A
        r_trunk_side, r_link = node_parts[k]
        g_t = 0.0 if not math.isfinite(r_trunk_side) else 1.0 / r_trunk_side
        g_l = 0.0 if not math.isfinite(r_link) else 1.0 / r_link
        total = g_t + g_l
        to_link = 0.0 if total <= 0.0 else flow * g_l / total
        if ordered[k].name in open_names:
            shares[ordered[k].name] = to_link
        flow -= to_link
    shares[source] = flow
    return shares


def design_sequential_network(source: str, trunk: Sequence[Sample], branches: Iterable[Branch],
                              policy: NetworkPolicy = NetworkPolicy()) -> NetworkDesign:
    """Size one metering throat per junction and predict every opening stage."""
    if len(trunk) < 2:
        raise ValueError("trunk needs at least two samples")
    total_len = arclengths([p for p, _ in trunk])[-1]
    ordered = sorted(branches, key=lambda b: b.split_s_mm)
    warnings: list[str] = []
    f = policy.target_open_branch_share
    throats: list[Throat] = []
    junctions: list[Junction] = []

    eq_below = None
    prev_s = 0.0
    for k, br in enumerate(ordered):
        if not 0.0 < br.split_s_mm < total_len:
            raise ValueError(f"split of {br.name} lies outside the trunk")
        seg = resistance(trunk, prev_s, br.split_s_mm)
        r_down = seg if eq_below is None else seg + eq_below
        # Room for the throat: between this split and the previous split / sleeve A.
        room = max(0.0, (br.split_s_mm - prev_s) - policy.reserved_length_mm)
        needed = max(0.0, br.link_resistance * f / (1.0 - f) - r_down)
        throat = solve_throat(needed, room, policy)
        throats.append(throat)
        r_trunk_side = r_down + throat.added_resistance
        share = (1.0 / br.link_resistance) / (1.0 / br.link_resistance + 1.0 / r_trunk_side)
        if share + 1e-9 < f:
            warnings.append(
                f"{br.name}: predicted share when opened {share:.0%} < target {f:.0%} "
                f"({throat.limited_by or 'geometry'})")
        junctions.append(Junction(
            order=k + 2, branch=br.name, split_s_mm=br.split_s_mm, room_mm=room,
            link_resistance=br.link_resistance, downstream_resistance=r_down,
            required_extra_resistance=needed, throat=throat, predicted_share_at_opening=share))
        eq_below = _parallel(r_trunk_side, br.link_resistance)
        prev_s = br.split_s_mm

    order = [source] + [b.name for b in ordered]
    stages = []
    for j in range(len(order)):
        open_names = set(order[:j + 1])
        stages.append({"open": order[:j + 1],
                       "shares": _stage_shares(source, ordered, trunk, throats, open_names)})
    return NetworkDesign(source, order, junctions, stages, policy, warnings)


# ── Automatic Link placement helpers ────────────────────────────────────────
def point_at_arclength(points: Sequence[Point], s: float) -> tuple[tuple[float, float, float],
                                                                  tuple[float, float, float]]:
    """Point and unit tangent (sleeve A → inlet) at arclength ``s``."""
    if len(points) < 2:
        raise ValueError("polyline needs at least two points")
    acc = arclengths(points)
    s = max(0.0, min(float(s), acc[-1]))
    for i in range(len(points) - 1):
        if s <= acc[i + 1] or i == len(points) - 2:
            seg = acc[i + 1] - acc[i]
            t = 0.0 if seg <= 1e-12 else (s - acc[i]) / seg
            a, b = points[i], points[i + 1]
            p = tuple(float(x) + (float(y) - float(x)) * t for x, y in zip(a, b))
            d = [float(y) - float(x) for x, y in zip(a, b)]
            n = math.sqrt(sum(v * v for v in d)) or 1.0
            return p, tuple(v / n for v in d)
    raise AssertionError("unreachable")


@dataclass(frozen=True)
class PlacementRules:
    min_from_source_sleeve_mm: float = 3.0   # clear of sleeve A and its C-port
    min_from_inlet_mm: float = 7.5           # clear of the Ø4 inlet + 2 mm reduction
    min_split_spacing_mm: float = 4.5        # two Y plenums + one metering throat


def choose_split_arclength(candidate_s: float, occupied_s: Iterable[float], total_length: float,
                           rules: PlacementRules = PlacementRules()) -> float | None:
    """Nearest admissible split position to ``candidate_s`` (None if the trunk is full)."""
    lo = rules.min_from_source_sleeve_mm
    hi = total_length - rules.min_from_inlet_mm
    if hi < lo:
        return None
    # Admissible set = [lo, hi] minus open intervals around occupied splits.
    forbidden = sorted((s - rules.min_split_spacing_mm, s + rules.min_split_spacing_mm) for s in occupied_s)
    intervals = []
    start = lo
    for a, b in forbidden:
        if b <= start:
            continue
        if a > start:
            intervals.append((start, min(a, hi)))
        start = max(start, b)
        if start >= hi:
            break
    if start <= hi:
        intervals.append((start, hi))
    best = None
    for a, b in intervals:
        if b < a:
            continue
        s = min(max(candidate_s, a), b)
        if best is None or abs(s - candidate_s) < abs(best - candidate_s):
            best = s
    return best
