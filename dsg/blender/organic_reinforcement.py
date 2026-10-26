"""Automatic geodesic bars with the installed manual tangent collar builder."""
import json
import numpy as np
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree


def mesh_self_intersections(vertices,faces):
    tree=BVHTree.FromPolygons(vertices.tolist(),faces.tolist(),all_triangles=True)
    return [(a,b) for a,b in tree.overlap(tree) if a<b and not set(faces[a])&set(faces[b])]


def regularize_generated_skin(context,obj):
    """Resolve intersections only in the new candidate, never its supports."""
    old=obj.data
    modifier=obj.modifiers.new('DSG_OrganicSkin','REMESH');modifier.mode='VOXEL';modifier.voxel_size=.08;modifier.adaptivity=0.;modifier.use_smooth_shade=True
    context.view_layer.update();deps=context.evaluated_depsgraph_get()
    mesh=bpy.data.meshes.new_from_object(obj.evaluated_get(deps),depsgraph=deps)
    obj.modifiers.remove(modifier);obj.data=mesh
    if old.users==0:bpy.data.meshes.remove(old)
    modifier=obj.modifiers.new('DSG_OrganicSkinFairing','SMOOTH');modifier.factor=.4;modifier.iterations=3
    context.view_layer.update();deps=context.evaluated_depsgraph_get()
    mesh=bpy.data.meshes.new_from_object(obj.evaluated_get(deps),depsgraph=deps);old=obj.data
    obj.modifiers.remove(modifier);obj.data=mesh
    if old.users==0:bpy.data.meshes.remove(old)
    obj['DSG_organic_skin_regularization_mm']=.08


