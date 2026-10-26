"""Sampled minimum body-radius checks on the final, outward closed skin.

These rays verify the supplied stations and angular directions only; this is
not a continuous thickness certificate or a mechanical assessment.
"""
import math

from mathutils import Vector
from mathutils.bvhtree import BVHTree


def validate_body_radius(vertices, faces, body_points, u_axes, v_axes,
                         nominal_radius_mm, tolerance_mm=.12, radial_samples=16):
    """Fail on an outside center, missing first hit, or excessive body shrink.

    Inputs use one world-space millimetre coordinate system. ``faces`` must be
    outward oriented triangles of the final closed candidate. RMF axes and
    centers must have matching lengths. Returns JSON-serializable evidence.
    """
    radius=float(nominal_radius_mm);tolerance=float(tolerance_mm)
    if (not math.isfinite(radius) or not math.isfinite(tolerance)
            or radius <= 0 or tolerance < 0 or tolerance >= radius
            or radial_samples < 4):
        raise ValueError('ORGANIC_RADIUS_INVALID_PARAMETERS')
    if not len(body_points) or len(body_points)!=len(u_axes) or len(body_points)!=len(v_axes):
        raise ValueError('ORGANIC_RADIUS_INVALID_FRAMES')
    vs=vertices.tolist() if hasattr(vertices,'tolist') else vertices
    fs=faces.tolist() if hasattr(faces,'tolist') else faces
    tree=BVHTree.FromPolygons(vs,fs,all_triangles=True)
    minimum=math.inf;maximum=0.;count=0
    for station,(point,u,v) in enumerate(zip(body_points,u_axes,v_axes)):
        center=Vector(point);u=Vector(u);v=Vector(v)
        if (not all(math.isfinite(x) for vector in (center,u,v) for x in vector)
                or u.length < 1.e-8 or v.length < 1.e-8
                or abs(u.normalized().dot(v.normalized())) > .001):
            raise ValueError('ORGANIC_RADIUS_INVALID_FRAME:'+str(station))
        nearest=tree.find_nearest(center)
        if not nearest or nearest[0] is None or (center-nearest[0]).dot(nearest[1]) > .0001:
            raise ValueError('ORGANIC_RADIUS_CENTER_OUTSIDE:'+str(station))
        for angle_index in range(radial_samples):
            angle=2.*math.pi*angle_index/radial_samples
            direction=(u*math.cos(angle)+v*math.sin(angle)).normalized()
            hit=tree.ray_cast(center,direction)
            if not hit or hit[0] is None or not math.isfinite(hit[3]):
                # A ray exactly in a welded ring plane can hit only shared
                # triangle edges. Retry on either side of that plane (10 nm).
                axial=u.cross(v).normalized();alternatives=[]
                for sign in (-1.,1.):
                    retry=tree.ray_cast(center+axial*(sign*1.e-5),direction)
                    if retry and retry[0] is not None and math.isfinite(retry[3]):alternatives.append(retry)
                if not alternatives:raise ValueError('ORGANIC_RADIUS_MISSING_HIT:'+str(station))
                hit=min(alternatives,key=lambda row:row[3])
            distance=float(hit[3]);minimum=min(minimum,distance);maximum=max(maximum,distance);count+=1
            if distance < radius-tolerance-1.e-5:
                raise ValueError('ORGANIC_RADIUS_EXCESSIVE_SHRINK:'
                                 +str(station)+':'+str(distance)+':'+str(radius-tolerance))
    return {'valid':True,'sampled':True,'station_count':len(body_points),
            'radial_samples_per_station':radial_samples,'ray_count':count,
            'minimum_radial_distance_mm':minimum,'maximum_radial_distance_mm':maximum,
            'nominal_radius_mm':radius,'tolerance_mm':tolerance}
