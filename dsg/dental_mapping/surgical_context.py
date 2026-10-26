"""Thin orchestration over existing DSG CBCT + implant + mesh engines.

No new segmentation engine lives here.  The module only connects:
- guide_module implant geometry,
- dicom_module's existing calibrated volume sampler,
- dental-mapping FDI/ToothFrame semantics,
- Blender BVH queries for safety distance to segmented neighboring teeth.
"""
from __future__ import annotations

import logging as _dsg_logging
_DSG_LOG = _dsg_logging.getLogger(__name__)

import math
import json
from typing import Any

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from .. import dental_assets, dental_asset_blender
from . import mesh_distance_core


def _modules():
    from .. import dicom_module, guide_module
    return dicom_module, guide_module


def _resolve_implant(implant_name: str | None = None):
    _dicom, guide = _modules()
    if implant_name:
        obj = bpy.data.objects.get(str(implant_name))
        if not guide.is_valid_implant_obj(obj):
            raise ValueError(f"Implante DSG no válido: {implant_name}")
        return obj
    props = getattr(bpy.context.scene, "dsg_props", None)
    active = getattr(getattr(bpy.context, "view_layer", None), "objects", None)
    active = getattr(active, "active", None) if active is not None else None
    if guide.is_valid_implant_obj(active):
        return active
    if props is not None and guide.is_valid_implant_obj(getattr(props, "implant_obj", None)):
        return props.implant_obj
    implants = guide.get_all_implant_objects(props)
    if len(implants) == 1:
        return implants[0]
    if not implants:
        raise ValueError("No hay implantes DSG en escena")
    raise ValueError("Hay varios implantes: especifica implant_name")


def _patient_tooth(fdi: int):
    obj = dental_asset_blender.find_one(fdi, "TOOTH")
    if obj is not None:
        return obj
    canonical = bpy.data.objects.get(dental_assets.object_name(fdi, "TOOTH"))
    return canonical


def _tooth_frame(fdi: int):
    return dental_asset_blender.find_one(fdi, "TOOTH_FRAME")


def _implant_geometry(implant):
    _dicom, guide = _modules()
    props = getattr(bpy.context.scene, "dsg_props", None)
    center = guide.get_implant_center_world(props, implant)
    axis = guide.get_implant_axis_world(props, implant).normalized()
    length = float(guide.get_implant_length_world(props, implant))
    diameter = float(guide.get_implant_nominal_diameter_world(props, implant))
    return center, axis, length, diameter


def _orthogonal_basis(axis: Vector):
    axis = axis.normalized()
    seed = Vector((1.0, 0.0, 0.0)) if abs(axis.x) < 0.85 else Vector((0.0, 1.0, 0.0))
    u = axis.cross(seed)
    if u.length < 1e-8:
        seed = Vector((0.0, 0.0, 1.0))
        u = axis.cross(seed)
    u.normalize()
    v = axis.cross(u).normalized()
    return u, v


def _stats(values):
    import numpy as np
    arr = np.asarray(values, dtype=float)
    if arr.size == 0:
        return {"count": 0, "mean": None, "median": None, "p10": None, "p90": None, "min": None, "max": None}
    return {
        "count": int(arr.size),
        "mean": float(arr.mean()), "median": float(np.median(arr)),
        "p10": float(np.percentile(arr, 10)), "p90": float(np.percentile(arr, 90)),
        "min": float(arr.min()), "max": float(arr.max()),
    }


def analyze_implant_bone_support(
    *,
    fdi: int,
    implant_name: str | None = None,
    radial_offset_mm: float = 0.75,
    axial_samples: int = 18,
    angular_samples: int = 16,
    include_samples: bool = False,
) -> dict[str, Any]:
    """Sample the already-loaded CBCT around the implant surface.

    The score is deliberately relative within the current CBCT acquisition and
    must not be interpreted as HU or an absolute bone-density diagnosis.
    """
    import numpy as np
    fdi = dental_assets.normalize_fdi(fdi, include_primary=False)
    dicom, _guide = _modules()
    implant = _resolve_implant(implant_name)
    center, axis, length, diameter = _implant_geometry(implant)
    radial_offset_mm = max(0.0, float(radial_offset_mm))
    axial_samples = max(6, min(96, int(axial_samples)))
    angular_samples = max(8, min(96, int(angular_samples)))
    radius = 0.5 * diameter + radial_offset_mm
    u, v = _orthogonal_basis(axis)

    positions = []
    records = []
    for iz in range(axial_samples):
        t = (iz + 0.5) / axial_samples
        axial = (t - 0.5) * length
        axial_zone = "APICAL" if t < 1/3 else ("MIDDLE" if t < 2/3 else "CERVICAL")
        ring_center = center + axis * axial
        for ia in range(angular_samples):
            a = 2.0 * math.pi * ia / angular_samples
            radial = math.cos(a) * u + math.sin(a) * v
            p = ring_center + radius * radial
            positions.append((p.x, p.y, p.z))
            records.append({"axial_zone": axial_zone, "radial": radial, "xyz": p})

    raw, valid = dicom.sample_cbct_density_world(positions, normalized=False, return_valid=True)
    info = dicom.get_cbct_density_info()
    low = float(info.get("auto_low", info.get("density_min", 0.0)))
    high = float(info.get("auto_high", info.get("density_max", 1.0)))
    if high <= low + 1e-6:
        low = float(info.get("density_min", 0.0)); high = float(info.get("density_max", 1.0))
    norm = np.clip((raw - low) / max(high - low, 1e-6), 0.0, 1.0)
    frame = _tooth_frame(fdi)
    x_sem = None; y_sem = None
    if frame is not None:
        m = frame.matrix_world.to_3x3()
        x_sem = Vector((m[0][0], m[1][0], m[2][0])).normalized()  # +X MESIAL
        y_sem = Vector((m[0][1], m[1][1], m[2][1])).normalized()  # +Y FACIAL

    by_axial = {k: [] for k in ("CERVICAL", "MIDDLE", "APICAL")}
    by_side = {k: [] for k in ("MESIAL", "DISTAL", "FACIAL", "LINGUAL_PALATAL")}
    samples = []
    valid_count = 0
    for rec, rv, nv, is_valid in zip(records, raw, norm, valid):
        if not bool(is_valid):
            if include_samples:
                samples.append({
                    "xyz": [float(c) for c in rec["xyz"]], "raw_gray": None,
                    "relative_density": None, "axial_zone": rec["axial_zone"],
                    "side": None, "valid_cbct_sample": False,
                })
            continue
        valid_count += 1
        nv = float(nv); rv = float(rv)
        by_axial[rec["axial_zone"]].append(nv)
        side = None
        radial = rec["radial"]
        if x_sem is not None and y_sem is not None:
            dx, dy = radial.dot(x_sem), radial.dot(y_sem)
            if abs(dx) >= abs(dy):
                side = "MESIAL" if dx >= 0 else "DISTAL"
            else:
                side = "FACIAL" if dy >= 0 else "LINGUAL_PALATAL"
            by_side[side].append(nv)
        samples.append({
            "xyz": [float(c) for c in rec["xyz"]], "raw_gray": rv,
            "relative_density": nv, "axial_zone": rec["axial_zone"], "side": side,
            "valid_cbct_sample": True,
        })
    valid_norm = [float(nv) for nv, ok in zip(norm, valid) if bool(ok)]
    overall = _stats(valid_norm)
    result = {
        "schema": "dsg.implant_bone_support.v1",
        "fdi": fdi, "implant": implant.name,
        "interpretation": "RELATIVE_CBCT_GRAY_NOT_HU",
        "sampling": {
            "radial_offset_mm": radial_offset_mm, "radius_from_implant_axis_mm": radius,
            "axial_samples": axial_samples, "angular_samples": angular_samples,
            "requested_sample_count": len(records),
            "valid_sample_count": int(valid_count),
            "valid_fraction": float(valid_count / max(1, len(records))),
        },
        "cbct": info,
        "overall": overall,
        "by_axial_zone": {k: _stats(vs) for k, vs in by_axial.items()},
        "by_semantic_side": {k: _stats(vs) for k, vs in by_side.items()},
        "bone_support_score": overall["mean"],
        "clinical_warning": "Relative CBCT gray support metric; not absolute HU and not a substitute for clinical assessment.",
    }
    if include_samples:
        result["samples"] = samples
    implant["DSG_bone_support_score"] = float(overall["mean"] or 0.0)
    implant["DSG_bone_support_schema"] = result["schema"]
    return result




