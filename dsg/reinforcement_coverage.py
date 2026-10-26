"""Useful frame reach and opening-flank coverage, without relaxing geometry gates."""
import math
import numpy as np

POLICY='FAR_FRAME_GEODESIC_LATTICE_V2'


def opening_targets(sleeves, records, radius):
    by_implant={s['implant_name']:s for s in sleeves};targets=[]
    for record in records:
        sleeve=by_implant.get(record['implant'])
        if sleeve is None:raise ValueError('OPENING_SLEEVE_MISSING:'+record['implant'])
        wall_radius=float(sleeve['outer_radius_mm'])*1.01
        clearance=float(record['width_mm'])*.5+float(radius)+.08
        if not 0<clearance<wall_radius:
            raise ValueError('OPENING_FLANK_HAS_NO_ROOM:'+sleeve['id'])
        delta=math.asin(clearance/wall_radius)
        for side in (-1,1):
            targets.append({'id':sleeve['id']+':OPENING_FLANK:'+str(side),'sleeve_id':sleeve['id'],
                'side':side,'angle_rad':float(record['angle_rad'])+side*delta,
                'opening_angle_rad':float(record['angle_rad']),'tolerance_deg':30.,
                'matrix_world':sleeve['matrix_world'],'radius_mm':wall_radius,
                'height_mm':float(sleeve['height_mm'])})
    return targets


def matching_targets(point,sleeve_id,targets):
    matched=[]
    for target in targets:
        if target['sleeve_id']!=sleeve_id:continue
        matrix=np.linalg.inv(np.asarray(target['matrix_world'],float))
        local=matrix[:3,:3]@np.asarray(point,float)+matrix[:3,3]
        angle=math.atan2(local[1],local[0])
        gap=abs(math.degrees(math.remainder(angle-target['angle_rad'],2*math.pi)))
        if gap<=target.get('tolerance_deg',30.)+1e-6:matched.append(target['id'])
    return matched


def route_metrics(routes,owners,request):
    supports={r['id']:np.asarray(r['original_mm'],float) for r in request['supports']}
    sleeves={r['id']:r for r in request['sleeves']};targets=request.get('coverage_policy',{}).get('targets',[])
    result={}
    for route in routes:
        origin=supports[route.start_id];center=np.asarray(sleeves[owners[route.route_id]]['center'],float)
        distance=float(np.linalg.norm(origin-center))
        chord=float(np.linalg.norm(np.asarray(route.points_mm[-1])-origin))
        result[route.route_id]={'origin_distance_mm':distance,
            'useful_length_mm':min(float(route.length_mm),1.6*max(chord,.01)),
            'targets':matching_targets(route.points_mm[-1],owners[route.route_id],targets)}
    return result


def continuous_groups(paths,metadata):
    groups={}
    for path in paths:
        if metadata[path.route_id]['role']!='PRIMARY' and not metadata[path.route_id].get('continuous_branch'):continue
        parent=path.route_id.rsplit(':SEG',1)[0]
        groups.setdefault(parent,[]).append(path.route_id)
    return {parent:sorted(labels,key=lambda key:int(key.rsplit(':SEG',1)[1])) for parent,labels in groups.items()}


