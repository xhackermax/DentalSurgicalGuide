"""Exact signed distance to the union of linearly interpolated solid balls."""
import numpy as np

def capsule_sdf(points,a,b,ra,rb):
 points=np.asarray(points,float);a=np.asarray(a,float);b=np.asarray(b,float);ra=float(ra);rb=float(rb);delta=b-a;length=float(np.linalg.norm(delta))
 if min(ra,rb)<=0 or not np.isfinite([*a,*b,ra,rb]).all():raise ValueError('INVALID_VARIABLE_CAPSULE')
 if length<1e-12:return np.linalg.norm(points-a,axis=-1)-max(ra,rb)
 k=(rb-ra)/length
 if abs(k)>=1.-1e-12:
  center,r=(b,rb)if rb>=ra else(a,ra);return np.linalg.norm(points-center,axis=-1)-r
 axis=delta/length;x=points-a;z=x@axis;rho2=np.maximum(0.,np.sum(x*x,axis=-1)-z*z);s=np.clip(z+k*np.sqrt(rho2/(1.-k*k)),0.,length)
 return np.sqrt((z-s)**2+rho2)-(ra+k*s)
