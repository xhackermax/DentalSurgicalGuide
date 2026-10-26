"""Recover removed functional Boolean volumes from saved clinical operations."""
import json,math
from pathlib import Path
import bpy
import numpy as np


def export_missing(context, guide, folder, export_mesh):
    from .. import guide_module as g
    from ..guide_export.mesh_checks import manifold_report
    props=context.scene.dsg_props
    before=set(bpy.data.objects)
    selected=list(context.selected_objects);active=context.view_layer.objects.active
    width=float(props.sleeve_lateral_opening_width)
    rows=[]
    def save(obj, kind, indices):
        if obj is None:raise ValueError('No se pudo reconstruir la protección de '+kind)
        vertices,faces=export_mesh(context,obj)
        if manifold_report(vertices,faces).blocking:
            raise ValueError('El volumen reconstruido no está cerrado: '+kind)
        path=Path(folder)/('functional_'+str(len(rows))+'.npz')
        np.savez(path,vertices=vertices,triangles=faces)
        rows.append({'label':'Saved '+kind+' '+str(len(rows)), 'file':str(path),
                     'closed':True,'kind':kind,'owner':guide.name,'channel_indices':indices,
                     'source':'RECONSTRUCTED_SAVED_BOOLEAN'})
    try:
        if str(guide.get('DSG_irrigation_resolution','')).upper()=='APPLIED':
            entries=g.sort_irrigation_entries_for_boolean(g.load_irrigation_path_entries(props))
            count=int(guide.get('DSG_irrigation_saved_path_count',guide.get('DSG_irrigation_cut_count',0)))
            if count<=0 or len(entries)!=count:
                raise ValueError('Faltan los trayectos guardados de irrigación para proteger sus luces.')
            links={}
            for entry in entries:
                if entry.get('link'):links.setdefault(int(entry.get('source_index',-1)),[]).append(entry)
            covered=set()
            for offset,entry in enumerate(entries):
                if entry.get('link'):continue
                index=int(entry.get('index',offset));linked=links.get(index,[])
                indices=[index]+[int(row['index']) for row in linked]
                name='DSG_OptimizerSavedLumen_'+str(index)
                obj=(g.build_irrigation_y_network_lumen_cutter(context,entry,linked,props,name=name)
                     if linked else g.build_irrigation_single_lumen_cutter(context,entry,props,name))
                save(obj,'IRRIGATION_LUMEN',indices);covered.update(indices)
            if covered!=set(range(count)):
                raise ValueError('La red guardada de irrigación está incompleta.')
            for offset,entry in enumerate(entries):
                effective,_=g._irrigation_entry_effective_props(props,entry)
                if str(effective.irr_sleeve_channel_mode).upper()=='DIRECT':continue
                obj=g.build_irrigation_c_only_cutter(context,entry['points'],effective,
                    implant_obj=entry.get('implant'),name='DSG_OptimizerSavedC_'+str(offset),extra_radius=.045)
                save(obj,'IRRIGATION_LUMEN',[int(entry.get('index',offset))])
        if guide.get('DSG_sleeve_lateral_opening',False):
            saved=json.loads(str(guide.get('DSG_sleeve_lateral_opening_records','[]')))
            if not saved:raise ValueError('Falta la posición guardada de la apertura lateral.')
            cutter,records,error=g._build_post_irrigation_lateral_opening_cutter(context,props,guide)
            actual={row['implant']:row for row in records}
            if error or len(actual)!=len(saved):raise ValueError('No se pudo reconstruir la apertura lateral guardada.')
            for row in saved:
                current=actual.get(row['implant'])
                if current is None or abs(math.remainder(float(current['angle_rad'])-float(row['angle_rad']),2*math.pi))>1e-6 or abs(float(current['width_mm'])-float(row['width_mm']))>1e-6:
                    raise ValueError('La apertura lateral actual no coincide con su posición guardada.')
            save(cutter,'LATERAL_OPENING',[])
        return rows
    finally:
        props.sleeve_lateral_opening_width=width
        for obj in set(bpy.data.objects)-before:
            mesh=obj.data if obj.type=='MESH' else None
            bpy.data.objects.remove(obj,do_unlink=True)
            if mesh is not None and mesh.users==0:bpy.data.meshes.remove(mesh)
        for obj in context.selected_objects:obj.select_set(False)
        for obj in selected:
            if obj.name in context.view_layer.objects and not obj.hide_get():obj.select_set(True)
        context.view_layer.objects.active=active
