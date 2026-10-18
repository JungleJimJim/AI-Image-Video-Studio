"""Sibling image/video storage and a recoverable upgrade from the old layout."""
import hashlib
from pathlib import Path
import shutil
from common import atomic_json, load_json


def media_folder(root, kind, output=None):
    base = Path(output or load_json(Path(root) / 'settings.json', {}).get('output') or Path(root) / 'Library')
    return base / ('Images' if kind == 'image' else 'Videos')


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def replace_paths(value, mapping):
    if isinstance(value, dict):
        return {key: replace_paths(item, mapping) for key, item in value.items()}
    if isinstance(value, list):
        return [replace_paths(item, mapping) for item in value]
    return mapping.get(value, value) if isinstance(value, str) else value


def finish_cleanup(root, journal_file, journal):
    if journal.get('complete'):
        return
    retry = False
    for item in journal.get('files', []):
        source, target = Path(item['source']), Path(item['target'])
        # Never remove a file that was changed after copying or whose copy is missing.
        try:
            if source != target and source.is_file() and target.is_file():
                if digest(source) == item['source_sha256'] and digest(target) == item['target_sha256']:
                    source.unlink()
        except OSError:
            retry = True  # A scanner/file viewer may hold a temporary Windows lock.
        for parent in (source.parent, source.parent.parent):
            if parent in (root, Path(journal['output'])) or not parent.is_relative_to(root):
                continue
            try:
                parent.rmdir()  # Only empty directories; no recursive removal.
            except OSError:
                pass
    journal['complete'] = not retry
    atomic_json(journal_file, journal)


def migrate_library(root, settings):
    root = Path(root).resolve()
    backup = root / 'library-layout-v2'
    journal_file = backup / 'migration.json'
    journal = load_json(journal_file, {})
    if settings.get('media_layout') == 2:
        if journal:
            finish_cleanup(root, journal_file, journal)
        return settings

    backup.mkdir(exist_ok=True)
    names = ('settings.json', 'images.json', 'library.json', 'queue.json')
    for name in names:
        if (root / name).is_file() and not (backup / name).exists():
            shutil.copy2(root / name, backup / name)
    # Retry an interrupted migration from the original indexes; originals remain
    # until every new index and the settings commit have been saved successfully.
    original = load_json(backup / 'settings.json', settings)
    old_output = Path(original.get('output', str(root / 'Videos'))).resolve()
    output = (old_output.parent / 'Library' if old_output.name.casefold() == 'videos'
              else old_output if old_output.name.casefold() == 'library' else old_output / 'Library')
    records = {name: load_json(backup / name, []) for name in ('images.json', 'library.json')}
    mapping, files, reserved = {}, [], set()

    def plan(source, target):
        source, target = Path(source).resolve(), Path(target).resolve()
        if source == target or str(source) in mapping or not source.is_file():
            return
        mapping[str(source)] = str(target)
        files.append(dict(source=str(source), target=str(target), source_sha256=digest(source)))

    for name, items in records.items():
        folder = media_folder(root, 'image' if name == 'images.json' else 'video', output)
        folder.mkdir(parents=True, exist_ok=True)
        for item in items:
            source = Path(item['path']).resolve()
            if not source.is_file() or str(source) in mapping:
                continue
            target = folder / source.name
            counter = 0
            # Preserve an existing destination even if it contains identical bytes.
            while target.resolve() != source and (target in reserved or any(
                    path.exists() for path in (target, target.with_suffix('.json'), target.with_suffix('.mask.png')))):
                counter += 1
                suffix = hashlib.sha256(str(source).encode()).hexdigest()[:8]
                target = folder / f'{source.stem}_{suffix}_{counter}{source.suffix}'
            reserved.add(target)
            plan(source, target)
            # Record paths can have different slash spelling from Path.resolve().
            mapping[item['path']] = str(target.resolve())
            if source.with_suffix('.json').is_file():
                plan(source.with_suffix('.json'), target.with_suffix('.json'))
            if item.get('mask_path'):
                plan(item['mask_path'], target.with_suffix('.mask.png'))
                mapping[item['mask_path']] = str(target.with_suffix('.mask.png').resolve())

    for item in files:
        source, target = Path(item['source']), Path(item['target'])
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.suffix.lower() == '.json':
            atomic_json(target, replace_paths(load_json(source, {}), mapping))
        else:
            shutil.copy2(source, target)
            if digest(target) != item['source_sha256']:
                raise OSError('A library file could not be verified after copying. The original is preserved.')
        item['target_sha256'] = digest(target)

    settings = {**original, 'output': str(output), 'media_layout': 2}
    journal = dict(output=str(output), files=files, complete=False)
    atomic_json(journal_file, journal)
    for name, items in records.items():
        atomic_json(root / name, replace_paths(items, mapping))
    queue = load_json(backup / 'queue.json', None)
    if queue is not None:
        for job in queue.get('jobs', []):
            saved = Path(job.get('output') or old_output).resolve()
            # An old job still gets separate Images and Videos subfolders on retry.
            job['output'] = str(output if saved == old_output else
                                saved.parent / 'Library' if saved.name.casefold() == 'videos' else saved)
        atomic_json(root / 'queue.json', queue)
    atomic_json(root / 'settings.json', settings)  # Commit last, after the indexes.
    finish_cleanup(root, journal_file, journal)
    return settings
