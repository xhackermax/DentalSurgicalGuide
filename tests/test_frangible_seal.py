"""Pure geometry tests for the frangible irrigation wall and its marks."""
from __future__ import annotations

import math

import numpy as np
import pytest

from dsg import frangible_seal as fs
from dsg.guide_export import mesh_checks as mc


def tri(verts, faces):
    t = []
    for f in faces:
        for i in range(1, len(f) - 1):
            t.append((f[0], f[i], f[i + 1]))
    return np.array(verts), np.array(t)


def test_membrane_is_closed_outward_and_has_the_expected_volume():
    d = fs.SealDesign()
    lumen = 0.5
    v, t = tri(*fs.revolve(fs.membrane_profile(lumen, d), segments=96))
    assert mc.manifold_report(v, t).status == "PASS"
    R, rw = lumen + d.wall_overlap_mm, lumen * d.weak_radius_ratio
    expected = math.pi * rw ** 2 * d.membrane_center_mm + math.pi * (R ** 2 - rw ** 2) * d.membrane_rim_mm
    assert mc.signed_volume_mm3(v, t) == pytest.approx(expected, rel=2e-3)


def test_membrane_is_thin_in_the_centre_and_thick_at_the_rim():
    d = fs.SealDesign()
    v, t = tri(*fs.revolve(fs.membrane_profile(0.5, d), segments=64))
    caster = mc.NumpyRayCaster(v, t)
    for r, expected in ((0.0, d.membrane_center_mm), (0.5, d.membrane_rim_mm)):
        dist, _n = caster.cast(np.array([[r, 0.0, d.pocket_depth_mm - 1.0]]), np.array([[0.0, 0.0, 1.0]]), 5.0)
        # first hit = front face; thickness = second hit from just behind it
        start = d.pocket_depth_mm + 1e-4
        dist2, _ = caster.cast(np.array([[r, 0.0, start]]), np.array([[0.0, 0.0, 1.0]]), 5.0)
        assert dist[0] == pytest.approx(1.0, abs=1e-6)
        assert dist2[0] + 1e-4 == pytest.approx(expected, abs=1e-4)


def test_nothing_is_added_inside_the_drill_bore():
    d = fs.SealDesign()
    v, _f = fs.revolve(fs.membrane_profile(0.5, d))
    assert min(z for _x, _y, z in v) >= d.pocket_depth_mm > 0.0


def test_countersink_is_a_closed_cutter_starting_inside_the_bore():
    d = fs.SealDesign()
    v, t = tri(*fs.revolve(fs.countersink_profile(0.5, d)))
    assert mc.manifold_report(v, t).status == "PASS"
    assert v[:, 2].min() == pytest.approx(-d.bore_clearance_mm)
    assert v[:, 2].max() == pytest.approx(d.countersink_depth_mm)
    assert d.countersink_depth_mm < d.pocket_depth_mm


def test_marks_are_printable_for_direct_and_c_outlets():
    d = fs.SealDesign()
    assert d.validate_outlet(0.50) == []       # DIRECT Ø1 mm
    assert d.validate_outlet(0.18) == []       # C outlet Ø0.36 mm
    assert d.validate_outlet(0.10)             # too small is reported


def test_design_validation():
    with pytest.raises(ValueError):
        fs.SealDesign(membrane_center_mm=0.3, membrane_rim_mm=0.25)
    with pytest.raises(ValueError):
        fs.SealDesign(countersink_depth_mm=0.5, pocket_depth_mm=0.3)
