import sys,numpy as np
sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
from dsg.irrigation_reroute import reroute
p=np.array([[-4.,0,0],[-3,0,0],[0,0,0],[4,0,0]])
def assess(q):
 cost=0.;gradient=np.zeros_like(q)
 for a,b in zip(q,q[1:]):
  for t in np.linspace(0,1,41):
   x=a+(b-a)*t;length=np.linalg.norm(x);deficit=max(0.,1.25-length)
   if deficit:
    cost+=deficit**2
    i=min(range(2,len(q)-1),key=lambda i:np.linalg.norm(q[i]-x))
    gradient[i]+=(x/length if length>1e-6 else np.array([0,0,1.]))*deficit
 return cost,gradient
out,report=reroute(p,assess,lambda q:assess(q)[0]<1e-8)
assert report['status']=='SAFE' and out is not None,report
assert np.array_equal(out[[0,1,-1]],p[[0,1,-1]])
assert np.array_equal(p[2],[0,0,0])
failed,report=reroute(p,lambda q:(1.,np.zeros_like(q)),lambda q:False,max_iterations=3)
assert failed is None and report['status']=='NO_SAFE_ROUTE'
print('IRRIGATION_LOCAL_REROUTE_ENDPOINTS_IMMUTABLE_AND_FAIL_CLOSED_PASS')
# An oblique implant axis is preferred over world-axis detours.
axis=np.array([1.,1.,1.]);axis/=np.linalg.norm(axis)
def axis_assess(q):
 displacement=q[2]-p[2]
 residual=max(0.,1.-float(displacement@axis))
 gradient=np.zeros_like(q);gradient[2]=axis*residual
 return residual*residual,gradient
out,report=reroute(p,axis_assess,lambda q:axis_assess(q)[0]<1e-9,preferred_axis=axis)
assert report['strategy']=='IMPLANT_AXIS'
assert np.linalg.norm(np.cross(out[2]-p[2],axis))<1e-8
assert np.array_equal(out[[0,1,-1]],p[[0,1,-1]])
print('IRRIGATION_IMPLANT_AXIS_PRIORITY_PASS')
# Search scale is case-dependent, not a fixed 1.5 mm displacement.
from dsg.irrigation_reroute import adaptive_limits
small=adaptive_limits(.5,.1,8.)
large=adaptive_limits(2.,1.,30.)
assert small['initial_step_mm']<large['initial_step_mm']
assert small['max_offset_mm']<large['max_offset_mm']
print('IRRIGATION_CASE_ADAPTIVE_SEARCH_LIMITS_PASS')
