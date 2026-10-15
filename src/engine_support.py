"""Pinned optional engine code; the original runtime and model files stay intact."""
import json
import os
from pathlib import Path, PurePosixPath
import secrets
import shutil
import stat
import subprocess
import zipfile

from common import CREATE_NO_WINDOW, atomic_json, comfy_root, load_json, resource, runtime_python
from downloads import Cancelled, download


def catalog():
    return json.loads(resource('engines.json').read_text(encoding='utf-8'))


def engine_root(root, key):
    if key not in catalog():raise ValueError('Unknown optional engine.')
    return Path(root)/'engines'/key


def ready(root, key):
    config=catalog()[key];folder=engine_root(root,key)
    return (load_json(folder/'installed.json',{}).get('revision')==config['revision']
            and runtime_python(root).is_file() and (folder/'code/main.py').is_file()
            and (folder/'dependencies/comfy_aimdo/control.py').is_file())


def extract(archive, destination, cancel):
    destination=Path(destination).resolve();destination.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(archive) as source:
        entries=source.infolist()
        if sum(x.file_size for x in entries)>300*1024**2:raise ValueError('The engine archive is unexpectedly large.')
        tops={PurePosixPath(x.filename).parts[0] for x in entries if x.filename}
        if len(tops)!=1:raise ValueError('The engine archive has an invalid structure.')
        for item in entries:
            if cancel.is_set():raise Cancelled('Engine installation cancelled. Retry from Models.')
            path=PurePosixPath(item.filename)
            if path.is_absolute() or '..' in path.parts or '\\' in item.filename or stat.S_ISLNK(item.external_attr>>16):
                raise ValueError('The engine archive contains an unsafe path.')
            relative=Path(*path.parts[1:])
            if not relative.parts or item.is_dir():continue
            target=(destination/relative).resolve()
            if not target.is_relative_to(destination):raise ValueError('The engine archive redirects outside its folder.')
            target.parent.mkdir(parents=True,exist_ok=True)
            with source.open(item) as src,target.open('wb') as dst:shutil.copyfileobj(src,dst)
    if not (destination/'main.py').is_file():raise ValueError('The engine entry point is missing.')


def install(root, key, report, cancel):
    if ready(root,key):return
    if not runtime_python(root).is_file():raise ValueError('Install the base runtime first.')
    config=catalog()[key];folder=engine_root(root,key);base=folder.parent
    base.mkdir(parents=True,exist_ok=True)
    cache=Path(root)/'downloads'/'engines';cache.mkdir(parents=True,exist_ok=True)
    if shutil.disk_usage(cache).free<512*1024**2:raise ValueError('Allow at least 512 MB free for the separate engine.')
    archive=download(config['archive'],cache/config['archive']['filename'],report,cancel)
    wheels=[download(f,cache/f['filename'],report,cancel) for f in config['wheels']]
    staging=base/('.'+key+'-install-'+secrets.token_hex(6));staging.mkdir()
    backup=base/('.'+key+'-previous-'+secrets.token_hex(6))
    try:
        report('Preparing the separate FLUX 3 engine…',None)
        extract(archive,staging/'code',cancel)
        log=Path(root)/'logs'/'flux3-engine-install.log';log.parent.mkdir(exist_ok=True)
        command=[str(runtime_python(root)),'-s','-m','pip','install','--no-index','--no-deps',
                 '--target',str(staging/'dependencies'),*[str(p) for p in wheels]]
        with log.open('w',encoding='utf-8') as output:
            process=subprocess.Popen(command,stdout=output,stderr=subprocess.STDOUT,creationflags=CREATE_NO_WINDOW,
                                     env={**os.environ,'SSLKEYLOGFILE':''})
            while process.poll() is None:
                if cancel.wait(.2):
                    process.terminate();process.wait(timeout=20)
                    raise Cancelled('Engine installation cancelled. Retry from Models.')
        if process.returncode:raise RuntimeError('The FLUX 3 engine dependency could not install. See logs/flux3-engine-install.log.')
        report('Checking FLUX 3 engine nodes on CPU. No model weights are loaded.',None)
        probe=subprocess.run([str(runtime_python(root)),'-s',str(resource('engine_worker.py')),str(staging),'--studio-probe'],
                             capture_output=True,text=True,timeout=180,creationflags=CREATE_NO_WINDOW)
        with log.open('a',encoding='utf-8') as output:output.write(probe.stdout+'\n'+probe.stderr)
        if probe.returncode:raise RuntimeError('The separate FLUX 3 engine check failed. See logs/flux3-engine-install.log.\n'+probe.stderr[-1500:])
        if cancel.is_set():raise Cancelled('Engine installation cancelled. Retry from Models.')
        atomic_json(staging/'installed.json',dict(revision=config['revision'],version=config['version']))
        if folder.exists():folder.rename(backup)
        try:staging.rename(folder)
        except Exception:
            if backup.exists():backup.rename(folder)
            raise
        report('FLUX 3 engine installed. The original engine was preserved.',1)
    finally:
        # These paths are generated beneath the managed engine folder, never model/media paths.
        for temporary in (staging,backup):
            if temporary.exists() and temporary.resolve().is_relative_to(base.resolve()):shutil.rmtree(temporary)


def command(root, key):
    if not ready(root,key):raise ValueError('Install or repair FLUX 3 in Models first.')
    folder=engine_root(root,key);user=Path(root)/'engine-profiles'/key;user.mkdir(parents=True,exist_ok=True)
    input_folder=comfy_root(root)/'input';input_folder.mkdir(parents=True,exist_ok=True)
    return [str(runtime_python(root)),'-s',str(resource('engine_worker.py')),str(folder),
            '--models-directory',str(comfy_root(root)/'models'),'--input-directory',str(input_folder),
            '--user-directory',str(user),'--offline']
