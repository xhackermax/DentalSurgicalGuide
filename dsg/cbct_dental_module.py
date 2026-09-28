"""CBCT tooth instances and FDI review for DSG 8.9.

UniversalLab already predicts one semantic label per tooth.  This module keeps
those learned instances intact; it does *not* re-split contacts with connected
components/watershed and it does not infer FDI from IOS geometry.
"""
from __future__ import annotations

import logging as _dsg_logging
_DSG_LOG = _dsg_logging.getLogger(__name__)

from typing import Any
import math
import json
import time

import bpy
from bpy.props import BoolProperty, IntProperty, PointerProperty, StringProperty
from bpy.types import Operator, PropertyGroup
from mathutils import Vector

from . import tooth_analysis
from . import dental_assets
from . import dental_asset_blender
from . import ui_style
from . import icon_manager

COLLECTION_NAME = "DSG_CBCT_Dentition"
LABEL_COLLECTION_NAME = "DSG_CBCT_FDI_Labels"
ALIGNMENT_REF_NAME = "Dental_DICOM_AlignmentRef"
TOOTH_OBJECT_PREFIX = dental_assets.object_prefix("TOOTH")
LABEL_OBJECT_PREFIX = dental_assets.object_prefix("FDI_LABEL")
SCENE_ACCEPTED_KEY = "DSG_cbct_fdi_accepted"
IMMEDIATE_UPPER_COMPOSITE_NAME = "Dental_DICOM_Immediate_Maxilla"
IMMEDIATE_LOWER_COMPOSITE_NAME = "Dental_DICOM_Immediate_Mandible"


def _np():
    import numpy as np
    return np


def _ensure_child_collection(context, name: str) -> bpy.types.Collection:
    from . import dicom_module
    parent = dicom_module.get_collection()
    dicom_module.ensure_collection_in_view_layer(context, parent)
    collection = bpy.data.collections.get(name)
    if collection is None:
        collection = bpy.data.collections.new(name)
    # A collection can be linked only once to this parent; children.get is by name.
    if parent.children.get(collection.name) is None:
        parent.children.link(collection)
    # Blender does not always synchronize a newly linked nested collection with
    # the active ViewLayer until a depsgraph update. Do it here so a tooth built
    # on this timer tick can be selected safely on the next one.
    dicom_module.ensure_collection_in_view_layer(context, collection)
    return collection


def _unlink_from_other_collections(obj: bpy.types.Object, keep: bpy.types.Collection) -> None:
    for collection in list(obj.users_collection):
        if collection != keep:
            try:
                collection.objects.unlink(obj)
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)


def _delete_object(obj: bpy.types.Object) -> None:
    data = getattr(obj, "data", None)
    kind = getattr(obj, "type", "")
    try:
        bpy.data.objects.remove(obj, do_unlink=True)
    except Exception:
        return
    if data is not None and getattr(data, "users", 1) == 0:
        try:
            if kind == "MESH":
                bpy.data.meshes.remove(data)
            elif kind == "FONT":
                bpy.data.curves.remove(data)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)


def clear_dentition(*, keep_alignment_reference: bool = False) -> None:
    for prefix in (TOOTH_OBJECT_PREFIX, LABEL_OBJECT_PREFIX):
        for obj in list(bpy.data.objects):
            if obj.name.startswith(prefix):
                _delete_object(obj)
    for name in (COLLECTION_NAME, LABEL_COLLECTION_NAME):
        collection = bpy.data.collections.get(name)
        if collection is not None and len(collection.objects) == 0:
            try:
                bpy.data.collections.remove(collection)
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
    if not keep_alignment_reference:
        for ref_name in (
            ALIGNMENT_REF_NAME,
            "Dental_DICOM_AlignmentRef",
            "Dental_DICOM_AlignmentComposite",
        ):
            ref = bpy.data.objects.get(ref_name)
            if ref is not None:
                _delete_object(ref)
        collection = bpy.data.collections.get(ALIGNMENT_WORK_COLLECTION)
        if collection is not None:
            for helper in list(collection.objects):
                _delete_object(helper)
            if len(collection.objects) == 0:
                try:
                    bpy.data.collections.remove(collection)
                except Exception:
                    _DSG_LOG.debug("suppressed exception", exc_info=True)


def _tooth_labels_present(labels) -> list[int]:
    np = _np()
    present = np.unique(labels)
    return [int(v) for v in present if 1 <= int(v) <= 52 and tooth_analysis.universal_to_fdi(v, source="CBCT")]


# v9.2.64 native semantic meshing policy. UniversalLab remains the immutable
# source of truth. Bounding boxes are cached only to crop empty background and
# to support on-demand single-tooth refinement; clinical tooth geometry is
# always extracted at native voxel resolution.
TOOTH_ROI_FULL_MARGIN_VOXELS = 5
_BBOX_CACHE: dict[str, Any] = {"key": None, "boxes": None}


def _labelmap_cache_key(labels, max_label: int):
    np = _np()
    arr = np.asarray(labels)
    try:
        ptr = int(arr.__array_interface__["data"][0])
    except Exception:
        ptr = id(arr)
    return (ptr, tuple(int(v) for v in arr.shape), str(arr.dtype), int(max_label))


def _bbox_slices(labels, max_label: int = 55):
    """Return one bbox per integer label, cached for the current labelmap."""
    key = _labelmap_cache_key(labels, max_label)
    if _BBOX_CACHE.get("key") == key and _BBOX_CACHE.get("boxes") is not None:
        return _BBOX_CACHE["boxes"]
    try:
        from scipy import ndimage
    except ImportError as exc:
        raise RuntimeError("Runtime IA incompleto: falta SciPy para individualizar los dientes") from exc
    boxes = ndimage.find_objects(labels, max_label=max_label)
    _BBOX_CACHE["key"] = key
    _BBOX_CACHE["boxes"] = boxes
    return boxes


def _expanded_bbox_bounds(labels_shape, bbox, *, margin_voxels: int):
    zsl, ysl, xsl = bbox
    margin = max(1, int(margin_voxels))
    z0 = max(0, int(zsl.start) - margin); z1 = min(int(labels_shape[0]), int(zsl.stop) + margin)
    y0 = max(0, int(ysl.start) - margin); y1 = min(int(labels_shape[1]), int(ysl.stop) + margin)
    x0 = max(0, int(xsl.start) - margin); x1 = min(int(labels_shape[2]), int(xsl.stop) + margin)
    return z0, z1, y0, y1, x0, x1


def correct_universal_semantics(labels) -> dict[str, Any]:
    """Validate arch first, then laterality, in DICOM patient coordinates."""
    np = _np()
    from . import dicom_module
    return tooth_analysis.correct_universal_semantics_array(
        np,
        labels,
        dicom_module.RUNTIME.spacing_zyx_mm,
        dicom_module.RUNTIME.orientation_xyz,
        dicom_module.RUNTIME.image_origin_patient,
    )


def correct_universal_mirroring(labels) -> dict[str, Any]:
    """Compatibility wrapper for callers that explicitly request laterality only."""
    np = _np()
    from . import dicom_module
    return tooth_analysis.correct_universal_mirroring_array(
        np,
        labels,
        dicom_module.RUNTIME.spacing_zyx_mm,
        dicom_module.RUNTIME.orientation_xyz,
        dicom_module.RUNTIME.image_origin_patient,
    )


def _clean_tooth_mask(mask, *, label: int, spacing_zyx):
    """Materialize one safe tooth component without ever merging large islands.

    Upstream BATCHDENTALSEG removes islands below 60 mm³.  If more than one
    >=60 mm³ component survives, DSG still creates geometry immediately from
    the largest component, marks that FDI for review, and excludes the other
    disconnected components from the clinical tooth object.  Thus a bad label
    can no longer become one multi-tooth object, but one bad label also cannot
    suppress the whole dentition.
    """
    np = _np()
    cc, diagnostics = tooth_analysis.analyze_tooth_mask_components(
        np, mask, spacing_zyx, minimum_island_mm3=60.0,
        relative_significant_fraction=1.0,
    )
    largest_id = int(diagnostics.get("largest_component_id", 0) or 0)
    if largest_id <= 0:
        diagnostics = dict(diagnostics)
        diagnostics["removed_voxels"] = int(np.asarray(mask, dtype=np.uint8).sum())
        diagnostics["status"] = "EMPTY"
        return np.zeros_like(mask, dtype=np.uint8), diagnostics

    cleaned = np.asarray(cc == largest_id, dtype=np.uint8)
    diagnostics = dict(diagnostics)
    diagnostics["removed_voxels"] = int(np.asarray(mask, dtype=np.uint8).sum()) - int(cleaned.sum())
    if int(diagnostics.get("significant_component_count", 0)) > 1:
        diagnostics["status"] = "REVIEW_MULTICOMPONENT_PRIMARY_SELECTED"
    else:
        diagnostics["status"] = "VALID_PRIMARY_COMPONENT"
    return cleaned, diagnostics


def _prepare_mesh_from_label(labels, label: int, bbox, *, step_size: int = 1,
                             refine: bool = False, preferred_mesher: str = "AUTO"):
    """Native-resolution single-label fallback / explicit refinement path.

    v9.2.64 no longer uses this function for the normal full-dentition build.
    The primary path extracts every FDI in one multi-label VTK pass. This helper
    remains for deterministic fallback and for the clinician-triggered CBCT
    refinement of one selected tooth.
    """
    np = _np()
    from . import dicom_module
    from . import cbct_surface_meshing

    measure = dicom_module.load_skimage_measure()
    preferred_upper = str(preferred_mesher or "AUTO").upper()
    vtk_module = (
        dicom_module.load_vtk()
        if preferred_upper not in {"SKIMAGE", "LEWINER", "SKIMAGE_LEWINER"}
        else None
    )
    if measure is None and vtk_module is None:
        raise RuntimeError("Falta un motor de superficie CBCT (VTK o scikit-image)")

    margin = TOOTH_ROI_FULL_MARGIN_VOXELS
    z0, z1, y0, y1, x0, x1 = _expanded_bbox_bounds(
        labels.shape, bbox, margin_voxels=margin
    )
    # The compact binary mask exists only in this fallback/on-demand path. The
    # standard v9.2.64 build never materializes one mask per tooth.
    mask = np.ascontiguousarray(
        np.asarray(labels[z0:z1, y0:y1, x0:x1]) == int(label), dtype=np.uint8
    )
    voxel_count = int(mask.sum())
    if voxel_count < 16:
        return None

    # Clinical geometry is always native. ``step_size`` is accepted only for
    # old API compatibility and deliberately ignored.
    extraction = cbct_surface_meshing.extract_binary_surface(
        mask,
        step_size=1,
        preferred_engine=preferred_mesher,
        vtk_module=vtk_module,
        skimage_measure=measure,
    )
    verts, faces, topology = cbct_surface_meshing.clean_surface_components(
        extraction.vertices_zyx, extraction.faces,
        spacing_zyx=dicom_module.RUNTIME.spacing_zyx_mm,
    )
    if len(faces) < 4:
        return None
    verts = np.asarray(verts, dtype=np.float64)
    faces = np.asarray(faces, dtype=np.int32)
    verts[:, 0] += float(z0)
    verts[:, 1] += float(y0)
    verts[:, 2] += float(x0)
    xyz = dicom_module._global_voxel_to_centered_xyz(verts)
    fdi = tooth_analysis.universal_to_fdi(label, source="CBCT")

    refine_stats = {"status": "SKIPPED_NATIVE_SOURCE"}
    if refine:
        try:
            from . import anatomy_refine
            xyz, faces, refine_stats = anatomy_refine.refine_segmented_surface(
                None, xyz, np.asarray(faces, dtype=np.int32),
                mask=mask, origin_zyx=(z0, y0, x0), kind="TOOTH_HIGH", label=int(label),
            )
        except Exception as refine_exc:
            refine_stats = {
                "status": "FALLBACK_SOURCE",
                "reason": f"{type(refine_exc).__name__}: {refine_exc}",
            }

    centroid = tuple(float(v) for v in np.asarray(xyz).mean(axis=0, dtype=np.float64))
    axis_info = None
    try:
        axis_info = tooth_analysis.pca_axis_from_xyz(np, xyz)
    except Exception:
        axis_info = None

    return {
        "label": int(label), "fdi": int(fdi),
        "xyz": np.ascontiguousarray(xyz, dtype=np.float32),
        "faces": np.ascontiguousarray(faces, dtype=np.int32),
        "voxel_count": int(voxel_count), "topology": dict(topology),
        "centroid": centroid, "refine_stats": dict(refine_stats),
        "axis_info": axis_info,
        "mesh_step_size": 1,
        "mesh_step_requested": 1,
        "full_resolution": True,
        "surface_mesher": str(extraction.engine),
        "surface_extract_s": float(extraction.elapsed_s),
        "surface_mesher_fallback": str(extraction.fallback_reason or ""),
        "surface_mesher_diagnostics": dict(extraction.diagnostics or {}),
        "roi_origin_zyx": (int(z0), int(y0), int(x0)),
        "roi_shape_zyx": tuple(int(v) for v in mask.shape),
        "roi_voxels": int(mask.size),
        "roi_margin_voxels": int(margin),
        "component_cleanup_stage": "POST_SURFACE",
    }


def _dentition_crop_bounds(labels_shape, boxes, present, *, margin_voxels: int = 2):
    valid = []
    for label in present:
        idx = int(label) - 1
        if 0 <= idx < len(boxes) and boxes[idx] is not None:
            valid.append(boxes[idx])
    if not valid:
        return None
    z0 = min(int(b[0].start) for b in valid); z1 = max(int(b[0].stop) for b in valid)
    y0 = min(int(b[1].start) for b in valid); y1 = max(int(b[1].stop) for b in valid)
    x0 = min(int(b[2].start) for b in valid); x1 = max(int(b[2].stop) for b in valid)
    m = max(1, int(margin_voxels))
    return (
        max(0, z0 - m), min(int(labels_shape[0]), z1 + m),
        max(0, y0 - m), min(int(labels_shape[1]), y1 + m),
        max(0, x0 - m), min(int(labels_shape[2]), x1 + m),
    )


