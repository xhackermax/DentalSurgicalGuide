"""Hard geometric limits for automatic reinforcements in clinical coordinates."""
import numpy as np

POLICY='FRAME_ABOVE_SIDEWALL_ONLY_V1'
CLEARANCE_MM=.05

def _sleeves(request):
 for sleeve in request['sleeves']:
  axis=np.asarray(sleeve['axis'],float);entry=np.asarray(sleeve['entry_axis'],float)
  if not np.isfinite(axis).all() or not np.isfinite(entry).all() or min(np.linalg.norm(axis),np.linalg.norm(entry))<1.e-9:
   raise ValueError('INVALID_CLINICAL_ENVELOPE_AXIS')
  yield sleeve,np.asarray(sleeve['center'],float),axis/np.linalg.norm(axis),entry/np.linalg.norm(entry)

def _clip(poly,axis,bound,above):
 if not len(poly):return []
 output=[]
 for first,second in zip(poly,[*poly[1:],poly[0]]):
  a=float(np.dot(first,axis)-bound);b=float(np.dot(second,axis)-bound)
  inside_a=a>=0 if above else a<=0;inside_b=b>=0 if above else b<=0
  if inside_a:output.append(first)
  if inside_a!=inside_b:output.append(first+(second-first)*(a/(a-b)))
 return output

def _disk_overlap(poly,axis,radius):
 if not len(poly):return False
 projected=np.asarray(poly);projected=projected-np.outer(projected@axis,axis)
 if np.min(np.linalg.norm(projected,axis=1))<=radius:return True
 for a,b in zip(projected,np.roll(projected,-1,axis=0)):
  delta=b-a;t=np.clip(-float(a@delta)/max(float(delta@delta),1.e-20),0.,1.)
  if np.linalg.norm(a+t*delta)<=radius:return True
 if len(projected)>=3:
  # The disk center can lie inside a large projected triangle even when all
  # vertices and edges remain outside the disk.
  from .frame_optimizer import _kernel
  for i in range(1,len(projected)-1):
   _,distance2=_kernel().closest_point_on_triangle(np.zeros(3),projected[0],projected[i],projected[i+1])
   if distance2<=radius*radius:return True
 return False

def validate_path_envelope(points,radius_mm,request,*,frame_projection_distance_mm=None,frame_end_projection_distance_mm=None):
 """Conservative capsule check, including segment interiors and tube radius."""
 if not request.get('reinforcement_envelope'):return {'valid':True,'legacy':True}
 points=np.asarray(points,float);radius=float(radius_mm)
 if points.ndim!=2 or points.shape[1]!=3 or len(points)<2 or not np.isfinite(points).all() or not np.isfinite(radius) or radius<=0:raise ValueError('INVALID_ENVELOPE_PATH')
 for sleeve,center,axis,entry in _sleeves(request):
  local=points-center;half=float(sleeve['height_mm'])*.5
  if float(np.max(local@entry))+radius>half-CLEARANCE_MM+1.e-8:raise ValueError('REINFORCEMENT_ABOVE_SLEEVE:'+sleeve['id'])
  for cap in (-half,half):
   for a,b in zip(local,local[1:]):
    poly=_clip([a,b],axis,cap-radius-CLEARANCE_MM,True)
    poly=_clip(poly,axis,cap+radius+CLEARANCE_MM,False)
    if _disk_overlap(poly,axis,float(sleeve['outer_radius_mm'])+radius):raise ValueError('REINFORCEMENT_SLEEVE_FLAT_FACE:'+sleeve['id'])
 if request.get('frame_lower_surface_file'):
  body=points
  if frame_projection_distance_mm is not None or frame_end_projection_distance_mm is not None:
   # The terminal section is a Coons collar, not the virtual circular tube.
   # Its complete final mesh is checked independently against the lower frame.
   from .generative_frame_worker import central_ios_body
   body,_=central_ios_body(points,frame_projection_distance_mm or 0.,frame_end_projection_distance_mm or 0.,radius)
  if not frame_barrier(request['frame_lower_surface_file']).clear(body,radius+CLEARANCE_MM):raise ValueError('REINFORCEMENT_TOUCHES_LOWER_FRAME_SURFACE')
 return {'valid':True,'policy':POLICY,'full_tube_radius_checked':True}

