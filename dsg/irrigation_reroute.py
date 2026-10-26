"""Bounded local centreline repair. Endpoints and sleeve contact never move."""
import numpy as np
import time


def adaptive_limits(radius_mm,penetration_mm,external_span_mm):
    radius=float(radius_mm);penetration=float(penetration_mm);span=float(external_span_mm)
    if not np.isfinite([radius,penetration,span]).all() or radius<=0 or penetration<0 or span<=0:
        raise ValueError('Escala local del recorrido inválida.')
    step=max(.05,min(.75,radius*.25,max(.1,penetration*.5)))
    reach=min(12.,max(step*4.,min(span*.35,2.*radius+2.*penetration)))
    return dict(initial_step_mm=step,max_offset_mm=reach,
                lumen_radius_mm=radius,initial_penetration_mm=penetration,external_span_mm=span)


def reroute(points,assess,verify,*,max_offset_mm=8.,max_iterations=24,max_seconds=20.,preferred_axis=None,initial_step_mm=.5):
    original=np.asarray(points,dtype=float).copy()
    if original.ndim!=2 or original.shape[1]!=3 or len(original)<4 or not np.isfinite(original).all():
        raise ValueError('El recorrido requiere controles intermedios finitos.')
    initial_step_mm=float(initial_step_mm)
    if not np.isfinite([initial_step_mm,max_offset_mm]).all() or initial_step_mm<=0 or max_offset_mm<=0:
        raise ValueError('Límites de búsqueda inválidos.')
    started=time.monotonic()
    current=original.copy();fixed=[0,1,len(original)-1]
    cost,gradient=assess(current);evaluated=0
    if verify(current):return current,dict(status='SAFE',iterations=0,evaluated=1,max_shift_mm=0.)
    basis=np.eye(3)
    if preferred_axis is not None:
        axis=np.asarray(preferred_axis,float)
        if axis.shape!=(3,) or not np.isfinite(axis).all() or np.linalg.norm(axis)<1e-8:
            raise ValueError('Eje de inserción del implante inválido.')
        axis=axis/np.linalg.norm(axis)
        u=np.cross(axis,np.eye(3)[int(np.argmin(abs(axis)))]);u/=np.linalg.norm(u)
        basis=np.asarray([axis,u,np.cross(axis,u)])
        # First try local lifts parallel to the actual implant, smallest first.
        distances=sorted(set(min(max_offset_mm,initial_step_mm*k) for k in (1,2,3,4,6,8,12,16))|{float(max_offset_mm)})
        for distance in distances:
            if distance>max_offset_mm:continue
            for sign in (1.,-1.):
                for i in range(2,len(original)-1):
                    if time.monotonic()-started>max_seconds:break
                    trial=original.copy();trial[i]+=axis*distance*sign
                    value,_=assess(trial);evaluated+=1
                    if value<max(1e-8,cost*.1) and verify(trial):
                        assert np.array_equal(trial[fixed],original[fixed])
                        return trial,dict(status='SAFE',strategy='IMPLANT_AXIS',axis_world=axis.tolist(),
                            evaluated=evaluated,iterations=1,max_shift_mm=distance)

    for iteration in range(max_iterations):
        if time.monotonic()-started>max_seconds:break
        best=None;best_cost=cost
        for i in range(2,len(current)-1):
            directions=list(basis)+list(-basis)
            norm=np.linalg.norm(gradient[i])
            if norm>1e-9:directions.insert(0,gradient[i]/norm)
            for direction in directions:
                for step in (initial_step_mm,initial_step_mm*2,initial_step_mm*4):
                    if time.monotonic()-started>max_seconds:break
                    trial=current.copy();trial[i]+=direction*step
                    if np.linalg.norm(trial[i]-original[i])>max_offset_mm+1e-8:continue
                    value,grad=assess(trial);evaluated+=1
                    if np.isfinite(value) and value<best_cost-1e-9:
                        best=trial;best_cost=value;best_gradient=grad
        if best is None:
            if initial_step_mm>.050001:
                initial_step_mm=max(.05,initial_step_mm*.5);continue
            break
        current=best;cost=best_cost;gradient=best_gradient
        if verify(current):
            assert np.array_equal(current[fixed],original[fixed])
            return current,dict(status='SAFE',strategy='LOCAL_AROUND_IMPLANT_AXIS' if preferred_axis is not None else 'LOCAL',iterations=iteration+1,evaluated=evaluated,
                max_shift_mm=float(np.linalg.norm(current-original,axis=1).max()))
    return None,dict(status='NO_SAFE_ROUTE',evaluated=evaluated,
                     reason='No hay un desvío seguro verificado con inicio, sleeve y final fijos.')
