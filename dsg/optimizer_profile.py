"""Fixed optimizer profile; evidence references and limits in docs/PERFIL_MINIMO_9_22_11.md.

Search bounds and sampling are engineering defaults, not clinical consensus.
The isotropic 1.6 mm reserve is a conservative proxy, not a measured buccal wall.
"""
def settings():
    return dict(max_shift_mm=3.,max_tilt_deg=5.,max_depth_mm=1.5,anatomical_frame_max_angle_deg=15.,
                boundary_reserve_mm=1.6,cervical_free_mm=1.,min_coverage=.8,
                budget=90,min_gain=.03,size_policy='LARGEST',
                max_diameter_mm=0.,max_length_mm=0.,sinus_invasion_mm=2.,
                min_apical_mm=3.,explain_rejections=True,graft_gap_mm=0.,
                mpr_guided_selection=True,combine_size_position=True,section_search=True,sinus_length_threshold_mm=10.,profile='LENGTH_DEPENDENT_SINUS_92219')

def margins(tooth=1.5,nerve=2.,implant=3.):
    import math
    if not all(math.isfinite(float(v)) for v in (tooth,nerve,implant)):
        raise ValueError('Margen de seguridad no verificable.')
    return dict(tooth=max(1.5,float(tooth)),nerve=max(2.,float(nerve)),
                implant=max(3.,float(implant)),cavity=0.)