_HEATMAP_STOPS = (
    (0.00, (0.02, 0.05, 0.60, 1.0)),  # deep blue
    (0.25, (0.00, 0.55, 0.85, 1.0)),  # cyan
    (0.50, (0.15, 0.75, 0.15, 1.0)),  # green
    (0.75, (0.95, 0.85, 0.10, 1.0)),  # yellow
    (1.00, (0.85, 0.05, 0.05, 1.0)),  # red
)


def _heatmap_rgba(value: float):
    """Auditable cold→hot ramp: blue→cyan→green→yellow→red."""
    t = max(0.0, min(1.0, float(value)))
    for (p0, c0), (p1, c1) in zip(_HEATMAP_STOPS[:-1], _HEATMAP_STOPS[1:]):
        if t <= p1:
            u = 0.0 if p1 <= p0 else (t - p0) / (p1 - p0)
            return tuple(float(a + (b - a) * u) for a, b in zip(c0, c1))
    return _HEATMAP_STOPS[-1][1]


def _surface_normal_probe_points(implant, offsets_mm):
    """Return flattened surface-normal probe positions and vertex count.

    Uses the inverse-transpose normal transform, so visualization remains
    geometrically correct even if an implant object has non-uniform scale.
    The base mesh is intentionally used because the heatmap attributes are
    written back to that same POINT domain.
    """
    mesh = implant.data
    normal_matrix = implant.matrix_world.to_3x3().inverted_safe().transposed()
    base_positions = []
    normals = []
    for vert in mesh.vertices:
        p = implant.matrix_world @ vert.co
        n = normal_matrix @ vert.normal
        if n.length <= 1e-12:
            n = Vector((0.0, 0.0, 1.0))
        else:
            n.normalize()
        base_positions.append(p)
        normals.append(n)
    points = []
    for offset in offsets_mm:
        off = float(offset)
        for p, n in zip(base_positions, normals):
            q = p + n * off
            points.append((float(q.x), float(q.y), float(q.z)))
    return points, len(base_positions)


def _axis_radial_probe_points(implant, radial_offset_mm: float):
    mesh = implant.data
    center, axis, _length, _diameter = _implant_geometry(implant)
    points = []
    for vert in mesh.vertices:
        p = implant.matrix_world @ vert.co
        delta = p - center
        radial = delta - axis * delta.dot(axis)
        if radial.length > 1e-8:
            p = p + radial.normalized() * float(radial_offset_mm)
        points.append((float(p.x), float(p.y), float(p.z)))
    return points, len(points)


def _sample_heatmap_values(dicom, implant, *, sampling_mode: str, radial_offset_mm: float, ring_offsets_mm):
    """Visualization sampler only; scoring remains axial×angular elsewhere."""
    mode = str(sampling_mode or "SURFACE_NORMAL_AVERAGE").upper()
    if mode == "AXIS_RADIAL":
        points, n = _axis_radial_probe_points(implant, radial_offset_mm)
        norm, valid = dicom.sample_cbct_density_world(points, normalized=True, return_valid=True)
        values = [float(v) if bool(ok) else 0.0 for v, ok in zip(norm, valid)]
        mask = [bool(ok) for ok in valid]
        return values, mask, {
            "mode": mode,
            "radial_offset_mm": float(radial_offset_mm),
            "ring_offsets_mm": [],
        }

    offsets = tuple(float(x) for x in (ring_offsets_mm or (0.25, 0.50, 1.00)) if float(x) >= 0.0)
    if not offsets:
        offsets = (max(0.0, float(radial_offset_mm)),)
    points, n = _surface_normal_probe_points(implant, offsets)
    norm, valid = dicom.sample_cbct_density_world(points, normalized=True, return_valid=True)

    # Points are grouped by offset, then vertex. Average only valid FOV samples.
    sums = [0.0] * n
    counts = [0] * n
    for ring_idx in range(len(offsets)):
        base = ring_idx * n
        for vertex_idx in range(n):
            idx = base + vertex_idx
            if bool(valid[idx]):
                sums[vertex_idx] += float(norm[idx])
                counts[vertex_idx] += 1
    values = [(sums[i] / counts[i]) if counts[i] else 0.0 for i in range(n)]
    mask = [count > 0 for count in counts]
    return values, mask, {
        "mode": "SURFACE_NORMAL_AVERAGE",
        "radial_offset_mm": None,
        "ring_offsets_mm": [float(x) for x in offsets],
    }


