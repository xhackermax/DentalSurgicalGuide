"""Adaptive Catmull-Bezier tube, preserving the solved surface route and radius."""
import numpy as np
from mathutils import Vector

from .organic_curve import adaptive_controls, smooth_route


def build(context, points, radius, name, bevel_resolution=8, cyclic=True, anchors=(), surface=None):
    from .. import guide_module as g
    if not cyclic:
        raise ValueError('El frame orgánico requiere un contorno cerrado.')
    route, deviation = smooth_route(points, g.get_insertion_axis(), radius)
    factor = np.ones(len(route))
    embed_stats = {'status': 'NOT_EVALUATED'}
    if surface is not None:
        # Predict the final Boolean on geodesic cross-sections and keep the
        # embed/thickness within the clinical limits (smooth correction).
        from . import frame_embed
        step = float(np.mean(np.linalg.norm(np.roll(route, -1, axis=0) - route, axis=1)))
        route, factor, embed_stats = frame_embed.optimise(context, surface, route, float(radius), step)
    # The clicked anchors follow the smoothed line (they move < 45 % radius).
    anchor_points = [route[int(np.argmin(np.linalg.norm(route - np.asarray(tuple(a)), axis=1)))]
                     for a in anchors]
    tolerance = min(.25, max(.05, float(radius)*.10))
    controls, left, right, stats = adaptive_controls(
        [tuple(p) for p in route], anchors=anchor_points,
        spacing=max(1.5, min(4.0, float(radius)*1.0)), tolerance=tolerance)
    obj = g.create_bezier_curve_object(context, name, [Vector(p) for p in controls],
                                       bevel_radius=float(radius),
                                       bevel_resolution=max(12, int(bevel_resolution)), cyclic=True)
    spline = obj.data.splines[0]
    for i, bp in enumerate(spline.bezier_points):
        bp.handle_left_type = 'FREE'
        bp.handle_right_type = 'FREE'
        bp.handle_left, bp.handle_right = Vector(left[i]), Vector(right[i])
        nearest = int(np.argmin(np.linalg.norm(route - np.asarray(controls[i]), axis=1)))
        bp.radius = float(factor[nearest])
    obj.data.resolution_u = 12
    obj.data.render_resolution_u = 12
    result = g.convert_curve_to_mesh(context, obj, name)
    for polygon in result.data.polygons:
        polygon.use_smooth = True
    result['DSG_frame_visible_sweep'] = 'SMOOTHED_CENTRIPETAL_CATMULL_BEZIER_V3'
    result['DSG_frame_smoothing_max_offset_mm'] = deviation
    result['DSG_frame_visible_control_count'] = len(controls)
    result['DSG_frame_curve_tolerance_mm'] = tolerance
    result['DSG_frame_curve_max_deviation_mm'] = stats['max_route_deviation_mm']
    result['DSG_frame_curve_length_mm'] = stats['curve_length_mm']
    result['DSG_frame_uniform_radius_mm'] = float(radius)
    result['DSG_frame_embed_status'] = str(embed_stats.get('status', ''))
    for key in ('min_thickness_mm', 'min_thickness_before_mm', 'thin_stations_before', 'embed_min_fraction',
                'embed_max_fraction', 'support_min_fraction', 'out_of_range_stations', 'max_radius_factor',
                'stations', 'iterations'):
        if key in embed_stats:
            result['DSG_frame_embed_' + key] = embed_stats[key]
    return result
