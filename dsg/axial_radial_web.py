"""Shared radial/level-set graph on an immutable IOS reference mesh."""
import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra

def axis_basis(axis,preferred=None):
 n=np.asarray(axis,float);length=np.linalg.norm(n)
 if not np.isfinite(n).all()or length<1e-12:raise ValueError('INVALID_INSERTION_AXIS')
 n=n/length
 if preferred is not None:
  u=np.asarray(preferred,float);u=u-n*float(u@n)
 else:u=np.cross(n,np.eye(3)[int(np.argmin(abs(n)))])
 if np.linalg.norm(u)<1e-10:u=np.cross(n,np.eye(3)[int(np.argmin(abs(n)))])
 u/=np.linalg.norm(u);return np.column_stack((u,np.cross(n,u),n))

def distance_fields(vertices,faces,allowed,sources):
 vertices=np.asarray(vertices,float);faces=np.asarray(faces,int);allowed=np.asarray(allowed,bool)
 edges=np.unique(np.sort(np.vstack((faces[:,[0,1]],faces[:,[1,2]],faces[:,[2,0]])),axis=1),axis=0);edges=edges[allowed[edges].all(axis=1)]
 lengths=np.linalg.norm(vertices[edges[:,0]]-vertices[edges[:,1]],axis=1);src=np.r_[edges[:,0],edges[:,1]];dst=np.r_[edges[:,1],edges[:,0]]
 graph=csr_matrix((np.r_[lengths,lengths],(src,dst)),shape=(len(vertices),len(vertices)))
 result={}
 for sid,ids in sorted(sources.items()):
  ids=np.unique(np.asarray(ids,int));ids=ids[allowed[ids]]
  if not len(ids):raise ValueError('MISSING_SLEEVE_SOURCE:'+sid)
  dist,pred,root=dijkstra(graph,directed=False,indices=ids,min_only=True,return_predecessors=True)
  dist[~allowed]=np.inf;result[sid]=(dist,pred,root)
 return graph,result