def prepare_universal_dentition_meshes(labels, *, preview_step_size: int = 1):
    """Prepare all FDI surfaces at native resolution in one semantic pass.

    v9.2.64 deliberately removes the preview/full-resolution duality. The first
    geometry shown to the clinician is already native-resolution clinical
    geometry. With VTK, one ``vtkDiscreteFlyingEdges3D`` pass extracts every
    requested FDI directly from the integer UniversalLab labelmap. No per-tooth
    binary masks, no step=2, no Taubin/MMG pass and no duplicated volume scan.
    """
    np = _np()
    from . import dicom_module
    from . import cbct_surface_meshing

    labels = np.asarray(labels)
    present = _tooth_labels_present(labels)
    boxes = _bbox_slices(labels, 55)
    started = time.perf_counter()
    if not present:
        return {
            "items": [], "prepare_s": 0.0, "surface_extract_s": 0.0,
            "candidate_count": 0, "prepared_count": 0,
            "engine_counts": {}, "vtk_available": bool(dicom_module.load_vtk()),
            "mesher_fallback_count": 0, "native_preview_count": 0,
            "native_fullres_count": 0, "roi_total_voxels": 0,
            "roi_vs_naive_fraction": 0.0, "bbox_cache": True,
            "roi_worker_count": 1, "single_pass": True,
        }

    bounds = _dentition_crop_bounds(labels.shape, boxes, present, margin_voxels=2)
    if bounds is None:
        raise RuntimeError("No se pudo localizar la dentición UniversalLab")
    z0, z1, y0, y1, x0, x1 = bounds
    crop = np.ascontiguousarray(labels[z0:z1, y0:y1, x0:x1])

    vtk_module = dicom_module.load_vtk()
    measure = dicom_module.load_skimage_measure()
    if vtk_module is None and measure is None:
        raise RuntimeError("Falta un motor de superficie CBCT full-resolution")

    batch = None
    # Optional Bioxel-style process isolation. AUTO keeps the faster in-process
    # C++/CUDA path; setting DSG_SURFACE_SIDECAR=1 forces a background Blender
    # worker without touching the clinical geometry or voxel resolution.
    try:
        from . import cbct_surface_worker_client
        batch = cbct_surface_worker_client.extract_multilabel_sidecar(
            crop, present, crop_origin_zyx=(z0, y0, x0),
            spacing_zyx=dicom_module.RUNTIME.spacing_zyx_mm,
        )
    except Exception:
        batch = None
    if batch is None:
        batch = cbct_surface_meshing.extract_multilabel_surface(
            crop, present,
            crop_origin_zyx=(z0, y0, x0),
            vtk_module=vtk_module,
            skimage_measure=measure,
            spacing_zyx=dicom_module.RUNTIME.spacing_zyx_mm,
        )

    # One histogram replaces N full-mask sums. The dentition crop contains each
    # tooth bbox completely, therefore its counts are the original label counts.
    counts = np.bincount(crop.reshape(-1).astype(np.int64, copy=False), minlength=56)
    prepared = []
    per_item_extract_s = float(batch.elapsed_s) / max(1, len(batch.items))
    for label in present:
        surface = batch.items.get(int(label))
        if surface is None:
            continue
        fdi = tooth_analysis.universal_to_fdi(label, source="CBCT")
        if not fdi:
            continue
        xyz = dicom_module._global_voxel_to_centered_xyz(surface.vertices_zyx)
        faces = np.ascontiguousarray(surface.faces, dtype=np.int32)
        if len(faces) < 4:
            continue
        centroid = tuple(float(v) for v in np.asarray(xyz).mean(axis=0, dtype=np.float64))
        try:
            axis_info = tooth_analysis.pca_axis_from_xyz(np, xyz)
        except Exception:
            axis_info = None
        prepared.append({
            "label": int(label), "fdi": int(fdi),
            "xyz": np.ascontiguousarray(xyz, dtype=np.float32),
            "faces": faces,
            "voxel_count": int(counts[int(label)]) if int(label) < len(counts) else 0,
            "topology": dict(surface.topology or {}),
            "centroid": centroid,
            "refine_stats": {"status": "SKIPPED_NATIVE_SOURCE"},
            "axis_info": axis_info,
            "mesh_step_size": 1,
            "mesh_step_requested": 1,
            "full_resolution": True,
            "surface_mesher": str(batch.engine),
            "surface_extract_s": float(per_item_extract_s),
            "surface_batch_extract_s": float(batch.elapsed_s),
            "surface_mesher_fallback": str(batch.fallback_reason or ""),
            "surface_mesher_diagnostics": dict(batch.diagnostics or {}),
            "roi_origin_zyx": (int(z0), int(y0), int(x0)),
            "roi_shape_zyx": tuple(int(v) for v in crop.shape),
            "roi_voxels": int(crop.size),
            "roi_margin_voxels": 2,
            "component_cleanup_stage": "POST_SURFACE",
            "single_multilabel_pass": bool((batch.diagnostics or {}).get("single_pass", False)),
        })

    prepared.sort(key=lambda item: int(item.get("label", 0) or 0))
    engine_counts = {str(batch.engine): int(len(prepared))} if prepared else {}
    diag = dict(batch.diagnostics or {})
    smp = dict(diag.get("vtk_smp") or {})
    backend = str(smp.get("backend_after") or smp.get("backend_before") or "")
    naive_voxels = int(labels.size) * max(1, len(prepared))
    roi_fraction = float(crop.size) / float(naive_voxels) if naive_voxels else 0.0
    return {
        "items": prepared,
        "prepare_s": float(time.perf_counter() - started),
        "surface_extract_s": float(batch.elapsed_s),
        "candidate_count": int(len(present)),
        "prepared_count": int(len(prepared)),
        "engine_counts": engine_counts,
        "vtk_available": bool(vtk_module is not None),
        "mesher_fallback_count": int(bool(batch.fallback_reason)),
        "native_preview_count": int(len(prepared)),  # legacy metric key
        "native_fullres_count": int(len(prepared)),
        "roi_total_voxels": int(crop.size),
        "roi_vs_naive_fraction": float(roi_fraction),
        "bbox_cache": True,
        "roi_worker_count": 1,
        "vtk_smp_backends": [backend] if backend else [],
        "vtk_smp_threads": int(smp.get("threads", 0) or 0),
        "single_pass": bool(diag.get("single_pass", False)),
        "per_tooth_binary_masks": not bool(diag.get("single_pass", False)),
        "component_cleanup_stage": "POST_SURFACE",
        "native_resolution": True,
    }


def upgrade_teeth_to_full_resolution(context, fdis) -> dict[str, Any]:
    """Promote only clinician-selected teeth to full CBCT-constrained meshes.

    The initial segmentation intentionally creates lightweight meshes for FDI
    review. Before an immediate-extraction boolean, the selected teeth must be
    rebuilt directly from the unchanged UniversalLab labelmap at native voxel
    resolution and refined within the CBCT/mask safety cage.
    """
    np = _np()
    from . import dicom_module
    wanted = sorted({int(value) for value in (fdis or ()) if int(value) > 0})
    if not wanted:
        return {"upgraded": 0, "skipped": 0, "elapsed_s": 0.0}
    labels = dicom_module.get_cached_semantic_cbct_labels(
        model_kind="universal", require_current_source=True,
    )
    if labels is None:
        raise RuntimeError("El CBCT/labelmap original ya no está disponible; no se puede recuperar el detalle local")
    boxes = _bbox_slices(labels, 55)
    started = time.perf_counter()
    upgraded = 0
    skipped = 0
    for fdi in wanted:
        obj = next((item for item in dentition_objects()
                    if int(item.get("DSG_fdi_number", 0) or 0) == fdi), None)
        if obj is None:
            skipped += 1
            continue
        label = int(obj.get("DSG_universal_label", 0) or 0)
        bbox = boxes[label - 1] if 0 < label <= len(boxes) else None
        if bbox is None:
            skipped += 1
            continue
        prepared = _prepare_mesh_from_label(labels, label, bbox, step_size=1, refine=True)
        if prepared is None:
            raise RuntimeError(f"No se pudo reconstruir el detalle CBCT del FDI {fdi}")
        old_mesh = obj.data
        old_mesh.name = f"DSG_Backup_FDI_{fdi}_PreviewMesh"
        old_mesh.use_fake_user = True
        mesh = bpy.data.meshes.new(f"{obj.name}_CBCT_FullResolution")
        verts_arr = np.ascontiguousarray(prepared["xyz"], dtype=np.float32)
        faces_arr = np.ascontiguousarray(prepared["faces"], dtype=np.int32)
        mesh.vertices.add(int(len(verts_arr)))
        mesh.vertices.foreach_set("co", verts_arr.ravel())
        loop_count = int(len(faces_arr) * 3)
        mesh.loops.add(loop_count)
        mesh.loops.foreach_set("vertex_index", faces_arr.ravel())
        mesh.polygons.add(int(len(faces_arr)))
        mesh.polygons.foreach_set("loop_start", np.arange(0, loop_count, 3, dtype=np.int32))
        mesh.polygons.foreach_set("loop_total", np.full(len(faces_arr), 3, dtype=np.int32))
        try:
            mesh.polygons.foreach_set("use_smooth", np.ones(len(faces_arr), dtype=np.bool_))
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        mesh.update(calc_edges=True)
        for material in old_mesh.materials:
            mesh.materials.append(material)
        obj.data = mesh
        refine_stats = dict(prepared.get("refine_stats") or {})
        obj["DSG_geometry_resolution"] = "CBCT_FULL_SELECTED"
        obj["DSG_geometry_preview_step_size"] = 1
        obj["DSG_geometry_improved"] = True
        obj["DSG_geometry_improved_source"] = "CBCT_NATIVE_LABEL_MASK_CAGED"
        obj["DSG_geometry_improved_backup_mesh"] = old_mesh.name
        obj["DSG_geometry_improved_json"] = json.dumps(refine_stats, ensure_ascii=False, default=str)
        obj["DSG_surface_mesher"] = str(prepared.get("surface_mesher", "UNKNOWN"))
        obj["DSG_surface_extract_s"] = float(prepared.get("surface_extract_s", 0.0) or 0.0)
        obj["DSG_surface_roi_voxels"] = int(prepared.get("roi_voxels", 0) or 0)
        obj["DSG_surface_roi_margin_voxels"] = int(prepared.get("roi_margin_voxels", 0) or 0)
        upgraded += 1
    elapsed = float(time.perf_counter() - started)
    context.scene["DSG_selected_teeth_full_resolution"] = int(upgraded)
    context.scene["DSG_selected_teeth_full_resolution_s"] = elapsed
    return {"upgraded": int(upgraded), "skipped": int(skipped), "elapsed_s": elapsed}


