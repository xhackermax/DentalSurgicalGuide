"""Upper-frame origins and final contact checks for automatic lattice bars."""
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree


def upper_frame_origins(context,frame,ctx,project,folder,radius):
 from .. import guide_module as g
 from ..reinforcement_envelope import upper_frame_vertex_mask,CLEARANCE_MM
 from ..guide_export.mesh_checks import signed_volume_mm3
 from .generative_frame import _export_mesh
 entry=-np.asarray(g.get_insertion_axis(),float);entry/=np.linalg.norm(entry)
 vertices,faces=_export_mesh(context,frame)
 if signed_volume_mm3(vertices,faces)<0:faces=faces[:,::-1]
 np.savez(folder/'frame_support.npz',vertices=vertices,triangles=faces)
 triangles=vertices[faces];normals=np.cross(triangles[:,1]-triangles[:,0],triangles[:,2]-triangles[:,0])
 lower=(normals@entry)<-.02*np.linalg.norm(normals,axis=1)
 if not np.any(lower):raise ValueError('FRAME_LOWER_SURFACE_UNVERIFIABLE')
 np.savez(folder/'frame_lower_surface.npz',vertices=vertices,triangles=faces[lower])
 tree=BVHTree.FromPolygons(vertices.tolist(),faces.tolist(),all_triangles=True)
 reach=float(np.linalg.norm(np.ptp(vertices,axis=0)))+1.
 allowed=upper_frame_vertex_mask(vertices,faces,entry)
 def below_entry(point):
  for sleeve in ctx['sleeves']:
   implant=__import__('bpy').data.objects.get(sleeve['implant_name'])
   axis=np.asarray(sleeve['axis'],float)*g.get_sleeve_occlusal_sign(context.scene.dsg_props,implant)
   if (point-np.asarray(sleeve['center']))@axis+1.25*radius>float(sleeve['height_mm'])*.5-CLEARANCE_MM:return False
  return True
 supports=[]
 for row in ctx['support_nodes']:
  start=np.asarray(row['xyz'],float)+entry*reach
  hit=tree.ray_cast(Vector(start),Vector(-entry),reach*2.)
  if not hit or hit[0] is None or np.asarray(hit[1])@entry<.1 or not below_entry(np.asarray(hit[0])):continue
  try:anchor=project(row['id'],hit[0],max(1.,2.5*ctx['frame_radius_mm']))
  except ValueError:continue
  anchor.update(origin_source='SEMANTIC_UPPER_FRAME_SURFACE',frame_entry_axis=entry.tolist(),upper_frame_surface=True);supports.append(anchor)
 points,indices=np.unique(vertices,axis=0,return_index=True);allowed=allowed[indices]
 allowed&=np.asarray([below_entry(point) for point in points])
 distance=np.where(allowed,np.inf,-np.inf)
 spacing=max(2.5,2.*float(ctx['frame_radius_mm']))
 for row in supports:distance=np.minimum(distance,np.sum((points-np.asarray(row['original_mm']))**2,axis=1))
 rejected=0;sampled=0;attempts=0
 while len(supports)<24 and len(distance) and attempts<256:
  attempts+=1;index=int(np.argmax(distance))
  if distance[index]<spacing**2:break
  point=points[index];distance[index]=-np.inf
  near=tree.find_nearest(Vector(point))
  if not near or near[0] is None or np.asarray(near[1])@entry<.1:rejected+=1;continue
  try:row=project('F'+str(sampled+1).zfill(3),point,max(1.,2.5*ctx['frame_radius_mm']))
  except ValueError:rejected+=1;continue
  row.update(origin_source='PRESERVED_UPPER_FRAME_MESH',frame_vertex_index=int(indices[index]),frame_entry_axis=entry.tolist(),upper_frame_surface=True)
  supports.append(row);sampled+=1;distance=np.minimum(distance,np.sum((points-point)**2,axis=1))
 if len(supports)<2:raise ValueError('FRAME_UPPER_SURFACE_HAS_TOO_FEW_VALID_ORIGINS')
 return supports,spacing,rejected,sampled,attempts,entry.tolist()


def validate_upper_frame_contact(vertices,faces,frame_vertices,frame_faces,entry_axis):
 """Reject any exact crossing of the frame's lower-facing surface."""
 from .sleeve_attachment import _segment_triangle
 from ..guide_export.mesh_checks import signed_volume_mm3
 frame_vertices=np.asarray(frame_vertices,float);frame_faces=np.asarray(frame_faces,int)
 if signed_volume_mm3(frame_vertices,frame_faces)<0:frame_faces=frame_faces[:,::-1]
 axis=np.asarray(entry_axis,float);axis/=np.linalg.norm(axis)
 first=np.asarray(vertices,float)[np.asarray(faces,int)];second=frame_vertices[frame_faces]
 tree=BVHTree.FromPolygons(np.asarray(vertices).tolist(),np.asarray(faces).tolist(),all_triangles=True)
 frame_tree=BVHTree.FromPolygons(frame_vertices.tolist(),frame_faces.tolist(),all_triangles=True)
 contacts=0
 for ia,ib in tree.overlap(frame_tree):
  a,b=first[ia],second[ib];normal=np.cross(b[1]-b[0],b[2]-b[0])
  hit=any(_segment_triangle(x,y,other) is not None for tri,other in ((a,b),(b,a)) for x,y in zip(tri,np.roll(tri,-1,axis=0)))
  if not hit:continue
  if normal@axis < -.02*np.linalg.norm(normal):raise ValueError('REINFORCEMENT_TOUCHES_LOWER_FRAME_SURFACE')
  if normal@axis>.1*np.linalg.norm(normal):contacts+=1
 return {'valid':True,'lower_frame_surface_clear':True,'upper_surface_crossings':contacts}

def verify_context_envelope(context,request):
 if not request.get('reinforcement_envelope'):return
 import bpy
 from .. import guide_module as g
 axis=-np.asarray(g.get_insertion_axis(),float);axis/=np.linalg.norm(axis)
 if not np.allclose(axis,request['reinforcement_envelope']['frame_entry_axis'],atol=1.e-7,rtol=0):raise ValueError('STALE_ENVELOPE: cambio el eje de entrada del frame.')
 for sleeve in request['sleeves']:
  implant=bpy.data.objects.get(sleeve['implant_name'])
  current=np.asarray(sleeve['axis'],float)*g.get_sleeve_occlusal_sign(context.scene.dsg_props,implant)
  if not np.allclose(current,sleeve['entry_axis'],atol=1.e-7,rtol=0):raise ValueError('STALE_ENVELOPE: cambio la entrada del sleeve.')
