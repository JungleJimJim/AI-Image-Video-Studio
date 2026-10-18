"""Recording imports and serial, cancellable talking-avatar generation."""
import base64
import binascii
import json
import math
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import time

from common import CREATE_NO_WINDOW, atomic_json, comfy_root, resource, runtime_python
from downloads import Cancelled
from media_storage import media_folder
import avatar_runtime

MODELS=('avatar_echo','avatar_soulx','avatar_longcat','avatar_infinite','avatar_musetalk')


def validate_options(raw):
    if not isinstance(raw,dict):raise ValueError('Choose avatar settings.')
    model=raw.get('model','avatar_echo')
    if model not in MODELS:raise ValueError('Choose a talking-avatar model.')
    kind=raw.get('source_type','image')
    if kind not in ('image','video') or kind=='video' and model not in ('avatar_infinite','avatar_musetalk'):
        raise ValueError('Choose a portrait, or use InfiniteTalk / MuseTalk for video dubbing.')
    result=dict(model=model,source_type=kind,memory='low',fps=25)
    for key in ('source_id','audio_id'):
        value=raw.get(key)
        if not isinstance(value,str) or not value or len(value)>100:
            raise ValueError('Choose a Library source and import a voice recording first.')
        result[key]=value
    for key, default, low, high, whole in [('width',512,256,768,True),('height',512,256,768,True),
            ('duration',5,.5,30,False),('audio_start',0,0,600,False),('steps',40 if model=='avatar_infinite' else 8,4,80,True)]:
        try:
            value=float(raw.get(key,default))
            if not math.isfinite(value) or not low<=value<=high or whole and not value.is_integer():raise ValueError()
            result[key]=int(value) if whole else value
        except (TypeError,ValueError,OverflowError):raise ValueError('Choose a valid '+key.replace('_',' ')+'.') from None
    if result['width']%64 or result['height']%64:
        raise ValueError('Avatar width and height must be multiples of 64.')
    seed=str(raw.get('seed','')).strip()
    try:
        result['seed']=secrets.randbelow(2**53) if seed in ('','-1') else int(seed)
        if not 0<=result['seed']<2**53:raise ValueError()
    except (ValueError,OverflowError):raise ValueError('Choose a seed from 0 to 9007199254740991, or leave it empty.') from None
    randomize=raw.get('randomize_seed',True)
    if not isinstance(randomize,bool):raise ValueError('Choose whether to prepare a new seed for each job.')
    result['randomize_seed']=randomize
    prompt=raw.get('prompt','A person speaking naturally, looking at the camera.')
    if not isinstance(prompt,str) or len(prompt)>10000:raise ValueError('Use a description under 10,000 characters.')
    result['prompt']=prompt.strip() or 'A person speaking naturally, looking at the camera.'
    variant=raw.get('variant','lite')
    if variant not in ('lite','pro'):raise ValueError('Choose SoulX Lite or Pro.')
    result['variant']=variant
    if model=='avatar_soulx':result['steps']=4
    elif model=='avatar_longcat':result['steps']=8
    elif model=='avatar_musetalk':result.pop('steps',None)
    if model!='avatar_soulx':result.pop('variant',None)
    adapters=raw.get('loras',[])
    if adapters and model not in ('avatar_longcat','avatar_infinite'):
        raise ValueError('This avatar workflow does not apply extra LoRAs. Use LongCat or InfiniteTalk for avatar LoRA generation.')
    result['loras']=adapters
    return result