def _commit_prepared_tooth(context, prepared, root, collection):
    """Fast Blender-only commit of one already prepared tooth mesh."""
    np = _np()
    from . import dicom_module
    label = int(prepared["label"]); fdi = int(prepared["fdi"])
    xyz = (np.load(str(prepared.get("xyz_path")), mmap_mode="r")
           if prepared.get("xyz_path") else np.asarray(prepared["xyz"], dtype=np.float32))
    faces = (np.load(str(prepared.get("faces_path")), mmap_mode="r")
             if prepared.get("faces_path") else np.asarray(prepared["faces"], dtype=np.int32))
    topology = dict(prepared.get("topology") or {})
    refine_stats = dict(prepared.get("refine_stats") or {"status": "SKIPPED"})
    centroid = tuple(float(v) for v in prepared.get("centroid", (0.0, 0.0, 0.0)))
    voxel_count = int(prepared.get("voxel_count", 0))

    name = dental_assets.object_name(fdi, "TOOTH")
    obj = dicom_module._new_surface_from_arrays(
        context, object_name=name, vertices_xyz=xyz,
        faces=faces, root=root,
    )
    _unlink_from_other_collections(obj, collection)
    dicom_module.ensure_object_in_view_layer(context, obj)
    if len(obj.data.materials) == 0:
        obj.data.materials.append(dicom_module._surface_material("TEETH"))

    voxel_volume = math.prod(float(v) for v in dicom_module.RUNTIME.spacing_zyx_mm)
    dental_asset_blender.stamp_object(
        obj, fdi=fdi, role="TOOTH", source="CBCT_TOTALSEGMENTATOR",
        coordinate_space="CBCT_DSG_ROOT", rename=True,
    )
    obj["DSG_fdi_number"] = int(fdi)
    obj["DSG_model_fdi_number"] = int(fdi)
    obj["DSG_fdi_user_override"] = False
    obj["DSG_universal_label"] = int(label)
    obj["DSG_source"] = "CBCT_TOTALSEGMENTATOR"
    obj["DSG_tooth_arch"] = tooth_analysis.arch_from_fdi(fdi)
    obj["DSG_tooth_side"] = tooth_analysis.side_from_fdi(fdi)
    obj["DSG_tooth_class"] = tooth_analysis.tooth_class_from_fdi(fdi)
    obj["DSG_tooth_instance"] = True
    obj["DSG_dental_ai_locator"] = True
    obj["DSG_voxel_count"] = int(voxel_count)
    obj["DSG_topology_status"] = str(topology.get("status", "VALID"))
    obj["DSG_component_count_raw"] = int(topology.get("component_count", 1))
    obj["DSG_significant_component_count"] = int(topology.get("significant_component_count", 1))
    obj["DSG_removed_island_voxels"] = int(topology.get("removed_voxels", 0))
    obj["DSG_volume_mm3"] = float(voxel_count * voxel_volume)
    obj["DSG_anatomy_refine_status"] = str(refine_stats.get("status", "UNKNOWN"))
    obj["DSG_anatomy_refine_backend"] = str(refine_stats.get("backend", "SOURCE"))
    obj["DSG_anatomy_refine_volume_ratio"] = float(refine_stats.get("volume_ratio", 1.0) or 1.0)
    obj["DSG_anatomy_refine_cbct_snapped"] = int(refine_stats.get("cbct_snapped", 0) or 0)
    obj["DSG_anatomy_refine_mmg"] = bool(refine_stats.get("mmg_used", False))
    obj["DSG_anatomy_refine_json"] = json.dumps(refine_stats, ensure_ascii=False, default=str)
    obj["DSG_geometry_preview_step_size"] = 1  # legacy key; clinical mesh is native
    obj["DSG_surface_mesher"] = str(prepared.get("surface_mesher", "UNKNOWN"))
    obj["DSG_surface_extract_s"] = float(prepared.get("surface_extract_s", 0.0) or 0.0)
    obj["DSG_surface_batch_extract_s"] = float(prepared.get("surface_batch_extract_s", 0.0) or 0.0)
    obj["DSG_surface_roi_voxels"] = int(prepared.get("roi_voxels", 0) or 0)
    obj["DSG_surface_roi_margin_voxels"] = int(prepared.get("roi_margin_voxels", 0) or 0)
    obj["DSG_surface_mesher_fallback"] = str(prepared.get("surface_mesher_fallback", "") or "")
    obj["DSG_surface_single_multilabel_pass"] = bool(prepared.get("single_multilabel_pass", False))
    obj["DSG_surface_component_cleanup_stage"] = str(prepared.get("component_cleanup_stage", "POST_SURFACE"))
    obj["DSG_normals_policy"] = "LAZY_ON_DEMAND"
    obj["DSG_geometry_resolution"] = (
        "CBCT_FULL_NATIVE" if bool(prepared.get("full_resolution", False)) else "CBCT_FULL_NATIVE"
    )
    obj["DSG_label_verified"] = False
    try:
        axis_info = prepared.get("axis_info")
        if axis_info is not None:
            apical = tooth_analysis.orient_axis_apical(axis_info["axis"], fdi)
            if apical is not None:
                obj["DSG_tooth_axis_xyz"] = [float(v) for v in apical]
                obj["DSG_tooth_axis_apical_local"] = [float(v) for v in apical]
                try:
                    axis_world = obj.matrix_world.to_3x3() @ Vector(apical)
                    if axis_world.length > 1.0e-9:
                        axis_world.normalize()
                        obj["DSG_tooth_axis_apical_world"] = [float(v) for v in axis_world]
                    origin_world = obj.matrix_world @ Vector(centroid)
                    obj["DSG_tooth_axis_origin_world"] = [float(v) for v in origin_world]
                except Exception:
                    _DSG_LOG.debug("suppressed exception", exc_info=True)
            shape_conf = float(axis_info.get("shape_confidence", 0.0))
            obj["DSG_axis_shape_confidence"] = shape_conf
            obj["DSG_tooth_axis_confidence"] = shape_conf
            obj["DSG_tooth_axis_method"] = "cbct_mesh_pca+fdi_arch_orientation"
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    obj["dental_suite_structure"] = "TOOTH_INSTANCE"
    obj["dental_suite_component"] = "DICOM"
    obj["dental_suite_role"] = dicom_module.ROLE_DICOM_TEETH
    return obj, centroid, int(faces.shape[0]), topology


def _mesh_from_label(context, labels, label: int, bbox, root, collection):
    """Compatibility wrapper. New full workflow prepares arrays off-main-thread."""
    prepared = _prepare_mesh_from_label(labels, int(label), bbox)
    if prepared is None:
        return None
    return _commit_prepared_tooth(context, prepared, root, collection)


FDI_LABEL_SIZE_MM = 2.15
FDI_LABEL_SURFACE_OFFSET_MM = 0.55
FDI_LABEL_CROWN_FRACTION = 0.52


def _vector_prop(obj, key: str):
    try:
        value = obj.get(key)
        if value is None:
            return None
        vec = Vector(tuple(float(v) for v in value[:3]))
        if vec.length <= 1.0e-9:
            return None
        vec.normalize()
        return vec
    except Exception:
        return None


def _tooth_world_vertices(tooth_obj: bpy.types.Object) -> list[Vector]:
    try:
        matrix = tooth_obj.matrix_world
        return [matrix @ vertex.co for vertex in tooth_obj.data.vertices]
    except Exception:
        return []


def _tooth_world_centroid(tooth_obj: bpy.types.Object) -> Vector:
    vertices = _tooth_world_vertices(tooth_obj)
    if vertices:
        total = Vector((0.0, 0.0, 0.0))
        for point in vertices:
            total += point
        return total / float(len(vertices))
    try:
        return tooth_obj.matrix_world.translation.copy()
    except Exception:
        return Vector((0.0, 0.0, 0.0))


def _fdi_arch_centres(teeth) -> dict[str, Vector]:
    grouped = {}
    for tooth in teeth:
        arch = str(tooth.get("DSG_tooth_arch", "") or "")
        if not arch:
            try:
                arch = str(tooth_analysis.arch_from_fdi(int(tooth.get("DSG_fdi_number", 0))) or "")
            except Exception:
                arch = ""
        if not arch:
            continue
        grouped.setdefault(arch, []).append(_tooth_world_centroid(tooth))

    result = {}
    for arch, points in grouped.items():
        if not points:
            continue
        center = Vector((0.0, 0.0, 0.0))
        for point in points:
            center += point
        result[arch] = center / float(len(points))
    return result


def _fdi_patient_superior_world() -> Vector:
    # apply_patient_orientation() places DICOM patient coordinates into Blender
    # world coordinates, therefore world +Z is patient superior.
    return Vector((0.0, 0.0, 1.0))


def _fdi_patient_anterior_world() -> Vector:
    # DICOM LPS: +Y posterior, hence anterior is -Y.
    return Vector((0.0, -1.0, 0.0))


def _fdi_tooth_coronal_world(tooth_obj: bpy.types.Object) -> Vector:
    apical = _vector_prop(tooth_obj, "DSG_tooth_axis_apical_world")
    if apical is not None:
        coronal = -apical
        coronal.normalize()
        return coronal
    local_apical = _vector_prop(tooth_obj, "DSG_tooth_axis_apical_local")
    if local_apical is not None:
        try:
            coronal = -(tooth_obj.matrix_world.to_3x3() @ local_apical)
            if coronal.length > 1.0e-9:
                coronal.normalize()
                return coronal
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    # FDI arch gives a safe anatomical fallback for crown direction.
    fdi = int(tooth_obj.get("DSG_fdi_number", 0) or 0)
    arch = str(tooth_analysis.arch_from_fdi(fdi) or "")
    return Vector((0.0, 0.0, -1.0 if arch == "MAXILLA" else 1.0))


def _fdi_vestibular_direction(tooth_obj: bpy.types.Object,
                              arch_centres: dict[str, Vector],
                              centroid_world: Vector,
                              coronal_world: Vector) -> Vector:
    """Estimate buccal/facial direction from the learned dental arch geometry.

    Radial direction away from the centre of the tooth arch works for anterior
    and posterior teeth and does not require a hand-authored per-FDI vector.
    """
    arch = str(tooth_obj.get("DSG_tooth_arch", "") or "")
    center = arch_centres.get(arch)
    direction = (centroid_world - center) if center is not None else _fdi_patient_anterior_world()

    # The vestibular vector belongs to the plane perpendicular to the long axis.
    direction -= coronal_world * direction.dot(coronal_world)
    if direction.length < 1.0e-6:
        direction = _fdi_patient_anterior_world()
        direction -= coronal_world * direction.dot(coronal_world)
    if direction.length < 1.0e-6:
        direction = Vector((0.0, -1.0, 0.0))
    direction.normalize()
    return direction


def _fdi_label_anchor_world(tooth_obj: bpy.types.Object,
                            arch_centres: dict[str, Vector]):
    """Choose the facial surface of the coronal half of the segmented tooth."""
    vertices = _tooth_world_vertices(tooth_obj)
    centroid = _tooth_world_centroid(tooth_obj)
    coronal = _fdi_tooth_coronal_world(tooth_obj)
    vestibular = _fdi_vestibular_direction(
        tooth_obj, arch_centres, centroid, coronal)

    if not vertices:
        anchor = centroid + vestibular * FDI_LABEL_SURFACE_OFFSET_MM
        return anchor, vestibular, coronal, centroid

    axial = [(point - centroid).dot(coronal) for point in vertices]
    low = min(axial)
    high = max(axial)
    axial_span = max(1.0e-6, high - low)
    crown_floor = low + axial_span * FDI_LABEL_CROWN_FRACTION

    candidates = [
        (point, axial_value)
        for point, axial_value in zip(vertices, axial)
        if axial_value >= crown_floor
    ]
    if not candidates:
        candidates = list(zip(vertices, axial))

    # Dominant criterion is vestibular prominence. A smaller coronal preference
    # keeps the number on crown enamel rather than sliding cervically.
    def score(item):
        point, axial_value = item
        facial = (point - centroid).dot(vestibular)
        coronal_norm = (axial_value - low) / axial_span
        return float(facial + 0.20 * axial_span * coronal_norm)

    surface_point, _ = max(candidates, key=score)
    anchor = surface_point + vestibular * FDI_LABEL_SURFACE_OFFSET_MM
    return anchor, vestibular, coronal, centroid


def _fdi_label_world_matrix(tooth_obj: bpy.types.Object,
                            arch_centres: dict[str, Vector]):
    """Build a text frame: glyph Y=patient superior, glyph Z=vestibular."""
    from mathutils import Matrix
    anchor, normal, coronal, centroid = _fdi_label_anchor_world(
        tooth_obj, arch_centres)

    up = _fdi_patient_superior_world()
    up -= normal * up.dot(normal)
    if up.length < 1.0e-6:
        up = coronal.copy()
        up -= normal * up.dot(normal)
    if up.length < 1.0e-6:
        up = Vector((0.0, 0.0, 1.0))
    up.normalize()

    # All numbers must read upright in patient coordinates.
    if up.dot(_fdi_patient_superior_world()) < 0.0:
        up.negate()

    right = up.cross(normal)
    if right.length < 1.0e-6:
        right = Vector((1.0, 0.0, 0.0))
    else:
        right.normalize()

    # Re-orthogonalise.
    up = normal.cross(right)
    if up.length > 1.0e-9:
        up.normalize()

    rotation = Matrix((right, up, normal)).transposed().to_3x3()
    matrix = Matrix.Translation(anchor) @ rotation.to_4x4()
    return matrix, {
        "anchor_world": [float(v) for v in anchor],
        "normal_world": [float(v) for v in normal],
        "up_world": [float(v) for v in up],
        "centroid_world": [float(v) for v in centroid],
    }


def _create_fdi_label(fdi: int, root, collection, tooth_obj,
                      arch_centres: dict[str, Vector]) -> bpy.types.Object:
    """Create one compact FDI label on the facial crown surface."""
    name = dental_assets.object_name(fdi, "FDI_LABEL")
    old = bpy.data.objects.get(name)
    if old is not None:
        _delete_object(old)

    curve = bpy.data.curves.new(name + "_CURVE", type="FONT")
    curve.body = str(int(fdi))
    curve.align_x = "CENTER"
    curve.align_y = "CENTER"
    curve.size = FDI_LABEL_SIZE_MM
    # FontCurve details are cosmetic and must never be able to invalidate the
    # clinical segmentation across Blender/Mixar versions.
    for attr, value in (
        ("space_character", 0.90),
        ("extrude", 0.018),
        ("bevel_depth", 0.008),
        ("resolution_u", 2),
        ("bevel_resolution", 0),
    ):
        try:
            setattr(curve, attr, value)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)

    obj = bpy.data.objects.new(name, curve)
    collection.objects.link(obj)

    # Parent to the individual tooth, not DICOM_ROOT. This keeps Blender's
    # relationship line short and ensures the label follows that tooth.
    world_matrix, audit = _fdi_label_world_matrix(tooth_obj, arch_centres)
    obj.parent = tooth_obj
    obj.matrix_world = world_matrix

    obj.show_in_front = True
    obj.hide_render = True
    obj.hide_select = True
    dental_asset_blender.stamp_object(
        obj, fdi=fdi, role="FDI_LABEL", source="CBCT_TOTALSEGMENTATOR",
        coordinate_space="WORLD", rename=True,
    )
    obj["DSG_fdi_number"] = int(fdi)
    obj["DSG_source"] = "CBCT_TOTALSEGMENTATOR"
    obj["DSG_label_anchor_mode"] = "VESTIBULAR_CORONAL_SURFACE"
    obj["DSG_label_orientation_mode"] = "PATIENT_SUPERIOR_UP"
    obj["DSG_label_parent_tooth"] = str(tooth_obj.name)
    obj["DSG_label_size_mm"] = float(FDI_LABEL_SIZE_MM)
    obj["DSG_label_anchor_world"] = audit["anchor_world"]
    obj["DSG_label_normal_world"] = audit["normal_world"]
    return obj


