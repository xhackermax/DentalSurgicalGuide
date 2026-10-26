import sys,bpy,numpy as np
sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
from dsg.blender.optimizer_snapshot_geometry import mesh_arrays,display_signature
from dsg import cbct_dental_module as dental,surface_smoothing as smooth
bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2);obj=bpy.context.object
base=np.asarray([v.co[:] for v in obj.data.vertices],float)
offset=obj.data.attributes.new(smooth.OFFSET_ATTRIBUTE,'FLOAT_VECTOR','POINT');delta=base*.025;offset.data.foreach_get('vector',np.empty(len(base)*3,np.float32));offset.data.foreach_set('vector',delta.ravel())
mod=obj.modifiers.new(dental.ALIGNMENT_VISUAL_SMOOTH_MODIFIER,'NODES');mod.node_group=smooth._display_nodes(bpy)
obj.data.update();bpy.context.view_layer.update()
v,f=mesh_arrays(obj);assert np.allclose(v,base+delta)
evaluated=obj.evaluated_get(bpy.context.evaluated_depsgraph_get());view=evaluated.to_mesh()
try:assert np.allclose(v,np.asarray([p.co[:] for p in view.vertices]))
finally:evaluated.to_mesh_clear()
original_data=obj.data;before=display_signature(obj)
obj.hide_set(True);obj.hide_viewport=True
hidden,_=mesh_arrays(obj);assert np.array_equal(hidden,v) and obj.hide_get() and obj.hide_viewport
assert obj.data==original_data and np.allclose(np.asarray([p.co[:] for p in obj.data.vertices]),base)
delta*=.5;offset.data.foreach_set('vector',delta.ravel());assert before!=display_signature(obj),'Offset edits did not invalidate proposal'
mod.show_viewport=False;raw,_=mesh_arrays(obj);assert np.allclose(raw,base)
mod.show_viewport=True
other=obj.modifiers.new('Unreviewed','BEVEL')
try:mesh_arrays(obj);raise AssertionError('Unreviewed modifier accepted')
except ValueError:pass
obj.modifiers.remove(other)
group=mod.node_group
attribute=next(n for n in group.nodes if n.bl_idname=='GeometryNodeInputNamedAttribute')
position=next(n for n in group.nodes if n.bl_idname=='GeometryNodeSetPosition')
assert attribute.outputs['Attribute'].type=='VECTOR'
mod.node_group.nodes.new('GeometryNodeSetPosition')
try:mesh_arrays(obj);raise AssertionError('Altered graph accepted')
except ValueError:pass
print('SMOOTHED_SNAPSHOT_PASS:visible_geometry,hidden_geometry,original_unchanged,offset_fingerprint,unknown_modifier_blocked,altered_graph_blocked')
