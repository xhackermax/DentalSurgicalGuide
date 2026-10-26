import sys,bpy
from unittest.mock import patch
sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
import dsg;dsg.register()
from dsg import guide_module as g
from dsg.blender import implant_optimizer as opt
scene=bpy.context.scene;p=scene.dsg_props
for o in list(scene.objects):bpy.data.objects.remove(o,do_unlink=True)
def cube(name):
 bpy.ops.mesh.primitive_cube_add();o=bpy.context.object;o.name=name;o[g.SUITE_ROLE_KEY]=g.ROLE_GUIDE;return o
current=cube(g.GUIDE_NAME);p.guide_obj=current
current['DSG_obsolete_hidden']=True;current['DSG_archive_reason']='final_cut_commit'
archived=cube('DSG_ArchivedGuide_Test');archived['DSG_obsolete_hidden']=True
source=cube('DSG_SourceFrame_Hidden');source['DSG_hidden_source']=True
with patch.object(g,'repair_core_object_pointers'):
 assert g.get_guide_visibility_objects(p)==[current],'Visibility control includes archived guides'
 assert not current.get('DSG_obsolete_hidden'),'Current guide inherited archive metadata'
 g._hide_retained_guide_sources()
 assert archived.hide_viewport and source.hide_viewport and not current.hide_viewport
 g._workflow_show_objects([archived,current])
 assert archived.hide_viewport,'Stage restore showed an archived guide'
# A proposal belongs to the step in which it was requested, not later stages.
preview=cube(opt.PREVIEW);opt.STATE.update(scene=scene,workflow_step=g.STEP_IMPLANT,preview_step=g.STEP_IMPLANT)
p['current_step']=g.STEP_NAME
assert opt.watch_preview() is None and bpy.data.objects.get(opt.PREVIEW) is None,'Proposal survived leaving implant placement'
print('EXCLUSIVE_VISIBILITY_PASS:only_current_guide,hidden_backups,stage_restore_no_archive,preview_removed_after_step_change')
