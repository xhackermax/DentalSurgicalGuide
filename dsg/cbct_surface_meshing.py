"""DSG CBCT native-resolution surface extraction engines.

Pure numerical helpers: no bpy imports.

v9.2.64 policy
---------------
* Clinical dental geometry is never downsampled.
* The primary UniversalLab path extracts all requested semantic tooth labels in
  one ``vtkDiscreteFlyingEdges3D`` pass over one dentition crop.
* No per-tooth binary masks are created on the VTK fast path.
* Disconnected islands are rejected after surface extraction.
* Normals and expensive anatomical refinement are lazy/on-demand.
* Full-resolution Lewiner remains a deterministic fallback.

``extract_binary_surface`` is retained for compatibility and explicit local
refinement. ``extract_multilabel_surface`` is the v9.2.64 fast clinical path.
All coordinates are returned in Z,Y,X voxel space; callers convert them into
the DICOM/Blender frame.
"""
from __future__ import annotations

import logging as _dsg_logging
_DSG_LOG = _dsg_logging.getLogger(__name__)

from dataclasses import dataclass
import importlib
import time
import threading
from typing import Any

import numpy as np


@dataclass(frozen=True)
class SurfaceExtraction:
    vertices_zyx: np.ndarray
    faces: np.ndarray
    engine: str
    elapsed_s: float
    requested_step: int
    effective_step: int
    source_shape_zyx: tuple[int, int, int]
    sampled_shape_zyx: tuple[int, int, int]
    fallback_reason: str = ""
    diagnostics: dict[str, Any] | None = None


def _as_binary_u8(mask) -> np.ndarray:
    arr = np.asarray(mask)
    if arr.ndim != 3:
        raise ValueError(f"La mascara debe ser 3-D; recibido shape={arr.shape!r}")
    return np.ascontiguousarray(arr != 0, dtype=np.uint8)


def _sample_for_step(mask_u8: np.ndarray, step_size: int) -> tuple[np.ndarray, int]:
    step = max(1, min(4, int(step_size)))
    if step == 1:
        return mask_u8, 1
    # Preview-only decimation of the *compact ROI*. The physical grid spacing is
    # restored in VTK or by multiplying marching-cubes coordinates by ``step``.
    sampled = np.ascontiguousarray(mask_u8[::step, ::step, ::step], dtype=np.uint8)
    # Tiny masks can become empty/degenerate when decimated. Fall back to native.
    if min(sampled.shape) < 2 or int(sampled.sum()) < 8:
        return mask_u8, 1
    return sampled, step


_VTK_SMP_CONFIGURED = False
_VTK_SMP_LOCK = threading.Lock()


def _configure_vtk_smp(vtk_module: Any) -> dict[str, Any]:
    """Enable a native VTK SMP backend when the wheel exposes one.

    This is intentionally best-effort and performed once. It never makes VTK a
    hard dependency and never fails surface extraction if the wheel was built
    with only the Sequential backend.
    """
    global _VTK_SMP_CONFIGURED
    info = {"backend_before": "", "backend_after": "", "threads": 0, "changed": False}
    tools = getattr(vtk_module, "vtkSMPTools", None)
    if tools is None:
        return info
    # vtkSMPTools.SetBackend()/Initialize() are explicitly not thread-safe.
    # Serialize the one-time configuration even if a future DSG worker policy
    # invokes meshing from more than one thread.
    with _VTK_SMP_LOCK:
        try:
            before = str(tools.GetBackend() or "")
            info["backend_before"] = before
            if not _VTK_SMP_CONFIGURED and before.lower() == "sequential":
                try:
                    if bool(tools.SetBackend("STDThread")):
                        cpu = max(1, min(8, int(__import__("os").environ.get("DSG_WORKER_CPU_THREADS", __import__("os").cpu_count() or 1))))
                        try:
                            tools.Initialize(cpu)
                        except Exception:
                            _DSG_LOG.debug("suppressed exception", exc_info=True)
                        info["changed"] = True
                except Exception:
                    _DSG_LOG.debug("suppressed exception", exc_info=True)
            _VTK_SMP_CONFIGURED = True
            info["backend_after"] = str(tools.GetBackend() or "")
            try:
                info["threads"] = int(tools.GetEstimatedNumberOfThreads())
            except Exception:
                info["threads"] = 0
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    return info