def rebuild_fdi_labels(context=None, *, strict: bool = False) -> list[bpy.types.Object]:
    """Rebuild the FDI display overlay without owning clinical segmentation.

    Tooth identity lives in the tooth object metadata. FONT objects are UI only.
    A text-layout failure therefore records REVIEW state but never deletes or
    invalidates segmented teeth unless an explicit diagnostic call uses strict=True.
    """
    context = context or bpy.context
    teeth = dentition_objects(context)
    if not teeth:
        return []

    errors = []
    labels = []
    try:
        for obj in list(bpy.data.objects):
            if obj.name.startswith(LABEL_OBJECT_PREFIX):
                _delete_object(obj)

        from . import dicom_module
        root = dicom_module.get_root(dicom_module.get_collection())
        label_collection = _ensure_child_collection(context, LABEL_COLLECTION_NAME)
        arch_centres = _fdi_arch_centres(teeth)

        for tooth in teeth:
            fdi = int(tooth.get("DSG_fdi_number", 0) or 0)
            if not tooth_analysis.valid_fdi(fdi, include_primary=True):
                continue
            try:
                labels.append(
                    _create_fdi_label(
                        fdi, root, label_collection, tooth, arch_centres,
                    )
                )
            except Exception as exc:
                errors.append(f"FDI {fdi}: {type(exc).__name__}: {exc}")
                if strict:
                    raise
    except Exception as exc:
        if strict:
            raise
        errors.append(f"overlay: {type(exc).__name__}: {exc}")

    scene = getattr(context, "scene", None)
    if scene is not None:
        try:
            scene["DSG_fdi_overlay_status"] = "OK" if not errors else "REVIEW"
            scene["DSG_fdi_overlay_error_count"] = int(len(errors))
            scene["DSG_fdi_overlay_errors_json"] = json.dumps(errors, ensure_ascii=False)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    if errors:
        print("[DSG FDI OVERLAY] " + " | ".join(errors[:8]))
    return labels


ALIGNMENT_VISUAL_SMOOTH_MODIFIER = "DSG_AlignmentClinicalSmooth"


def set_alignment_visual_smoothing(obj: bpy.types.Object, enabled: bool) -> None:
    """Toggle non-destructive clinical display smoothing on a segmented tooth.

    The source mesh datablock is never remeshed or overwritten.  Geometry
    measurements continue to use the original segmentation; this modifier exists
    only to make the high-resolution CBCT teeth easier to inspect against IOS.
    """
    if obj is None or getattr(obj, "type", None) != "MESH":
        return
    try:
        for poly in obj.data.polygons:
            poly.use_smooth = True
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)

    mod = obj.modifiers.get(ALIGNMENT_VISUAL_SMOOTH_MODIFIER)
    if mod is None:
        try:
            mod = obj.modifiers.new(ALIGNMENT_VISUAL_SMOOTH_MODIFIER, "LAPLACIANSMOOTH")
            if hasattr(mod, "iterations"):
                mod.iterations = 2
            if hasattr(mod, "lambda_factor"):
                mod.lambda_factor = 0.12
            if hasattr(mod, "lambda_border"):
                mod.lambda_border = 0.03
            if hasattr(mod, "use_volume_preserve"):
                mod.use_volume_preserve = True
            if hasattr(mod, "use_normalized"):
                mod.use_normalized = True
            mod.show_render = False
            obj["DSG_alignment_visual_smoothing"] = "LAPLACIAN_NON_DESTRUCTIVE"
        except Exception:
            # Blender builds without Laplacian support still get smooth shading.
            mod = None
    if mod is not None:
        try:
            mod.show_viewport = bool(enabled)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)


def set_dentition_alignment_visual_smoothing(context, enabled: bool) -> list[bpy.types.Object]:
    teeth = dentition_objects(context)
    for tooth in teeth:
        set_alignment_visual_smoothing(tooth, enabled)
    return teeth


def reset_scene_state(scene=None) -> None:
    scene = scene or getattr(bpy.context, "scene", None)
    if scene is None:
        return
    props = getattr(scene, "dsg_cbct_dental", None)
    if props is not None:
        props.ready = False
        props.accepted = False
        props.tooth_count = 0
        props.primary_count = 0
        props.labels_visible = True
        props.status = ""
    scene[SCENE_ACCEPTED_KEY] = False
    scene["DSG_tooth_analysis_completed"] = False


def dentition_objects(context=None) -> list[bpy.types.Object]:
    """Return tooth objects belonging to the current scene, not stale datablocks."""
    context = context or bpy.context
    scene = getattr(context, "scene", None)
    objects = []
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        canonical = dental_asset_blender.is_family_object(obj, role="TOOTH")
        legacy = obj.name.startswith(TOOTH_OBJECT_PREFIX) and tooth_analysis.valid_fdi(
            obj.get("DSG_fdi_number", 0), include_primary=True
        )
        if not (canonical or legacy):
            continue
        if scene is not None:
            try:
                if scene.objects.get(obj.name) is not obj:
                    continue
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
        objects.append(obj)
    objects.sort(key=lambda obj: int(obj.get("DSG_fdi_number", 0)))
    return objects


def labels_visible(visible: bool) -> None:
    for obj in bpy.data.objects:
        if obj.name.startswith(LABEL_OBJECT_PREFIX):
            obj.hide_set(not bool(visible))


def labels_visible_for_arch(arch: str) -> None:
    """Show FDI labels only for the CBCT arch used as alignment reference."""
    wanted = str(arch or "").upper()
    for obj in bpy.data.objects:
        if not obj.name.startswith(LABEL_OBJECT_PREFIX):
            continue
        try:
            fdi = int(obj.get("DSG_fdi_number", 0) or 0)
            label_arch = tooth_analysis.arch_from_fdi(fdi)
            obj.hide_set(label_arch != wanted)
        except Exception:
            # A malformed cosmetic label must never obstruct the workflow.
            try:
                obj.hide_set(True)
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)


ALIGNMENT_COMPOSITE_NAME = "Dental_DICOM_AlignmentComposite"
ALIGNMENT_WORK_COLLECTION = "DSG_ALIGNMENT_WORK"
LEGACY_ALIGNMENT_REFERENCE_NAMES = (
    "Dental_DICOM_AlignmentRef",
    ALIGNMENT_COMPOSITE_NAME,
)
ALIGNMENT_COMPOSITE_QUALITY = "ALL_SEGMENTED_DUPLICATE_COMPOSITE"
NATIVE_ALIGNMENT_REFERENCE_NAME = ALIGNMENT_COMPOSITE_NAME
ALIGNMENT_REF_NAME = ALIGNMENT_COMPOSITE_NAME


def dental_runtime_contract_preflight() -> dict[str, object]:
    """Validate literals used by runtime-created dental assets."""
    spaces = set(dental_assets.coordinate_spaces())
    sources = set(dental_assets.source_names())
    required_spaces = {"CBCT_DSG_ROOT", "WORLD"}
    required_sources = {"CBCT_TOTALSEGMENTATOR"}
    missing_spaces = sorted(required_spaces - spaces)
    missing_sources = sorted(required_sources - sources)
    return {
        "ok": not missing_spaces and not missing_sources,
        "missing_spaces": missing_spaces,
        "missing_sources": missing_sources,
        "coordinate_spaces": sorted(spaces),
    }


def native_alignment_code_preflight() -> dict[str, object]:
    """Cheap readiness test with no scene mutation."""
    return {
        "json_available": "json" in globals(),
        "numpy_available": _np() is not None,
        "builder_version": "ALL_SEGMENTED_DUPLICATE_COMPOSITE_V1",
    }


def _alignment_source_kind(obj, tooth_names: set[str], dicom_module) -> str:
    if obj.name in tooth_names:
        return "TOOTH"
    role = str(dicom_module._suite_role(obj) or "").upper()
    if role == str(dicom_module.ROLE_DICOM_MANDIBULAR_CANAL).upper():
        return "CANAL"
    if bool(obj.get("DSG_safety_structure", False)):
        return "SAFETY"
    if role == str(dicom_module.ROLE_DICOM_BONE).upper():
        return "BONE"
    return "OTHER"


def segmented_alignment_source_objects(context=None) -> list[bpy.types.Object]:
    """Return every current clinical CBCT segmentation mesh, never helpers.

    Teeth are ordered first because their vertex/face ranges define the only
    geometry used by landmark picking and IOS↔CBCT ICP. Bone/canal remain in the
    same final Blender object as disconnected components for visual/context use.
    """
    context = context or bpy.context
    scene = getattr(context, "scene", None)
    from . import dicom_module

    teeth = dentition_objects(context)
    tooth_names = {obj.name for obj in teeth}
    sources = list(teeth)

    if scene is None:
        return sources

    for obj in scene.objects:
        if obj.type != "MESH" or obj.name in tooth_names:
            continue
        if obj.name in LEGACY_ALIGNMENT_REFERENCE_NAMES:
            continue
        if bool(obj.get("dental_suite_alignment_reference", False)):
            continue
        if bool(obj.get("DSG_segmentation_skipped", False)):
            continue

        role = str(dicom_module._suite_role(obj) or "").upper()
        is_bone = (
            role == str(dicom_module.ROLE_DICOM_BONE).upper()
            and (
                bool(obj.get("DSG_full_segmentation", False))
                or str(obj.name) == str(dicom_module.NAME_DICOM_BONE)
                or bool(obj.get("DSG_semantic_source", ""))
                or "semantic" in str(obj.get("dicom_surface_engine", "")).lower()
            )
        )
        is_canal = (
            role == str(dicom_module.ROLE_DICOM_MANDIBULAR_CANAL).upper()
            or str(obj.get("DSG_structure", "")).upper() == "MANDIBULAR_CANAL"
        )
        is_other_semantic = bool(obj.get("DSG_safety_structure", False))

        if is_bone or is_canal or is_other_semantic:
            sources.append(obj)

    # Stable clinical ordering: all teeth first, then bone, then safety structures.
    priority = {"TOOTH": 0, "BONE": 1, "CANAL": 2, "SAFETY": 3, "OTHER": 4}
    sources.sort(
        key=lambda obj: (
            priority.get(_alignment_source_kind(obj, tooth_names, dicom_module), 9),
            int(obj.get("DSG_fdi_number", 0) or 0),
            obj.name,
        )
    )
    return sources


def _alignment_work_collection(context) -> bpy.types.Collection:
    from . import dicom_module
    parent = dicom_module.get_collection()
    collection = bpy.data.collections.get(ALIGNMENT_WORK_COLLECTION)
    if collection is None:
        collection = bpy.data.collections.new(ALIGNMENT_WORK_COLLECTION)
    if parent.children.get(collection.name) is None:
        parent.children.link(collection)
    dicom_module.ensure_collection_in_view_layer(context, collection)
    return collection


def _delete_alignment_duplicate(obj) -> None:
    if obj is None:
        return
    mesh = obj.data if getattr(obj, "type", None) == "MESH" else None
    try:
        bpy.data.objects.remove(obj, do_unlink=True)
    except Exception:
        return
    if mesh is not None and mesh.users == 0:
        try:
            bpy.data.meshes.remove(mesh)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)


def _duplicate_segmented_sources(context, sources):
    """Create real Blender copies before composing the disposable target."""
    collection = _alignment_work_collection(context)
    duplicates = []
    for index, source in enumerate(sources, start=1):
        duplicate = source.copy()
        duplicate.data = source.data.copy()
        duplicate.name = f"ALIGN_DUP_{index:02d}_{source.name}"
        duplicate.matrix_world = source.matrix_world.copy()
        duplicate["DSG_alignment_duplicate"] = True
        duplicate["DSG_alignment_duplicate_source"] = source.name
        duplicate.hide_render = True
        collection.objects.link(duplicate)
        try:
            duplicate.hide_set(True)
            duplicate.hide_viewport = True
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        duplicates.append((source, duplicate))
    return duplicates


def _segmentation_signature(sources) -> str:
    records = []
    for obj in sources:
        mesh = getattr(obj, "data", None)
        records.append({
            "name": obj.name,
            "vertices": int(len(mesh.vertices)) if mesh is not None else 0,
            "polygons": int(len(mesh.polygons)) if mesh is not None else 0,
            "matrix": [round(float(v), 8) for row in obj.matrix_world for v in row],
        })
    return json.dumps(records, separators=(",", ":"), sort_keys=True)


def set_segmented_sources_alignment_visibility(context, visible: bool) -> None:
    """Show originals in DICOM; hide them while the two-object alignment is active."""
    for obj in segmented_alignment_source_objects(context):
        try:
            obj.hide_viewport = not bool(visible)
            obj.hide_set(not bool(visible))
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    for obj in list(getattr(context.scene, "objects", ())):
        if str(getattr(obj, "name", "")).startswith(LABEL_OBJECT_PREFIX):
            try:
                obj.hide_viewport = not bool(visible)
                obj.hide_set(not bool(visible))
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)


def clear_alignment_working_composite(context=None, *, restore_sources: bool = False) -> None:
    context = context or bpy.context
    for name in LEGACY_ALIGNMENT_REFERENCE_NAMES:
        obj = bpy.data.objects.get(name)
        if obj is not None:
            _delete_alignment_duplicate(obj)

    collection = bpy.data.collections.get(ALIGNMENT_WORK_COLLECTION)
    if collection is not None:
        for obj in list(collection.objects):
            _delete_alignment_duplicate(obj)
        if len(collection.objects) == 0:
            try:
                bpy.data.collections.remove(collection)
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)

    props = getattr(getattr(context, "scene", None), "dicp_props", None)
    if props is not None:
        try:
            target = props.icp_target_obj
            if target is not None and str(target.name) in LEGACY_ALIGNMENT_REFERENCE_NAMES:
                props.icp_target_obj = None
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)

    if restore_sources:
        set_segmented_sources_alignment_visibility(context, True)