def import_audio(root, raw, report, cancel):
    encoded=raw.get('data','')
    if not isinstance(encoded,str) or not encoded.startswith('data:') or ';base64,' not in encoded:
        raise ValueError('Choose a WAV, MP3, M4A, OGG or FLAC recording.')
    try:content=base64.b64decode(encoded.split(';base64,',1)[1],validate=True)
    except (ValueError,binascii.Error):raise ValueError('The voice recording upload is invalid.') from None
    if not 0<len(content)<=60*1024**2:raise ValueError('Choose a recording no larger than 60 MB.')
    identifier=secrets.token_hex(12)
    folder=media_folder(root,'image').parent/'Audio';folder.mkdir(parents=True,exist_ok=True)
    source=folder/(identifier+'.upload');target=folder/(identifier+'.wav')
    source.write_bytes(content)
    try:
        if cancel.is_set():raise Cancelled('Audio import cancelled.')
        report('Checking the voice recording. No voice service is contacted…',None)
        command=[str(runtime_python(root)),'-s',str(resource('avatar_audio_worker.py'))]
        result=subprocess.run(command,input=json.dumps(dict(source=str(source),target=str(target))),
            capture_output=True,text=True,timeout=120,creationflags=CREATE_NO_WINDOW,
            env={**os.environ,'SSLKEYLOGFILE':''})
        if result.returncode:raise ValueError('The recording could not be decoded. '+result.stderr.strip().splitlines()[-1][:500])
        if cancel.is_set():
            target.unlink(missing_ok=True);raise Cancelled('Audio import cancelled.')
        info=json.loads(result.stdout)
        return dict(id=identifier,path=str(target),name=Path(str(raw.get('name','Voice recording'))).name[:200],
                    created=time.strftime('%Y-%m-%d %H:%M'),**info)
    finally:
        source.unlink(missing_ok=True)


def generate(root, source, audio, options, output, report, cancel):
    if not avatar_runtime.ready(root):raise ValueError('Install the selected avatar model and runtime in Models first.')
    folder=Path(root)/'avatar-jobs'/secrets.token_hex(12);folder.mkdir(parents=True)
    result_file=folder/'result.json'
    request=folder/'job.json'
    payload=dict(root=str(Path(root).resolve()),source=source,audio=audio,options=json.loads(json.dumps(options)),
                 destination=str(folder/'output.mp4'),result=str(result_file))
    if options['loras']:
        from loras import lora_folder
        for item in payload['options']['loras']:
            item['path']=str(comfy_root(root)/'models/loras'/item['name'])
    atomic_json(request,payload)
    log=Path(root)/'logs/avatar.log';log.parent.mkdir(exist_ok=True)
    started=time.monotonic()
    try:
        with log.open('w',encoding='utf-8') as stream:
            process=subprocess.Popen([str(runtime_python(root)),'-s',str(resource('avatar_worker.py')),
                '--root',str(root),'--job',str(request)],stdout=stream,stderr=subprocess.STDOUT,
                creationflags=CREATE_NO_WINDOW,env={**os.environ,'SSLKEYLOGFILE':'','TEMP':str(folder),'TMP':str(folder),
                    'HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1','HF_HUB_DISABLE_TELEMETRY':'1'})
            while process.poll() is None:
                if cancel.wait(.25):
                    avatar_runtime.stop_process(process);raise Cancelled('Avatar generation cancelled. Existing Library files are preserved.')
                elapsed=int(time.monotonic()-started)
                report(f'Creating talking avatar · {elapsed//60:02d}:{elapsed%60:02d} elapsed',None)
        if process.returncode:
            detail=log.read_text(encoding='utf-8',errors='replace')[-3000:]
            from engine import explain_engine_error
            raise RuntimeError('Talking-avatar generation failed. '+explain_engine_error(detail))
        result=json.loads(result_file.read_text(encoding='utf-8'))
        file=Path(result['path']).resolve()
        if file!=Path(payload['destination']).resolve() or not file.is_file() or file.stat().st_size<100:
            raise RuntimeError('The avatar engine did not return a valid MP4 file.')
        destination=media_folder(root,'video',output)
        destination.mkdir(parents=True,exist_ok=True)
        target=destination/('Avatar_'+time.strftime('%Y%m%d_%H%M%S')+'_'+secrets.token_hex(4)+'.mp4')
        if target.exists():raise RuntimeError('The avatar output filename is already in use.')
        shutil.move(str(file),str(target))
        return target,round(time.monotonic()-started,1),result
    finally:
        # Private requests can contain prompts and recording paths, never settings/models.
        request.unlink(missing_ok=True)
        if folder.resolve().is_relative_to((Path(root)/'avatar-jobs').resolve()):
            shutil.rmtree(folder,ignore_errors=True)
