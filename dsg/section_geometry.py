"""Parallel mesh sections, filled by even/odd scanline parity (mm).

Preserves inner contours and disconnected components. This is a sampled stack,
not a projection and not a certificate for geometry between sampled planes.
"""
import numpy as np

def raster_sections(vertices,faces,x,y,z):
    v=np.asarray(vertices,float);f=np.asarray(faces,int)
    x,y,z=(np.asarray(a,float) for a in (x,y,z))
    if v.ndim!=2 or v.shape[1]!=3 or not np.isfinite(v).all():raise ValueError('Malla de cortes inválida.')
    if f.ndim!=2 or f.shape[1]!=3 or not len(f):raise ValueError('Faltan triángulos para los cortes.')
    if not all(a.ndim==1 and len(a)>0 and np.isfinite(a).all() and np.all(np.diff(a)>0) for a in (x,y,z)):
        raise ValueError('Rejilla de cortes inválida.')
    triangles=v[f]
    # Do not clip on the left in X: crossings outside the ROI establish parity.
    low=triangles.min(axis=1);high=triangles.max(axis=1)
    keep=(low[:,1]<=y[-1])&(high[:,1]>=y[0])&(low[:,2]<=z[-1])&(high[:,2]>=z[0])&(low[:,0]<=x[-1])
    triangles=triangles[keep];low=low[keep,2];high=high[keep,2]
    out=np.zeros((len(z),len(y),len(x)),bool)
    for iz,height in enumerate(z):
        tri=triangles[(low<=height)&(high>height)]
        if not len(tri):continue
        a=tri;b=np.roll(tri,-1,axis=1)
        cross=((a[:,:,2]<=height)&(b[:,:,2]>height))|((b[:,:,2]<=height)&(a[:,:,2]>height))
        counts=cross.sum(axis=1)
        if np.any(counts!=2):raise ValueError('Intersección de corte ambigua; se requiere revisión 3D.')
        aa=a[cross].reshape(-1,2,3);bb=b[cross].reshape(-1,2,3)
        ratio=(height-aa[:,:,2])/(bb[:,:,2]-aa[:,:,2])
        segments=aa[:,:,:2]+ratio[:,:,None]*(bb[:,:,:2]-aa[:,:,:2])
        a=segments[:,0];b=segments[:,1]
        for iy,row in enumerate(y):
            hit=((a[:,1]<=row)&(b[:,1]>row))|((b[:,1]<=row)&(a[:,1]>row))
            if not hit.any():continue
            aa=a[hit];bb=b[hit]
            crossings=aa[:,0]+(row-aa[:,1])*(bb[:,0]-aa[:,0])/(bb[:,1]-aa[:,1])
            crossings.sort()
            out[iz,iy]=(np.searchsorted(crossings,x,side='right')%2)==1
    return out
