"""Finite, reproducible search frames derived from the immutable case snapshot."""
import numpy as np
from .implant_optimization import _matrix


def search_frames(request):
    base=_matrix(request['implant']['matrix']);platform=np.asarray(request['platform'],float)
    out=[{'id':'PLACED','matrix':base.tolist(),'angle_deg':0.}]
    fdi=int(request.get('target_fdi') or 0)
    sockets=[s for s in request.get('sockets',[]) if fdi and int(s.get('fdi') or 0)==fdi]
    if len(sockets)!=1:return out
    tooth=sockets[0];local=np.load(tooth['vertices_path'],allow_pickle=False)
    m=_matrix(tooth['matrix']);points=local@m[:3,:3].T+m[:3,3]
    if len(points)<4 or not np.isfinite(points).all():return out
    values,vectors=np.linalg.eigh(np.cov(points.T))
    if values[-2]<=0 or values[-1]<1.5*values[-2]:return out
    original=base[:3,2]/np.linalg.norm(base[:3,2]);axis=vectors[:,-1]
    if axis@original<0:axis=-axis
    cosine=float(np.clip(axis@original,-1,1));angle=float(np.degrees(np.arccos(cosine)))
    # A bounded engineering search seed, not a prescribed clinical angle.
    limit=float(request.get('settings',{}).get('anatomical_frame_max_angle_deg',15.))
    if not np.isfinite(limit) or not 0<=limit<=15.:raise ValueError('Límite de búsqueda anatómica inválido.')
    if angle<.1 or angle>limit:return out
    v=np.cross(original,axis)
    skew=np.array([[0,-v[2],v[1]],[v[2],0,-v[0]],[-v[1],v[0],0]])
    rotation=np.eye(3)+skew+skew@skew/(1+cosine)
    seed=base.copy();seed[:3,:3]=rotation@base[:3,:3]
    local_platform=(np.linalg.inv(base)@np.r_[platform,1.])[:3]
    seed[:3,3]=platform-seed[:3,:3]@local_platform
    out.append({'id':'EXTRACTED_TOOTH:'+str(fdi),'matrix':seed.tolist(),'angle_deg':angle})
    return out


def frame_request(request,frame):
    return dict(request,implant=dict(request['implant'],matrix=frame['matrix']),axis_frame=frame)


def validate_candidate_reference(request,row):
    """Reconstruct the authorized frame; do not trust proposal-supplied axes."""
    identifier=row.get('axis_reference','PLACED')
    seed=next((f for f in search_frames(request) if f['id']==identifier),None)
    if seed is None:raise ValueError('El eje propuesto no pertenece a la búsqueda anatómica autorizada.')
    m=_matrix(row['matrix']);frame=np.asarray(seed['matrix'])[:3,:3]
    p=np.asarray(row['parameters'],float);settings=request['settings']
    if p.shape!=(5,) or not np.isfinite(p).all() or np.linalg.norm(p[:2])>settings['max_shift_mm']+1e-8 or abs(p[2])>settings.get('max_depth_mm',0.)+1e-8 or np.linalg.norm(p[3:])>1e-8:
        raise ValueError('La traslación propuesta supera los límites actuales.')
    if not np.allclose(m[:3,:3],frame,atol=1e-5):raise ValueError('La orientación no coincide con el eje validado.')
    actual=m[:3,:3]@np.asarray(row['asset']['platform_local_mm'])+m[:3,3]
    expected=np.asarray(request['platform'])+frame@p[:3]
    if not np.allclose(actual,expected,atol=1e-4):raise ValueError('La plataforma no coincide con la propuesta validada.')
    return seed
