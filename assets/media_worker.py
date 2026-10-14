"""CPU-only media operations, executed by the installed Pillow/PyAV runtime."""
import json
from pathlib import Path
import sys
import warnings
from PIL import Image, ImageOps

warnings.simplefilter('error', Image.DecompressionBombWarning)
Image.MAX_IMAGE_PIXELS = 25_000_000


def video_frame(path, seconds=0):
    import av
    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        duration = float(stream.duration * stream.time_base) if stream.duration else container.duration / av.time_base if container.duration else None
        if duration is not None and seconds >= duration:
            raise ValueError('Choose a frame position inside the video.')
        if seconds > 0:
            container.seek(max(0, int(seconds / stream.time_base)), stream=stream, backward=True)
        last = None
        for frame in container.decode(stream):
            last = frame
            if frame.time is None or frame.time + .0001 >= seconds:
                return frame.to_image().convert('RGB')
        if last:
            return last.to_image().convert('RGB')
    raise ValueError('No readable frame at this position.')


def image(path):
    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im)
        im.load()
        return im.convert('RGB')


def run(o):
    action = o['action']
    target = Path(o['target'])
    target.parent.mkdir(parents=True, exist_ok=True)
    if action == 'thumbnail':
        im = video_frame(o['source']) if o['media_type']=='video' else image(o['source'])
        ImageOps.fit(im, (256,256), method=Image.Resampling.LANCZOS).save(target, 'JPEG', quality=85)
        return {}
    if action == 'frame':
        im = video_frame(o['source'], o['timestamp'])
    elif action == 'crop':
        im = image(o['source'])
        x,y,w,h = o['box']
        if x < 0 or y < 0 or w < 1 or h < 1 or x+w > im.width or y+h > im.height:
            raise ValueError('Crop rectangle must be inside the image.')
        im = im.crop((x,y,x+w,y+h)).resize((o['width'],o['height']), Image.Resampling.LANCZOS)
    elif action == 'mask':
        im = image(o['source']).getchannel('R')
        if im.size != (o['width'],o['height']):
            raise ValueError('The mask dimensions do not match the output size.')
        if not im.getbbox():
            raise ValueError('Paint an area to edit, or turn off the mask.')
        im = im.convert('RGB')
    else:
        raise ValueError('Unknown media operation.')
    im.save(target, 'PNG')
    return dict(width=im.width, height=im.height)


if __name__ == '__main__':
    request = json.load(sys.stdin)
    if isinstance(request, list):
        result=[]
        for item in request:
            try: result.append({'ok':True, **run(item)})
            except Exception as e: result.append({'error':str(e)})
        print(json.dumps(result))
    else:
        print(json.dumps(run(request)))