def _vtk_poly_to_arrays(poly, numpy_support):
    if poly is None or poly.GetNumberOfPoints() < 4 or poly.GetNumberOfPolys() < 4:
        raise RuntimeError("VTK devolvio una superficie vacia")
    points_xyz = np.asarray(
        numpy_support.vtk_to_numpy(poly.GetPoints().GetData()), dtype=np.float64
    )
    polys = poly.GetPolys()
    if hasattr(polys, "GetConnectivityArray") and polys.GetConnectivityArray() is not None:
        conn = np.asarray(numpy_support.vtk_to_numpy(polys.GetConnectivityArray()), dtype=np.int64)
        offsets = np.asarray(numpy_support.vtk_to_numpy(polys.GetOffsetsArray()), dtype=np.int64)
        sizes = np.diff(offsets)
        if len(sizes) == 0 or not np.all(sizes == 3):
            raise RuntimeError("VTK produjo celdas no triangulares")
        faces = conn.reshape((-1, 3))
    else:
        raw = np.asarray(numpy_support.vtk_to_numpy(polys.GetData()), dtype=np.int64)
        if raw.size % 4 != 0:
            raise RuntimeError("CellArray VTK inesperado")
        raw = raw.reshape((-1, 4))
        if not np.all(raw[:, 0] == 3):
            raise RuntimeError("VTK produjo celdas no triangulares")
        faces = raw[:, 1:4]
    vertices_zyx = np.ascontiguousarray(points_xyz[:, (2, 1, 0)], dtype=np.float64)
    return vertices_zyx, np.ascontiguousarray(faces, dtype=np.int32)


def _vtk_flying_edges(mask_u8: np.ndarray, *, step_size: int, vtk_module: Any) -> tuple[np.ndarray, np.ndarray, int, str, dict[str, Any]]:
    sampled, step = _sample_for_step(mask_u8, step_size)
    padded = np.pad(sampled, 1, mode="constant", constant_values=0)
    nz, ny, nx = (int(v) for v in padded.shape)

    try:
        numpy_support = importlib.import_module("vtk.util.numpy_support")
    except Exception as exc:
        raise RuntimeError(f"vtk.util.numpy_support no disponible: {exc}") from exc

    smp_info = _configure_vtk_smp(vtk_module)
    image = vtk_module.vtkImageData()
    image.SetDimensions(nx, ny, nz)
    image.SetSpacing(float(step), float(step), float(step))
    image.SetOrigin(-float(step), -float(step), -float(step))
    scalars = numpy_support.numpy_to_vtk(
        np.ascontiguousarray(padded).ravel(order="C"),
        deep=True,
        array_type=vtk_module.VTK_UNSIGNED_CHAR,
    )
    scalars.SetName("DSG_binary_label")
    image.GetPointData().SetScalars(scalars)

    engine = "VTK_DISCRETE_FLYING_EDGES"
    discrete_cls = getattr(vtk_module, "vtkDiscreteFlyingEdges3D", None)
    if discrete_cls is not None:
        flying = discrete_cls()
        flying.SetInputData(image)
        # Binary segmentation: generate the boundary of label value 1.
        if hasattr(flying, "SetValue"):
            flying.SetValue(0, 1)
        elif hasattr(flying, "GenerateValues"):
            flying.GenerateValues(1, 1, 1)
        if hasattr(flying, "ComputeNormalsOff"):
            flying.ComputeNormalsOff()
        if hasattr(flying, "ComputeGradientsOff"):
            flying.ComputeGradientsOff()
        if hasattr(flying, "ComputeScalarsOff"):
            flying.ComputeScalarsOff()
        flying.Update()
    else:
        engine = "VTK_FLYING_EDGES_COMPAT"
        flying = vtk_module.vtkFlyingEdges3D()
        flying.SetInputData(image)
        flying.SetValue(0, 0.5)
        flying.ComputeNormalsOff()
        flying.ComputeGradientsOff()
        flying.ComputeScalarsOff()
        if hasattr(flying, "InterpolateAttributesOff"):
            flying.InterpolateAttributesOff()
        flying.Update()

    vertices_zyx, faces = _vtk_poly_to_arrays(flying.GetOutput(), numpy_support)
    return vertices_zyx, faces, int(step), engine, smp_info