def build_bar(context,name,piece,support_a,support_b):
    from .. import guide_module as g
    from .generative_frame import _export_mesh
    from ..guide_export.mesh_checks import manifold_report
    pts=[Vector(p) for p in piece['points_mm']];radius=float(piece['radius_mm'])
    if support_a is None or support_b is None:raise ValueError('MISSING_ORGANIC_SUPPORT:'+piece['route_id'])
    points,arc=g._polyline_cumulative_lengths(pts);length=arc[-1]
    neck=g._reinforcement_extended_neck_length(radius,length)
    contacts=[];trees=[];trims=[];parts=[];combined=None;sections=[]
    try:
        for support,chain in ((support_a,pts),(support_b,list(reversed(pts)))):
            from ..guide_export.mesh_checks import signed_volume_mm3
            vertices,faces=_export_mesh(context,support)
            if signed_volume_mm3(vertices,faces)<0:faces=faces[:,::-1]
            tree=BVHTree.FromPolygons(vertices.tolist(),faces.tolist(),all_triangles=True)
            trees.append(tree);hit=None;station=0.;previous=None;was_inside=False
            nearest=tree.find_nearest(chain[0])
            for j,point in enumerate(chain):
                if j:station+=(point-chain[j-1]).length
                if station>length*.38:break
                near=tree.find_nearest(point)
                if not near or near[0] is None:continue
                signed=(point-near[0]).dot(near[1])
                if signed<=.0001:was_inside=True
                if was_inside and signed>.0001:
                    delta=point-chain[j-1]
                    ray=tree.ray_cast(chain[j-1],delta.normalized(),delta.length+.002)
                    if ray and ray[0] is not None:hit=(ray[0],ray[1],station-(point-ray[0]).length)
                    else:hit=(near[0],near[1],station)
                    break
                previous=near
            if hit is None and nearest and nearest[0] is not None and nearest[3]<=max(3.,radius*2.):
                hit=(nearest[0],nearest[1],0.)
            if hit is None:raise ValueError('NO_ORGANIC_CONTACT:'+support.name)
            contact,normal,station=hit;contacts.append((Vector(contact),Vector(normal)))
            trims.append(min(length*.44,max(.35,neck+station)))
        body_points=g._trim_polyline_by_distances(pts,trims[0],trims[1])
        if len(body_points)<2:raise ValueError('ORGANIC_BODY_TOO_SHORT')
        tangents=g._polyline_vertex_tangents(body_points)
        start_u=g._preferred_reinforcement_tube_u(contacts[0][1],tangents[0]);end_u=g._preferred_reinforcement_tube_u(contacts[1][1],tangents[-1])
        body,frames=g._create_open_rotation_minimizing_tube(context,name+'_Body',body_points,radius,48,start_u,desired_end_u=end_u)
        if body is None:raise ValueError('ORGANIC_BODY_FAILED')
        parts.append(body)
        sections.extend([*list(p),radius] for p in body_points)
        for i,(support,tree,contact) in enumerate(zip((support_a,support_b),trees,contacts)):
            index=0 if i==0 else -1;direction=tangents[index] if i==0 else -tangents[index]
            collar=g._build_reinforcement_coons_blend_object(context,name+'_Collar'+str(i),contact[0],contact[1],direction,support,radius,length,
                surface_tree=tree,tube_center_override=body_points[index],tube_tangent_override=direction,tube_u_override=frames['u_axes'][index],tube_v_override=frames['v_axes'][index],
                support_embed_depth_override=min(.18,max(.06,radius*.12)),cap_tube=False,footprint_radius_ratio=1.2,fullness_scale=0.,tangent_handle_scale=1.,bound_tube_halfspace=True)
            if collar is None:raise ValueError('ORGANIC_COLLAR_FAILED')
            parts.append(collar)
            sections.extend(json.loads(collar.get('DSG_organic_sections_json','[]')))
        combined=g.build_combined_mesh_object_world(context,parts,name)
        if combined is None:raise ValueError('ORGANIC_COMBINE_FAILED')
        g.clean_boolean_cutter_mesh(combined,merge_dist=.00035,max_vertices=700000)
        vertices,faces=_export_mesh(context,combined)
        from ..guide_export.mesh_checks import signed_volume_mm3
        if signed_volume_mm3(vertices,faces)<0:
            import bmesh
            bm=bmesh.new();bm.from_mesh(combined.data);bmesh.ops.reverse_faces(bm,faces=list(bm.faces));bm.to_mesh(combined.data);bm.free();combined.data.update()
            vertices,faces=_export_mesh(context,combined)
        intersections=mesh_self_intersections(vertices,faces)
        if intersections:
            regularize_generated_skin(context,combined)
            vertices,faces=_export_mesh(context,combined)
            if mesh_self_intersections(vertices,faces):raise ValueError('ORGANIC_FINAL_SELF_INTERSECTION')
        combined['DSG_organic_final_self_intersections']=0
        from .organic_quality import validate_body_radius
        radius_check=validate_body_radius(vertices,faces,body_points,frames['u_axes'],frames['v_axes'],radius)
        combined['DSG_organic_body_radius_json']=json.dumps(radius_check)
        ios=bpy.data.objects.get(g.CLOSED_MODEL_NAME)
        if ios is not None:
            v,f=_export_mesh(context,ios)
            if signed_volume_mm3(v,f)<0:f=f[:,::-1]
            ios_tree=BVHTree.FromPolygons(v.tolist(),f.tolist(),all_triangles=True)
            skin=BVHTree.FromPolygons(vertices.tolist(),faces.tolist(),all_triangles=True)
            failures=[]
            for section in sections:
                center=Vector(section[:3]);extent=float(section[3]);supported=False
                for tree in (ios_tree,*trees):
                    witness=tree.find_nearest(center)
                    if not witness or witness[0] is None:continue
                    if (center-witness[0]).dot(witness[1])<=0:
                        supported=True;break
                    if witness[3]>extent+.03:continue
                    face=skin.find_nearest(witness[0])
                    if face and face[0] is not None and (witness[0]-face[0]).dot(face[1])<=.03:
                        supported=True;break
                if not supported:failures.append(section)
            if failures:raise ValueError('ORGANIC_FINAL_UNSUPPORTED_SECTIONS:'+str(len(failures))+':'+name)
            combined['DSG_organic_final_support_sections']=len(sections)
            combined['DSG_organic_final_support_verified']=True

        check=manifold_report(vertices,faces)
        if check.blocking:raise ValueError('ORGANIC_MESH_NOT_CLOSED:'+str(check.metrics))
        for polygon in combined.data.polygons:polygon.use_smooth=True
        combined['DSG_organic_collar_count']=2;combined['DSG_organic_blend']='BOUNDED_TANGENT_COONS_HERMITE'
        combined['DSG_organic_footprint_radius_ratio']=1.2;combined['DSG_organic_internal_caps']=False
        combined['DSG_organic_rotation_minimizing_frame']=True
        return combined
    except Exception:
        if combined is not None:g.safe_remove_object_with_data(combined)
        raise
    finally:
        for obj in parts:g.safe_remove_object_with_data(obj)


