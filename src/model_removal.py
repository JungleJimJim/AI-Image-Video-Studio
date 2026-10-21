"""Remove catalog weights while retaining dependencies used by other models."""
import hashlib
import json
from pathlib import Path

from common import comfy_root, manifest
from downloads import Cancelled
from packs import catalog, model_path


def all_models():
    return {'wan13':dict(name='NSFW Wan 1.3B · E14',files=manifest()['models'])} | catalog()


def removal_plan(root, key):
    models=all_models()
    if key not in models:
        raise ValueError('Choose a known model to uninstall.')
    ownership={}
    for model,pack in models.items():
        for f in pack['files']:
            ownership.setdefault((f['folder'],f['filename']),set()).add(model)
    # A complete or partial unique weight establishes that a model uses its shared files.
    active=set()
    for model,pack in models.items():
        if all(model_path(root,f).is_file() for f in pack['files']):
            active.add(model)
        for f in pack['files']:
            path=model_path(root,f)
            if ownership[(f['folder'],f['filename'])]=={model} and (path.exists() or path.with_name(path.name+'.part').exists()):
                active.add(model)
    active.discard(key)
    remove=[];keep=[]
    base=(comfy_root(root)/'models').resolve()
    for f in models[key]['files']:
        path=model_path(root,f)
        if path.is_symlink() or not path.resolve().is_relative_to(base):
            raise ValueError('A model path points outside the managed models folder. No files were removed.')
        users=sorted(ownership[(f['folder'],f['filename'])]&active)
        for candidate in (path,path.with_name(path.name+'.part')):
            if not candidate.is_file():continue
            if candidate.is_symlink() or not candidate.resolve().is_relative_to(base):
                raise ValueError('A model file redirects outside the managed folder.')
            stat=candidate.stat()
            item=dict(path=str(candidate),filename=candidate.name,bytes=stat.st_size,modified=stat.st_mtime_ns,
                      reclaimed_bytes=0 if stat.st_nlink>1 else stat.st_size)
            if users or f['folder'].startswith('loras'):
                keep.append(item|dict(used_by=[models[x]['name'] for x in users] or ['LoRA library (preserved)']))
            else:remove.append(item)
    payload=dict(model=key,name=models[key]['name'],files=remove,shared=keep,bytes=sum(x['reclaimed_bytes'] for x in remove))
    payload['ticket']=hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
    return payload


def uninstall(root,key,ticket,report,cancel):
    plan=removal_plan(root,key)
    if not isinstance(ticket,str) or ticket!=plan['ticket']:
        raise ValueError('The model files changed. Review the uninstall preview again.')
    for index,item in enumerate(plan['files']):
        if cancel.is_set():raise Cancelled('Model removal cancelled. Removed weights can be downloaded again.')
        Path(item['path']).unlink()
        report('Removed '+item['filename'],(index+1)/max(1,len(plan['files'])))
    report('Model uninstalled. Shared dependencies, LoRAs and library media were preserved.',1)
    return plan
