"""Pinned managed OpenJutsu engine, nodes and selectable verified model packs."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import time
import zipfile

from common import atomic_json, comfy_root, existing_parent, load_json, resource, runtime_python, in_program_files
from downloads import Cancelled, checksum, download

SHARED_CATEGORIES = ('diffusion_models', 'text_encoders', 'vae', 'loras', 'checkpoints', 'clip_vision', 'sams', 'ultralytics')


def catalog():
    return json.loads(resource('openjutsu-backend.json').read_text(encoding='utf-8'))


def folder(root):
    return Path(root) / 'engines/openjutsu'


def models_folder(root):
    saved = load_json(Path(root) / 'openjutsu-settings.json', {})
    if not isinstance(saved, dict):saved = {}
    return Path(saved.get('models') or (Path(root) / 'openjutsu-models')).expanduser().resolve()


def validate_models_folder(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError('Choose a dedicated folder for OpenJutsu model downloads.')
    path = Path(value).expanduser()
    if not path.is_absolute():raise ValueError('Choose an absolute model-folder path.')
    path = path.resolve()
    if path == path.parent or len(str(path)) > 180 or in_program_files(path):
        raise ValueError('Choose a writable model folder outside Program Files, under 180 characters long.')
    return path


def ready(root):
    base = folder(root)
    config = catalog()
    return (load_json(base / 'installed.json', {}).get('revision') == config['revision']
            and runtime_python(root).is_file() and (base / 'code/main.py').is_file()
            and (base / 'tools/ffmpeg.exe').is_file() and (base / 'tools/ffprobe.exe').is_file()
            and (base / 'dependencies/insightface/__init__.py').is_file()
            and all((base / 'code/custom_nodes' / n['name'] / '__init__.py').is_file() for n in config['nodes']))


def path_for(root, spec):
    return models_folder(root) / spec['folder'] / spec['filename']


def available(root, spec):
    target = path_for(root, spec)
    if spec.get('unpack'):
        marker = load_json(target.with_suffix('.installed.json'), {})
        destination = target.parent / 'models/buffalo_l'
        return (marker.get('sha256') == spec['sha256'] and set(marker.get('files', {})) == set(spec['members'])
                and all((destination / name).is_file() and (destination / name).stat().st_size == size
                        for name, size in marker.get('files', {}).items()))
    candidates = [target]
    if spec['folder'].split('/')[0] in SHARED_CATEGORIES:
        candidates.append(comfy_root(root) / 'models' / spec['folder'] / spec['filename'])
    for candidate in candidates:
        if candidate.is_file() and candidate.stat().st_size == spec['size']:
            return True
    return False


def inventory(root):
    config = catalog()
    groups = []
    for key, group in config['groups'].items():
        groups.append(dict(id=key, name=group['name'], gated=group.get('gated', False),
            source=group['source'], ready=all(available(root, f) for f in group['files']),
            size=sum(f['size'] for f in group['files']),
            remaining=sum(f['size'] for f in group['files'] if not available(root, f))))
    return dict(ready=ready(root), models=str(models_folder(root)), groups=groups,
                software_size=sum(f['size'] for f in [config['engine'], config['ffmpeg'],
                    *config['wheels'], *[n['archive'] for n in config['nodes']]]))


def install_software(root, report, cancel):
    if ready(root):return
    if not runtime_python(root).is_file():raise ValueError('Install Studio\'s base runtime first.')
    import openjutsu
    config = catalog()
    base = folder(root)
    base.parent.mkdir(parents=True, exist_ok=True)
    cache = Path(root) / 'downloads/openjutsu-backend'
    cache.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(base.parent).free < 3 * 1024**3:
        raise ValueError('Allow 3 GB free in the Studio data folder for the managed backend software.')
    specs = [config['engine'], config['ffmpeg'], *config['wheels'], *[n['archive'] for n in config['nodes']]]
    paths = {f['filename']: download(f, cache / f['filename'], report, cancel) for f in specs}
    staging = base.parent / ('.openjutsu-backend-' + secrets.token_hex(6))
    previous = base.parent / ('.openjutsu-backend-previous-' + secrets.token_hex(6))
    staging.mkdir()
    activated = False
    log = Path(root) / 'logs/openjutsu-backend-install.log'
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text('', encoding='utf-8')
    try:
        report('Preparing the separate OpenJutsu engine and pinned node packs…', None)
        openjutsu.extract(paths[config['engine']['filename']], staging / 'code', cancel)
        for node in config['nodes']:
            destination = staging / 'code/custom_nodes' / node['name']
            if node.get('subdirectory'):
                temporary = staging / 'node-source'
                openjutsu.extract(paths[node['archive']['filename']], temporary, cancel)
                shutil.copytree(temporary / node['subdirectory'], destination)
                for license_file in temporary.glob('LICENSE*'):shutil.copy2(license_file, destination / license_file.name)
                if temporary.resolve().parent != staging.resolve():raise ValueError('Invalid temporary node source path.')
                shutil.rmtree(temporary)
            else:openjutsu.extract(paths[node['archive']['filename']], destination, cancel)
            # Avoid importing unrelated preprocessors and patch nodes. Original sources/licenses remain alongside these adapters.
            if node.get('adapter'):
                init = destination / '__init__.py'
                init.rename(destination / '__init__.upstream.py')
                init.write_text(node['adapter'], encoding='utf-8')
        tools = staging / 'tools'
        tools.mkdir()
        with zipfile.ZipFile(paths[config['ffmpeg']['filename']]) as package:
            for name in ('ffmpeg.exe', 'ffprobe.exe'):
                entry = next(n for n in package.namelist() if n.endswith('/' + name))
                with package.open(entry) as source, (tools / name).open('wb') as output:shutil.copyfileobj(source, output)
            for item in package.infolist():
                if Path(item.filename).name.lower().startswith('license') and not item.is_dir():
                    (tools / Path(item.filename).name).write_bytes(package.read(item))
        atomic_json(staging / 'backend-spec.json', config)
        command = [str(runtime_python(root)), '-s', '-m', 'pip', 'install', '--no-index', '--no-deps',
                   '--target', str(staging / 'dependencies'), *[str(paths[f['filename']]) for f in config['wheels']]]
        env = openjutsu.environment(staging)
        openjutsu.wait_process(command, staging, env, log, report, cancel, 'Installing isolated backend dependencies')
        report('Checking all OpenJutsu nodes and deferred imports on CPU; no model weights are loaded…', None)
        openjutsu.wait_process([str(runtime_python(root)), '-s', str(resource('openjutsu_backend_worker.py')),
            str(staging), str(models_folder(root)), 'probe'], staging, env, log, report, cancel, 'Checking the managed backend')
        if cancel.is_set():raise Cancelled('Managed backend installation cancelled.')
        atomic_json(staging / 'installed.json', dict(revision=config['revision']))
        if base.exists():base.rename(previous)
        try:
            staging.rename(base)
            activated = True
        except Exception:
            if previous.exists():previous.rename(base)
            raise
        report('Managed OpenJutsu engine and nodes installed and checked.', 1)
    finally:
        for temporary in (staging, *([previous] if activated else [])):
            if temporary.exists() and temporary.resolve().parent == base.parent.resolve():shutil.rmtree(temporary)


def selection(keys):
    groups = catalog()['groups']
    if not isinstance(keys, list) or any(not isinstance(k, str) or k not in groups for k in keys) or len(set(keys)) != len(keys):
        raise ValueError('Choose valid OpenJutsu model packs.')
    return [groups[key] for key in keys]


def preflight(root, keys, token=''):
    groups = selection(keys)
    if not isinstance(token, str):raise ValueError('Enter a valid Hugging Face read token.')
    for group in groups:
        if group.get('gated') and not token.strip() and not all(available(root, f) for f in group['files']):
            raise ValueError('FLUX relighting requires Hugging Face access. Accept the model\'s conditions using the link in OpenJutsu setup and enter your read token there.')
    files = {f['sha256']: f for group in groups for f in group['files']}
    if not files:return []
    needed = sum(f['size'] for f in files.values() if not available(root, f))
    if shutil.disk_usage(existing_parent(models_folder(root))).free < needed + 2 * 1024**3:
        raise ValueError(f'OpenJutsu needs about {needed / 1024**3:.1f} GB of model downloads plus 2 GB free space. Choose another model folder with enough space.')
    return list(files.values())


def unpack_faces(root, spec, archive, cancel):
    target = path_for(root, spec)
    destination = target.parent / 'models/buffalo_l'
    staging = target.parent / ('.buffalo-' + secrets.token_hex(6))
    staging.mkdir(parents=True)
    try:
        files = {}
        with zipfile.ZipFile(archive) as package:
            if sum(i.file_size for i in package.infolist()) > 1024**3:raise ValueError('Unexpected face-model archive size.')
            for item in package.infolist():
                if cancel.is_set():raise Cancelled('Face model installation cancelled.')
                name = Path(item.filename.replace('\\', '/')).name
                if item.is_dir():continue
                if name not in spec['members'] or name in files:raise ValueError('Unexpected face-model archive member.')
                with package.open(item) as source, (staging / name).open('wb') as output:shutil.copyfileobj(source, output)
                files[name] = item.file_size
        if set(files) != set(spec['members']):raise ValueError('The face-model archive is incomplete.')
        destination.mkdir(parents=True, exist_ok=True)
        for name in files:os.replace(staging / name, destination / name)
        hashes = {name:checksum(destination / name, cancel) for name in files}
        atomic_json(target.with_suffix('.installed.json'), dict(sha256=spec['sha256'], files=files, hashes=hashes))
    finally:
        if staging.exists() and staging.resolve().parent == target.parent.resolve():shutil.rmtree(staging)


def install_models(root, keys, report, cancel, token=''):
    files = preflight(root, keys, token)
    models_folder(root).mkdir(parents=True, exist_ok=True)
    for spec in files:
        if cancel.is_set():raise Cancelled('OpenJutsu model installation cancelled. Verified downloads are preserved.')
        shared = comfy_root(root) / 'models' / spec['folder'] / spec['filename']
        target = path_for(root, spec)
        if spec.get('unpack') and available(root, spec):
            marker = load_json(target.with_suffix('.installed.json'), {})
            destination = target.parent / 'models/buffalo_l'
            if set(marker.get('hashes', {})) == set(spec['members']) and all(
                    checksum(destination / name, cancel) == marker['hashes'][name] for name in spec['members']):
                report('Verified installed face identity models.', 1)
                continue
        if (not spec.get('unpack') and spec['folder'].split('/')[0] in SHARED_CATEGORIES
                and shared != target and shared.is_file() and shared.stat().st_size == spec['size']):
            report('Verifying existing shared model: ' + spec['filename'], None)
            if checksum(shared, cancel) == spec['sha256']:
                report('Reusing shared model: ' + spec['filename'], 1)
                continue
        result = download(spec, target, report, cancel, token)
        if spec.get('unpack'):unpack_faces(root, spec, result, cancel)
    report('Selected OpenJutsu model packs are installed and verified.', 1)


class ManagedEngine:
    def __init__(self, root):
        self.root = Path(root)
        self.process = None
        self.log = None
        self.url = ''

    def start(self, report, cancel):
        import openjutsu
        if not ready(self.root):raise ValueError('Install the managed OpenJutsu backend first.')
        self.close()
        base = folder(self.root)
        data = self.root / 'openjutsu-data'
        data.mkdir(parents=True, exist_ok=True)
        models = models_folder(self.root)
        models.mkdir(parents=True, exist_ok=True)
        shared = comfy_root(self.root) / 'models'
        # JSON is also valid YAML. Read existing Studio models through an extra search path; never move or rename them.
        mapping = {key: key for key in SHARED_CATEGORIES}
        atomic_json(data / 'shared-models.yaml', {'studio': dict(base_path=str(shared), **mapping)})
        from media_storage import media_folder
        output = media_folder(self.root, 'video', load_json(self.root / 'settings.json', {}).get('output', str(self.root / 'Library'))) / 'OpenJutsu'
        output.mkdir(parents=True, exist_ok=True)
        for name in ('input', 'temp', 'profile'):(data / name).mkdir(exist_ok=True)
        port = openjutsu.unused_port()
        names = [n['name'] for n in catalog()['nodes']]
        command = [str(runtime_python(self.root)), '-s', str(resource('openjutsu_backend_worker.py')), str(base), str(models), 'run',
            '--listen', '127.0.0.1', '--port', str(port), '--disable-auto-launch', '--offline',
            '--disable-assets', '--disable-api-nodes', '--front-end-root', str(data / 'frontend'),
            '--disable-all-custom-nodes', '--whitelist-custom-nodes', *names,
            '--models-directory', str(models), '--extra-model-paths-config', str(data / 'shared-models.yaml'),
            '--input-directory', str(data / 'input'), '--temp-directory', str(data / 'temp'),
            '--output-directory', str(output), '--user-directory', str(data / 'profile'),
            '--enable-dynamic-vram', '--disable-pinned-memory', '--vram-headroom', '1']
        log = self.root / 'logs/openjutsu-engine.log'
        log.parent.mkdir(parents=True, exist_ok=True)
        self.log = log.open('w', encoding='utf-8')
        try:
            self.process = subprocess.Popen(command, cwd=base / 'code', env=openjutsu.environment(base),
                stdin=subprocess.DEVNULL, stdout=self.log, stderr=subprocess.STDOUT, creationflags=__import__('common').CREATE_NO_WINDOW)
            self.url = f'http://127.0.0.1:{port}'
            started = time.monotonic()
            deadline = started + 600
            last_report = 0
            while time.monotonic() < deadline:
                if cancel.wait(.5):raise Cancelled('Opening the managed backend cancelled.')
                if self.process.poll() is not None:raise RuntimeError('The managed backend could not start. See logs/openjutsu-engine.log.\n' + log.read_text(errors='replace')[-2000:])
                elapsed = int(time.monotonic() - started)
                if elapsed >= last_report + 5:
                    report(f'Starting the managed backend · {elapsed} s', None)
                    last_report = elapsed
                try:
                    openjutsu.request_json(self.url + '/system_stats', timeout=2)
                    report('Managed OpenJutsu backend ready.', 1)
                    return self.url
                except OSError:pass
            raise RuntimeError('Managed backend startup timed out. See logs/openjutsu-engine.log.')
        except Exception:
            self.close()
            raise

    def close(self):
        from avatar_runtime import stop_process
        if self.process:stop_process(self.process)
        self.process = None
        if self.log:self.log.close()
        self.log = None
        self.url = ''
