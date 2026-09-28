"""DSG v9.2.64 native-resolution threshold surface engine.

Pure numerical module, no bpy imports.

Goals
-----
* Never downsample the clinical scalar field.
* Reuse one calibrated float32 volume for repeated HU/density thresholds.
* Build an exact block min/max hierarchy (Span-Space style pruning).
* Classify active blocks on CUDA when available.
* Extract the native isosurface either with a Torch/CUDA Marching Cubes
  implementation or with continuous vtkFlyingEdges3D on active hierarchy chunks.
* Fall back to full-resolution scikit-image when neither accelerator is usable.

All vertices are returned in GLOBAL voxel Z,Y,X coordinates. The caller owns
conversion into the DICOM/Blender frame.
"""
from __future__ import annotations

import logging as _dsg_logging
_DSG_LOG = _dsg_logging.getLogger(__name__)

from dataclasses import dataclass, field
import math
import time
from typing import Any

import numpy as np


@dataclass
class ThresholdBlockIndex:
    shape_zyx: tuple[int, int, int]
    block_size: int
    parent_factor: int
    block_min: np.ndarray
    block_max: np.ndarray
    parent_min: np.ndarray
    parent_max: np.ndarray
    build_s: float
    torch_module: Any | None = None
    cuda_device: Any | None = None
    density_cuda: Any | None = None
    block_min_cuda: Any | None = None
    block_max_cuda: Any | None = None
    gpu_enabled: bool = False
    # Persistent zero-copy VTK view of the same full-resolution NumPy scalar
    # volume. Kept here so repeated thresholds never recopy hundreds of MB.
    vtk_numpy_view: Any | None = None
    vtk_image: Any | None = None
    vtk_filter: Any | None = None
    vtk_module_token: int = 0
    diagnostics: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ThresholdSurface:
    vertices_zyx: np.ndarray
    faces: np.ndarray
    engine: str
    elapsed_s: float
    diagnostics: dict[str, Any]


def _padded_point_shape(shape, block_size: int):
    out = []
    b = int(block_size)
    for dim in shape:
        cells = max(0, int(dim) - 1)
        blocks = max(1, int(math.ceil(cells / float(b))))
        out.append(blocks * b + 1)
    return tuple(out)


def _cpu_block_minmax(values: np.ndarray, block_size: int):
    from numpy.lib.stride_tricks import sliding_window_view
    b = int(block_size)
    target = _padded_point_shape(values.shape, b)
    pads = tuple((0, int(t - s)) for s, t in zip(values.shape, target))
    padded = np.pad(values, pads, mode="edge") if any(p[1] for p in pads) else values
    windows = sliding_window_view(padded, (b + 1, b + 1, b + 1))[::b, ::b, ::b]
    mins = np.min(windows, axis=(-3, -2, -1)).astype(np.float32, copy=False)
    maxs = np.max(windows, axis=(-3, -2, -1)).astype(np.float32, copy=False)
    return np.ascontiguousarray(mins), np.ascontiguousarray(maxs)


