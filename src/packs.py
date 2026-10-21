"""Optional, pinned and checksum-verified model packs."""
import json
from pathlib import Path
import shutil

from common import comfy_root, existing_parent, resource, runtime_python
from downloads import download
import engine_support
from model_files import available_ids, file_status, remaining_bytes, reuse_alias, unique_files


def catalog():
    return json.loads(resource('packs.json').read_text(encoding='utf-8'))


def model_path(root, file):
    return comfy_root(root) / 'models' / file['folder'] / file['filename']


def ready(root, key):
    pack = catalog().get(key)
    return bool(pack and runtime_python(root).is_file() and all(
        model_path(root, f).is_file() and model_path(root, f).stat().st_size == f['size'] for f in pack['files'])
        and (not pack.get('engine') or engine_support.ready(root,pack['engine']))
        and (not pack.get('avatar_runtime') or __import__('avatar_runtime').ready(root)))


def inventory(root):
    result = []
    packs = catalog()
    known = manifest_files() + [f for pack in packs.values() for f in pack['files']]
    available = available_ids(root, known)
    for key, pack in packs.items():
        statuses = file_status(root, pack['files'], available=available)
        remaining = sum(x['remaining'] for x in {x['id']:x for x in statuses}.values())
        result.append({k:v for k,v in pack.items() if k != 'files'} | dict(
            id=key, ready=ready(root, key), size=sum(f['size'] for f in pack['files']), remaining=remaining,
            download_files=statuses,
            engine_ready=(not pack.get('engine') or engine_support.ready(root,pack['engine']))
                         and (not pack.get('avatar_runtime') or __import__('avatar_runtime').ready(root))))
    return result


def manifest_files():
    from common import manifest
    return manifest()['models']


def install(root, keys, report, cancel, token=''):
    if not isinstance(token,str):raise ValueError('Enter a valid Hugging Face read token.')
    if not isinstance(keys, list) or not keys or any(not isinstance(k, str) for k in keys) or len(set(keys)) != len(keys):
        raise ValueError('Choose one or more different model packs.')
    packs = catalog()
    if any(key not in packs for key in keys):
        raise ValueError('Unknown model pack.')
    for key in keys:
        pack=packs[key]
        if pack.get('gated') and not token.strip() and any(not model_path(root,f).is_file()
                or model_path(root,f).stat().st_size!=f['size'] for f in pack['files']):
            raise ValueError('FLUX 3 requires Hugging Face access. Open its model page in Models, accept the access conditions, and enter a read token for that account in Settings before installing.')
    if not runtime_python(root).is_file():
        raise ValueError('Install the base runtime in Settings first.')
    # Encoders and VAEs shared by packs are downloaded and counted only once.
    files = unique_files(f for key in keys for f in packs[key]['files'])
    known = unique_files(manifest_files() + [f for pack in packs.values() for f in pack['files']])
    remaining = remaining_bytes(root, files, known)
    reserve=3 if any(packs[key].get('avatar_runtime') for key in keys) else 2
    if shutil.disk_usage(existing_parent(root)).free < remaining + reserve * 1024**3:
        raise ValueError(f'Allow {remaining/1024**3 + reserve:.1f} GB free for the selected packs.')
    for key in keys:
        if packs[key].get('engine'):engine_support.install(root,packs[key]['engine'],report,cancel)
    if any(packs[key].get('avatar_runtime') for key in keys):
        from avatar_runtime import install as install_avatar_runtime
        install_avatar_runtime(root,report,cancel)
    for f in files:
        if not reuse_alias(root, f, known, report, cancel):
            download(f, model_path(root, f), report, cancel, token)
    report('Selected model packs are installed and verified.', 1)
