"""Predict the final Boolean on geodesic cross-sections of the frame.

The guide frame is a tube whose part inside the passive (retentive) model
is removed by the final Boolean.  Where the tube sinks too deep, or rides
over a cusp, the material left can become thin enough to break.

For every station along the smoothed centreline this module looks at the
surface band that lies within one tube radius of the frame route measured
*geodesically* on the retentive shell (never through the air, so the far
wall of an embrasure or the other side of a cusp does not count), cuts it
with the plane normal to the tube and predicts what the Boolean will leave:

* retained thickness: top of the tube minus the surface profile under it;
* embed: how deep the bottom of the tube goes below that surface.

The centreline is then moved along the surface normal, with a smooth
envelope, until every station keeps at least ``MIN_THICKNESS_MM`` and an
embed between ``EMBED_MIN_FRACTION`` and ``EMBED_MAX_FRACTION`` of the
diameter.  Where both cannot hold, the tube is thickened locally.
"""
import numpy as np

MIN_THICKNESS_MM = 2.0
EMBED_MIN_FRACTION = 0.30
EMBED_MAX_FRACTION = 0.45
MAX_RADIUS_FACTOR = 1.5
SLAB_HALF_WIDTH_MM = 0.25
TOLERANCE_MM = 0.03


def _circular(values, function, half):
    stack = [np.roll(values, shift, axis=0) for shift in range(-half, half + 1)]
    return function(np.stack(stack), axis=0)


def _gaussian(values, sigma):
    from .organic_curve import circular_gaussian
    return circular_gaussian(values, sigma)


def _envelope(values, step, window_mm, sigma_mm, positive=True):
    """Smooth requirement that never falls below (or above) the original."""
    half = max(1, int(round(window_mm / step)))
    peak = _circular(values, np.max if positive else np.min, half)
    return _gaussian(peak, sigma_mm / step)


def _geodesic_band(context, surface, route, radius):
    """Surface vertices within ~1.3 radius of the route, measured on the shell."""
    from scipy.sparse import csr_matrix
    from scipy.sparse.csgraph import dijkstra
    from scipy.spatial import cKDTree
    from .. import guide_module as g
    cache = g._build_frame_surface_graph_cache(context, surface)[0]
    if cache is None:
        raise RuntimeError('surface graph unavailable')
    labels = g._frame_component_labels(cache)
    coords = cache['coords']
    if labels is not None and int(labels.max(initial=0)) > 0:
        component = g._frame_preferred_component(cache, labels, g.get_insertion_axis())
        members = np.flatnonzero(labels == component)
    else:
        members = np.arange(len(coords))
    sources = np.unique(members[cKDTree(coords[members]).query(route)[1]])
    count = int(cache['vertex_count'])
    graph = cache.get('scipy_csr_graph')
    if graph is None:
        graph = csr_matrix((cache['csr_weights'], cache['csr_dst'], cache['csr_offsets']), shape=(count, count))
        cache['scipy_csr_graph'] = graph
    distance = dijkstra(graph, directed=True, indices=sources, min_only=True, limit=float(radius) * 1.3)
    band = np.flatnonzero(np.isfinite(distance))
    return coords[band], cache['normals'][band]


def _frames(route, band_points, band_normals, band_tree, radius, step):
    guide = _gaussian(route, 1.0 / step)
    tangents = np.roll(guide, -1, axis=0) - np.roll(guide, 1, axis=0)
    tangents /= np.maximum(np.linalg.norm(tangents, axis=1), 1e-12)[:, None]
    normals = np.zeros_like(route)
    for index, centre in enumerate(route):
        near = band_tree.query_ball_point(centre, radius * 1.6)
        if near:
            normals[index] = band_normals[near].mean(axis=0)
    normals = _gaussian(normals, max(2.0, radius) / step)
    normals -= tangents * np.sum(normals * tangents, axis=1)[:, None]
    lengths = np.linalg.norm(normals, axis=1)
    fallback = lengths < 1e-9
    normals[fallback] = np.array([0.0, 0.0, 1.0])
    normals /= np.maximum(np.linalg.norm(normals, axis=1), 1e-12)[:, None]
    return tangents, normals


def predict(route, tangents, normals, radii, band_points, band_tree):
    """Retained thickness, embed depth and support for every station."""
    count = len(route)
    thickness = np.full(count, np.inf)
    embed = np.zeros(count)
    supported = np.zeros(count, dtype=bool)
    for index in range(count):
        centre, tangent, normal, radius = route[index], tangents[index], normals[index], radii[index]
        near = band_tree.query_ball_point(centre, radius * 1.6)
        if not near:
            continue
        offset = band_points[near] - centre
        slab = np.abs(offset @ tangent) <= SLAB_HALF_WIDTH_MM
        if not np.any(slab):
            continue
        offset = offset[slab]
        lateral = offset @ np.cross(tangent, normal)
        height = offset @ normal
        central = np.abs(lateral) <= 0.5 * radius
        if not np.any(central):
            continue
        supported[index] = True
        half_chord = np.sqrt(np.maximum(radius * radius - lateral[central] ** 2, 0.0))
        surface = np.maximum(height[central], -half_chord)
        thickness[index] = float(np.min(half_chord - surface))
        embed[index] = float(np.max(height[central]) + radius)
    return thickness, embed, supported


SUPPORT_WINDOW_MM = 4.0  # ±: the 30 % minimum embed must hold within each window


