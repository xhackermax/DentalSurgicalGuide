"""Insertion-axis exterior placement, independent of world Z."""
import numpy as np

def height_bounds(points,radii,axis,sleeves):
 points=np.asarray(points,float);radii=np.broadcast_to(np.asarray(radii,float),len(points));axis=np.asarray(axis,float);axis=axis/np.linalg.norm(axis)
 lower=radii+.15;upper=np.full(len(points),np.inf)
 for sleeve in sleeves:
  n=np.asarray(sleeve['entry_axis'],float);n/=np.linalg.norm(n);dot=float(axis@n);bound=float(sleeve['height_mm'])*.5-.05-radii-(points-np.asarray(sleeve['center']))@n
  if dot>1e-8:upper=np.minimum(upper,bound/dot)
  elif dot< -1e-8:lower=np.maximum(lower,bound/dot)
  elif np.any(bound<0):raise ValueError('NO_EXTERIOR_SPACE:'+sleeve['id'])
 return lower,upper

def lift_offsets(points,offsets,radii,axis,sleeves):
 points=np.asarray(points,float);axis=np.asarray(axis,float);axis/=np.linalg.norm(axis);lower,upper=height_bounds(points,radii,axis,sleeves)
 if np.any(lower>upper):raise ValueError('NO_EXTERIOR_SPACE')
 height=np.clip(np.asarray(offsets,float),lower,upper);return points+height[:,None]*axis