def apply_implant_bone_support_heatmap(
    *, fdi: int, implant_name: str | None = None, radial_offset_mm: float = 0.75,
    sampling_mode: str = "SURFACE_NORMAL_AVERAGE",
    ring_offsets_mm=(0.25, 0.50, 1.00),
    emission_strength: float = 0.25,
) -> dict[str, Any]:
    """Visualize existing DSG CBCT support values on the implant.

    This is deliberately *not* the clinical scoring sampler.  The MCP-facing
    BoneSupportScore continues to use topology-independent axial×angular
    sampling.  This function only gives the clinician a richer surface view.
    """
    fdi = dental_assets.normalize_fdi(fdi, include_primary=False)
    dicom, _guide = _modules()
    implant = _resolve_implant(implant_name)
    if implant.type != "MESH" or implant.data is None:
        raise ValueError("El implante debe ser una malla")
    mesh = implant.data

    values, valid_mask, sampling = _sample_heatmap_values(
        dicom, implant,
        sampling_mode=sampling_mode,
        radial_offset_mm=max(0.0, float(radial_offset_mm)),
        ring_offsets_mm=ring_offsets_mm,
    )

    float_attr = mesh.attributes.get("DSG_BONE_SUPPORT_RELATIVE")
    if float_attr is None or float_attr.domain != 'POINT' or float_attr.data_type != 'FLOAT':
        if float_attr is not None:
            mesh.attributes.remove(float_attr)
        float_attr = mesh.attributes.new("DSG_BONE_SUPPORT_RELATIVE", type='FLOAT', domain='POINT')

    color_attr = mesh.color_attributes.get("DSG_BONE_SUPPORT_COLOR")
    if color_attr is None or color_attr.domain != 'POINT':
        if color_attr is not None:
            mesh.color_attributes.remove(color_attr)
        color_attr = mesh.color_attributes.new(
            name="DSG_BONE_SUPPORT_COLOR", type='FLOAT_COLOR', domain='POINT'
        )

    valid_values = []
    for i, (value, ok) in enumerate(zip(values, valid_mask)):
        value = float(value) if bool(ok) else 0.0
        float_attr.data[i].value = value
        color_attr.data[i].color = _heatmap_rgba(value) if bool(ok) else (0.12, 0.12, 0.12, 1.0)
        if bool(ok):
            valid_values.append(value)
    try:
        mesh.color_attributes.active_color = color_attr
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)

    material_name = "DSG_BoneSupport_Heatmap"
    mat = bpy.data.materials.get(material_name) or bpy.data.materials.new(material_name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    out = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    try:
        vcol = nodes.new("ShaderNodeVertexColor")
        vcol.layer_name = "DSG_BONE_SUPPORT_COLOR"
        links.new(vcol.outputs.get("Color"), bsdf.inputs.get("Base Color"))
        color_output = vcol.outputs.get("Color")
    except Exception:
        attr = nodes.new("ShaderNodeAttribute")
        attr.attribute_name = "DSG_BONE_SUPPORT_COLOR"
        links.new(attr.outputs.get("Color"), bsdf.inputs.get("Base Color"))
        color_output = attr.outputs.get("Color")
    if color_output is not None and "Emission Color" in bsdf.inputs:
        links.new(color_output, bsdf.inputs["Emission Color"])
        bsdf.inputs["Emission Strength"].default_value = max(0.0, float(emission_strength))
    links.new(bsdf.outputs.get("BSDF"), out.inputs.get("Surface"))
    try:
        bsdf.inputs["Roughness"].default_value = 0.35
        bsdf.inputs["Metallic"].default_value = 0.0
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)

    if "DSG_heatmap_previous_materials_json" not in implant:
        implant["DSG_heatmap_previous_materials_json"] = json.dumps(
            [slot.material.name if slot.material else "" for slot in implant.material_slots]
        )
    mesh.materials.clear()
    mesh.materials.append(mat)
    implant["DSG_heatmap_active"] = True
    implant["DSG_heatmap_sampling_mode"] = sampling["mode"]
    implant["DSG_heatmap_valid_fraction"] = float(len(valid_values) / max(1, len(mesh.vertices)))
    implant["DSG_heatmap_palette"] = "BLUE_CYAN_GREEN_YELLOW_RED"

    stats = {
        "min": float(min(valid_values)) if valid_values else None,
        "mean": float(sum(valid_values) / len(valid_values)) if valid_values else None,
        "max": float(max(valid_values)) if valid_values else None,
    }
    return {
        "schema": "dsg.implant_bone_support_heatmap.v2",
        "fdi": fdi,
        "implant": implant.name,
        "attribute": "DSG_BONE_SUPPORT_RELATIVE",
        "color_attribute": "DSG_BONE_SUPPORT_COLOR",
        "material": mat.name,
        "sampling": sampling,
        "palette": "BLUE_CYAN_GREEN_YELLOW_RED",
        "valid_fraction": implant["DSG_heatmap_valid_fraction"],
        "surface_stats": stats,
        "interpretation": "RELATIVE_CBCT_GRAY_NOT_HU",
        "scoring_note": "Visualization sampler only; BoneSupportScore uses topology-independent axial-angular sampling.",
    }

def clear_implant_bone_support_heatmap(*, implant_name: str | None = None) -> dict[str, Any]:
    implant = _resolve_implant(implant_name)
    mesh = implant.data if implant.type == "MESH" else None
    restored = []
    if mesh is not None:
        previous_raw = str(implant.get("DSG_heatmap_previous_materials_json", "[]"))
        try:
            previous = json.loads(previous_raw)
        except Exception:
            previous = []
        mesh.materials.clear()
        for name in previous:
            mat = bpy.data.materials.get(str(name)) if name else None
            if mat is not None:
                mesh.materials.append(mat); restored.append(mat.name)
    for key in ("DSG_heatmap_active", "DSG_heatmap_radial_offset_mm", "DSG_heatmap_valid_fraction", "DSG_heatmap_previous_materials_json"):
        try:
            del implant[key]
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    return {"schema": "dsg.implant_bone_support_heatmap_clear.v1", "implant": implant.name, "restored_materials": restored}


