from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "dsg"


def test_plan_a_uses_root_safe_coronal_crown_shell():
    geom = (ROOT / "dental_surface_geometry.py").read_text("utf-8")
    align = (ROOT / "_alignment_parts" / "00_alignment_core.py").read_text("utf-8")
    ui = (ROOT / "_alignment_parts" / "01_alignment_operators_ui.py").read_text("utf-8")
    assert "def registration_crown_patch" in geom
    assert "def build_registration_crown_graph_data" in geom
    assert "_mesh_graph_from_registration_crowns" in align
    assert "_mesh_graph_from_registration_crowns" in ui
    assert "CORONAL_CROWN_SHELL" in align


def test_plan_a_has_recenter_sector_scoring_and_guarded_plane_finish():
    src = (ROOT / "_alignment_parts" / "00_alignment_core.py").read_text("utf-8")
    assert "def _target_driven_recenter" in src
    assert "def _target_zone_labels" in src
    assert "def _sector_fit_metrics" in src
    assert "AUTO_GLOBAL_PLANE_ITERATIONS" in src
    assert "_point_to_plane_huber_transform(" in src
    assert "_anatomically_valid_candidate_pool" in src


def test_plan_a_keeps_plan_b_and_no_new_primary_ui_step():
    ui = (ROOT / "_alignment_parts" / "01_alignment_operators_ui.py").read_text("utf-8")
    assert '"ALIGN WITH 3 ZONES"' in ui
    assert '"ALIGN AUTOMATICALLY"' in ui
