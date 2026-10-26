"""Repair only a pending irrigation path; the exact lumen guard remains authoritative."""
import numpy as np
from mathutils import Vector
from ..irrigation_reroute import reroute,adaptive_limits


def repair_entry(context,entry,props,model):
    from .. import guide_module as g
    if model is None or model.type!='MESH':
        return None,dict(status='NO_SAFE_ROUTE',reason='Falta el modelo para verificar el desvío.')
    tree=g._build_world_surface_bvh(context,model)
    report=g.get_mesh_solid_report(model,max_polygons=500000)
    if tree is None or not report.get('solid'):
        return None,dict(status='NO_SAFE_ROUTE',reason='El modelo no es cerrado/verificable para desviar automáticamente.')
    controls=np.asarray([list(p) for p in entry['points']],float)
    if len(controls)==3:
        controls=np.vstack((controls[:2],(controls[1]+controls[2])*.5,controls[2:]))
    def trial(q):return dict(entry,points=[Vector(p) for p in q])
    observed={}
    def assess(q):
        groups=g._irrigation_model_preflight_sample_groups(trial(q),props)
        cost=0.;gradient=np.zeros_like(q);maximum_deficit=0.;maximum_radius=0.
        for group in groups:
            for point,radius,_ in group[::max(1,len(group)//96)]:
                point=Vector(point);near=tree.find_nearest(point)
                if near is None or near[0] is None:return float('inf'),gradient
                loc,normal,_,distance=near
                inside=g._bvh_point_inside_solid(tree,point,tolerance=.01)
                deficit=max(0.,float(radius)+.22-(-float(distance) if inside else float(distance)))
                maximum_deficit=max(maximum_deficit,deficit);maximum_radius=max(maximum_radius,float(radius))
                if deficit<=0:continue
                cost+=deficit*deficit
                direction=(loc-point) if inside else (point-loc)
                if direction.length<1e-7:direction=Vector(normal)
                if direction.length<1e-7:continue
                direction.normalize()
                i=min(range(2,len(q)-1),key=lambda i:float(np.linalg.norm(q[i]-point)))
                gradient[i]+=np.asarray(direction)*deficit
        observed.update(deficit=maximum_deficit,radius=maximum_radius)
        return cost,gradient
    def verify(q):
        ok,_,data=g.irrigation_model_cut_preflight(context,trial(q),props,model,
            _model_tree=tree,_model_solid_report=report)
        return bool(ok and data.get('status') in {'green','orange'})
    implant=entry.get('implant')
    if not g.is_valid_implant_obj(implant):
        return None,dict(status='NO_SAFE_ROUTE',reason='Falta el implante para orientar el desvío.')
    axis=g.get_implant_axis_world(props,implant)
    initial_cost,_=assess(controls)
    if not np.isfinite(initial_cost) or observed.get('radius',0.)<=0:
        return None,dict(status='NO_SAFE_ROUTE',reason='No se puede medir la invasión del recorrido.')
    limits=adaptive_limits(observed['radius'],observed['deficit'],float(np.linalg.norm(np.diff(controls[1:],axis=0),axis=1).sum()))
    points,receipt=reroute(controls,assess,verify,preferred_axis=np.asarray(axis,float),
                           initial_step_mm=limits['initial_step_mm'],max_offset_mm=limits['max_offset_mm'])
    receipt['adaptive_search']=limits
    return points,receipt


def write_controls(curve,points):
    spline=curve.data.splines[0]
    if spline.type!='BEZIER':raise ValueError('La curva editable no es Bezier.')
    if len(points)<len(spline.bezier_points):raise ValueError('No se reducen los controles existentes.')
    if len(points)>len(spline.bezier_points):spline.bezier_points.add(len(points)-len(spline.bezier_points))
    inverse=curve.matrix_world.inverted_safe()
    for index,(control,point) in enumerate(zip(spline.bezier_points,points)):
        control.co=inverse@Vector(point)
        control.handle_left_type=control.handle_right_type='VECTOR' if index<2 else 'AUTO'
    curve.data.update_tag()
