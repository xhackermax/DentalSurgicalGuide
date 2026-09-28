"""Internal low-poly glyph library for DSG engraving.

The end user does not need a font file or any external Python dependency.
Glyphs are stored as compact 5x7 bitmaps and converted directly into a
single Blender mesh through BMesh. Adjacent filled cells share topology, so
there are no Curve/FONT datablocks and no text-to-mesh operator calls.
"""

from __future__ import annotations

import logging as _dsg_logging
_DSG_LOG = _dsg_logging.getLogger(__name__)

import unicodedata

import bpy
import bmesh
from mathutils import Matrix, Vector

GLYPH_LIBRARY_VERSION = "DSG_BLOCK_5X7_V1"
BASE_ROWS = 7
DEFAULT_TRACKING_CELLS = 1.0

# 5x7 uppercase clinical block alphabet. A filled pixel is represented by #.
# Patterns are deliberately simple and robust for small 3D-printed engraving.
_GLYPHS = {
    "A": (".###.", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"),
    "B": ("####.", "#...#", "#...#", "####.", "#...#", "#...#", "####."),
    "C": (".####", "#....", "#....", "#....", "#....", "#....", ".####"),
    "D": ("####.", "#...#", "#...#", "#...#", "#...#", "#...#", "####."),
    "E": ("#####", "#....", "#....", "####.", "#....", "#....", "#####"),
    "F": ("#####", "#....", "#....", "####.", "#....", "#....", "#...."),
    "G": (".###.", "#...#", "#....", "#.###", "#...#", "#...#", ".###."),
    "H": ("#...#", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"),
    "I": ("#####", "..#..", "..#..", "..#..", "..#..", "..#..", "#####"),
    "J": ("..###", "...#.", "...#.", "...#.", "...#.", "#..#.", ".##.."),
    "K": ("#...#", "#..#.", "#.#..", "##...", "#.#..", "#..#.", "#...#"),
    "L": ("#....", "#....", "#....", "#....", "#....", "#....", "#####"),
    "M": ("#...#", "##.##", "#.#.#", "#.#.#", "#...#", "#...#", "#...#"),
    "N": ("#...#", "##..#", "#.#.#", "#..##", "#...#", "#...#", "#...#"),
    "O": (".###.", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."),
    "P": ("####.", "#...#", "#...#", "####.", "#....", "#....", "#...."),
    "Q": (".###.", "#...#", "#...#", "#...#", "#.#.#", "#..#.", ".##.#"),
    "R": ("####.", "#...#", "#...#", "####.", "#.#..", "#..#.", "#...#"),
    "S": (".####", "#....", "#....", ".###.", "....#", "....#", "####."),
    "T": ("#####", "..#..", "..#..", "..#..", "..#..", "..#..", "..#.."),
    "U": ("#...#", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."),
    "V": ("#...#", "#...#", "#...#", "#...#", ".#.#.", ".#.#.", "..#.."),
    "W": ("#...#", "#...#", "#...#", "#.#.#", "#.#.#", "##.##", "#...#"),
    "X": ("#...#", ".#.#.", "..#..", "..#..", "..#..", ".#.#.", "#...#"),
    "Y": ("#...#", ".#.#.", "..#..", "..#..", "..#..", "..#..", "..#.."),
    "Z": ("#####", "....#", "...#.", "..#..", ".#...", "#....", "#####"),

    "0": (".###.", "#...#", "#..##", "#.#.#", "##..#", "#...#", ".###."),
    "1": ("..#..", ".##..", "..#..", "..#..", "..#..", "..#..", ".###."),
    "2": (".###.", "#...#", "....#", "...#.", "..#..", ".#...", "#####"),
    "3": ("####.", "....#", "....#", ".###.", "....#", "....#", "####."),
    "4": ("...#.", "..##.", ".#.#.", "#..#.", "#####", "...#.", "...#."),
    "5": ("#####", "#....", "#....", "####.", "....#", "....#", "####."),
    "6": (".###.", "#....", "#....", "####.", "#...#", "#...#", ".###."),
    "7": ("#####", "....#", "...#.", "..#..", ".#...", ".#...", ".#..."),
    "8": (".###.", "#...#", "#...#", ".###.", "#...#", "#...#", ".###."),
    "9": (".###.", "#...#", "#...#", ".####", "....#", "....#", ".###."),

    "-": (".....", ".....", ".....", ".###.", ".....", ".....", "....."),
    ".": (".....", ".....", ".....", ".....", ".....", ".##..", ".##.."),
    "_": (".....", ".....", ".....", ".....", ".....", ".....", "#####"),
    "/": ("....#", "...#.", "...#.", "..#..", ".#...", ".#...", "#...."),
    ":": (".....", ".##..", ".##..", ".....", ".##..", ".##..", "....."),
    "#": (".#.#.", ".#.#.", "#####", ".#.#.", "#####", ".#.#.", ".#.#."),
}

_SPACE_ADVANCE = 3
_ACCENTED = {
    "Á": ("A", "ACUTE"), "É": ("E", "ACUTE"), "Í": ("I", "ACUTE"),
    "Ó": ("O", "ACUTE"), "Ú": ("U", "ACUTE"),
    "À": ("A", "GRAVE"), "È": ("E", "GRAVE"), "Ì": ("I", "GRAVE"),
    "Ò": ("O", "GRAVE"), "Ù": ("U", "GRAVE"),
    "Ü": ("U", "DIAERESIS"), "Ñ": ("N", "TILDE"), "Ç": ("C", "CEDILLA"),
}


def _base_cells(pattern):
    cells = set()
    for row_index, row in enumerate(pattern):
        y = BASE_ROWS - 1 - row_index
        for x, token in enumerate(row):
            if token == "#":
                cells.add((x, y))
    return cells


def _accent_cells(kind, width):
    mid = max(1, width // 2)
    if kind == "ACUTE":
        return {(max(0, mid - 1), BASE_ROWS), (mid, BASE_ROWS + 1)}
    if kind == "GRAVE":
        return {(mid, BASE_ROWS), (max(0, mid - 1), BASE_ROWS + 1)}
    if kind == "DIAERESIS":
        return {(max(0, mid - 1), BASE_ROWS + 1), (min(width - 1, mid + 1), BASE_ROWS + 1)}
    if kind == "TILDE":
        return {
            (max(0, mid - 2), BASE_ROWS),
            (max(0, mid - 1), BASE_ROWS + 1),
            (mid, BASE_ROWS + 1),
            (min(width - 1, mid + 1), BASE_ROWS),
        }
    if kind == "CEDILLA":
        return {(mid, -1), (max(0, mid - 1), -2)}
    return set()


def normalize_character(char):
    """Return a supported uppercase glyph key without external font fallback."""
    if not char:
        return " "
    char = char.upper()
    if char in _GLYPHS or char in _ACCENTED or char == " ":
        return char

    # Preserve useful clinical identifiers while avoiding unsupported glyphs.
    decomposed = unicodedata.normalize("NFKD", char)
    for token in decomposed:
        if token in _GLYPHS:
            return token
    return "-"


def glyph_cells(char):
    key = normalize_character(char)
    if key == " ":
        return set(), _SPACE_ADVANCE, key

    accent = None
    base_key = key
    if key in _ACCENTED:
        base_key, accent = _ACCENTED[key]

    pattern = _GLYPHS.get(base_key, _GLYPHS["-"])
    cells = _base_cells(pattern)
    width = max((len(row) for row in pattern), default=5)
    if accent:
        cells.update(_accent_cells(accent, width))

    if not cells:
        return set(), max(1, width), key

    min_x = min(x for x, _y in cells)
    max_x = max(x for x, _y in cells)
    shifted = {(x - min_x, y) for x, y in cells}
    return shifted, (max_x - min_x + 1), key


def prepare_text(text):
    """Normalize a clinical identifier and report substitutions."""
    source = str(text or "").replace("\n", " ").replace("\r", " ")
    normalized = []
    substitutions = []
    for char in source:
        key = normalize_character(char)
        normalized.append(key)
        if key != char.upper():
            substitutions.append((char, key))
    return "".join(normalized), substitutions


def _collect_text_cells(text, tracking_cells=DEFAULT_TRACKING_CELLS):
    prepared, substitutions = prepare_text(text)
    all_cells = set()
    cursor = 0.0
    placements = []

    for char in prepared:
        cells, width, key = glyph_cells(char)
        x_offset = int(round(cursor))
        for x, y in cells:
            all_cells.add((x + x_offset, y))
        placements.append((key, x_offset, width))
        cursor += float(width) + float(tracking_cells)

    if placements:
        cursor -= float(tracking_cells)
    return all_cells, max(0.0, cursor), prepared, substitutions


def create_glyph_mesh_object(
    context,
    name,
    body,
    size,
    extrude,
    matrix_world=None,
    tracking_cells=DEFAULT_TRACKING_CELLS,
):
    """Create a low-poly, internally generated engraving mesh.

    ``size`` is the height of the seven-row capital body in Blender units.
    Accents may extend slightly above this nominal height. ``extrude`` may be
    zero for a planar preview or positive for a solid Boolean cutter.
    """
    cells, advance, prepared, substitutions = _collect_text_cells(
        body, tracking_cells=tracking_cells)
    if not cells:
        return None

    scale = max(0.01, float(size)) / float(BASE_ROWS)
    depth = max(0.0, float(extrude))

    min_x = min(x for x, _y in cells)
    max_x = max(x for x, _y in cells) + 1
    min_y = min(y for _x, y in cells)
    max_y = max(y for _x, y in cells) + 1
    center_x = (float(min_x) + float(max_x)) * 0.5
    center_y = (float(min_y) + float(max_y)) * 0.5
    z_bottom = -depth * 0.5

    bm = bmesh.new()
    vertex_cache = {}

    def vertex_at(x, y):
        key = (int(x), int(y))
        vert = vertex_cache.get(key)
        if vert is None:
            vert = bm.verts.new(Vector((
                (float(x) - center_x) * scale,
                (float(y) - center_y) * scale,
                z_bottom,
            )))
            vertex_cache[key] = vert
        return vert

    for x, y in sorted(cells, key=lambda item: (item[1], item[0])):
        verts = (
            vertex_at(x, y),
            vertex_at(x + 1, y),
            vertex_at(x + 1, y + 1),
            vertex_at(x, y + 1),
        )
        try:
            bm.faces.new(verts)
        except ValueError:
            # A face can already exist only if malformed duplicate input slipped
            # through. The glyph library deliberately continues safely.
            pass

    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()

    if depth > 1e-8 and bm.faces:
        result = bmesh.ops.extrude_face_region(bm, geom=list(bm.faces))
        top_verts = [element for element in result.get("geom", ()) if isinstance(element, bmesh.types.BMVert)]
        if top_verts:
            bmesh.ops.translate(bm, verts=top_verts, vec=Vector((0.0, 0.0, depth)))
        try:
            bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)

    mesh = bpy.data.meshes.new(name + "_Mesh")
    bm.to_mesh(mesh)
    bm.free()
    try:
        mesh.validate(verbose=False, clean_customdata=False)
        mesh.update(calc_edges=True)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)

    obj = bpy.data.objects.new(name, mesh)
    obj.matrix_world = matrix_world.copy() if isinstance(matrix_world, Matrix) else Matrix.Identity(4)
    collection = getattr(context, "collection", None)
    if collection is None:
        collection = getattr(getattr(context, "scene", None), "collection", None)
    if collection is None:
        bpy.data.objects.remove(obj, do_unlink=True)
        return None
    collection.objects.link(obj)

    obj["DSG_glyph_library"] = GLYPH_LIBRARY_VERSION
    obj["DSG_glyph_text"] = prepared
    obj["DSG_glyph_cell_count"] = int(len(cells))
    obj["DSG_glyph_advance_cells"] = float(advance)
    obj["DSG_glyph_substitutions"] = int(len(substitutions))
    mesh["DSG_glyph_library"] = GLYPH_LIBRARY_VERSION
    return obj


def supported_characters():
    return tuple(sorted(set(_GLYPHS) | set(_ACCENTED) | {" "}))