def verify_coverage(request,pieces,report,receipts=None):
    primary=[p for p in pieces if p['member_role']=='PRIMARY']
    secondary=[p for p in pieces if p['member_role']=='SECONDARY']
    if not secondary or not report.get('lattice_complete'):
        raise ValueError('GEODESIC_LATTICE_REQUIRED: las ramas directas no son una celosía.')
    targets=request.get('coverage_policy',{}).get('targets',[]);covered=set();angles={}
    for member in primary:
        point=member['points_mm'][-1]
        if receipts is not None:
            receipt=receipts.get(member['route_id'],{})
            if not receipt.get('positive_volume_overlap') or receipt.get('sleeve_id')!=member['sleeve_id'] or 'witness_mm' not in receipt:
                raise ValueError('PHYSICAL_OPENING_ANCHOR_UNVERIFIED:'+member['route_id'])
            point=receipt['witness_mm']
        covered.update(matching_targets(point,member['sleeve_id'],targets))
    missing=sorted({t['id'] for t in targets}-covered)
    if missing and request.get('coverage_policy',{}).get('require_all_flanks',True):raise ValueError('OPENING_FLANK_UNSUPPORTED:'+','.join(missing))
    if request.get('reinforcement_topology')=='ADAPTIVE_SPIDERWEB_V1':
        from .spiderweb import verify_web,frame_rim_available
        web=verify_web(pieces,frame_rim=bool(report.get('web_existing_frame_outer_ring') and frame_rim_available(request)),frame_nodes=[a['id']for a in request.get('supports',[])+request.get('web_growth_supports',[])])
        return dict(web,policy=POLICY,covered_targets=sorted(covered),uncovered_targets=missing,opening_flanks_complete=not missing,
                    physical_witnesses=receipts is not None,geodesic_lattice_verified=True,primary_count=len(primary),secondary_count=len(secondary),
                    primary_lengths_mm=[sum(float(np.linalg.norm(np.asarray(b)-a)) for a,b in zip(p['points_mm'],p['points_mm'][1:])) for p in primary])
    # Every primary must participate in a real triangular geodesic cross-brace.
    node_owners={};node_graph={};adjacency={p['route_id']:set() for p in primary};cross=[]
    for p in primary:
        labels=list(p.get('nodes',{}))
        for label in labels:node_owners.setdefault(label,set()).add(p['route_id']);node_graph.setdefault(label,set())
        for a,b in zip(labels,labels[1:]):node_graph[a].add(b);node_graph[b].add(a)
    for p in secondary:
        a,b=p['origin'],p['port']
        if a not in node_owners or b not in node_owners:continue
        if node_owners[a]&node_owners[b]:continue
        cross.append((a,b));node_graph[a].add(b);node_graph[b].add(a)
        for first in node_owners[a]:
            for second in node_owners[b]:adjacency[first].add(second);adjacency[second].add(first)
    reached=set();pending=[primary[0]['route_id']] if primary else []
    while pending:
        label=pending.pop()
        if label in reached:continue
        reached.add(label);pending.extend(adjacency[label]-reached)
    triangulated=set()
    for a,b in cross:
        for c in node_graph[a]&node_graph[b]:
            for label in (a,b,c):triangulated.update(node_owners[label])
    if len(primary)<2 or reached!=set(adjacency) or triangulated!=set(adjacency):
        raise ValueError('GEODESIC_LATTICE_DISCONNECTED_OR_NOT_TRIANGULATED')
    return {'policy':POLICY,'covered_targets':sorted(covered),'uncovered_targets':missing,'opening_flanks_complete':not missing,
            'physical_witnesses':receipts is not None,'geodesic_lattice_verified':True,
            'primary_count':len(primary),'secondary_count':len(secondary),
            'primary_lengths_mm':[sum(float(np.linalg.norm(np.asarray(b)-a)) for a,b in zip(p['points_mm'],p['points_mm'][1:])) for p in primary]}