def _world_bvh_and_vertices(obj):
    if obj is None or obj.type != "MESH":
        return None, []
    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated = obj.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    try:
        verts_world = [evaluated.matrix_world @ v.co for v in mesh.vertices]
        polygons = [tuple(int(i) for i in p.vertices) for p in mesh.polygons]
        tree = BVHTree.FromPolygons(verts_world, polygons, all_triangles=False)
        return tree, verts_world
    finally:
        evaluated.to_mesh_clear()


def _world_triangles(obj):
    """Return evaluated world-space triangles as an ``(N,3,3)`` NumPy array."""
    import numpy as np
    if obj is None or obj.type != "MESH":
        return np.empty((0, 3, 3), dtype=np.float64)
    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated = obj.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    try:
        mesh.calc_loop_triangles()
        if not mesh.loop_triangles or not mesh.vertices:
            return np.empty((0, 3, 3), dtype=np.float64)
        coords = np.empty(len(mesh.vertices) * 3, dtype=np.float64)
        mesh.vertices.foreach_get("co", coords)
        coords = coords.reshape((-1, 3))
        matrix = np.asarray(evaluated.matrix_world, dtype=np.float64)
        hom = np.concatenate((coords, np.ones((len(coords), 1), dtype=np.float64)), axis=1)
        world = hom @ matrix.T
        world = world[:, :3]
        indices = np.empty(len(mesh.loop_triangles) * 3, dtype=np.int32)
        try:
            mesh.loop_triangles.foreach_get("vertices", indices)
            indices = indices.reshape((-1, 3))
        except Exception:
            indices = np.asarray([tuple(int(i) for i in tri.vertices) for tri in mesh.loop_triangles], dtype=np.int32)
        return world[indices]
    finally:
        evaluated.to_mesh_clear()


def _sample_vectors(values, max_count: int):
    if len(values) <= max_count:
        return values
    stride = max(1, int(math.ceil(len(values) / max_count)))
    return values[::stride]


def _object_surface_distance(source, target, *, max_vertices_per_side: int = 6000):
    """World-space mesh separation with intersection detection.

    For non-intersecting surfaces the reported minimum is the best of
    bidirectional vertex→surface queries. It is explicitly labelled as an
    approximation rather than an exact clinical clearance theorem.
    """
    if source is None or target is None or source.type != "MESH" or target.type != "MESH":
        return None
    source_tree, source_vertices = _world_bvh_and_vertices(source)
    target_tree, target_vertices = _world_bvh_and_vertices(target)
    if source_tree is None or target_tree is None:
        return None

    try:
        overlaps = source_tree.overlap(target_tree)
    except Exception:
        overlaps = []
    if overlaps:
        return {
            "distance_mm": 0.0,
            "intersection": True,
            "overlap_pair_count": int(len(overlaps)),
            "method": "WORLD_BVH_INTERSECTION",
            "distance_semantics": "INTERSECTING_SURFACES",
        }

    best = None; best_src = None; best_dst = None; best_direction = None
    for p in _sample_vectors(source_vertices, max_vertices_per_side):
        hit = target_tree.find_nearest(p)
        if hit is None or hit[0] is None:
            continue
        d = float(hit[3])
        if best is None or d < best:
            best, best_src, best_dst, best_direction = d, p, hit[0], "IMPLANT_TO_TOOTH"
    for p in _sample_vectors(target_vertices, max_vertices_per_side):
        hit = source_tree.find_nearest(p)
        if hit is None or hit[0] is None:
            continue
        d = float(hit[3])
        if best is None or d < best:
            best, best_src, best_dst, best_direction = d, hit[0], p, "TOOTH_TO_IMPLANT"
    if best is None:
        return None
    return {
        "distance_mm": float(best),
        "intersection": False,
        "implant_point_world": [float(v) for v in best_src],
        "tooth_point_world": [float(v) for v in best_dst],
        "method": "WORLD_BVH_BIDIRECTIONAL_VERTEX_SURFACE",
        "sample_direction": best_direction,
        "distance_semantics": "APPROXIMATE_MINIMUM_NONINTERSECTING_SURFACE_DISTANCE",
        "safety_note": "Use explicit clinician/user clearance constraints; this metric does not invent a safe threshold.",
    }


def _object_surface_distance_full_vertex(source, target):
    """Bidirectional full-vertex BVH recheck used as an upper bound for exact mode."""
    result = _object_surface_distance(source, target, max_vertices_per_side=10**9)
    if result and not result.get("intersection"):
        result = dict(result)
        result["method"] = "WORLD_BVH_FULL_VERTEX_BIDIRECTIONAL"
        result["distance_semantics"] = "FULL_VERTEX_BIDIRECTIONAL_UPPER_BOUND"
    return result


def _object_surface_distance_exact(source, target, *, max_candidate_pairs: int = 1_500_000):
    """Triangle-surface confirmation verifier.  Fails closed if broad phase is incomplete."""
    preliminary = _object_surface_distance_full_vertex(source, target)
    if preliminary is None:
        return None
    if preliminary.get("intersection"):
        out = dict(preliminary)
        out.update({
            "method": "WORLD_BVH_INTERSECTION_EXACT_ZERO",
            "distance_semantics": "EXACT_INTERSECTING_SURFACES",
            "exact_complete": True,
            "candidate_pairs": 0,
        })
        return out
    upper = float(preliminary.get("distance_mm", math.inf))
    source_tris = _world_triangles(source)
    target_tris = _world_triangles(target)
    if len(source_tris) == 0 or len(target_tris) == 0 or not math.isfinite(upper):
        return {
            **preliminary,
            "method": "EXACT_TRIANGLE_SURFACE_UNAVAILABLE",
            "distance_semantics": "UNVERIFIED",
            "exact_complete": False,
            "error": "Evaluated triangle mesh unavailable",
        }
    exact = mesh_distance_core.exact_mesh_surface_distance(
        source_tris, target_tris, upper_bound_mm=upper,
        max_candidate_pairs=max_candidate_pairs,
    )
    out = {
        "distance_mm": float(exact.distance),
        "intersection": bool(exact.distance <= 1.0e-10),
        "implant_point_world": [float(v) for v in exact.source_point],
        "tooth_point_world": [float(v) for v in exact.target_point],
        "method": "WORLD_TRIANGLE_TRIANGLE_EXACT_AABB_SWEEP",
        "distance_semantics": "EXACT_MESH_SURFACE_DISTANCE" if exact.complete else "INCOMPLETE_EXACT_RECHECK",
        "exact_complete": bool(exact.complete),
        "candidate_pairs": int(exact.candidate_pairs),
        "source_triangle_index": int(exact.source_triangle),
        "target_triangle_index": int(exact.target_triangle),
        "preliminary_upper_bound_mm": upper,
        "safety_note": "Exact mode is intended for confirmation gates; if exact_complete is false the gate must fail closed.",
    }
    return out


