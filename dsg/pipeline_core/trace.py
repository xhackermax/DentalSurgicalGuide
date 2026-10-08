import json,os,time
from pathlib import Path
from .contracts import DSGError,SCHEMA_VERSION

class RunTrace:
    """Exportable record: no request paths, patient names, raw IDs or logs."""
    def __init__(self,path,run_id,version,engine,input_summary):
        self.path=Path(path);self.started=time.perf_counter();self.stage_started=self.started
        self.payload={'schema_version':SCHEMA_VERSION,'run_id':run_id,'dsg_version':version,
                      'engine':engine,'input':{k:v for k,v in input_summary.items() if k in ('dims_zyx','spacing_zyx','source_hash')},
                      'status':'RUNNING','stages':[],'fallbacks':[]}
        self.write()
    def write(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        temp=self.path.with_suffix('.tmp')
        temp.write_text(json.dumps(self.payload,ensure_ascii=False,indent=2),encoding='utf-8')
        os.replace(temp,self.path)
    def _close(self,status):
        if self.payload['stages'] and self.payload['stages'][-1]['status']=='RUNNING':
            self.payload['stages'][-1].update(status=status,duration_s=time.perf_counter()-self.stage_started)
    def start(self,name):
        if self.payload['stages'] and self.payload['stages'][-1]['name']==name:return
        self._close('OK');self.stage_started=time.perf_counter()
        self.payload['stages'].append({'name':name,'status':'RUNNING','duration_s':0.0});self.write()
    def fallback(self,source,target,reason_code):
        self.payload['fallbacks'].append({'source':source,'target':target,'reason_code':reason_code});self.write()
    def fail(self,error):
        self._close('ERROR');self.payload['status']='ERROR'
        self.payload['error']={'stage':error.stage,'reason':error.reason} if isinstance(error,DSGError) else {'stage':self.payload['stages'][-1]['name'] if self.payload['stages'] else 'bootstrap','reason':'Error inesperado','type':type(error).__name__}
        self.payload['elapsed_s']=time.perf_counter()-self.started;self.write()
    def finish(self):
        self._close('OK');self.payload['status']='OK';self.payload['elapsed_s']=time.perf_counter()-self.started;self.write()
