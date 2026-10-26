"""Implicit shared-node web: exact variable-radius capsules, bounded surface extraction."""
import numpy as np
import bpy,bmesh
from scipy.ndimage import gaussian_filter
from skimage.measure import marching_cubes
from ..axial_capsule import capsule_sdf

def clean_volume_mesh(mesh,step):
 # Marching cubes can produce numerically coincident grid-corner vertices.
 # Contract their sub-micron edges before the independent closed-solid gate.
 bm=bmesh.new();bm.from_mesh(mesh);bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=.0001);bmesh.ops.dissolve_degenerate(bm,edges=list(bm.edges),dist=.0001);bmesh.ops.triangulate(bm,faces=list(bm.faces));bm.to_mesh(mesh);bm.free();mesh.update()
 from ..guide_export.mesh_checks import connected_components
 coords=np.array([v.co[:]for v in mesh.vertices]);mesh.calc_loop_triangles();triangles=np.array([t.vertices[:]for t in mesh.loop_triangles]);labels=connected_components(len(coords),triangles);ids,counts=np.unique(labels,return_counts=True);remove=[]
 for component,count in zip(ids,counts):
  members=np.flatnonzero(labels==component)
  if count<.001*len(coords)and np.ptp(coords[members],axis=0).max()<4*step:remove.extend(members.tolist())
 if remove:
  bm=bmesh.new();bm.from_mesh(mesh);bm.verts.ensure_lookup_table();bmesh.ops.delete(bm,geom=[bm.verts[i]for i in remove],context='VERTS');bm.to_mesh(mesh);bm.free();mesh.update()
 return mesh

def build_implicit_volume(context,web,name):
 samples=np.vstack([np.asarray(p['points_mm'])for p in web['pieces']]);rmax=max(max(p['point_radii_mm'])for p in web['pieces']);rmin=min(min(p['point_radii_mm'])for p in web['pieces']);fair=bool(web.get('style',{}).get('surface_fairing'));step=min(.075 if fair else .06,rmin/5.)
 band=4*.85*rmin+4*step if fair else 4*step
 low=np.floor((samples.min(axis=0)-rmax-band)/step)*step;high=samples.max(axis=0)+rmax+band;shape=np.ceil((high-low)/step).astype(int)+1
 if np.prod(shape)>100_000_000:raise ValueError('AXIAL_VOLUME_GRID_TOO_LARGE')
 field=np.full(tuple(shape),band,np.float32)
 for piece in web['pieces']:
  points=np.asarray(piece['points_mm']);radii=piece['point_radii_mm']
  for a,b,ra,rb in zip(points,points[1:],radii,radii[1:]):
   pad=max(ra,rb)+band;start=np.maximum(0,np.floor((np.minimum(a,b)-pad-low)/step).astype(int));stop=np.minimum(shape,np.ceil((np.maximum(a,b)+pad-low)/step).astype(int)+1)
   if np.any(stop<=start):continue
   ranges=[np.arange(start[i],stop[i])*step+low[i]for i in range(3)];grid=np.stack(np.meshgrid(*ranges,indexing='ij'),axis=-1);sdf=capsule_sdf(grid,a,b,ra,rb).astype(np.float32);region=tuple(slice(int(s),int(e))for s,e in zip(start,stop));np.minimum(field[region],sdf,out=field[region])
 # A sub-voxel fairing removes extraction ridges; the independent continuous
 # section validator measures the final mesh, including any resulting loss.
 if fair:
  from ..axial_surface_fairing import fair_union_field
  field=fair_union_field(field,step,rmin)
  web['report'].update(surface_fairing='ONE_SIDED_HEAT_FAIRING',surface_fairing_scale_mm=.85*rmin,original_strut_envelope_preserved=True,pn_loop_implementation=False)
 else:gaussian_filter(field,sigma=.45,output=field,mode='nearest',truncate=2.)
 vertices,faces,_normals,_values=marching_cubes(field,level=0.,spacing=(step,)*3,gradient_direction='ascent',allow_degenerate=False);vertices+=low
 del field,_normals,_values
 mesh=bpy.data.meshes.new(name);mesh.from_pydata(vertices.tolist(),[],faces.tolist());mesh.update()
 clean_volume_mesh(mesh,step)
 obj=bpy.data.objects.new(name,mesh);context.scene.collection.objects.link(obj);obj['DSG_axial_voxel_size_mm']=step;obj['DSG_axial_volume_method']='EXACT_VARIABLE_RADIUS_CAPSULE_UNION';return obj
