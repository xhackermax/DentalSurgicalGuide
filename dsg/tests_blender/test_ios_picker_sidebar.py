"""Sidebar controls must remain usable while the three-point picker is active."""
import sys,unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock,patch
import bpy
sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
import dsg
dsg.register()
from dsg import alignment_module as a,core

class PickerSidebarTests(unittest.TestCase):
 def setUp(self):
  self.objects=[]
  for name in ('TestIOSLower','TestIOSUpper','TestCBCT'):
   mesh=bpy.data.meshes.new(name);mesh.from_pydata([(0,0,0),(1,0,0),(0,1,0)],[],[(0,1,2)])
   obj=bpy.data.objects.new(name,mesh);bpy.context.scene.collection.objects.link(obj);self.objects.append(obj)
  self.p=bpy.context.scene.dicp_props;self.p.icp_source_obj=self.objects[0];self.p.icp_target_obj=self.objects[2]
  self.window=NS(x=0,y=0,width=800,height=600,type='WINDOW')
  self.sidebar=NS(x=600,y=0,width=200,height=600,type='UI')
  self.fake=NS(_source=self.objects[0],_target=self.objects[2],_phase='source',_region=self.window,_area=NS(regions=[self.window,self.sidebar]),_raycast=Mock(return_value=None),report=Mock(),_restore_scene_state=Mock(),as_pointer=lambda: 123456789)
 def tearDown(self):
  self.p.icp_source_obj=None;self.p.icp_target_obj=None
  for obj in self.objects:
   mesh=obj.data;bpy.data.objects.remove(obj,do_unlink=True);bpy.data.meshes.remove(mesh)
 def event(self,x=700,y=200):return NS(type='LEFTMOUSE',value='PRESS',mouse_x=x,mouse_y=y,ctrl=False)
 def test_sidebar_click_reaches_ios_controls(self):
  with patch.object(a.lifecycle,'is_active',return_value=True):
   self.assertEqual(a.DICP_OT_PickLandmarks.modal(self.fake,bpy.context,self.event()),{'PASS_THROUGH'})
  self.fake._raycast.assert_not_called()
 def test_source_change_stops_old_picker_without_casting(self):
  self.p.icp_source_obj=self.objects[1]
  with patch.object(a.lifecycle,'is_active',return_value=True),patch.object(core,'_show_only_alignment_ios') as show:
   self.assertEqual(a.DICP_OT_PickLandmarks.modal(self.fake,bpy.context,self.event(100)),{'CANCELLED'})
   show.assert_called_once()
  self.fake._restore_scene_state.assert_called_once();self.fake._raycast.assert_not_called()
 def test_viewport_still_raycast_picks(self):
  with patch.object(a.lifecycle,'is_active',return_value=True):
   self.assertEqual(a.DICP_OT_PickLandmarks.modal(self.fake,bpy.context,self.event(100)),{'RUNNING_MODAL'})
  self.fake._raycast.assert_called_once()

suite=unittest.defaultTestLoader.loadTestsFromTestCase(PickerSidebarTests)
r=unittest.TextTestRunner(verbosity=2).run(suite)
if not r.wasSuccessful():raise SystemExit(1)
print('IOS_PICKER_SIDEBAR_PASS')