def validate_mesh_envelope(vertices,faces,request):
 """Check final triangles, including collars and face-interior cap crossings."""
 if not request.get('reinforcement_envelope'):return {'valid':True,'legacy':True}
 vertices=np.asarray(vertices,float);faces=np.asarray(faces,int)
 if vertices.ndim!=2 or vertices.shape[1]!=3 or not len(vertices) or not np.isfinite(vertices).all() or faces.ndim!=2 or faces.shape[1]!=3 or not len(faces):raise ValueError('INVALID_ENVELOPE_MESH')
 for sleeve,center,axis,entry in _sleeves(request):
  local=vertices-center;half=float(sleeve['height_mm'])*.5
  if float(np.max(local@entry))>half-CLEARANCE_MM+1.e-8:raise ValueError('REINFORCEMENT_ABOVE_SLEEVE:'+sleeve['id'])
  triangles=local[faces];axial=triangles@axis
  for cap in (-half,half):
   candidates=np.flatnonzero((axial.min(axis=1)<=cap+CLEARANCE_MM)&(axial.max(axis=1)>=cap-CLEARANCE_MM))
   for i in candidates:
    poly=_clip(list(triangles[i]),axis,cap-CLEARANCE_MM,True)
    poly=_clip(poly,axis,cap+CLEARANCE_MM,False)
    if _disk_overlap(poly,axis,float(sleeve['outer_radius_mm'])+CLEARANCE_MM):raise ValueError('REINFORCEMENT_SLEEVE_FLAT_FACE:'+sleeve['id'])
 return {'valid':True,'policy':POLICY,'final_triangles_checked':True,'flat_faces_clear':True}

def upper_frame_vertex_mask(vertices,faces,entry_axis):
 vertices=np.asarray(vertices,float);faces=np.asarray(faces,int);axis=np.asarray(entry_axis,float);axis/=np.linalg.norm(axis)
 triangles=vertices[faces];normals=np.cross(triangles[:,1]-triangles[:,0],triangles[:,2]-triangles[:,0]);length=np.linalg.norm(normals,axis=1)
 selected=(normals@axis)>.1*np.maximum(length,1.e-20)
 mask=np.zeros(len(vertices),bool);mask[faces[selected].ravel()]=True
 return mask

class FrameLowerSurfaceBarrier:
 """An oriented surface barrier, deliberately distinct from closed keepouts."""
 def __init__(self,vertices,faces):
  from scipy.spatial import cKDTree
  from .frame_optimizer import _kernel
  vertices=np.asarray(vertices,float);faces=np.asarray(faces,int)
  if vertices.ndim!=2 or vertices.shape[1]!=3 or not np.isfinite(vertices).all() or faces.ndim!=2 or faces.shape[1]!=3 or not len(faces) or faces.min()<0 or faces.max()>=len(vertices):raise ValueError('INVALID_FRAME_SURFACE_BARRIER')
  self.triangles=vertices[faces];self.low=self.triangles.min(axis=1);self.high=self.triangles.max(axis=1);self.kernel=_kernel()
  centers=self.triangles.mean(axis=1);radii=np.linalg.norm(self.triangles-centers[:,None,:],axis=2).max(axis=1);bins=np.floor(np.log2(np.maximum(radii,1.e-6))).astype(int)
  self.buckets=[]
  for label in np.unique(bins):
   ids=np.flatnonzero(bins==label);self.buckets.append((ids,cKDTree(centers[ids]),float(radii[ids].max())))
 def near(self,point,radius):
  point=np.asarray(point,float)
  for ids,tree,extent in self.buckets:
   rows=tree.query_ball_point(point,radius+extent+1.e-8)
   for row in rows:
    if self.kernel.closest_point_on_triangle(point,*self.triangles[ids[row]])[1]<=radius*radius:return True
  return False
 def clear(self,points,radius):
  points=np.asarray(points,float);radius=float(radius)
  if points.ndim!=2 or points.shape[1]!=3 or len(points)<2 or not np.isfinite(points).all() or not np.isfinite(radius) or radius<=0:raise ValueError('INVALID_FRAME_BARRIER_SWEEP')
  for a,b in zip(points,points[1:]):
   middle=(a+b)*.5;half=np.linalg.norm(b-a)*.5;low=np.minimum(a,b)-radius;high=np.maximum(a,b)+radius
   for ids,tree,extent in self.buckets:
    rows=tree.query_ball_point(middle,half+radius+extent+1.e-8)
    selected=ids[np.asarray(rows,int)];selected=selected[np.all(self.high[selected]>=low,axis=1)&np.all(self.low[selected]<=high,axis=1)]
    for tri in self.triangles[selected]:
     if self.kernel._segment_triangle_hit(a,b,tri):return False
     distance=min(self.kernel.closest_point_on_triangle(a,*tri)[1],self.kernel.closest_point_on_triangle(b,*tri)[1])
     for c,d in zip(tri,np.roll(tri,-1,axis=0)):distance=min(distance,self.kernel.closest_points_segments(a,b,c,d)[2])
     if distance<=radius*radius+1.e-12:return False
  return True
 def steering_penalty(self,points,radius):
  # Steering is sampled; the independent segment sweep is authoritative.
  return np.asarray([1000. if self.near(p,radius+.05) else 0. for p in points])

from functools import lru_cache
@lru_cache(maxsize=4)
def frame_barrier(path):
 data=np.load(path,allow_pickle=False)
 return FrameLowerSurfaceBarrier(data['vertices'],data['triangles'])
