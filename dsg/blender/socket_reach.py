"""Make the CBCT-tooth cutter reach the IOS surface so the socket opens.

CBCT segmentation often loses part of the crown (restorations, artefacts,
partial volume), so the segmented tooth can end below the surface of the
closed IOS.  Subtracting it then leaves a closed cavity *inside* the model,
which the post-Boolean cleanup removes as a floating island: no socket.

The coronal cross-section is extruded along the tooth's own axis until it
passes the local IOS surface. The root below the section is preserved.
"""
import numpy as np

BAND_MM = 2.0
CLEARANCE_MM = 1.0
MAX_EXTENSION_MM = 12.0


def _world(obj):
    mesh = obj.data
    co = np.empty(len(mesh.vertices) * 3)
    mesh.vertices.foreach_get('co', co)
    matrix = np.array(obj.matrix_world)
    return co.reshape(-1, 3) @ matrix[:3, :3].T + matrix[:3, 3]


def occlusal_direction(tooth, cutter_points):
    apical = tooth.get('DSG_tooth_axis_apical_world')
    if apical is not None:
        axis = -np.asarray(tuple(apical), dtype=float)
        if np.linalg.norm(axis) > 1e-9:
            return axis / np.linalg.norm(axis)
    centred = cutter_points - cutter_points.mean(axis=0)
    axis = np.linalg.svd(centred, full_matrices=False)[2][0]
    return axis / np.linalg.norm(axis)


def plan_extension(cutter_points, surface_points, occlusal, band=BAND_MM,
                   clearance=CLEARANCE_MM, limit=MAX_EXTENSION_MM):
    """Axial shift per cutter vertex (pure NumPy); zeros when already open."""
    t = cutter_points @ occlusal
    top = float(t.max())
    in_band = t > top - band
    centre = cutter_points[in_band].mean(axis=0)
    radial_of = lambda p: np.linalg.norm((p - centre) - np.outer((p - centre) @ occlusal, occlusal), axis=1)
    radius = float(radial_of(cutter_points[in_band]).max())
    s = surface_points @ occlusal
    column = (radial_of(surface_points) <= radius) & (s > top - 15.0) & (s < top + limit + 5.0)
    if not column.any():
        return np.zeros(len(t)), 0.0
    need = float(s[column].max()) - top + clearance
    if need <= 0.0:
        return np.zeros(len(t)), 0.0
    if need > limit:
        raise ValueError("La prolongación necesaria supera el límite; revisa el eje y la superficie IOS.")
    x = np.clip((t - (top - band)) / band, 0.0, 1.0)
    return need * x * x * (3.0 - 2.0 * x), need


def requirement(cutter, tooth, surface_obj):
    """Extension needed for the root section to come out of the IOS.

    Rays are cast along the tooth axis from inside the coronal section of
    the cutter (shrunk to 60 % so its border does not graze the walls); the
    extension needed is how far the section must rise to leave the model
    through the closure above it, plus clearance.  Earlier this took the
    highest IOS point in a wide column around the axis, which caught the
    cusps of the neighbouring teeth and asked for several millimetres too
    many (e.g. 6.5 mm instead of 1.7 mm).
    """
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    points = _world(cutter)
    occlusal = occlusal_direction(tooth, points)
    levels = points @ occlusal
    top = float(levels.max())
    section = points[levels > top - BAND_MM]
    centre = section.mean(axis=0)
    samples = centre + (section - centre) * 0.6
    samples = np.vstack([centre, samples[np.linspace(0, len(samples) - 1, min(len(samples), 32)).astype(int)]])
    matrix = surface_obj.matrix_world
    mesh = surface_obj.data
    tree = BVHTree.FromPolygons([matrix @ v.co for v in mesh.vertices],
                                [tuple(p.vertices) for p in mesh.polygons])
    direction = Vector(tuple(occlusal))
    need = 0.0
    for sample in samples:
        hit, normal, _face, distance = tree.ray_cast(Vector(tuple(sample)), direction)
        if hit is None or normal.dot(direction) <= 0.0:
            continue  # nothing above, or this point is already outside the model
        need = max(need, float(sample @ occlusal) + float(distance) - top + CLEARANCE_MM)
    if need > MAX_EXTENSION_MM:
        raise ValueError('La prolongación necesaria supera el límite; revisa el eje y la superficie IOS.')
    return max(0., need), occlusal, points


