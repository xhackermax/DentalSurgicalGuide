"""Continuous IOS-guided exterior design sheet; bridges do not alter the IOS."""
import numpy as np
from mathutils import Vector
from scipy.spatial import ConvexHull,cKDTree
from scipy.ndimage import label as component_label,binary_dilation,distance_transform_edt
from scipy.interpolate import RBFInterpolator
from ..axial_radial_web import axis_basis,distance_fields,build_radial_graph
from ..axial_extrados import height_bounds
from .axial_web_surface import mesh_tree,ray_height,exterior_floor

def outward_tree(v,f):
 t=v[f]
 if np.einsum('ij,ij->i',t[:,0],np.cross(t[:,1],t[:,2])).sum()<0:f=f[:,::-1]
 return mesh_tree(v,f)

def free_floor(tree,p,n,lo,hi,r):
 if lo>hi:return None
 h=hi
 for _ in range(100):
  q=p+n*h;near=tree.find_nearest(Vector(q))
  if not near or near[0]is None:return None
  signed=float((q-np.asarray(near[0]))@np.asarray(near[1]))
  if signed<-.025 or near[3]<r+.045:return None
  gap=float(near[3])-r-.055
  if gap<.012 or h<=lo+1e-6:return h
  h=max(lo,h-.8*gap)
 return None

