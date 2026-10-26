"""Organic tooth surfaces from the segmentation model's own grid.

TotalSegmentator predicts teeth at 0.5 mm and the label map is enlarged to the
CBCT grid with nearest neighbour, so every step is ~3 native voxels. Smoothing
the native mesh cannot remove steps that large. Instead this module:

1. recovers the model grid exactly from the enlarged label map (verified, not assumed);
2. runs ITK's AntiAliasBinaryImageFilter (Whitaker 2000) per tooth on that grid,
   so the surface may move at most about one model voxel from the prediction;
3. shares one boundary with every neighbouring tooth (no gaps, no overlaps);
4. matches the label's voxel volume by shifting only the free, non-contact surface;
5. extracts the zero level with marching cubes on a 2x finer grid.

No bpy here: it runs in the isolated smoothing worker and in tests.
"""
from __future__ import annotations

import time

import numpy as np

ALGORITHM = 'ITK_ANTIALIAS_MODEL_GRID_1'
MODEL_SPACING_MM = 0.5
TOOTH_LABEL_MAX = 52  # 53-55 are jaws and canals: bone is not a tooth contact.
AA_MAX_RMS = 0.01
AA_ITERATIONS = 200
SUBDIVISIONS = 2
MAX_LEVEL_SHIFT = 0.5           # model voxels
MAX_DISTANCE_TO_SOURCE_MM = 1.0
MAX_VOLUME_ERROR_PERCENT = 3.0


def model_grid(shape_zyx, spacing_zyx, model_spacing=MODEL_SPACING_MM):
    """Model grid size and native->model index ratio per axis (corner aligned)."""
    shape = np.asarray(shape_zyx, dtype=np.int64)
    spacing = np.asarray(spacing_zyx, dtype=np.float64)
    low = np.maximum(np.rint(shape * spacing / float(model_spacing)).astype(np.int64), 2)
    ratio = (low - 1) / np.maximum(shape - 1, 1)
    return low, ratio


def block_agreement(labels, lo, hi, ratio):
    """Fraction of native neighbours inside one model cell that share a label.

    1.0 means the label map really is a nearest-neighbour enlargement of the
    model grid, so recovering that grid loses nothing.
    """
    sub = np.asarray(labels[lo[0]:hi[0], lo[1]:hi[1], lo[2]:hi[2]])
    agree = total = 0
    for axis in range(3):
        cell = np.rint(np.arange(lo[axis], hi[axis]) * ratio[axis]).astype(np.int64)
        same = cell[1:] == cell[:-1]
        a = [slice(None)] * 3; b = [slice(None)] * 3
        a[axis] = slice(0, -1); b[axis] = slice(1, None)
        shape = [1, 1, 1]; shape[axis] = -1
        sel = np.broadcast_to(same.reshape(shape), sub[tuple(a)].shape)
        eq = sub[tuple(a)] == sub[tuple(b)]
        agree += int(eq[sel].sum()); total += int(sel.sum())
    return agree / total if total else 0.0


def _bbox(labels, label):
    from scipy import ndimage
    found = ndimage.find_objects((np.asarray(labels) == label).astype(np.uint8), max_label=1)
    return found[0] if found and found[0] is not None else None


def _antialias(sitk, binary):
    image = sitk.GetImageFromArray(np.ascontiguousarray(binary, dtype=np.uint8))
    out = sitk.AntiAliasBinary(image, AA_MAX_RMS, AA_ITERATIONS)
    return sitk.GetArrayFromImage(out).astype(np.float32)  # >0 inside


def _components(faces, count):
    from scipy import sparse
    from scipy.sparse import csgraph
    edges = np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]]])
    graph = sparse.coo_matrix((np.ones(len(edges)), (edges[:, 0], edges[:, 1])), shape=(count, count))
    return csgraph.connected_components(graph, directed=False)[1]


def _compact(vertices, faces):
    used, inverse = np.unique(faces, return_inverse=True)
    return vertices[used], inverse.reshape(-1, 3).astype(np.int64)


