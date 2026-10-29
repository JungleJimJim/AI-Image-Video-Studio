"""Recoverable Library deletion, restoration and bounded ZIP exports. No inference."""
from pathlib import Path
import os
import hashlib
import re
import secrets
import shutil
import stat
import time
import zipfile
from common import atomic_json, load_json
from media_storage import metadata_path

MAX_SELECTION = 500

def identifiers(raw):
    if not isinstance(raw, list) or not 1 <= len(raw) <= MAX_SELECTION:
        raise ValueError('Select between 1 and 500 Library items.')
    if any(not isinstance(x, str) or not 1 <= len(x) <= 128 for x in raw):
        raise ValueError('Invalid Library selection.')
    return list(dict.fromkeys(raw))

def selected(images, videos, raw):
    ids = identifiers(raw)
    records = {x['id']: {**x, 'media_type': kind} for values, kind in ((images, 'image'), (videos, 'video')) for x in values}
    if any(x not in records for x in ids):
        raise ValueError('Some selected items are no longer in Library. Refresh and select them again.')
    return [records[x] for x in ids]

def references(value, ids, paths):
    if isinstance(value, dict):
        return any(references(v, ids, paths) for v in value.values())
    if isinstance(value, list):
        return any(references(v, ids, paths) for v in value)
    return isinstance(value, str) and (value in ids or value in paths)

def regular_file(path):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
        raise ValueError('Only ordinary Library files can be moved or exported.')
    return info

def index_write(root, images, videos):
    atomic_json(Path(root) / 'images.json', images)
    atomic_json(Path(root) / 'library.json', videos)

def manifest_path(root, token):
    if not isinstance(token, str) or not re.fullmatch('[0-9a-f]{32}', token):
        raise ValueError('Invalid Trash entry.')
    return Path(root) / 'library-trash' / (token + '.json')

def rollback(root, manifest, journal):
    restoring = journal['status'] == 'restoring'
    for move in reversed(journal['moves']):
        origin, target = Path(move['source']), Path(move['target'])
        source, destination = (origin, target) if restoring else (target, origin)
        if source.exists():
            if destination.exists():
                raise ValueError('A file at the recovery location changed. Both copies have been preserved.')
            destination.parent.mkdir(parents=True, exist_ok=True)
            source.rename(destination)
    index_write(root, journal['before_images'], journal['before_videos'])
    journal['status'] = 'trashed' if restoring else 'rolled_back'
    journal.pop('before_images', None); journal.pop('before_videos', None)
    atomic_json(manifest, journal)

def recover(root):
    warnings = []
    for manifest in (Path(root) / 'library-trash').glob('*.json'):
        journal = load_json(manifest, {})
        if journal.get('status') in ('pending', 'restoring'):
            try:
                rollback(root, manifest, journal)
            except (OSError, ValueError, KeyError) as error:
                warnings.append('Library Trash recovery needs attention: ' + str(error))
    return warnings

def trash(root, images, videos, raw):
    items = selected(images, videos, raw)
    ids = {x['id'] for x in items}
    token = secrets.token_hex(16)
    manifest = manifest_path(root, token)
    # A shared physical file survives while another Library record still references it.
    kept_paths = {os.path.normcase(str(Path(x[key]).absolute())) for x in [*images, *videos] if x['id'] not in ids for key in ('path', 'mask_path') if x.get(key)}
    files = {}
    for item in items:
        primary = Path(item['path']).absolute()
        candidates = [primary]
        if item.get('mask_path'):
            candidates.append(Path(item['mask_path']).absolute())
        for sidecar in (metadata_path(primary), primary.with_suffix('.json')):
            if sidecar.is_file() and sidecar.stat().st_size < 8 * 1024**2:
                content = load_json(sidecar, {})
                if isinstance(content, dict) and content.get('id') == item['id']:
                    candidates.append(sidecar)
        for source in candidates:
            source = source.absolute()
            if os.path.normcase(str(source)) in kept_paths or not source.exists() or os.path.normcase(str(source)) in files:
                continue
            info = regular_file(source)
            target = source.parent / '.studio-trash' / token / (str(len(files)) + '-' + source.name)
            if target.exists():
                raise ValueError('A Trash destination already exists.')
            files[os.path.normcase(str(source))] = dict(source=str(source), target=str(target), size=info.st_size, modified=info.st_mtime_ns)
    journal = dict(id=token, status='pending', created=time.strftime('%Y-%m-%d %H:%M:%S'), items=items,
                   moves=list(files.values()), before_images=images, before_videos=videos)
    atomic_json(manifest, journal)
    try:
        for move in journal['moves']:
            source, target = Path(move['source']), Path(move['target'])
            info = regular_file(source)
            if (info.st_size, info.st_mtime_ns) != (move['size'], move['modified']):
                raise ValueError('A selected file changed. Refresh before deleting it.')
            target.parent.mkdir(parents=True, exist_ok=True)
            source.rename(target)
        remaining_images = [x for x in images if x['id'] not in ids]
        remaining_videos = [x for x in videos if x['id'] not in ids]
        index_write(root, remaining_images, remaining_videos)
        journal['status'] = 'trashed'
        journal.pop('before_images'); journal.pop('before_videos')
        atomic_json(manifest, journal)
    except Exception:
        # Reload the pre-commit journal so rollback retains the original index snapshots.
        pending = load_json(manifest, {})
        if pending.get('status') == 'pending':
            rollback(root, manifest, pending)
        raise
    return dict(images=remaining_images, videos=remaining_videos, batch=token, deleted=list(ids), count=len(ids))

