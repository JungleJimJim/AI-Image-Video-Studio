"""Optional local speech providers, isolated from the image/video Python packages."""
import json,math,os,secrets,shutil,subprocess,time
from pathlib import Path
from common import CREATE_NO_WINDOW,atomic_json,load_json,resource,runtime_python
from downloads import Cancelled,download

KOKORO_VOICES=('af_heart','af_bella','af_nicole','af_sarah','af_sky','am_adam','am_michael','bf_emma','bf_isabella','bm_george','bm_lewis')
LANGUAGES=('Auto','English','Chinese','Japanese','Korean','German','French','Russian','Portuguese','Spanish','Italian')

def catalog():
    return load_json(resource('local-voices.json'),{})

def folder(root,model):
    if model not in catalog():raise ValueError('Choose Kokoro or Qwen3-TTS.')
    return Path(root)/'extensions'/'local-voices'/model

def inventory(root):
    result=[]
    for model,spec in catalog().items():
        base=folder(root,model);marker=load_json(base/'ready.json',{})
        files=spec['files']
        ready=marker.get('version')==spec['version'] and load_json(base/'packages/studio-dependencies.json',{}).get('requirements')==spec['requirements'] and all((base/'weights'/f['filename']).is_file() and (base/'weights'/f['filename']).stat().st_size==f['size'] for f in files)
        result.append(dict(id=model,name=spec['name'],ready=ready,size=sum(f['size'] for f in files),source=spec['source'],license=spec['license'],vram_tier_gb=spec['vram_tier_gb'],vram_note=spec['vram_note']))
    return result

def validate(raw):
    model=raw.get('model')
    if model not in catalog():raise ValueError('Choose a local voice model.')
    o=dict(protocol='local',endpoint='',model=model)
    device=raw.get('device','cpu' if model=='kokoro' else 'cuda')
    if device not in ('cpu','cuda') or model=='kokoro' and device!='cpu':raise ValueError('Kokoro uses CPU; Qwen supports CPU or CUDA.')
    voice=raw.get('voice','af_heart')
    if model=='kokoro' and voice not in KOKORO_VOICES:raise ValueError('Choose a listed Kokoro voice.')
    language=raw.get('language','English')
    if language not in LANGUAGES:raise ValueError('Choose a supported speech language.')
    if model=='kokoro' and language not in ('Auto','English'):raise ValueError('This Kokoro pack exposes English voices.')
    try:
        speed=float(raw.get('speed',1))
        if not math.isfinite(speed) or not .5<=speed<=2:raise ValueError()
    except (ValueError,TypeError):raise ValueError('Speech speed must be from 0.5 to 2.') from None
    o.update(device=device,voice=voice,language=language,speed=speed)
    return o

def process(command,log,report,cancel,label):
    with Path(log).open('a',encoding='utf-8') as output:
        child=subprocess.Popen(command,stdout=output,stderr=subprocess.STDOUT,creationflags=CREATE_NO_WINDOW,env={**os.environ,'SSLKEYLOGFILE':'','PYTHONPATH':''})
        started=time.monotonic()
        try:
            while child.poll() is None:
                if cancel.wait(.25):
                    child.terminate();child.wait(timeout=15);raise Cancelled(label+' cancelled.')
                elapsed=int(time.monotonic()-started)
                report(label+f' · {elapsed//60:02d}:{elapsed%60:02d} elapsed',None)
        finally:
            if child.poll() is None:child.terminate();child.wait(timeout=15)
    if child.returncode:raise RuntimeError(label+' failed. '+Path(log).read_text(encoding='utf-8',errors='replace')[-1800:])

