"""Incremental physical checks in the isolated generative worker."""
import numpy as np

class NativeGrowthSession:
    def __init__(self,context,pieces,request):
        import bpy
        if not bpy.app.background:raise ValueError('GROWTH_SESSION_REQUIRES_ISOLATED_WORKER')
        from .organic_reinforcement import build_network
        from .generative_frame import case_geometry_fingerprint
        self.context=context;self.request=request;self.pieces=list(pieces);self.objects=build_network(context,pieces,request)
        self.hashes=[case_geometry_fingerprint(o)for o in self.objects]
    def accept(self,piece,previous):
        from .organic_reinforcement import build_network
        from .generative_frame import case_geometry_fingerprint
        if [p['route_id']for p in previous]!=[p['route_id']for p in self.pieces]:raise ValueError('GROWTH_PARENT_IDENTITIES_CHANGED')
        if any(not np.array_equal(a['points_mm'],b['points_mm'])for a,b in zip(previous,self.pieces)):raise ValueError('GROWTH_CHANGED_EXISTING_CURVE')
        if any(case_geometry_fingerprint(o)!=digest for o,digest in zip(self.objects,self.hashes)):raise ValueError('GROWTH_CHANGED_EXISTING_MESH')
        try:created=build_network(self.context,[piece],self.request,existing_pieces=previous,existing_objects=self.objects)
        except ValueError as exc:return {'valid':False,'reason':str(exc)}
        self.pieces=list(previous)+[piece];self.objects.extend(created);self.hashes.extend(case_geometry_fingerprint(o)for o in created)
        if self.request.get('web_diagnostics'):
            import json
            from pathlib import Path
            Path(self.request['job_dir'],'growth_partial.json').write_text(json.dumps(dict(render_pieces=self.pieces,web_growth_supports=self.request.get('web_growth_supports',[]))),encoding='utf-8')
        return {'valid':True}
    def close(self):
        from .. import guide_module as g
        for obj in reversed(self.objects):g.safe_remove_object_with_data(obj)
        self.objects=[]
    def __enter__(self):return self
    def __exit__(self,*exc):self.close()