def extend(cutter, tooth, surface_obj, extension_mm=None, plan=None):
    """Extrude the coronal cross-section by the chosen physical length."""
    import bmesh
    from mathutils import Vector
    required,occlusal,points = plan if plan is not None else requirement(cutter,tooth,surface_obj)
    need = required if extension_mm is None else float(extension_mm)
    if need <= 0.0:
        return 0.0
    top = float((points @ occlusal).max())
    cut_level = top - BAND_MM
    centre = points.mean(axis=0)
    plane_world = centre + occlusal*(cut_level-float(centre @ occlusal))
    inverse = cutter.matrix_world.inverted()
    plane_local = inverse @ Vector(plane_world)
    normal_local = (cutter.matrix_world.to_3x3().transposed() @ Vector(occlusal)).normalized()
    direction_local = inverse.to_3x3() @ Vector(occlusal)
    bm = bmesh.new()
    try:
        bm.from_mesh(cutter.data)
        if not all(edge.is_manifold for edge in bm.edges):
            raise RuntimeError('El resto radicular debe ser cerrado antes de prolongarlo.')
        bmesh.ops.bisect_plane(bm, geom=list(bm.verts)+list(bm.edges)+list(bm.faces),
                              plane_co=plane_local, plane_no=normal_local,
                              clear_outer=True, clear_inner=False, dist=1e-6)
        boundary = [edge for edge in bm.edges if edge.is_boundary]
        if not boundary:
            raise RuntimeError('No se pudo obtener el contorno oclusal del resto radicular.')
        ring = {vertex for edge in boundary for vertex in edge.verts}
        if any(sum(edge in boundary for edge in vertex.link_edges) != 2 for vertex in ring):
            raise RuntimeError('El contorno radicular no forma un bucle de extrusión válido.')
        result = bmesh.ops.extrude_edge_only(bm,edges=boundary)
        new_vertices = [item for item in result['geom'] if isinstance(item,bmesh.types.BMVert)]
        bmesh.ops.translate(bm,verts=new_vertices,vec=direction_local*(BAND_MM+need))
        cap_edges = [edge for edge in bm.edges if edge.is_boundary]
        bmesh.ops.holes_fill(bm,edges=cap_edges,sides=0)
        bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces))
        if not all(edge.is_manifold for edge in bm.edges):
            raise RuntimeError('La prolongación oclusal no quedó cerrada y manifold.')
        bm.to_mesh(cutter.data)
        cutter.data.update()
        cutter['DSG_occlusal_extension_method'] = 'ROOT_CROSS_SECTION_EXTRUSION'
        cutter['DSG_occlusal_extension_mm'] = float(need)
        cutter['DSG_occlusal_extrusion_length_mm'] = float(BAND_MM+need)
        cutter['DSG_occlusal_boundary_vertices'] = len(ring)
    finally:
        bm.free()
    return need


def cutter_tree(cutter):
    """World-space BVH of a cutter, kept to verify the socket after cleanup."""
    from mathutils.bvhtree import BVHTree
    matrix = cutter.matrix_world
    mesh = cutter.data
    return BVHTree.FromPolygons([matrix @ v.co for v in mesh.vertices],
                                [tuple(p.vertices) for p in mesh.polygons])


ON_CUTTER_MM = 0.02


def verify_opening(surface_obj, tooth, tree):
    """Socket open to the outside and as deep as the tooth, without rays.

    After the island cleanup, any part of the model lying on the cutter
    surface is a socket wall connected to the outer shell (a cutter left
    inside makes a closed cavity, which the cleanup removes).  The deepest
    such point along the tooth axis must reach half the segmented length.
    Judged over the whole socket, so inclined canines (the axis line can
    leave the model) and multi-rooted molars (the axis line hits the
    furcation) pass, and a socket that already existed is recognised.
    """
    from mathutils import Vector
    points = _world(tooth)
    axis = occlusal_direction(tooth, points)
    levels = points @ axis
    top = float(levels.max())
    length = float(np.ptp(levels))
    centre = points.mean(axis=0)
    radial = lambda p: np.linalg.norm((p - centre) - np.outer((p - centre) @ axis, axis), axis=1)
    after = _world(surface_obj)
    near = (radial(after) <= float(radial(points).max()) + 1.0) & ((after @ axis) >= top - length - 2.0)
    walls = [p for p in after[near]
             if (hit := tree.find_nearest(Vector(p), ON_CUTTER_MM))[0] is not None]
    if not walls:
        raise RuntimeError('La extracción no abrió el alvéolo en el IOS.')
    depth = top - float((np.asarray(walls) @ axis).min())
    if depth < length * 0.5:
        raise RuntimeError('La extracción no abre el alvéolo hacia la raíz; el IOS no se confirma.')
    return {'verified': True, 'axial_depth_mm': round(depth, 3),
            'segmented_length_mm': round(length, 3), 'socket_wall_vertices': len(walls)}