def augment_request(request, project, end_clearance=2.5):
    targets=opening_targets(request['sleeves'],request.get('lateral_openings',[]),request['radius_mm'])
    request['coverage_policy']={'id':POLICY,'targets':targets,'require_lattice':True,'require_all_flanks':False,
        'criterion':'FARTHEST_VALID_FRAME_ORIGINS_AND_LONG_DISTRIBUTED_GEODESICS'}
    for target in targets:
        matrix=np.asarray(target['matrix_world'],float);extent=max(0.,target['height_mm']*.5-end_clearance)
        axial=np.linspace(-extent,extent,max(3,int(2*extent/.5)+1))
        choices=[]
        for variant in range(3):
            angle=target['angle_rad']+target['side']*math.radians(12*variant)
            ranked=[]
            for z in axial:
                local=np.asarray([target['radius_mm']*math.cos(angle),target['radius_mm']*math.sin(angle),z])
                point=matrix[:3,:3]@local+matrix[:3,3]
                try:row=project(target['id']+':V'+str(variant),point)
                except ValueError:continue
                offset=point-np.asarray(row['point_mm'])
                # A local IOS normal is not a wall-contact test. The exact swept
                # junction and protected-volume checks decide admissibility.
                if np.linalg.norm(offset)>12.:continue
                row.update(sleeve_id=target['sleeve_id'],axis=request['sleeves'][next(i for i,s in enumerate(request['sleeves']) if s['id']==target['sleeve_id'])]['axis'],
                    opening_target=target['id'],azimuth_deg=math.degrees(angle)%360,axial_level_mm=float(z),
                    end_clearance_admissible=True,required_end_clearance_mm=end_clearance)
                ranked.append((float(np.linalg.norm(offset)),abs(float(z)),row))
            if ranked:choices.append(min(ranked,key=lambda r:r[:2]))
        # Two genuinely different wall directions per flank. Every origin is
        # attempted against these before ordinary sleeve ports.
        choices.sort(key=lambda r:r[:2])
        request['ports'].extend(row for _,_,row in choices[:2])
    return request


def prioritize_pairs(pairs,request,limit=120):
    centers={s['id']:np.asarray(s['center'],float) for s in request['sleeves']}
    supports={r['id']:np.asarray(r['original_mm'],float) for r in request['supports']}
    ports={r['id']:r for r in request['ports']};groups={}
    for pair in pairs:groups.setdefault((pair.port.sleeve_id,pair.start.id),[]).append(pair)
    ordered=sorted(groups,key=lambda key:(key[0],-float(np.linalg.norm(supports[key[1]]-centers[key[0]])),key[1]))
    for key,options in groups.items():
        options.sort(key=lambda p:(0 if ports[p.end.id].get('opening_target') else 1,
            ports[p.end.id].get('opening_target',''),float(np.linalg.norm(np.asarray(ports[p.end.id]['original_mm'])-np.asarray(ports[p.end.id]['point_mm']))),p.end.id))
        # Interleave critical flanks before spending the budget on variants.
        buckets={}
        for pair in options:buckets.setdefault(ports[pair.end.id].get('opening_target','~ORDINARY'),[]).append(pair)
        keys=sorted(buckets)
        groups[key]=[buckets[tag][level] for level in range(max(map(len,buckets.values()))) for tag in keys if level<len(buckets[tag])]
    selected=[];counts={}
    for level in range(max((len(v) for v in groups.values()),default=0)):
        for key in ordered:
            if level<len(groups[key]) and counts.get(key[0],0)<limit:
                selected.append(groups[key][level]);counts[key[0]]=counts.get(key[0],0)+1
    return tuple(selected)


def failure_message(outcome,request=None):
    if request and request.get('reinforcement_envelope') and outcome.get('status')!='CANDIDATE':
        return 'Sin celosía completa que respete la salida superior del frame y las paredes del sleeve. La guía se conserva.'
    report=outcome.get('report',{});selection=report.get('sleeve_anchor_selection',{})
    missing=selection.get('missing_targets_in_pool',selection.get('uncovered_targets',[]))
    if missing:
        return 'Sin celosía completa: faltan anclajes válidos en '+str(len(missing))+' lado(s) de la apertura lateral. La guía se conserva.'
    if outcome.get('status')=='NO_VALID_GEODESIC_LATTICE':
        return 'Sin celosía completa: conexiones geodésicas verificadas '+str(report.get('lattice_links_completed',0))+'/'+str(report.get('lattice_required_links',0))+'. La guía se conserva.'
    return 'Sin propuesta geométrica válida: '+str(outcome.get('rejections',[])[-3:])


