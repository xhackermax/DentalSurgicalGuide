import sys,bpy,numpy as np
sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
from dsg import core,cbct_dental_module as dental,cbct_post_smoothing as post,surface_smoothing
bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2);tooth=bpy.context.object
original=tooth.data;cached=original.copy();tooth[post.ORIGINAL_MESH]=original;tooth[post.CACHED_MESH]=cached;tooth[post.SOURCE_HASH]=post.mesh_hash(original)
fresh=original.copy();tooth.data=fresh
calls=[];old=surface_smoothing.set_measured_display_smoothing
# Isolate state routing from the independently tested measured-smoothing filter.
def measured(obj,enabled,**kw):
 calls.append(enabled)
 mod=obj.modifiers.get(dental.ALIGNMENT_VISUAL_SMOOTH_MODIFIER)
 if enabled:
  if surface_smoothing.OFFSET_ATTRIBUTE not in obj.data.attributes:obj.data.attributes.new(surface_smoothing.OFFSET_ATTRIBUTE,'FLOAT_VECTOR','POINT')
  if mod is None:mod=obj.modifiers.new(dental.ALIGNMENT_VISUAL_SMOOTH_MODIFIER,'NODES')
 if mod:mod.show_viewport=enabled
surface_smoothing.set_measured_display_smoothing=measured
tooth['DSG_cbct_spacing_zyx_mm']=[.2,.2,.2]
try:
 bpy.context.scene[core.EXTRACTION_SMOOTHING_KEY]=True
 assert core.ensure_extraction_smoothing(bpy.context,tooth),'Stale cache suppressed current-mesh smoothing'
 assert calls==[True] and tooth.data==fresh
 bpy.context.scene[core.EXTRACTION_SMOOTHING_KEY]=False
 assert not core.ensure_extraction_smoothing(bpy.context,tooth)
 assert calls==[True,False] and tooth.data==fresh
 # Cached post-processing: OFF restores exact source; ON restores exact cache.
 tooth.data=cached
 assert core.tooth_smoothing_state(bpy.context,tooth)
 assert not core.ensure_extraction_smoothing(bpy.context,tooth)
 assert tooth.data==original
 bpy.context.scene[core.EXTRACTION_SMOOTHING_KEY]=True
 assert core.ensure_extraction_smoothing(bpy.context,tooth) and tooth.data==cached
 mesh,temporary=core._tooth_cutter_source(bpy.context,tooth)
 assert mesh==cached and not temporary,'Baked smoothing must not need an offset attribute'
 print('EXTRACTION_SMOOTHING_TOGGLE_PASS:stale_cache,current_mesh_on_off,baked_cache_on_off,cutter_source')
finally:surface_smoothing.set_measured_display_smoothing=old

# A preview error must restore both the button choice and actual tooth state.
from unittest.mock import patch
from types import SimpleNamespace
from dsg.blender import extraction_extension as ext,ios_tooth_edit
bpy.context.scene[core.EXTRACTION_SMOOTHING_KEY]=True
tooth.data=cached
failure=lambda context: (core.ensure_extraction_smoothing(context,tooth),(_ for _ in ()).throw(ValueError('Synthetic preview failure')))
with patch.object(core,'_immediate_extraction_fdis',return_value=[15]),patch.object(core,'_immediate_cbct_teeth',return_value=[tooth]),patch.object(ios_tooth_edit,'model',return_value=None),patch.object(ext,'preview',side_effect=failure):
 outcome=ext.DSG_OT_ToggleExtractionSmoothing.execute(SimpleNamespace(report=lambda *a:None),bpy.context)
 assert outcome=={'CANCELLED'} and core.extraction_smoothing_wanted(bpy.context.scene) and tooth.data==cached
print('TOGGLE_ERROR_ROLLBACK_PASS:choice_and_actual_mesh_restored')
