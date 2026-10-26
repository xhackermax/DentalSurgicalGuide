"""User-configured planning rule, not a clinical consensus recommendation."""
import math
LENGTH_THRESHOLD_MM=10.
def permitted_invasion(length_mm,maximum_mm=2.):
    try:length=float(length_mm);maximum=float(maximum_mm)
    except (TypeError,ValueError):raise ValueError('Longitud o límite del seno no verificable.') from None
    if not math.isfinite(length) or length<=0 or not math.isfinite(maximum) or maximum<0:
        raise ValueError('Longitud o límite del seno no verificable.')
    return min(2.,maximum) if length<LENGTH_THRESHOLD_MM else 0.
