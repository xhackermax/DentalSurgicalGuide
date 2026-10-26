"""Bounded deterministic selection of already validated sleeve connections.

Coverage of marked supports wins before sleeve-port diversity and total length.
The caller supplies exact inter-route compatibility; no geometry gate is relaxed.
"""
import math


def select_sleeve_routes(candidates,owners,pair_compatible,budget=4096,*,minimum_per_sleeve=0,alternatives_limit=32,route_metrics=None,required_targets=(),preferred_targets=(),maximum_per_sleeve=None):
    """Return ``(tuple(routes), report)`` with at most one per sleeve/support.

    ``owners[route.route_id]`` identifies each route's sleeve. ``pair_compatible``
    must check two actual-radius routes, including routes for different sleeves.
    A budget-limited result is feasible but never advertised as proven maximal.
    A positive ``minimum_per_sleeve`` requires that many direct connections for
    every sleeve in ``owners`` before a selected set can be reported feasible.
    Reported alternatives include the best set for each observed connection/
    port count before filling remaining slots by the same objective. This keeps
    smaller, diverse sets available for downstream lattice validation.
    """
    if isinstance(budget,bool) or not isinstance(budget,int) or budget<1:
        raise ValueError('Selection budget must be a positive integer.')
    if isinstance(minimum_per_sleeve,bool) or not isinstance(minimum_per_sleeve,int) or minimum_per_sleeve<0:
        raise ValueError('Minimum connections per sleeve must be a nonnegative integer.')
    if isinstance(alternatives_limit,bool) or not isinstance(alternatives_limit,int) or alternatives_limit<1:
        raise ValueError('Alternative limit must be a positive integer.')
    if maximum_per_sleeve is not None and (isinstance(maximum_per_sleeve,bool) or not isinstance(maximum_per_sleeve,int) or maximum_per_sleeve<max(1,minimum_per_sleeve)):
        raise ValueError('Maximum connections per sleeve must cover the minimum.')
    preferred_targets=set(preferred_targets)
    policy_metrics=route_metrics
    required_targets=set(required_targets)
    sleeves=sorted(set(owners.values()))
    candidates=tuple(candidates);unique={}
    for route in candidates:
        sleeve=owners[route.route_id]
        length=float(route.length_mm)
        if not math.isfinite(length) or length<0:raise ValueError('Invalid route length.')
        points=tuple(tuple(float(v) for v in point) for point in route.points_mm)
        key=(sleeve,route.start_id,route.end_id,points)
        previous=unique.get(key)
        if previous is None or (length,route.route_id)<(float(previous.length_mm),previous.route_id):unique[key]=route
    groups={}
    for route in unique.values():groups.setdefault((owners[route.route_id],route.start_id),[]).append(route)
    ordered=sorted(groups,key=lambda key:(-max((policy_metrics.get(r.route_id,{}).get('origin_distance_mm',0.) for r in groups[key]),default=0.),key) if policy_metrics is not None else (len(groups[key]),key))
    for options in groups.values():
        options.sort(key=lambda route:(-len(policy_metrics.get(route.route_id,{}).get('targets',[])),-float(route.length_mm),route.end_id,route.route_id) if policy_metrics is not None else (float(route.length_mm),route.end_id,route.route_id))
    best=();best_score=(0,0,0.,());states=0;complete=True;compatibility={};feasible=False;feasible_sets={}

    def score(routes):
        ports={(owners[route.route_id],route.end_id) for route in routes}
        if policy_metrics is not None:
            targets={t for r in routes for t in policy_metrics.get(r.route_id,{}).get('targets',[])}
            reach=math.fsum(policy_metrics.get(r.route_id,{}).get('origin_distance_mm',0.) for r in routes)
            useful=math.fsum(policy_metrics.get(r.route_id,{}).get('useful_length_mm',float(r.length_mm)) for r in routes)
            return ((-len(targets&(required_targets|preferred_targets)),-len(routes),-reach),-len(ports),-useful,tuple(sorted(r.route_id for r in routes)))
        return (-len(routes),-len(ports),math.fsum(float(route.length_mm) for route in routes),tuple(sorted(route.route_id for route in routes)))

    def compatible(a,b):
        key=tuple(sorted((id(a),id(b))))
        if key not in compatibility:compatibility[key]=bool(pair_compatible(a,b))
        return compatibility[key]

    remaining_targets=[set() for _ in range(len(ordered)+1)]
    if policy_metrics is not None:
        for index in range(len(ordered)-1,-1,-1):
            remaining_targets[index]=remaining_targets[index+1]|{t for r in groups[ordered[index]] for t in policy_metrics.get(r.route_id,{}).get('targets',[])}

    def visit(index,selected):
        nonlocal states,complete,best,best_score,feasible
        if states>=budget:complete=False;return
        states+=1
        if required_targets:
            covered={t for r in selected for t in policy_metrics.get(r.route_id,{}).get('targets',[])} if policy_metrics is not None else set()
            if not required_targets<=covered|remaining_targets[index]:return
        current=score(selected)
        meets_minimum=all(sum(owners[route.route_id]==sleeve for route in selected)>=minimum_per_sleeve for sleeve in sleeves)
        if required_targets:
            covered_targets={t for r in selected for t in policy_metrics.get(r.route_id,{}).get('targets',[])} if policy_metrics is not None else set()
            meets_minimum=meets_minimum and required_targets<=covered_targets
        if meets_minimum:feasible_sets.setdefault(current[3],(current,selected))
        if meets_minimum and (not feasible or current<best_score):
            best=selected;best_score=current;feasible=True
        if index==len(ordered):return
        for route in groups[ordered[index]]:
            if maximum_per_sleeve is not None and sum(owners[r.route_id]==owners[route.route_id] for r in selected)>=maximum_per_sleeve:continue
            if all(compatible(route,other) for other in selected):visit(index+1,selected+(route,))
            if not complete:return
        visit(index+1,selected)

    visit(0,())
    best=tuple(sorted(best,key=lambda route:(owners[route.route_id],route.start_id,route.end_id,route.route_id)))
    available={sleeve:sorted(origin for owner,origin in groups if owner==sleeve) for sleeve in sleeves}
    covered={sleeve:sorted(route.start_id for route in best if owners[route.route_id]==sleeve) for sleeve in sleeves}
    ranked=sorted(feasible_sets.values(),key=lambda item:item[0]);representatives={}
    for item in ranked:
        # Structural reach ranks candidates, but must not turn every score into
        # a separate layout-size group and crowd smaller complete networks out.
        key=(-len(item[1]),item[0][1]) if policy_metrics is not None else item[0][:2]
        representatives.setdefault(key,item)
    alternatives={item[0][3]:item for item in list(representatives.values())[:alternatives_limit]}
    for item in ranked:
        if len(alternatives)>=alternatives_limit:break
        alternatives.setdefault(item[0][3],item)
    if policy_metrics is not None:
        buckets={}
        for item in ranked:buckets.setdefault(len(item[1]),[]).append(item)
        for size,items in buckets.items():
            leaders={}
            for item in items:
                signature=tuple(sorted((owners[r.route_id],r.start_id,r.end_id) for r in item[1]))
                leaders.setdefault(signature,item)
            preferred=list(leaders.values());preferred_ids={item[0][3] for item in preferred}
            buckets[size]=preferred+[item for item in items if item[0][3] not in preferred_ids]

        balanced={}
        for level in range(max((len(rows) for rows in buckets.values()),default=0)):
            for size in sorted(buckets,reverse=True):
                if level<len(buckets[size]) and len(balanced)<alternatives_limit:
                    item=buckets[size][level];balanced[item[0][3]]=item
            if len(balanced)>=alternatives_limit:break
        alternatives=balanced
    alternatives=sorted(alternatives.values(),key=lambda item:item[0])
    report={'candidate_count':len(candidates),'deduplicated_candidate_count':len(unique),
            'direct_connection_count':len(best),'distinct_sleeve_port_count':-best_score[1],
            'direct_total_length_mm':math.fsum(float(r.length_mm) for r in best),'available_origins_by_sleeve':available,
            'supported_origins_by_sleeve':covered,
            'unconnected_origins_by_sleeve':{sleeve:sorted(set(available[sleeve])-set(covered[sleeve])) for sleeve in sleeves},
            'search_budget':budget,'search_states_visited':states,'search_complete':complete,
            'maximum_direct_connections_proven':complete and feasible,'pair_compatibility_checks':len(compatibility),
            'minimum_per_sleeve':minimum_per_sleeve,'maximum_per_sleeve':maximum_per_sleeve,'minimum_connections_satisfied':feasible,
            'no_feasible_minimum_set_proven':complete and not feasible,
            'alternative_route_sets':[list(item[0][3]) for item in alternatives],
            'alternatives_limit':alternatives_limit,'feasible_route_sets_found':len(feasible_sets),
            'alternative_groups_found':len(representatives),
            'alternatives_complete':complete and len(alternatives)==len(feasible_sets),
            'selection_criterion':'SUPPORT_COVERAGE_THEN_SLEEVE_PORT_DIVERSITY_THEN_LENGTH'}
    if policy_metrics is not None:
        covered={t for r in best for t in policy_metrics.get(r.route_id,{}).get('targets',[])}
        report.update(selection_criterion='OPENING_FLANKS_THEN_FRAME_COVERAGE_THEN_FARTHEST_ORIGINS_THEN_LONG_GEODESICS',
                      covered_targets=sorted(covered&required_targets),uncovered_targets=sorted(required_targets-covered),
                      covered_preferred_targets=sorted(covered&preferred_targets),uncovered_preferred_targets=sorted(preferred_targets-covered),
                      available_targets=sorted(remaining_targets[0]),missing_targets_in_pool=sorted(required_targets-remaining_targets[0]),
                      selected_origin_reach_mm={r.start_id:policy_metrics[r.route_id]['origin_distance_mm'] for r in best},
                      selected_route_lengths_mm={r.route_id:float(r.length_mm) for r in best})
    return best,report
