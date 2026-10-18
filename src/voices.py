"""Fish Speech / SGLang-Omni loopback connection and cancellable audio transport."""
import base64,json,math,os,secrets,subprocess,time,urllib.parse,urllib.request
from pathlib import Path
from common import CREATE_NO_WINDOW,atomic_json,resource,runtime_python
from downloads import Cancelled

def connection(raw):
    protocol=raw.get('protocol','fish')
    if protocol not in ('fish','sglang'):raise ValueError('Choose Fish Speech API or SGLang-Omni.')
    endpoint=raw.get('endpoint','http://127.0.0.1:8080' if protocol=='fish' else 'http://127.0.0.1:8000')
    try:
        url=urllib.parse.urlsplit(endpoint)
        if url.scheme!='http' or url.hostname not in ('127.0.0.1','localhost','::1') or not url.port or url.username or url.password or url.query or url.fragment or url.path not in ('','/'):
            raise ValueError()
    except (TypeError,ValueError):raise ValueError('Enter a local server address such as http://127.0.0.1:8080. Only loopback connections are supported.') from None
    model=raw.get('model','fish_s2')
    if model not in ('fish_s2','fish_drama3'):raise ValueError('Choose S2-Pro or Drama 3.')
    if protocol=='sglang' and model!='fish_drama3':raise ValueError('This SGLang recipe is for Drama 3. Choose Drama 3.')
    return dict(protocol=protocol,endpoint=endpoint.rstrip('/'),model=model)

def validate_options(raw):
    o=connection(raw)
    for key,default,limit in [('text','',12000),('reference_id','',100),('transcript','',10000)]:
        value=raw.get(key,default)
        if not isinstance(value,str) or len(value)>limit:raise ValueError(f'Use valid {key.replace("_"," ")} text under {limit} characters.')
        o[key]=value.strip()
    if not o['text']:raise ValueError('Enter the words to speak first.')
    if o['reference_id'] and not o['transcript']:raise ValueError('Enter the exact transcript of the reference recording.')
    for key,default,low,high in [('temperature',.7,.1,1),('top_p',.7,.1,1)]:
        try:
            value=float(raw.get(key,default))
            if not low<=value<=high:raise ValueError()
        except (ValueError,TypeError,OverflowError):raise ValueError(f'{key} must be from {low} to {high}.') from None
        o[key]=value
    try:
        seed=str(raw.get('seed','')).strip();o['seed']=secrets.randbelow(2**31) if seed in ('','-1') else int(seed)
        if not 0<=o['seed']<2**32:raise ValueError()
    except (ValueError,TypeError,OverflowError):raise ValueError('Voice seed must be empty or a whole number from 0 to 4294967295.') from None
    o['randomize_seed']=raw.get('randomize_seed',True)
    if not isinstance(o['randomize_seed'],bool):raise ValueError('Choose whether to prepare a new voice seed.')
    return o

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise ValueError('Voice server redirects are not allowed. Check its local address.')

def check(raw):
    o=connection(raw);route='/v1/tts/defaults' if o['protocol']=='fish' else '/v1/models'
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
    try:
        with opener.open(o['endpoint']+route,timeout=5) as response:
            result=json.loads(response.read(1024*1024))
    except (OSError,ValueError) as error:raise ValueError('Cannot connect to the local voice server. Start it using the setup guide, then check the address. '+str(error)[:180]) from None
    family=result.get('model_family') if isinstance(result,dict) else None
    expected='s2' if o['model']=='fish_s2' else 'drama3'
    if family and family!=expected:raise ValueError(f'The Fish server has {family} loaded. Choose the matching model or restart the server with {expected}.')
    return dict(connected=True,protocol=o['protocol'],endpoint=o['endpoint'],model=o['model'],server=result)

def payload(o,reference=None):
    if o['protocol']=='fish':
        data=dict(text=o['text'],format='wav',streaming=False,seed=o['seed'],temperature=o['temperature'],top_p=o['top_p'],references=[])
        if reference:data['references']=[dict(audio=base64.b64encode(reference).decode(),text=o['transcript'])]
        return '/v1/tts',data
    data=dict(input=o['text'],model='fishaudio/drama-3',response_format='wav',stream=False,seed=o['seed'],temperature=o['temperature'],top_p=o['top_p'])
    if reference:data['references']=[dict(audio='data:audio/wav;base64,'+base64.b64encode(reference).decode(),text=o['transcript'])]
    return '/v1/audio/speech',data

def generate(root,o,recording,report,cancel):
    if not runtime_python(root).is_file():raise ValueError('Install the base runtime in Settings before generating speech.')
    check(o)
    reference=None
    if recording:
        path=Path(recording['path'])
        if not path.is_file() or path.stat().st_size>20*1024**2 or not .1<=recording.get('duration',0)<=60:raise ValueError('Use a reference recording from 0.1 to 60 seconds, under 20 MB.')
        reference=path.read_bytes()
    route,data=payload(o,reference)
    folder=Path(root)/'voice-jobs'/secrets.token_hex(12);folder.mkdir(parents=True)
    request=folder/'request.json';target=folder/'response.wav'
    atomic_json(request,dict(url=o['endpoint']+route,payload=data,target=str(target)))
    log=Path(root)/'logs/voice.log';log.parent.mkdir(exist_ok=True)
    started=time.monotonic();process=None
    try:
        with log.open('w',encoding='utf-8') as output:
            process=subprocess.Popen([str(runtime_python(root)),'-s',str(resource('voice_worker.py')),str(request)],stdout=output,stderr=subprocess.STDOUT,creationflags=CREATE_NO_WINDOW,env={**os.environ,'SSLKEYLOGFILE':''})
            while process.poll() is None:
                if cancel.wait(.25):
                    process.terminate();process.wait(timeout=10)
                    raise Cancelled('Studio stopped waiting for speech. The external voice server may still finish its request.')
                elapsed=int(time.monotonic()-started)
                report(f'Creating voice · {elapsed//60:02d}:{elapsed%60:02d} elapsed',None)
        if process.returncode:raise RuntimeError('Voice server request failed. '+log.read_text(encoding='utf-8',errors='replace')[-1500:])
        if cancel.is_set():raise Cancelled('Voice result cancelled.')
        if not target.is_file() or not 44<target.stat().st_size<=60*1024**2:raise ValueError('Voice server returned an empty or oversized recording.')
        return target.read_bytes(),round(time.monotonic()-started,1)
    finally:
        if process and process.poll() is None:process.terminate();process.wait(timeout=10)
        request.unlink(missing_ok=True);target.unlink(missing_ok=True);folder.rmdir()
