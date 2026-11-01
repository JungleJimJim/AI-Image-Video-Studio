"""Full OpenJutsu workspace with a managed or optional external ComfyUI backend."""
import json
import os
from pathlib import Path, PurePosixPath
import secrets
import shutil
import socket
import stat
import subprocess
import threading
import time
import urllib.parse
import urllib.request
import zipfile

from common import CREATE_NO_WINDOW, atomic_json, load_json, resource, runtime_python
from downloads import Cancelled, download

BRIDGE_VERSION = 2
DEFAULT_BACKEND = 'http://127.0.0.1:8188'


def catalog():
    return json.loads(resource('openjutsu.json').read_text(encoding='utf-8'))


def folder(root):
    return Path(root) / 'extensions/openjutsu'


def local_url(value):
    """Only a literal loopback origin, with no credentials, path, query or fragment."""
    try:
        parsed = urllib.parse.urlsplit(value.strip()) if isinstance(value, str) else None
        if (not parsed or parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost', '::1')
                or parsed.username or parsed.password or parsed.path not in ('', '/')
                or parsed.query or parsed.fragment or not parsed.port):
            raise ValueError()
        host = '[::1]' if parsed.hostname == '::1' else '127.0.0.1'
        return f'http://{host}:{parsed.port}'
    except (ValueError, AttributeError):
        raise ValueError('Enter a local HTTP address with a port, such as http://127.0.0.1:8188.') from None


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def request_json(url, timeout=5):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    with opener.open(url, timeout=timeout) as response:
        raw = response.read(16 * 1024**2 + 1)
    if len(raw) > 16 * 1024**2:
        raise ValueError('The local service returned an unexpectedly large response.')
    return json.loads(raw)


def ready(root):
    base = folder(root)
    marker = load_json(base / 'installed.json', {})
    return (marker.get('revision') == catalog()['revision'] and marker.get('bridge') == BRIDGE_VERSION
            and runtime_python(root).is_file() and (base / 'node/node.exe').is_file()
            and (base / 'code/.next/BUILD_ID').is_file()
            and (base / 'code/node_modules/next/dist/bin/next').is_file()
            and (base / 'dependencies/comfy_api_proxy/cli.py').is_file())


def extract(archive, destination, cancel):
    destination = Path(destination).resolve()
    with zipfile.ZipFile(archive) as package:
        if sum(item.file_size for item in package.infolist()) > 600 * 1024**2:
            raise ValueError('The OpenJutsu archive is unexpectedly large.')
        for item in package.infolist():
            if cancel.is_set():
                raise Cancelled('OpenJutsu installation cancelled.')
            path = PurePosixPath(item.filename)
            if (path.is_absolute() or '..' in path.parts or '\\' in item.orig_filename
                    or any(':' in part for part in path.parts)
                    or stat.S_ISLNK(item.external_attr >> 16)):
                raise ValueError('Unsafe OpenJutsu archive path.')
            if len(path.parts) < 2 or item.is_dir():
                continue
            target = (destination / Path(*path.parts[1:])).resolve()
            if not target.is_relative_to(destination):
                raise ValueError('Unsafe OpenJutsu archive destination.')
            target.parent.mkdir(parents=True, exist_ok=True)
            with package.open(item) as source, target.open('wb') as output:
                shutil.copyfileobj(source, output)


