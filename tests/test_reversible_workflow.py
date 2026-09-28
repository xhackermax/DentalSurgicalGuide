from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "dsg"


def test_dicom_checkpoint_protects_its_hidden_copies_and_restores_route_ssot():
    src = (ROOT / "core.py").read_text("utf-8")
    restore = src.split("def restore_dicom_route_checkpoint", 1)[1].split("class DSG_SUITE_OT_StartSimpleRoute", 1)[0]
    assert "DICOM_ROUTE_CHECKPOINT_COLLECTION" in restore
    assert "users_collection" in restore
    assert "workflow_route = restored_route" in restore


def test_back_can_cancel_active_async_segmentation_instead_of_being_dead():
    core = (ROOT / "core.py").read_text("utf-8")
    dicom = (ROOT / "_dicom_parts" / "06_operators_b.py").read_text("utf-8")
    assert "cancel_semantic_workflow(context" in core
    assert "def cancel_semantic_workflow(context" in dicom
    assert "restore_dicom_route_checkpoint(context)" in dicom


def test_alignment_modal_handles_back_request_and_ctrl_z_as_safe_rollback():
    src = (ROOT / "_alignment_parts" / "01_alignment_operators_ui.py").read_text("utf-8")
    modal = src.split("    def modal(self, context, event):", 1)[1].split("    def cancel(self, context):", 1)[0]
    assert 'event.type == \'Z\'' in modal
    assert "getattr(event, 'ctrl', False)" in modal
    assert 'DSG_alignment_cancel_requested' in modal
    assert "return self._rollback(context, \"\")" in modal
