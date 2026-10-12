"""Blender-free executable regression harness for FEM replacement safety."""
import ast
import json
import math
import unittest
from pathlib import Path
from types import SimpleNamespace


class Obj(dict):
    def __init__(self, name, **metadata):
        super().__init__(metadata)
        self.name = name
        self.hide_render = False
        self._hidden = False
        self.show_in_front = True

    def hide_set(self, value):
        self._hidden = value

    def hide_get(self):
        return self._hidden


class Vec(tuple):
    def __new__(cls, coords):
        return tuple.__new__(cls, map(float, coords))

    def __sub__(self, other):
        return SimpleNamespace(length=math.dist(self, other))


class Fixture:
    def __init__(self):
        self.old = Obj('DSG_Reinforcement_00', DSG_reinforcement_confirmed=True,
                       DSG_reinforcement_fem_generated=True)
        self.guide = Obj('Guide', DSG_frame_fem_profile='OLD')
        self.objects = [self.old]
        self.props = SimpleNamespace(reinforcement_count=1, reinforcement_bevel_resolution=8,
                                     reinforcement_preview_obj=None, current_step=6)
        self.context = SimpleNamespace(scene=SimpleNamespace(dsg_props=self.props))
        self.failure = None
        self.creations = 0
        self.beams = [SimpleNamespace(i=0, j=1, active=True, render=True, virtual=False,
                                      radius_mm=1.0, tag='TEST') for _ in range(2)]
        self.nodes = [SimpleNamespace(xyz=[0, 0, 0]), SimpleNamespace(xyz=[2, 0, 0])]
        rows = [dict(length_mm=2.0, governing='bending', utilization=0.4) for _ in self.beams]
        self.result = SimpleNamespace(hard_safe=True, recommended=True,
                                      active_elements=[0, 1], final_bundle=SimpleNamespace(worst_results=rows))
        self.guide_module = SimpleNamespace(
            REINFORCEMENT_PREFIX='DSG_Reinforcement_', ROLE_REINFORCEMENT='REINFORCEMENT',
            STEP_REINFORCEMENT=6,
            get_pending_reinforcement_preview=lambda props: getattr(props, "pending_preview", None),
            get_active_guide_obj=lambda props: self.guide,
            _valid_obj=lambda obj: obj is self.guide or obj in self.objects,
            get_confirmed_reinforcement_curves=lambda: [x for x in self.objects
                 if x.name.startswith('DSG_Reinforcement_') and x.get('DSG_reinforcement_confirmed')],
            create_poly_curve_object=self.create_curve,
            register_dsg_object=self.register,
            safe_remove_object=lambda obj: self.objects.remove(obj),
            set_active=self.activate,
        )
        self.bpy = SimpleNamespace(context=self.context, data=SimpleNamespace(objects=self))
        self.fem = SimpleNamespace(optimize_reinforcement=self.optimize)

    def get(self, name):
        return next((obj for obj in self.objects if obj.name == name), None)

    def optimize(self, *_args, **_kwargs):
        if self.failure == 'solve':
            raise RuntimeError('singular FEM')
        return self.result

    def create_curve(self, _context, name, _points, **_kwargs):
        self.creations += 1
        if self.failure == 'second_curve' and self.creations == 2:
            raise RuntimeError('failed mesh builder')
        obj = Obj(name)
        self.objects.append(obj)
        return obj

    def register(self, obj, role, name, metadata):
        obj.update(metadata)
        return obj

    def activate(self, _context, obj):
        if self.failure == 'commit':
            raise RuntimeError('cannot activate candidate')

    def run(self):
        source = Path(__file__).resolve().parents[1] / 'frame_structural.py'
        tree = ast.parse(source.read_text('utf-8'))
        function = next(x for x in tree.body if isinstance(x, ast.FunctionDef)
                        and x.name == 'create_fem_reinforcements')
        module = ast.Module(body=[function], type_ignores=[])
        ast.fix_missing_locations(module)
        env = {
            'bpy': self.bpy, 'guide_module': self.guide_module, 'fem': self.fem,
            'Vector': Vec, 'json': json, 'FRAME_FEM_SCHEMA': 'test.schema',
            'FRAME_FEM_PROFILE': 'BALANCED',
            '_fem_build_model': lambda _context: dict(nodes=self.nodes, elements=self.beams,
                load_cases=[], monitor_nodes=[1], config=None, keep_out=None),
            '_fem_summary': lambda model, result: dict(hard_safe=result.hard_safe,
                recommended=result.recommended, max_utilization=0.4,
                sleeve_displacement_mm=0.01, volume_mm3=10, history=[]),
            '_DSG_LOG': SimpleNamespace(warning=lambda *_a, **_k: None),
        }
        exec(compile(module, str(source), 'exec'), env)
        return env['create_fem_reinforcements'](self.context)


class TransactionTests(unittest.TestCase):
    def test_direct_service_rejects_wrong_step_before_solver_or_mutation(self):
        f=Fixture()
        f.props.current_step=5
        with self.assertRaisesRegex(RuntimeError, "paso de refuerzos"):
            f.run()
        self.assertEqual(f.objects, [f.old])

    def test_direct_service_rejects_pending_manual_preview(self):
        f=Fixture()
        f.props.pending_preview=Obj("DSG_PENDING")
        with self.assertRaisesRegex(RuntimeError, "manual pendiente"):
            f.run()
        self.assertEqual(f.objects, [f.old])

    def test_solver_failure_does_not_erase_previous(self):
        f = Fixture()
        f.failure = 'solve'
        with self.assertRaisesRegex(RuntimeError, 'singular'):
            f.run()
        self.assertEqual(f.objects, [f.old])
        self.assertEqual(f.props.reinforcement_count, 1)

    def test_partial_curve_failure_rolls_back_temp_only(self):
        f = Fixture()
        f.failure = 'second_curve'
        with self.assertRaisesRegex(RuntimeError, 'mesh builder'):
            f.run()
        self.assertEqual(f.objects, [f.old])
        self.assertEqual(f.old.name, 'DSG_Reinforcement_00')
        self.assertTrue(f.old.get('DSG_reinforcement_confirmed'))

    def test_commit_failure_restores_original_names_visibility_and_metadata(self):
        f = Fixture()
        f.failure = 'commit'
        with self.assertRaisesRegex(RuntimeError, 'activate'):
            f.run()
        self.assertEqual(f.objects, [f.old])
        self.assertEqual(f.old.name, 'DSG_Reinforcement_00')
        self.assertFalse(f.old.hide_get())
        self.assertEqual(f.guide['DSG_frame_fem_profile'], 'OLD')
        self.assertEqual(f.props.reinforcement_count, 1)

    def test_success_swaps_set_without_duplicates(self):
        f = Fixture()
        f.run()
        self.assertNotIn(f.old, f.objects)
        self.assertEqual([x.name for x in f.objects],
                         ['DSG_Reinforcement_00', 'DSG_Reinforcement_01'])
        self.assertTrue(all(x['DSG_reinforcement_confirmed'] for x in f.objects))
        self.assertEqual(f.props.reinforcement_count, 2)
        self.assertEqual(f.guide['DSG_frame_fem_profile'], 'BALANCED')


if __name__ == '__main__':
    unittest.main()