def analyze_implant_neighbor_clearance(*, fdi: int, implant_name: str | None = None,
                                      required_clearance_mm: float | None = None,
                                      verification_mode: str = "FAST") -> dict[str, Any]:
    fdi = dental_assets.normalize_fdi(fdi, include_primary=False)
    implant = _resolve_implant(implant_name)
    mode = str(verification_mode or "FAST").upper()
    if mode not in {"FAST", "FULL_VERTEX", "EXACT"}:
        raise ValueError("verification_mode must be FAST, FULL_VERTEX or EXACT")
    neighbors = dental_assets.neighbor_fdis(fdi)
    out = {}
    unverified = []
    for side, neighbor_fdi in neighbors.items():
        tooth = _patient_tooth(neighbor_fdi) if neighbor_fdi else None
        if tooth is None and neighbor_fdi:
            unverified.append({"side": side, "fdi": neighbor_fdi, "reason": "EXPECTED_SEGMENTED_NEIGHBOR_MISSING"})
            result = None
        elif tooth is None:
            result = None
        elif mode == "EXACT":
            result = _object_surface_distance_exact(implant, tooth)
        elif mode == "FULL_VERTEX":
            result = _object_surface_distance_full_vertex(implant, tooth)
        else:
            result = _object_surface_distance(implant, tooth)
        if mode == "EXACT" and result is not None and not bool(result.get("exact_complete", False)):
            unverified.append({"side": side, "fdi": neighbor_fdi, "reason": "EXACT_RECHECK_INCOMPLETE"})
        out[side] = {
            "fdi": neighbor_fdi, "object": tooth.name if tooth else None,
            "clearance": result,
        }
    distances = [v["clearance"]["distance_mm"] for v in out.values() if v.get("clearance")]
    minimum = min(distances) if distances else None
    required = None if required_clearance_mm is None else max(0.0, float(required_clearance_mm))
    verified = not unverified and minimum is not None and (mode != "EXACT" or all(
        (not v.get("clearance")) or bool(v["clearance"].get("exact_complete", False))
        for v in out.values()))
    # Only the exact verifier may be used as a hard confirmation gate.  No 0.02 mm
    # permissive tolerance is applied; only tiny floating-point epsilon remains.
    if minimum is None or required is None:
        safe = None
    elif mode == "EXACT" and not verified:
        safe = None
    else:
        safe = bool(minimum + 1.0e-7 >= required)
    return {
        "schema": "dsg.implant_neighbor_clearance.v3",
        "fdi": fdi, "implant": implant.name, "neighbors": out,
        "minimum_neighbor_clearance_mm": minimum,
        "required_clearance_mm": required,
        "deficit_mm": (max(0.0, required - minimum) if minimum is not None and required is not None else None),
        "safe": safe,
        "verification_mode": mode,
        "hard_gate_eligible": bool(mode == "EXACT" and verified),
        "unverified_neighbors": unverified,
        "method": ("EXACT_TRIANGLE_SURFACE" if mode == "EXACT" else
                   "FULL_VERTEX_BVH_RECHECK" if mode == "FULL_VERTEX" else
                   "FAST_BVH_APPROXIMATION"),
        "measurement_space": "WORLD",
        "threshold_policy": "EXPLICIT_CONTEXT_VALUE_NOT_HARDCODED_IN_MEASUREMENT_ENGINE",
        "evidence_rule_ids": ["IMPLANT_TOOTH_CLEARANCE"],
    }


def analyze_interdental_space(*, fdi: int, implant_name: str | None = None) -> dict[str, Any]:
    """Context metric between the two segmented teeth adjacent to a missing site.

    The global tooth-to-tooth minimum is deliberately NOT used alone to select
    implant diameter, because roots can converge/diverge away from the planned
    implant trajectory. If an implant is supplied, its trajectory-specific
    neighbor clearances are included as the decision metric.
    """
    fdi = dental_assets.normalize_fdi(fdi, include_primary=False)
    neighbors = dental_assets.neighbor_fdis(fdi)
    mesial = _patient_tooth(neighbors.get("mesial")) if neighbors.get("mesial") else None
    distal = _patient_tooth(neighbors.get("distal")) if neighbors.get("distal") else None
    global_distance = _object_surface_distance(mesial, distal) if mesial and distal else None
    if global_distance:
        global_distance = {
            "distance_mm": global_distance.get("distance_mm"),
            "intersection": global_distance.get("intersection", False),
            "method": global_distance.get("method"),
            "distance_semantics": "GLOBAL_MINIMUM_BETWEEN_SEGMENTED_NEIGHBOR_TEETH",
        }
    trajectory = None
    if implant_name is not None:
        trajectory = analyze_implant_neighbor_clearance(
            fdi=fdi, implant_name=implant_name, required_clearance_mm=None)
    return {
        "schema": "dsg.interdental_space.v1",
        "fdi": fdi,
        "neighbors": {
            "mesial": {"fdi": neighbors.get("mesial"), "object": mesial.name if mesial else None},
            "distal": {"fdi": neighbors.get("distal"), "object": distal.name if distal else None},
        },
        "global_tooth_to_tooth_minimum": global_distance,
        "trajectory_specific": trajectory,
        "decision_note": "Use trajectory-specific implant-to-tooth clearance for diameter selection; the global tooth-to-tooth minimum is context only.",
        "evidence_rule_ids": ["IMPLANT_TOOTH_CLEARANCE", "IMPLANT_DIAMETER_SELECTION"],
    }


