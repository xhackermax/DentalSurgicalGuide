"""Frangible irrigation wall + perforation marks: pure geometry (no ``bpy``).

Local frame of one sleeve outlet (all mm):

* origin  = point where the irrigation outlet meets the sleeve bore surface;
* +z      = outward, i.e. from the bore into the sleeve wall along the outlet;
* z < 0   = inside the drill bore (must stay free: nothing is ever added there).

::

      bore (drill)   │ sleeve wall ─────────────────────────▶ +z
                     │
      countersink  ╲ │ ┌ pocket ┐┌membrane┐ irrigation channel
      (cut, 0.2 mm) ╲│ │ 0.30mm ││0.10 c. │ (water arrives here)
                     │ └────────┘│0.25 rim│
                     │           └────────┘

* The **membrane** fills the outlet channel between ``pocket_depth`` and
  ``pocket_depth + rim`` and overlaps the surrounding wall so the union seals.
  It is 0.10 mm thick in the centre (weak spot) and 0.25 mm at the rim, so it
  breaks in the centre and does not detach as a whole.
* The **mark** is material *removed*, never added inside the bore: a conical
  countersink around the outlet on the bore wall plus the open pocket in front
  of the membrane. It self-centres a probe/bur and stays printable.
* The **opening order** is engraved as a digit on the guide exterior next to
  the sleeve (handled by the Blender adapter).
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class SealDesign:
    membrane_center_mm: float = 0.10
    membrane_rim_mm: float = 0.25
    weak_radius_ratio: float = 0.55        # thin centre radius / outlet lumen radius
    wall_overlap_mm: float = 0.15          # membrane radius beyond the outlet lumen
    pocket_depth_mm: float = 0.30          # open pocket in front of the membrane
    countersink_extra_radius_mm: float = 0.30
    countersink_depth_mm: float = 0.20
    bore_clearance_mm: float = 0.30        # cutters start this far inside the bore
    label_size_mm: float = 2.0
    label_depth_mm: float = 0.30
    min_printable_feature_mm: float = 0.30

    def __post_init__(self):
        if not 0.0 < self.membrane_center_mm < self.membrane_rim_mm:
            raise ValueError("membrane centre must be thinner than its rim")
        if not 0.2 <= self.weak_radius_ratio < 1.0:
            raise ValueError("weak_radius_ratio must be in [0.2, 1)")
        if self.countersink_depth_mm > self.pocket_depth_mm:
            raise ValueError("countersink must end before the membrane")

    def validate_outlet(self, lumen_radius_mm: float) -> list[str]:
        """Printability problems for an outlet of this lumen radius."""
        problems = []
        if 2.0 * lumen_radius_mm < self.min_printable_feature_mm:
            problems.append(f"pocket Ø{2 * lumen_radius_mm:.2f} mm < printable {self.min_printable_feature_mm:.2f} mm")
        if self.countersink_extra_radius_mm < self.min_printable_feature_mm * 0.5:
            problems.append("countersink too narrow to be seen")
        if self.pocket_depth_mm < self.min_printable_feature_mm:
            problems.append("pocket too shallow to be printed")
        return problems


def membrane_profile(lumen_radius_mm: float, d: SealDesign = SealDesign()) -> list[tuple[float, float]]:
    """Closed (r, z) profile of the membrane, counter-clockwise, first/last on the axis."""
    R = lumen_radius_mm + d.wall_overlap_mm
    rw = max(0.05, lumen_radius_mm * d.weak_radius_ratio)
    z0 = d.pocket_depth_mm
    return [
        (0.0, z0), (R, z0),                                  # flat front face (visible)
        (R, z0 + d.membrane_rim_mm), (rw, z0 + d.membrane_rim_mm),   # thick rim
        (rw, z0 + d.membrane_center_mm), (0.0, z0 + d.membrane_center_mm),  # thin centre
    ]


def countersink_profile(lumen_radius_mm: float, d: SealDesign = SealDesign()) -> list[tuple[float, float]]:
    """Closed (r, z) profile of the countersink cutter (starts inside the bore)."""
    r_top = lumen_radius_mm + d.countersink_extra_radius_mm
    return [
        (0.0, -d.bore_clearance_mm), (r_top, -d.bore_clearance_mm),
        (r_top, 0.0), (lumen_radius_mm, d.countersink_depth_mm),
        (0.0, d.countersink_depth_mm),
    ]


def revolve(profile: list[tuple[float, float]], segments: int = 48):
    """Solid of revolution around +z.

    ``profile`` is an open polyline whose first and last points lie on the axis
    (r = 0). Returns ``(verts, faces)`` of a closed, outward-oriented 2-manifold.
    """
    if len(profile) < 3 or profile[0][0] != 0.0 or profile[-1][0] != 0.0:
        raise ValueError("profile must start and end on the axis")
    segments = max(8, int(segments))
    verts: list[tuple[float, float, float]] = []
    ring_index: list[list[int] | int] = []
    for r, z in profile:
        if r == 0.0:
            ring_index.append(len(verts))
            verts.append((0.0, 0.0, z))
        else:
            ids = []
            for k in range(segments):
                a = 2.0 * math.pi * k / segments
                ids.append(len(verts))
                verts.append((r * math.cos(a), r * math.sin(a), z))
            ring_index.append(ids)
    faces: list[tuple[int, ...]] = []
    for a, b in zip(ring_index[:-1], ring_index[1:]):
        for k in range(segments):
            k1 = (k + 1) % segments
            if isinstance(a, int) and isinstance(b, int):
                raise ValueError("two consecutive axis points")
            if isinstance(a, int):
                faces.append((a, b[k1], b[k]))
            elif isinstance(b, int):
                faces.append((a[k], a[k1], b))
            else:
                faces.append((a[k], a[k1], b[k1], b[k]))
    # Orient outward: the profile is traversed so that the solid is on one side;
    # flip every face if the signed volume comes out negative.
    if _signed_volume(verts, faces) < 0.0:
        faces = [tuple(reversed(f)) for f in faces]
    return verts, faces


def _signed_volume(verts, faces) -> float:
    vol = 0.0
    for f in faces:
        a = verts[f[0]]
        for i in range(1, len(f) - 1):
            b, c = verts[f[i]], verts[f[i + 1]]
            vol += (a[0] * (b[1] * c[2] - b[2] * c[1]) - a[1] * (b[0] * c[2] - b[2] * c[0])
                    + a[2] * (b[0] * c[1] - b[1] * c[0])) / 6.0
    return vol
