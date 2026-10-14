"""Shared library, bounded thumbnail queue, and non-destructive CPU editing."""
import base64
import hashlib
import json
import math
from pathlib import Path
import queue
import secrets
import subprocess
import threading
import time
from common import CREATE_NO_WINDOW, comfy_root, resource, runtime_python


def process(root, request, timeout=60):
    python = runtime_python(root)
    if not python.is_file():
        raise ValueError('Install the runtime in Models first.')
    result = subprocess.run([str(python), '-s', str(resource('media_worker.py'))],
        input=json.dumps(request), capture_output=True, text=True, timeout=timeout,
        creationflags=CREATE_NO_WINDOW)
    if result.returncode:
        detail = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else 'Could not read the media.'
        raise ValueError(detail)
    return json.loads(result.stdout)


def record(root, action, source, **options):
    identifier = secrets.token_hex(12)
    folder = Path(root) / 'Library Edits'
    file = folder / (action.title()+'_'+time.strftime('%Y%m%d_%H%M%S')+'_'+identifier[:6]+'.png')
    dimensions = process(root, dict(action=action, source=source['path'], target=str(file), **options))
    return dict(id=identifier, path=str(file), name=file.name, kind=action, parent_id=source['id'],
        created=time.strftime('%Y-%m-%d %H:%M'), options=options, **dimensions)


def crop_options(raw):
    values = {}
    for name, low, high in [('x',0,25000),('y',0,25000),('crop_width',1,25000),('crop_height',1,25000),('width',64,4096),('height',64,4096)]:
        try:
            n = float(raw.get(name))
            if not math.isfinite(n) or not n.is_integer() or not low <= n <= high:
                raise ValueError()
            values[name] = int(n)
        except (ValueError, TypeError, OverflowError):
            raise ValueError(f'Choose a valid whole number for {name.replace("_", " ")}.') from None
    if values['width']*values['height'] > 16_777_216:
        raise ValueError('Resize to at most 16 megapixels.')
    return dict(box=[values[k] for k in ('x','y','crop_width','crop_height')], width=values['width'], height=values['height'])


def stage_mask(root, value, width, height):
    if not isinstance(value,str) or not value.startswith('data:image/png;base64,'):
        raise ValueError('Use a PNG mask painted in the editor.')
    try: data=base64.b64decode(value.split(',',1)[1], validate=True)
    except ValueError: raise ValueError('Invalid mask data.') from None
    if not 0 < len(data) <= 8*1024**2:
        raise ValueError('The mask is too large.')
    folder = comfy_root(root) / 'input'
    folder.mkdir(parents=True,exist_ok=True)
    target = folder / ('studio-mask-'+secrets.token_hex(12)+'.png')
    incoming = target.with_suffix('.upload')
    try:
        incoming.write_bytes(data)
        process(root,dict(action='mask',source=str(incoming),target=str(target),width=width,height=height))
    finally:
        incoming.unlink(missing_ok=True)
    return target.name


def catalog_page(images, videos, query):
    try:
        page = max(0,int(query.get('page',['0'])[0]))
        count = max(1,min(100,int(query.get('count',['24'])[0])))
    except (ValueError,TypeError):
        raise ValueError('Invalid library page.') from None
    kind=query.get('type',['all'])[0]
    search=query.get('search',[''])[0].casefold()[:200]
    records=[{**x,'media_type':'image'} for x in images]+[{**x,'media_type':'video'} for x in videos]
    records=[x for x in records if (kind=='all' or kind==x['media_type']) and search in (x.get('name','')+' '+str(x.get('options',{}).get('prompt',''))).casefold()]
    records.sort(key=lambda x:x.get('created',''),reverse=True)
    return dict(items=records[page*count:(page+1)*count],total=len(records),page=page,count=count)


class Thumbnails:
    def __init__(self,root):
        self.root=Path(root)
        self.queue=queue.Queue(maxsize=200)
        self.pending=set()
        self.failed=set()
        self.lock=threading.Lock()
        self.thread=None
        self.stop=threading.Event()

    def get(self, record, media_type):
        file=Path(record['path'])
        if not file.is_file(): return None
        stat=file.stat()
        stamp=hashlib.sha256(f'{file.resolve()}:{stat.st_size}:{stat.st_mtime_ns}'.encode()).hexdigest()[:20]
        target=self.root/'thumbnails'/(stamp+'.jpg')
        if target.is_file(): return target
        with self.lock:
            if stamp not in self.pending and stamp not in self.failed and not self.queue.full():
                self.pending.add(stamp)
                self.queue.put((stamp,dict(action='thumbnail',source=str(file),target=str(target),media_type=media_type)))
                if not self.thread or not self.thread.is_alive():
                    self.thread=threading.Thread(target=self.work,daemon=True)
                    self.thread.start()
        return None

    def work(self):
        while not self.stop.is_set():
            try: batch=[self.queue.get(timeout=2)]
            except queue.Empty:
                with self.lock:
                    if self.queue.empty():
                        self.thread=None
                        return
                continue
            while len(batch)<16:
                try: batch.append(self.queue.get_nowait())
                except queue.Empty: break
            try: result=process(self.root,[x[1] for x in batch],timeout=90)
            except Exception: result=[{'error':'Thumbnail unavailable'}]*len(batch)
            with self.lock:
                for (key,_), item in zip(batch,result):
                    self.pending.discard(key)
                    if item.get('error'): self.failed.add(key)