def install(root,model,report,cancel):
    spec=catalog().get(model)
    if not spec:raise ValueError('Unknown local voice model.')
    python=runtime_python(root)
    if not python.is_file():raise ValueError('Install the base runtime in Models first.')
    base=folder(root,model);base.mkdir(parents=True,exist_ok=True)
    needed=sum(f['size'] for f in spec['files'] if not (base/'weights'/f['filename']).is_file())
    reserve=4*1024**3 if model=='qwen_tts' else 800*1024**2
    if shutil.disk_usage(base).free<needed+reserve:raise ValueError('Allow more free space for the voice model and its isolated runtime.')
    log=Path(root)/'logs'/('voice-install-'+model+'.log');log.parent.mkdir(exist_ok=True)
    log.write_text('Installing '+spec['name']+'\n',encoding='utf-8')
    packages=base/'packages'
    if load_json(packages/'studio-dependencies.json',{}).get('requirements')!=spec['requirements']:
        staging=base/('packages-setup-'+secrets.token_hex(6));staging.mkdir()
        try:
            command=[str(python),'-s','-m','pip','install','--target',str(staging),'--upgrade','--no-compile','--no-cache-dir','--disable-pip-version-check','--index-url','https://pypi.org/simple',*(['--extra-index-url',spec['extra_index']] if spec.get('extra_index') else []),*spec['requirements']]
            process(command,log,report,cancel,'Installing isolated '+spec['name']+' dependencies')
            probe=base/'probe.json';atomic_json(probe,dict(model=model,packages=str(staging),probe=True))
            try:process([str(python),'-s',str(resource('local_voice_worker.py')),str(probe)],log,report,cancel,'Checking voice runtime imports')
            finally:probe.unlink(missing_ok=True)
            if packages.exists():
                old=base/('packages-old-'+secrets.token_hex(6));packages.rename(old)
            else:old=None
            try:staging.rename(packages)
            except Exception:
                if old:old.rename(packages)
                raise
            if old:shutil.rmtree(old)
            atomic_json(packages/'studio-dependencies.json',dict(requirements=spec['requirements']))
        finally:
            if staging.exists() and staging.parent==base:shutil.rmtree(staging)
    for f in spec['files']:
        if cancel.is_set():raise Cancelled('Voice installation cancelled; downloads can resume.')
        download(f,base/'weights'/f['filename'],report,cancel)
    atomic_json(base/'ready.json',dict(version=spec['version'],model=model))
    report(spec['name']+' installed. Choose it in Voice.',1)

def check(root,raw):
    o=validate(raw);item=next(x for x in inventory(root) if x['id']==o['model'])
    if not item['ready']:raise ValueError('Install '+item['name']+' from Models first.')
    return dict(connected=True,protocol='local',model=o['model'],name=item['name'],endpoint='')

def generate(root,o,recording,report,cancel):
    check(root,o)
    if o['model']=='qwen_tts':
        if not recording:raise ValueError('Choose a reference voice recording for Qwen voice cloning.')
        if not .1<=recording.get('duration',0)<=15:raise ValueError('Use a Qwen reference recording from 0.1 to 15 seconds.')
    base=folder(root,o['model']);job=Path(root)/'voice-jobs'/secrets.token_hex(12);job.mkdir(parents=True)
    target=job/'speech.wav';request=job/'request.json'
    atomic_json(request,dict(model=o['model'],packages=str(base/'packages'),weights=str(base/'weights'),options=o,reference=recording['path'] if recording else None,target=str(target)))
    log=Path(root)/'logs'/('voice-'+o['model']+'.log');log.parent.mkdir(exist_ok=True);log.write_text('',encoding='utf-8')
    started=time.monotonic()
    try:
        process([str(runtime_python(root)),'-s',str(resource('local_voice_worker.py')),str(request)],log,report,cancel,'Creating '+catalog()[o['model']]['name']+' speech')
        if not target.is_file() or not 44<target.stat().st_size<=60*1024**2:raise ValueError('The voice result is empty or too large.')
        with target.open('rb') as f:header=f.read(12)
        if header[:4]!=b'RIFF' or header[8:12]!=b'WAVE':raise ValueError('The voice model did not return WAV audio.')
        return target.read_bytes(),round(time.monotonic()-started,1)
    finally:
        request.unlink(missing_ok=True);target.unlink(missing_ok=True);job.rmdir()