def patch_bridge(code):
    """Allow framing by this Studio session only, retaining upstream API origin checks."""
    path = code / 'next.config.ts'
    source = path.read_text(encoding='utf-8')
    for line in ('  { key: "X-Frame-Options", value: "DENY" },\n',
                 '  { key: "Content-Security-Policy", value: "frame-ancestors \'none\'" },\n'):
        if source.count(line) != 1:
            raise ValueError('OpenJutsu framing headers changed; the integration needs review.')
        source = source.replace(line, '')
    path.write_text(source, encoding='utf-8')
    path = code / 'proxy.ts'
    source = path.read_text(encoding='utf-8')
    old = '  return authorize(request) ?? NextResponse.next();'
    if source.count(old) != 1:
        raise ValueError('OpenJutsu access middleware changed; the integration needs review.')
    source = source.replace(old, '''  const response = authorize(request) ?? NextResponse.next();
  const parent = process.env.STUDIO_PARENT_ORIGIN ?? "";
  const allowed = /^http:\\/\\/127\\.0\\.0\\.1:[0-9]{1,5}$/.test(parent);
  response.headers.set("Content-Security-Policy", "frame-ancestors " + (allowed ? parent : "'none'"));
  if (!allowed) response.headers.set("X-Frame-Options", "DENY");
  return response;''')
    path.write_text(source, encoding='utf-8')
    # Each start supplies these explicitly; no cloud credentials or user .env files are copied.
    (code / '.env.example').unlink(missing_ok=True)
    from openjutsu_backend import catalog as backend_catalog
    defaults = backend_catalog()['defaults']
    model = code / 'lib/model.ts'
    model.write_text(model.read_text(encoding='utf-8').replace('qwen3vl_32b_minimax_h3_int4_convrot.safetensors', defaults['encoder']), encoding='utf-8')
    picture = code / 'lib/picture.ts'
    picture.write_text(picture.read_text(encoding='utf-8')
        .replace('qwen3vl_32b_minimax_h3_int4_convrot.safetensors', defaults['encoder'])
        .replace('solarRank: 384, ...solarLoraFiles(384)', 'solarRank: 64, ...solarLoraFiles(64)'), encoding='utf-8')
    for workflow in (code / 'workflows/picture').glob('*.api.json'):
        source = workflow.read_text(encoding='utf-8').replace('flux2-vae.safetensors', defaults['flux_vae']).replace('qwen3vl_4b_fp8_scaled.safetensors', defaults['flux_encoder'])
        workflow.write_text(source, encoding='utf-8')


def environment(base, **extra):
    return {**os.environ, 'SSLKEYLOGFILE': '', 'NEXT_TELEMETRY_DISABLED': '1',
            'PYTHONDONTWRITEBYTECODE': '1', 'COMFY_API_KEY': '', 'OPENJUTSU_PASSWORD': '',
            'NPM_CONFIG_CACHE': str(base.parent.parent / 'downloads/openjutsu/npm-cache'),
            'PATH': str(base / 'node') + os.pathsep + os.environ.get('PATH', ''), **extra}


def wait_process(command, cwd, env, log, report, cancel, label):
    from avatar_runtime import stop_process
    with log.open('a', encoding='utf-8') as stream:
        process = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                   stdout=stream, stderr=subprocess.STDOUT, creationflags=CREATE_NO_WINDOW)
        try:
            started = time.monotonic()
            while process.poll() is None:
                if cancel.wait(.3):
                    raise Cancelled('OpenJutsu installation cancelled.')
                if time.monotonic() - started > 1200:
                    raise RuntimeError(label + ' timed out after 20 minutes. Retry installation; verified downloads are retained.')
                report(f'{label} · {int(time.monotonic() - started)} s', None)
            if process.returncode:
                raise RuntimeError(label + ' failed. See logs/' + log.name + '.\n' + log.read_text(errors='replace')[-1800:])
        finally:
            if process.poll() is None:
                stop_process(process)


def install(root, report, cancel):
    if not runtime_python(root).is_file():
        raise ValueError('Install the Studio base runtime in Models or Settings first.')
    config = catalog()
    base = folder(root)
    base.parent.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(base.parent).free < 3 * 1024**3:
        raise ValueError('Allow at least 3 GB free for the optional OpenJutsu app and build files.')
    cache = Path(root) / 'downloads/openjutsu'
    cache.mkdir(parents=True, exist_ok=True)
    specs = [config['archive'], config['node'], *config['wheels']]
    paths = [download(spec, cache / spec['filename'], report, cancel) for spec in specs]
    staging = base.parent / ('.openjutsu-install-' + secrets.token_hex(6))
    backup = base.parent / ('.openjutsu-previous-' + secrets.token_hex(6))
    installed = False
    staging.mkdir()
    log = Path(root) / 'logs/openjutsu-install.log'
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text('', encoding='utf-8')
    try:
        extract(paths[0], staging / 'code', cancel)
        extract(paths[1], staging / 'node', cancel)
        patch_bridge(staging / 'code')
        env = environment(staging)
        run = lambda cmd, label: wait_process(cmd, staging / 'code', env, log, report, cancel, label)
        run([str(runtime_python(root)), '-s', '-m', 'pip', 'install', '--no-index', '--no-deps',
             '--target', str(staging / 'dependencies'), *map(str, paths[2:])], 'Installing isolated OpenJutsu proxy')
        run([str(runtime_python(root)), '-s', str(resource('openjutsu_worker.py')), str(staging), 'patch'],
            'Applying upstream progress fixes')
        node = str(staging / 'node/node.exe')
        npm = str(staging / 'node/node_modules/npm/bin/npm-cli.js')
        run([node, npm, 'ci', '--no-audit', '--no-fund'], 'Installing locked OpenJutsu app dependencies')
        run([node, str(staging / 'code/node_modules/next/dist/bin/next'), 'build'], 'Building all OpenJutsu modes')
        if cancel.is_set():
            raise Cancelled('OpenJutsu installation cancelled.')
        if not (staging / 'code/.next/BUILD_ID').is_file():
            raise RuntimeError('OpenJutsu did not produce a production build.')
        atomic_json(staging / 'installed.json', dict(revision=config['revision'], bridge=BRIDGE_VERSION))
        if base.exists():
            base.rename(backup)
        try:
            staging.rename(base)
            installed = True
        except Exception:
            if backup.exists():
                backup.rename(base)
            raise
        report('OpenJutsu app installed. Its managed backend is available in OpenJutsu setup.', 1)
    finally:
        for temporary in (staging, *([backup] if installed else [])):
            if temporary.exists() and temporary.resolve().parent == base.parent.resolve():
                shutil.rmtree(temporary)


