"""Catch ineffective display smoothing and unmeasured shrinkage of CBCT meshes."""
import sys
from pathlib import Path
import unittest
from unittest.mock import patch
import numpy as np
import bpy

parent = Path(sys.argv[sys.argv.index('--') + 1]).resolve()
sys.path.insert(0, str(parent))
import dsg
dsg.register()
vtk = dsg.dicom_module.load_vtk()

def enclosed_volume(v, f):
    pts = np.asarray(v, dtype=np.float64) - np.mean(v,axis=0)
    tri = pts[f]
    return abs(np.einsum('ij,ij->i',tri[:,0],np.cross(tri[:,1],tri[:,2])).sum()/6)

def mean_edge_normal_variation(v, f):
    tri = v[f]
    normal = np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0])
    normal /= np.maximum(np.linalg.norm(normal,axis=1)[:,None],1e-20)
    edges = np.sort(np.concatenate((f[:,(0,1)],f[:,(1,2)],f[:,(2,0)])),axis=1)
    face_ids = np.tile(np.arange(len(f)),3)
    order = np.lexsort((edges[:,1],edges[:,0]))
    edges, face_ids = edges[order],face_ids[order]
    pairs = np.where(np.all(edges[:-1]==edges[1:],axis=1))[0]
    return np.mean(1-np.einsum('ij,ij->i',normal[face_ids[pairs]],normal[face_ids[pairs+1]]))

class ConstrainedSurfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        coordinates = np.indices((36,36,36),dtype=np.float64)
        mask = ((coordinates-17.5)**2).sum(axis=0) < 13.3**2
        from dsg import cbct_surface_meshing
        surface = cbct_surface_meshing.extract_binary_surface(mask.astype(np.uint8), vtk_module=vtk)
        cls.vertices = np.asarray(surface.vertices_zyx,dtype=np.float64)*.2
        cls.faces = surface.faces
        # Model inference is coarser than the returned native label grid. This
        # reproduces the broad stair treads observed in the real dental meshes.
        coarse_coordinates=np.round(coordinates/2.5)*2.5
        coarse_mask=((coarse_coordinates-17.5)**2).sum(axis=0)<13.3**2
        coarse=cbct_surface_meshing.extract_binary_surface(coarse_mask.astype(np.uint8),vtk_module=vtk)
        cls.coarse_vertices=np.asarray(coarse.vertices_zyx,dtype=np.float64)*.2
        cls.coarse_faces=coarse.faces

    def smoother(self):
        try:
            from dsg import surface_smoothing
        except ImportError:
            self.fail('Missing constrained volume-preserving smoothing')
        return surface_smoothing

    def test_voxel_steps_improve_without_shrinkage_or_added_geometry(self):
        module = self.smoother()
        source = self.vertices.copy()
        faces = self.faces.copy()
        result, stats = module.smooth_surface_preserving_volume(source,faces,max_distance_mm=.1,vtk_module=vtk)
        np.testing.assert_array_equal(source,self.vertices)
        np.testing.assert_array_equal(faces,self.faces)
        self.assertEqual(result.shape,source.shape)
        self.assertGreater(np.mean(np.linalg.norm(result-source,axis=1)),.02)
        self.assertLessEqual(np.max(np.linalg.norm(result-source,axis=1)),.10001)
        self.assertAlmostEqual(enclosed_volume(result,faces)/enclosed_volume(source,faces),1,places=5)
        self.assertLess(mean_edge_normal_variation(result,faces), .75*mean_edge_normal_variation(source,faces))
        self.assertEqual(stats['status'],'READY')

    def test_open_mesh_is_rejected_instead_of_claiming_volume_preservation(self):
        module = self.smoother()
        with self.assertRaisesRegex(ValueError,'cerrada'):
            module.smooth_surface_preserving_volume(self.vertices,self.faces[:-1],max_distance_mm=.1,vtk_module=vtk)

    def test_new_button_produces_visible_measured_geometry_change(self):
        module = self.smoother()
        dental = dsg.cbct_dental_module
        mesh = bpy.data.meshes.new('VoxelSphereSource')
        mesh.from_pydata(self.coarse_vertices.tolist(), [], self.coarse_faces.tolist())
        obj = bpy.data.objects.new(dental.dental_assets.object_name(11,'TOOTH'),mesh)
        obj['DSG_fdi_number'] = 11
        obj['DSG_cbct_spacing_zyx_mm'] = [.2,.2,.2]
        bpy.context.scene.collection.objects.link(obj)
        spacing_before = dsg.dicom_module.RUNTIME.spacing_zyx_mm
        dsg.dicom_module.RUNTIME.spacing_zyx_mm = (.2,.2,.2)
        try:
            before = np.array([tuple(v.co) for v in mesh.vertices])
            self.assertEqual(bpy.ops.dsg.cbct_toggle_surface_smoothing(),{'FINISHED'})
            bpy.context.view_layer.update()
            evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
            display_mesh = evaluated.to_mesh()
            try:
                display = np.array([tuple(v.co) for v in display_mesh.vertices])
            finally:
                evaluated.to_mesh_clear()
            self.assertGreater(np.mean(np.linalg.norm(display-before,axis=1)),.02,'Button changes a flag but does not actually smooth the surface')
            self.assertLess(mean_edge_normal_variation(display,self.coarse_faces),.15*mean_edge_normal_variation(before,self.coarse_faces),'The evaluated surface still retains excessive voxel steps')
            self.assertLessEqual(np.max(np.linalg.norm(display-before,axis=1)),.25001)
            self.assertAlmostEqual(enclosed_volume(display,self.coarse_faces)/enclosed_volume(before,self.coarse_faces),1,places=5)
            np.testing.assert_array_equal(np.array([tuple(v.co) for v in mesh.vertices]),before)
            self.assertEqual(bpy.ops.dsg.cbct_toggle_surface_smoothing(),{'FINISHED'})
            bpy.context.view_layer.update()
            evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
            display_mesh = evaluated.to_mesh()
            try:
                np.testing.assert_array_equal(np.array([tuple(v.co) for v in display_mesh.vertices]),before)
            finally:
                evaluated.to_mesh_clear()
            with patch.object(module,'smooth_surface_preserving_volume',side_effect=AssertionError('Cached toggle must not recompute the surface')):
                self.assertEqual(bpy.ops.dsg.cbct_toggle_surface_smoothing(),{'FINISHED'})
            self.assertTrue(obj.modifiers[dental.ALIGNMENT_VISUAL_SMOOTH_MODIFIER].show_viewport)
        finally:
            dsg.dicom_module.RUNTIME.spacing_zyx_mm = spacing_before
            bpy.context.scene.pop('DSG_cbct_visual_smoothing_enabled',None)
            bpy.data.objects.remove(obj,do_unlink=True)
            bpy.data.meshes.remove(mesh)

    def test_each_disconnected_anatomical_component_retains_its_own_volume(self):
        module = self.smoother()
        count = len(self.vertices)
        vertices = np.concatenate((self.vertices,self.vertices*.6+np.array((15,0,0))))
        faces = np.concatenate((self.faces,self.faces+count))
        result,stats = module.smooth_surface_preserving_volume(vertices,faces,max_distance_mm=.1,vtk_module=vtk)
        self.assertEqual(stats['component_count'],2)
        for before,after in ((vertices[:count],result[:count]),(vertices[count:],result[count:])):
            self.assertAlmostEqual(enclosed_volume(after,self.faces)/enclosed_volume(before,self.faces),1,places=5)

    def test_surface_button_includes_segmented_jaws_but_excludes_the_canal(self):
        dental=dsg.cbct_dental_module
        created=[]
        try:
            for label in ('MAXILLA','MANDIBLE','CANAL'):
                mesh=bpy.data.meshes.new('Scope_'+label)
                mesh.from_pydata(self.vertices.tolist(),[],self.faces.tolist())
                obj=bpy.data.objects.new('Scope_'+label,mesh)
                bpy.context.scene.collection.objects.link(obj)
                if label!='CANAL':
                    obj['DSG_bone_arch']=label
                else:
                    obj['DSG_semantic_class']=55
                created.append(obj)
            targets=dental.visual_smoothing_objects(bpy.context)
            self.assertIn(created[0],targets)
            self.assertIn(created[1],targets)
            self.assertNotIn(created[2],targets)
        finally:
            for obj in created:
                mesh=obj.data
                bpy.data.objects.remove(obj,do_unlink=True)
                bpy.data.meshes.remove(mesh)

try:
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ConstrainedSurfaceTests))
    if not result.wasSuccessful():
        raise AssertionError('Constrained smoothing regressions')
finally:
    dsg.unregister()