def _virtual_implant_world_geometry(implant, candidate_diameter_mm: float):
    """Evaluated implant geometry with local radial XY scaled to a trial diameter.

    Returns world-space vertices plus *triangulated* faces so the same virtual
    candidate can be used by the fast BVH path and the exact triangle-distance
    verifier without creating temporary Blender objects.
    """
    _dicom, guide = _modules()
    props = getattr(bpy.context.scene, "dsg_props", None)
    current_diameter = max(0.01, float(guide.get_implant_nominal_diameter_world(props, implant)))
    target = max(0.01, float(candidate_diameter_mm))
    ratio = target / current_diameter
    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated = implant.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    try:
        try:
            mesh.calc_loop_triangles()
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        matrix = evaluated.matrix_world
        verts = [
            matrix @ Vector((float(v.co.x) * ratio, float(v.co.y) * ratio, float(v.co.z)))
            for v in mesh.vertices
        ]
        faces = [tuple(int(i) for i in tri.vertices) for tri in mesh.loop_triangles]
        return verts, faces, current_diameter
    finally:
        evaluated.to_mesh_clear()


def _world_geometry_to_object_surface_distance(source_vertices, source_faces, target,
                                                *, max_vertices_per_side: int = 6000,
                                                verification_mode: str = "FAST",
                                                max_candidate_pairs: int = 1_500_000):
    """Distance from virtual triangulated geometry to a real Blender mesh.

    FAST and FULL_VERTEX are ranking/precheck modes.  EXACT uses the full-vertex
    result only as a valid observed upper bound and then evaluates every
    triangle pair whose AABBs could improve that bound.  If the exact candidate
    budget is exceeded, the result is explicitly incomplete and must not be
    treated as a hard safety pass.
    """
    mode = str(verification_mode or "FAST").upper()
    if mode not in {"FAST", "FULL_VERTEX", "EXACT"}:
        raise ValueError("verification_mode must be FAST, FULL_VERTEX or EXACT")
    if target is None or target.type != "MESH" or not source_vertices or not source_faces:
        return None
    source_tree = BVHTree.FromPolygons(source_vertices, source_faces, all_triangles=True)
    target_tree, target_vertices = _world_bvh_and_vertices(target)
    if source_tree is None or target_tree is None:
        return None
    try:
        overlaps = source_tree.overlap(target_tree)
    except Exception:
        overlaps = []
    if overlaps:
        return {
            "distance_mm": 0.0,
            "intersection": True,
            "method": "VIRTUAL_IMPLANT_WORLD_BVH_INTERSECTION",
            "distance_semantics": "EXACT_INTERSECTING_SURFACES" if mode == "EXACT" else "INTERSECTING_SURFACES",
            "exact_complete": True if mode == "EXACT" else None,
        }

    limit = 10**9 if mode in {"FULL_VERTEX", "EXACT"} else max_vertices_per_side
    best = None
    for point in _sample_vectors(source_vertices, limit):
        hit = target_tree.find_nearest(point)
        if hit is not None and hit[0] is not None:
            distance = float(hit[3])
            best = distance if best is None or distance < best else best
    for point in _sample_vectors(target_vertices, limit):
        hit = source_tree.find_nearest(point)
        if hit is not None and hit[0] is not None:
            distance = float(hit[3])
            best = distance if best is None or distance < best else best
    if best is None:
        return None

    if mode != "EXACT":
        return {
            "distance_mm": float(best),
            "intersection": False,
            "method": ("VIRTUAL_IMPLANT_WORLD_BVH_FULL_VERTEX" if mode == "FULL_VERTEX" else
                       "VIRTUAL_IMPLANT_WORLD_BVH_BIDIRECTIONAL_DISTANCE"),
            "distance_semantics": ("FULL_VERTEX_BIDIRECTIONAL_UPPER_BOUND" if mode == "FULL_VERTEX" else
                                   "APPROXIMATE_MINIMUM_NONINTERSECTING_SURFACE_DISTANCE"),
        }

    source_triangles = np.asarray(
        [[[float(source_vertices[i][0]), float(source_vertices[i][1]), float(source_vertices[i][2])]
          for i in face] for face in source_faces], dtype=np.float64)
    target_triangles = _world_triangles(target)
    if len(source_triangles) == 0 or len(target_triangles) == 0:
        return {
            "distance_mm": float(best), "intersection": False,
            "method": "VIRTUAL_EXACT_TRIANGLE_SURFACE_UNAVAILABLE",
            "distance_semantics": "UNVERIFIED", "exact_complete": False,
        }
    exact = mesh_distance_core.exact_mesh_surface_distance(
        source_triangles, target_triangles, upper_bound_mm=float(best),
        max_candidate_pairs=max_candidate_pairs,
    )
    return {
        "distance_mm": float(exact.distance),
        "intersection": bool(exact.distance <= 1.0e-10),
        "method": "VIRTUAL_IMPLANT_WORLD_TRIANGLE_TRIANGLE_EXACT_AABB_SWEEP",
        "distance_semantics": "EXACT_MESH_SURFACE_DISTANCE" if exact.complete else "INCOMPLETE_EXACT_RECHECK",
        "exact_complete": bool(exact.complete),
        "candidate_pairs": int(exact.candidate_pairs),
        "source_triangle_index": int(exact.source_triangle),
        "target_triangle_index": int(exact.target_triangle),
        "preliminary_upper_bound_mm": float(best),
    }