def build_segmented_alignment_composite(
    context,
    *,
    set_generated_surface: bool = False,
) -> bpy.types.Object:
    """Duplicate every segmented CBCT mesh and merge the copies into one object.

    The result is disposable. Original clinical segmentations are never joined,
    transformed, remeshed or modified.

    Geometry order is intentional:
      [all tooth vertices/faces] + [bone] + [canal/safety]
    so the alignment engine can use only the dental prefix while the Blender
    scene still contains exactly two alignment objects: IOS + CBCT composite.
    """
    np = _np()
    from . import dicom_module

    sources = segmented_alignment_source_objects(context)
    teeth = dentition_objects(context)
    tooth_names = {obj.name for obj in teeth}
    if not teeth:
        raise RuntimeError("No hay dientes CBCT segmentados para construir el objeto de alineamiento")
    if not sources:
        raise RuntimeError("No hay elementos CBCT segmentados para duplicar")

    source_signature = _segmentation_signature(sources)
    clear_alignment_working_composite(context, restore_sources=False)

    duplicates = _duplicate_segmented_sources(context, sources)
    root = dicom_module.get_root(dicom_module.get_collection())
    root_inverse = root.matrix_world.inverted_safe()

    vertex_chunks = []
    face_chunks = []
    source_records = []
    material_records = []
    vertex_offset = 0
    face_offset = 0
    dental_vertex_count = 0
    dental_face_count = 0

    try:
        for source, duplicate in duplicates:
            mesh = getattr(duplicate, "data", None)
            if mesh is None or len(mesh.vertices) < 3:
                continue

            coords = np.empty(len(mesh.vertices) * 3, dtype=np.float64)
            mesh.vertices.foreach_get("co", coords)
            coords = coords.reshape((-1, 3))

            to_root = root_inverse @ duplicate.matrix_world
            matrix = np.asarray(to_root, dtype=np.float64)
            coords_root = coords @ matrix[:3, :3].T + matrix[:3, 3]

            mesh.calc_loop_triangles()
            tri_count = len(mesh.loop_triangles)
            if tri_count < 1:
                continue
            triangles = np.empty(tri_count * 3, dtype=np.int32)
            mesh.loop_triangles.foreach_get("vertices", triangles)
            triangles = triangles.reshape((-1, 3)) + int(vertex_offset)

            kind = _alignment_source_kind(source, tooth_names, dicom_module)
            v_start = int(vertex_offset)
            f_start = int(face_offset)
            v_end = v_start + int(len(coords_root))
            f_end = f_start + int(tri_count)

            vertex_chunks.append(coords_root)
            face_chunks.append(triangles)

            material_name = ""
            try:
                if len(source.data.materials) and source.data.materials[0] is not None:
                    material_name = str(source.data.materials[0].name)
            except Exception:
                material_name = ""

            source_records.append({
                "source": source.name,
                "duplicate": duplicate.name,
                "kind": kind,
                "fdi": int(source.get("DSG_fdi_number", 0) or 0),
                "vertex_start": v_start,
                "vertex_end": v_end,
                "face_start": f_start,
                "face_end": f_end,
                "material": material_name,
            })
            material_records.append((f_start, f_end, material_name, kind))

            vertex_offset = v_end
            face_offset = f_end
            if kind == "TOOTH":
                dental_vertex_count = v_end
                dental_face_count = f_end

        if not vertex_chunks or not face_chunks or dental_vertex_count < 3:
            raise RuntimeError("Las copias segmentadas no contienen geometría dental suficiente")

        vertices = np.concatenate(vertex_chunks, axis=0)
        faces = np.concatenate(face_chunks, axis=0)

        obj = dicom_module._new_surface_from_arrays(
            context,
            object_name=ALIGNMENT_COMPOSITE_NAME,
            vertices_xyz=vertices,
            faces=faces,
            root=root,
        )

        # Reuse source materials without editing them. This preserves visual
        # distinction between teeth/bone/canal inside the ONE composite object.
        slot_by_name = {}
        for f_start, f_end, material_name, kind in material_records:
            material = bpy.data.materials.get(material_name) if material_name else None
            if material is None:
                fallback = "TEETH" if kind == "TOOTH" else "BONE_ONLY"
                try:
                    material = dicom_module._surface_material(fallback)
                except Exception:
                    material = None
            if material is None:
                continue
            if material.name not in slot_by_name:
                slot_by_name[material.name] = len(obj.data.materials)
                obj.data.materials.append(material)
            slot = int(slot_by_name[material.name])
            for polygon_index in range(f_start, min(f_end, len(obj.data.polygons))):
                obj.data.polygons[polygon_index].material_index = slot

        try:
            for polygon in obj.data.polygons:
                polygon.use_smooth = True
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)

        dicom_module._set_suite_role(
            obj, dicom_module.ROLE_DICOM_ALIGNMENT_COMPOSITE, component="ALIGNMENT")
        obj["dental_suite_structure"] = "ALL_SEGMENTED_CBCT"
        obj["dental_suite_alignment_reference"] = True
        obj["dental_suite_alignment_reference_quality"] = ALIGNMENT_COMPOSITE_QUALITY
        obj["DSG_alignment_disposable"] = True
        obj["DSG_alignment_duplicate_composite"] = True
        obj["DSG_alignment_source_count"] = int(len(source_records))
        obj["DSG_alignment_tooth_count"] = int(len(teeth))
        obj["DSG_alignment_dental_vertex_count"] = int(dental_vertex_count)
        obj["DSG_alignment_dental_face_count"] = int(dental_face_count)
        obj["DSG_alignment_total_vertex_count"] = int(len(vertices))
        obj["DSG_alignment_total_face_count"] = int(len(faces))
        obj["DSG_alignment_source_signature"] = source_signature
        obj["DSG_alignment_components_json"] = json.dumps(
            source_records, separators=(",", ":"))
        obj["dicom_reference_stride"] = 1
        obj["dicom_reference_native_resolution"] = True
        obj["dicom_surface_method"] = "DUPLICATE_ALL_SEGMENTED_MESHES_NO_REMESH"
        obj.hide_render = True

        if set_generated_surface:
            props = context.scene.dicom_wizard_pro
            props.generated_surface_name = obj.name
            props.surface_ready = True

        context.scene["DSG_alignment_reference_pending"] = False
        context.scene["DSG_alignment_reference_status"] = "ALL_SEGMENTED_COMPOSITE_READY"
        return obj
    finally:
        # Intermediate duplicates prove the originals were never joined. Once the
        # unique composite exists, the temporary copies have no further purpose.
        for _source, duplicate in duplicates:
            if bpy.data.objects.get(duplicate.name) is not None:
                _delete_alignment_duplicate(duplicate)



def _immediate_source_hidden(obj) -> bool:
    hidden = bool(getattr(obj, "hide_viewport", False))
    try:
        hidden = hidden or bool(obj.hide_get())
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    return hidden


def _delete_named_mesh(name: str) -> None:
    obj = bpy.data.objects.get(name)
    if obj is None:
        return
    mesh = obj.data if obj.type == "MESH" else None
    try:
        bpy.data.objects.remove(obj, do_unlink=True)
    except Exception:
        return
    if mesh is not None and mesh.users == 0:
        try:
            bpy.data.meshes.remove(mesh)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)


def _join_immediate_arch_sources(context, *, arch: str, bone_obj, teeth, output_name: str, excluded_fdis: set[int]):
    """Duplicate and Ctrl+J one jaw with its visible teeth.

    This intentionally mirrors the clinician's requested Blender operation:
    maxilla joins only upper visible teeth; mandible joins only lower visible
    teeth.  The mandibular nerve is never part of ``sources`` and therefore can
    never be swallowed by this Ctrl+J composite.
    """
    if bone_obj is None or getattr(bone_obj, "type", None) != "MESH":
        raise RuntimeError(f"No se encontró el hueso separado para {arch}")
    _delete_named_mesh(output_name)
    collection = _alignment_work_collection(context)
    sources = [bone_obj] + list(teeth)
    duplicates = []
    for index, source in enumerate(sources):
        dup = source.copy()
        dup.data = source.data.copy()
        dup.name = f"__DSG_IMMEDIATE_JOIN_{arch}_{index:02d}__"
        dup.matrix_world = source.matrix_world.copy()
        dup.hide_viewport = False
        dup.hide_render = False
        dup.hide_select = False
        collection.objects.link(dup)
        try:
            dup.hide_set(False)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        duplicates.append(dup)
    if not duplicates:
        raise RuntimeError(f"No hay geometría para crear el modelo inmediato {arch}")

    previous_active = context.view_layer.objects.active
    previous_selection = list(context.selected_objects)
    # Ctrl+J removes every selected object except the active one. Never retain
    # and dereference those StructRNA wrappers after the operator: Blender then
    # raises "StructRNA of type Object has been removed" even when the join was
    # clinically successful. Names are stable lookup keys for cleanup/restore.
    duplicate_names = [str(dup.name) for dup in duplicates]
    previous_active_name = str(previous_active.name) if previous_active is not None else ""
    previous_selection_names = [str(obj.name) for obj in previous_selection]
    try:
        bpy.ops.object.mode_set(mode="OBJECT") if context.object and context.object.mode != "OBJECT" else None
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    try:
        bpy.ops.object.select_all(action="DESELECT")
        for dup in duplicates:
            dup.select_set(True)
        # The bone is active, exactly as if the user selected bone + teeth and
        # pressed Ctrl+J with the jaw object as the active object.
        context.view_layer.objects.active = duplicates[0]
        result = bpy.ops.object.join()
        if "FINISHED" not in result:
            raise RuntimeError(f"Ctrl+J no pudo unir {arch} con sus dientes")
        joined = context.view_layer.objects.active
        if joined is None or joined.type != "MESH":
            raise RuntimeError(f"Ctrl+J no devolvió una malla para {arch}")
        joined.name = output_name
        joined.data.name = output_name + "_Mesh"
        joined["DSG_immediate_arch_composite"] = True
        joined["DSG_bone_arch"] = str(arch).upper()
        joined["DSG_excluded_fdis"] = ",".join(str(v) for v in sorted(excluded_fdis))
        joined["DSG_visible_tooth_count"] = int(len(teeth))
        joined["DSG_join_method"] = "BLENDER_CTRL_J_DUPLICATES"
        joined["dental_suite_structure"] = f"IMMEDIATE_{str(arch).upper()}"
        joined["dental_suite_alignment_reference"] = False
        joined["dental_suite_component"] = "DICOM"
        return joined
    finally:
        # If join failed, remove any orphan duplicates. If it succeeded they no
        # longer exist except for the active joined object.
        for duplicate_name in duplicate_names:
            live_duplicate = bpy.data.objects.get(duplicate_name)
            if live_duplicate is not None and live_duplicate.name != output_name:
                _delete_alignment_duplicate(live_duplicate)
        try:
            if context.view_layer.objects.active is None:
                live_active = bpy.data.objects.get(previous_active_name) if previous_active_name else None
                context.view_layer.objects.active = live_active
            for object_name in previous_selection_names:
                live_object = bpy.data.objects.get(object_name)
                if live_object is not None and live_object != context.view_layer.objects.active:
                    live_object.select_set(True)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)


def build_immediate_arch_composites(context, *, excluded_fdis) -> dict[str, Any]:
    """Build the two socket-review models after the clinician hides teeth with H."""
    from . import dicom_module
    excluded = {int(v) for v in excluded_fdis if int(v) > 0}
    if not excluded:
        raise RuntimeError("No hay FDI de extracción seleccionados")

    maxilla = bpy.data.objects.get(str(context.scene.get("DSG_maxilla_object", "") or ""))
    mandible = bpy.data.objects.get(str(context.scene.get("DSG_mandible_object", "") or ""))
    if maxilla is None:
        maxilla = bpy.data.objects.get(dicom_module.NAME_DICOM_MAXILLA)
    if mandible is None:
        mandible = bpy.data.objects.get(dicom_module.NAME_DICOM_MANDIBLE)
    if maxilla is None or mandible is None:
        raise RuntimeError("La segmentación inmediata debe contener maxilar y mandíbula separados")

    upper_teeth = []
    lower_teeth = []
    for tooth in dentition_objects(context):
        fdi = int(tooth.get("DSG_fdi_number", 0) or 0)
        # H is the clinical extraction selection.  Excluded list is stored as a
        # second check so the socket remains open even if viewport visibility is
        # changed by a later UI refresh.
        if fdi in excluded or _immediate_source_hidden(tooth):
            continue
        arch = str(tooth_analysis.arch_from_fdi(fdi) or "")
        if arch == "MAXILLA":
            upper_teeth.append(tooth)
        elif arch == "MANDIBLE":
            lower_teeth.append(tooth)

    upper = _join_immediate_arch_sources(
        context, arch="MAXILLA", bone_obj=maxilla, teeth=upper_teeth,
        output_name=IMMEDIATE_UPPER_COMPOSITE_NAME, excluded_fdis=excluded,
    )
    lower = _join_immediate_arch_sources(
        context, arch="MANDIBLE", bone_obj=mandible, teeth=lower_teeth,
        output_name=IMMEDIATE_LOWER_COMPOSITE_NAME, excluded_fdis=excluded,
    )

    # Display exactly the two joined jaw models plus the independent nerve.
    for source in dentition_objects(context):
        try:
            source.hide_set(True)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    for source in (maxilla, mandible, bpy.data.objects.get(dicom_module.NAME_DICOM_BONE)):
        if source is not None:
            try:
                source.hide_set(True)
                source.hide_viewport = True
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
    for obj in (upper, lower):
        try:
            obj.hide_set(False)
            obj.hide_viewport = False
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    canal = bpy.data.objects.get(dicom_module.NAME_DICOM_MANDIBULAR_CANAL)
    if canal is not None:
        try:
            canal.hide_set(False)
            canal.hide_viewport = False
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        canal["DSG_immediate_join_excluded"] = True

    context.scene["DSG_immediate_upper_composite"] = upper.name
    context.scene["DSG_immediate_lower_composite"] = lower.name
    context.scene["DSG_immediate_excluded_fdis"] = ",".join(str(v) for v in sorted(excluded))
    return {
        "upper": upper,
        "lower": lower,
        "upper_teeth": len(upper_teeth),
        "lower_teeth": len(lower_teeth),
        "excluded_fdis": sorted(excluded),
        "canal_separate": canal is not None,
    }


def ensure_segmented_alignment_composite(context) -> bpy.types.Object:
    sources = segmented_alignment_source_objects(context)
    teeth = dentition_objects(context)
    if not teeth:
        raise RuntimeError("No hay dientes CBCT segmentados")
    signature = _segmentation_signature(sources)

    existing = bpy.data.objects.get(ALIGNMENT_COMPOSITE_NAME)
    if (
        existing is not None
        and existing.type == "MESH"
        and str(existing.get("dental_suite_alignment_reference_quality", "")) == ALIGNMENT_COMPOSITE_QUALITY
        and str(existing.get("DSG_alignment_source_signature", "")) == signature
        and int(existing.get("DSG_alignment_tooth_count", 0)) == len(teeth)
        and int(existing.get("DSG_alignment_dental_vertex_count", 0)) > 2
    ):
        return existing

    return build_segmented_alignment_composite(context)


