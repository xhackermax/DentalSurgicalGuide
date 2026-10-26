"""Real secondary-hole closure must resolve its own progress dependency."""
import sys
from unittest.mock import patch
import bpy,bmesh
sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
import dsg
dsg.register()
from dsg import guide_module as g
from dsg.blender import progress_overlay as progress

def source():
    vertices=[(-2,-2,0),(2,-2,0),(2,2,0),(-2,2,0),(-1,-1,2),(1,-1,2),(1,1,2),(-1,1,2)]
    faces=[(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]
    mesh=bpy.data.meshes.new('OpenDentalTest');mesh.from_pydata(vertices,[],faces);mesh.update()
    obj=bpy.data.objects.new('OpenDentalTest',mesh);bpy.context.scene.collection.objects.link(obj)
    return obj

try:
    assert '_progress' not in g.__dict__,'Test must not rely on a leaked global progress module'
    obj=source();original=[tuple(v.co) for v in obj.data.vertices]
    with patch.object(progress,'step',wraps=progress.step) as steps:
        repaired,diagnostics=g.close_scanned_model_holes(bpy.context,obj)
        assert any(call.args[0]==92 for call in steps.call_args_list)
    assert diagnostics['filled_count']==1 and repaired!=obj,diagnostics
    assert [tuple(v.co) for v in obj.data.vertices]==original
    assert g._verify_original_anatomy_vertices_unchanged(obj,repaired)[0]
    bm=bmesh.new();bm.from_mesh(repaired.data)
    assert len([e for e in bm.edges if len(e.link_faces)==1])==4,'Basal opening changed'
    bm.free()
    reviewed,diagnostics=g.close_scanned_model_holes(bpy.context,repaired)
    assert reviewed==repaired and diagnostics['filled_count']==0
    # Volumetric route uses the same missing dependency; isolate its early progress
    # before expensive remeshing (not a claim of whole volumetric geometry validation).
    class ReachedDirection(RuntimeError):pass
    with patch.object(g,'_automatic_base_direction',side_effect=ReachedDirection),patch.object(progress,'step') as steps:
        try:g._close_open_model_volumetric(bpy.context,obj);raise AssertionError('Sentinel not reached')
        except ReachedDirection:pass
        assert steps.call_args_list[0].args[0]==42
    assert [tuple(v.co) for v in obj.data.vertices]==original
    print('SCAN_HOLES_PROGRESS_PASS:real_hole_fill,base_preserved,anatomy_preserved,no_holes,volumetric_dependency',flush=True)
finally:dsg.unregister()
