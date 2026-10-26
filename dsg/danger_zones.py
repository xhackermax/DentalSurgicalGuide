"""Classify measured cavity relationships using the caller's effective limit.

The user-configured sinus allowance is 2 mm only below 10 mm implant length;
at 10 mm or longer it is zero. This is a planning preference, not a clinical
consensus recommendation. Nasal classification retains its existing numeric
noise handling.
"""

SAFE = 'SAFE'
ALERT = 'ALERT'
BLOCK = 'BLOCK'

SINUS_MAX_MM = 2.0
NASAL_ALERT_MM = 1.0
TOLERANCE_MM = 0.05  # numeric noise of a voxel surface, never counted as invasion


def is_sinus(kind):
    return 'sinus' in str(kind)


def classify(kind, penetration_mm, clearance_mm, sinus_max_mm=SINUS_MAX_MM, nasal_alert_mm=NASAL_ALERT_MM):
    """Status and message for one zone.

    ``penetration_mm``: deepest implant point inside the zone (0 if none).
    ``clearance_mm``: shortest distance from the implant to the zone when it
    does not enter it (``None`` when unknown / far).
    """
    depth = max(0.0, float(penetration_mm))
    if is_sinus(kind):
        limit = max(0.0, min(SINUS_MAX_MM, float(sinus_max_mm)))
        if depth > limit:
            return BLOCK, f'invade {depth:.1f} mm el seno (máximo {limit:.1f} mm)'
        if depth > 0.:
            return ALERT, f'invade {depth:.1f} mm el seno (permitido hasta {limit:.1f} mm)'
        return SAFE, _free(clearance_mm)
    if depth > TOLERANCE_MM:
        return BLOCK, f'invade {depth:.1f} mm la cavidad nasal (no permitido)'
    if clearance_mm is not None and float(clearance_mm) < float(nasal_alert_mm):
        return ALERT, f'a {float(clearance_mm):.1f} mm de la cavidad nasal'
    return SAFE, _free(clearance_mm)


def _free(clearance_mm):
    return 'libre' if clearance_mm is None else f'libre · {float(clearance_mm):.1f} mm'
