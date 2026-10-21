"""Isolated FaceFusion video jobs, with pinned downloads and preserved source media."""
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import shutil
import stat
import subprocess
import time
import zipfile

from common import CREATE_NO_WINDOW, atomic_json, load_json, resource, runtime_python
from downloads import Cancelled, download
from media_storage import media_folder

DEFAULTS=dict(model='facefusion_video',source_id='',reference_id='',selector='reference',
    face_position=0,reference_frame=0,similarity=.6,pixel_boost='256x256',quality=90,
    provider='cuda',encoder='libx264')


def catalog():return json.loads(resource('video-faceswap.json').read_text(encoding='utf-8'))
def folder(root):return Path(root)/'extensions/video_faceswap'


def tools(root):
    saved=load_json(folder(root)/'installed.json',{}).get('tools',{})
    result={key:next((str(p) for p in (Path(saved.get(key,'')),folder(root)/'tools'/(key+'.exe'),Path(shutil.which(key) or '')) if p.is_file()),'') for key in ('ffmpeg','ffprobe')}
    return result if all(result.values()) else None


def ready(root):
    config=catalog();base=folder(root)
    return (load_json(base/'installed.json',{}).get('revision')==config['revision']
        and runtime_python(root).is_file() and (base/'code/facefusion.py').is_file()
        and (base/'dependencies/onnxruntime/__init__.py').is_file() and bool(tools(root))
        and all((base/'code/.assets/models'/f['filename']).is_file() and (base/'code/.assets/models'/f['filename']).stat().st_size==f['size'] for f in config['models']))


def inventory(root):
    config=catalog()
    return dict(ready=ready(root),name='FaceFusion · HyperSwap video',version=config['version'],
        source=config['repository'],size=sum(f['size'] for f in config['models']+config['wheels'])+config['archive']['size'])


