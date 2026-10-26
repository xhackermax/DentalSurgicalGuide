"""9.22.6: a nominal catalogue size is applied with DSG's own implant mesh."""
import sys
import bpy,numpy as np
from mathutils import Matrix
sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
import dsg
dsg.register()
from dsg import guide_module as g
from dsg.blender import implant_optimizer as opt,safety_volume as safety
from dsg.blender.safety_volume import _mesh_arrays
from dsg.implant_catalogues import rows,inside_envelope
try:
    assert g.deferred_post_register();safety.unregister()
    for o in list(bpy.context.scene.objects):bpy.data.objects.remove(o,do_unlink=True)
    scene=bpy.context.scene;props=scene.dsg_props
    mesh=g.make_embedded_implant_mesh(g.IMPLANT_PREFIX+'Nominal_Mesh',4.,10.)
    implant=bpy.data.objects.new(g.IMPLANT_PREFIX+'Nominal',mesh);scene.collection.objects.link(implant)
    implant.matrix_world=Matrix.Translation((1,2,3))@Matrix.Rotation(.3,4,'Y')
    implant['DSG_implant_diameter'],implant['DSG_implant_length']=4.,10.
    bpy.context.view_layer.update()
    v,_,_=_mesh_arrays(implant.data)
    assert inside_envelope(v,4.,10.),'DSG template is not inside its own nominal envelope'
    platform=g.get_implant_platform_center_world(props,implant).copy();axis=g.get_implant_axis_world(props,implant).copy()
    asset=next(r for r in rows('BTI_COREX') if r['diameter_mm']==3.75 and r['length_mm']==8.5)
    base=np.asarray(implant.matrix_world);matrix=base.copy();matrix[:3,3]=np.asarray(platform)-base[:3,:3]@np.asarray(asset['platform_local_mm'])
    opt.STATE['target']=implant.name
    opt._commit(bpy.context,{'matrix':matrix.tolist(),'asset':asset})
    assert abs(implant['DSG_implant_diameter']-3.75)<1e-6 and abs(implant['DSG_implant_length']-8.5)<1e-6
    assert (g.get_implant_platform_center_world(props,implant)-platform).length<1e-4,'Platform moved'
    assert (g.get_implant_axis_world(props,implant)-axis).length<1e-6,'Axis changed'
    assert implant['DSG_catalogue_asset_id']==asset['id'] and implant['DSG_optimizer_family']=='BTI CORE-X'
    assert 'DSG_catalogue_platform_local_mm' not in implant
    v,_,_=_mesh_arrays(implant.data);assert inside_envelope(v,3.75,8.5)
    assert opt.current_size(implant)=={'id':asset['id'],'diameter_mm':3.75,'length_mm':8.5}
    # A pose that does not match the validated one is rolled back to the previous size.
    implant.data.vertices[100].co.x+=.003 # Preserve an existing local mesh edit on failure.
    original_vertices,_,_=_mesh_arrays(implant.data)
    implant['DSG_catalogue_platform_local_mm']=[0.,0.,4.25]
    bad=matrix.copy();bad[0,3]+=1.
    other=next(r for r in rows('BTI_COREX') if r['diameter_mm']==4.25 and r['length_mm']==10)
    try:opt._commit(bpy.context,{'matrix':bad.tolist(),'asset':other});raise AssertionError('Mismatched pose applied')
    except RuntimeError:pass
    assert abs(implant['DSG_implant_diameter']-3.75)<1e-6 and abs(implant['DSG_implant_length']-8.5)<1e-6,'No rollback'
    assert implant['DSG_catalogue_asset_id']==asset['id']
    assert (g.get_implant_platform_center_world(props,implant)-platform).length<1e-4
    restored_vertices,_,_=_mesh_arrays(implant.data)
    assert np.array_equal(restored_vertices,original_vertices),'Rollback regenerated the mesh and lost the local edit'
    assert list(implant['DSG_catalogue_platform_local_mm'])==[0.,0.,4.25],'Rollback lost cervical reference metadata'
    controller=bpy.data.objects.new('DSG_CombinedController',None);scene.collection.objects.link(controller)
    controller['DSG_implant_emergence_controller']=True
    before=implant.matrix_world.copy();implant.parent=controller;implant.matrix_world=before
    scene.dsg_opt_depth_mm=1.5;scene.dsg_opt_shift_mm=1.
    translated=np.asarray(implant.matrix_world).copy();parameters=np.array([.5,0.,-1.5,0.,0.])
    target_platform=np.asarray(platform)+translated[:3,:3]@parameters[:3]
    translated[:3,3]=target_platform-translated[:3,:3]@np.asarray(other['platform_local_mm'])
    opt._commit(bpy.context,{'matrix':translated.tolist(),'asset':other,'parameters':parameters.tolist()})
    assert np.linalg.norm(np.asarray(g.get_implant_platform_center_world(props,implant))-target_platform)<1e-4
    assert (g.get_implant_axis_world(props,implant)-axis).length<1e-6
    print('NOMINAL_SIZE_APPLY_PASS: exact rollback, validated combined translation with controller, fixed axis',flush=True)
finally:dsg.unregister()
