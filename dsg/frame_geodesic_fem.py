"""Discretize a curved, surface-authoritative route into the existing 3D FEM.

This creates *analytical* beam elements along a supplied intrinsic polyline.
It never finds routes, straightens the path, or generates Blender geometry.
Only a later measured post-Boolean geometry gate may approve printable guides.
"""
from __future__ import annotations

from dataclasses import replace

import numpy as np

from . import frame_fem_core as fem


class InvalidBeamPath(ValueError):
    pass


def append_geodesic_beams(
    nodes: list[fem.Node],
    elements: list[fem.BeamElement],
    path_points_mm,
    *,
    start_node: int,
    end_node: int,
    beam_template: fem.BeamElement,
    label: str,
    max_segment_mm: float = 2.0,
    zero_tolerance_mm: float = 0.02,
) -> tuple[int, ...]:
    """Represent every bend in a curved reinforcement with beam segments.

    Input must include the fixed support and sleeve attachment coordinates as
    its first and last points. This is a single topological member, so none
    of its constituent segments is prunable in the H1 implementation.
    """
    pts = np.asarray(path_points_mm, dtype=np.float64)
    if pts.ndim != 2 or pts.shape[1] != 3 or len(pts) < 2 or not np.isfinite(pts).all():
        raise InvalidBeamPath("nonfinite or empty FEM polyline")
    if not (0 <= start_node < len(nodes) and 0 <= end_node < len(nodes)) or start_node == end_node:
        raise InvalidBeamPath("invalid FEM endpoint identity")
    if np.linalg.norm(pts[0] - nodes[start_node].xyz) > zero_tolerance_mm:
        raise InvalidBeamPath("FEM support differs from surface path start")
    if np.linalg.norm(pts[-1] - nodes[end_node].xyz) > zero_tolerance_mm:
        raise InvalidBeamPath("FEM sleeve differs from surface path end")
    if not (np.isfinite(max_segment_mm) and max_segment_mm > 0):
        raise InvalidBeamPath("invalid FEM resolution")
    lengths = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    if not np.all(lengths > 1e-6):
        raise InvalidBeamPath("duplicate FEM path points")
    if np.any(lengths > max_segment_mm + 1e-8):
        raise InvalidBeamPath("GEODESIC_SEGMENT_TOO_LONG: refine the surface path first")
    # Stage *all* validation before mutating caller-owned FEM state.
    mids = [
        fem.Node(xyz=np.array(p, dtype=float), fixed=np.zeros(6, dtype=bool),
                 role="GEODESIC_PATH")
        for p in pts[1:-1]
    ]
    first_new_node = len(nodes)
    chain_nodes = [start_node, *range(first_new_node, first_new_node + len(mids)), end_node]
    beams = [
        replace(beam_template, i=int(i), j=int(j), tag=f"{label}:SEG{k:03d}",
                prunable=False, active=True, render=True, virtual=False)
        for k, (i, j) in enumerate(zip(chain_nodes, chain_nodes[1:]))
    ]
    first_element = len(elements)
    nodes.extend(mids)
    elements.extend(beams)
    return tuple(range(first_element, first_element + len(beams)))
