"""Blockout by extrusion along the view (ODC method)."""
import importlib.util
import pathlib
import unittest

import numpy as np

_PATH = pathlib.Path(__file__).resolve().parents[1] / 'blender' / 'blockout_sweep.py'
_SPEC = importlib.util.spec_from_file_location('blockout_sweep_under_test', _PATH)
sweep = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(sweep)


def strip(n=6):
    """A 2 x n quad strip in the XZ plane (a vertical wall facing +y... tilted up)."""
    xs = np.arange(n, dtype=float)
    lower = np.column_stack([xs, np.zeros(n), np.zeros(n)])
    upper = np.column_stack([xs, -0.2 * np.ones(n), np.ones(n)])
    world = np.vstack([lower, upper])
    tris = []
    for i in range(n - 1):
        a, b, c, d = i, i + 1, n + i + 1, n + i
        tris += [(a, b, c), (a, c, d)]
    return world, np.array(tris)


def closed(faces):
    edges = {}
    for face in faces:
        for a, b in zip(face, face[1:] + face[:1]):
            key = (min(a, b), max(a, b))
            edges[key] = edges.get(key, 0) + 1
    return all(count == 2 for count in edges.values())


class Sweep(unittest.TestCase):
    def test_extrusion_is_closed_and_reaches_the_hiding_surface(self):
        world, tris = strip()
        normals = np.tile([0.0, 0.3, 1.0], (len(world), 1))
        hits = np.full(len(world), 2.0)
        vertices, faces = sweep.build_sweep(world, tris, normals, hits, (0, 0, 1))
        self.assertTrue(closed([list(f) for f in faces]))
        n = len(vertices) // 2
        tops = vertices[n:, 2] - vertices[:n, 2]
        self.assertTrue(np.allclose(tops, 2.0 + sweep.MERGE_MM + sweep.FLOOR_MM))

    def test_visible_surface_is_not_extruded(self):
        world, tris = strip()
        normals = np.tile([0.0, 0.3, 1.0], (len(world), 1))
        hits = np.zeros(len(world))
        vertices, faces = sweep.build_sweep(world, tris, normals, hits, (0, 0, 1))
        self.assertEqual(len(faces), 0)

    def test_draft_opens_only_the_walls_without_curtains(self):
        world, tris = strip()
        normals = np.tile([0.0, 1.0, 0.0], (len(world), 1))
        hits = np.full(len(world), 20.0)                         # tall extrusion
        v0, f0 = sweep.build_sweep(world, tris, normals, hits, (0, 0, 1), draft_deg=0.0)
        v6, f6 = sweep.build_sweep(world, tris, normals, hits, (0, 0, 1), draft_deg=6.0)
        n = len(v0) // 2
        shift = np.linalg.norm((v6[n:] - v0[n:])[:, :2], axis=1)
        self.assertLessEqual(float(shift.max()), sweep.MAX_LEAN_MM + 1e-9)   # no curtains
        self.assertGreater(float(shift.max()), 0.1)                           # walls do open
        self.assertTrue(np.allclose(v6[:n], v0[:n]))                         # the floor never leans
        self.assertTrue(closed([list(x) for x in f6]))

    def test_survey_line_is_the_convex_silhouette(self):
        # ridge seen from the guide (-z): lower faces face the guide, upper turn away
        world = np.array([[0, 0, 0], [2, 0, 0], [0, 1, 1], [2, 1, 1], [0, 0, 2], [2, 0, 2]], float)
        tris = np.array([(0, 1, 3), (0, 3, 2), (2, 3, 5), (2, 5, 4)])
        down = np.array([0.0, 0.7071, -0.7071])
        up = np.array([0.0, 0.7071, 0.7071])
        normals = np.array([down, down, up, up])
        points, edges = sweep.survey_line(world, tris, normals, (0, 0, 1))
        self.assertEqual(len(edges), 1)
        self.assertTrue(np.allclose(points[:, 2], 1.0))       # on the ridge (max perimeter)
        # the crease at a gingival margin (back face below, front above) is not a survey line
        _p, crease = sweep.survey_line(world, tris, np.array([up, up, down, down]), (0, 0, 1))
        self.assertEqual(len(crease), 0)

if __name__ == '__main__':
    unittest.main()