# Compatibility names retained for internal/external callers. Their semantics are
# now the complete duplicated segmentation composite, not a tooth-only shell.
def build_native_tooth_alignment_reference(context, *, set_generated_surface: bool = False):
    return build_segmented_alignment_composite(
        context, set_generated_surface=set_generated_surface)


def ensure_native_tooth_alignment_reference(context):
    return ensure_segmented_alignment_composite(context)


def iter_build_universal_dentition(
    context, labels, *, run_mirroring_check: bool = False, alignment_max_axis: int = 176,
    prepared_meshes=None,
):
    """Yield after each tooth so Blender can redraw between mesh creations.

    Neural inference is already finished when this generator starts. Only Blender
    datablock creation happens here, on the main thread. One tooth per timer tick
    prevents a second UI freeze while 20-32 marching-cubes meshes are built.
    The generator's StopIteration.value is the same summary dictionary returned
    by :func:`build_universal_dentition`.
    """
    np = _np()
    from . import dicom_module
    labels = np.asarray(labels)
    if labels.ndim != 3:
        raise RuntimeError("El mapa UniversalLab no es 3D")
    present = _tooth_labels_present(labels)
    if not present:
        raise RuntimeError("UniversalLab no devolvió dientes individualizados")

    semantic_info = correct_universal_semantics(labels) if run_mirroring_check else {
        "arch": {"checked": False}, "laterality": {"checked": False}
    }
    arch_info = semantic_info.get("arch", {})
    mirror_info = semantic_info.get("laterality", {})
    present = _tooth_labels_present(labels)
    boxes = _bbox_slices(labels, 55)
    clear_dentition(keep_alignment_reference=False)
    root = dicom_module.get_root(dicom_module.get_collection())
    # Create/synchronize collections once. Doing this 20-32 times was avoidable
    # ViewLayer/depsgraph work on Blender's main thread.
    tooth_collection = _ensure_child_collection(context, COLLECTION_NAME)
    label_collection = _ensure_child_collection(context, LABEL_COLLECTION_NAME)

    tooth_count = 0
    primary_count = 0
    total_faces = 0
    records = []
    invalid_topology = []
    mesh_build_total_s = 0.0
    # Optional DSG 9.1.33 audit from the path-continuity reconciler.  Failure to
    # decode it never affects clinical geometry.
    path_by_label = {}
    try:
        raw_path = context.scene.get("DSG_tooth_path_reconciliation_json", "")
        path_payload = json.loads(raw_path) if isinstance(raw_path, str) and raw_path else {}
        for arch_key in ("upper", "lower"):
            for item in ((path_payload.get(arch_key) or {}).get("teeth") or []):
                path_by_label[int(item.get("label", 0) or 0)] = dict(item)
    except Exception:
        path_by_label = {}
    prepared_by_label = {}
    prepared_total_s = 0.0
    if isinstance(prepared_meshes, dict):
        prepared_total_s = float(prepared_meshes.get("prepare_s", 0.0) or 0.0)
        for item in prepared_meshes.get("items", []) or []:
            try:
                prepared_by_label[int(item.get("label", 0))] = item
            except Exception:
                continue
    total_candidates = len(present)
    for index, label in enumerate(present, start=1):
        bbox = boxes[label - 1] if label - 1 < len(boxes) else None
        if bbox is None:
            yield {"phase": "tooth", "index": index, "total": total_candidates, "label": int(label), "skipped": True}
            continue
        build_started = time.perf_counter()
        prepared = prepared_by_label.pop(int(label), None)
        result = (
            _commit_prepared_tooth(context, prepared, root, tooth_collection)
            if prepared is not None
            else _mesh_from_label(context, labels, label, bbox, root, tooth_collection)
        )
        build_s = time.perf_counter() - build_started
        mesh_build_total_s += build_s
        if result is None:
            yield {"phase": "tooth", "index": index, "total": total_candidates, "label": int(label), "skipped": True}
            continue
        obj, centroid, faces, topology = result
        fdi = int(obj["DSG_fdi_number"])
        path_info = path_by_label.get(int(label))
        if path_info:
            obj["DSG_tooth_path_status"] = str(path_info.get("status", ""))
            obj["DSG_tooth_path_growth_ratio"] = float(path_info.get("growth_ratio", 1.0) or 1.0)
            obj["DSG_tooth_path_seed_voxels"] = int(path_info.get("seed_voxels", 0) or 0)
            obj["DSG_tooth_path_territory_voxels"] = int(path_info.get("territory_voxels", 0) or 0)
            obj["DSG_tooth_path_reconciled"] = bool(path_info.get("status") == "PATH_RECONSTRUCTED")
        if int(topology.get("significant_component_count", 0)) > 1:
            invalid_topology.append({
                "label": int(label),
                "fdi": int(fdi),
                "warning": "varias islas >=60 mm3; se materializó solo la principal",
                "diagnostics": dict(topology),
            })
        tooth_count += 1
        primary_count += int(fdi >= 50)
        total_faces += faces
        records.append({"label": int(label), "fdi": fdi, "object": obj.name, "faces": int(faces), "build_s": float(build_s)})
        yield {
            "phase": "tooth", "index": index, "total": total_candidates,
            "label": int(label), "fdi": int(fdi), "faces": int(faces),
            "tooth_count": int(tooth_count), "build_s": float(build_s),
        }

    if tooth_count == 0:
        raise RuntimeError("No se pudo crear ninguna superficie dental")

    # FDI layout requires the complete arch. Build the overlay only after every
    # segmented tooth exists, so vestibular directions use the full arch.
    # UI overlay is best-effort only. Tooth FDI identity is already stored on
    # the clinical tooth objects and cannot be rolled back by FONT placement.
    rebuild_fdi_labels(context, strict=False)

    # Segmentation ends here with clinical tooth geometry. The numerical
    # alignment target belongs to the NEXT stage and is built on demand.
    # This prevents an Alignment preparation error from rolling back a valid
    # UniversalLab segmentation.
    ref = None

    props = context.scene.dsg_cbct_dental
    props.ready = True
    props.accepted = False
    props.tooth_count = int(tooth_count)
    props.primary_count = int(primary_count)
    props.labels_visible = True
    arch_source = str(arch_info.get("source", "NONE") or "NONE")
    arch_corrected = bool(arch_info.get("corrected", False))
    arch_ambiguous = len(arch_info.get("ambiguous_labels", []) or [])
    arch_text = (
        "arcos corregidos" if arch_corrected else
        "arcos revisar" if not arch_info.get("checked", False) or arch_ambiguous else
        "arcos verificados"
    )
    topology_count = len(invalid_topology)
    topology_text = f" · {topology_count} FDI REVISAR" if topology_count else ""
    props.status = f"{tooth_count} dientes · {arch_text}{topology_text} · FDI CBCT · mallas {mesh_build_total_s:.1f} s"
    context.scene["DSG_cbct_topology_invalid_count"] = int(topology_count)
    context.scene["DSG_cbct_topology_invalid_json"] = json.dumps(invalid_topology, ensure_ascii=False)
    # Every new segmentation invalidates any earlier clinical acknowledgement.
    # The geometry itself is already cleaned to the dominant connected island,
    # but the clinician must visually confirm that the retained island carries
    # the intended FDI before the warning is considered reviewed.
    context.scene["DSG_cbct_topology_review_acknowledged"] = False
    context.scene["DSG_cbct_topology_review_acknowledged_count"] = 0
    context.scene["DSG_cbct_topology_review_acknowledged_fdis"] = "[]"
    context.scene["DSG_cbct_arch_validation_source"] = arch_source
    context.scene["DSG_cbct_arch_validation_checked"] = bool(arch_info.get("checked", False))
    context.scene["DSG_cbct_arch_validation_corrected"] = arch_corrected
    context.scene["DSG_cbct_arch_validation_reason"] = str(arch_info.get("reason", "") or "")
    context.scene["DSG_cbct_arch_validation_ambiguous"] = int(arch_ambiguous)
    context.scene[SCENE_ACCEPTED_KEY] = False
    context.scene["DSG_tooth_analysis_completed"] = False
    return {
        "alignment_reference": None, "tooth_count": tooth_count,
        "primary_count": primary_count, "total_faces": total_faces,
        "arch": arch_info, "mirror": mirror_info, "records": records,
        "invalid_topology": invalid_topology,
        "mesh_build_s": float(mesh_build_total_s),
        "mesh_prepare_worker_s": float(prepared_total_s),
    }


def build_universal_dentition(context, labels, *, run_mirroring_check: bool = True) -> dict[str, Any]:
    """Synchronous compatibility wrapper around the single dentition builder."""
    iterator = iter_build_universal_dentition(
        context, labels, run_mirroring_check=run_mirroring_check, alignment_max_axis=192
    )
    while True:
        try:
            next(iterator)
        except StopIteration as finished:
            return finished.value or {}


def current_payload(scene=None) -> dict[str, Any]:
    objects = dentition_objects()
    return {
        "schema": tooth_analysis.SCHEMA,
        "asset_schema": dental_assets.schema(),
        "asset_contract_version": dental_assets.contract_version(),
        "asset_contract_sha256": dental_assets.contract_sha256(),
        "asset_contract_file": dental_assets.CONTRACT_FILENAME,
        "numbering_system": "FDI_ISO_3950",
        "identity_source": "CBCT_TotalSegmentator",
        "reviewed": bool((scene or bpy.context.scene).get(SCENE_ACCEPTED_KEY, False)) if (scene or getattr(bpy.context, "scene", None)) else False,
        "teeth": [
            {
                "fdi": int(obj.get("DSG_fdi_number", 0)),
                "model_fdi": int(obj.get("DSG_model_fdi_number", obj.get("DSG_fdi_number", 0))),
                "user_override": bool(obj.get("DSG_fdi_user_override", False)),
                "universal_label": int(obj.get("DSG_universal_label", 0)),
                "source": str(obj.get("DSG_source", "CBCT_TOTALSEGMENTATOR")),
                "volume_mm3": float(obj.get("DSG_volume_mm3", 0.0)),
                "voxel_count": int(obj.get("DSG_voxel_count", 0)),
                "review_state": "ACCEPTED" if bool(obj.get("DSG_label_verified", False)) else "REVIEW",
                "family_id": str(obj.get("DSG_family_id", dental_assets.family_id(int(obj.get("DSG_fdi_number", 0))))),
                "asset_id": str(obj.get("DSG_asset_id", dental_assets.asset_id(int(obj.get("DSG_fdi_number", 0)), "TOOTH"))),
                "tooth_class": tooth_analysis.tooth_class_from_fdi(int(obj.get("DSG_fdi_number", 0))),
                "arch": tooth_analysis.arch_from_fdi(int(obj.get("DSG_fdi_number", 0))),
                "side": tooth_analysis.side_from_fdi(int(obj.get("DSG_fdi_number", 0))),
                "object": obj.name,
            }
            for obj in objects
        ],
    }


class DSGCBCTDentalProperties(PropertyGroup):
    ready: BoolProperty(default=False, options={"HIDDEN"})
    accepted: BoolProperty(default=False, options={"HIDDEN"})
    tooth_count: IntProperty(default=0, min=0, options={"HIDDEN"})
    primary_count: IntProperty(default=0, min=0, options={"HIDDEN"})
    labels_visible: BoolProperty(default=True)
    status: StringProperty(default="")


