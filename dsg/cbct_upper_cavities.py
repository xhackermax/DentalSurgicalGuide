"""Named upper air-cavity classes; no generic air-threshold anatomy guessing."""
import numpy as np

CLASSES={'left_maxillary_sinus':56,'right_maxillary_sinus':57,'nasal_cavity_left':58,'nasal_cavity_right':59}


def merge_nasal(primary,nasal,class_map):
    if nasal.shape!=primary.shape or nasal.dtype.kind not in 'iu':raise ValueError('Cavidad nasal incompatible con el CBCT.')
    result=primary.copy()
    background=primary==0
    for raw_id,name in class_map.items():
        if name in CLASSES and 'nasal_cavity' in name:
            result[(nasal==int(raw_id)) & background]=CLASSES[name]
    return result


def _infer_task(image,task,device='gpu',task_id=None):
    import torch
    from totalsegmentator.config import setup_nnunet,setup_totalseg,set_config_key
    from totalsegmentator.libs import download_pretrained_weights
    from totalsegmentator.nnunet import nnUNet_predict_image
    from totalsegmentator.python_api import get_task_config
    from totalsegmentator.registry import get_task_classes,requires_license
    if requires_license(task):raise RuntimeError('El modelo nasal requiere una licencia que debe configurarse.')
    setup_nnunet();setup_totalseg();set_config_key('send_usage_stats',False)
    config=get_task_config(task,quiet=True)
    model_id=config['task_id'] if task_id is None else task_id
    download_pretrained_weights(model_id)
    resolved=torch.device('cuda:0') if device=='gpu' else torch.device('cpu')
    seg,_,_=nnUNet_predict_image(image,None,model_id,model=config['model'],folds=config['folds'],trainer=config['trainer'],tta=False,
        multilabel_image=True,resample=config['resample'],crop=None,crop_path=None,task_name=task,output_task_name=task,nora_tag='None',
        preview=False,save_binary=False,nr_threads_resampling=1,nr_threads_saving=1,crop_addon=[0,0,0],output_type='nifti',statistics=False,
        quiet=True,verbose=False,test=0,skip_saving=True,device=resolved,resampling_order=1,save_lowres=False,use_cropped_logits_resampling=False)
    raw=np.asanyarray(seg.dataobj)
    if raw.shape!=image.shape:raise RuntimeError('El modelo nasal devolvió otra geometría de volumen.')
    return np.ascontiguousarray(np.transpose(raw,(2,1,0))),get_task_classes(task)


def infer_nasal(image,device='gpu'):
    return _infer_task(image,'head_glands_cavities',device)


def infer_sinuses(image,device='gpu'):
    # Official teeth stage 113 predicts jaws/canal/sinuses; stage 115 is tooth-only.
    return _infer_task(image,'teeth',device,task_id=113)


def prepare(labels,spacing,dims,out_dir):
    from .cbct_pipeline_tasks import compact_mask_for_classes,_save_binary_surface
    results={}
    for name,label in CLASSES.items():
        mask,origin=compact_mask_for_classes(labels,(label,))
        if mask is None:
            results[name]={'status':'NOT_FOUND','label':label}
            continue
        surface=_save_binary_surface(mask,origin,spacing,dims,out_dir,name,label)
        boundary=any(origin[axis]==0 or origin[axis]+mask.shape[axis]==dims[axis] for axis in range(3))
        results[name]={'status':'CANDIDATE' if surface else 'NOT_FOUND','label':label,'touches_fov_boundary':boundary,**(surface or {})}
    return results