def _skimage_lewiner(mask_u8: np.ndarray, *, step_size: int, measure_module: Any) -> tuple[np.ndarray, np.ndarray, int]:
    step = max(1, min(4, int(step_size)))
    padded = np.pad(mask_u8, 1, mode="constant", constant_values=0).astype(np.float32, copy=False)
    vertices, faces, _normals, _values = measure_module.marching_cubes(
        padded,
        level=0.5,
        step_size=step,
        allow_degenerate=False,
        method="lewiner",
    )
    vertices = np.asarray(vertices, dtype=np.float64)
    vertices -= 1.0
    return (
        np.ascontiguousarray(vertices, dtype=np.float64),
        np.ascontiguousarray(faces, dtype=np.int32),
        int(step),
    )


def extract_binary_surface(
    mask,
    *,
    step_size: int = 1,
    preferred_engine: str = "AUTO",
    vtk_module: Any | None = None,
    skimage_measure: Any | None = None,
) -> SurfaceExtraction:
    """Extract an isosurface from one compact binary ROI.

    ``AUTO`` tries VTK Flying Edges first and falls back to Lewiner. No engine
    failure is allowed to destroy the segmentation route if the fallback exists.
    """
    mask_u8 = _as_binary_u8(mask)
    if int(mask_u8.sum()) < 8:
        raise RuntimeError("Mascara demasiado pequena para extraer superficie")

    requested = max(1, min(4, int(step_size)))
    preferred = str(preferred_engine or "AUTO").upper()
    started = time.perf_counter()
    vtk_error = ""

    if preferred in {"AUTO", "VTK", "FLYING_EDGES", "VTK_FLYING_EDGES"} and vtk_module is not None:
        try:
            vertices, faces, effective, vtk_engine, smp_info = _vtk_flying_edges(
                mask_u8, step_size=requested, vtk_module=vtk_module
            )
            sampled_shape = tuple(int(v) for v in mask_u8[::effective, ::effective, ::effective].shape)
            return SurfaceExtraction(
                vertices_zyx=vertices,
                faces=faces,
                engine=str(vtk_engine),
                elapsed_s=float(time.perf_counter() - started),
                requested_step=requested,
                effective_step=int(effective),
                source_shape_zyx=tuple(int(v) for v in mask_u8.shape),
                sampled_shape_zyx=sampled_shape,
                diagnostics={"vtk_smp": dict(smp_info or {})},
            )
        except Exception as exc:
            vtk_error = f"{type(exc).__name__}: {exc}"
            if preferred not in {"AUTO"} and skimage_measure is None:
                raise

    if skimage_measure is None:
        detail = f"; VTK fallo: {vtk_error}" if vtk_error else ""
        raise RuntimeError(f"No hay motor de superficie CBCT disponible{detail}")

    vertices, faces, effective = _skimage_lewiner(
        mask_u8, step_size=requested, measure_module=skimage_measure
    )
    return SurfaceExtraction(
        vertices_zyx=vertices,
        faces=faces,
        engine="SKIMAGE_LEWINER",
        elapsed_s=float(time.perf_counter() - started),
        requested_step=requested,
        effective_step=int(effective),
        source_shape_zyx=tuple(int(v) for v in mask_u8.shape),
        sampled_shape_zyx=tuple(int(v) for v in mask_u8.shape),
        fallback_reason=vtk_error,
        diagnostics={},
    )