class DSG_OT_CBCTAcceptFDI(Operator):
    bl_idname = "dsg.cbct_accept_fdi"
    bl_label = "Confirmar FDI"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        objects = dentition_objects()
        if not objects:
            self.report({"ERROR"}, "No hay dientes CBCT individualizados")
            return {"CANCELLED"}
        # Recovery for scenes produced by 9.2.20 before the incremental builder
        # propagated UniversalLab's already-computed arch validation to Scene.
        # Re-evaluate the cached integer labelmap; never infer arch from the mesh
        # names or silently mark an ambiguous result as checked.
        if not bool(context.scene.get("DSG_cbct_arch_validation_checked", False)):
            try:
                from . import dicom_module
                labels = dicom_module.get_cached_semantic_cbct_labels(
                    model_kind="universal", require_current_source=True
                )
                if labels is not None:
                    semantic_info = correct_universal_semantics(labels)
                    arch_info = dict(semantic_info.get("arch") or {})
                    ambiguous = len(arch_info.get("ambiguous_labels", []) or [])
                    context.scene["DSG_cbct_arch_validation_source"] = str(
                        arch_info.get("source", "UNIVERSALLAB_RECOVERY") or "UNIVERSALLAB_RECOVERY"
                    )
                    context.scene["DSG_cbct_arch_validation_checked"] = bool(
                        arch_info.get("checked", False)
                    ) and ambiguous == 0
                    context.scene["DSG_cbct_arch_validation_corrected"] = bool(
                        arch_info.get("corrected", False)
                    )
                    context.scene["DSG_cbct_arch_validation_reason"] = str(
                        arch_info.get("reason", "") or ""
                    )
                    context.scene["DSG_cbct_arch_validation_ambiguous"] = int(ambiguous)
            except Exception as exc:
                print(f"[DSG CBCT] No se pudo recuperar la validación de arcos: {exc}")
        invalid_topology_count = int(context.scene.get("DSG_cbct_topology_invalid_count", 0) or 0)
        automatic_ambiguity = int(context.scene.get("DSG_cbct_arch_validation_ambiguous", 0) or 0)
        fdis = [int(obj.get("DSG_fdi_number", 0)) for obj in objects]
        if len(fdis) != len(set(fdis)) or any(not tooth_analysis.valid_fdi(v, include_primary=True) for v in fdis):
            self.report({"ERROR"}, "La numeración contiene FDI duplicados o inválidos")
            return {"CANCELLED"}

        # A multi-component learned label is not itself multi-component clinical
        # geometry: both the VTK and Lewiner builders have already discarded all
        # but the dominant connected surface before the Blender object is created.
        # The old gate nevertheless cancelled confirmation using the *pre-cleanup*
        # diagnostic count, which made an otherwise valid dentition impossible to
        # accept.  Treat this as an explicit visual-review warning instead.
        topology_review_objects = [
            obj for obj in objects
            if int(obj.get("DSG_significant_component_count", 0) or 0) > 1
        ]
        topology_review_fdis = sorted({
            int(obj.get("DSG_fdi_number", 0) or 0)
            for obj in topology_review_objects
            if int(obj.get("DSG_fdi_number", 0) or 0) > 0
        })
        if invalid_topology_count or topology_review_objects:
            context.scene["DSG_cbct_topology_review_acknowledged"] = True
            context.scene["DSG_cbct_topology_review_acknowledged_count"] = int(
                max(invalid_topology_count, len(topology_review_objects))
            )
            context.scene["DSG_cbct_topology_review_acknowledged_fdis"] = json.dumps(
                topology_review_fdis, ensure_ascii=False
            )
            for obj in topology_review_objects:
                obj["DSG_topology_review_acknowledged"] = True
                obj["DSG_topology_review_policy"] = "PRIMARY_COMPONENT_VISUALLY_CONFIRMED"
            shown = ", ".join(str(v) for v in topology_review_fdis[:8])
            suffix = f" (FDI {shown})" if shown else ""
            self.report(
                {"WARNING"},
                f"Revisión registrada: {max(invalid_topology_count, len(topology_review_objects))} "
                f"FDI tenían islas secundarias descartadas{suffix}"
            )
        if not bool(context.scene.get("DSG_cbct_arch_validation_checked", False)) or automatic_ambiguity:
            # The button is an explicit visual confirmation by the clinician.
            # Some valid CBCT series do not expose enough patient-orientation
            # metadata for the automatic arch validator, and partial scans can
            # make its maxilla/mandible confidence ambiguous.  Neither should
            # reject a coherent FDI layout the clinician has explicitly checked.
            # Invalid/duplicate FDI and disconnected anatomy were rejected above.
            if automatic_ambiguity:
                context.scene["DSG_cbct_arch_validation_auto_ambiguous"] = automatic_ambiguity
            context.scene["DSG_cbct_arch_validation_source"] = "USER_VISUAL_CONFIRMATION"
            context.scene["DSG_cbct_arch_validation_checked"] = True
            context.scene["DSG_cbct_arch_validation_corrected"] = False
            context.scene["DSG_cbct_arch_validation_reason"] = (
                "FDI coherente confirmado visualmente; "
                + ("ambigüedad automática de arcos revisada" if automatic_ambiguity else "orientación DICOM automática no disponible")
            )
            context.scene["DSG_cbct_arch_validation_ambiguous"] = 0
            self.report({"INFO"}, "FDI confirmado visualmente; se registró la validación clínica de los arcos")
        for obj in objects:
            obj["DSG_label_verified"] = True
        props = context.scene.dsg_cbct_dental
        props.accepted = True
        reviewed_topology_count = int(context.scene.get("DSG_cbct_topology_review_acknowledged_count", 0) or 0)
        topology_suffix = f" · {reviewed_topology_count} avisos de islas revisados" if reviewed_topology_count else ""
        props.status = f"FDI confirmado · {len(objects)} dientes{topology_suffix}"
        context.scene[SCENE_ACCEPTED_KEY] = True
        context.scene["DSG_tooth_analysis_completed"] = True
        self.report({"INFO"}, props.status)
        return {"FINISHED"}


class DSG_OT_CBCTImproveGeometry(Operator):
    bl_idname = "dsg.cbct_improve_geometry"
    bl_label = "Mejorar geometría"
    bl_description = "Refina el diente activo contra el borde del CBCT original con límites subvoxel"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = getattr(context.view_layer.objects, "active", None)
        return bool(
            obj is not None and getattr(obj, "type", "") == "MESH"
            and int(obj.get("DSG_universal_label", 0) or 0) > 0
            and int(obj.get("DSG_fdi_number", 0) or 0) > 0
        )

    def execute(self, context):
        np = _np()
        from . import anatomy_refine, dicom_module

        obj = context.view_layer.objects.active
        label = int(obj.get("DSG_universal_label", 0) or 0)
        fdi = int(obj.get("DSG_fdi_number", 0) or 0)
        if str(obj.get("DSG_geometry_resolution", "") or "") == "FDI_PREVIEW":
            try:
                summary = upgrade_teeth_to_full_resolution(context, (fdi,))
            except Exception as exc:
                self.report({"ERROR"}, f"No se pudo recuperar la geometría CBCT completa: {exc}")
                return {"CANCELLED"}
            context.scene.dsg_cbct_dental.status = (
                f"FDI {fdi} reconstruido a resolución CBCT completa · "
                f"{float(summary.get('elapsed_s', 0.0)):.1f} s"
            )
            self.report({"INFO"}, context.scene.dsg_cbct_dental.status)
            return {"FINISHED"}
        labels = dicom_module.get_cached_semantic_cbct_labels(
            model_kind="universal", require_current_source=True
        )
        if labels is None:
            self.report({"ERROR"}, "El CBCT/labelmap original ya no está disponible; vuelve a cargar el caso")
            return {"CANCELLED"}

        boxes = _bbox_slices(labels, 55)
        bbox = boxes[label - 1] if 0 < label <= len(boxes) else None
        if bbox is None:
            self.report({"ERROR"}, f"No se encontró la máscara radiográfica del FDI {fdi}")
            return {"CANCELLED"}
        zsl, ysl, xsl = bbox
        z0 = max(0, int(zsl.start) - 2); z1 = min(labels.shape[0], int(zsl.stop) + 2)
        y0 = max(0, int(ysl.start) - 2); y1 = min(labels.shape[1], int(ysl.stop) + 2)
        x0 = max(0, int(xsl.start) - 2); x1 = min(labels.shape[2], int(xsl.stop) + 2)
        mask = np.asarray(labels[z0:z1, y0:y1, x0:x1] == label, dtype=np.uint8)

        mesh = obj.data
        if len(mesh.vertices) < 4 or len(mesh.polygons) < 4 or any(len(p.vertices) != 3 for p in mesh.polygons):
            self.report({"ERROR"}, "El diente debe ser una malla triangular válida")
            return {"CANCELLED"}
        vertices = np.empty(len(mesh.vertices) * 3, dtype=np.float64)
        triangles = np.empty(len(mesh.polygons) * 3, dtype=np.int32)
        mesh.vertices.foreach_get("co", vertices)
        mesh.polygons.foreach_get("vertices", triangles)
        vertices = vertices.reshape((-1, 3))
        triangles = triangles.reshape((-1, 3))

        refined_v, refined_f, stats = anatomy_refine.refine_segmented_surface(
            context, vertices, triangles, mask=mask, origin_zyx=(z0, y0, x0),
            kind="TOOTH_HIGH", label=label,
        )
        if str(stats.get("status", "")) != "OK":
            self.report({"ERROR"}, f"Refinado rechazado por seguridad: {stats.get('reason', 'resultado no válido')}")
            return {"CANCELLED"}

        # Keep the exact previous datablock recoverable in the .blend in addition
        # to Blender Undo. The clinical object identity and transform do not change.
        old_mesh = mesh
        old_mesh.name = f"DSG_Backup_FDI_{fdi}_Before_CBCT_Refine"
        old_mesh.use_fake_user = True
        new_mesh = bpy.data.meshes.new(f"{obj.name}_CBCT_Refined_Mesh")
        new_mesh.from_pydata(
            np.asarray(refined_v, dtype=np.float32).tolist(), [],
            np.asarray(refined_f, dtype=np.int32).tolist(),
        )
        new_mesh.update()
        for material in old_mesh.materials:
            new_mesh.materials.append(material)
        obj.data = new_mesh
        for polygon in new_mesh.polygons:
            polygon.use_smooth = True
        obj["DSG_geometry_improved"] = True
        obj["DSG_geometry_improved_source"] = "CBCT_EDGE_MASK_CAGED"
        obj["DSG_geometry_improved_backup_mesh"] = old_mesh.name
        obj["DSG_geometry_improved_json"] = json.dumps(stats, ensure_ascii=False, default=str)
        snapped = int(stats.get("cbct_snapped", 0) or 0)
        context.scene.dsg_cbct_dental.status = f"FDI {fdi} mejorado contra CBCT · {snapped:,} vértices ajustados"
        self.report({"INFO"}, context.scene.dsg_cbct_dental.status)
        return {"FINISHED"}


class DSG_OT_CBCTToggleFDI(Operator):
    bl_idname = "dsg.cbct_toggle_fdi"
    bl_label = "Mostrar/Ocultar FDI"
    bl_options = {"REGISTER"}

    def execute(self, context):
        props = context.scene.dsg_cbct_dental
        props.labels_visible = not bool(props.labels_visible)
        labels_visible(props.labels_visible)
        return {"FINISHED"}


class DSG_OT_CBCTEditFDI(Operator):
    bl_idname = "dsg.cbct_edit_fdi"
    bl_label = "Corregir FDI seleccionado"
    bl_options = {"REGISTER", "UNDO"}

    new_fdi: IntProperty(name="FDI", min=11, max=85, default=11)

    @classmethod
    def poll(cls, context):
        obj = context.view_layer.objects.active
        return bool(obj and obj.type == "MESH" and obj.name.startswith(TOOTH_OBJECT_PREFIX))

    def invoke(self, context, event):
        obj = context.view_layer.objects.active
        self.new_fdi = int(obj.get("DSG_fdi_number", 11)) if obj else 11
        return context.window_manager.invoke_props_dialog(self, width=300)

    def execute(self, context):
        obj = context.view_layer.objects.active
        if obj is None or not obj.name.startswith(TOOTH_OBJECT_PREFIX):
            return {"CANCELLED"}
        value = int(self.new_fdi)
        if not tooth_analysis.valid_fdi(value, include_primary=True):
            self.report({"ERROR"}, "FDI no válido")
            return {"CANCELLED"}
        for other in dentition_objects():
            if other != obj and int(other.get("DSG_fdi_number", 0)) == value:
                self.report({"ERROR"}, f"FDI {value} ya está asignado")
                return {"CANCELLED"}
        old = int(obj.get("DSG_fdi_number", 0))
        model_fdi = int(obj.get("DSG_model_fdi_number", old))
        try:
            dental_asset_blender.stamp_object(
                obj, fdi=value, role="TOOTH",
                source=str(obj.get("DSG_asset_source", obj.get("DSG_source", "USER")) or "USER"),
                coordinate_space=str(obj.get("DSG_coordinate_space", "CBCT_DSG_ROOT") or "CBCT_DSG_ROOT"),
                rename=True,
            )
        except Exception as exc:
            self.report({"ERROR"}, f"No se pudo reasignar la familia FDI: {exc}")
            return {"CANCELLED"}
        obj["DSG_fdi_number"] = value
        obj["DSG_fdi_user_override"] = bool(value != model_fdi)
        obj["DSG_tooth_arch"] = tooth_analysis.arch_from_fdi(value)
        obj["DSG_tooth_side"] = tooth_analysis.side_from_fdi(value)
        obj["DSG_tooth_class"] = tooth_analysis.tooth_class_from_fdi(value)
        obj["DSG_label_verified"] = False
        old_label_name = dental_assets.object_name(old, "FDI_LABEL")
        label_obj = bpy.data.objects.get(old_label_name)
        if label_obj is not None and label_obj.type == "FONT":
            dental_asset_blender.stamp_object(
                label_obj, fdi=value, role="FDI_LABEL", source="CBCT_TOTALSEGMENTATOR",
                coordinate_space="CBCT_DSG_ROOT", rename=True,
            )
            label_obj.data.body = str(value)
            label_obj["DSG_fdi_number"] = value
        rebuild_fdi_labels(context)
        props = context.scene.dsg_cbct_dental
        props.accepted = False
        context.scene[SCENE_ACCEPTED_KEY] = False
        context.scene["DSG_tooth_analysis_completed"] = False
        return {"FINISHED"}


