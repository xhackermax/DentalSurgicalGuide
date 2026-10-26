"""Geometry-derived MPR wall comparisons; no new clinical acceptance thresholds."""
import math


def wall_summary(surround, cervical_free_mm=1.):
    rows=[r for r in surround.get('rows', []) if r['depth_mm']>=float(cervical_free_mm)]
    if not rows:
        raise ValueError('No hay cortes de pared verificables bajo la banda cervical.')
    walls=[]
    for row in rows:
        value=row.get('wall_mm') if row.get('inside_bone') else 0.
        if value is None or not math.isfinite(float(value)) or float(value)<0:
            raise ValueError('Espesor de pared no verificable.')
        walls.append(float(value))
    return dict(status='MEASURED',minimum_wall_mm=min(walls),sampled_rays=len(rows),
                angular_directions=16,axial_levels=8,
                metric='SAMPLED_NATIVE_BONE_WALL_NOT_STABILITY')


def wall_bonus(wall_mm):
    value=float(wall_mm)
    if not math.isfinite(value) or value<0:
        raise ValueError('Reserva de pared inválida.')
    # Bounded engineering tie-break. Existing coverage and hard guards remain.
    return .2*value/(value+1.)