# =============================================================================
# v9.2.64 — native full-resolution multi-label extraction
# =============================================================================

@dataclass(frozen=True)
class LabelSurfaceExtraction:
    label: int
    vertices_zyx: np.ndarray
    faces: np.ndarray
    topology: dict[str, Any]


@dataclass(frozen=True)
class MultiLabelSurfaceExtraction:
    items: dict[int, LabelSurfaceExtraction]
    engine: str
    elapsed_s: float
    source_shape_zyx: tuple[int, int, int]
    crop_origin_zyx: tuple[int, int, int]
    crop_shape_zyx: tuple[int, int, int]
    diagnostics: dict[str, Any] | None = None
    fallback_reason: str = ""


def _triangle_components(vertices: np.ndarray, faces: np.ndarray) -> tuple[np.ndarray, int]:
    """Connected-component id per vertex, using triangle edges.

    SciPy's compiled sparse graph implementation is preferred. A compact
    union-find fallback keeps this helper usable in minimal installations.
    """
    vertices = np.asarray(vertices)
    faces = np.asarray(faces, dtype=np.int64)
    n_vertices = int(len(vertices))
    if n_vertices == 0:
        return np.empty(0, dtype=np.int32), 0
    if len(faces) == 0:
        return np.arange(n_vertices, dtype=np.int32), n_vertices

    try:
        from scipy.sparse import coo_matrix
        from scipy.sparse.csgraph import connected_components
        e01 = faces[:, (0, 1)]
        e12 = faces[:, (1, 2)]
        e20 = faces[:, (2, 0)]
        edges = np.concatenate((e01, e12, e20), axis=0)
        rows = np.concatenate((edges[:, 0], edges[:, 1]))
        cols = np.concatenate((edges[:, 1], edges[:, 0]))
        data = np.ones(len(rows), dtype=np.uint8)
        graph = coo_matrix((data, (rows, cols)), shape=(n_vertices, n_vertices)).tocsr()
        count, labels = connected_components(graph, directed=False, return_labels=True)
        return np.asarray(labels, dtype=np.int32), int(count)
    except Exception:
        parent = np.arange(n_vertices, dtype=np.int64)
        rank = np.zeros(n_vertices, dtype=np.uint8)

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = int(parent[x])
            return x

        def union(a: int, b: int) -> None:
            ra, rb = find(a), find(b)
            if ra == rb:
                return
            if rank[ra] < rank[rb]:
                ra, rb = rb, ra
            parent[rb] = ra
            if rank[ra] == rank[rb]:
                rank[ra] += 1

        for tri in faces:
            a, b, c = (int(v) for v in tri)
            union(a, b); union(b, c); union(c, a)
        roots = np.fromiter((find(i) for i in range(n_vertices)), dtype=np.int64, count=n_vertices)
        _unique, inverse = np.unique(roots, return_inverse=True)
        return np.asarray(inverse, dtype=np.int32), int(len(_unique))


