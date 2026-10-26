"""Fixed automatic style and spatially distributed sparse frame origins."""
import numpy as np

def sparse_origins(rows,target):
 target=int(target);sids=sorted({r['target']for r in rows})
 if target<2*len(sids)or len(rows)<target:raise ValueError('INSUFFICIENT_SAFE_ORIGINS_FOR_HALF_DENSITY')
 selected=[];used=set()
 def add(options):
  options=[r for r in options if r['vertex']not in used]
  if not options:raise ValueError('INSUFFICIENT_DISTINCT_ORIGINS')
  if not selected:r=max(options,key=lambda r:r['distance'])
  else:r=max(options,key=lambda r:(min(np.linalg.norm(r['point']-p['point'])for p in selected),r['distance']))
  selected.append(r);used.add(r['vertex'])
 for sid in sids:
  group=[r for r in rows if r['target']==sid]
  first=max(group,key=lambda r:r['distance']);selected.append(first);used.add(first['vertex']);add(group)
 while len(selected)<target:add(rows)
 return selected
