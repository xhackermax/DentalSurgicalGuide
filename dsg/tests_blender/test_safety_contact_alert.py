"""New neighbour contacts alert once, wait for native transforms, and clear."""
import sys
from types import SimpleNamespace
from unittest.mock import patch
import bpy
sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
import dsg
dsg.register()
from dsg.blender import safety_alerts as alerts
try:
    implant=bpy.data.objects.new('AlertImplant',None);bpy.context.scene.collection.objects.link(implant)
    tooth=bpy.data.objects.new('DSG_Tooth_FDI_16',None);bpy.context.scene.collection.objects.link(tooth)
    tooth['DSG_fdi_number']=16
    messages=[]
    context=SimpleNamespace(scene=bpy.context.scene,window=SimpleNamespace(modal_operators=[object()]))
    with patch.object(alerts,'_display_ready',return_value=True),patch.object(alerts,'_show_popup',side_effect=lambda ctx,name,contacts:messages.append((name,contacts))):
        alerts.observe(context,implant,[tooth.name])
        assert alerts._dispatch(context)==.1 and not messages,'Alert interrupted a modal transform'
        context.window.modal_operators=[]
        assert alerts._dispatch(context) is None and len(messages)==1
        assert alerts.contact_label(tooth.name)=='Diente FDI 16'
        alerts.observe(context,implant,[tooth.name]);alerts._dispatch(context)
        assert len(messages)==1,'Repeated the same contact popup'
        alerts.observe(context,implant,[]);alerts._dispatch(context)
        assert not alerts.active(context.scene)
        alerts.observe(context,implant,[tooth.name]);alerts._dispatch(context)
        assert len(messages)==2,'Re-entry into contact did not alert'
        alerts.observe(context,implant,[tooth.name,'Nerve']);alerts._dispatch(context)
        assert len(messages)==3,'New contact did not alert'
    print('SAFETY_CONTACT_ALERT_PASS: FDI label, modal deferral, one popup per contact, clear and re-entry',flush=True)
finally:
    dsg.unregister()
