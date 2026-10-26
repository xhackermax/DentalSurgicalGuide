"""Continuous axial fill of the retentive model (pure NumPy)."""
import numpy as np

# Each iteration reaches one more ring of free vertices: 8 rings (~0.5-1 mm
# on an IOS) closes pits and softens borders without spreading fill onto
# the crowns the guide rests on.
FILL_ITERATIONS = 8
PIT_NEIGHBOUR_SHARE = 0.6
PIT_PASSES = 3


def blockout_shift(hits, retention, edges, min_hit=0.0, max_hit=0.0,
                   iterations=FILL_ITERATIONS):
    """Axial fill per vertex for a retention value, without pits or holes.

    ``hits`` encodes the ray result of each vertex: -1 = not a candidate
    (its axis points into the model: it never moves), 0 = candidate whose
    ray found nothing, >0 = axial distance to the blocking surface.

    Vertices with a measured blocking surface get exactly ``hit - retention``.
    Candidates without one (rays slipping between triangles, free borders)
    are filled from their neighbours: max(own need, neighbour average),
    bounded by any surface above them.  The fill is therefore continuous: a
    vertex can no longer stay behind as a pit among raised neighbours, and
    the borders of a blocked zone ramp down instead of leaving a step.
    """
    hits = np.asarray(hits, dtype=np.float64)
    count = len(hits)
    candidate = hits >= 0.0
    measured = hits > 0.0
    too_far = measured & (hits > max_hit) if max_hit > 0.0 else np.zeros(count, bool)
    fixed = measured & ~too_far
    required = np.where(fixed & (hits > min_hit), np.maximum(0.0, hits - retention), 0.0)
    upper = np.full(count, np.inf)
    upper[too_far] = np.maximum(0.0, hits[too_far] - retention)
    free = candidate & ~fixed
    shift = required.copy()
    edges = np.asarray(edges, dtype=np.int64).reshape(-1, 2)
    if not len(edges):
        return shift
    a, b = edges[:, 0], edges[:, 1]
    degree = np.maximum(np.bincount(a, minlength=count) + np.bincount(b, minlength=count), 1)

    def neighbour_mean(values):
        return (np.bincount(a, weights=values[b], minlength=count)
                + np.bincount(b, weights=values[a], minlength=count)) / degree

    if free.any():
        for _ in range(int(iterations)):
            shift = np.where(free, np.minimum(upper, np.maximum(required, neighbour_mean(shift))), required)
    # Hole closing: a vertex that never moves on its own (noisy normal facing
    # away) but sits inside a raised zone would stay behind as a pit.  It
    # follows its neighbours when most of them are raised; vertices on the
    # edge of a zone (tooth walls) are not lifted, so walls do not fold.
    still = ~candidate
    for _ in range(PIT_PASSES):
        raised = (shift > 0.0).astype(np.float64)
        share = neighbour_mean(raised)
        pit = still & (share >= PIT_NEIGHBOUR_SHARE)
        if not pit.any():
            break
        shift = np.where(pit, np.maximum(shift, neighbour_mean(shift) / np.maximum(share, 1e-9)), shift)
    return shift
