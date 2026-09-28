"""Blender boundary for the export gate: the only ``guide_export`` module
that imports ``bpy``/``mathutils``.

Responsibilities (and nothing else):
* convert a Blender object into world-space NumPy arrays (mm);
* provide a BVH-backed ``RayCaster`` implementation;
* measure implant ↔ anatomy clearance with BVH queries;
* read the current plan (implants, sleeves, inputs) into ``ExportContext``.
"""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from ..version import DSG_VERSION_STR
from .report import ExportContext, ImplantRecord, sha256_file

LOG = logging.getLogger("dsg.guide_export")
_MAX_INPUT_HASH_BYTES = 4 * 1024 ** 3


# ── Geometry extraction ─────────────────────────────────────────────────────
def mesh_arrays(obj, depsgraph=None) -> tuple[np.ndarray, np.ndarray]:
    """Evaluated (modifiers applied) world-space triangles, as exported to STL."""
    depsgraph = depsgraph or bpy.context.evaluated_depsgraph_get()
    eval_obj = obj.evaluated_get(depsgraph)
    mesh = eval_obj.to_mesh()
    try:
        mesh.calc_loop_triangles()
        n_v, n_t = len(mesh.vertices), len(mesh.loop_triangles)
        co = np.empty(n_v * 3, dtype=np.float64)
        mesh.vertices.foreach_get("co", co)
        tris = np.empty(n_t * 3, dtype=np.int64)
        mesh.loop_triangles.foreach_get("vertices", tris)
    finally:
        eval_obj.to_mesh_clear()
    co = co.reshape(-1, 3)
    mw = np.array(obj.matrix_world, dtype=np.float64)
    world = co @ mw[:3, :3].T + mw[:3, 3]
    return world, tris.reshape(-1, 3)


def triangulate_for_stl(obj) -> int:
    """Triangulate with BEAUTY before writing STL; returns the triangle count.

    Exact Booleans leave large concave n-gons. Blender's STL writer
    triangulates them on the fly and, on concave n-gons, can emit a diagonal
    that duplicates an existing edge (edges shared by 3+ triangles: a
    non-manifold STL, measured on real DSG sleeves in Blender 5.2). BMesh's
    BEAUTY triangulation does not, so the file written is exactly the manifold
    triangle mesh the quality gate checks.
    """
    import bmesh
    bm = bmesh.new()
    try:
        bm.from_mesh(obj.data)
        bmesh.ops.triangulate(bm, faces=bm.faces[:], quad_method="BEAUTY", ngon_method="BEAUTY")
        # "Pinch" edges (two surfaces touching along one edge: 4, 6… faces) are a
        # known EXACT-Boolean artefact. Splitting them separates the two sheets
        # without moving any vertex, so every edge is shared by exactly two
        # triangles again. Odd counts are left for the quality gate to report.
        pinched = [e for e in bm.edges if len(e.link_faces) > 2 and len(e.link_faces) % 2 == 0]
        if pinched:
            bmesh.ops.split_edges(bm, edges=pinched)
            LOG.info("export: split %d pinched edge(s)", len(pinched))
        bm.to_mesh(obj.data)
        obj.data.update()
        obj["DSG_export_pinched_edges_split"] = len(pinched)
        return len(bm.faces)
    finally:
        bm.free()


def bvh_from_arrays(vertices: np.ndarray, triangles: np.ndarray) -> BVHTree:
    return BVHTree.FromPolygons(vertices.tolist(), triangles.tolist(), all_triangles=True)


class BVHRayCaster:
    """``RayCaster`` implementation backed by ``mathutils.bvhtree``."""

    def __init__(self, vertices: np.ndarray, triangles: np.ndarray):
        self._tree = bvh_from_arrays(vertices, triangles)

    def cast(self, origins, directions, max_distance):
        n = len(origins)
        dist = np.full(n, np.inf)
        normals = np.zeros((n, 3))
        ray_cast = self._tree.ray_cast
        for i in range(n):
            loc, nor, _idx, d = ray_cast(Vector(origins[i]), Vector(directions[i]), float(max_distance))
            if loc is not None:
                dist[i] = d
                normals[i] = nor
        return dist, normals


# ── Anatomical clearance ────────────────────────────────────────────────────
def object_clearance_mm(obj_a, obj_b, depsgraph=None) -> tuple[float | None, bool, str]:
    """Minimum distance between two meshes.

    Returns ``(distance_mm, intersects, method)``. Distance is measured
    bidirectionally from every vertex of each mesh to the other surface, i.e.
    a tight *upper bound* of the true surface distance; ``intersects`` comes
    from an exact BVH triangle-overlap test and forces distance 0.
    """
    if obj_a is None or obj_b is None or obj_a.type != "MESH" or obj_b.type != "MESH":
        return None, False, "UNAVAILABLE"
    va, ta = mesh_arrays(obj_a, depsgraph)
    vb, tb = mesh_arrays(obj_b, depsgraph)
    if not len(ta) or not len(tb):
        return None, False, "EMPTY_MESH"
    tree_a, tree_b = bvh_from_arrays(va, ta), bvh_from_arrays(vb, tb)
    if tree_a.overlap(tree_b):
        return 0.0, True, "BVH_TRIANGLE_OVERLAP"
    best = np.inf
    # Implant → canal from every implant vertex first; the result bounds the
    # search so only canal vertices inside that radius need the reverse query.
    for co in va:
        hit = tree_b.find_nearest(Vector(co))
        if hit[0] is not None and hit[3] < best:
            best = hit[3]
    if np.isfinite(best):
        lo, hi = va.min(axis=0) - best, va.max(axis=0) + best
        vb = vb[np.all((vb >= lo) & (vb <= hi), axis=1)]
    for verts, tree in ((vb, tree_a),):
        for co in verts:
            hit = tree.find_nearest(Vector(co), best if np.isfinite(best) else 1.0e9)
            if hit[0] is not None and hit[3] < best:
                best = hit[3]
    return (float(best) if np.isfinite(best) else None), False, "BVH_VERTEX_BIDIRECTIONAL_UPPER_BOUND"


