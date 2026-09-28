"""DSG CBCT-constrained anatomical surface refinement.

The segmentation mask and original CBCT remain the source of truth.  This module
improves triangle distribution/visual continuity without free-form sculpting:

1. Optional MMG surface remesh when a compatible ``mmgpy`` wheel is already
   importable in the current Blender ABI.
2. Small Taubin passes (non-shrinking compared with ordinary Laplacian smooth).
3. Reprojection to the original segmentation signed-distance surface for teeth.
4. Sub-voxel attraction to a strong local CBCT edge, only inside a narrow band.
5. Volume/displacement guards.  Unsafe refinements fall back to the original
   marching-cubes geometry instead of inventing anatomy.

The module has no required external dependency.  SciPy is used when available
from the existing DSG AI runtime.  MMG is an optional accelerator/remesher.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RefineProfile:
    taubin_iterations: int
    taubin_lambda: float
    taubin_mu: float
    max_band_voxels: float
    cbct_snap_fraction: float
    min_volume_ratio: float
    max_volume_ratio: float
    use_sdf: bool
    allow_mmg: bool


PROFILES = {
    "TOOTH": RefineProfile(
        # v9.2.64: preserve the native label geometry. Automatic tooth refinement
        # is projection-only; no remeshing or Taubin displacement is allowed.
        taubin_iterations=0,
        taubin_lambda=0.0,
        taubin_mu=0.0,
        max_band_voxels=0.72,
        cbct_snap_fraction=0.55,
        min_volume_ratio=0.998,
        max_volume_ratio=1.030,
        use_sdf=True,
        allow_mmg=False,
    ),
    # Manual, clinician-triggered finishing pass. It remains sub-voxel and
    # mask-caged, but samples the original CBCT edge more strongly than the
    # automatic segmentation pass.
    "TOOTH_HIGH": RefineProfile(
        # Explicit high-detail refinement may snap sub-voxel to the source CBCT
        # but still cannot smooth/remesh away the native UniversalLab boundary.
        taubin_iterations=0,
        taubin_lambda=0.0,
        taubin_mu=0.0,
        max_band_voxels=0.90,
        cbct_snap_fraction=0.75,
        min_volume_ratio=0.995,
        max_volume_ratio=1.035,
        use_sdf=True,
        allow_mmg=False,
    ),
    "JAW": RefineProfile(
        taubin_iterations=0,
        taubin_lambda=0.0,
        taubin_mu=0.0,
        max_band_voxels=0.62,
        cbct_snap_fraction=0.32,
        min_volume_ratio=0.995,
        max_volume_ratio=1.020,
        use_sdf=False,
        allow_mmg=False,
    ),
    "BONE": RefineProfile(
        taubin_iterations=0,
        taubin_lambda=0.0,
        taubin_mu=0.0,
        max_band_voxels=0.55,
        cbct_snap_fraction=0.28,
        min_volume_ratio=0.995,
        max_volume_ratio=1.020,
        use_sdf=False,
        allow_mmg=False,
    ),
}

MAX_SDF_VOXELS = 12_000_000  # retained for compatibility; automatic path no longer builds 3-D EDT/SDF
MAX_TAUBIN_VERTICES = 180_000
MAX_MMG_TOOTH_VERTICES = 180_000
MAX_CBCT_SNAP_VERTICES = 180_000
MAX_MASK_CAGE_VERTICES = 220_000
SAMPLE_CHUNK_VERTICES = 60_000


def _mesh_volume(np, vertices, faces) -> float:
    v = np.asarray(vertices, dtype=np.float64)
    f = np.asarray(faces, dtype=np.int64)
    if len(v) < 4 or len(f) < 4:
        return 0.0
    tri = v[f]
    signed = np.einsum("ij,ij->i", tri[:, 0], np.cross(tri[:, 1], tri[:, 2]))
    return float(abs(signed.sum()) / 6.0)


def _vertex_normals(np, vertices, faces):
    v = np.asarray(vertices, dtype=np.float64)
    f = np.asarray(faces, dtype=np.int64)
    normals = np.zeros_like(v, dtype=np.float64)
    if len(f) == 0:
        return normals
    tri = v[f]
    fn = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    for corner in range(3):
        np.add.at(normals, f[:, corner], fn)
    lengths = np.linalg.norm(normals, axis=1)
    valid = lengths > 1e-12
    normals[valid] /= lengths[valid, None]
    return normals


def _laplacian_delta(np, vertices, faces):
    """Uniform umbrella Laplacian without Python adjacency sets."""
    v = np.asarray(vertices, dtype=np.float64)
    f = np.asarray(faces, dtype=np.int64)
    sums = np.zeros_like(v, dtype=np.float64)
    counts = np.zeros(len(v), dtype=np.float64)
    for a, b in ((0, 1), (1, 2), (2, 0)):
        ia = f[:, a]
        ib = f[:, b]
        np.add.at(sums, ia, v[ib])
        np.add.at(sums, ib, v[ia])
        np.add.at(counts, ia, 1.0)
        np.add.at(counts, ib, 1.0)
    valid = counts > 0
    average = v.copy()
    average[valid] = sums[valid] / counts[valid, None]
    return average - v


def _taubin(np, vertices, faces, *, iterations: int, lam: float, mu: float):
    v = np.asarray(vertices, dtype=np.float64).copy()
    if len(v) > MAX_TAUBIN_VERTICES or len(faces) == 0 or iterations <= 0:
        return v
    for _ in range(int(iterations)):
        v += float(lam) * _laplacian_delta(np, v, faces)
        v += float(mu) * _laplacian_delta(np, v, faces)
    return v


def _cap_displacement(np, refined, source, max_mm: float):
    if len(refined) != len(source):
        return refined, 0
    delta = refined - source
    length = np.linalg.norm(delta, axis=1)
    mask = length > float(max_mm)
    if mask.any():
        delta[mask] *= (float(max_mm) / np.maximum(length[mask], 1e-12))[:, None]
        refined = source + delta
    return refined, int(mask.sum())


def _try_mmg(np, vertices, faces, *, min_spacing: float):
    """Best-effort MMG surface remesh for teeth only.

    The current user-supplied extension is Linux-only, so this path is optional.
    If a Windows cp311/cp313 mmgpy wheel is later bundled/installed, DSG uses it
    automatically.  Failure never blocks clinical segmentation.
    """
    try:
        from mmgpy import MmgMeshS  # type: ignore
    except Exception as exc:
        return vertices, faces, {"used": False, "reason": f"not_importable:{type(exc).__name__}"}
    if len(vertices) > MAX_MMG_TOOTH_VERTICES:
        return vertices, faces, {"used": False, "reason": "mesh_too_large"}
    try:
        mesh = MmgMeshS(
            np.ascontiguousarray(vertices, dtype=np.float64),
            np.ascontiguousarray(faces, dtype=np.int32),
        )
        hmin = max(0.08, 0.42 * float(min_spacing))
        hmax = max(hmin * 1.8, min(0.42, 1.35 * float(min_spacing)))
        hausd = max(0.025, min(0.12, 0.28 * float(min_spacing)))
        mesh.remesh(
            progress=False,
            hmin=float(hmin),
            hmax=float(hmax),
            hausd=float(hausd),
            hgrad=1.20,
        )
        out_v = np.asarray(mesh.get_vertices(), dtype=np.float64)
        out_f = np.asarray(mesh.get_triangles(), dtype=np.int32)
        if len(out_v) < 4 or len(out_f) < 4:
            raise RuntimeError("MMG devolvió una malla vacía")
        return out_v, out_f, {
            "used": True,
            "hmin": float(hmin), "hmax": float(hmax),
            "hausd": float(hausd), "hgrad": 1.20,
        }
    except Exception as exc:
        return vertices, faces, {"used": False, "reason": f"failed:{type(exc).__name__}:{exc}"}


def _build_sdf(np, ndimage, mask, origin_zyx, spacing_zyx):
    mask = np.asarray(mask, dtype=bool)
    if mask.ndim != 3 or mask.size > MAX_SDF_VOXELS:
        return None
    # A real exterior halo is required so signed distance is meaningful even
    # when the compact crop touches the segmented object.
    pad = 2
    padded = np.pad(mask, pad, mode="constant", constant_values=False)
    spacing = tuple(float(v) for v in spacing_zyx)
    inside = ndimage.distance_transform_edt(padded, sampling=spacing)
    outside = ndimage.distance_transform_edt(~padded, sampling=spacing)
    sdf = np.asarray(inside - outside, dtype=np.float32)
    gz, gy, gx = np.gradient(sdf, *spacing, edge_order=1)
    origin = tuple(int(v) - pad for v in origin_zyx)
    return sdf, (gz, gy, gx), origin


def _sample_grid(np, ndimage, grid, coords_local_zyx):
    q = np.asarray(coords_local_zyx, dtype=np.float64).T
    return ndimage.map_coordinates(grid, q, order=1, mode="nearest", prefilter=False)



def _sample_local_mask(np, ndimage, mask, coords_local_zyx):
    """Trilinear mask sampling in bounded chunks without materialising float volumes."""
    coords = np.asarray(coords_local_zyx, dtype=np.float64)
    out = np.empty((len(coords),), dtype=np.float32)
    for start in range(0, len(coords), SAMPLE_CHUNK_VERTICES):
        end = min(len(coords), start + SAMPLE_CHUNK_VERTICES)
        q = coords[start:end].T
        out[start:end] = ndimage.map_coordinates(
            mask, q, output=np.float32, order=1, mode="nearest", prefilter=False
        )
    return out


def _project_to_mask_surface(np, ndimage, dicom_module, vertices, faces, mask, origin_zyx, *, band_mm: float, normals=None):
    """Fast local cage projection onto the learned 0.5 mask isosurface.

    This replaces the old full 3-D EDT + signed-distance-field construction.
    We only sample five points along each mesh normal inside a narrow sub-voxel
    band, find the nearest inside/outside transition, and move the vertex to that
    crossing. Complexity follows mesh size instead of crop volume, which keeps
    Blender responsive while the mask remains the anatomical source of truth.
    """
    if mask is None or len(vertices) == 0 or len(vertices) > MAX_MASK_CAGE_VERTICES:
        return vertices, 0, {"used": False, "reason": "missing_or_too_large"}
    v = np.asarray(vertices, dtype=np.float64).copy()
    normals = _vertex_normals(np, v, faces) if normals is None else np.asarray(normals, dtype=np.float64)
    nlen = np.linalg.norm(normals, axis=1)
    valid_normal = nlen > 0.5
    if not valid_normal.any():
        return v, 0, {"used": False, "reason": "no_valid_normals"}

    spacing_z, spacing_y, spacing_x = (float(x) for x in dicom_module.RUNTIME.spacing_zyx_mm)
    sign_x, sign_y, sign_z = dicom_module._dicom_display_signs_xyz()
    q_global = dicom_module._centered_xyz_to_global_voxel(v)
    q = q_global - np.asarray(tuple(int(x) for x in origin_zyx), dtype=np.float64)[None, :]
    dvox = np.empty_like(v)
    dvox[:, 0] = sign_z * normals[:, 2] / max(spacing_z, 1e-9)
    dvox[:, 1] = sign_y * normals[:, 1] / max(spacing_y, 1e-9)
    dvox[:, 2] = sign_x * normals[:, 0] / max(spacing_x, 1e-9)

    offsets = np.asarray((-1.0, -0.5, 0.0, 0.5, 1.0), dtype=np.float64) * float(band_mm)
    values = np.empty((len(v), len(offsets)), dtype=np.float32)
    for index, off in enumerate(offsets):
        values[:, index] = _sample_local_mask(np, ndimage, mask, q + dvox * float(off))

    a = values[:, :-1] - 0.5
    b = values[:, 1:] - 0.5
    delta = values[:, 1:] - values[:, :-1]
    crossing = (a * b <= 0.0) & (np.abs(delta) > 1.0e-4)
    midpoint_abs = np.abs(0.5 * (offsets[:-1] + offsets[1:]))
    score = np.where(crossing, midpoint_abs[None, :], np.inf)
    best = np.argmin(score, axis=1)
    has_crossing = np.isfinite(score[np.arange(len(v)), best]) & valid_normal
    if not has_crossing.any():
        return v, 0, {"used": True, "crossings": 0}

    row = np.arange(len(v))
    v0 = values[row, best].astype(np.float64)
    v1 = values[row, best + 1].astype(np.float64)
    denom = v1 - v0
    t = np.zeros(len(v), dtype=np.float64)
    good_denom = np.abs(denom) > 1.0e-6
    t[good_denom] = (0.5 - v0[good_denom]) / denom[good_denom]
    t = np.clip(t, 0.0, 1.0)
    crossing_mm = offsets[best] + t * (offsets[best + 1] - offsets[best])
    crossing_mm = np.clip(crossing_mm, -float(band_mm), float(band_mm))
    v[has_crossing] += normals[has_crossing] * crossing_mm[has_crossing, None]
    return v, int(has_crossing.sum()), {
        "used": True,
        "crossings": int(has_crossing.sum()),
        "max_band_mm": float(band_mm),
    }


def _project_to_sdf(np, ndimage, dicom_module, vertices, sdf_pack, *, iterations: int = 2):
    if sdf_pack is None:
        return vertices, 0
    sdf, gradients, origin = sdf_pack
    v = np.asarray(vertices, dtype=np.float64).copy()
    sign_x, sign_y, sign_z = dicom_module._dicom_display_signs_xyz()
    moved = 0
    for _ in range(max(1, int(iterations))):
        global_q = dicom_module._centered_xyz_to_global_voxel(v)
        local_q = global_q - np.asarray(origin, dtype=np.float64)[None, :]
        d = _sample_grid(np, ndimage, sdf, local_q)
        gz = _sample_grid(np, ndimage, gradients[0], local_q)
        gy = _sample_grid(np, ndimage, gradients[1], local_q)
        gx = _sample_grid(np, ndimage, gradients[2], local_q)
        g = np.column_stack((sign_x * gx, sign_y * gy, sign_z * gz))
        norm_sq = np.einsum("ij,ij->i", g, g)
        good = np.isfinite(d) & np.isfinite(norm_sq) & (norm_sq > 1e-8)
        step = np.zeros_like(v)
        step[good] = -(d[good] / norm_sq[good])[:, None] * g[good]
        # One projection wave may not move farther than half a native voxel.
        cap = 0.50 * min(float(s) for s in dicom_module.RUNTIME.spacing_zyx_mm)
        length = np.linalg.norm(step, axis=1)
        over = length > cap
        step[over] *= (cap / np.maximum(length[over], 1e-12))[:, None]
        active = good & (np.linalg.norm(step, axis=1) > 1e-5)
        v[active] += step[active]
        moved += int(active.sum())
        if not active.any():
            break
    return v, moved


def _clamp_sdf_band(np, ndimage, dicom_module, vertices, sdf_pack, *, band_mm: float):
    if sdf_pack is None:
        return vertices, 0
    sdf, gradients, origin = sdf_pack
    v = np.asarray(vertices, dtype=np.float64).copy()
    global_q = dicom_module._centered_xyz_to_global_voxel(v)
    local_q = global_q - np.asarray(origin, dtype=np.float64)[None, :]
    d = _sample_grid(np, ndimage, sdf, local_q)
    violation = np.abs(d) > float(band_mm)
    if not violation.any():
        return v, 0
    sign_x, sign_y, sign_z = dicom_module._dicom_display_signs_xyz()
    gz = _sample_grid(np, ndimage, gradients[0], local_q)
    gy = _sample_grid(np, ndimage, gradients[1], local_q)
    gx = _sample_grid(np, ndimage, gradients[2], local_q)
    g = np.column_stack((sign_x * gx, sign_y * gy, sign_z * gz))
    norm_sq = np.einsum("ij,ij->i", g, g)
    good = violation & np.isfinite(norm_sq) & (norm_sq > 1e-8)
    target_d = np.clip(d, -float(band_mm), float(band_mm))
    correction = np.zeros_like(v)
    correction[good] = -((d[good] - target_d[good]) / norm_sq[good])[:, None] * g[good]
    v[good] += correction[good]
    return v, int(good.sum())


def _cbct_edge_snap(np, dicom_module, vertices, faces, *, band_mm: float, fraction: float, normals=None):
    """Move vertices toward a strong local radiographic edge within the mask band."""
    if getattr(dicom_module.RUNTIME, "volume", None) is None or len(vertices) == 0:
        return vertices, 0, 0
    if len(vertices) > MAX_CBCT_SNAP_VERTICES:
        return vertices, 0, 0
    v = np.asarray(vertices, dtype=np.float64).copy()
    normals = _vertex_normals(np, v, faces) if normals is None else np.asarray(normals, dtype=np.float64)
    nlen = np.linalg.norm(normals, axis=1)
    valid_normal = nlen > 0.5
    if not valid_normal.any():
        return v, 0, 0

    spacing_z, spacing_y, spacing_x = (float(x) for x in dicom_module.RUNTIME.spacing_zyx_mm)
    sign_x, sign_y, sign_z = dicom_module._dicom_display_signs_xyz()
    q = dicom_module._centered_xyz_to_global_voxel(v)
    dvox = np.empty_like(v)
    dvox[:, 0] = sign_z * normals[:, 2] / max(spacing_z, 1e-9)
    dvox[:, 1] = sign_y * normals[:, 1] / max(spacing_y, 1e-9)
    dvox[:, 2] = sign_x * normals[:, 0] / max(spacing_x, 1e-9)

    offsets = np.asarray((-1.0, -0.5, 0.0, 0.5, 1.0), dtype=np.float64) * float(band_mm)
    density = []
    for off in offsets:
        density.append(dicom_module._runtime_density_at_voxel_coordinates(q + dvox * float(off)))
    if any(item is None for item in density):
        return v, 0, 0
    values = np.column_stack(density)
    diffs = np.abs(np.diff(values, axis=1))
    best = np.argmax(diffs, axis=1)
    best_contrast = diffs[np.arange(len(v)), best]
    typical = np.median(diffs, axis=1)

    auto_low = float(getattr(dicom_module.RUNTIME, "auto_low", 0.0))
    auto_high = float(getattr(dicom_module.RUNTIME, "auto_high", 0.0))
    dynamic = abs(auto_high - auto_low)
    if dynamic <= 1e-6:
        dynamic = abs(float(getattr(dicom_module.RUNTIME, "density_max", 1.0)) -
                      float(getattr(dicom_module.RUNTIME, "density_min", 0.0)))
    min_contrast = max(1e-6, 0.025 * dynamic)
    reliable = (
        valid_normal
        & np.isfinite(best_contrast)
        & (best_contrast >= min_contrast)
        & (best_contrast >= 1.20 * np.maximum(typical, 1e-9))
    )
    mids = 0.5 * (offsets[:-1] + offsets[1:])
    chosen = mids[best]
    move_mm = np.zeros(len(v), dtype=np.float64)
    move_mm[reliable] = float(fraction) * chosen[reliable]
    v[reliable] += normals[reliable] * move_mm[reliable, None]
    return v, int(reliable.sum()), int((best_contrast >= min_contrast).sum())


def _volume_guard(np, source_vertices, refined_vertices, faces, *, min_ratio: float, max_ratio: float):
    source_volume = _mesh_volume(np, source_vertices, faces)
    if source_volume <= 1e-9 or len(source_vertices) != len(refined_vertices):
        current = _mesh_volume(np, refined_vertices, faces)
        ratio = current / source_volume if source_volume > 1e-9 else 1.0
        return refined_vertices, ratio, False
    refined = np.asarray(refined_vertices, dtype=np.float64)
    source = np.asarray(source_vertices, dtype=np.float64)
    current = _mesh_volume(np, refined, faces)
    ratio = current / source_volume
    if min_ratio <= ratio <= max_ratio:
        return refined, float(ratio), False
    # Blend back toward the segmentation source until volume is inside the
    # clinical guard.  This is intentionally conservative and deterministic.
    weight = 0.5
    best = source.copy()
    best_ratio = 1.0
    for _ in range(10):
        candidate = source + weight * (refined - source)
        candidate_ratio = _mesh_volume(np, candidate, faces) / source_volume
        if min_ratio <= candidate_ratio <= max_ratio:
            best = candidate
            best_ratio = candidate_ratio
            break
        weight *= 0.5
    return best, float(best_ratio), True


def refine_segmented_surface(
    context,
    vertices_xyz,
    faces,
    *,
    mask=None,
    origin_zyx=(0, 0, 0),
    kind: str = "TOOTH",
    label: int | None = None,
):
    """Responsive CBCT-constrained refinement without volumetric EDT bottlenecks.

    9.2.14 deliberately keeps all heavy 3-D distance transforms out of the
    automatic Blender timer path. The learned mask is still the hard anatomical
    cage, but it is sampled locally along mesh normals. Any numerical anomaly or
    excessive change falls back to the marching-cubes source geometry.
    """
    from . import dicom_module

    total_started = time.perf_counter()
    np = dicom_module.load_numpy()
    if np is None:
        return vertices_xyz, faces, {"status": "SKIPPED", "reason": "numpy_missing"}
    source_v = np.asarray(vertices_xyz, dtype=np.float64)
    source_f = np.asarray(faces, dtype=np.int32)
    if len(source_v) < 4 or len(source_f) < 4:
        return vertices_xyz, faces, {"status": "SKIPPED", "reason": "mesh_too_small"}
    profile = PROFILES.get(str(kind).upper(), PROFILES["BONE"])
    min_spacing = min(float(s) for s in dicom_module.RUNTIME.spacing_zyx_mm)
    band_mm = max(0.035, float(profile.max_band_voxels) * min_spacing)
    stats: dict[str, Any] = {
        "status": "OK",
        "kind": str(kind).upper(),
        "label": int(label) if label is not None else None,
        "source_vertices": int(len(source_v)),
        "source_faces": int(len(source_f)),
        "band_mm": float(band_mm),
        "mmg_used": False,
        "sdf_used": False,
        "mask_cage_used": False,
        "cbct_snapped": 0,
        "volume_guarded": False,
        "timings_s": {},
    }
    try:
        ndimage = dicom_module.load_scipy_ndimage()
        refined_v = source_v.copy()
        refined_f = source_f.copy()

        # MMG stays optional. It is never required for segmentation and is only
        # attempted on compact teeth because topology changes are costlier to QA.
        if profile.allow_mmg and ndimage is not None and mask is not None:
            t0 = time.perf_counter()
            refined_v, refined_f, mmg_stats = _try_mmg(
                np, refined_v, refined_f, min_spacing=min_spacing
            )
            stats["timings_s"]["mmg"] = float(time.perf_counter() - t0)
            stats["mmg"] = mmg_stats
            stats["mmg_used"] = bool(mmg_stats.get("used", False))

        t0 = time.perf_counter()
        if not stats["mmg_used"] or len(refined_v) <= MAX_TAUBIN_VERTICES:
            refined_v = _taubin(
                np, refined_v, refined_f,
                iterations=profile.taubin_iterations,
                lam=profile.taubin_lambda,
                mu=profile.taubin_mu,
            )
        stats["timings_s"]["taubin"] = float(time.perf_counter() - t0)

        # One normal build is reused for mask-cage + CBCT snap + final cage.
        # np.add.at over every triangle was previously repeated three times per
        # tooth and became visible at full dentition scale. Moves are sub-voxel,
        # so reusing the post-Taubin normals is both stable and substantially faster.
        t0 = time.perf_counter()
        shared_normals = _vertex_normals(np, refined_v, refined_f)
        stats["timings_s"]["normals_once"] = float(time.perf_counter() - t0)

        # Fast anatomical cage: sample only along surface normals instead of
        # constructing two whole-volume Euclidean distance transforms + gradient.
        if ndimage is not None and mask is not None:
            t0 = time.perf_counter()
            refined_v, projected, cage_stats = _project_to_mask_surface(
                np, ndimage, dicom_module, refined_v, refined_f, mask, origin_zyx,
                band_mm=band_mm, normals=shared_normals,
            )
            stats["timings_s"]["mask_cage_1"] = float(time.perf_counter() - t0)
            stats["mask_cage"] = cage_stats
            stats["mask_cage_used"] = bool(cage_stats.get("used", False))
            stats["mask_cage_projected"] = int(projected)
        elif len(refined_v) == len(source_v):
            refined_v, capped = _cap_displacement(np, refined_v, source_v, band_mm * 0.55)
            stats["source_displacement_capped"] = int(capped)

        # CBCT edge attraction is intentionally bounded. Very large surfaces skip
        # this optional correction instead of freezing Blender; the learned mask
        # cage remains authoritative and geometry is still valid.
        t0 = time.perf_counter()
        refined_v, snapped, candidates = _cbct_edge_snap(
            np, dicom_module, refined_v, refined_f,
            band_mm=band_mm, fraction=profile.cbct_snap_fraction, normals=shared_normals,
        )
        stats["timings_s"]["cbct_snap"] = float(time.perf_counter() - t0)
        stats["cbct_snapped"] = int(snapped)
        stats["cbct_edge_candidates"] = int(candidates)

        # Re-seat the post-CBCT geometry on the learned mask boundary. This makes
        # the CBCT a sub-voxel refiner, never a free sculptor.
        if ndimage is not None and mask is not None:
            t0 = time.perf_counter()
            refined_v, projected2, cage_stats2 = _project_to_mask_surface(
                np, ndimage, dicom_module, refined_v, refined_f, mask, origin_zyx,
                band_mm=band_mm, normals=shared_normals,
            )
            stats["timings_s"]["mask_cage_2"] = float(time.perf_counter() - t0)
            stats["mask_cage_projected_final"] = int(projected2)
            if cage_stats2.get("used"):
                stats["mask_cage_used"] = True

        if len(refined_v) == len(source_v):
            refined_v, capped = _cap_displacement(np, refined_v, source_v, band_mm)
            stats["source_displacement_capped_final"] = int(capped)

        t0 = time.perf_counter()
        if len(refined_v) == len(source_v) and len(refined_f) == len(source_f):
            refined_v, ratio, guarded = _volume_guard(
                np, source_v, refined_v, source_f,
                min_ratio=profile.min_volume_ratio,
                max_ratio=profile.max_volume_ratio,
            )
            stats["volume_ratio"] = float(ratio)
            stats["volume_guarded"] = bool(guarded)
        else:
            src_vol = _mesh_volume(np, source_v, source_f)
            out_vol = _mesh_volume(np, refined_v, refined_f)
            stats["volume_ratio"] = float(out_vol / src_vol) if src_vol > 1e-9 else 1.0
            if not (profile.min_volume_ratio <= stats["volume_ratio"] <= profile.max_volume_ratio):
                stats["status"] = "FALLBACK_SOURCE"
                stats["reason"] = "mmg_volume_outside_guard"
                stats["timings_s"]["volume_guard"] = float(time.perf_counter() - t0)
                stats["timings_s"]["total"] = float(time.perf_counter() - total_started)
                return source_v.astype(np.float32), source_f, stats
        stats["timings_s"]["volume_guard"] = float(time.perf_counter() - t0)

        if len(refined_v) == len(source_v):
            max_move = float(np.linalg.norm(refined_v - source_v, axis=1).max(initial=0.0))
            stats["max_move_mm"] = max_move
            if max_move > band_mm * 1.05:
                stats["status"] = "FALLBACK_SOURCE"
                stats["reason"] = "displacement_outside_guard"
                stats["timings_s"]["total"] = float(time.perf_counter() - total_started)
                return source_v.astype(np.float32), source_f, stats

        if not np.isfinite(refined_v).all():
            raise RuntimeError("coordenadas no finitas tras refinado")
        stats["output_vertices"] = int(len(refined_v))
        stats["output_faces"] = int(len(refined_f))
        backend = "MMG+CBCT" if stats["mmg_used"] else "DSG_TAUBIN+CBCT"
        if stats["mask_cage_used"]:
            backend += "+MASK_CAGE"
        stats["backend"] = backend
        stats["timings_s"]["total"] = float(time.perf_counter() - total_started)
        return np.asarray(refined_v, dtype=np.float32), np.asarray(refined_f, dtype=np.int32), stats
    except Exception as exc:
        stats["status"] = "FALLBACK_SOURCE"
        stats["reason"] = f"{type(exc).__name__}: {exc}"
        stats["timings_s"]["total"] = float(time.perf_counter() - total_started)
        return source_v.astype(np.float32), source_f, stats
