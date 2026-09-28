"""Unit tests for the pure export quality gate (no Blender needed)."""
from __future__ import annotations

import json

import numpy as np
import pytest

from dsg.guide_export import mesh_checks as mc
from dsg.guide_export import report as rp
from dsg.guide_export.policy import ExportPolicy
from dsg.guide_export.service import ExportGate, ExportOptions, summarize


def box(size=(10.0, 10.0, 2.0), offset=(0.0, 0.0, 0.0)):
    sx, sy, sz = size
    ox, oy, oz = offset
    v = np.array([[x, y, z] for x in (0, sx) for y in (0, sy) for z in (0, sz)], float) + (ox, oy, oz)
    # outward-oriented triangles (vertex index = 4x + 2y + z)
    quads = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    t = []
    for a, b, c, d in quads:
        t += [(a, b, c), (a, c, d)]
    return v, np.array(t)


def merge(*meshes):
    vs, ts, off = [], [], 0
    for v, t in meshes:
        vs.append(v); ts.append(t + off); off += len(v)
    return np.vstack(vs), np.vstack(ts)


def test_box_is_outward_closed_solid():
    v, t = box()
    assert mc.signed_volume_mm3(v, t) == pytest.approx(200.0)
    assert mc.manifold_report(v, t).status == "PASS"


def test_open_mesh_blocks_unless_overridden():
    v, t = box()
    r = mc.manifold_report(v, t[:-1])
    assert r.status == "FAIL" and r.blocking and r.metrics["boundary_edges"] == 3
    gate = ExportGate(ExportPolicy(), ExportOptions(allow_non_manifold=True, check_wall_thickness=False),
                      arrays=lambda _o: (v, t[:-1]))
    assert not any(c.blocking for c in gate.check_solid(None))


def test_flipped_triangle_is_detected():
    v, t = box()
    t = t.copy(); t[0] = t[0][::-1]
    assert mc.manifold_report(v, t).metrics["inconsistent_orientation_edges"] > 0


def test_islands_debris_is_auto_removable_but_detached_part_is_not():
    guide = box((20, 20, 3))
    debris = box((0.2, 0.2, 0.2), (50, 0, 0))       # 0.008 mm³
    sleeve = box((5, 5, 5), (80, 0, 0))            # 125 mm³
    v, t = merge(guide, debris)
    assert mc.island_removal_decision(mc.islands(v, t)).status == "WARN"
    v, t = merge(guide, debris, sleeve)
    decision = mc.island_removal_decision(mc.islands(v, t))
    assert decision.blocking and decision.metrics["significant_islands"] == 1


def test_island_confirmation_turns_block_into_warning():
    v, t = merge(box((20, 20, 3)), box((5, 5, 5), (80, 0, 0)))
    gate = ExportGate(ExportPolicy(), ExportOptions(confirm_island_removal=True), arrays=lambda _o: (v, t))
    r = gate.check_islands(None)
    assert r.status == "WARN" and not r.blocking and "confirmation" in r.message


def test_connected_components_long_chain_converges():
    n = 2000
    t = np.array([(i, i + 1, i + 2) for i in range(n - 2)])
    assert len(np.unique(mc.connected_components(n, t))) == 1


@pytest.mark.parametrize("thickness,expected", [(2.0, "PASS"), (0.6, "WARN")])
def test_wall_thickness_on_slab(thickness, expected):
    v, t = box((10, 10, thickness))
    r = mc.wall_thickness_report(v, t, mc.NumpyRayCaster(v, t), ExportPolicy(min_wall_thickness_mm=1.0))
    assert r.status == expected
    assert r.metrics["min_mm"] == pytest.approx(thickness, abs=1e-3)


def test_thin_wall_blocks_only_when_policy_says_so():
    v, t = box((10, 10, 0.5))
    r = mc.wall_thickness_report(v, t, mc.NumpyRayCaster(v, t), ExportPolicy(block_thin_walls=True))
    assert r.status == "FAIL" and r.blocking


def test_canal_clearance_statuses():
    assert mc.clearance_status("c", 3.1, 2.0).status == "PASS"
    assert mc.clearance_status("c", 1.2, 2.0).status == "WARN"
    assert mc.clearance_status("c", 0.0, 2.0, intersects=True).status == "WARN"
    assert mc.clearance_status("c", None, 2.0).status == "SKIPPED"


def test_gate_anatomy_without_canal_is_skipped_not_passed():
    gate = ExportGate(ExportPolicy(), ExportOptions(), clearance=lambda a, b: (5.0, False, "X"))
    class Obj:  # minimal stand-in
        name = "Implant_36"
    assert gate.check_anatomy([Obj()], None)[0].status == "SKIPPED"
    assert gate.check_anatomy([Obj()], object())[0].status == "PASS"


def test_policy_rejects_invalid_thresholds():
    with pytest.raises(ValueError):
        ExportPolicy(min_wall_thickness_mm=-1)


def test_report_is_complete_and_written_atomically(tmp_path):
    stl = tmp_path / "DSG_Guide_case.stl"
    stl.write_bytes(b"solid x\nendsolid x\n")
    ctx = rp.ExportContext(dsg_version="9.7.0", blender_version="5.2.2", case_name="case",
                           implants=[rp.ImplantRecord(name="Implant_36", fdi=36, diameter_mm=4.1)])
    checks = [mc.CheckResult("closed_solid", "PASS", "ok"), mc.CheckResult("wall_thickness", "WARN", "thin")]
    data = rp.build_report(ctx, checks, stl, stl_sha256=rp.sha256_file(stl))
    path = rp.write_report(data, stl)
    loaded = json.loads(path.read_text("utf-8"))
    assert path.name == "DSG_Guide_case.dsg-report.json"
    assert loaded["schema"] == rp.SCHEMA and loaded["quality"]["overall"] == "WARN"
    assert loaded["output"]["stl_sha256"] == rp.sha256_file(stl)
    assert loaded["implants"][0]["fdi"] == 36
    assert "WARN" in summarize(checks) or "warning" in summarize(checks)