def _signed_volume(vertices, faces):
    centred = vertices - vertices.mean(axis=0)
    tri = centred[faces]
    return float(np.einsum('ij,ij->i', tri[:, 0], np.cross(tri[:, 1], tri[:, 2])).sum() / 6.0)


def _closed(faces):
    edges = np.sort(np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]]), axis=1)
    _, counts = np.unique(edges, axis=0, return_counts=True)
    return bool(np.all(counts == 2)), int(np.count_nonzero(counts != 2))


def _model_region(labels, ratio, low_shape, start, stop):
    """Model-grid labels for cells [start, stop); cells outside the grid are background."""
    shape = np.asarray(labels.shape)
    out = np.zeros(tuple(int(b - a) for a, b in zip(start, stop)), dtype=labels.dtype)
    inner_lo = np.maximum(start, 0); inner_hi = np.minimum(stop, low_shape)
    if np.any(inner_hi <= inner_lo):
        return out
    idx = [np.clip(np.rint(np.arange(inner_lo[a], inner_hi[a]) / ratio[a]).astype(np.int64), 0, shape[a] - 1)
           for a in range(3)]
    out[tuple(slice(int(inner_lo[a] - start[a]), int(inner_hi[a] - start[a])) for a in range(3))] = \
        np.asarray(labels[np.ix_(*idx)])
    return out


class NeighbourCache:
    """Anti-aliased level set of each tooth, computed once per batch.

    Every tooth needs the level sets of its neighbours for the shared contact;
    caching them in model-grid coordinates turns ~7 filter runs per tooth into one.
    """

    def __init__(self, labels, ratio, low_shape, boxes, sitk):
        self.labels, self.ratio, self.low_shape, self.boxes, self.sitk = labels, ratio, low_shape, boxes, sitk
        self.fields = {}

    def _field(self, label):
        if label not in self.fields:
            box = self.boxes[label - 1]
            start = np.floor(np.array([b.start for b in box]) * self.ratio).astype(np.int64) - 3
            stop = np.ceil(np.array([b.stop - 1 for b in box]) * self.ratio).astype(np.int64) + 4
            region = _model_region(self.labels, self.ratio, self.low_shape, start, stop)
            from scipy import ndimage
            # Same filled shell each tooth builds for itself, so both sides of a contact agree.
            self.fields[label] = (start, _antialias(self.sitk, ndimage.binary_fill_holes(region == label)))
        return self.fields[label]

    def sample(self, label, start, shape):
        origin, field = self._field(label)
        out = np.full(shape, float(field.min()), dtype=np.float32)  # far outside
        a = np.maximum(start, origin); b = np.minimum(start + np.asarray(shape), origin + np.asarray(field.shape))
        if np.all(b > a):
            out[tuple(slice(int(a[i] - start[i]), int(b[i] - start[i])) for i in range(3))] = \
                field[tuple(slice(int(a[i] - origin[i]), int(b[i] - origin[i])) for i in range(3))]
        return out


