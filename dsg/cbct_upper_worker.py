"""Local cavity-only inference; does not rerun or replace dental anatomy."""
import json,sys
from pathlib import Path
from cbct_pipeline_worker import bootstrap,atomic_json

def main():
    req=json.loads(Path(sys.argv[-1]).read_text('utf-8'));bootstrap(req)
    out=Path(req['job_dir'])
    try:
        import numpy as np
        import nibabel as nib
        from totalsegmentator.config import set_config_key,setup_totalseg
        from dsg.cbct_upper_cavities import infer_nasal,infer_sinuses,CLASSES,prepare
        image=nib.load(req['input_nifti'])
        import torch
        device=req['device'] if torch.cuda.is_available() else 'cpu'
        setup_totalseg();set_config_key('send_usage_stats',False)
        atomic_json(out/'progress.json',{'message':'Identificando senos maxilares…'})
        raw,mapping=infer_sinuses(image,device)
        labels=np.zeros(raw.shape,dtype=np.uint8)
        for value,name in mapping.items():
            if name in CLASSES:labels[raw==int(value)]=CLASSES[name]
        atomic_json(out/'progress.json',{'message':'Identificando cavidad nasal…'})
        nasal,mapping=infer_nasal(image,device)
        if nasal.shape!=labels.shape:raise RuntimeError('Geometría nasal incompatible.')
        for value,name in mapping.items():
            if name in CLASSES and 'nasal' in name:labels[(nasal==int(value)) & (labels==0)]=CLASSES[name]
        spacing=tuple(float(x) for x in image.header.get_zooms()[:3][::-1])
        atomic_json(out/'progress.json',{'message':'Preparando superficies para revisar…'})
        surfaces=prepare(labels,spacing,labels.shape,out)
        atomic_json(out/'result.json',{'ok':True,'upper_cavities':surfaces})
    except Exception as exc:
        atomic_json(out/'result.json',{'ok':False,'error':str(exc)})
        raise

if __name__=='__main__':main()
