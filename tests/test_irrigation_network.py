"""Pure tests for the sequential-opening irrigation network (no Blender)."""
from __future__ import annotations

import math

import pytest

from dsg import irrigation_network as net


def straight(length, radius=0.5, step=0.25, inlet=True):
    """Trunk along +X from sleeve A (x=0) to the inlet; Ø4 inlet like DSG."""
    n = int(round(length / step))
    out = []
    for i in range(n + 1):
        x = i * step
        r = radius
        if inlet and x >= length - 4.0:
            r = 2.0
        elif inlet and x >= length - 6.0:
            r = radius + (2.0 - radius) * (x - (length - 6.0)) / 2.0
        out.append(((x, 0.0, 0.0), r))
    return out


def link_r(length):
    return net.resistance(straight(length, inlet=False))


def test_resistance_matches_poiseuille_for_uniform_tube():
    tube = straight(10.0, radius=0.5, inlet=False)
    assert net.resistance(tube) == pytest.approx(10.0 / 1.0 ** 4)
    assert net.resistance(tube, 2.0, 5.0) == pytest.approx(3.0)


def test_project_arclength():
    pts = [(0, 0, 0), (10, 0, 0), (10, 10, 0)]
    s, d = net.project_arclength(pts, (10.5, 4.0, 0))
    assert s == pytest.approx(14.0) and d == pytest.approx(0.5)


def test_order_is_from_A_towards_the_inlet():
    trunk = straight(40.0)
    design = net.design_sequential_network("A", trunk, [
        net.Branch("C", 22.0, link_r(8.0)), net.Branch("B", 10.0, link_r(8.0))])
    assert design.order == ["A", "B", "C"]
    assert [j.order for j in design.junctions] == [2, 3]


def test_only_A_open_gets_all_the_water():
    design = net.design_sequential_network("A", straight(40.0), [
        net.Branch("B", 10.0, link_r(8.0)), net.Branch("C", 22.0, link_r(8.0))])
    first = design.stages[0]
    assert first["open"] == ["A"] and first["shares"] == {"A": pytest.approx(1.0)}


@pytest.mark.parametrize("target", [0.6, 0.75, 0.8])
def test_each_newly_opened_branch_gets_the_target_share(target):
    policy = net.NetworkPolicy(target_open_branch_share=target)
    design = net.design_sequential_network("A", straight(60.0), [
        net.Branch("B", 12.0, link_r(9.0)), net.Branch("C", 26.0, link_r(12.0)),
        net.Branch("D", 40.0, link_r(6.0))], policy)
    assert not design.warnings, design.warnings
    for stage, name in zip(design.stages[1:], ["B", "C", "D"]):
        assert stage["shares"][name] >= target - 1e-6
        assert sum(stage["shares"].values()) == pytest.approx(1.0)


def test_unreachable_target_is_warned_with_the_real_prediction():
    design = net.design_sequential_network("A", straight(60.0), [
        net.Branch("B", 12.0, link_r(9.0))], net.NetworkPolicy(target_open_branch_share=0.95))
    assert design.warnings and "B" in design.warnings[0]
    assert design.stages[1]["shares"]["B"] == pytest.approx(design.junctions[0].predicted_share_at_opening)


def test_flow_to_A_decreases_as_branches_open():
    design = net.design_sequential_network("A", straight(60.0), [
        net.Branch("B", 12.0, link_r(9.0)), net.Branch("C", 26.0, link_r(9.0))])
    a_share = [s["shares"]["A"] for s in design.stages]
    assert a_share[0] == pytest.approx(1.0) and a_share[0] > a_share[1] > a_share[2]


def test_throats_sit_on_the_trunk_towards_A_and_are_printable():
    policy = net.NetworkPolicy()
    design = net.design_sequential_network("A", straight(60.0), [
        net.Branch("B", 12.0, link_r(9.0)), net.Branch("C", 26.0, link_r(9.0))], policy)
    for j in design.junctions:
        if j.throat.active:
            assert policy.min_throat_diameter_mm - 1e-9 <= j.throat.diameter_mm <= policy.max_throat_diameter_mm + 1e-9
            assert j.throat.length_mm <= j.room_mm + 1e-9


def test_long_downstream_path_needs_no_throat():
    # A is very far from the split and the branch is short: the branch already dominates.
    design = net.design_sequential_network("A", straight(80.0), [net.Branch("B", 60.0, link_r(2.0))])
    assert not design.junctions[0].throat.active
    assert design.stages[1]["shares"]["B"] >= 0.75


def test_no_room_is_reported_not_hidden():
    design = net.design_sequential_network("A", straight(30.0), [net.Branch("B", 2.0, link_r(20.0))])
    j = design.junctions[0]
    assert not j.throat.exact and j.throat.limited_by
    assert design.warnings


def test_solve_throat_adds_requested_resistance():
    policy = net.NetworkPolicy()
    t = net.solve_throat(1.0, 5.0, policy)
    assert t.exact and t.added_resistance == pytest.approx(1.0, rel=1e-6)
    assert net.solve_throat(0.0, 5.0, policy) is net.NO_THROAT


def test_design_serialises():
    d = net.design_sequential_network("A", straight(40.0), [net.Branch("B", 12.0, link_r(8.0))]).as_dict()
    assert d["schema"] == "dsg.irrigation_sequential_network.v1"
    assert d["perforation_order"] == ["A", "B"]
    assert math.isfinite(d["junctions"][0]["throat"]["diameter_mm"])


def test_policy_validation():
    with pytest.raises(ValueError):
        net.NetworkPolicy(target_open_branch_share=0.3)
    with pytest.raises(ValueError):
        net.NetworkPolicy(min_throat_diameter_mm=1.2)


def test_point_at_arclength():
    p, t = net.point_at_arclength([(0, 0, 0), (10, 0, 0), (10, 10, 0)], 12.0)
    assert p == pytest.approx((10.0, 2.0, 0.0)) and t == pytest.approx((0.0, 1.0, 0.0))


def test_split_placement_respects_sleeve_inlet_and_spacing():
    rules = net.PlacementRules(min_from_source_sleeve_mm=3.0, min_from_inlet_mm=7.5, min_split_spacing_mm=4.5)
    assert net.choose_split_arclength(1.0, [], 40.0, rules) == pytest.approx(3.0)
    assert net.choose_split_arclength(39.0, [], 40.0, rules) == pytest.approx(32.5)
    assert net.choose_split_arclength(15.0, [], 40.0, rules) == pytest.approx(15.0)
    s = net.choose_split_arclength(15.0, [14.0], 40.0, rules)
    assert s == pytest.approx(18.5)
    # 10 is blocked by both neighbours: nearest free point is 3.5 (8 - 4.5), not 20.5.
    assert net.choose_split_arclength(10.0, [8.0, 16.0], 40.0, rules) == pytest.approx(3.5)
    assert net.choose_split_arclength(10.0, [], 9.0, rules) is None