def build_network(context,pieces,request,*,existing_pieces=(),existing_objects=()):
    from .. import guide_module as g,frame_structural as s
    from .generative_frame import _export_mesh
    from ..organic_reinforcement import validate_mesh_keepouts
    from ..frame_swept_clearance_core import CylinderKeepOut
    if len(existing_pieces)!=len(existing_objects):raise ValueError('GROWTH_EXISTING_NETWORK_MISMATCH')
    all_pieces=tuple(existing_pieces)+tuple(pieces)
    frame=s._frame_obj(context);nodes={row['id']:frame for row in (request['supports']+request.get('web_growth_supports',[]))};created=[];zones=[];obstacles=[]
    for sleeve in request['sleeves']:
        zones.append(CylinderKeepOut(sleeve['id']+':FULL_DRILL',tuple(sleeve['center']),tuple(sleeve['axis']),sleeve['inner_radius_mm'],sleeve['height_mm']*.5+20.))
        obj=bpy.data.objects.get(g.SLEEVE_SOURCE_PREFIX+f"{int(sleeve['id'][1:]):02d}")
        if obj is None:raise ValueError('MISSING_SLEEVE_SOURCE:'+sleeve['id'])
        for p in all_pieces:
            if p.get('sleeve_id')==sleeve['id']:nodes[p['port']]=obj
    for row in request.get('obstacles',[]):
        data=np.load(row['file'],allow_pickle=False);obstacles.append({'label':row['label'],'vertices_mm':data['vertices'],'triangles':data['triangles'],'closed':row['closed']})
    for previous,obj in zip(existing_pieces,existing_objects):
        if not obj.get('DSG_organic_final_support_verified') or not obj.get('DSG_organic_final_keepouts_verified'):raise ValueError('GROWTH_UNVERIFIED_PARENT')
        for label in previous.get('nodes',{}):
            if label not in (previous['origin'],previous['port']):nodes[label]=obj
    try:
        for index,piece in enumerate(pieces):
            from . import generative_frame
            generative_frame.STATE['message']='Creando malla final · '+str(index+1)+'/'+str(len(pieces))
            if not bpy.app.background and context.screen:
                for area in context.screen.areas:area.tag_redraw()
                try:bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP',iterations=1)
                except RuntimeError:pass
            name='DSG_GenerativePreview_'+request.get('run_id','test')+'_'+str(index+len(existing_objects))
            obj=build_bar(context,name,piece,nodes.get(piece['origin']),nodes.get(piece['port']));created.append(obj)
            obj['DSG_organic_nominal_radius_mm']=float(piece['radius_mm'])
            vertices,faces=_export_mesh(context,obj)
            if request.get('reinforcement_envelope'):
                from ..reinforcement_envelope import validate_mesh_envelope
                from .reinforcement_envelope import validate_upper_frame_contact
                envelope=validate_mesh_envelope(vertices,faces,request)
                fv,ff=_export_mesh(context,frame)
                upper=validate_upper_frame_contact(vertices,faces,fv,ff,request['reinforcement_envelope']['frame_entry_axis'])
                if (piece['member_role']=='PRIMARY' or {piece['origin'],piece['port']}&{row['id']for row in (request['supports']+request.get('web_growth_supports',[]))}) and not upper['upper_surface_crossings']:raise ValueError('FRAME_UPPER_ATTACHMENT_UNVERIFIED')
                obj['DSG_reinforcement_envelope_verified']=True
                obj['DSG_reinforcement_envelope_json']=json.dumps(dict(envelope,frame_contact=upper))
            check=validate_mesh_keepouts(vertices,faces,zones,obstacles)
            if not check['valid']:raise ValueError(check['reason'])
            obj['DSG_organic_final_keepouts_verified']=True
            if piece['member_role']=='PRIMARY':
                from .sleeve_attachment import certify_sleeve_attachment
                sleeve_obj=nodes.get(piece['port'])
                if sleeve_obj is None:raise ValueError('MISSING_DIRECT_SLEEVE_ANCHOR')
                sv,sf=_export_mesh(context,sleeve_obj)
                receipt=certify_sleeve_attachment(vertices,faces,sv,sf)
                receipt.update(sleeve_id=piece['sleeve_id'],sleeve_name=sleeve_obj.name)
                obj['DSG_sleeve_anchor_receipt_json']=json.dumps(receipt,sort_keys=True)
                if request.get('reinforcement_topology'):
                    fv,ff=_export_mesh(context,frame)
                    frame_receipt=certify_sleeve_attachment(vertices,faces,fv,ff)
                    obj['DSG_frame_anchor_receipt_json']=json.dumps(frame_receipt,sort_keys=True)

            if request.get('reinforcement_topology')=='ADAPTIVE_SPIDERWEB_V1' and piece['member_role']=='SECONDARY':
                from .sleeve_attachment import certify_sleeve_attachment
                receipts={}
                for label in (piece['origin'],piece['port']):
                    support=nodes.get(label)
                    if support is None:raise ValueError('WEB_PHYSICAL_JOINT_MISSING:'+label)
                    sv,sf=_export_mesh(context,support)
                    if piece.get('web_kind')=='GROWTH':
                        points=np.asarray(piece['points_mm'],float);endpoint=points[0]if label==piece['origin']else points[-1]
                        parent_radius=float(support.get('DSG_organic_nominal_radius_mm',piece['radius_mm']))
                        bound=3.*max(parent_radius,float(piece['radius_mm']))
                        if label in {row['id']for row in (request['supports']+request.get('web_growth_supports',[]))}:
                            length=float(np.linalg.norm(np.diff(points,axis=0),axis=1).sum())
                            projection=piece.get('frame_neck_start_mm')if label==piece['origin']else piece.get('frame_neck_end_mm')
                            bound=min(.44*length,float(projection or 0.)+3.*piece['radius_mm'])+piece['radius_mm']
                        receipts[label]=certify_sleeve_attachment(vertices,faces,sv,sf,near_point_mm=endpoint,maximum_witness_distance_mm=bound)
                    else:receipts[label]=certify_sleeve_attachment(vertices,faces,sv,sf)
                obj['DSG_web_joint_receipts_json']=json.dumps(receipts,sort_keys=True)
                obj['DSG_web_joints_verified']=True

            for label in piece.get('nodes',{}):
                if label not in (piece['origin'],piece['port']):
                    if label in nodes and nodes[label]!=obj:raise ValueError('WEB_NODE_HAS_TWO_PHYSICAL_PARENTS:'+label)
                    nodes[label]=obj
            if piece.get('web_kind')=='GROWTH':
                certify_generated_contacts(context,piece,obj,tuple(existing_pieces)+tuple(pieces[:index]),tuple(existing_objects)+tuple(created[:-1]))
        if request.get('reinforcement_topology'):
            from ..guide_export.mesh_checks import connected_components
            fv,ff=_export_mesh(context,frame);components=connected_components(len(fv),ff)
            tree=BVHTree.FromPolygons(fv.tolist(),ff.tolist(),all_triangles=True);attached=set()
            for piece,obj in zip(all_pieces,tuple(existing_objects)+tuple(created)):
                if piece['member_role']!='PRIMARY':continue
                receipt=json.loads(obj['DSG_frame_anchor_receipt_json']);near=tree.find_nearest(Vector(receipt['witness_mm']))
                if not near or near[2] is None:raise ValueError('WEB_FRAME_RIM_ATTACHMENT_UNVERIFIED')
                attached.add(int(components[int(ff[near[2],0])]))
            for piece,obj in zip(all_pieces,tuple(existing_objects)+tuple(created)):
                if piece['member_role']=='PRIMARY':continue
                receipts=json.loads(obj.get('DSG_web_joint_receipts_json','{}'))
                for label in {piece['origin'],piece['port']}&{row['id']for row in (request['supports']+request.get('web_growth_supports',[]))}:
                    if label not in receipts:raise ValueError('WEB_FRAME_BRANCH_ATTACHMENT_UNVERIFIED')
                    near=tree.find_nearest(Vector(receipts[label]['witness_mm']))
                    if not near or near[2]is None:raise ValueError('WEB_FRAME_BRANCH_ATTACHMENT_UNVERIFIED')
                    attached.add(int(components[int(ff[near[2],0])]))
            if len(attached)!=1:raise ValueError('WEB_FRAME_RIM_DISCONNECTED')
            for obj in created:obj['DSG_web_frame_rim_verified']=True
        return created
    except Exception:
        for obj in created:g.safe_remove_object_with_data(obj)
        raise

