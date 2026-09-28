"""Sequential-opening irrigation network in real Blender (bpy 5.2).

Scene: three implants in a row; the main channel starts at sleeve A
(DSG_Implant_01) and runs past B and C to an inlet in the air. B and C are
linked with "Link selected" (given in reverse order on purpose).
"""
from __future__ import annotations

import json

import pytest

pytestmark = pytest.mark.requires_bpy

from irrigation_scene import A, B, C, build_linked_network


@pytest.fixture(scope="module")
def network():
    g, props, teardown = build_linked_network()
    yield g, props
    teardown()


def _entries(g, props):
    entries = g.load_irrigation_path_entries(props)
    source = [e for e in entries if not e["link"]][0]
    links = [e for e in entries if e["link"]]
    return source, links


def test_link_selected_creates_one_branch_per_implant_on_the_main_trunk(network):
    g, props = network
    source, links = _entries(g, props)
    assert source["implant_name"] == A
    assert sorted(e["implant_name"] for e in links) == [B, C]
    assert all(int(e["source_index"]) == int(source["index"]) for e in links)


def test_roles_initial_open_linked_frangible_ordered_along_trunk(network):
    import bpy
    g, props = network
    objs = {n: bpy.data.objects[n] for n in (A, B, C)}
    assert not g.irrigation_implant_is_sealed(objs[A])
    assert g.irrigation_implant_is_sealed(objs[B]) and g.irrigation_implant_is_sealed(objs[C])
    # Selected as "C,B" but ordered by position: B's Y is nearer to A.
    assert [objs[n]["DSG_irrigation_open_order"] for n in (A, B, C)] == [1, 2, 3]
    assert objs[A]["DSG_irrigation_network_role"] == "SOURCE_OPEN"


def test_design_gives_each_newly_opened_sleeve_most_of_the_water(network):
    g, props = network
    design = g.irrigation_network_summary(props)[0]
    target = design["policy"]["target_open_branch_share"]
    assert design["perforation_order"] == [A, B, C]
    stages = design["stages"]
    assert stages[0]["shares"] == {A: pytest.approx(1.0)}
    assert stages[1]["shares"][B] >= target - 1e-6
    assert stages[2]["shares"][C] >= target - 1e-6
    assert stages[2]["shares"][A] < stages[1]["shares"][A] < 1.0


def test_trunk_is_throttled_towards_A_and_links_keep_full_lumen(network):
    g, props = network
    source, links = _entries(g, props)
    balances = g._calculate_midpoint_wye_balances(source, links, props)
    assert balances["mode"] == "SEQUENTIAL_OPENING"
    ordered = g.order_links_along_trunk(source, links, props)
    trunk = g._apply_entry_midpoint_geometry(g._entry_lumen_samples(source, props), source, ordered)
    throttled = g._apply_entry_balancing(trunk, source, ordered, balances)
    for throat in balances["throats"]:
        assert throat["diameter"] < 1.0
        assert min(r for _p, r in throttled) == pytest.approx(min(t["diameter"] for t in balances["throats"]) / 2, abs=0.02)
    for link in links:
        samples = g._entry_lumen_samples(link, props)
        assert g._apply_entry_balancing(samples, link, ordered, balances) == [(p, r) for p, r in samples]


def test_legacy_mode_keeps_full_lumen(network):
    g, props = network
    source, links = _entries(g, props)
    props.irr_sequential_opening = False
    try:
        assert g._calculate_midpoint_wye_balances(source, links, props) == {}
    finally:
        props.irr_sequential_opening = True


def test_y_network_cutter_and_wall_build_in_sequential_mode(network):
    import bpy
    g, props = network
    source, links = _entries(g, props)
    cutter = g.build_irrigation_y_network_lumen_cutter(bpy.context, source, links, props, name="T_Cut")
    wall = g.build_irrigation_y_network_hollow_wall(bpy.context, source, links, props, name="T_Wall")
    try:
        assert cutter is not None and cutter["DSG_irrigation_balancing_mode"] == "SEQUENTIAL_OPENING_TRUNK_THROATS"
        assert wall is not None and wall["DSG_irrigation_balancing_mode"] == "SEQUENTIAL_OPENING_TRUNK_THROATS"
    finally:
        for obj in (cutter, wall):
            if obj is not None:
                bpy.data.objects.remove(obj, do_unlink=True)


def test_frangible_wall_is_100_microns_closed_and_numbered(network):
    import bpy
    from dsg.guide_export import blender_adapter, mesh_checks
    g, props = network
    seal, message = g.build_frangible_irrigation_seal_object(bpy.context, props, bpy.data.objects[B])
    try:
        assert seal is not None, message
        assert seal["DSG_seal_center_thickness_mm"] == pytest.approx(0.10)
        assert seal["DSG_irrigation_open_order"] == 2
        v, t = blender_adapter.mesh_arrays(seal)
        assert mesh_checks.manifold_report(v, t).status == "PASS"
        # One membrane per outlet (C mode: two), thin centre / thick rim.
        assert len(mesh_checks.islands(v, t)) == seal["DSG_seal_outlet_count"] == 2
        assert seal["DSG_seal_rim_thickness_mm"] == pytest.approx(0.25)
    finally:
        if seal is not None:
            bpy.data.objects.remove(seal, do_unlink=True)


def test_apply_irrigation_runs_and_records_the_network(network):
    import bpy
    g, props = network
    assert bpy.ops.dsg.confirm_irrigation() == {"FINISHED"}
    stored = json.loads(props.guide_obj["DSG_irrigation_network_json"])
    assert stored[0]["perforation_order"] == [A, B, C]
    assert json.loads(props.guide_obj["DSG_irrigation_sealed_implants"]) == sorted([B, C]) or \
        set(json.loads(props.guide_obj["DSG_irrigation_sealed_implants"])) == {B, C}


def test_network_panel_draws(network):
    g, props = network
    calls = []

    class Layout:
        def __getattr__(self, name):
            def call(*args, **kwargs):
                calls.append((name, args, kwargs))
                return self
            return call

        def __setattr__(self, name, value):
            calls.append(("set", name, value))

    g._draw_irrigation_sequential_network(Layout(), props)
    labels = " ".join(str(kw.get("text", "")) for n, _a, kw in calls if n == "label")
    assert "1 · DSG_Implant_01" in labels and "2 · DSG_Implant_02" in labels and "3 · DSG_Implant_03" in labels
