"""User-requested GitHub updates. No model, settings or media migration."""
from copy import deepcopy
import ctypes
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

from common import (APP_EXE, APP_NAME, CREATE_NO_WINDOW, VERSION, atomic_json,
                    check_data_path, check_install_path, installed_data_path, load_json)
from downloads import Cancelled, download

REPOSITORY = 'https://github.com/JungleJimJim/AI-Image-Video-Studio'
LATEST = 'https://api.github.com/repos/JungleJimJim/AI-Image-Video-Studio/releases/latest'


def version_tuple(value):
    if not isinstance(value, str) or not re.fullmatch(r'v?\d{1,5}\.\d{1,5}\.\d{1,5}', value):
        raise ValueError('GitHub did not return a supported stable version number.')
    return tuple(int(part) for part in value.removeprefix('v').split('.'))


def latest_release():
    request = urllib.request.Request(LATEST, headers={
        'User-Agent': 'AI-Image-Video-Studio/' + VERSION, 'Accept': 'application/vnd.github+json'})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            data = response.read(1024 * 1024 + 1)
        if len(data) > 1024 * 1024:
            raise ValueError('The GitHub release response was too large.')
        return json.loads(data)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            raise ValueError('No published update was found on GitHub.') from None
        raise ValueError(f'GitHub could not check for updates (HTTP {error.code}). Try again later.') from None
    except (OSError, ValueError) as error:
        raise ValueError('Could not check GitHub for updates. Check your connection and try again.') from error


def release_offer(release, current):
    if not isinstance(release, dict) or release.get('draft') is not False or release.get('prerelease') is not False:
        raise ValueError('Only published stable GitHub releases can be installed.')
    tag = release.get('tag_name', '')
    available = version_tuple(tag) > version_tuple(current)
    version = tag.removeprefix('v')
    public = dict(current=current, version=version, available=available,
                  url=REPOSITORY + '/releases/tag/' + tag, notes=str(release.get('body') or '')[:12000])
    if not available:
        return public, None
    name = 'AIImageVideoStudio-Setup-' + version + '.exe'
    files = [asset for asset in release.get('assets', []) if asset.get('name') == name]
    if len(files) != 1:
        raise ValueError('The new release does not have a Windows installer yet. Try again later.')
    asset = files[0]
    expected = REPOSITORY + '/releases/download/' + tag + '/' + name
    digest, size = asset.get('digest', ''), asset.get('size')
    if asset.get('browser_download_url') != expected or asset.get('state') != 'uploaded':
        raise ValueError('The release installer is not available from the expected GitHub repository.')
    if not isinstance(digest, str) or not re.fullmatch(r'sha256:[a-fA-F0-9]{64}', digest):
        raise ValueError('GitHub has not supplied a SHA-256 checksum for this installer. Try again later.')
    if type(size) is not int or not 0 < size <= 1024**3:
        raise ValueError('The release installer has an unsupported size.')
    public['bytes'] = size
    return public, dict(label='Studio update ' + version, filename=name, size=size,
                        sha256=digest[7:].lower(), url=expected)