def build_radial_graph(vertices,faces,allowed,sources,starts,*,spacing,spread_basis=None):
 vertices=np.asarray(vertices,float);faces=np.asarray(faces,int);allowed=np.asarray(allowed,bool)
 if spacing<=0:raise ValueError('INVALID_CELL_SPACING')
 graph,fields=distance_fields(vertices,faces,allowed,sources);sids=sorted(fields);stack=np.array([fields[s][0]for s in sids]);distance=stack.min(axis=0);owner=stack.argmin(axis=0)
 nodes={};edges={};frame_nodes={};source_nodes={};radial_nodes=set();level_nodes=set();used=set();routes=[];covered_vertices=set()
 finite=distance[np.isfinite(distance)&allowed]
 if not len(finite):raise ValueError('EMPTY_REFERENCE_REGION')
 levels=np.arange(spacing*.65,float(finite.max())+1e-8,spacing)
 def vertex(i):
  key='V:'+str(int(i));nodes.setdefault(key,vertices[int(i)].tolist());return key
 def crossing(a,b,k):
  a,b=sorted((int(a),int(b)));key=f'I:{k}:{a}:{b}'
  if key not in nodes:
   t=(levels[k]-distance[a])/(distance[b]-distance[a]);nodes[key]=(vertices[a]+t*(vertices[b]-vertices[a])).tolist()
  return key
 def edge(a,b,role):
  if a==b:return
  key=tuple(sorted((a,b)))
  if key not in edges or role=='PRIMARY':edges[key]=role
 for label,start in sorted(starts.items()):
  pinned=None
  if isinstance(start,(tuple,list)):start,pinned=start
  start=int(start)
  if not allowed[start]or not np.isfinite(distance[start]):continue
  sid=pinned or sids[int(owner[start])]
  if sid not in fields or not np.isfinite(fields[sid][0][start]):raise ValueError('UNREACHABLE_PINNED_SLEEVE:'+str(sid))
  dist,pred,root=fields[sid];chain=[start];current=start
  if spread_basis is not None:
   projected=vertices@np.asarray(spread_basis);center=projected[np.asarray(sources[sid],int)].mean(axis=0);direction=projected[start]-center;direction/=max(np.linalg.norm(direction),1e-9)
  while int(pred[current])>=0:
   nxt=int(pred[current])
   if spread_basis is not None:
    neighbors=graph.indices[graph.indptr[current]:graph.indptr[current+1]];neighbors=neighbors[dist[neighbors]<dist[current]-1e-9]
    if len(neighbors):
     delta=projected[neighbors]-center;unit=delta/np.maximum(np.linalg.norm(delta,axis=1)[:,None],1e-9);angle=1-unit@direction
     nxt=int(neighbors[np.argmin(angle*20.+dist[neighbors]*.015)])
   if dist[nxt]>=dist[current]-1e-10:raise ValueError('RADIAL_DISTANCE_NOT_DECREASING')
   chain.append(nxt);current=nxt
   if len(chain)>len(vertices):raise ValueError('RADIAL_PREDECESSOR_CYCLE')
  if current not in set(map(int,sources[sid])):raise ValueError('RADIAL_MISSING_SLEEVE_ENDPOINT')
  used.add(sid);frame_nodes[label]=vertex(start);source_nodes[vertex(current)]=sid;route=[vertex(start)];covered_vertices.update(chain)
  for a,b in zip(chain,chain[1:]):
   low,high=sorted((distance[a],distance[b]));ks=np.flatnonzero((levels>low+1e-9)&(levels<high-1e-9))
   mids=sorted((crossing(a,b,int(k))for k in ks),key=lambda key:np.linalg.norm(np.asarray(nodes[key])-vertices[a]))
   route.extend(mids+[vertex(b)])
  for a,b in zip(route,route[1:]):edge(a,b,'PRIMARY')
  radial_nodes.update(route);routes.append(dict(frame=label,sleeve=sid,nodes=route,length_mm=float(np.linalg.norm(np.diff(vertices[chain],axis=0),axis=1).sum()),shortest_distance_mm=float(dist[start])))
 if used!=set(sources):raise ValueError('UNCONNECTED_SLEEVE:'+','.join(sorted(set(sources)-used)))
 good=allowed[faces].all(axis=1)&np.isfinite(distance[faces]).all(axis=1)
 valid_faces=faces[good];d=distance[valid_faces]
 for k,level in enumerate(levels):
  selected=valid_faces[(d.min(axis=1)<level-1e-9)&(d.max(axis=1)>level+1e-9)]
  for triangle in selected:
   hits=[]
   for a,b in zip(triangle,np.roll(triangle,-1)):
    if (distance[a]-level)*(distance[b]-level)<0:hits.append(crossing(a,b,k));covered_vertices.update((int(a),int(b)))
   if len(hits)==2:edge(*hits,'SECONDARY');level_nodes.update(hits)
 adjacency={}
 for a,b in edges:adjacency.setdefault(a,set()).add(b);adjacency.setdefault(b,set()).add(a)
 reached=set();pending=list(radial_nodes)
 while pending:
  node=pending.pop()
  if node in reached:continue
  reached.add(node);pending.extend(adjacency.get(node,set())-reached)
 edges={key:role for key,role in edges.items()if set(key)<=reached};nodes={k:p for k,p in nodes.items()if k in reached}
 adjacency={k:neighbors&reached for k,neighbors in adjacency.items()if k in reached}
 # Truncate transverse ends at the nearest real radial junction. Never return
 # an unattached level-set stub at the cropped design boundary.
 pending=[n for n,adj in adjacency.items()if len(adj)==1 and n not in radial_nodes]
 while pending:
  node=pending.pop()
  if node not in adjacency or len(adjacency[node])!=1 or node in radial_nodes:continue
  other=next(iter(adjacency[node]));edges.pop(tuple(sorted((node,other))),None);adjacency[other].remove(node);adjacency.pop(node);nodes.pop(node,None)
  if len(adjacency[other])==1:pending.append(other)
 terminals={n for n,adj in adjacency.items()if len(adj)!=2}|set(frame_nodes.values())|set(source_nodes)
 terminals|={n for n,adj in adjacency.items()if len({edges[tuple(sorted((n,m)))]for m in adj})>1}
 pieces=[];visited=set()
 for start in sorted(terminals):
  for nxt in sorted(adjacency.get(start,())):
   first=tuple(sorted((start,nxt)))
   if first in visited:continue
   role=edges[first];chain=[start,nxt];visited.add(first);previous,current=start,nxt
   while current not in terminals:
    nxt=next(n for n in adjacency[current]if n!=previous);key=tuple(sorted((current,nxt)));visited.add(key);chain.append(nxt);previous,current=current,nxt
   pieces.append(dict(route_id=f'AXIAL:{len(pieces):04d}',origin=chain[0],port=chain[-1],node_chain=chain,member_role=role,points_mm=[nodes[n]for n in chain]))
 components=0;seen=set()
 for n in adjacency:
  if n in seen:continue
  components+=1;pending=[n]
  while pending:
   q=pending.pop()
   if q in seen:continue
   seen.add(q);pending.extend(adjacency[q]-seen)
 report=dict(cycle_count=len(edges)-len(nodes)+components,component_count=components,frame_origin_count=len(frame_nodes),used_sleeves=sorted(used),radial_transverse_junctions=len(radial_nodes&level_nodes&terminals),ring_level_count=len(levels),reference_node_count=len(nodes),reference_edge_count=len(edges),radial_lengths_mm=[r['length_mm']for r in routes])
 if report['cycle_count']<2:raise ValueError('INSUFFICIENT_WEB_CELLS')
 return dict(nodes=nodes,pieces=pieces,frame_nodes=frame_nodes,source_nodes=source_nodes,radials=routes,report=report)
