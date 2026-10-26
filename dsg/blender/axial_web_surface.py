"""Read-only clinical reference extraction and insertion-axis exterior lift."""
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

def mesh_tree(vertices,faces):return BVHTree.FromPolygons(np.asarray(vertices).tolist(),np.asarray(faces).tolist(),all_triangles=True)

def ray_height(tree,point,axis,reach):
 hit=tree.ray_cast(Vector(point+axis*reach),Vector(-axis),2*reach)
 return np.asarray(hit[0],float)if hit and hit[0]is not None else None

def exterior_floor(tree,point,axis,minimum,radius,maximum):
 # Trace down from the free entry-side interval. A lower pocket separated
 # by IOS material is never accepted as an exterior solution.
 if not np.isfinite(maximum):maximum=minimum+100.
 h=float(maximum)
 for _ in range(50):
  near=tree.find_nearest(Vector(point+axis*h))
  if not near or near[0]is None or near[3]<radius+.055:return None
  gap=float(near[3])-radius-.06
  if gap<.018:return h
  next_h=max(float(minimum),h-.9*gap)
  if h-next_h<1e-6:return h
  h=next_h
 return h