def generate_sheet_trace(request,progress=print):
 a=np.load(request['surface_file']);iv=np.asarray(a['vertices'],float);it=np.asarray(a['triangles'],int);a.close()
 a=np.load(request['frame_support_file']);fv=np.asarray(a['vertices'],float);ft=np.asarray(a['triangles'],int);a.close()
 n=np.asarray(request['reinforcement_envelope']['frame_entry_axis'],float);n/=np.linalg.norm(n)
 basis=axis_basis(n,np.asarray(request['surface_matrix'])[:3,0]);uv=basis[:,:2];fx=fv@uv
 tri=fv[ft];norm=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]);
 if np.einsum('ij,ij->i',tri[:,0],np.cross(tri[:,1],tri[:,2])).sum()<0:norm=-norm
 lower_frame=mesh_tree(fv,ft[(norm@n)<-.02*np.linalg.norm(norm,axis=1)])
 ios=outward_tree(iv,it);frame=outward_tree(fv,ft);reach=np.linalg.norm(np.ptp(iv,axis=0))+30
 style=request.get('axial_web_style')or{};scale=float(style.get('size_scale',1.));radius=float(request['radius_mm']);root=.65*radius*scale;small=.55*radius*scale;step=.45
 hull=ConvexHull(fx);xx=np.arange(fx[:,0].min(),fx[:,0].max()+step,step);yy=np.arange(fx[:,1].min(),fx[:,1].max()+step,step)
 gx,gy=np.meshgrid(xx,yy);xy=np.column_stack((gx.ravel(),gy.ravel()));inside=np.all(xy@hull.equations[:,:2].T+hull.equations[:,2]<.05,axis=1)
 base=float((iv@n).min()-10);p=xy@uv.T+n*base
 footprint=np.zeros(len(p),bool);fh=np.full(len(p),np.nan);fn=np.zeros(len(p))
 for i in np.flatnonzero(inside):
  hit=ray_height(frame,p[i],n,reach)
  if hit is not None:footprint[i]=True;fh[i]=hit@n;fn[i]=float(np.asarray(frame.find_nearest(Vector(hit))[1])@n)
 holes,count=component_label((inside&~footprint).reshape(gx.shape));sizes=np.bincount(holes.ravel());sizes[0]=0
 if count==0:raise ValueError('NO_FRAME_OPENING')
 opening=holes==sizes.argmax();frame_depth=distance_transform_edt(footprint.reshape(gx.shape))[footprint.reshape(gx.shape)];band=max(root+.4,1.5*float(np.percentile(frame_depth,95))*step);domain=binary_dilation(opening,iterations=int(np.ceil(band/step))).ravel()&inside
 # Fit absolute exterior height to real upper-frame samples and curved-wall ports.
 constraints=[]
 for i in np.flatnonzero(footprint)[::3]:constraints.append((xy[i],fh[i]+root*.65))
 ports={};sleeve_ports={}
 for s in request['sleeves']:
  sid=s['id'];c=np.asarray(s['center'],float);sn=np.asarray(s['entry_axis'],float);sn/=np.linalg.norm(sn);sb=axis_basis(sn,uv[:,0]);h=s['height_mm']*.5-(2.2*radius+.2)
  if h<=-s['height_mm']*.5+radius+.1:raise ValueError('SLEEVE_HAS_NO_SIDEWALL_BAND:'+sid)
  points=[c+sn*h+s['outer_radius_mm']*(sb[:,0]*np.cos(t)+sb[:,1]*np.sin(t))for t in np.linspace(0,2*np.pi,8,endpoint=False)]
  if style.get('frame_smoothing'):
   # The doubled body must also clear anatomy at its fixed sidewall port.
   # Slide only along this sleeve's own axis, staying below its flat cap.
   body=.4*radius*scale;limit=s['height_mm']*.5-body-.15
   for k,q in enumerate(points):
    offset=0.
    while True:
     nearest=ios.find_nearest(Vector(q+sn*offset))
     if nearest and nearest[3]>=body+.15 and float((q+sn*offset-np.asarray(nearest[0]))@np.asarray(nearest[1]))>=0:break
     offset+=.05
     if h+offset>limit:raise ValueError('SLEEVE_PORT_HAS_NO_EXTERIOR_CLEARANCE:'+sid)
    points[k]=q+sn*offset
  sleeve_ports[sid]=points
  constraints.extend((q@uv,float(q@n))for q in points)
  domain&=np.linalg.norm(xy-c@uv,axis=1)>s['outer_radius_mm']+small+.12
 cx=np.asarray([t[0]for t in constraints]);ch=np.asarray([t[1]for t in constraints]);cx,unique=np.unique(cx,axis=0,return_index=True);ch=ch[unique]
 fit=RBFInterpolator(cx,ch,kernel='thin_plate_spline',smoothing=.35,neighbors=min(32,len(cx)));desired=fit(xy)
 guide=None
 if request.get('guide_surface_file'):
  a=np.load(request['guide_surface_file']);guide=outward_tree(a['vertices'],a['triangles']);a.close()
 _,ceiling=height_bounds(p,np.full(len(p),small+.08),n,request['sleeves']);ceiling+=base
 heights=desired.copy();radii=np.full(len(p),small);bridge=np.zeros(len(p),bool)
 progress(f'Construyendo superficie exterior continua: {int(domain.sum())} muestras')
 for i in np.flatnonzero(domain):
  lo=desired[i]-2*radius
  if footprint[i]:lo=max(lo,fh[i]+small+.12)
  if guide is not None:
   hit=ray_height(guide,p[i],n,reach)
   if hit is not None:lo=max(lo,float(hit@n)+small*.3)
  barrier=exterior_floor(lower_frame,p[i],n,lo-base,small+.12,ceiling[i]-base)
  if barrier is None:domain[i]=False;continue
  floor=free_floor(ios,p[i],n,max(lo-base,barrier),ceiling[i]-base,small)
  if floor is None:domain[i]=False;continue
  heights[i]=np.clip(desired[i],floor+base,ceiling[i]);hit=ray_height(ios,p[i],n,reach);bridge[i]=hit is None
 vertices=xy@uv.T+heights[:,None]*n
 w=len(xx);h=len(yy);idx=np.arange(w*h).reshape(h,w);aa=idx[:-1,:-1].ravel();bb=aa+1;cc=aa+w;dd=cc+1
 faces=np.vstack((np.column_stack((aa,bb,dd)),np.column_stack((aa,dd,cc))))
 
 if request.get('design_sheet_debug_file'):np.savez(request['design_sheet_debug_file'],xy=xy,shape=gx.shape,inside=inside,footprint=footprint,domain=domain,heights=heights,ceiling=ceiling,desired=desired,frame_height=fh)
 ids=np.flatnonzero(domain);tree=cKDTree(xy[ids]);sources={}
 for sid,points in sleeve_ports.items():
  sources[sid]=[]
  for q in points:
   _,j=tree.query(q@uv);j=int(ids[j]);sources[sid].append(j);ports[j]=(sid,q)
 _,fields=distance_fields(vertices,faces,domain,sources);sids=sorted(sources);dist=np.array([fields[s][0]for s in sids]);near=dist.min(axis=0);owner=dist.argmin(axis=0)
 rows=[]
 for j in np.flatnonzero(footprint&(fn>.6)):
  point=xy[j]@uv.T+n*(fh[j]+(.55*.4*radius*scale if style.get('frame_smoothing')else root*.65));d,k=tree.query(xy[j]);k=int(ids[k])
  if d>max(1.8,band*.6) or not np.isfinite(near[k]) or near[k]<2.5*radius:continue
  _,hi=height_bounds(point[None,:],np.array([root+.08]),n,request['sleeves'])
  nearest=ios.find_nearest(Vector(point))
  if hi[0]<0 or not nearest or nearest[3]<root+.04:continue
  bottom=lower_frame.find_nearest(Vector(point))
  if bottom is None or bottom[0]is None or bottom[3]<small+.15:continue
  rows.append(dict(vertex=k,point=point,distance=float(near[k]),owner=sids[int(owner[k])]))
 minimum_distal=max(3.*radius,.25*max(r['distance']for r in rows));rows=[r for r in rows if r['distance']>=minimum_distal]
 selected=[];used=set()
 for sid in sids:
  center=np.asarray(next(s for s in request['sleeves']if s['id']==sid)['center'])@uv
  group=[dict(r,distance=float(fields[sid][0][r['vertex']]),target=sid)for r in rows if r['owner']==sid]
  if not group:group=[dict(r,distance=float(fields[sid][0][r['vertex']]),target=sid)for r in rows if np.isfinite(fields[sid][0][r['vertex']])]
  for sector in range(40):
   choices=[r for r in group if int((np.arctan2(*(xy[r['vertex']]-center)[::-1])%(2*np.pi))/(2*np.pi)*40)==sector]
   for r in sorted(choices,key=lambda r:-r['distance']):
    if r['vertex']in used or any(np.linalg.norm(r['point']-q['point'])<2.6*.65*radius for q in selected):continue
    selected.append(r);used.add(r['vertex']);break
 if style.get('target_frame_origins'):
  from ..axial_web_style import sparse_origins
  selected=sparse_origins(selected,int(style['target_frame_origins']))
 starts={f'F{k}':(r['vertex'],r['target'])for k,r in enumerate(selected)}
 progress(f'Trazando radios distales y frentes transversales: {len(starts)} origenes')
 web=build_radial_graph(vertices,faces,domain,sources,starts,spacing=max(1.8,1.9*radius),spread_basis=uv)
 fixed={}
 for label,key in web['frame_nodes'].items():fixed[key]=(selected[int(label[1:])]['point'],.4*radius*scale if style else root,'FRAME',label)
 for key,sid in web['source_nodes'].items():fixed[key]=(ports[int(key.split(':')[1])][1],.4*radius*scale if style else small,'SLEEVE',sid)
 for key,(q,r,kind,target)in fixed.items():web['nodes'][key]=q.tolist()
 for piece in web['pieces']:
  piece['points_mm']=[web['nodes'][k]for k in piece['node_chain']];piece['radius_mm']=(.4*radius if piece['member_role']=='PRIMARY'else .25*radius)*scale
  pr=piece['radius_mm'];piece['point_radii_mm']=[fixed[k][1]if k in fixed else pr for k in piece['node_chain']]
 web['attachments']={k:dict(point_mm=q.tolist(),radius_mm=r,kind=kind,target=target)for k,(q,r,kind,target)in fixed.items()}
 web['style']=style
 web['report'].update(size_scale=scale,reference_frame_origins=style.get('reference_frame_origins'),target_frame_origins=style.get('target_frame_origins'),manual_union_requested=bool(style.get('manual_union')),topology='AXIAL_RADIAL_WEB_V2',reference_method='GEODESIC_DISTANCE_GUIDED_EXTRADOS_PATHS',upper_frame_band_mm=band,design_sheet_vertices=int(domain.sum()),bridge_samples=int(bridge[domain].sum()),exterior_axis=n.tolist(),visual_review='PENDING',mechanics_evaluated=False)
 return web
