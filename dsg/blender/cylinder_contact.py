"""Intersection of mesh triangles with a closed finite cylinder in local mm."""
import numpy as np


def clip_z(polygon, bound, below):
    result = []
    for a, b in zip(polygon, np.roll(polygon, -1, axis=0)):
        inside_a = a[2] <= bound if below else a[2] >= bound
        inside_b = b[2] <= bound if below else b[2] >= bound
        if inside_a:
            result.append(a)
        if inside_a != inside_b:
            result.append(a + (b-a)*((bound-a[2])/(b[2]-a[2])))
    return np.asarray(result)


def intersects(vertices, triangles, radius, half_height, epsilon=1e-6):
    vertices = np.asarray(vertices, dtype=float)
    tris = np.asarray(triangles, dtype=int)
    if radius <= 0 or half_height <= 0 or not np.isfinite(vertices).all():
        raise ValueError('Geometría inválida en la protección cilíndrica.')
    if not len(tris):
        raise ValueError('La malla de seguridad no contiene triángulos.')
    r, h = radius+epsilon, half_height+epsilon
    p = vertices[tris]
    low, high = p.min(axis=1), p.max(axis=1)
    mask = ((low[:,2] <= h) & (high[:,2] >= -h)
            & (low[:,0] <= r) & (high[:,0] >= -r)
            & (low[:,1] <= r) & (high[:,1] >= -r))
    # Most dental faces are fully between the end caps: test these together.
    candidates = p[mask]
    inside_caps = np.all(np.abs(candidates[:,:,2]) <= h, axis=1)
    xy = candidates[inside_caps,:,:2]
    following = np.roll(xy, -1, axis=1)
    delta = following-xy
    t = np.clip(-np.sum(xy*delta, axis=2)/np.maximum(np.sum(delta*delta,axis=2),1e-20),0,1)
    nearest = xy+t[:,:,None]*delta
    if np.any(np.sum(nearest*nearest,axis=2) <= r*r):
        return True
    cross = xy[:,:,0]*following[:,:,1]-xy[:,:,1]*following[:,:,0]
    if np.any((np.abs(np.sum(cross,axis=1)) > epsilon) & (np.all(cross >= -epsilon,axis=1) | np.all(cross <= epsilon,axis=1))):
        return True
    # Only faces crossing a cap need polygon clipping.
    for triangle in candidates[~inside_caps]:
        poly = clip_z(triangle, h, True)
        if len(poly) < 3:
            continue
        poly = clip_z(poly, -h, False)
        if len(poly) < 3:
            continue
        xy = poly[:,:2]
        following = np.roll(xy, -1, axis=0)
        delta = following-xy
        t = np.clip(-np.sum(xy*delta, axis=1)/np.maximum(np.sum(delta*delta, axis=1), 1e-20), 0, 1)
        nearest = xy+t[:,None]*delta
        if np.min(np.sum(nearest*nearest, axis=1)) <= r*r:
            return True
        cross = xy[:,0]*following[:,1]-xy[:,1]*following[:,0]
        if abs(float(np.sum(cross))) > epsilon and (np.all(cross >= -epsilon) or np.all(cross <= epsilon)):
            return True
    return False