def _reduce_parent_minmax(block_min: np.ndarray, block_max: np.ndarray, factor: int):
    f = max(2, int(factor))
    shape = np.asarray(block_min.shape, dtype=np.int64)
    padded_shape = ((shape + f - 1) // f) * f
    pads = tuple((0, int(p - s)) for s, p in zip(shape, padded_shape))
    mn = np.pad(block_min, pads, mode="constant", constant_values=np.inf)
    mx = np.pad(block_max, pads, mode="constant", constant_values=-np.inf)
    pz, py, px = (int(v) for v in padded_shape)
    mn = mn.reshape(pz // f, f, py // f, f, px // f, f).min(axis=(1, 3, 5))
    mx = mx.reshape(pz // f, f, py // f, f, px // f, f).max(axis=(1, 3, 5))
    return np.ascontiguousarray(mn, dtype=np.float32), np.ascontiguousarray(mx, dtype=np.float32)


def _try_prepare_cuda(values: np.ndarray, torch_module: Any | None, block_size: int):
    if torch_module is None:
        return None
    torch = torch_module
    try:
        if not bool(torch.cuda.is_available()):
            return None
        device = torch.device("cuda")
        free_b, _total_b = torch.cuda.mem_get_info(device)
        required = int(values.nbytes * 1.30)
        if int(free_b) < required:
            return None
        tensor = torch.as_tensor(values, dtype=torch.float32, device=device)
        return device, tensor
    except Exception:
        return None


def _gpu_block_minmax(tensor, block_size: int, torch_module: Any):
    torch = torch_module
    import torch.nn.functional as F
    b = int(block_size)
    shape = tuple(int(v) for v in tensor.shape)
    target = _padded_point_shape(shape, b)
    # replicate padding keeps the exact min/max of the final partial block.
    pz, py, px = (int(target[i] - shape[i]) for i in range(3))
    x = tensor[None, None]
    if pz or py or px:
        x = F.pad(x, (0, px, 0, py, 0, pz), mode="replicate")
    maxs = F.max_pool3d(x, kernel_size=b + 1, stride=b)[0, 0]
    mins = -F.max_pool3d(-x, kernel_size=b + 1, stride=b)[0, 0]
    return mins, maxs


def build_threshold_index(
    density_zyx,
    *,
    block_size: int = 16,
    parent_factor: int = 4,
    torch_module: Any | None = None,
    prefer_cuda: bool = True,
) -> ThresholdBlockIndex:
    started = time.perf_counter()
    values = np.ascontiguousarray(density_zyx, dtype=np.float32)
    if values.ndim != 3 or min(values.shape) < 2:
        raise ValueError("El CBCT calibrado debe ser un volumen 3-D")
    b = max(4, min(32, int(block_size)))
    pf = max(2, min(8, int(parent_factor)))

    device = None
    density_cuda = None
    block_min_cuda = None
    block_max_cuda = None
    gpu = False
    gpu_error = ""

    if prefer_cuda:
        prepared = _try_prepare_cuda(values, torch_module, b)
        if prepared is not None:
            device, density_cuda = prepared
            try:
                block_min_cuda, block_max_cuda = _gpu_block_minmax(density_cuda, b, torch_module)
                block_min = block_min_cuda.detach().cpu().numpy().astype(np.float32, copy=False)
                block_max = block_max_cuda.detach().cpu().numpy().astype(np.float32, copy=False)
                gpu = True
            except Exception as exc:
                gpu_error = f"{type(exc).__name__}: {exc}"
                density_cuda = None
                block_min_cuda = None
                block_max_cuda = None
                device = None
                block_min, block_max = _cpu_block_minmax(values, b)
        else:
            block_min, block_max = _cpu_block_minmax(values, b)
    else:
        block_min, block_max = _cpu_block_minmax(values, b)

    parent_min, parent_max = _reduce_parent_minmax(block_min, block_max, pf)
    elapsed = float(time.perf_counter() - started)
    return ThresholdBlockIndex(
        shape_zyx=tuple(int(v) for v in values.shape),
        block_size=b,
        parent_factor=pf,
        block_min=np.ascontiguousarray(block_min),
        block_max=np.ascontiguousarray(block_max),
        parent_min=parent_min,
        parent_max=parent_max,
        build_s=elapsed,
        torch_module=torch_module,
        cuda_device=device,
        density_cuda=density_cuda,
        block_min_cuda=block_min_cuda,
        block_max_cuda=block_max_cuda,
        gpu_enabled=bool(gpu),
        diagnostics={
            "gpu_index": bool(gpu),
            "gpu_error": gpu_error,
            "block_grid": tuple(int(v) for v in block_min.shape),
            "parent_grid": tuple(int(v) for v in parent_min.shape),
            "density_bytes": int(values.nbytes),
            "native_resolution": True,
        },
    )


def active_blocks(index: ThresholdBlockIndex, level: float) -> np.ndarray:
    """Exact active leaf blocks: min <= level <= max."""
    t = float(level)
    if index.gpu_enabled and index.block_min_cuda is not None:
        torch = index.torch_module
        try:
            mask = (index.block_min_cuda <= t) & (index.block_max_cuda >= t)
            coords = torch.nonzero(mask, as_tuple=False)
            return np.asarray(coords.detach().cpu().numpy(), dtype=np.int32)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    mask = (index.block_min <= t) & (index.block_max >= t)
    return np.ascontiguousarray(np.argwhere(mask), dtype=np.int32)


def active_parent_blocks(index: ThresholdBlockIndex, level: float) -> np.ndarray:
    t = float(level)
    mask = (index.parent_min <= t) & (index.parent_max >= t)
    return np.ascontiguousarray(np.argwhere(mask), dtype=np.int32)


def _weld_by_quantization(vertices, faces, tol: float = 1e-6):
    vertices = np.asarray(vertices, dtype=np.float64)
    faces = np.asarray(faces, dtype=np.int64)
    if len(vertices) == 0 or len(faces) == 0:
        return vertices.astype(np.float32), faces.astype(np.int32)
    q = np.rint(vertices / float(tol)).astype(np.int64)
    _keys, first, inv = np.unique(q, axis=0, return_index=True, return_inverse=True)
    vf = inv[faces]
    valid = (vf[:, 0] != vf[:, 1]) & (vf[:, 1] != vf[:, 2]) & (vf[:, 2] != vf[:, 0])
    vv = vertices[np.asarray(first, dtype=np.int64)]
    vf = vf[valid]
    if len(vf):
        tri = vv[vf]
        area2 = np.linalg.norm(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1)
        vf = vf[area2 > 1e-10]
    return np.ascontiguousarray(vv, dtype=np.float32), np.ascontiguousarray(vf, dtype=np.int32)


def _vtk_scalar_chunk(values: np.ndarray, level: float, origin_zyx, vtk_module: Any):
    from vtk.util import numpy_support
    from . import cbct_surface_meshing
    arr = np.ascontiguousarray(values, dtype=np.float32)
    nz, ny, nx = (int(v) for v in arr.shape)
    image = vtk_module.vtkImageData()
    image.SetDimensions(nx, ny, nz)
    image.SetSpacing(1.0, 1.0, 1.0)
    image.SetOrigin(0.0, 0.0, 0.0)
    scalars = numpy_support.numpy_to_vtk(
        arr.ravel(order="C"), deep=True, array_type=vtk_module.VTK_FLOAT
    )
    scalars.SetName("DSG_native_density")
    image.GetPointData().SetScalars(scalars)
    cbct_surface_meshing._configure_vtk_smp(vtk_module)
    fe = vtk_module.vtkFlyingEdges3D()
    fe.SetInputData(image)
    fe.SetValue(0, float(level))
    fe.ComputeNormalsOff(); fe.ComputeGradientsOff(); fe.ComputeScalarsOff()
    if hasattr(fe, "InterpolateAttributesOff"):
        fe.InterpolateAttributesOff()
    fe.Update()
    poly = fe.GetOutput()
    if poly is None or poly.GetNumberOfPolys() == 0:
        return None
    v, f = cbct_surface_meshing._vtk_poly_to_arrays(poly, numpy_support)
    v += np.asarray(origin_zyx, dtype=np.float64)[None, :]
    return v, f



def _prepare_vtk_zero_copy_cache(density_zyx, index: ThresholdBlockIndex, vtk_module: Any):
    """Bind VTK directly to DSG's persistent float32 NumPy volume.

    ``deep=False`` is safe because both the flat view and its base array are kept
    alive by RUNTIME/index for the life of the loaded DICOM case.
    """
    token = id(vtk_module)
    if index.vtk_filter is not None and index.vtk_module_token == token:
        return index.vtk_filter
    from vtk.util import numpy_support
    from . import cbct_surface_meshing
    values = np.ascontiguousarray(density_zyx, dtype=np.float32)
    flat = values.ravel(order="C")
    nz, ny, nx = (int(v) for v in values.shape)
    image = vtk_module.vtkImageData()
    image.SetDimensions(nx, ny, nz)
    image.SetSpacing(1.0, 1.0, 1.0)
    image.SetOrigin(0.0, 0.0, 0.0)
    scalars = numpy_support.numpy_to_vtk(
        flat, deep=False, array_type=vtk_module.VTK_FLOAT
    )
    scalars.SetName("DSG_native_density_zero_copy")
    image.GetPointData().SetScalars(scalars)
    cbct_surface_meshing._configure_vtk_smp(vtk_module)
    fe = vtk_module.vtkFlyingEdges3D()
    fe.SetInputData(image)
    fe.ComputeNormalsOff(); fe.ComputeGradientsOff(); fe.ComputeScalarsOff()
    if hasattr(fe, "InterpolateAttributesOff"):
        fe.InterpolateAttributesOff()
    index.vtk_numpy_view = flat
    index.vtk_image = image
    index.vtk_filter = fe
    index.vtk_module_token = token
    return fe


def _compact_remove_degenerate(vertices, faces):
    vertices = np.asarray(vertices, dtype=np.float64)
    faces = np.asarray(faces, dtype=np.int64)
    if len(faces) == 0:
        return vertices.astype(np.float32), faces.astype(np.int32)
    valid = (faces[:,0] != faces[:,1]) & (faces[:,1] != faces[:,2]) & (faces[:,2] != faces[:,0])
    faces = faces[valid]
    if len(faces):
        tri = vertices[faces]
        area2 = np.linalg.norm(np.cross(tri[:,1]-tri[:,0], tri[:,2]-tri[:,0]), axis=1)
        faces = faces[area2 > 1e-10]
    used = np.unique(faces.ravel()) if len(faces) else np.empty(0, dtype=np.int64)
    if len(used) == len(vertices):
        return np.ascontiguousarray(vertices, dtype=np.float32), np.ascontiguousarray(faces, dtype=np.int32)
    remap = np.full(len(vertices), -1, dtype=np.int64)
    remap[used] = np.arange(len(used), dtype=np.int64)
    return (
        np.ascontiguousarray(vertices[used], dtype=np.float32),
        np.ascontiguousarray(remap[faces], dtype=np.int32),
    )


def extract_threshold_vtk_zero_copy(
    density_zyx,
    level: float,
    index: ThresholdBlockIndex,
    *,
    vtk_module: Any,
) -> ThresholdSurface:
    started = time.perf_counter()
    from vtk.util import numpy_support
    from . import cbct_surface_meshing
    fe = _prepare_vtk_zero_copy_cache(density_zyx, index, vtk_module)
    fe.SetValue(0, float(level))
    fe.Modified()
    fe.Update()
    poly = fe.GetOutput()
    if poly is None or poly.GetNumberOfPolys() < 1:
        raise RuntimeError("Flying Edges no produjo superficie para el umbral")
    # Flying Edges may emit zero-area cells / duplicate points when the
    # isovalue lands exactly on samples. vtkStaticCleanPolyData removes those
    # in compiled code with absolute tolerance 0, preserving every coordinate.
    clean_cls = getattr(vtk_module, "vtkStaticCleanPolyData", None)
    if clean_cls is not None:
        cleaner = clean_cls(); cleaner.SetInputData(poly)
        if hasattr(cleaner, "ToleranceIsAbsoluteOn"):
            cleaner.ToleranceIsAbsoluteOn()
        if hasattr(cleaner, "SetAbsoluteTolerance"):
            cleaner.SetAbsoluteTolerance(0.0)
        cleaner.Update()
        poly = cleaner.GetOutput()
    vertices, faces = cbct_surface_meshing._vtk_poly_to_arrays(poly, numpy_support)
    vertices, faces = _compact_remove_degenerate(vertices, faces)
    return ThresholdSurface(
        vertices_zyx=vertices,
        faces=faces,
        engine="VTK_FLYING_EDGES_NATIVE_ZERO_COPY",
        elapsed_s=float(time.perf_counter() - started),
        diagnostics={
            "native_resolution": True,
            "vtk_zero_copy": True,
            "vtk_full_volume": True,
            "vtk_internal_computational_trimming": True,
            "block_index_build_s": float(index.build_s),
            "gpu_block_classification": bool(index.gpu_enabled),
        },
    )


def extract_threshold_vtk_hierarchy(
    density_zyx,
    level: float,
    index: ThresholdBlockIndex,
    *,
    vtk_module: Any,
) -> ThresholdSurface:
    started = time.perf_counter()
    values = np.asarray(density_zyx, dtype=np.float32)
    parents = active_parent_blocks(index, level)
    if len(parents) == 0:
        raise RuntimeError("El umbral no cruza ninguna celda del CBCT")
    chunk_cells = int(index.block_size * index.parent_factor)
    shape = tuple(int(v) for v in values.shape)
    vertex_parts = []
    face_parts = []
    offset = 0
    processed = 0
    for pz, py, px in parents:
        z0 = int(pz) * chunk_cells; y0 = int(py) * chunk_cells; x0 = int(px) * chunk_cells
        # point end is cell end + 1
        z1 = min(shape[0], z0 + chunk_cells + 1)
        y1 = min(shape[1], y0 + chunk_cells + 1)
        x1 = min(shape[2], x0 + chunk_cells + 1)
        if z1 - z0 < 2 or y1 - y0 < 2 or x1 - x0 < 2:
            continue
        chunk = values[z0:z1, y0:y1, x0:x1]
        finite = chunk[np.isfinite(chunk)]
        if finite.size == 0 or float(finite.min()) > float(level) or float(finite.max()) < float(level):
            continue
        result = _vtk_scalar_chunk(chunk, level, (z0, y0, x0), vtk_module)
        if result is None:
            continue
        v, f = result
        vertex_parts.append(v)
        face_parts.append(np.asarray(f, dtype=np.int32) + int(offset))
        offset += len(v)
        processed += 1
    if not face_parts:
        raise RuntimeError("Flying Edges no produjo superficie para el umbral")
    vertices = np.concatenate(vertex_parts, axis=0)
    faces = np.concatenate(face_parts, axis=0)
    vertices, faces = _weld_by_quantization(vertices, faces, tol=1e-6)
    return ThresholdSurface(
        vertices_zyx=vertices,
        faces=faces,
        engine="VTK_FLYING_EDGES_NATIVE_HIERARCHICAL",
        elapsed_s=float(time.perf_counter() - started),
        diagnostics={
            "native_resolution": True,
            "active_parent_blocks": int(len(parents)),
            "processed_chunks": int(processed),
            "chunk_cells": int(chunk_cells),
            "block_index_build_s": float(index.build_s),
            "gpu_block_classification": bool(index.gpu_enabled),
        },
    )


# Standard Marching Cubes corner/edge convention used by skimage CASESCLASSIC.
_CORNERS = np.asarray([
    (0, 0, 0), (0, 0, 1), (0, 1, 1), (0, 1, 0),
    (1, 0, 0), (1, 0, 1), (1, 1, 1), (1, 1, 0),
], dtype=np.int64)
_EDGES = np.asarray([
    (0, 1), (1, 2), (2, 3), (3, 0),
    (4, 5), (5, 6), (6, 7), (7, 4),
    (0, 4), (1, 5), (2, 6), (3, 7),
], dtype=np.int64)
_EDGE_LOW = np.minimum(_CORNERS[_EDGES[:, 0]], _CORNERS[_EDGES[:, 1]])
_EDGE_AXIS = np.argmax(np.abs(_CORNERS[_EDGES[:, 1]] - _CORNERS[_EDGES[:, 0]]), axis=1).astype(np.int64)


def _load_mc_classic_table():
    try:
        from skimage.measure import _marching_cubes_lewiner as mcl
        from skimage.measure import _marching_cubes_lewiner_luts as luts
        return np.asarray(mcl._to_array(luts.CASESCLASSIC), dtype=np.int64)
    except Exception:
        return None


def _torch_cuda_marching_cubes(
    density_zyx,
    level: float,
    index: ThresholdBlockIndex,
    *,
    max_blocks_per_batch: int = 64,
) -> ThresholdSurface:
    """Exact native-grid Marching Cubes on CUDA using the classic case table.

    The algorithm enumerates cells only inside exact active min/max blocks. Grid
    edge IDs are globally unique, so duplicate vertices are removed without a
    spatial tolerance and block boundaries remain watertight.
    """
    started = time.perf_counter()
    torch = index.torch_module
    if torch is None or not index.gpu_enabled or index.density_cuda is None:
        raise RuntimeError("CUDA no está preparado para Marching Cubes")
    tri_table_np = _load_mc_classic_table()
    if tri_table_np is None:
        raise RuntimeError("No está disponible la tabla Marching Cubes de skimage")

    blocks = active_blocks(index, level)
    if len(blocks) == 0:
        raise RuntimeError("El umbral no cruza ninguna celda del CBCT")
    device = index.cuda_device
    volume = index.density_cuda
    zdim, ydim, xdim = (int(v) for v in index.shape_zyx)
    b = int(index.block_size)

    table = torch.as_tensor(tri_table_np, dtype=torch.int64, device=device)
    corners = torch.as_tensor(_CORNERS, dtype=torch.int64, device=device)
    edges = torch.as_tensor(_EDGES, dtype=torch.int64, device=device)
    edge_low = torch.as_tensor(_EDGE_LOW, dtype=torch.int64, device=device)
    edge_axis = torch.as_tensor(_EDGE_AXIS, dtype=torch.int64, device=device)
    bit_weights = (1 << torch.arange(8, dtype=torch.int64, device=device))
    oz, oy, ox = torch.meshgrid(
        torch.arange(b, dtype=torch.int64, device=device),
        torch.arange(b, dtype=torch.int64, device=device),
        torch.arange(b, dtype=torch.int64, device=device),
        indexing="ij",
    )
    cell_offsets = torch.stack((oz, oy, ox), dim=-1).reshape(-1, 3)

    all_edge_ids = []
    all_positions = []
    all_faces = []
    vertex_offset = 0
    active_cells_total = 0
    triangles_total = 0

    blocks_per_batch = max(1, int(max_blocks_per_batch))
    for start in range(0, len(blocks), blocks_per_batch):
        block_np = blocks[start:start + blocks_per_batch]
        block_t = torch.as_tensor(block_np, dtype=torch.int64, device=device)
        bases = block_t[:, None, :] * b
        coords = (bases + cell_offsets[None, :, :]).reshape(-1, 3)
        valid_cell = (
            (coords[:, 0] < zdim - 1) &
            (coords[:, 1] < ydim - 1) &
            (coords[:, 2] < xdim - 1)
        )
        coords = coords[valid_cell]
        if int(coords.shape[0]) == 0:
            continue
        pc = coords[:, None, :] + corners[None, :, :]
        vals = volume[pc[:, :, 0], pc[:, :, 1], pc[:, :, 2]]
        cases = ((vals >= float(level)).to(torch.int64) * bit_weights[None, :]).sum(dim=1)
        nontrivial = (cases != 0) & (cases != 255)
        coords = coords[nontrivial]
        vals = vals[nontrivial]
        cases = cases[nontrivial]
        if int(coords.shape[0]) == 0:
            continue
        active_cells_total += int(coords.shape[0])

        rows = table[cases]
        valid_ref = rows >= 0
        nvalid = valid_ref.sum(dim=1)
        # CASESCLASSIC always emits edge refs in groups of 3.
        valid_cells = (nvalid >= 3) & ((nvalid % 3) == 0)
        coords = coords[valid_cells]
        vals = vals[valid_cells]
        rows = rows[valid_cells]
        nvalid = nvalid[valid_cells]
        if int(coords.shape[0]) == 0:
            continue

        refs_flat = rows.reshape(-1)
        valid_flat = refs_flat >= 0
        edge_ref = refs_flat[valid_flat]
        cell_rep = torch.repeat_interleave(
            torch.arange(len(coords), dtype=torch.int64, device=device), nvalid
        )
        base = coords[cell_rep]
        cell_vals = vals[cell_rep]
        ep = edges[edge_ref]
        p0 = base + corners[ep[:, 0]]
        p1 = base + corners[ep[:, 1]]
        row_idx = torch.arange(len(edge_ref), dtype=torch.int64, device=device)
        v0 = cell_vals[row_idx, ep[:, 0]]
        v1 = cell_vals[row_idx, ep[:, 1]]
        den = v1 - v0
        t = torch.where(
            torch.abs(den) > 1e-12,
            (float(level) - v0) / den,
            torch.full_like(den, 0.5),
        )
        pos = p0.to(torch.float32) + t[:, None] * (p1 - p0).to(torch.float32)

        low = base + edge_low[edge_ref]
        axis = edge_axis[edge_ref]
        edge_id = (((low[:, 0] * ydim + low[:, 1]) * xdim + low[:, 2]) * 3 + axis)
        # Stable sort gives first position for each unique grid edge.
        order = torch.argsort(edge_id)
        sorted_id = edge_id[order]
        first_mask = torch.ones(len(order), dtype=torch.bool, device=device)
        if len(order) > 1:
            first_mask[1:] = sorted_id[1:] != sorted_id[:-1]
        first = order[first_mask]
        unique_ids = sorted_id[first_mask]
        unique_pos = pos[first]
        # searchsorted maps every edge reference to the sorted unique id list.
        inverse = torch.searchsorted(unique_ids, edge_id)
        faces = inverse.reshape(-1, 3)
        # Our >= case convention is the complement of skimage's outward winding.
        faces = faces[:, (0, 2, 1)]

        all_edge_ids.append(unique_ids.detach().cpu().numpy().astype(np.int64, copy=False))
        all_positions.append(unique_pos.detach().cpu().numpy().astype(np.float32, copy=False))
        all_faces.append(faces.detach().cpu().numpy().astype(np.int64, copy=False) + int(vertex_offset))
        vertex_offset += int(unique_pos.shape[0])
        triangles_total += int(faces.shape[0])

    if not all_faces:
        raise RuntimeError("CUDA Marching Cubes no produjo superficie")

    ids = np.concatenate(all_edge_ids, axis=0)
    positions = np.concatenate(all_positions, axis=0)
    faces = np.concatenate(all_faces, axis=0)
    unique_ids, first, inverse = np.unique(ids, return_index=True, return_inverse=True)
    vertices = positions[np.asarray(first, dtype=np.int64)]
    faces = inverse[faces]
    valid = (
        (faces[:, 0] != faces[:, 1]) &
        (faces[:, 1] != faces[:, 2]) &
        (faces[:, 2] != faces[:, 0])
    )
    faces = faces[valid]
    if len(faces):
        tri = vertices[faces]
        area2 = np.linalg.norm(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1)
        faces = faces[area2 > 1e-10]
    return ThresholdSurface(
        vertices_zyx=np.ascontiguousarray(vertices, dtype=np.float32),
        faces=np.ascontiguousarray(faces, dtype=np.int32),
        engine="TORCH_CUDA_MARCHING_CUBES_NATIVE",
        elapsed_s=float(time.perf_counter() - started),
        diagnostics={
            "native_resolution": True,
            "active_leaf_blocks": int(len(blocks)),
            "active_cells": int(active_cells_total),
            "triangles_before_cleanup": int(triangles_total),
            "unique_grid_edges": int(len(unique_ids)),
            "block_index_build_s": float(index.build_s),
            "gpu_block_classification": True,
            "cuda_device": str(index.cuda_device),
        },
    )


def extract_threshold_surface(
    density_zyx,
    level: float,
    index: ThresholdBlockIndex,
    *,
    vtk_module: Any | None = None,
    skimage_measure: Any | None = None,
    prefer_gpu: bool = True,
) -> ThresholdSurface:
    """Best available exact native-resolution threshold surface."""
    errors = []
    if prefer_gpu and index.gpu_enabled:
        try:
            # Avoid pathological temporary allocations. The exact block pruning
            # still leaves a huge surface in some full-head thresholds; VTK is
            # better at streaming those cases.
            leaf = active_blocks(index, level)
            estimated_cells = int(len(leaf)) * int(index.block_size ** 3)
            if estimated_cells <= 18_000_000:
                return _torch_cuda_marching_cubes(density_zyx, level, index)
        except Exception as exc:
            errors.append(f"CUDA:{type(exc).__name__}:{exc}")

    if vtk_module is not None:
        try:
            # Global Flying Edges already performs its own computational trimming.
            # A persistent zero-copy input is usually faster than thousands of
            # Python-level chunk calls while remaining exactly full resolution.
            result = extract_threshold_vtk_zero_copy(
                density_zyx, level, index, vtk_module=vtk_module
            )
            if errors:
                d = dict(result.diagnostics); d["prior_errors"] = errors
                return ThresholdSurface(result.vertices_zyx, result.faces, result.engine, result.elapsed_s, d)
            return result
        except Exception as exc:
            errors.append(f"VTK_ZERO_COPY:{type(exc).__name__}:{exc}")
            try:
                result = extract_threshold_vtk_hierarchy(
                    density_zyx, level, index, vtk_module=vtk_module
                )
                d = dict(result.diagnostics); d["prior_errors"] = errors
                return ThresholdSurface(result.vertices_zyx, result.faces, result.engine, result.elapsed_s, d)
            except Exception as exc2:
                errors.append(f"VTK_HIER:{type(exc2).__name__}:{exc2}")

    if skimage_measure is not None:
        started = time.perf_counter()
        values = np.asarray(density_zyx, dtype=np.float32)
        finite = values[np.isfinite(values)]
        if finite.size == 0 or float(finite.min()) > float(level) or float(finite.max()) < float(level):
            raise RuntimeError("El umbral no contiene anatomía visible")
        outside = min(float(finite.min()), float(level) - max(1e-3, abs(float(level)) * 1e-5))
        safe = np.where(np.isfinite(values), values, outside).astype(np.float32, copy=False)
        v, f, _n, _sv = skimage_measure.marching_cubes(
            safe, level=float(level), step_size=1,
            allow_degenerate=False, method="lewiner"
        )
        return ThresholdSurface(
            vertices_zyx=np.ascontiguousarray(v, dtype=np.float32),
            faces=np.ascontiguousarray(f, dtype=np.int32),
            engine="SKIMAGE_LEWINER_NATIVE_FULL_VOLUME_FALLBACK",
            elapsed_s=float(time.perf_counter() - started),
            diagnostics={"native_resolution": True, "prior_errors": errors},
        )

    raise RuntimeError("No hay motor de isosuperficie native full-res: " + " | ".join(errors))
