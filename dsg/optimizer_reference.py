"""Deterministic catalogue ordering and a sampled local bone-crest reference.

The crest estimate is geometric, not a prescription of commercial implant
depth. No sinus surface is ever used as a cervical height reference.
"""
import math
import numpy as np


def crest_reference(native,x,y,z,cx,cy,*,radius=3.,minimum_samples=8):
    """Median coronal surface of a fixed 16-direction ring in native bone.

Use the same ring for every implant size. Require at least 0.5 mm of
consecutive native bone and eight distinct columns; thin isolated voxels or
highly inconsistent rim heights do not authorize an automatic reference.
"""
    x,y,z=map(np.asarray,(x,y,z))
    pitch=float(z[1]-z[0]);run=max(2,int(math.ceil(.5/pitch)))
    heights=[];directions=[];seen=set()
    for direction,angle in enumerate(np.arange(16)*2*math.pi/16):
        px=cx+radius*math.cos(angle);py=cy+radius*math.sin(angle)
        if px<x[0] or px>x[-1] or py<y[0] or py>y[-1]:continue
        ix=int(np.argmin(abs(x-px)));iy=int(np.argmin(abs(y-py)))
        if (ix,iy) in seen:continue
        seen.add((ix,iy))
        column=native[:,iy,ix]
        starts=np.flatnonzero(np.convolve(column.astype(np.int16),np.ones(run,dtype=np.int16),'valid')==run)
        # A surface must be observed. The upper map/FOV boundary is not bone
        # crest when the column continues beyond the sampled region.
        if len(starts) and starts[-1]+run<len(z):
            heights.append(float(z[starts[-1]+run-1]+pitch/2));directions.append(direction)
    if len(heights)<minimum_samples:return None
    if len({d//4 for d in directions})<4:return None
    gaps=np.diff(directions+[directions[0]+16])
    if max(gaps)>6:return None
    spread=float(np.percentile(heights,75)-np.percentile(heights,25))
    if spread>2.:return None
    return {'height_mm':float(np.median(heights)),'spread_mm':spread,'samples':len(heights),
            'method':'FIXED_RING_MEDIAN_NATIVE_CREST','radius_mm':float(radius),
            'sampled_quadrants':4}


def candidate_rank(row):
    """Ascending priority: length, diameter, crest agreement, contact, movement.

Stable geometric/id tie breaks prevent catalogue row order from choosing a
different proposal when all measured priorities are equal.
"""
    a=row['asset'];e=row['evaluation']
    return (-float(a['length_mm']),-float(a['diameter_mm']),
            abs(float(row.get('crest_error_mm',0.))),-round(float(e['score']),8),
            -round(float(e.get('mpr_wall_reserve_mm',0.)),6),
            round(float(row.get('movement_mm',0.)),8),
            tuple(round(float(v),8) for v in row.get('parameters',[])),str(a['id']))