def _corridor(route, tangents, normals, radii, band_points, tree, step=0.4):
    """Allowed shift along the normal for every station (outward positive).

    Moving the centre outward by d lowers the embed by d and raises the
    retained thickness by d, so the clinical limits become an interval.
    """
    thickness, embed, supported = predict(route, tangents, normals, radii, band_points, tree)
    lower = np.maximum(embed - EMBED_MAX_FRACTION * 2.0 * radii, MIN_THICKNESS_MM - thickness)
    upper = embed - EMBED_MIN_FRACTION * 2.0 * radii
    # A station without surface under the tube: never push it further out.
    lower[~supported] = -radii[~supported]
    upper[~supported] = 0.0
    # Sampling noise of the cross-sections: a smooth envelope that stays above
    # the measured requirement (never lowers a safety limit).
    lower = np.maximum(lower, _envelope(lower, step, 0.8, 0.6))
    # Thickness and the 45 % maximum are hard limits at every station (that is
    # where the frame would break).  The 30 % minimum is a support condition:
    # it must hold within every short window, so the tube may bridge a valley
    # between cusps (more material there, not less) instead of dipping into
    # each one, which is what made it look like a stack of rolls.
    half = max(1, int(round(SUPPORT_WINDOW_MM / step)))
    upper = _circular(upper, np.max, half)
    return lower, upper


def _minimum_bending(shift, lower, upper, iterations=4000):
    """Least-bending profile inside the corridor (projected bi-Laplacian).

    Clipping a smoothed profile against the limits leaves small corners where
    it touches them.  Minimising the bending energy (sum of squared second
    differences) under the same bounds removes them: the tube flexes only as
    much as the anatomy forces it to.
    """
    value = np.clip(shift, lower, upper)
    for _ in range(iterations):
        second = np.roll(value, -1) - 2.0 * value + np.roll(value, 1)
        fourth = np.roll(second, -1) - 2.0 * second + np.roll(second, 1)
        value = np.clip(value - fourth / 20.0, lower, upper)
    return value


def solve(route, band_points, band_normals, radius, step):
    """Smoothest centreline inside the clinical corridor (thicken if needed)."""
    from scipy.spatial import cKDTree
    route = np.array(route, dtype=float)
    tree = cKDTree(band_points)
    factor = np.ones(len(route))
    tangents, normals = _frames(route, band_points, band_normals, tree, radius, step)
    sigma = max(2.5, radius * 1.6) / step
    window = max(1.5, radius * 0.5)
    first = predict(route, tangents, normals, radius * factor, band_points, tree)
    passes = 0
    for passes in range(1, 4):
        for _grow in range(8):
            lower, upper = _corridor(route, tangents, normals, radius * factor, band_points, tree, step)
            infeasible = lower > upper + 1e-6
            if not np.any(infeasible) or factor.max() >= MAX_RADIUS_FACTOR:
                break
            factor = np.minimum(MAX_RADIUS_FACTOR, factor * np.where(infeasible, 1.08, 1.0))
            factor = np.clip(_envelope(factor, step, window, sigma * step), 1.0, MAX_RADIUS_FACTOR)
        # Thickness has priority where the corridor still does not exist.
        upper = np.maximum(upper, lower)
        shift = np.clip(0.0, lower, upper)
        for _ in range(300):
            shift = np.clip(_gaussian(shift, sigma), lower, upper)
        shift = _minimum_bending(shift, lower, upper)
        route = route + normals * shift[:, None]
        if float(np.abs(shift).max()) < TOLERANCE_MM:
            break
    radii = radius * factor
    thickness, embed, supported = predict(route, tangents, normals, radii, band_points, tree)
    fraction = embed / (2.0 * radii)
    valid = supported & np.isfinite(thickness)
    window_support = _circular(np.where(valid, fraction, 0.0), np.max, max(1, int(round(SUPPORT_WINDOW_MM / step))))
    out_of_range = valid & ((thickness < MIN_THICKNESS_MM - TOLERANCE_MM)
                            | (window_support < EMBED_MIN_FRACTION - 0.01)
                            | (fraction > EMBED_MAX_FRACTION + 0.01))
    before = first[2] & np.isfinite(first[0])
    before_fraction = first[1][before] / (2.0 * radius)
    stats = {
        'status': 'OK' if not np.any(out_of_range) else 'REVIEW',
        'stations': int(len(route)),
        'supported_stations': int(valid.sum()),
        'iterations': int(passes),
        'min_thickness_mm': float(thickness[valid].min()) if np.any(valid) else 0.0,
        'min_thickness_before_mm': float(first[0][before].min()) if np.any(before) else 0.0,
        'thin_stations_before': int((first[0][before] < MIN_THICKNESS_MM).sum()),
        'embed_before_min_fraction': float(before_fraction.min()) if len(before_fraction) else 0.0,
        'embed_before_max_fraction': float(before_fraction.max()) if len(before_fraction) else 0.0,
        'embed_min_fraction': float(fraction[valid].min()) if np.any(valid) else 0.0,
        'support_min_fraction': float(window_support[valid].min()) if np.any(valid) else 0.0,
        'embed_max_fraction': float(fraction[valid].max()) if np.any(valid) else 0.0,
        'out_of_range_stations': int(out_of_range.sum()),
        'max_radius_factor': float(factor.max()),
        'band_vertices': int(len(band_points)),
    }
    return route, factor, stats


def optimise(context, surface, route, radius, step):
    try:
        import scipy.spatial  # noqa: F401  (dependency check)
    except ImportError:
        return np.array(route, dtype=float), np.ones(len(route)), {'status': 'SKIPPED_NO_SCIPY'}
    band_points, band_normals = _geodesic_band(context, surface, np.array(route, dtype=float), radius)
    if not len(band_points):
        return np.array(route, dtype=float), np.ones(len(route)), {'status': 'SKIPPED_NO_BAND'}
    return solve(route, band_points, band_normals, radius, step)
