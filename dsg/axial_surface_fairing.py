"""One-sided heat fairing of a union: fill concave seams without eroding struts.

This is an independent level-set adaptation, not the PN-Loop algorithm.
The union is formed before fairing, so subdividing a route cannot add beads.
"""
import numpy as np
from scipy.ndimage import gaussian_filter

def fair_union_field(field,step_mm,minimum_radius_mm):
 sigma_mm=.85*float(minimum_radius_mm)
 smooth=gaussian_filter(field,sigma=sigma_mm/float(step_mm),mode='nearest',truncate=4.)
 np.minimum(smooth,field,out=smooth)
 return smooth
