"""Atomic perimeter-loop beam assembly for the experimental DSG geodesic FEM.

Uses the already-authoritative surface route samples, and the existing FEM
beam discretizer. The loop is NONPRUNABLE, kept in the volume accounting.
It does not make hard-clamped support nodes physically calibrated contact
conditions: that remains a separate H4 acceptance gate.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import numpy as np

from . import frame_fem_core as fem
from . import frame_geodesic_fem as geodesic_fem


class InvalidPerimeterLoop(ValueError):
    pass


@dataclass(frozen=True)
class PerimeterLoop:
    beam_indices: tuple[int, ...]
    edges: tuple[dict, ...]
    length_mm: float
    radius_mm: float
    is_closed: bool = True
    support_contact_calibrated: bool = False


def append_perimeter_loop(
    nodes: list[fem.Node],
    elements: list[fem.BeamElement],
    support_indices: tuple[int,int,int,int],
    surface_edge_paths: list,
    *,
    radius_mm: float,
    template: fem.BeamElement,
    max_segment_mm: float = 1.51,
) -> PerimeterLoop:
    """Append four surface-routed members as one atomic perimeter addition."""
    ids=tuple(int(x) for x in support_indices)
    if len(ids)!=4 or len(set(ids))!=4 or any(i<0 or i>=len(nodes) for i in ids):
        raise InvalidPerimeterLoop("PERIMETER_REQUIRES_FOUR_DISTINCT_SUPPORTS")
    if len(surface_edge_paths)!=4:
        raise InvalidPerimeterLoop("PERIMETER_REQUIRES_FOUR_SURFACE_EDGES")
    r=float(radius_mm)
    if not math.isfinite(r) or r<=0:
        raise InvalidPerimeterLoop("PERIMETER_INVALID_RADIUS")
    # Stage on copy-of-lists, committing only after all edges pass.
    staged_nodes=list(nodes)
    staged_elements=list(elements)
    records=[]
    all_indices=[]
    total=0.
    pairs=tuple(zip(ids, ids[1:]+ids[:1]))
    for k,((i,j),raw) in enumerate(zip(pairs,surface_edge_paths)):
        points=np.asarray(raw,dtype=np.float64)
        if points.ndim!=2 or points.shape[1]!=3 or len(points)<2 or not np.isfinite(points).all():
            raise InvalidPerimeterLoop(f"PERIMETER_EDGE_{k+1}_INVALID")
        distances=np.linalg.norm(np.diff(points,axis=0),axis=1)
        if np.any(distances<=1e-6):
            raise InvalidPerimeterLoop(f"PERIMETER_EDGE_{k+1}_DUPLICATE_POINTS")
        try:
            idx=geodesic_fem.append_geodesic_beams(
                staged_nodes,staged_elements,points,
                start_node=i,end_node=j,
                beam_template=template,label=f"FRAME_PERIMETER_E{k+1}",
                max_segment_mm=max_segment_mm,
            )
        except geodesic_fem.InvalidBeamPath as exc:
            raise InvalidPerimeterLoop(
                f"PERIMETER_EDGE_{k+1}_INVALID: {exc}"
            ) from exc
        for beam_id in idx:
            beam=staged_elements[beam_id]
            beam.locked_radius=True
            beam.prunable=False
            beam.radius_mm=r
        length=float(distances.sum())
        total+=length
        all_indices.extend(idx)
        records.append({
            "edge":f"E{k+1}",
            "support_from":i,"support_to":j,
            "beam_indices":list(idx),
            "length_mm":length,
        })
    nodes[:]=staged_nodes
    elements[:]=staged_elements
    return PerimeterLoop(tuple(all_indices),tuple(records),total,r)
