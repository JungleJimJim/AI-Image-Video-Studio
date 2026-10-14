"""Local image imports and safe staging for image-to-video."""
import base64
import binascii
from pathlib import Path
import secrets
import shutil
import subprocess

from common import CREATE_NO_WINDOW, comfy_root, runtime_python


def import_image(root, data, report):
    value = data.get('data', '')
    name = data.get('name', 'Image')
    if not isinstance(value, str) or not value.startswith(('data:image/png;base64,', 'data:image/jpeg;base64,', 'data:image/webp;base64,')):
        raise ValueError('Choose a PNG, JPEG or WebP image.')
    try:
        raw = base64.b64decode(value.split(',',1)[1], validate=True)
    except (ValueError, binascii.Error):
        raise ValueError('The image upload is not valid.') from None
    if not 0 < len(raw) <= 25 * 1024**2:
        raise ValueError('Choose an image no larger than 25 MB.')
    if not runtime_python(root).is_file():
        raise ValueError('Install the base runtime in Settings before importing an image.')
    folder = Path(root) / 'Imported Images'
    folder.mkdir(parents=True, exist_ok=True)
    identifier = secrets.token_hex(12)
    incoming = folder / (identifier + '.upload')
    target = folder / (identifier + '.png')
    report('Checking the selected image…', None)
    incoming.write_bytes(raw)
    # Decode actual pixels, reject oversized/invalid input, honor camera orientation,
    # and retain originals at the user's selected location.
    script = """from PIL import Image,ImageOps
import json,sys,warnings
warnings.simplefilter('error',Image.DecompressionBombWarning)
Image.MAX_IMAGE_PIXELS=25000000
with Image.open(sys.argv[1]) as im:
 if im.format not in ('PNG','JPEG','WEBP'): raise ValueError('Unsupported image format')
 im.seek(0)
 im=ImageOps.exif_transpose(im)
 im.load()
 if im.width*im.height>25000000: raise ValueError('Image exceeds 25 megapixels')
 if 'A' in im.getbands():
  rgba=im.convert('RGBA'); bg=Image.new('RGBA',im.size,'white'); bg.alpha_composite(rgba); im=bg.convert('RGB')
 else: im=im.convert('RGB')
 im.save(sys.argv[2],'PNG')
 print(json.dumps({'width':im.width,'height':im.height}))
"""
    try:
        result = subprocess.run([str(runtime_python(root)), '-s', '-c', script, str(incoming), str(target)],
                                capture_output=True, text=True, timeout=45, creationflags=CREATE_NO_WINDOW)
        if result.returncode:
            raise ValueError('The image could not be decoded. Use a valid PNG, JPEG or WebP under 25 megapixels.')
        import json
        dimensions = json.loads(result.stdout)
        return dict(id=identifier, path=str(target), name=Path(str(name)).name[:200], kind='imported', **dimensions)
    finally:
        incoming.unlink(missing_ok=True)


def stage_image(root, record):
    source = Path(record['path'])
    if not source.is_file():
        raise ValueError('The starting image is missing. Import it again.')
    identifier = record['id']
    if len(identifier) != 24 or any(c not in '0123456789abcdef' for c in identifier):
        raise ValueError('Invalid image library entry.')
    destination = comfy_root(root) / 'input' / ('studio-source-' + identifier + '.png')
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return destination.name
