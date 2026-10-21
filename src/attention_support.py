"""Optional SageAttention settings and a small, explicit compatibility check."""
import json
from pathlib import Path
import subprocess
import time

from common import CREATE_NO_WINDOW, atomic_json, load_json, resource, runtime_python
from downloads import Cancelled

PROBE_TIMEOUT=180


def validate(mode):
    if mode not in ('pytorch','sage'):raise ValueError('Choose PyTorch or SageAttention.')
    return mode


def command(root,base,session,engine_dir=None):
    # The attention worker already prepares an isolated engine's dependency path.
    # Launch its main module directly so Comfy's early parser never sees the
    # engine_worker's private positional folder argument.
    entry=Path(engine_dir)/'code'/'main.py' if engine_dir else base[2]
    arguments=base[4:] if engine_dir else base[3:]
    result=[*base[:2],str(resource('attention_worker.py')),'--entry',str(entry),
            '--status-file',str(Path(root)/'attention-status.json'),'--session',session]
    if engine_dir:result+=['--engine-dir',str(engine_dir)]
    return [*result,'--',*arguments]


def snapshot(root,mode='pytorch',engine=None):
    check=load_json(Path(root)/'attention-check.json',{})
    status=load_json(Path(root)/'attention-status.json',{})
    live=bool(engine and engine.process and engine.process.poll() is None)
    if not engine or status.get('session')!=getattr(engine,'attention_session',None):status={}
    selected=getattr(engine,'signature',None)
    starting='starting' if selected and len(selected)>3 and selected[3]=='sage' else 'pytorch'
    return dict(preference=mode,check=check,engine_running=live,
                active=status.get('active',starting if live else 'idle'),
                reason=status.get('reason','No generation engine is running.' if not live else 'Using PyTorch attention.'))


def check(root,report,cancel):
    if not runtime_python(root).is_file():raise ValueError('Install the base runtime in Models or Settings first.')
    report('Checking SageAttention with a small math test. No media is generated…',None)
    args=[str(runtime_python(root)),'-s',str(resource('attention_worker.py')),'--probe','--kernel-test']
    process=subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,creationflags=CREATE_NO_WINDOW)
    deadline=time.monotonic()+PROBE_TIMEOUT
    stdout=stderr=''
    last_stage='Starting the compatibility check'
    try:
        while True:
            if cancel.is_set():raise Cancelled('Attention check cancelled.')
            if time.monotonic()>deadline:
                raise RuntimeError('The attention compatibility check timed out during: '+last_stage+
                                   '. PyTorch is still available. See logs/attention-check.log for details.')
            try:stdout,stderr=process.communicate(timeout=.2);break
            except subprocess.TimeoutExpired as error:
                output=error.output or ''
                if isinstance(output,bytes):output=output.decode('utf-8',errors='replace')
                stages=[line.split(' ',1)[1] for line in output.splitlines() if line.startswith('STUDIO_ATTENTION_STAGE ')]
                if stages and stages[-1]!=last_stage:
                    last_stage=stages[-1];report(last_stage+'…',None)
        lines=[line for line in stdout.splitlines() if line.startswith('STUDIO_ATTENTION_PROBE ')]
        if process.returncode or not lines:raise RuntimeError('SageAttention check failed. '+stderr[-700:])
        result=json.loads(lines[-1].split(' ',1)[1])
        result['checked_at']=time.time()
        atomic_json(Path(root)/'attention-check.json',result)
        report('SageAttention is compatible.' if result.get('available') else result.get('reason','PyTorch remains available.'),1)
        return result
    finally:
        if process.poll() is None:
            process.terminate()
        try:stdout,stderr=process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill();stdout,stderr=process.communicate(timeout=5)
        log=Path(root)/'logs'/'attention-check.log'
        try:
            log.parent.mkdir(parents=True,exist_ok=True)
            log.write_text(stdout+'\n'+stderr,encoding='utf-8')
        except OSError:pass