def functional_surface_mask(surface,obstacles,radius_mm,tolerance_mm=0.,progress=lambda text:None):
    """Conservative graph corridor around saved functional solids.

    Each vertex clearance includes half its longest incident graph edge. The
    distance Lipschitz bound therefore protects the full connecting edge. Exact
    swept paths and final meshes are still validated independently afterwards.
    """
    from .ios_surface import SolidClearanceIndex
    points=surface.vertices_mm;n=len(points);allowed=np.ones(n,bool)
    src=np.repeat(np.arange(n),np.diff(surface.csr_offsets));margin=np.zeros(n)
    np.maximum.at(margin,src,surface.csr_lengths_mm*.5)
    np.maximum.at(margin,surface.csr_destinations,surface.csr_lengths_mm*.5)
    required=margin+float(radius_mm)+float(tolerance_mm)+1e-6;details=[]
    for obstacle in obstacles:
        progress('Preparando recorrido alrededor de '+str(obstacle.get('label','volumen funcional')))
        index=SolidClearanceIndex(obstacle);xyz=np.asarray(obstacle['vertices_mm'],float)
        low=xyz.min(axis=0);high=xyz.max(axis=0)
        candidates=np.flatnonzero(allowed&np.all(points>=low-required[:,None],axis=1)&np.all(points<=high+required[:,None],axis=1))
        blocked=0
        for label in candidates:
            point=points[label];distance=required[label];hit=False
            for ids,tree,extent in index.buckets:
                rows=tree.query_ball_point(point,distance+extent+1e-8)
                for row in rows:
                    triangle=index.triangles[ids[row]]
                    if index.kernel.closest_point_on_triangle(point,*triangle)[1]<=distance*distance:
                        hit=True;break
                if hit:break
            if not hit and np.all(point>=low) and np.all(point<=high):hit=index.contains(point)
            if hit:allowed[label]=False;blocked+=1
        details.append({'label':index.label,'tested_vertices':len(candidates),'blocked_vertices':blocked})
    return allowed,{'blocked_vertices':int(np.count_nonzero(~allowed)),'functional_volumes':details,'full_edge_clearance_bound':True}


def protected_anchor_reason(surface,anchor,radius_mm,obstacles):
    from .ios_surface import validate_anchor,check_mesh_obstacles
    point=validate_anchor(surface,anchor)
    clear,reason=check_mesh_obstacles(np.vstack((point,point+[1e-8,0,0])),radius_mm,obstacles)
    return None if clear else reason



def layout_trial_report(report):
    # The live selection report later receives the trial list. Keep this
    # historical snapshot independent, otherwise a valid candidate is cyclic.
    from copy import deepcopy
    return deepcopy(report)


def lattice_trial_plan(alternatives,limit=12,route_nodes=None):
    """Spend the bounded search on distinct sizes and joint stations first."""
    unique=[]
    for ids in alternatives:
        ids=tuple(ids)
        if ids not in unique:unique.append(ids)
    if route_nodes:
        leaders={}
        for ids in unique:
            signature=tuple(sorted(tuple(route_nodes[key]) for key in ids))
            leaders.setdefault(signature,ids)
        buckets={}
        for ids in leaders.values():buckets.setdefault(len(ids),[]).append(ids)
        ordered=[]
        for level in range(max((len(rows) for rows in buckets.values()),default=0)):
            for size in sorted(buckets,reverse=True):
                if level<len(buckets[size]):ordered.append(buckets[size][level])
        first=ordered[:max(1,limit//4)]
        stations=((.40,.72),(.45,.80),(.35,.75),(.25,.65))
        trials=[(ids,fraction) for fraction in stations for ids in first]
        return trials[:limit]
    representatives={}
    for ids in unique:representatives.setdefault(len(ids),ids)
    first=list(representatives.values());stations=((.40,.72),(.35,.75),(.25,.65),(.45,.80))
    trials=[(ids,fractions) for fractions in stations for ids in first]
    buckets={}
    for ids in unique:
        if ids not in first:buckets.setdefault(len(ids),[]).append(ids)
    for level in range(max((len(rows) for rows in buckets.values()),default=0)):
        for size in sorted(buckets,reverse=True):
            if level<len(buckets[size]):trials.append((buckets[size][level],stations[0]))
    return trials[:limit]
