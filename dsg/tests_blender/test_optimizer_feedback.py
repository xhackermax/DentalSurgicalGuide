"""Use the real minimal-UI proxy: status/results must reach Blender's layout."""
import sys,bpy
sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
import dsg
dsg.register()
from dsg import guide_module as g
from dsg.blender import implant_optimizer as opt
class Layout:
 def __init__(self):self.labels=[];self.props=[];self.ops=[]
 def box(self):return self
 def row(self,**kwargs):return self
 def prop(self,owner,key,**kwargs):self.props.append(key)
 def label(self,**kwargs):self.labels.append(kwargs.get('text',''))
 def operator(self,key,**kwargs):self.ops.append(key);return self
 def separator(self):pass
try:
 assert g.deferred_post_register()
 scene=bpy.context.scene;scene.dsg_opt_open=True;scene.dsg_opt_details=False
 opt.STATE.update(message='88 % · Ø 5.5 × 8.5 mm · posición 1558/1620',process=object(),result=None)
 panel=Layout();opt.draw(g._DSGMinimalUILayout(panel,bpy.context),bpy.context)
 assert any('88 %' in x for x in panel.labels),panel.labels
 row={'asset':{'diameter_mm':3.75,'length_mm':8.},'parameters':[1.5,0,-.75,0,0],
  'evaluation':{'violations':[{'code':'WALL','label':'Hueco fuera del hueso nativo','actual':.315,'limit':0.}]}}
 opt.STATE.update(process=None,message='No se encontró una alternativa admisible.',result={
  'status':'NO_FEASIBLE','best':None,'closest':row,'evaluated':702,'elapsed_s':130.,'reasons':['Detalle de otro candidato']})
 panel=Layout();opt.draw(g._DSGMinimalUILayout(panel,bpy.context),bpy.context)
 assert any('702' in x for x in panel.labels),panel.labels
 assert any('3.75' in x for x in panel.labels),panel.labels
 assert any('Hueco fuera del hueso nativo' in x for x in panel.labels),panel.labels
 assert 'Detalle de otro candidato' not in panel.labels
 assert 'dsg.apply_implant_optimization' not in panel.ops
 opt.STATE['result']['status']='BONE_REVIEW';opt.STATE['message']='Requiere revisión ósea en CBCT.'
 panel=Layout();opt.draw(g._DSGMinimalUILayout(panel,bpy.context),bpy.context)
 assert any('Referencia para revisión ósea' in x for x in panel.labels),panel.labels
 assert any('Viabilidad clínica no determinada' in x for x in panel.labels),panel.labels
 assert not any('rechazada' in x or 'NO ADMISIBLE' in x for x in panel.labels),panel.labels
 assert 'dsg.apply_implant_optimization' not in panel.ops
 opt.STATE['result']['status']='NOMINAL_PROPOSAL';opt.STATE['result']['best']=row
 row['evaluation'].update(metric='SECTION_ENVELOPE_AND_NATIVE_SUPPORT_NOT_STABILITY',section_contact_fraction=.8)
 scene.dsg_opt_details=True
 panel=Layout();opt.draw(g._DSGMinimalUILayout(panel,bpy.context),bpy.context)
 assert not any('Con reserva local' in x for x in panel.labels),panel.labels
 assert any('Anillo en hueso segmentado' in x for x in panel.labels),panel.labels
 print('OPTIMIZER_FEEDBACK_PASS:real_minimal_proxy,progress,result_dimensions,rejection,no_apply',flush=True)
finally:
 opt.STATE.update(process=None,result=None,message='');dsg.unregister()