def validate(raw):
    if not isinstance(raw,dict):raise ValueError('Choose valid video faceswap options.')
    o=DEFAULTS|{key:value for key,value in raw.items() if key in DEFAULTS}
    if o['model']!='facefusion_video':raise ValueError('Choose the video faceswap model.')
    for key in ('source_id','reference_id'):
        if not isinstance(o[key],str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',o[key]):raise ValueError('Choose a target video and reference face from Library.')
    for key,lo,hi,whole in [('face_position',0,99,True),('reference_frame',0,10_000_000,True),('similarity',0,1,False),('quality',1,100,True)]:
        try:
            value=float(o[key])
            if not math.isfinite(value) or not lo<=value<=hi or (whole and not value.is_integer()):raise ValueError()
            o[key]=int(value) if whole else round(value/0.05)*0.05
            if not whole:o[key]=round(o[key],2)
        except (ValueError,TypeError,OverflowError):raise ValueError('Choose a valid '+key.replace('_',' ')+'.') from None
    if o['selector'] not in ('reference','one','many') or o['pixel_boost'] not in ('256x256','512x512') or o['provider'] not in ('cuda','cpu') or o['encoder'] not in ('libx264','h264_nvenc'):
        raise ValueError('Choose supported person selection, quality and processing options.')
    return o


def arguments(o,source,target,output,private):
    return ['headless-run','--processors','face_swapper','--face-swapper-model','hyperswap_1a_256',
        '--source-paths',str(source),'--target-path',str(target),'--output-path',str(output),
        '--temp-path',str(private/'temp'),'--jobs-path',str(private/'jobs'),
        '--face-selector-mode',o['selector'],'--face-selector-order','large-small',
        '--reference-face-position',str(o['face_position']),'--reference-frame-number',str(o['reference_frame']),
        '--reference-face-distance',str(o['similarity']),'--face-swapper-pixel-boost',o['pixel_boost'],
        '--face-detector-model','yolo_face','--face-landmarker-model','2dfan4','--face-mask-types','box','occlusion',
        '--execution-providers',o['provider'],'--execution-thread-count','2','--video-memory-strategy','moderate',
        '--output-video-encoder',o['encoder'],'--output-video-quality',str(o['quality']),
        '--output-video-scale','1.0','--output-audio-encoder','aac','--output-audio-volume','100',
        '--workflow-strategy','disk','--download-providers','huggingface']


def environment(root):
    selected=tools(root) or {}
    paths=list(dict.fromkeys(str(Path(path).parent) for path in selected.values()))
    return {**os.environ,'SSLKEYLOGFILE':'','PATH':os.pathsep.join([*paths,os.environ.get('PATH','')]),'PYTHONDONTWRITEBYTECODE':'1'}


def wait_process(command,root,log,report,cancel,stage,cwd=None):
    from avatar_runtime import stop_process
    log.parent.mkdir(parents=True,exist_ok=True)
    with log.open('w',encoding='utf-8') as stream:
        process=subprocess.Popen(command,cwd=cwd,stdin=subprocess.DEVNULL,stdout=stream,stderr=subprocess.STDOUT,
            creationflags=CREATE_NO_WINDOW,env=environment(root))
        started=time.monotonic()
        while process.poll() is None:
            if cancel.wait(.3):
                stop_process(process)
                raise Cancelled(stage+' cancelled. Existing Library media is preserved.')
            elapsed=int(time.monotonic()-started)
            report(f'{stage} · {elapsed//60:02d}:{elapsed%60:02d} elapsed',None)
    if process.returncode:raise RuntimeError(stage+' failed. '+log.read_text(errors='replace')[-2500:])


def extract_code(archive,destination):
    destination=Path(destination).resolve()
    with zipfile.ZipFile(archive) as package:
        if sum(item.file_size for item in package.infolist())>64*1024**2:raise ValueError('The video faceswap archive is unexpectedly large.')
        for item in package.infolist():
            path=PurePosixPath(item.filename)
            if path.is_absolute() or '..' in path.parts or '\\' in item.filename or stat.S_ISLNK(item.external_attr>>16):raise ValueError('Unsafe video faceswap archive path.')
            if len(path.parts)<2 or item.is_dir():continue
            target=(destination/Path(*path.parts[1:])).resolve()
            if not target.is_relative_to(destination):raise ValueError('Unsafe video faceswap destination.')
            target.parent.mkdir(parents=True,exist_ok=True)
            with package.open(item) as source,target.open('wb') as output:shutil.copyfileobj(source,output)
    if not (destination/'facefusion.py').is_file():raise ValueError('FaceFusion entry point is missing.')


def install(root,report,cancel):
    if not runtime_python(root).is_file():raise ValueError('Install the Studio runtime in Models first.')
    config=catalog();base=folder(root);base.mkdir(parents=True,exist_ok=True)
    cache=Path(root)/'downloads/video_faceswap';cache.mkdir(parents=True,exist_ok=True)
    if shutil.disk_usage(base).free<sum(f['size'] for f in config['models'])+1024**3:raise ValueError('Allow at least 3 GB free for video faceswap installation.')
    archive=download(config['archive'],cache/config['archive']['filename'],report,cancel)
    extract_code(archive,base/'code')
    wheels=[download(file,cache/file['filename'],report,cancel) for file in config['wheels']]
    wait_process([str(runtime_python(root)),'-s','-m','pip','install','--no-index','--no-deps','--upgrade','--target',str(base/'dependencies'),*[str(path) for path in wheels]],
        root,Path(root)/'logs/video-faceswap-install.log',report,cancel,'Installing isolated video faceswap dependencies')
    if not tools(root):
        archive=download(config['ffmpeg'],cache/config['ffmpeg']['filename'],report,cancel)
        destination=base/'tools';destination.mkdir(exist_ok=True)
        with zipfile.ZipFile(archive) as package:
            for name in ('ffmpeg.exe','ffprobe.exe'):
                entry=next(x for x in package.infolist() if PurePosixPath(x.filename).name==name)
                with package.open(entry) as source,(destination/name).open('wb') as output:shutil.copyfileobj(source,output)
            for item in package.infolist():
                if PurePosixPath(item.filename).name.lower().startswith('license') and not item.is_dir():
                    (destination/PurePosixPath(item.filename).name).write_bytes(package.read(item))
    for file in config['models']:download(file,base/'code/.assets/models'/file['filename'],report,cancel)
    selected=tools(root)
    if not selected:raise ValueError('FFmpeg and FFprobe are required. Repair video faceswap in Models.')
    private=base/'probe'
    args=arguments(DEFAULTS,'reference.png','target.mp4',private/'output.mp4',private)
    # The probe parses the real CLI and enumerates downloads; it never opens the inputs.
    command=[str(runtime_python(root)),'-s',str(resource('video_faceswap_worker.py')),'--folder',str(base),'--probe','--',*args]
    wait_process(command,root,Path(root)/'logs/video-faceswap-check.log',report,cancel,'Checking video faceswap without processing media')
    atomic_json(base/'installed.json',dict(revision=config['revision'],version=config['version'],tools=selected))
    report('Video faceswap installed. No media was processed.',1)


def run(root,source,reference,o,output,report,cancel):
    if not ready(root):raise ValueError('Install FaceFusion video faceswap from the Faceswap tab or Models first.')
    private=Path(root)/'video-faceswap-jobs'/secrets.token_hex(12);private.mkdir(parents=True)
    destination=private/'result.mp4';started=time.monotonic()
    try:
        command=[str(runtime_python(root)),'-s',str(resource('video_faceswap_worker.py')),'--folder',str(folder(root)),'--',*arguments(o,reference['path'],source['path'],destination,private)]
        wait_process(command,root,Path(root)/'logs/video-faceswap.log',report,cancel,'Swapping video face')
        if cancel.is_set():raise Cancelled('Video faceswap cancelled.')
        if not destination.is_file() or destination.stat().st_size<100:raise ValueError('The video faceswap engine did not return a valid video.')
        from media import process
        info=process(root,dict(action='video_info',source=str(destination)))
        target=media_folder(root,'video',output)/('Faceswap_'+time.strftime('%Y%m%d_%H%M%S')+'_'+secrets.token_hex(4)+'.mp4')
        target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists():raise ValueError('The faceswap output filename is already in use.')
        shutil.move(str(destination),target)
        return target,round(time.monotonic()-started,1),info
    finally:
        # Exact private job directory only; user sources, models and settings are outside it.
        if private.resolve().parent==(Path(root)/'video-faceswap-jobs').resolve():shutil.rmtree(private,ignore_errors=True)


def import_video(root,path,output,report,cancel):
    source=Path(path)
    if not source.is_file() or source.suffix.lower() not in ('.mp4','.mov','.webm','.mkv','.avi'):raise ValueError('Choose an existing MP4, MOV, WebM, MKV or AVI video.')
    from media import process
    info=process(root,dict(action='video_info',source=str(source)))
    identifier=secrets.token_hex(12);target=media_folder(root,'video',output)/('Imported_'+identifier+source.suffix.lower())
    target.parent.mkdir(parents=True,exist_ok=True)
    if shutil.disk_usage(target.parent).free<source.stat().st_size+256*1024**2:raise ValueError('Not enough free space to copy this video into Library.')
    temporary=target.with_suffix('.importing')
    try:
        with source.open('rb') as reader,temporary.open('xb') as writer:
            while chunk:=reader.read(8*1024**2):
                if cancel.is_set():raise Cancelled('Video import cancelled. The original is preserved.')
                writer.write(chunk);report('Importing local video into Library…',None)
        if cancel.is_set():raise Cancelled('Video import cancelled.')
        temporary.replace(target)
    finally:temporary.unlink(missing_ok=True)
    return dict(id=identifier,path=str(target),name=source.name,kind='imported_video',
        created=time.strftime('%Y-%m-%d %H:%M'),options={},**info)