# ── Input fingerprints ──────────────────────────────────────────────────────
def fingerprint(path: str) -> dict:
    """SHA-256 of a file, or of a directory's files (sorted, content-hashed)."""
    if not path:
        return {"path": "", "sha256": None, "note": "not recorded"}
    p = Path(bpy.path.abspath(path))
    try:
        if p.is_file():
            return {"path": str(p), "sha256": sha256_file(p), "bytes": p.stat().st_size}
        if p.is_dir():
            files = sorted(f for f in p.rglob("*") if f.is_file())
            total = sum(f.stat().st_size for f in files)
            h = hashlib.sha256()
            if total > _MAX_INPUT_HASH_BYTES:
                for f in files:
                    st = f.stat()
                    h.update(f"{f.relative_to(p)}|{st.st_size}\n".encode())
                return {"path": str(p), "sha256": h.hexdigest(), "files": len(files), "bytes": total,
                        "note": "directory too large: digest of names+sizes only"}
            for f in files:
                h.update(str(f.relative_to(p)).encode() + b"\0")
                h.update(sha256_file(f).encode())
            return {"path": str(p), "sha256": h.hexdigest(), "files": len(files), "bytes": total}
    except OSError as exc:
        LOG.warning("fingerprint failed for %s: %s", p, exc)
        return {"path": str(p), "sha256": None, "note": f"unreadable: {exc}"}
    return {"path": str(p), "sha256": None, "note": "missing"}


# ── Plan reader (guide_module facade) ───────────────────────────────────────
def _vec(v) -> list[float] | None:
    try:
        return [float(v[0]), float(v[1]), float(v[2])]
    except Exception:  # noqa: BLE001 - optional metadata
        return None


def _safe(fn, *args):
    try:
        return fn(*args)
    except Exception as exc:  # noqa: BLE001 - optional metadata, logged
        LOG.debug("plan reader: %s failed: %s", getattr(fn, "__name__", fn), exc)
        return None


def read_export_context(context, guide_ns, *, operator_options: dict | None = None) -> ExportContext:
    """Collect case/plan metadata. ``guide_ns`` is the ``guide_module``
    namespace (passed in, not imported, to keep this adapter decoupled)."""
    scene = context.scene
    props = scene.dsg_props
    settings = getattr(scene, "dsg_suite_settings", None)
    dicp = getattr(scene, "dicp_props", None)
    ctx = ExportContext(
        dsg_version=DSG_VERSION_STR,
        blender_version=bpy.app.version_string,
        case_name=str(getattr(settings, "case_name", "") or ""),
        patient_folder=str(getattr(settings, "patient_folder", "") or ""),
        operator_options=dict(operator_options or {}),
    )
    ctx.inputs = {
        "dicom": fingerprint(str(scene.get("DSG_patient_dicom_path", "") or "")),
        "ios": fingerprint(str(getattr(dicp, "ios_source_filepath", "") or "")),
    }
    if dicp is not None:
        ctx.inputs["alignment"] = {k: float(getattr(dicp, k, 0.0) or 0.0)
                                   for k in ("landmark_rmse", "icp_error", "icp_overlap", "icp_p95")}
    param_names = ("sleeve_inner_diameter", "sleeve_wall", "sleeve_height", "sleeve_implant_gap",
                   "fresa_offset", "drill_extra_depth", "drill_sleeve_clearance", "blockout_relief",
                   "retention_percent", "implant_tooth_clearance", "tube_radius", "connector_diameter")
    ctx.plan_parameters = {n: round(float(getattr(props, n)), 4) for n in param_names if hasattr(props, n)}

    for implant in _safe(guide_ns.get_all_implant_objects, props) or []:
        rec = ImplantRecord(
            name=implant.name,
            fdi=int(implant.get("DSG_target_fdi", 0) or 0) or None,
            diameter_mm=_safe(guide_ns.get_implant_nominal_diameter_world, props, implant),
            length_mm=_safe(guide_ns.get_implant_length_world, props, implant),
            platform_world_mm=_vec(_safe(guide_ns.get_implant_platform_center_world, props, implant)),
            axis_world=_vec(_safe(guide_ns.get_sleeve_axis_world, props, implant)),
        )
        rec.sleeve = {
            "center_world_mm": _vec(_safe(guide_ns.get_sleeve_center_world, props, implant)),
            "irrigation_open_order": int(implant.get("DSG_irrigation_open_order", 0) or 0) or None,
            "irrigation_frangible_wall": bool(implant.get("DSG_irrigation_sealed", False)),
        }
        ctx.implants.append(rec)
    summary_fn = getattr(guide_ns, "irrigation_network_summary", None)
    if callable(summary_fn):
        ctx.irrigation_network = _safe(summary_fn, props) or []
    return ctx


def find_mandibular_canal():
    try:
        from .. import core
        return core.find_role(core.ROLE_DICOM_MANDIBULAR_CANAL)
    except Exception as exc:  # noqa: BLE001 - absent canal is reported as SKIPPED
        LOG.debug("canal lookup failed: %s", exc)
        return None