def analyze_implant_diameter_options(*, fdi: int, implant_name: str | None = None,
                                     diameters_mm=None, clearance_mm: float = 1.5,
                                     verification_mode: str = "FAST") -> dict[str, Any]:
    """Evaluate real catalog diameters on the current implant trajectory.

    No diameter is invented or automatically recommended. MCP/user supplies the
    catalog values; DSG measures each virtual radial variant against actual
    segmented neighboring teeth. FAST is intended for ranking. EXACT is slower
    and may be used to verify a chosen candidate; an incomplete exact recheck
    yields ``safe=None`` rather than a false pass.
    """
    fdi = dental_assets.normalize_fdi(fdi, include_primary=False)
    implant = _resolve_implant(implant_name)
    required = max(0.0, float(clearance_mm))
    mode = str(verification_mode or "FAST").upper()
    if mode not in {"FAST", "FULL_VERTEX", "EXACT"}:
        raise ValueError("verification_mode must be FAST, FULL_VERTEX or EXACT")
    if diameters_mm is None:
        diameters = []
    else:
        diameters = sorted({round(float(v), 4) for v in diameters_mm if float(v) > 0.0})
    neighbors = dental_assets.neighbor_fdis(fdi)
    teeth = {side: (_patient_tooth(value) if value else None) for side, value in neighbors.items()}
    options = []
    for diameter in diameters:
        verts, faces, current_diameter = _virtual_implant_world_geometry(implant, diameter)
        side_results = {}
        distances = []
        unverified = []
        for side, tooth in teeth.items():
            neighbor_fdi = neighbors.get(side)
            if tooth is None and neighbor_fdi:
                result = None
                unverified.append({"side": side, "fdi": neighbor_fdi, "reason": "EXPECTED_SEGMENTED_NEIGHBOR_MISSING"})
            else:
                result = _world_geometry_to_object_surface_distance(
                    verts, faces, tooth, verification_mode=mode) if tooth else None
            if mode == "EXACT" and result is not None and not bool(result.get("exact_complete", False)):
                unverified.append({"side": side, "fdi": neighbor_fdi, "reason": "EXACT_RECHECK_INCOMPLETE"})
            side_results[side] = {
                "fdi": neighbor_fdi, "object": tooth.name if tooth else None, "clearance": result}
            if result is not None:
                distances.append(float(result["distance_mm"]))
        minimum = min(distances) if distances else None
        verified = not unverified and minimum is not None and (mode != "EXACT" or all(
            (not row.get("clearance")) or bool(row["clearance"].get("exact_complete", False))
            for row in side_results.values()))
        if minimum is None or (mode == "EXACT" and not verified):
            safe = None
        else:
            # No permissive clinical tolerance. Tiny epsilon is numerical only.
            safe = bool(minimum + 1.0e-7 >= required)
        options.append({
            "diameter_mm": float(diameter),
            "minimum_neighbor_clearance_mm": minimum,
            "required_clearance_mm": required,
            "safe": safe,
            "hard_gate_eligible": bool(mode == "EXACT" and verified),
            "unverified_neighbors": unverified,
            "deficit_mm": (max(0.0, required - minimum) if minimum is not None else None),
            "neighbors": side_results,
        })
    safe_diameters = [o["diameter_mm"] for o in options if o.get("safe") is True]
    _dicom, guide = _modules()
    props = getattr(bpy.context.scene, "dsg_props", None)
    current_diameter = float(guide.get_implant_nominal_diameter_world(props, implant))
    return {
        "schema": "dsg.implant_diameter_options.v2",
        "fdi": fdi, "implant": implant.name,
        "current_diameter_mm": current_diameter,
        "required_tooth_clearance_mm": required,
        "catalog_diameters_mm": diameters,
        "verification_mode": mode,
        "options": options,
        "widest_safe_catalog_diameter_mm": max(safe_diameters) if safe_diameters else None,
        "catalog_required": not bool(diameters),
        "method": ("VIRTUAL_RADIAL_VARIANTS_EXACT_TRIANGLE_SURFACE" if mode == "EXACT" else
                   "VIRTUAL_RADIAL_VARIANTS_FULL_VERTEX_BVH" if mode == "FULL_VERTEX" else
                   "VIRTUAL_RADIAL_VARIANTS_FAST_WORLD_BVH"),
        "selection_policy": "DO_NOT_MAXIMIZE_DIAMETER_AUTOMATICALLY; MCP must combine anatomy, prosthetics, bone, stability, evidence and rescue flexibility.",
        "rescue_reserve_note": "Preserving a larger future diameter is a user strategy, not a universal clinical rule.",
        "evidence_rule_ids": ["IMPLANT_TOOTH_CLEARANCE", "IMPLANT_DIAMETER_SELECTION", "NARROW_IMPLANT_USE"],
    }


def enrich_implant_context(base: dict[str, Any], *, fdi: int, implant_name: str | None = None) -> dict[str, Any]:
    result = dict(base)
    result["schema"] = "dsg.full_implant_planning_context.v1"
    result["gold_standard"] = None
    try:
        from . import library
        result["gold_standard"] = library.read_crown_gold_standard(fdi)
    except Exception as exc:
        result["gold_standard_error"] = str(exc)
    implant = None
    try:
        implant = _resolve_implant(implant_name)
    except Exception as exc:
        result["implant"] = None
        result["surgical_context_status"] = "IMPLANT_NOT_AVAILABLE"
        result["surgical_context_error"] = str(exc)
        return result
    result["implant"] = implant.name
    try:
        _dicom, guide = _modules()
        props = getattr(bpy.context.scene, "dsg_props", None)
        required = float(getattr(props, "implant_tooth_clearance", 1.5)) if props is not None else 1.5
        result["neighbor_clearance"] = analyze_implant_neighbor_clearance(
            fdi=fdi, implant_name=implant.name, required_clearance_mm=required)
        result["interdental_space"] = analyze_interdental_space(
            fdi=fdi, implant_name=implant.name)
    except Exception as exc:
        result["neighbor_clearance_error"] = str(exc)
    try:
        result["bone_support"] = analyze_implant_bone_support(fdi=fdi, implant_name=implant.name)
    except Exception as exc:
        result["bone_support_error"] = str(exc)
    result["surgical_context_status"] = "READY" if "bone_support" in result else "PARTIAL"
    return result