def unused_port(preferred=None):
    with socket.socket() as sock:
        try:
            sock.bind(('127.0.0.1', preferred or 0))
        except OSError:
            sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


class Workspace:
    def __init__(self, root):
        self.root = Path(root)
        self.processes = []
        self.logs = []
        self.url = ''
        self.http_ready = False
        self.lock = threading.RLock()
        saved = load_json(self.root / 'openjutsu-settings.json', {})
        if not isinstance(saved, dict):saved = {}
        try:
            self.backend = local_url(saved.get('backend', DEFAULT_BACKEND))
        except (ValueError, AttributeError):
            self.backend = DEFAULT_BACKEND
        port = saved.get('app_port')
        self.app_port = port if type(port) is int and 1024 <= port <= 65535 else None
        self.check_result = None
        self.mode = saved.get('mode', 'external' if 'backend' in saved else 'managed')
        if self.mode not in ('managed', 'external'):self.mode = 'managed'
        self.external_backend = self.backend
        from openjutsu_backend import ManagedEngine
        self.engine = ManagedEngine(self.root)

    @property
    def processes_alive(self):
        return (bool(self.processes) and all(process.poll() is None for process in self.processes)
                and (self.mode == 'external' or (self.engine.process is not None and self.engine.process.poll() is None)))

    @property
    def running(self):
        return self.http_ready and self.processes_alive

    def snapshot(self):
        from openjutsu_backend import inventory
        return dict(ready=ready(self.root), running=self.running, owned=bool(self.processes), url=self.url if self.running else '',
                    backend=self.backend, mode=self.mode, managed=inventory(self.root), check=self.check_result, source=catalog()['repository'])

    def configure(self, value, mode=None, models=None):
        with self.lock:
            if self.processes:
                raise ValueError('Stop the OpenJutsu workspace before changing its backend.')
            chosen = mode or 'external'
            if chosen not in ('managed', 'external'):raise ValueError('Choose Managed or External backend.')
            target = local_url(value) if chosen == 'external' else self.external_backend
            from openjutsu_backend import validate_models_folder, models_folder
            directory = validate_models_folder(models) if models is not None else models_folder(self.root)
            from openjutsu_backend import folder as backend_folder
            if directory.is_relative_to(backend_folder(self.root).resolve()) or directory.is_relative_to(folder(self.root).resolve()):
                raise ValueError('Choose a model folder outside the managed software folders so repairs preserve the weights.')
            self.mode = chosen
            self.backend = self.external_backend = target
            atomic_json(self.root / 'openjutsu-settings.json', dict(backend=target, mode=chosen, models=str(directory), app_port=self.app_port))
            self.check_result = None

    def check(self):
        """Inspect registered nodes only. Per-mode model checks remain in OpenJutsu."""
        if self.mode == 'managed' and not self.engine.process:
            self.check_result = dict(connected=False, error='Open the workspace to start the managed backend. Installation checks its nodes on CPU.', missing=[])
            return self.check_result
        try:
            stats = request_json(self.backend + '/system_stats')
            nodes = request_json(self.backend + '/object_info', timeout=15)
            if not isinstance(stats, dict) or not isinstance(nodes, dict):
                raise ValueError('Invalid ComfyUI response.')
            groups = catalog()['node_groups']
            missing = [{**group, 'missing': [node for node in group['nodes'] if node not in nodes]}
                       for group in groups if any(node not in nodes for node in group['nodes'])]
            self.check_result = dict(connected=True, missing=missing,
                                     version=stats.get('system', {}).get('comfyui_version', 'unknown'))
        except (OSError, ValueError) as error:
            self.check_result = dict(connected=False, error=str(error)[:600], missing=[])
        return self.check_result

    def start(self, parent, report, cancel):
        parent = local_url(parent)
        if not parent.startswith('http://127.0.0.1:'):
            raise ValueError('The Studio parent must use IPv4 loopback.')
        with self.lock:
            if self.running:
                return self.url
            self.close()
            if not ready(self.root):
                raise ValueError('Install the OpenJutsu app first.')
            base = folder(self.root)
            app_port, proxy_port = unused_port(self.app_port), unused_port()
            while app_port == proxy_port:
                proxy_port = unused_port()
            self.app_port = app_port
            saved = load_json(self.root / 'openjutsu-settings.json', {})
            atomic_json(self.root / 'openjutsu-settings.json', {**saved, 'backend': self.external_backend, 'mode': self.mode, 'app_port': app_port})
            proxy_token = secrets.token_urlsafe(32)
            try:
                if self.mode == 'managed':self.backend = self.engine.start(report, cancel)
                env = environment(base, COMFYUI_URL=self.backend, COMFY_BASE_URL=f'http://127.0.0.1:{proxy_port}',
                                  COMFY_API_KEY=proxy_token, STUDIO_PARENT_ORIGIN=parent)
                commands = [
                [str(runtime_python(self.root)), '-s', str(resource('openjutsu_worker.py')), str(base), 'proxy',
                 'run', '--comfyui', self.backend, '--host', '127.0.0.1', '--port', str(proxy_port),
                 '--max-upload-mb', '500', '--token', proxy_token, '--state-dir', str(base / 'proxy-state')],
                [str(base / 'node/node.exe'), str(base / 'code/node_modules/next/dist/bin/next'),
                 'start', '--hostname', '127.0.0.1', '--port', str(app_port)],
                ]
                for name, command in zip(('proxy', 'app'), commands):
                    log = self.root / f'logs/openjutsu-{name}.log'
                    log.parent.mkdir(parents=True, exist_ok=True)
                    stream = log.open('w', encoding='utf-8')
                    self.logs.append(stream)
                    self.processes.append(subprocess.Popen(command, cwd=base / 'code', env=env,
                        stdin=subprocess.DEVNULL, stdout=stream, stderr=subprocess.STDOUT, creationflags=CREATE_NO_WINDOW))
                self.url = f'http://127.0.0.1:{app_port}'
                deadline = time.monotonic() + 90
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
                while time.monotonic() < deadline:
                    if cancel.wait(.3):
                        raise Cancelled('Opening OpenJutsu cancelled.')
                    if not self.processes_alive:
                        raise RuntimeError('OpenJutsu could not start. See logs/openjutsu-app.log and openjutsu-proxy.log.')
                    try:
                        with opener.open(self.url, timeout=2) as response:
                            if response.status == 200 and request_json(f'http://127.0.0.1:{proxy_port}/api/v2/health',timeout=2).get('status') == 'healthy':
                                self.http_ready = True
                                report('OpenJutsu workspace ready. Its jobs run in its own backend.', 1)
                                return self.url
                    except OSError:
                        pass
                raise RuntimeError('OpenJutsu startup timed out. See logs/openjutsu-app.log.')
            except Exception:
                self.close()
                raise

    def stop(self):
        # Stopping the web app cannot cancel an externally owned ComfyUI render.
        # Keep its live progress available until the backend is idle.
        if self.processes:
            try:
                queue = request_json(self.backend + '/queue')
                if queue.get('queue_running') or queue.get('queue_pending'):
                    raise ValueError('Finish or cancel OpenJutsu jobs in its workspace before stopping it.')
            except OSError:
                self.close()
                return False
        self.close()
        return True

    def close(self):
        from avatar_runtime import stop_process
        with self.lock:
            for process in reversed(self.processes):
                stop_process(process)
            self.processes.clear()
            for stream in self.logs:
                stream.close()
            self.logs.clear()
            self.url = ''
            self.http_ready = False
            self.engine.close()
            self.backend = self.external_backend
