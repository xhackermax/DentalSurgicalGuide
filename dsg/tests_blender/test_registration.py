"""Run with Blender --background --factory-startup --python-exit-code 1.

Catches missing operator definitions and failed add-on registration/re-enabling.
Usage: --python this_file -- /absolute/path/to/addon-parent
"""
import sys
from pathlib import Path
from unittest.mock import patch

import bpy

addon_parent = (
    Path(sys.argv[sys.argv.index("--") + 1]).resolve()
    if "--" in sys.argv
    else Path(__file__).resolve().parents[2]
)
sys.path.insert(0, str(addon_parent))
import dsg

EXPECTED = (
    "segment_semantic_structure",
    "segment_all",
    "direct_dicom_to_surface",
)

for cycle in range(2):
    dsg.register()
    assert hasattr(bpy.types.Scene, "dicom_wizard_pro")
    for name in EXPECTED:
        op = getattr(bpy.ops.dicom_wizard_pro, name)
        assert op.get_rna_type().identifier, name
    # Keep Blender and the real operators; replace only the expensive external
    # worker launch. Literal requests catch wrong targets and lost route modes.
    module = dsg.dicom_module
    requests = []
    def start(context, structure="ALL", route_mode="FULL"):
        requests.append((structure, route_mode))
        context.scene["DSG_cbct_requested_engine_route"] = "TOOTHSEG_FULL"
        return True
    with patch.object(module, "_start_async_full_segmentation", start):
        assert bpy.ops.dicom_wizard_pro.segment_all(route_mode="SIMPLE_ARCHES") == {"FINISHED"}
        assert requests.pop() == ("ALL", "SIMPLE_ARCHES")
        assert bpy.ops.dicom_wizard_pro.segment_all() == {"FINISHED"}
        assert requests.pop() == ("ALL", "FULL")
        assert bpy.ops.dicom_wizard_pro.segment_semantic_structure(target="TEETH") == {"FINISHED"}
        assert requests.pop() == ("TEETH", "FULL")
        assert bpy.ops.dicom_wizard_pro.segment_semantic_structure(target="BONE") == {"FINISHED"}
        assert requests.pop() == ("ALL", "FULL")
        assert bpy.ops.dicom_wizard_pro.segment_semantic_structure(target="BONE_ONLY") == {"FINISHED"}
        assert requests.pop() == ("ALL", "FULL")
        assert bpy.ops.dicom_wizard_pro.direct_dicom_to_surface() == {"FINISHED"}
        assert requests.pop() == ("ALL", "FULL")
        assert bpy.context.scene["DSG_cbct_requested_engine_route"] == "TOOTHSEG_FULL"
    with patch.object(module, "_start_async_full_segmentation", return_value=False):
        assert bpy.ops.dicom_wizard_pro.segment_all() == {"CANCELLED"}
    print(f"REGISTRATION_CYCLE_{cycle + 1}_PASS")
    dsg.unregister()
    assert not hasattr(bpy.types.Scene, "dicom_wizard_pro")
    print(f"UNREGISTER_CYCLE_{cycle + 1}_PASS")

print("DSG_REGISTRATION_TEST_PASS", bpy.app.version_string)
