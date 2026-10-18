"""Optional, isolated dependencies and pinned source adapters for talking avatars."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import zipfile

from common import CREATE_NO_WINDOW, atomic_json, comfy_root, load_json, resource, runtime_python
from downloads import Cancelled
import engine_support


REQUIREMENTS = ('numpy==2.2.6','scipy==1.15.3','pillow==11.3.0',
    'diffusers==0.35.1','transformers==4.57.3','tokenizers==0.22.1',
    'huggingface_hub==0.36.0','accelerate==1.10.1','peft==0.17.1','optimum-quanto==0.2.7',
    'librosa==0.11.0','soundfile==0.13.1','soxr==0.5.0.post1','numba==0.61.2',
    'llvmlite==0.44.0','lazy-loader==0.4','pooch==1.8.2','audioread==3.0.1',
    'scikit-learn==1.6.1','threadpoolctl==3.6.0','joblib==1.5.1',
    'omegaconf==2.3.0','antlr4-python3-runtime==4.9.3','easydict==1.13',
    'pyloudnorm==0.1.1','gguf==0.17.1','loguru==0.7.3','ftfy==6.3.1',
    'imageio==2.37.0','imageio-ffmpeg==0.6.0','moviepy==2.2.1','decorator==5.2.1',
    'proglog==0.1.12','python-dotenv==1.1.1','onnxruntime==1.22.1',
    'coloredlogs==15.0.1','humanfriendly==10.0','flatbuffers==25.2.10',
    'einops==0.8.1','opencv-python==4.12.0.88','scikit-image==0.25.2',
    'tifffile==2025.5.10','future==1.0.0','wcwidth==0.2.13',
    'win32-setctime==1.2.0','colorama==0.4.6','importlib_metadata==8.7.0','zipp==3.23.0',
    'pyreadline3==3.5.4','msgpack==1.1.1','standard-aifc==3.13.0','standard-sunau==3.13.0',
    'standard-chunk==3.13.0','audioop-lts==0.2.1','protobuf==5.29.5',
    'ninja==1.11.1.4','platformdirs==4.3.8')


def folder(root):
    return engine_support.engine_root(root, 'avatar')


def signature():
    config = load_json(resource('avatar-runtime.json'), {})
    return hashlib.sha256((config['sha256']+'\n'+'\n'.join(REQUIREMENTS)+
        json.dumps(config['dependencies'],sort_keys=True)).encode()).hexdigest()


def ready(root):
    base = folder(root)
    return engine_support.ready(root,'avatar') and load_json(base/'avatar-ready.json',{}).get('signature')==signature()


def stop_process(process):
    if process.poll() is not None:
        return
    if os.name == 'nt':
        # Only the process started for this job and its own descendants.
        subprocess.run(['taskkill.exe','/PID',str(process.pid),'/T','/F'],
                       capture_output=True,creationflags=CREATE_NO_WINDOW,timeout=20)
    else:
        process.terminate()
    try:
        process.wait(timeout=20)
    except subprocess.TimeoutExpired:
        process.kill();process.wait(timeout=10)


def install(root, report, cancel):
    if ready(root):
        return
    base=folder(root)
    if not engine_support.ready(root,'avatar'):
        engine_support.install(root,'avatar',report,cancel)
    config=load_json(resource('avatar-runtime.json'),{})
    archive=resource('avatar-sources.zip')
    if hashlib.sha256(archive.read_bytes()).hexdigest()!=config['sha256']:
        raise ValueError('The avatar source bundle failed its checksum check. Reinstall the app.')
    sources=base/'adapters';sources.mkdir(exist_ok=True)
    with zipfile.ZipFile(archive) as package:
        for entry in package.infolist():
            path=(sources/entry.filename).resolve()
            if not path.is_relative_to(sources.resolve()) or entry.file_size>4_000_000:
                raise ValueError('Invalid avatar source archive.')
            if cancel.is_set():raise Cancelled('Avatar installation cancelled. Retry in Models.')
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes(package.read(entry))
    dependencies=base/'avatar-dependencies';dependencies.mkdir(exist_ok=True)
    temporary=base/'install-temp';temporary.mkdir(exist_ok=True)
    environment={**os.environ,'SSLKEYLOGFILE':'','TEMP':str(temporary),'TMP':str(temporary),
                 'PIP_CACHE_DIR':str(base/'pip-cache')}
    log=Path(root)/'logs/avatar-install.log';log.parent.mkdir(exist_ok=True)
    report('Installing isolated talking-avatar dependencies. Existing model engines stay intact…',None)
    # The shared CUDA/PyTorch runtime remains untouched. Each dependency is pinned;
    # its installation directory is visible only to the avatar worker process.
    from downloads import download
    cache=Path(root)/'downloads/avatar-dependencies';cache.mkdir(parents=True,exist_ok=True)
    packages=[download(spec,cache/spec['filename'],report,cancel) for spec in config['dependencies']]
    command=[str(runtime_python(root)),'-s','-m','pip','install','--disable-pip-version-check',
             '--no-index','--no-build-isolation','--no-deps','--upgrade','--target',str(dependencies),
             *[str(path) for path in packages]]
    with log.open('w',encoding='utf-8') as output:
        process=subprocess.Popen(command,stdout=output,stderr=subprocess.STDOUT,
            creationflags=CREATE_NO_WINDOW,env=environment)
        while process.poll() is None:
            if cancel.wait(.2):
                stop_process(process);raise Cancelled('Avatar installation cancelled. Retry in Models.')
    if process.returncode:
        raise RuntimeError('The avatar dependencies could not install. See logs/avatar-install.log. Downloaded weights are preserved.')
    report('Checking avatar interfaces on CPU. No images or videos are generated…',None)
    probe=subprocess.run([str(runtime_python(root)),'-s',str(resource('avatar_worker.py')),
        '--root',str(root),'--probe'],capture_output=True,text=True,timeout=180,
        creationflags=CREATE_NO_WINDOW,env={**environment,'CUDA_VISIBLE_DEVICES':''})
    with log.open('a',encoding='utf-8') as output:output.write(probe.stdout+'\n'+probe.stderr)
    if probe.returncode:
        raise RuntimeError('The avatar runtime check failed. See logs/avatar-install.log. Existing generators are unaffected.\n'+probe.stderr[-1200:])
    if cancel.is_set():raise Cancelled('Avatar installation cancelled. Retry in Models.')
    atomic_json(base/'avatar-ready.json',dict(signature=signature(),sources=config['sources'],cpu_probe=True))
    report('Talking-avatar runtime installed and checked.',1)
