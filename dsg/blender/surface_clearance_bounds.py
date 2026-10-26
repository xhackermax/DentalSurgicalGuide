"""Certified threshold test using the 1-Lipschitz surface-distance function."""
import heapq
import itertools
import numpy as np


def classify(triangles,nearest_distance,margin,tolerance=.02,max_refinements=10000):
    """Bounds the distance over whole faces, including edge/face interiors.

    A centroid sample is an upper bound. Sample minus the triangle's bounding
    radius is a lower bound everywhere on that triangle. Subdivision certifies
    the threshold; an unresolved numerical boundary is blocked conservatively.
    """
    triangles=np.asarray(triangles,dtype=float)
    if triangles.ndim!=3 or triangles.shape[1:]!=(3,3) or not len(triangles) or not np.isfinite(triangles).all():
        raise ValueError('Superficie inválida para medir el margen del nervio.')
    if margin<0 or tolerance<=0:
        raise ValueError('Margen o tolerancia inválidos.')
    heap=[];counter=itertools.count();upper=float('inf')
    def add(triangle):
        nonlocal upper
        center=triangle.mean(axis=0)
        distance=float(nearest_distance(center))
        if not np.isfinite(distance) or distance<0:
            raise ValueError('No se pudo medir la distancia al canal mandibular.')
        upper=min(upper,distance)
        radius=float(np.linalg.norm(triangle-center,axis=1).max())
        heapq.heappush(heap,(max(0.,distance-radius),next(counter),triangle))
    for triangle in triangles:add(triangle)
    for _ in range(max_refinements):
        lower=min(upper,heap[0][0])
        if upper<margin:
            return {'lower_mm':lower,'upper_mm':upper,'status':'BUFFER_INVADED'}
        if lower>margin+tolerance:
            return {'lower_mm':lower,'upper_mm':upper,'status':'SAFE'}
        if upper-lower<=tolerance:
            return {'lower_mm':lower,'upper_mm':upper,'status':'LIMIT'}
        bound,_index,triangle=heapq.heappop(heap)
        if bound>=upper:
            continue
        a,b,c=triangle;ab=(a+b)*.5;bc=(b+c)*.5;ca=(c+a)*.5
        for child in ((a,ab,ca),(ab,b,bc),(ca,bc,c),(ab,bc,ca)):add(np.asarray(child))
    raise RuntimeError('No se pudo verificar la distancia a la estructura protegida; revisa la geometría.')
