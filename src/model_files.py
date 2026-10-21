"""Shared, content-identified model files; no model-name or architecture guesses."""
import os
from pathlib import Path
import tempfile

from common import comfy_root


def model_path(root, spec):
    return comfy_root(root) / 'models' / spec['folder'] / spec['filename']


def content_id(spec):
    return f"{spec['sha256']}:{spec['size']}"


def unique_files(specs):
    result = {}
    for spec in specs:
        key = str(Path(spec['folder']) / spec['filename']).replace('\\', '/').casefold()
        if key in result and content_id(result[key]) != content_id(spec):
            raise ValueError('Conflicting shared model files in the catalog.')
        result.setdefault(key, spec)
    return list(result.values())


def available_ids(root, specs):
    return {content_id(f) for f in unique_files(specs)
            if model_path(root, f).is_file() and model_path(root, f).stat().st_size == f['size']}


def file_status(root, specs, known_specs=None, available=None):
    """Small stat-only estimates. Installation still verifies SHA-256 before reuse."""
    specs = unique_files(specs)
    if available is None:
        available = available_ids(root, known_specs if known_specs is not None else specs)
    return [dict(id=content_id(f), size=f['size'], remaining=0 if content_id(f) in available else f['size'])
            for f in specs]


def remaining_bytes(root, specs, known_specs=None):
    return sum(x['remaining'] for x in {x['id']:x for x in file_status(root, specs, known_specs)}.values())


def reuse_alias(root, spec, known_specs, report, cancel):
    """Give required filenames hard links to verified identical data on Windows/NTFS."""
    from downloads import Cancelled, checksum
    if cancel.is_set():
        raise Cancelled('Cancelled. Shared model files were kept.')
    destination = model_path(root, spec)
    base = (comfy_root(root) / 'models').resolve()
    if destination.is_symlink() or not destination.resolve().is_relative_to(base):
        raise ValueError('A shared model path points outside the managed models folder.')
    for other in known_specs:
        if content_id(other) != content_id(spec):
            continue
        source = model_path(root, other)
        if source == destination or source.is_symlink() or not source.resolve().is_relative_to(base):
            continue
        if not source.is_file() or source.stat().st_size != spec['size']:
            continue
        if destination.exists() and source.samefile(destination):
            continue  # The normal downloader still verifies the existing data.
        report('Verifying shared file: ' + spec['label'], 0)
        if checksum(source, cancel) != spec['sha256']:
            continue
        if cancel.is_set():
            raise Cancelled('Cancelled. Shared model files were kept.')
        destination.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix='.shared-', dir=destination.parent)
        os.close(fd)
        temporary = Path(temporary)
        temporary.unlink()
        try:
            os.link(source, temporary)
            os.replace(temporary, destination)
        except OSError as error:
            raise RuntimeError('This drive could not share an existing model file. No second copy was downloaded. '
                               'Use an NTFS data drive with hard-link support and retry.') from error
        finally:
            temporary.unlink(missing_ok=True)
        report('Reused shared file: ' + spec['label'], 1)
        return True
    return False