def certify_generated_contacts(context,piece,obj,older_pieces,older_objects):
    """Only declared local welds may intersect an older generated branch."""
    from .generative_frame import _export_mesh
    from .sleeve_attachment import _segment_triangle
    from ..frame_optimizer import _kernel
    vertices,faces=_export_mesh(context,obj);triangles=vertices[faces]
    tree=BVHTree.FromPolygons(vertices.tolist(),faces.tolist(),all_triangles=True);kernel=_kernel()
    endpoints={piece['origin']:np.asarray(piece['points_mm'][0]),piece['port']:np.asarray(piece['points_mm'][-1])}
    low=vertices.min(axis=0);high=vertices.max(axis=0)
    for older,support in zip(older_pieces,older_objects):
        ov,of=_export_mesh(context,support)
        if np.any(ov.max(axis=0)<low-1e-7)or np.any(ov.min(axis=0)>high+1e-7):continue
        labels=set(older.get('nodes',{}))|{older['origin'],older['port']};shared=[endpoints[k]for k in endpoints if k in labels]
        limit=3.*max(float(piece['radius_mm']),float(older['radius_mm']))
        def local(points):return bool(shared)and any(all(np.linalg.norm(np.asarray(p)-center)<=limit+1e-5 for p in points)for center in shared)
        other=ov[of];bvh=BVHTree.FromPolygons(ov.tolist(),of.tolist(),all_triangles=True)
        for first,second in tree.overlap(bvh):
            a,b=triangles[first],other[second];witnesses=[]
            for tri,opposite in ((a,b),(b,a)):
                for p,q in zip(tri,np.roll(tri,-1,axis=0)):
                    point=_segment_triangle(p,q,opposite)
                    if point is not None:witnesses.append(point)
            if not witnesses:
                distance,pa,pb=kernel.triangle_triangle_distance(a,b)
                if distance>1e-12:continue
                witnesses=[pa,pb]
            if not local(witnesses):raise ValueError('GROWTH_NATIVE_UNDECLARED_CONTACT:'+older['route_id'])
        points=np.asarray(piece['points_mm'],float)
        for point in points[::max(1,len(points)//24)]:
            near=bvh.find_nearest(Vector(point))
            if near and near[0]is not None and near[3]>.02 and (Vector(point)-near[0]).dot(near[1])<0 and not local([point]):
                raise ValueError('GROWTH_NATIVE_NONLOCAL_CONTAINMENT:'+older['route_id'])