def prepare_implant_axis_from_prosthetic_context(*, fdi: int) -> dict[str, Any]:
    """Prepare DSG's existing one-shot implant axis from final prosthetic assets.

    No implant is created and no surgical geometry is committed.  The function
    only feeds DSG_ImplantAxis, the same advisory controller already consumed by
    guide_module when the clinician/MCP later creates an implant preview.
    """
    fdi = dental_assets.normalize_fdi(fdi, include_primary=False)
    _dicom, guide = _modules()
    axis_obj = dental_asset_blender.find_one(fdi, "PROSTHETIC_AXIS")
    center_obj = dental_asset_blender.find_one(fdi, "EMERGENCE_CENTER")
    crown = dental_asset_blender.find_one(fdi, "CROWN_TARGET")
    if axis_obj is None or center_obj is None or crown is None:
        raise dental_assets.DentalAssetContractError(
            f"FDI {fdi}: CROWN_TARGET + EMERGENCE_CENTER + PROSTHETIC_AXIS required"
        )
    z = axis_obj.matrix_world.to_3x3() @ Vector((0.0, 0.0, 1.0))
    if z.length <= 1e-8:
        raise RuntimeError("PROSTHETIC_AXIS is degenerate")
    # Gold Standard +Z is coronal/occlusal; the implant insertion axis consumed
    # by the guide is apical, therefore invert it.
    apical = (-z).normalized()
    origin = center_obj.matrix_world.translation.copy()

    guide.invalidate_pending_implant_axis_empty()
    empty = bpy.data.objects.get(guide.IMPLANT_AXIS_EMPTY_NAME)
    if empty is None:
        empty = bpy.data.objects.new(guide.IMPLANT_AXIS_EMPTY_NAME, None)
        empty.empty_display_type = "SINGLE_ARROW"
        empty.empty_display_size = 8.0
        bpy.context.scene.collection.objects.link(empty)
    guide.orient_empty_to_vector(empty, apical)
    empty.location = origin
    empty.hide_render = True
    empty.hide_viewport = False
    empty.hide_select = False
    try:
        empty.hide_set(False)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    empty["DSG_pending_implant_axis"] = True
    empty["DSG_target_fdi"] = fdi
    empty["DSG_axis_confidence"] = 1.0
    empty["DSG_axis_method"] = "PROSTHETIC_AXIS_FROM_ARCHITECT_GOLD_STANDARD"
    empty["DSG_axis_source_tooth"] = ""
    empty["DSG_axis_source_crown"] = crown.name
    empty["DSG_axis_apical_world"] = tuple(float(v) for v in apical)
    empty["DSG_axis_origin_world"] = tuple(float(v) for v in origin)
    empty["DSG_axis_clinical_review_required"] = True
    empty["DSG_target_family_id"] = dental_assets.family_id(fdi)
    empty["DSG_target_tooth_class"] = dental_assets.tooth_class_from_fdi(fdi)
    empty["DSG_target_arch"] = dental_assets.arch_from_fdi(fdi)
    empty["DSG_target_side"] = dental_assets.side_from_fdi(fdi)
    empty["DSG_asset_contract_sha256"] = dental_assets.contract_sha256()
    return {
        "schema": "dsg.implant_axis_proposal.v1",
        "fdi": fdi,
        "axis_object": empty.name,
        "origin_world": [float(v) for v in origin],
        "apical_axis_world": [float(v) for v in apical],
        "source": "FINAL_CROWN_TARGET_EMERGENCE_GOLD_STANDARD",
        "clinical_review_required": True,
        "committed_implant": False,
    }


def evaluate_implant_candidate(*, fdi: int, implant_name: str | None = None,
                               constraints: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return objective candidate metrics; apply only explicitly supplied constraints."""
    fdi = dental_assets.normalize_fdi(fdi, include_primary=False)
    implant = _resolve_implant(implant_name)
    _dicom, guide = _modules()
    props = getattr(bpy.context.scene, "dsg_props", None)
    axis_obj = dental_asset_blender.find_one(fdi, "PROSTHETIC_AXIS")
    center_obj = dental_asset_blender.find_one(fdi, "EMERGENCE_CENTER")
    if axis_obj is None or center_obj is None:
        raise dental_assets.DentalAssetContractError(
            f"FDI {fdi}: EMERGENCE_CENTER and PROSTHETIC_AXIS required"
        )
    preferred_coronal = (axis_obj.matrix_world.to_3x3() @ Vector((0, 0, 1))).normalized()
    preferred_apical = -preferred_coronal
    actual_axis = guide.get_implant_axis_world(props, implant).normalized()
    if actual_axis.dot(preferred_apical) < 0:
        actual_axis = -actual_axis
    dot = max(-1.0, min(1.0, float(actual_axis.dot(preferred_apical))))
    axis_deviation_deg = math.degrees(math.acos(dot))
    platform = guide.get_implant_platform_center_world(props, implant)
    emergence_center = center_obj.matrix_world.translation.copy()
    emergence_offset_mm = float((platform - emergence_center).length) if platform is not None else None

    neighbor = analyze_implant_neighbor_clearance(fdi=fdi, implant_name=implant.name)
    bone = analyze_implant_bone_support(fdi=fdi, implant_name=implant.name)
    metrics = {
        "axis_deviation_deg": float(axis_deviation_deg),
        "emergence_offset_mm": emergence_offset_mm,
        "minimum_neighbor_clearance_mm": neighbor.get("minimum_neighbor_clearance_mm"),
        "bone_support_score": bone.get("bone_support_score"),
    }
    constraints = dict(constraints or {})
    checks = {}
    if "max_axis_deviation_deg" in constraints:
        limit = float(constraints["max_axis_deviation_deg"])
        checks["max_axis_deviation_deg"] = {"limit": limit, "value": metrics["axis_deviation_deg"], "pass": metrics["axis_deviation_deg"] <= limit}
    if "max_emergence_offset_mm" in constraints and metrics["emergence_offset_mm"] is not None:
        limit = float(constraints["max_emergence_offset_mm"])
        checks["max_emergence_offset_mm"] = {"limit": limit, "value": metrics["emergence_offset_mm"], "pass": metrics["emergence_offset_mm"] <= limit}
    if "min_neighbor_clearance_mm" in constraints and metrics["minimum_neighbor_clearance_mm"] is not None:
        limit = float(constraints["min_neighbor_clearance_mm"])
        checks["min_neighbor_clearance_mm"] = {"limit": limit, "value": metrics["minimum_neighbor_clearance_mm"], "pass": metrics["minimum_neighbor_clearance_mm"] >= limit}
    if "min_bone_support_score" in constraints and metrics["bone_support_score"] is not None:
        limit = float(constraints["min_bone_support_score"])
        checks["min_bone_support_score"] = {"limit": limit, "value": metrics["bone_support_score"], "pass": metrics["bone_support_score"] >= limit}
    return {
        "schema": "dsg.implant_candidate_evaluation.v1",
        "fdi": fdi, "implant": implant.name,
        "metrics": metrics,
        "constraints": constraints,
        "checks": checks,
        "all_explicit_constraints_pass": all(x["pass"] for x in checks.values()) if checks else None,
        "ranking_policy": "NO_HIDDEN_WEIGHTS_MCP_OR_USER_SUPPLIES_PREFERENCES",
        "neighbor_clearance": neighbor,
        "bone_support": bone,
    }