def trash_list(root):
    result = []
    for path in (Path(root) / 'library-trash').glob('*.json'):
        value = load_json(path, {})
        if value.get('status') == 'trashed':
            result.append(dict(id=value['id'], created=value['created'], count=len(value['items']),
                               names=[x['name'] for x in value['items'][:5]]))
    return sorted(result, key=lambda x: x['created'], reverse=True)

def restore(root, images, videos, token):
    manifest = manifest_path(root, token)
    journal = load_json(manifest, {})
    if journal.get('status') != 'trashed':
        raise ValueError('That Trash entry is no longer available.')
    existing = {x['id'] for x in [*images, *videos]}
    if any(x['id'] in existing for x in journal['items']):
        raise ValueError('An item with the same ID is already in Library.')
    for move in journal['moves']:
        source, target = Path(move['source']), Path(move['target'])
        if source.exists():
            raise ValueError('A file already exists at the original location. It will not be overwritten.')
        info = regular_file(target)
        if info.st_size != move['size']:
            raise ValueError('A file in Trash changed. Restore it manually to preserve both versions.')
    journal.update(status='restoring', before_images=images, before_videos=videos)
    atomic_json(manifest, journal)
    try:
        for move in journal['moves']:
            source, target = Path(move['source']), Path(move['target'])
            source.parent.mkdir(parents=True, exist_ok=True)
            target.rename(source)
        restored_images = [*images, *[{k:v for k,v in x.items() if k != 'media_type'} for x in journal['items'] if x['media_type'] == 'image']]
        restored_videos = [*videos, *[{k:v for k,v in x.items() if k != 'media_type'} for x in journal['items'] if x['media_type'] == 'video']]
        index_write(root, restored_images, restored_videos)
        journal['status'] = 'restored'
        journal.pop('before_images'); journal.pop('before_videos')
        atomic_json(manifest, journal)
    except Exception:
        rollback(root, manifest, load_json(manifest, {}))
        raise
    return dict(images=restored_images, videos=restored_videos, count=len(journal['items']))

def export_zip(root, items):
    folder = Path(root) / 'temp' / 'library-exports'
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.glob('*.zip'):
        if re.fullmatch('[0-9a-f]{32}.zip', old.name) and time.time() - old.stat().st_mtime > 86400:
            try: old.unlink()
            except OSError: pass
    sizes = []
    for item in items:
        path = Path(item['path'])
        sizes.append(regular_file(path).st_size)
    if shutil.disk_usage(folder).free < sum(sizes) + 16 * 1024**2:
        raise ValueError('Not enough free space to prepare this ZIP export.')
    token = secrets.token_hex(16)
    target = folder / (token + '.zip')
    try:
        with zipfile.ZipFile(target, 'x', compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
            used = set()
            for item in items:
                path = Path(item['path'])
                name = ('Images/' if item['media_type'] == 'image' else 'Videos/') + path.name
                if name.casefold() in used:
                    name = str(Path(name).with_name(path.stem + '-' + hashlib.sha256(item['id'].encode()).hexdigest()[:12] + path.suffix))
                used.add(name.casefold())
                archive.write(path, name)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    return dict(id=token, path=target, name='Studio-Library-' + time.strftime('%Y%m%d-%H%M%S') + '.zip', count=len(items))