def clean_surface_components(
    vertices_zyx: np.ndarray,
    faces: np.ndarray,
    *,
    spacing_zyx=(1.0, 1.0, 1.0),
    minimum_significant_mm3: float = 60.0,
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    """Keep only the dominant connected surface component.

    v9.2.64 deliberately performs island rejection *after* native-resolution
    surface extraction. This avoids one connected-components pass over every
    per-tooth voxel mask. Component significance is estimated from enclosed
    mesh volume where possible, with triangle count as a robust fallback for
    clipped/open acquisitions.
    """
    vertices = np.asarray(vertices_zyx, dtype=np.float64)
    triangles = np.asarray(faces, dtype=np.int32)
    if len(vertices) < 4 or len(triangles) < 4:
        return vertices, triangles, {
            "status": "EMPTY", "component_count": 0,
            "significant_component_count": 0, "removed_faces": 0,
        }

    vertex_components, count = _triangle_components(vertices, triangles)
    face_components = vertex_components[triangles[:, 0]]
    # A valid triangle must not straddle components. If malformed input does,
    # assign it to its first vertex but mark the anomaly for audit.
    mixed = np.any(vertex_components[triangles] != face_components[:, None], axis=1)

    spacing = np.asarray(spacing_zyx, dtype=np.float64).reshape(3)
    mm_vertices = vertices * spacing[None, :]
    component_rows = []
    for cid in range(int(count)):
        face_idx = np.flatnonzero(face_components == cid)
        if face_idx.size == 0:
            continue
        tri = mm_vertices[triangles[face_idx]]
        signed = np.einsum(
            "ij,ij->i", tri[:, 0], np.cross(tri[:, 1], tri[:, 2])
        )
        volume = float(abs(signed.sum()) / 6.0)
        area_vec = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
        area = float(0.5 * np.linalg.norm(area_vec, axis=1).sum())
        component_rows.append((cid, int(face_idx.size), volume, area))

    if not component_rows:
        return vertices, triangles, {
            "status": "EMPTY", "component_count": 0,
            "significant_component_count": 0, "removed_faces": int(len(triangles)),
        }

    # Closed components use volume; open/clipped components fall back to area.
    dominant = max(component_rows, key=lambda row: (row[2] if row[2] > 1e-6 else 0.0, row[3], row[1]))
    keep_cid = int(dominant[0])
    keep_faces = triangles[face_components == keep_cid]
    used = np.unique(keep_faces.ravel())
    remap = np.full(len(vertices), -1, dtype=np.int64)
    remap[used] = np.arange(len(used), dtype=np.int64)
    out_vertices = np.ascontiguousarray(vertices[used], dtype=np.float64)
    out_faces = np.ascontiguousarray(remap[keep_faces], dtype=np.int32)

    significant = 0
    for _cid, face_count, volume, area in component_rows:
        if volume >= float(minimum_significant_mm3):
            significant += 1
        elif volume <= 1e-6 and area >= 15.0 and face_count >= 40:
            significant += 1

    diagnostics = {
        "status": (
            "REVIEW_MULTICOMPONENT_PRIMARY_SELECTED" if significant > 1
            else "VALID_PRIMARY_COMPONENT"
        ),
        "component_count": int(len(component_rows)),
        "significant_component_count": int(significant),
        "largest_component_id": int(keep_cid),
        "largest_component_faces": int(len(keep_faces)),
        "largest_component_volume_mm3": float(dominant[2]),
        "largest_component_area_mm2": float(dominant[3]),
        "removed_faces": int(len(triangles) - len(keep_faces)),
        "mixed_component_triangles": int(np.count_nonzero(mixed)),
    }
    return out_vertices, out_faces, diagnostics


def _vtk_multilabel_flying_edges(
    labels_crop: np.ndarray,
    label_values: list[int],
    *,
    crop_origin_zyx=(0, 0, 0),
    vtk_module: Any,
    spacing_zyx=(1.0, 1.0, 1.0),
) -> MultiLabelSurfaceExtraction:
    """Extract all requested semantic labels in one VTK pass at native resolution."""
    started = time.perf_counter()
    arr = np.asarray(labels_crop)
    if arr.ndim != 3:
        raise ValueError("El labelmap debe ser 3-D")
    values = sorted({int(v) for v in label_values if int(v) > 0})
    if not values:
        raise ValueError("No hay labels dentales para extraer")

    try:
        numpy_support = importlib.import_module("vtk.util.numpy_support")
    except Exception as exc:
        raise RuntimeError(f"vtk.util.numpy_support no disponible: {exc}") from exc

    # UniversalLab uses <=55, therefore uint8 preserves labels exactly and cuts
    # transfer bandwidth in half versus uint16/int32.
    crop_u8 = np.ascontiguousarray(arr, dtype=np.uint8)
    padded = np.pad(crop_u8, 1, mode="constant", constant_values=0)
    nz, ny, nx = (int(v) for v in padded.shape)
    smp_info = _configure_vtk_smp(vtk_module)

    image = vtk_module.vtkImageData()
    image.SetDimensions(nx, ny, nz)
    image.SetSpacing(1.0, 1.0, 1.0)
    image.SetOrigin(-1.0, -1.0, -1.0)
    scalars = numpy_support.numpy_to_vtk(
        padded.ravel(order="C"), deep=True,
        array_type=vtk_module.VTK_UNSIGNED_CHAR,
    )
    scalars.SetName("DSG_semantic_label")
    image.GetPointData().SetScalars(scalars)

    cls = getattr(vtk_module, "vtkDiscreteFlyingEdges3D", None)
    if cls is None:
        raise RuntimeError("Este VTK no incluye vtkDiscreteFlyingEdges3D")
    flying = cls()
    flying.SetInputData(image)
    if hasattr(flying, "SetNumberOfContours"):
        flying.SetNumberOfContours(len(values))
    for i, value in enumerate(values):
        flying.SetValue(i, int(value))
    if hasattr(flying, "ComputeNormalsOff"):
        flying.ComputeNormalsOff()
    if hasattr(flying, "ComputeGradientsOff"):
        flying.ComputeGradientsOff()
    # Keep scalars ON here. The output point scalar is the semantic label and
    # lets DSG split all teeth without rerunning VTK or materializing masks.
    if hasattr(flying, "ComputeScalarsOn"):
        flying.ComputeScalarsOn()
    flying.Update()
    poly = flying.GetOutput()
    if poly is None or poly.GetNumberOfPoints() < 4 or poly.GetNumberOfPolys() < 4:
        raise RuntimeError("VTK multietiqueta devolvió una superficie vacía")

    # One compiled connectivity pass for the complete dentition is much cheaper
    # than N SciPy sparse-graph constructions. RegionId is preserved alongside
    # the semantic point scalar and lets DSG reject islands after meshing.
    connectivity_used = False
    connectivity_cls = getattr(vtk_module, "vtkPolyDataConnectivityFilter", None)
    if connectivity_cls is not None:
        try:
            connectivity = connectivity_cls()
            connectivity.SetInputData(poly)
            connectivity.SetExtractionModeToAllRegions()
            connectivity.ColorRegionsOn()
            connectivity.Update()
            poly = connectivity.GetOutput()
            connectivity_used = True
        except Exception:
            connectivity_used = False

    points_xyz = np.asarray(
        numpy_support.vtk_to_numpy(poly.GetPoints().GetData()), dtype=np.float64
    )
    vertices_zyx = np.ascontiguousarray(points_xyz[:, (2, 1, 0)], dtype=np.float64)
    polys = poly.GetPolys()
    if hasattr(polys, "GetConnectivityArray") and polys.GetConnectivityArray() is not None:
        conn = np.asarray(numpy_support.vtk_to_numpy(polys.GetConnectivityArray()), dtype=np.int64)
        offsets = np.asarray(numpy_support.vtk_to_numpy(polys.GetOffsetsArray()), dtype=np.int64)
        sizes = np.diff(offsets)
        if len(sizes) == 0 or not np.all(sizes == 3):
            raise RuntimeError("VTK multietiqueta produjo celdas no triangulares")
        triangles = conn.reshape((-1, 3))
    else:
        raw = np.asarray(numpy_support.vtk_to_numpy(polys.GetData()), dtype=np.int64).reshape((-1, 4))
        if not np.all(raw[:, 0] == 3):
            raise RuntimeError("VTK multietiqueta produjo celdas no triangulares")
        triangles = raw[:, 1:4]

    # ConnectivityFilter may make RegionId the active scalar. Always retrieve
    # the semantic label array by name so component coloring cannot overwrite
    # the FDI identity used to split the single-pass output.
    point_scalars = poly.GetPointData().GetArray("DSG_semantic_label")
    if point_scalars is None:
        point_scalars = poly.GetPointData().GetScalars()
    if point_scalars is None:
        raise RuntimeError("VTK no conservó el identificador semántico de cada diente")
    point_labels = np.asarray(numpy_support.vtk_to_numpy(point_scalars), dtype=np.int32).reshape(-1)
    tri_labels = point_labels[triangles[:, 0]]
    label_mismatch = np.any(point_labels[triangles] != tri_labels[:, None], axis=1)
    point_region = None
    tri_region = None
    if connectivity_used:
        try:
            region_array = poly.GetPointData().GetArray("RegionId")
            if region_array is not None:
                point_region = np.asarray(numpy_support.vtk_to_numpy(region_array), dtype=np.int32).reshape(-1)
                tri_region = point_region[triangles[:, 0]]
        except Exception:
            point_region = None; tri_region = None

    z0, y0, x0 = (int(v) for v in crop_origin_zyx)
    origin = np.asarray((z0, y0, x0), dtype=np.float64)
    items: dict[int, LabelSurfaceExtraction] = {}
    for label in values:
        face_idx = np.flatnonzero((tri_labels == int(label)) & ~label_mismatch)
        if face_idx.size < 4:
            continue
        label_faces_global = triangles[face_idx]
        topology = None
        # Fast path: VTK already colored connected components globally. For the
        # normal one-component tooth no graph/volume calculation is necessary.
        if tri_region is not None:
            regions = np.unique(tri_region[face_idx])
            if len(regions) == 1:
                topology = {
                    "status": "VALID_PRIMARY_COMPONENT",
                    "component_count": 1,
                    "significant_component_count": 1,
                    "largest_component_id": int(regions[0]),
                    "removed_faces": 0,
                    "cleanup_backend": "VTK_REGION_ID",
                }
            elif len(regions) > 1:
                spacing = np.asarray(spacing_zyx, dtype=np.float64).reshape(3)
                rows = []
                for rid in regions:
                    rid_faces = label_faces_global[tri_region[face_idx] == int(rid)]
                    used_r = np.unique(rid_faces.ravel())
                    tri_mm = vertices_zyx[rid_faces] * spacing[None, None, :]
                    signed = np.einsum("ij,ij->i", tri_mm[:,0], np.cross(tri_mm[:,1], tri_mm[:,2]))
                    volume = float(abs(signed.sum()) / 6.0)
                    area = float(0.5 * np.linalg.norm(
                        np.cross(tri_mm[:,1]-tri_mm[:,0], tri_mm[:,2]-tri_mm[:,0]), axis=1
                    ).sum())
                    rows.append((int(rid), int(len(rid_faces)), volume, area, rid_faces))
                dominant = max(rows, key=lambda row: (row[2] if row[2] > 1e-6 else 0.0, row[3], row[1]))
                label_faces_global = dominant[4]
                significant = sum(
                    1 for row in rows
                    if row[2] >= 60.0 or (row[2] <= 1e-6 and row[3] >= 15.0 and row[1] >= 40)
                )
                topology = {
                    "status": "REVIEW_MULTICOMPONENT_PRIMARY_SELECTED" if significant > 1 else "VALID_PRIMARY_COMPONENT",
                    "component_count": int(len(rows)),
                    "significant_component_count": int(significant),
                    "largest_component_id": int(dominant[0]),
                    "largest_component_faces": int(dominant[1]),
                    "largest_component_volume_mm3": float(dominant[2]),
                    "largest_component_area_mm2": float(dominant[3]),
                    "removed_faces": int(len(face_idx) - dominant[1]),
                    "cleanup_backend": "VTK_REGION_ID",
                }

        used = np.unique(label_faces_global.ravel())
        remap = np.full(len(vertices_zyx), -1, dtype=np.int64)
        remap[used] = np.arange(len(used), dtype=np.int64)
        local_v = vertices_zyx[used]
        local_f = np.asarray(remap[label_faces_global], dtype=np.int32)
        if topology is None:
            local_v, local_f, topology = clean_surface_components(
                local_v, local_f, spacing_zyx=spacing_zyx,
            )
        if len(local_f) < 4:
            continue
        # VTK image origin -1 exactly cancels the one-voxel padding. Crop origin
        # restores global UniversalLab voxel coordinates.
        local_v = np.ascontiguousarray(local_v + origin[None, :], dtype=np.float64)
        items[int(label)] = LabelSurfaceExtraction(
            label=int(label), vertices_zyx=local_v,
            faces=np.ascontiguousarray(local_f, dtype=np.int32),
            topology=dict(topology),
        )

    return MultiLabelSurfaceExtraction(
        items=items,
        engine="VTK_DISCRETE_FLYING_EDGES_MULTILABEL_NATIVE",
        elapsed_s=float(time.perf_counter() - started),
        source_shape_zyx=tuple(int(v) for v in arr.shape),
        crop_origin_zyx=(z0, y0, x0),
        crop_shape_zyx=tuple(int(v) for v in crop_u8.shape),
        diagnostics={
            "vtk_smp": dict(smp_info or {}),
            "requested_labels": values,
            "produced_labels": sorted(items),
            "vtk_points": int(poly.GetNumberOfPoints()),
            "vtk_triangles": int(poly.GetNumberOfPolys()),
            "mixed_label_triangles_dropped": int(np.count_nonzero(label_mismatch)),
            "native_resolution": True,
            "single_pass": True,
            "connectivity_backend": "VTK_REGION_ID" if connectivity_used else "SCIPY_FALLBACK",
        },
    )


def extract_multilabel_surface(
    labels_crop,
    label_values,
    *,
    crop_origin_zyx=(0, 0, 0),
    vtk_module: Any | None = None,
    skimage_measure: Any | None = None,
    spacing_zyx=(1.0, 1.0, 1.0),
) -> MultiLabelSurfaceExtraction:
    """Native-resolution multi-label extraction with deterministic fallback.

    VTK performs one pass over the cropped semantic labelmap. The fallback is
    full-resolution Lewiner per label and is used only when VTK is unavailable.
    No preview/downsample geometry is ever emitted by this function.
    """
    arr = np.asarray(labels_crop)
    values = sorted({int(v) for v in label_values if int(v) > 0})
    vtk_error = ""
    if vtk_module is not None:
        try:
            return _vtk_multilabel_flying_edges(
                arr, values, crop_origin_zyx=crop_origin_zyx,
                vtk_module=vtk_module, spacing_zyx=spacing_zyx,
            )
        except Exception as exc:
            vtk_error = f"{type(exc).__name__}: {exc}"

    if skimage_measure is None:
        raise RuntimeError(
            "No hay motor full-resolution para labelmap dental"
            + (f"; VTK: {vtk_error}" if vtk_error else "")
        )

    started = time.perf_counter()
    z0, y0, x0 = (int(v) for v in crop_origin_zyx)
    origin = np.asarray((z0, y0, x0), dtype=np.float64)
    items: dict[int, LabelSurfaceExtraction] = {}
    for label in values:
        mask = np.ascontiguousarray(arr == int(label), dtype=np.uint8)
        if int(mask.sum()) < 8:
            continue
        vertices, faces, _effective = _skimage_lewiner(
            mask, step_size=1, measure_module=skimage_measure
        )
        vertices, faces, topology = clean_surface_components(
            vertices, faces, spacing_zyx=spacing_zyx,
        )
        if len(faces) < 4:
            continue
        items[int(label)] = LabelSurfaceExtraction(
            label=int(label),
            vertices_zyx=np.ascontiguousarray(vertices + origin[None, :], dtype=np.float64),
            faces=np.ascontiguousarray(faces, dtype=np.int32),
            topology=dict(topology),
        )

    return MultiLabelSurfaceExtraction(
        items=items,
        engine="SKIMAGE_LEWINER_MULTILABEL_FALLBACK_NATIVE",
        elapsed_s=float(time.perf_counter() - started),
        source_shape_zyx=tuple(int(v) for v in arr.shape),
        crop_origin_zyx=(z0, y0, x0),
        crop_shape_zyx=tuple(int(v) for v in arr.shape),
        diagnostics={"native_resolution": True, "single_pass": False},
        fallback_reason=vtk_error,
    )
