"""Optional, isolated enhancement passes. Originals always stay in the library."""
import json
import math
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import time

from common import CREATE_NO_WINDOW, atomic_json, comfy_root, existing_parent, load_json, resource, runtime_python
from downloads import Cancelled, download
from packs import ready as pack_ready

QUALITY = ('BICUBIC','LOW','MEDIUM','HIGH','ULTRA','HIGHBITRATE_LOW','HIGHBITRATE_MEDIUM',
           'HIGHBITRATE_HIGH','HIGHBITRATE_ULTRA','STREAMING_MEDIUM','STREAMING_ULTRA',
           'DENOISE_LOW','DENOISE_MEDIUM','DENOISE_HIGH','DENOISE_ULTRA',
           'DEBLUR_LOW','DEBLUR_MEDIUM','DEBLUR_HIGH','DEBLUR_ULTRA')
PREPROCESS = ('none',)+tuple(x for x in QUALITY if x.startswith(('DENOISE_','DEBLUR_')))
IMAGE_DEFAULTS = dict(scale=2.0,detail_strength=1.0,steps=25,cfg=1.0,seed='',randomize_seed=True,memory='auto',
    prompt='Enhance this image to high resolution with rich fine details. Improve clarity while preserving the original composition, lighting, atmosphere and visual style.',negative='')
VIDEO_DEFAULTS = dict(scale=2.0,quality='HIGHBITRATE_HIGH',strength=1.0,preprocess='none',
                      preprocess_strength=1.0,frames_per_chunk=48,encoder='h264_nvenc')


def extension_root(root):
    return Path(root)/'extensions'/'rtx_vsr'


def vsr_ready(root):
    config=json.loads(resource('enhancers.json').read_text())['rtx_vsr']
    marker=load_json(extension_root(root)/'installed.json',{})
    return marker.get('revision')==config['revision'] and runtime_python(root).is_file() and all(
        (extension_root(root)/f['filename']).is_file() and (extension_root(root)/f['filename']).stat().st_size==f['size'] for f in config['files'])


def inventory(root):
    return dict(image=pack_ready(root,'qwen21'),video=vsr_ready(root),image_defaults=IMAGE_DEFAULTS,
                video_defaults=VIDEO_DEFAULTS,quality=list(QUALITY),preprocess=list(PREPROCESS))


def validate(raw,kind):
    if not isinstance(raw,dict):raise ValueError('Choose valid enhancement options.')
    defaults=IMAGE_DEFAULTS if kind=='image' else VIDEO_DEFAULTS
    o={**defaults,**{k:v for k,v in raw.items() if k in defaults}}
    numeric={'scale':(1,4)}
    numeric.update({'detail_strength':(0,2),'steps':(1,60),'cfg':(1,15)} if kind=='image' else
                   {'strength':(0,1),'preprocess_strength':(0,1),'frames_per_chunk':(4,240)})
    for key,(lo,hi) in numeric.items():
        try:
            value=float(o[key])
            if not math.isfinite(value) or not lo<=value<=hi or (key in ('steps','frames_per_chunk') and not value.is_integer()):raise ValueError()
            o[key]=int(value) if key in ('steps','frames_per_chunk') else value
        except (TypeError,ValueError,OverflowError):raise ValueError(f'{key.replace("_"," ").capitalize()} must be between {lo} and {hi}.') from None
    if kind=='image':
        if not isinstance(o['randomize_seed'],bool):raise ValueError('Choose whether to prepare a new seed for each job.')
        if o['memory'] not in ('auto','low'):raise ValueError('Choose a supported memory mode.')
        for field in ('prompt','negative'):
            if not isinstance(o[field],str) or len(o[field])>10000:raise ValueError('Enhancement prompts must be text under 10,000 characters.')
        if not o['prompt'].strip():raise ValueError('Describe the image enhancement.')
        try:
            o['seed']=secrets.randbelow(2**53) if str(o['seed']).strip() in ('','-1') else int(o['seed'])
            if not 0<=o['seed']<2**53:raise ValueError()
        except (TypeError,ValueError,OverflowError):raise ValueError('Use an empty or valid whole-number enhancement seed.') from None
    elif o['quality'] not in QUALITY or o['preprocess'] not in PREPROCESS or o['encoder'] not in ('h264_nvenc','hevc_nvenc','libx264'):
        raise ValueError('Choose supported RTX VSR quality, preprocessing and encoding options.')
    return o


def image_size(width,height,scale):
    factor=min(float(scale),math.sqrt((2048*2048)/(width*height)))
    w=max(64,int(width*factor/32)*32);h=max(64,int(height*factor/32)*32)
    if max(w,h)>4096:
        factor=min(factor,4096/max(width,height));w=max(64,int(width*factor/32)*32);h=max(64,int(height*factor/32)*32)
    return w,h


