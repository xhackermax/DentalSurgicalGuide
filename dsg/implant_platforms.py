"""Narrow / standard / wide grouping of catalogue sizes (pure Python).

Catalogues that name their prosthetic platform per reference (MIS NP/SP/WP,
Straumann NNC/RN/WN, Klockner MV/NV/RV, Astra EV x.x) are grouped by that
name.  Single-connection catalogues (e.g. BTI CORE-X, one 3.5 connection for
every diameter) carry no platform, so the usual clinical diameter classes are
used: narrow < 3.75 mm, standard 3.75–4.25 mm, wide ≥ 4.5 mm.  This is a
size grouping for the proposal, not a prosthetic compatibility statement.
"""
NARROW, STANDARD, WIDE = 'NARROW', 'STANDARD', 'WIDE'
ORDER = (NARROW, STANDARD, WIDE)
LABELS = {NARROW: 'Estrecha (narrow)', STANDARD: 'Estándar (standard)', WIDE: 'Ancha (wide)'}
SHORT = {NARROW: 'Narrow', STANDARD: 'Standard', WIDE: 'Wide'}

_NAMED = {
    'NP': NARROW, 'NV': NARROW, 'MV': NARROW, 'NNC': NARROW, 'NC': NARROW,
    'SP': STANDARD, 'RP': STANDARD, 'RV': STANDARD, 'RN': STANDARD, 'RC': STANDARD,
    'WP': WIDE, 'WN': WIDE, 'WV': WIDE,
}
STANDARD_FROM_MM = 3.75
WIDE_FROM_MM = 4.5


def by_diameter(diameter_mm):
    d = float(diameter_mm)
    if d < STANDARD_FROM_MM - 1e-6:
        return NARROW
    if d < WIDE_FROM_MM - 1e-6:
        return STANDARD
    return WIDE


def platform_class(asset):
    """NARROW / STANDARD / WIDE for one catalogue row."""
    name = str(asset.get('platform', '') or '').strip().upper()
    if name in _NAMED:
        return _NAMED[name]
    if name.startswith('EV'):
        try:
            return by_diameter(float(name[2:].strip()))
        except ValueError:
            pass
    return by_diameter(asset['diameter_mm'])


def platform_label(asset):
    """Readable platform of a row, with the catalogue name when it has one."""
    group = SHORT[platform_class(asset)]
    name = str(asset.get('platform', '') or '').strip()
    return f'{group} ({name})' if name else group