def process_identity(pid):
    """Capture an exact Windows process identity, including PID reuse protection."""
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE,wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    handle = kernel.OpenProcess(0x1000 | 0x100000, False, pid)
    if not handle:
        if ctypes.get_last_error() in (87, 1168):return None
        raise OSError('Could not inspect the studio process for a safe update.')
    try:
        if kernel.WaitForSingleObject(handle,0)==0:return None
        times = [wintypes.FILETIME() for _ in range(4)]
        path = ctypes.create_unicode_buffer(32768)
        size = wintypes.DWORD(len(path))
        if not kernel.GetProcessTimes(handle, *(ctypes.byref(value) for value in times)) or not kernel.QueryFullProcessImageNameW(handle, 0, path, ctypes.byref(size)):
            if kernel.WaitForSingleObject(handle,0)==0:return None
            raise OSError('Could not read the studio process identity.')
        created = (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
        return dict(pid=pid, created=created, path=str(Path(path.value).resolve()))
    finally:
        kernel.CloseHandle(handle)


def wait_for_exit(records, timeout=90):
    deadline = time.monotonic() + timeout
    while True:
        # A reused PID is a different process. Never stop any process here.
        if not any(process_identity(record['pid']) == record for record in records):return
        if time.monotonic() >= deadline:
            raise RuntimeError('The studio has not finished closing. Its files were not replaced. Close it and try the update again.')
        time.sleep(.25)


def install_context(installation, data):
    if installation is None:
        raise ValueError('Install the packaged Windows app to enable automatic installation of updates.')
    if not isinstance(installation,(str,Path)) or not isinstance(data,(str,Path)):
        raise ValueError('Choose recognized application and studio data folders.')
    installation, data = check_install_path(installation), check_data_path(data)
    if load_json(installation/'studio-install.json', {}).get('app') != APP_NAME or not (installation/APP_EXE).is_file():
        raise ValueError('This is not a recognized studio application installation.')
    if load_json(data/'studio-data.json', {}).get('app') != APP_NAME or installed_data_path(installation) != data:
        raise ValueError('The installed application and studio data folders do not match. Run Setup to repair their registration.')
    return installation, data


class UpdateManager:
    def __init__(self, data, current=VERSION, installation=None):
        self.data, self.current = Path(data).resolve(), current
        self.installation = installation if installation is not None else (Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else None)
        self.lock = threading.RLock()
        self.offer = None
        self.info = dict(status='idle', current=current, available=False, error='')
        try:
            install_context(self.installation, self.data)
            self.info.update(can_install=True, install_reason='')
        except ValueError as error:
            self.info.update(can_install=False, install_reason=str(error))

    def snapshot(self):
        with self.lock:
            return {**deepcopy(self.info), 'last_result':load_json(self.data/'updates/update-result.json', {})}

    def check(self):
        with self.lock:
            if self.info['status'] in ('checking', 'downloading', 'installing'):
                raise ValueError('An update operation is already in progress.')
            self.offer = None
            self.info.update(status='checking', available=False, error='', ticket='')
        try:
            public, spec = release_offer(latest_release(), self.current)
            with self.lock:
                ticket = secrets.token_hex(24) if spec else ''
                self.offer = dict(spec=spec, version=public['version'], ticket=ticket) if spec else None
                self.info.update(public, status='checked', ticket=ticket)
        except Exception as error:
            with self.lock:self.info.update(status='error', error=str(error))
        return self.snapshot()

    def prepare(self, ticket, report, cancel):
        installation, data = install_context(self.installation, self.data)
        with self.lock:
            offer = deepcopy(self.offer)
            if not offer or not isinstance(ticket, str) or not secrets.compare_digest(ticket, offer['ticket']):
                raise ValueError('Check for updates again before installing.')
            if self.info['status'] != 'checked':raise ValueError('An update operation is already in progress.')
            self.info.update(status='downloading', error='')
        try:
            folder = data/'updates'/offer['version']
            folder.mkdir(parents=True, exist_ok=True)
            if shutil.disk_usage(folder).free < offer['spec']['size'] + 100*1024**2:
                raise ValueError('There is not enough free space to download the update.')
            installer = download(offer['spec'], folder/offer['spec']['filename'], report, cancel)
            if cancel.is_set():raise Cancelled('Update download cancelled. The current app is unchanged.')
            records = []
            instance = load_json(data/'.studio-instance.json', {})
            for pid in dict.fromkeys([os.getpid(), os.getppid(), instance.get('desktop_pid')]):
                if type(pid) is int and pid > 0:
                    identity = process_identity(pid)
                    if identity and (pid != os.getppid() or Path(identity['path']) == installation/APP_EXE):records.append(identity)
            request = folder/'apply-update.json'
            atomic_json(request, dict(schema=1, installation=str(installation), data=str(data),
                current=self.current, version=offer['version'], processes=records))
            return installer, request
        except Exception as error:
            with self.lock:self.info.update(status='error', error=str(error))
            raise

    def launch(self, installer, request):
        # The independent installer waits for both frozen-app processes and the host.
        subprocess.Popen([str(installer), '--apply-update', str(request)], cwd=installer.parent,
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=CREATE_NO_WINDOW)
        with self.lock:self.info.update(status='installing')


def apply_update(request, copy_app, elevate, relaunch=True):
    """Run in the downloaded Setup, after the old app has exited."""
    request = Path(request).resolve()
    if request.stat().st_size > 65536:raise ValueError('The update request is too large.')
    data = load_json(request, {})
    if data.get('schema') != 1 or data.get('version') != VERSION:
        raise ValueError('The update request does not match this installer.')
    version_tuple(data.get('current'))
    if version_tuple(VERSION) <= version_tuple(data['current']):raise ValueError('The update must be newer than the installed app.')
    installation, root = install_context(data.get('installation'), data.get('data'))
    if request != root/'updates'/VERSION/'apply-update.json':
        raise ValueError('The update request is outside the studio update folder.')
    records = data.get('processes')
    if not isinstance(records, list) or len(records) > 3 or any(
        not isinstance(record,dict) or set(record)!= {'pid','created','path'} or
        type(record['pid']) is not int or record['pid'] <= 0 or type(record['created']) is not int or
        not isinstance(record['path'],str) for record in records):
        raise ValueError('Invalid studio process identities.')
    result_path = root/'updates/update-result.json'
    try:
        wait_for_exit(records)
        if (root/'.studio-instance.json').exists():
            raise RuntimeError('A studio session is still open. Its files were not replaced.')
        install_context(installation, root)
        if load_json(installation/'studio-install.json', {}).get('version') != data['current']:
            raise ValueError('The installed app changed after the update was requested. Check for updates again.')
        from common import in_program_files
        if in_program_files(installation):elevate(installation)
        else:copy_app(installation)
        # Keep Windows' installed-app version current without changing the data mapping.
        from common import registered_installation, UNINSTALL_KEY
        if registered_installation() == (installation,root):
            import winreg
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER,UNINSTALL_KEY,0,winreg.KEY_SET_VALUE) as key:
                    winreg.SetValueEx(key,'DisplayVersion',0,winreg.REG_SZ,VERSION)
            except OSError:pass
        atomic_json(result_path, dict(ok=True, version=VERSION, message='Studio updated to '+VERSION+'. Settings, models and library media were kept.'))
    except Exception as error:
        atomic_json(result_path, dict(ok=False, version=VERSION, error=str(error)))
        raise
    finally:
        if relaunch and (installation/APP_EXE).is_file():
            subprocess.Popen([str(installation/APP_EXE)], cwd=installation,
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=CREATE_NO_WINDOW)