class DSG_OT_CBCTSwapArches(Operator):
    bl_idname = "dsg.cbct_swap_arches"
    bl_label = "Intercambiar maxilar / mandíbula"
    bl_description = (
        "Intercambia todos los FDI entre arcos conservando lado y posición dental. "
        "Úsalo solo durante la revisión si la identificación automática del arco es incorrecta."
    )
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return bool(dentition_objects())

    def execute(self, context):
        objects = list(dentition_objects())
        plan = []
        for obj in objects:
            old_label = int(obj.get("DSG_universal_label", 0) or 0)
            new_label = tooth_analysis.universal_arch_counterpart(old_label)
            new_fdi = tooth_analysis.universal_to_fdi(new_label, source="CBCT")
            if not new_label or not new_fdi:
                self.report({"ERROR"}, f"No se puede intercambiar arco para {obj.name}")
                return {"CANCELLED"}
            plan.append((obj, old_label, new_label, int(new_fdi)))

        # Temporary names avoid 18<->48 style object-name collisions.
        for index, (obj, _, _, _) in enumerate(plan):
            obj.name = f"__DSG_ARCH_SWAP_{index:02d}__"

        label_objects = {}
        for obj, old_label, new_label, new_fdi in plan:
            old_fdi = int(obj.get("DSG_fdi_number", 0) or 0)
            lab = bpy.data.objects.get(dental_assets.object_name(old_fdi, "FDI_LABEL"))
            if lab is not None:
                label_objects[obj.as_pointer()] = lab
                lab.name = f"__DSG_ARCH_LABEL_SWAP_{obj.as_pointer()}__"

        for obj, old_label, new_label, new_fdi in plan:
            source = str(obj.get("DSG_source", "CBCT_TOTALSEGMENTATOR") or "CBCT_TOTALSEGMENTATOR")
            dental_asset_blender.stamp_object(
                obj, fdi=new_fdi, role="TOOTH", source=source,
                coordinate_space=str(obj.get("DSG_coordinate_space", "CBCT_DSG_ROOT") or "CBCT_DSG_ROOT"),
                rename=True,
            )
            obj["DSG_universal_label"] = int(new_label)
            obj["DSG_fdi_number"] = int(new_fdi)
            obj["DSG_model_fdi_number"] = int(new_fdi)
            obj["DSG_fdi_user_override"] = True
            obj["DSG_tooth_arch"] = tooth_analysis.arch_from_fdi(new_fdi)
            obj["DSG_tooth_side"] = tooth_analysis.side_from_fdi(new_fdi)
            obj["DSG_tooth_class"] = tooth_analysis.tooth_class_from_fdi(new_fdi)
            obj["DSG_label_verified"] = False

            lab = label_objects.get(obj.as_pointer())
            if lab is not None and lab.type == "FONT":
                dental_asset_blender.stamp_object(
                    lab, fdi=new_fdi, role="FDI_LABEL", source="CBCT_TOTALSEGMENTATOR",
                    coordinate_space="CBCT_DSG_ROOT", rename=True,
                )
                lab.data.body = str(new_fdi)
                lab["DSG_fdi_number"] = int(new_fdi)

        rebuild_fdi_labels(context)
        props = context.scene.dsg_cbct_dental
        props.accepted = False
        props.status = f"{len(plan)} dientes · maxilar/mandíbula intercambiados manualmente · revisar FDI"
        context.scene[SCENE_ACCEPTED_KEY] = False
        context.scene["DSG_tooth_analysis_completed"] = False
        context.scene["DSG_cbct_arch_validation_source"] = "USER_ARCH_SWAP"
        context.scene["DSG_cbct_arch_validation_checked"] = True
        context.scene["DSG_cbct_arch_validation_corrected"] = True
        context.scene["DSG_cbct_arch_validation_reason"] = "intercambio manual de arcos"
        context.scene["DSG_cbct_arch_validation_ambiguous"] = 0
        self.report({"WARNING"}, "Arcos intercambiados. Revisa la numeración antes de confirmar FDI.")
        return {"FINISHED"}


class DSG_OT_CBCTDeleteTooth(Operator):
    bl_idname = "dsg.cbct_delete_tooth"
    bl_label = "Marcar diente como ausente"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.view_layer.objects.active
        return bool(obj and obj.type == "MESH" and obj.name.startswith(TOOTH_OBJECT_PREFIX))

    def execute(self, context):
        obj = context.view_layer.objects.active
        fdi = int(obj.get("DSG_fdi_number", 0))
        label = bpy.data.objects.get(dental_assets.object_name(fdi, "FDI_LABEL"))
        if label is not None:
            _delete_object(label)
        _delete_object(obj)
        rebuild_fdi_labels(context)
        props = context.scene.dsg_cbct_dental
        props.tooth_count = len(dentition_objects())
        props.accepted = False
        context.scene[SCENE_ACCEPTED_KEY] = False
        context.scene["DSG_tooth_analysis_completed"] = False
        return {"FINISHED"}


def draw_review(layout, context) -> None:
    props = getattr(context.scene, "dsg_cbct_dental", None)
    if props is None or not props.ready or not dentition_objects():
        return
    box = layout.box()
    box.label(text="Dentición CBCT · FDI", icon_value=icon_manager.icon_id("status_ok"))
    if props.primary_count:
        box.label(text=f"{props.tooth_count} dientes · {props.primary_count} temporales")
    else:
        box.label(text=f"{props.tooth_count} dientes individualizados")
    box.label(text="TotalSegmentator · FDI obtenido directamente del CBCT")
    if str(getattr(props, "status", "")):
        box.label(text=str(props.status)[:110])

    row = ui_style.secondary_action(box)
    row.operator(DSG_OT_CBCTToggleFDI.bl_idname, text="OCULTAR FDI" if props.labels_visible else "MOSTRAR FDI")
    edit = row.operator(DSG_OT_CBCTEditFDI.bl_idname, text="CORREGIR FDI")
    del edit
    row2 = ui_style.tertiary_action(box)
    row2.operator(DSG_OT_CBCTDeleteTooth.bl_idname, text="MARCAR AUSENTE")
    row2.operator(DSG_OT_CBCTSwapArches.bl_idname, text="INTERCAMBIAR ARCOS")

    improve = ui_style.primary_action(box)
    improve.operator(
        DSG_OT_CBCTImproveGeometry.bl_idname,
        text="MEJORAR GEOMETRÍA",
        icon="MOD_SMOOTH",
    )
    box.label(text="Selecciona un diente · ajuste subvoxel contra el CBCT original")

    arch_checked = bool(context.scene.get("DSG_cbct_arch_validation_checked", False))
    arch_source = str(context.scene.get("DSG_cbct_arch_validation_source", "NONE") or "NONE")
    arch_reason = str(context.scene.get("DSG_cbct_arch_validation_reason", "") or "")
    arch_row = box.row()
    arch_row.alert = not arch_checked
    arch_row.label(
        text=f"Arco: {'verificado' if arch_checked else 'REVISAR'} · {arch_source}"
    )
    if arch_reason:
        box.label(text=arch_reason[:105])

    invalid_topology_count = int(context.scene.get("DSG_cbct_topology_invalid_count", 0) or 0)
    if invalid_topology_count:
        topology_ack = bool(context.scene.get("DSG_cbct_topology_review_acknowledged", False))
        topo = box.row()
        topo.alert = not topology_ack
        topo.label(text=(
            f"Revisado: {invalid_topology_count} FDI tenían varias islas dentarias"
            if topology_ack else
            f"Revisar: {invalid_topology_count} FDI tenían varias islas dentarias"
        ))
        box.label(text=(
            "Confirmación clínica registrada · las islas secundarias quedaron descartadas"
            if topology_ack else
            "DSG muestra solo la isla principal; confirma visualmente su FDI para continuar"
        ))

    accept = ui_style.primary_action(box)
    accept.operator(
        DSG_OT_CBCTAcceptFDI.bl_idname,
        text="FDI CONFIRMADO ✓" if props.accepted else "CONFIRMAR DENTICIÓN FDI",
        icon_value=icon_manager.icon_id("status_ok") if props.accepted else 0,
    )
    if not props.accepted:
        note = box.row()
        note.alert = True
        note.label(text="Confirma la numeración antes de pasar a alineamiento")


def draw_alignment_handoff(layout, context) -> None:
    objects = dentition_objects()
    if not objects:
        return
    accepted = bool(context.scene.get(SCENE_ACCEPTED_KEY, False))
    box = layout.box()
    box.label(text="FDI procedente del CBCT", icon_value=icon_manager.icon_id("status_ok" if accepted else "status_info"))
    box.label(text=f"{len(objects)} dientes · {'confirmado' if accepted else 'pendiente de revisión'}")
    box.label(text="El IOS se usa para alineamiento; no vuelve a numerar los dientes")


class DSG_OT_InstallAIRuntime(Operator):
    """Compatibility button from older DSG layouts; installs TotalSegmentator only."""
    bl_idname = "dsg.install_ai_runtime"
    bl_label = "Instalar TotalSegmentator"
    bl_description = "Instala TotalSegmentator y los modelos task=teeth en un runtime aislado"
    bl_options = {"REGISTER"}

    def execute(self, context):
        from . import totalseg_runtime
        status = totalseg_runtime.quick_status()
        if status.dependencies_ready and status.model_ready:
            self.report({"INFO"}, f"TotalSegmentator {status.version} ya está listo · {status.device}")
            return {"FINISHED"}
        try:
            started = totalseg_runtime.start_install()
        except Exception as exc:
            msg = f"TotalSegmentator: {type(exc).__name__}: {exc}"
            try:
                context.scene.dicom_wizard_pro.status = msg[:240]
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
            self.report({"ERROR"}, msg[:240])
            return {"CANCELLED"}
        if not started:
            self.report({"INFO"}, "La instalación TotalSegmentator ya está en curso")
        else:
            pd = totalseg_runtime.payload_diagnostics()
            complete = all(pd.get(k) for k in ("runtime_archive", "dataset113", "dataset115"))
            self.report({"INFO"}, "Extrayendo payload local" if complete else "Construyendo payload completo + instalando")
        return {"FINISHED"}


class DSG_OT_AIStatusRefresh(Operator):
    bl_idname = "dsg.ai_status_refresh"
    bl_label = "Revisar TotalSegmentator"
    bl_options = {"REGISTER"}

    def execute(self, context):
        from . import totalseg_runtime
        status = totalseg_runtime.quick_status()
        context.scene.dicom_wizard_pro.status = (
            f"TotalSegmentator {status.version} · {status.device} · task=teeth "
            + ("✓" if status.dependencies_ready and status.model_ready else f"pendiente · {status.error}")
        )
        return {"FINISHED"}



CLASSES = (
    DSGCBCTDentalProperties,
    DSG_OT_InstallAIRuntime,
    DSG_OT_AIStatusRefresh,
    DSG_OT_CBCTImproveGeometry,
    DSG_OT_CBCTAcceptFDI,
    DSG_OT_CBCTToggleFDI,
    DSG_OT_CBCTEditFDI,
    DSG_OT_CBCTSwapArches,
    DSG_OT_CBCTDeleteTooth,
)


_REGISTERED_CLASSES = []
_SCENE_PROPERTY_OWNED = False
_DEFERRED_METADATA_MIGRATED = False


def _cleanup_stale_registration() -> None:
    """Remove only this module's known RNA footprint before a fresh register."""
    if hasattr(bpy.types.Scene, "dsg_cbct_dental"):
        try:
            del bpy.types.Scene.dsg_cbct_dental
        except Exception as exc:
            raise RuntimeError(f"No se pudo liberar Scene.dsg_cbct_dental: {exc}") from exc
    for cls in reversed(CLASSES):
        registered = getattr(bpy.types, cls.__name__, None)
        target = registered if registered is not None else cls
        try:
            bpy.utils.unregister_class(target)
        except RuntimeError:
            # Expected when neither the current nor a stale class is registered.
            pass




def migrate_existing_asset_metadata() -> int:
    """One-time compatible stamping for teeth saved by pre-v9 DSG scenes."""
    migrated = 0
    for obj in list(bpy.data.objects):
        if getattr(obj, "type", "") == "MESH" and (
            obj.name.startswith(TOOTH_OBJECT_PREFIX) or bool(obj.get("DSG_tooth_instance", False))
        ):
            source = str(obj.get("DSG_source", "CBCT_TOTALSEGMENTATOR") or "CBCT_TOTALSEGMENTATOR").upper()
            if source not in dental_assets.source_names():
                source = "USER"
            if dental_asset_blender.migrate_legacy_tooth_object(obj, source=source):
                migrated += 1
            continue
        if getattr(obj, "type", "") == "FONT" and obj.name.startswith(LABEL_OBJECT_PREFIX):
            try:
                fdi = int(obj.get("DSG_fdi_number", 0) or 0)
            except Exception:
                fdi = 0
            if not dental_assets.valid_fdi(fdi, include_primary=True):
                continue
            try:
                dental_asset_blender.stamp_object(
                    obj, fdi=fdi, role="FDI_LABEL", source="CBCT_TOTALSEGMENTATOR",
                    coordinate_space="CBCT_DSG_ROOT", rename=False,
                )
                migrated += 1
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
    return migrated


def register():
    global _SCENE_PROPERTY_OWNED
    if _REGISTERED_CLASSES:
        return
    _cleanup_stale_registration()
    try:
        for cls in CLASSES:
            bpy.utils.register_class(cls)
            _REGISTERED_CLASSES.append(cls)
        bpy.types.Scene.dsg_cbct_dental = PointerProperty(type=DSGCBCTDentalProperties)
        _SCENE_PROPERTY_OWNED = True
        # IMPORTANT: do not touch bpy.data here. Blender/Mixar may still expose
        # _RestrictData while an add-on is being enabled. Existing-object
        # migration is performed by deferred_post_register() after normal
        # scene data access is available.
    except Exception:
        if _SCENE_PROPERTY_OWNED and hasattr(bpy.types.Scene, "dsg_cbct_dental"):
            try:
                del bpy.types.Scene.dsg_cbct_dental
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
        _SCENE_PROPERTY_OWNED = False
        for cls in reversed(_REGISTERED_CLASSES):
            try:
                bpy.utils.unregister_class(cls)
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
        _REGISTERED_CLASSES.clear()
        raise


def deferred_post_register() -> bool:
    """Run data-sensitive CBCT metadata migration after _RestrictData is gone."""
    global _DEFERRED_METADATA_MIGRATED
    if _DEFERRED_METADATA_MIGRATED:
        return True
    try:
        objects = getattr(bpy.data, "objects", None)
        scenes = getattr(bpy.data, "scenes", None)
    except Exception:
        return False
    if objects is None or scenes is None:
        return False
    migrate_existing_asset_metadata()
    _DEFERRED_METADATA_MIGRATED = True
    return True


def unregister():
    global _SCENE_PROPERTY_OWNED, _DEFERRED_METADATA_MIGRATED
    _DEFERRED_METADATA_MIGRATED = False
    if _SCENE_PROPERTY_OWNED and hasattr(bpy.types.Scene, "dsg_cbct_dental"):
        try:
            del bpy.types.Scene.dsg_cbct_dental
        finally:
            _SCENE_PROPERTY_OWNED = False
    for cls in reversed(_REGISTERED_CLASSES):
        try:
            bpy.utils.unregister_class(cls)
        except RuntimeError:
            pass
    _REGISTERED_CLASSES.clear()