def organic_tooth(labels, label, spacing_zyx, *, to_display, source_xyz=None, sitk=None, boxes=None, cache=None, surface_kind="TOOTH"):
    """Return (xyz vertices, faces, stats) for one tooth label.

    ``to_display(native_zyx) -> xyz`` maps native voxel indices to the object's
    coordinates, exactly as the faithful (CLEAN) path does. ``source_xyz`` are
    the current mesh vertices; output parts far from them (islands the review
    already discarded) are dropped, and the distance to them is a safety gate.
    """
    from scipy import ndimage
    from scipy.spatial import cKDTree
    from skimage import measure
    if sitk is None:
        import SimpleITK as sitk  # noqa: N813 - library name
    if surface_kind not in {"TOOTH", "ARCH"}:
        raise ValueError("Tipo de superficie desconocido")
    arch = surface_kind == "ARCH"
    started = time.perf_counter()
    labels = np.asarray(labels)
    spacing = np.asarray(spacing_zyx, dtype=np.float64)
    shape = np.asarray(labels.shape)
    low_shape, ratio = model_grid(shape, spacing)
    model_spacing = spacing / ratio
    box = boxes[label - 1] if boxes is not None and label <= len(boxes) else _bbox(labels, label)
    if box is None:
        raise ValueError('Label sin vóxeles')
    margin_native = np.ceil(4 / ratio).astype(np.int64)
    lo = np.maximum([s.start for s in box] - margin_native, 0)
    hi = np.minimum([s.stop for s in box] + margin_native, shape)
    agreement = block_agreement(labels, lo, hi, ratio)
    if agreement < 0.995:
        raise ValueError(f'La máscara no procede de la rejilla del modelo ({agreement:.3f})')

    # Model grid: sample each model cell at its corner-aligned native voxel.
    # Two background cells beyond the margin keep the level set closed at the crop border.
    ulo = np.floor(lo * ratio).astype(np.int64) - 4
    uhi = np.ceil((hi - 1) * ratio).astype(np.int64) + 5
    low = _model_region(labels, ratio, low_shape, ulo, uhi)

    # Keep only the parts of the label the review kept in the current mesh
    # (e.g. a primary component chosen over a detached fragment).
    tooth = low == label
    parts, count = ndimage.label(tooth, structure=np.ones((3, 3, 3), dtype=bool))
    if source_xyz is not None and len(source_xyz) and count > 1 and not arch:
        tree = cKDTree(np.asarray(source_xyz, dtype=np.float64))
        shell = tooth & ~ndimage.binary_erosion(tooth)
        kept = []
        for part in range(1, count + 1):
            cells = np.argwhere(shell & (parts == part))
            xyz_cells = np.asarray(to_display((cells + ulo) / ratio), dtype=np.float64)
            # Model voxels are ~0.5 mm: a shell cell of a kept part lies within one cell of the mesh.
            if np.mean(tree.query(xyz_cells, distance_upper_bound=1.0)[0] <= 1.0) >= 0.3:
                kept.append(part)
        if not kept:
            raise ValueError('La segmentación no coincide con el diente actual')
        tooth = np.isin(parts, kept)
    dropped_parts = int(count - (len(np.unique(parts[tooth])) if count else 0))
    # The model labels pulp separately; the displayed tooth is its outer shell
    # (the surface pipeline already drops inner shells), so fill closed cavities.
    if not arch:
        tooth = ndimage.binary_fill_holes(tooth)

    own = _antialias(sitk, tooth)
    neighbours = [] if arch else [int(v) for v in np.unique(low) if 0 < v <= TOOTH_LABEL_MAX and v != label]
    contact = np.full(own.shape, np.inf, dtype=np.float32)
    for other in neighbours:
        # Both teeth use the same midline (L_k - L_j) / 2 = 0, so they cannot overlap.
        theirs = (cache.sample(other, ulo, own.shape) if cache is not None
                  else _antialias(sitk, low == other))
        contact = np.minimum(contact, 0.5 * (own - theirs))

    # Evaluate on an exact 1/SUBDIVISIONS model-voxel lattice.
    if arch:
        # Same exact half-voxel lattice without allocating three full coordinate grids.
        fine_shape = (np.asarray(own.shape) - 1) * SUBDIVISIONS + 1
        own_f = ndimage.zoom(own, fine_shape / np.asarray(own.shape), order=3, mode='nearest')
        contact_f = np.full(own_f.shape, np.inf, dtype=np.float32)
    else:
        axes = [np.arange(0, n - 1 + 1e-9, 1.0 / SUBDIVISIONS) for n in own.shape]
        grid = np.meshgrid(*axes, indexing='ij')
        own_f = ndimage.map_coordinates(own, grid, order=3, mode='nearest')
        contact_f = (ndimage.map_coordinates(np.where(np.isfinite(contact), contact, 8.0), grid, order=3, mode='nearest')
                     if neighbours else np.full(own_f.shape, np.inf, dtype=np.float32))
    cell_volume = float(np.prod(model_spacing / SUBDIVISIONS))
    # Reference volume: native voxels whose model cell belongs to the kept, filled tooth.
    # The native map is a nearest-neighbour copy of the model grid, so this is exact.
    cells = [np.rint(np.arange(lo[a], hi[a]) * ratio[a]).astype(np.int64) - ulo[a] for a in range(3)]
    target = float(np.count_nonzero(tooth[np.ix_(*cells)]) * np.prod(spacing))

    def field(shift):
        return np.minimum(own_f - shift, contact_f)

    # Only the free surface moves to match volume: contacts stay on the shared midline.
    low_shift, high_shift = -MAX_LEVEL_SHIFT, MAX_LEVEL_SHIFT
    for _ in range(24):
        shift = 0.5 * (low_shift + high_shift)
        if np.count_nonzero(field(shift) > 0) * cell_volume > target:
            low_shift = shift
        else:
            high_shift = shift
    shift = 0.5 * (low_shift + high_shift)
    values = field(shift)
    values[[0, -1], :, :] = values[:, [0, -1], :] = values[:, :, [0, -1]] = -1.0
    vertices, faces, _normals, _values = measure.marching_cubes(values, 0.0, method='lewiner')
    faces = faces.astype(np.int64)
    native_zyx = (vertices / SUBDIVISIONS + ulo) / ratio
    xyz = np.asarray(to_display(native_zyx), dtype=np.float64)

    # Keep outer shells only: an inner shell (pulp chamber) is oriented against the
    # outer one, so its signed volume has the opposite sign. Smoothing can also pinch
    # off a few cells; drop parts under 1% of the triangles.
    comp = _components(faces, len(xyz))
    face_comp = comp[faces[:, 0]]
    sizes = np.bincount(face_comp, minlength=comp.max() + 1)
    volumes = np.array([_signed_volume(xyz, faces[face_comp == c]) if sizes[c] else 0.0
                        for c in range(len(sizes))])
    outer_sign = np.sign(volumes[int(np.argmax(sizes))])
    keep_ids = np.flatnonzero((sizes >= 0.01 * sizes.max()) & (np.sign(volumes) == outer_sign))
    inner_shells = int(np.count_nonzero((sizes > 0) & (np.sign(volumes) != outer_sign)))
    if arch:
        # Bone/arch cavities and small disconnected anatomical parts are retained.
        keep_ids = np.flatnonzero(sizes > 0)
        inner_shells = 0
    xyz, faces = _compact(xyz, faces[np.isin(face_comp, keep_ids)])

    closed, bad_edges = _closed(faces)
    if not closed:
        raise ValueError(f'Malla abierta ({bad_edges} aristas)')
    volume = _signed_volume(xyz, faces)
    if volume < 0:
        faces = faces[:, ::-1]; volume = -volume
    stats = {
        'algorithm': ALGORITHM, 'surface_kind': surface_kind, 'model_grid': low_shape.tolist(), 'model_spacing_mm': model_spacing.tolist(),
        'model_grid_agreement': agreement, 'neighbour_teeth': neighbours, 'level_shift_model_voxels': shift,
        'voxel_count_volume_mm3': target, 'final_volume_mm3': volume,
        'delta_vs_voxel_count_percent': 100.0 * (volume / target - 1.0) if target else None,
        'kept_components': len(keep_ids), 'inner_shells_removed': inner_shells, 'dropped_label_parts': dropped_parts, 'final_vertex_count': int(len(xyz)), 'closed': closed,
    }
    if source_xyz is not None and len(source_xyz):
        distance = cKDTree(np.asarray(source_xyz, dtype=np.float64)).query(xyz)[0]
        stats.update(distance_to_source_p95_mm=float(np.percentile(distance, 95)),
                     distance_to_source_max_mm=float(distance.max()))
        if distance.max() > MAX_DISTANCE_TO_SOURCE_MM:
            raise ValueError(f'Se aleja {distance.max():.2f} mm de la segmentación')
    if stats['delta_vs_voxel_count_percent'] is not None and abs(stats['delta_vs_voxel_count_percent']) > MAX_VOLUME_ERROR_PERCENT:
        raise ValueError(f"Cambio de volumen {stats['delta_vs_voxel_count_percent']:.1f} %")
    stats['elapsed_s'] = time.perf_counter() - started
    return xyz.astype(np.float32), faces.astype(np.int32), stats