def image_workflow(o,prefix):
    from workflows import node,decode
    from loras import apply_to_graph
    g={'1':node('UNETLoader',unet_name='qwen_image_2.1_int8_convrot.safetensors',weight_dtype='default'),
       '2':node('CLIPLoader',clip_name='qwen3vl_8b_int8_convrot.safetensors',type='qwen_image',device='default'),
       '3':node('VAELoader',vae_name='qwen_image_2.1_vae_bf16.safetensors'),
       '4':node('LoadImage',image=o['input_file']),
       '5':node('TextEncodeQwenImage21',clip=['2',0],prompt=o['prompt'],negative_prompt=o['negative'],vae=['3',0],resolution=1024,**{'images.image_1':['4',0]}),
       '6':node('EmptyLatentImage',width=o['width'],height=o['height'],batch_size=1),
       '7':node('KSampler',model=['1',0],positive=['5',0],negative=['5',1],latent_image=['6',0],seed=o['seed'],steps=o['steps'],cfg=o['cfg'],sampler_name='euler',scheduler='simple',denoise=1.0),
       '8':decode(['7',0],['3',0]),'9':node('SaveImage',images=['8',0],filename_prefix=prefix)}
    builtin='studio/qwen21/elusarcas-qwen2-1-detailer-v1.safetensors'
    additional=[x for x in o.get('loras',[]) if x['name']!=builtin]
    if len(additional)>7:raise ValueError('Use at most seven extra LoRAs with the built-in detail enhancer.')
    return apply_to_graph(g,{**o,'loras':[dict(name=builtin,strength=o['detail_strength']),*additional]},['1',0])


def install_video(root,report,cancel):
    if not runtime_python(root).is_file():raise ValueError('Install the base runtime before adding RTX enhancement.')
    config=json.loads(resource('enhancers.json').read_text())['rtx_vsr']
    folder=extension_root(root);folder.mkdir(parents=True,exist_ok=True)
    for file in config['files']:download(file,folder/file['filename'],report,cancel)
    cache=Path(root)/'downloads'/'enhancers';cache.mkdir(parents=True,exist_ok=True)
    required=sum(f['size'] for f in config['wheels'] if not (cache/f['filename']).is_file())
    if shutil.disk_usage(existing_parent(cache)).free<required+1024**3:raise ValueError('Allow enough space for the SDK download plus one GB for installation.')
    wheels=[download(f,cache/f['filename'],report,cancel) for f in config['wheels']]
    log=Path(root)/'logs'/'upscaler-install.log';log.parent.mkdir(exist_ok=True)
    report('Installing the NVIDIA VFX bindings and FFmpeg. Existing PyTorch dependencies are kept.',None)
    command=[str(runtime_python(root)),'-s','-m','pip','install','--no-index','--no-deps',*[str(p) for p in wheels]]
    with log.open('w',encoding='utf-8') as output:
        process=subprocess.Popen(command,stdout=output,stderr=subprocess.STDOUT,creationflags=CREATE_NO_WINDOW,env={**os.environ,'SSLKEYLOGFILE':''})
        while process.poll() is None:
            if cancel.wait(.3):
                process.terminate();process.wait(timeout=20)
                raise Cancelled('Upscaler installation cancelled. Retry from Models.')
    if process.returncode:raise RuntimeError('Upscaler dependency installation failed. See logs/upscaler-install.log.\n'+log.read_text(errors='replace')[-2500:])
    check=subprocess.run([str(runtime_python(root)),'-s','-c','import nvvfx,imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())'],capture_output=True,text=True,timeout=60,creationflags=CREATE_NO_WINDOW,env={**os.environ,'SSLKEYLOGFILE':''})
    if check.returncode:raise RuntimeError('The NVIDIA bindings could not import. Check your NVIDIA driver and logs/upscaler-install.log.\n'+check.stderr[-2000:])
    atomic_json(folder/'installed.json',dict(revision=config['revision'],packages=config['packages']))
    report('RTX video enhancement installed. No video was processed.',1)


def run_video(root,source,output,options,report,cancel):
    if not vsr_ready(root):raise ValueError('Install RTX video enhancement in Models first.')
    folder=Path(root)/'enhancement-jobs'/secrets.token_hex(12);folder.mkdir(parents=True)
    private_output=folder/'output'
    payload=dict(extension=str(extension_root(root)),source=str(source),output=str(private_output),options=options,
                 progress=str(folder/'progress.json'),result=str(folder/'result.json'),cancel=str(folder/'cancel'))
    atomic_json(folder/'job.json',payload)
    log=Path(root)/'logs'/'upscaler.log';log.parent.mkdir(exist_ok=True)
    command=[str(runtime_python(root)),'-s',str(resource('upscale_worker.py')),str(folder/'job.json')]
    cancelled=False;deadline=None
    with log.open('w',encoding='utf-8') as handle:
        process=subprocess.Popen(command,stdout=handle,stderr=subprocess.STDOUT,creationflags=CREATE_NO_WINDOW)
        while process.poll() is None:
            if cancel.is_set() and not cancelled:
                cancelled=True;deadline=time.monotonic()+20;(folder/'cancel').touch()
            if cancelled and time.monotonic()>deadline:
                process.terminate();process.wait(timeout=20);break
            progress=load_json(folder/'progress.json',{})
            report('Cancelling RTX enhancement…' if cancelled else f'RTX video enhancement · {progress.get("frames",0)} frames processed',None)
            time.sleep(.3)
    if cancelled:raise Cancelled('Video enhancement cancelled. The original is preserved.')
    if process.returncode:raise RuntimeError('RTX enhancement failed. The original is preserved.\n'+log.read_text(errors='replace')[-3000:])
    result=load_json(folder/'result.json',{})
    path=Path(result.get('output',''))
    if not path.is_file() or not path.resolve().is_relative_to(private_output.resolve()):raise RuntimeError('The upscaler did not return a valid output file.')
    destination=Path(output).resolve()/path.name
    if destination.parent!=Path(output).resolve() or destination.exists():raise RuntimeError('The enhancement output path is already in use.')
    destination.parent.mkdir(parents=True,exist_ok=True)
    # Source and destination are verified file paths; private work never shares a user cache folder.
    shutil.move(str(path.resolve()),str(destination))
    result['output']=str(destination)
    return result
