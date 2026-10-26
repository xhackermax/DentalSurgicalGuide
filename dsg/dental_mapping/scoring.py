"""Deterministic scoring helpers for future library/implant candidate selection."""
from __future__ import annotations

import math
from typing import Any, Mapping


def crown_candidate_score(
    *,
    deformation: Mapping[str, Any] | None = None,
    proximal: Mapping[str, Any] | None = None,
    mapping_confidence: float | None = None,
) -> dict[str, Any]:
    """Return an explainable score; hard invalid states are never compensated."""
    reasons = []
    if deformation and bool(deformation.get("requires_review", False)):
        reasons.append("ANATOMIC_FIT_REVIEW")
    hard_invalid = False
    prox_pen = 0.0
    prox_gap = 0.0
    prox_area = 0.0
    if proximal:
        for side in ("mesial", "distal"):
            item = proximal.get(side) or {}
            penetration = float(item.get("penetration_mm", 0.0) or 0.0)
            if penetration > 0.03:
                hard_invalid = True
                reasons.append(f"{side.upper()}_PENETRATION")
            if item.get("mean_gap_mm") is not None:
                prox_gap += float(item["mean_gap_mm"])
            prox_area += float(item.get("near_contact_area_mm2", 0.0) or 0.0)
            prox_pen += penetration
    conf = 1.0 if mapping_confidence is None else max(0.0, min(1.0, float(mapping_confidence)))
    score = 100.0 * conf - 15.0 * prox_gap + 0.5 * prox_area - 1000.0 * prox_pen
    if hard_invalid:
        score = float("-inf")
    return {
        "valid": not hard_invalid,
        "score": score if math.isfinite(score) else None,
        "reasons": reasons,
        "components": {
            "mapping_confidence": conf,
            "proximal_gap_mm_sum": prox_gap,
            "near_contact_area_mm2_sum": prox_area,
            "penetration_mm_sum": prox_pen,
        },
    }
