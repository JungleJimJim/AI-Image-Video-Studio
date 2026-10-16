"""Desktop studio with a private loopback backend and native Windows window."""
import argparse
import atexit
import http.server
import json
import mimetypes
import os
from pathlib import Path
import secrets
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request

from common import (APP_NAME, CREATE_NO_WINDOW, VERSION, app_root, atomic_json, runtime_ready,
                    gpu_info, install_ready, load_json, manifest, resource)
from downloads import Cancelled, provision
from engine import DEFAULTS, Engine, validate_options
from desktop import activate_desktop, open_desktop
from loras import (download_lora, import_loras, installed_loras, lora_folder, validate_selection,
                   model_catalog as lora_models, validate_model)
from images import import_image, stage_image
from packs import inventory as pack_inventory, ready as pack_ready, install as install_packs
from workflows import IMAGE_DEFAULTS, validate_image_options, validate_edit_options
from media import Thumbnails, catalog_page, crop_options, details as media_details, record as media_record, stage_mask
from resources import ResourceMonitor
from job_queue import JobQueue, ACTIVE
import enhancements
from updates import UpdateManager
from model_removal import removal_plan, uninstall as uninstall_model


class Studio:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.token = secrets.token_urlsafe(32)
        self.settings = load_json(self.root / "settings.json", {"output": str(self.root / "Videos"), "options": DEFAULTS.copy()})
        self.settings.setdefault("output", str(self.root / "Videos"))
        self.settings.setdefault("options", DEFAULTS.copy())
        self.settings.setdefault('wan_loras', self.settings['options'].get('loras', [])
                                 if self.settings['options'].get('model','wan13')=='wan13' else [])
        self.settings.setdefault('model_loras', {})
        self.settings['model_loras'].setdefault('wan13', self.settings['wan_loras'])
        for key in ('options','image_options','edit_options'):
            saved = self.settings.get(key,{})
            if saved.get('model') in lora_models() and saved.get('loras'):
                self.settings['model_loras'].setdefault(saved['model'],saved['loras'])
        self.gpu = gpu_info()
        self.state = {"busy": False, "stage": "Ready" if install_ready(self.root) else "Setup needed", "progress": 0, "error": "", "result": None}
        self.events = []
        self.lock = threading.RLock()
        self.cancel = threading.Event()
        self.engine = Engine(self.root, self.report)
        self.videos = load_json(self.root / "library.json", [])
        self.images = load_json(self.root / 'images.json', [])
        self._last_log = ""
        self.worker = None
        self.resources = ResourceMonitor()
        self.thumbnails = Thumbnails(self.root)
        self.revision = 0
        self.queue = JobQueue(self.root)
        self.closing = False
        self.removing_model = None
        self.updates = UpdateManager(self.root)

    def report(self, message, progress):
        with self.lock:
            self.state.update(stage=message, progress=progress)
            stage = message.split(":")[0].split(" · ")[0]
            if stage != self._last_log:
                self.events.append(time.strftime("%H:%M:%S") + "  " + message)
                self.events = self.events[-100:]
                self._last_log = stage

    def snapshot(self):
        with self.lock:
            if not self.state["busy"] and self.state["stage"] == "Setup needed" and install_ready(self.root):
                self.state["stage"] = "Ready"
            base=manifest()['models']
            from packs import model_path
            base_info=dict(id='wan13',name='NSFW Wan 1.3B · E14',kind='video',family='wan13',
                description='The original text-to-video model. Runtime software remains available if these weights are removed.',
                ready=install_ready(self.root),size=sum(f['size'] for f in base),
                remaining=sum(f['size'] for f in base if not model_path(self.root,f).is_file() or model_path(self.root,f).stat().st_size!=f['size']))
            return {**self.state, "ready": install_ready(self.root), "gpu": self.gpu,
                    'base_model':base_info,
                    "settings": self.settings, "library": self.videos[-30:][::-1],
                    "loras": installed_loras(self.root),
                    'lora_models': list(lora_models().values()),
                    'packs': pack_inventory(self.root), 'images': self.images[-60:][::-1],
                    'runtime_ready': runtime_ready(self.root), 'queue': self.queue.snapshot(),
                    'enhancers': enhancements.inventory(self.root),
                    'updates': self.updates.snapshot(),
                    'resources': self.resources.snapshot(),
                    'library_revision': self.revision, 'library_count': len(self.images)+len(self.videos),
                    "log": self.events[-40:], "root": str(self.root), "version": VERSION}

    def run_job(self, target, queue_id=None):
        with self.lock:
            if self.state["busy"]:
                raise ValueError("Wait for the current operation to finish, or cancel it first.")
            self.cancel.clear()
            self.engine.cancel.clear()
            self.state.update(busy=True, error="", result=None, progress=None, stage="Starting…")
        def work():
            outcome='completed';detail=''
            try:
                target()
            except Cancelled as error:
                outcome='cancelled';detail=str(error)
                self.report(str(error), 0)
            except Exception as error:
                outcome='failed';detail=str(error)
                self.report("Operation failed. See the error below.", 0)
                with self.lock:
                    self.state["error"] = str(error)
                (self.root / "logs").mkdir(exist_ok=True)
                with (self.root / "logs" / "activity.log").open("a", encoding="utf-8") as log:
                    log.write(time.strftime("%Y-%m-%d %H:%M:%S") + " " + str(error) + "\n")
            finally:
                with self.lock:
                    if queue_id:
                        item=self.queue.get(queue_id)
                        item.update(status=outcome,error=detail,finished=time.strftime('%Y-%m-%d %H:%M:%S'))
                        if outcome=='failed' and not self.queue.continue_on_error:self.queue.paused=True
                        if outcome=='completed' and self.state.get('latest_media'):
                            item['result_id']=self.state['latest_media']['id']
                        self.queue.save()
                    self.removing_model=None
                    self.state["busy"] = False
                    self._kick_queue()
        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()

    def generate(self, raw, prepare=False, output=None):
        output=output or self.settings['output']
        options = validate_options(raw)
        options['loras'] = self.selected_loras(options['model'],raw)
        options['upscale']=self.auto_enhancement(raw.get('upscale'), 'video')
        if not (install_ready(self.root) or runtime_ready(self.root)) or (options['model']=='wan13' and not install_ready(self.root)):
            raise ValueError("Install the runtime and model in Settings first.")
        if options['model'] != 'wan13' and not pack_ready(self.root, options['model']):
            raise ValueError('Install the selected video model pack in Settings first.')
        source = None
        if options['mode'] == 'image':
            source = next((x for x in self.images if x['id']==options['source_image']), None)
            if not source or not Path(source['path']).is_file():
                raise ValueError('Choose an existing image from the image library.')
        if options['model'] == 'ltx2':
            options.update(steps=8, cfg=1.0, sampler='euler', scheduler='distilled', shift=1.0)
        def job():
            if source:
                options['input_file'] = stage_image(self.root, source)
            with self.lock:
                self.remember_loras(options['model'],options['loras'])
                self.settings["options"] = {**options, "seed": raw.get("seed", "")}
                atomic_json(self.root / "settings.json", self.settings)
            file, workflow, seconds = self.engine.generate(options, output)
            info = {"id": secrets.token_hex(12), "path": str(file), "name": file.name,
                    "created": time.strftime("%Y-%m-%d %H:%M"), "options": options, "seconds": seconds,
                    'width':options['width'],'height':options['height']}
            atomic_json(file.with_suffix(".json"), {**info, "workflow": workflow})
            with self.lock:
                self.videos.append(info)
                self.revision += 1
                atomic_json(self.root / "library.json", self.videos)
                self.state["result"] = info
                self.state['latest_media']={**info,'media_type':'video'}
            self.report(f"Video saved · {seconds:.0f} seconds to generate · seed {options['seed']}", 1)
            if options['upscale']['enabled']:self.enhance_record(info,'video',options['upscale']['options'],output)
        if prepare:return job,options
        self.run_job(job)

    def generate_image(self, raw, prepare=False, output=None):
        output=output or self.settings['output']
        options = validate_image_options(raw)
        options['loras'] = self.selected_loras(options['model'],raw)
        options['upscale']=self.auto_enhancement(raw.get('upscale'),'image')
        from packs import catalog
        if catalog()[options['model']]['kind'] != 'image':
            raise ValueError('That model needs a starting image. Use the Image Editor.')
        if not (install_ready(self.root) or runtime_ready(self.root)) or not pack_ready(self.root, options['model']):
            raise ValueError('Install the base runtime and selected image model in Settings first.')
        def job():
            with self.lock:
                self.remember_loras(options['model'],options['loras'])
                self.settings['image_options'] = {**options, 'seed': raw.get('seed','')}
                atomic_json(self.root / 'settings.json', self.settings)
            folder = Path(output) / 'Images'
            file, workflow, seconds = self.engine.generate(options, folder, kind='image')
            info = dict(id=secrets.token_hex(12), path=str(file), name=file.name, kind='generated',
                        created=time.strftime('%Y-%m-%d %H:%M'), options=options, seconds=seconds,
                        width=options['width'], height=options['height'])
            atomic_json(file.with_suffix('.json'), {**info, 'workflow':workflow})
            with self.lock:
                self.images.append(info)
                self.revision += 1
                atomic_json(self.root / 'images.json', self.images)
                self.state['image_result'] = info
                self.state['latest_media'] = {**info, 'media_type':'image'}
            self.report(f'Image saved · {seconds:.0f} seconds · seed {options["seed"]}', 1)
            if options['upscale']['enabled']:self.enhance_record(info,'image',options['upscale']['options'],output)
        if prepare:return job,options
        self.run_job(job)

    def import_image(self, data):
        def job():
            info = import_image(self.root, data, self.report)
            info['created'] = time.strftime('%Y-%m-%d %H:%M')
            with self.lock:
                self.images.append(info)
                self.revision += 1
                atomic_json(self.root / 'images.json', self.images)
                self.state['import_result'] = info
                self.state['latest_media'] = {**info, 'media_type':'image'}
            self.report('Starting image added. Choose it in Image → Video.', 1)
        self.run_job(job)

    def find_media(self, identifier, media_type='image'):
        items = self.images if media_type=='image' else self.videos
        source = next((x for x in items if x['id']==identifier),None)
        if not source or not Path(source['path']).is_file():
            raise ValueError('This library file is missing. Import it again or choose another item.')
        return source

    def add_image(self, info, workflow=None):
        atomic_json(Path(info['path']).with_suffix('.json'), {**info, **({'workflow':workflow} if workflow else {})})
        with self.lock:
            self.images.append(info)
            self.revision += 1
            atomic_json(self.root/'images.json',self.images)
            self.state['image_result']=info
            self.state['latest_media']={**info,'media_type':'image'}

    def edit_image(self, raw, prepare=False, output=None):
        output=output or self.settings['output']
        options=validate_edit_options(raw)
        options['loras'] = self.selected_loras(options['model'],raw)
        options['upscale']=self.auto_enhancement(raw.get('upscale'),'image')
        if not (install_ready(self.root) or runtime_ready(self.root)) or not pack_ready(self.root,options['model']):
            raise ValueError('Install the runtime and selected editor model in Models first.')
        source=self.find_media(options['source_image'])
        refs=[self.find_media(x) for x in options['references']]
        mask=raw.get('mask','')
        def job():
            options['input_file']=stage_image(self.root,source)
            options['reference_files']=[stage_image(self.root,x) for x in refs]
            try:
                if mask:
                    options['mask_file']=stage_mask(self.root,mask,options['width'],options['height'])
                with self.lock:
                    self.remember_loras(options['model'],options['loras'])
                    self.settings['edit_options']={k:v for k,v in options.items() if k not in ('input_file','reference_files','mask_file')}
                    self.settings['edit_options']['seed']=raw.get('seed','')
                    atomic_json(self.root/'settings.json',self.settings)
                file,workflow,seconds=self.engine.generate(options,Path(output)/'Images',kind='edit')
                mask_path = None
                if options.get('mask_file'):
                    import shutil
                    from common import comfy_root
                    mask_path = file.with_suffix('.mask.png')
                    shutil.copy2(comfy_root(self.root)/'input'/options['mask_file'],mask_path)
                info=dict(id=secrets.token_hex(12),path=str(file),name=file.name,kind='edited',
                    parent_id=source['id'],reference_ids=options['references'],created=time.strftime('%Y-%m-%d %H:%M'),
                    options=options,seconds=seconds,width=options['width'],height=options['height'])
                if mask_path:
                    info['mask_path'] = str(mask_path)
                self.add_image(info,workflow)
                self.report('Edited image saved in the library.',1)
                if options['upscale']['enabled']:self.enhance_record(info,'image',options['upscale']['options'],output)
            finally:
                if options.get('mask_file'):
                    from common import comfy_root
                    (comfy_root(self.root)/'input'/options['mask_file']).unlink(missing_ok=True)
        if prepare:return job,{**options,**({'mask':mask} if mask else {})}
        self.run_job(job)

    def auto_enhancement(self,raw,kind):
        if not raw or (isinstance(raw,dict) and not raw.get('enabled')):return dict(enabled=False)
        if not isinstance(raw,dict) or raw.get('enabled') is not True:raise ValueError('Choose whether to enhance the result.')
        if not (pack_ready(self.root,'qwen21') if kind=='image' else enhancements.vsr_ready(self.root)):
            raise ValueError('Install '+('Qwen 2.1 Detail Enhancer' if kind=='image' else 'RTX video enhancement')+' in Models before enabling this option.')
        options=enhancements.validate(raw.get('options',{}),kind)
        if kind=='image':
            options['loras']=self.selected_loras('qwen21',raw.get('options',{}))
            if len([x for x in options['loras'] if x['name']!='studio/qwen21/elusarcas-qwen2-1-detailer-v1.safetensors'])>7:
                raise ValueError('Use at most seven extra LoRAs with the built-in detail enhancer.')
        return dict(enabled=True,options=options)

    def enhance_record(self,source,kind,options,output):
        if self.cancel.is_set():raise Cancelled('Enhancement cancelled. The original is preserved.')
        if kind=='image':
            w,h=enhancements.image_size(source['width'],source['height'],options['scale'])
            o={**options,'model':'qwen21','width':w,'height':h,'input_file':stage_image(self.root,source)}
            file,workflow,seconds=self.engine.generate(o,Path(output)/'Images',kind='enhance')
            info=dict(id=secrets.token_hex(12),path=str(file),name=file.name,kind='enhanced',parent_id=source['id'],
                      created=time.strftime('%Y-%m-%d %H:%M'),options=o,seconds=seconds,width=w,height=h)
            self.add_image(info,workflow)
        else:
            self.engine.stop()
            result=enhancements.run_video(self.root,source['path'],Path(output)/'Enhanced Videos',options,self.report,self.cancel)
            file=Path(result['output']);w,h=map(int,result['resolution'].split('x'))
            info=dict(id=secrets.token_hex(12),path=str(file),name=file.name,kind='enhanced',parent_id=source['id'],
                      created=time.strftime('%Y-%m-%d %H:%M'),options=options,seconds=result['seconds'],width=w,height=h)
            atomic_json(file.with_suffix('.json'),info)
            with self.lock:
                self.videos.append(info);self.revision+=1;atomic_json(self.root/'library.json',self.videos)
                self.state['result']=info;self.state['latest_media']={**info,'media_type':'video'}
        self.report('Enhanced copy saved. The original remains in the library.',1)

    def upscale(self,raw,kind,prepare=False,output=None):
        source=self.find_media(raw.get('source_id'),kind)
        wrapper=self.auto_enhancement(dict(enabled=True,options=raw),kind)
        options={**wrapper['options'],'source_id':source['id'],'model':'qwen21' if kind=='image' else 'rtx_vsr'}
        def job():self.enhance_record(source,kind,wrapper['options'],output or self.settings['output'])
        return (job,options) if prepare else self.run_job(job)

    def prepare_queued(self,kind,raw,output=None):
        if kind=='image':return self.generate_image(raw,prepare=True,output=output)
        if kind=='video':return self.generate(raw,prepare=True,output=output)
        if kind=='edit':return self.edit_image(raw,prepare=True,output=output)
        if kind in ('enhance_image','enhance_video'):return self.upscale(raw,kind.split('_')[1],prepare=True,output=output)
        raise ValueError('Choose a supported queue job.')

    def queue_options(self,options):
        options=dict(options)
        mask=options.pop('mask','')
        if mask:
            if not isinstance(mask,str) or not mask.startswith('data:image/png;base64,') or len(mask)>35*1024**2:
                raise ValueError('Choose a valid painted PNG mask.')
            name=secrets.token_hex(12)+'.txt';folder=self.root/'queue-masks';folder.mkdir(exist_ok=True)
            (folder/name).write_text(mask,encoding='utf-8');options['_mask']=name
        return options

    def hydrate_queued(self,item):
        raw=dict(item['options']);name=raw.pop('_mask',None)
        if name:
            import re
            if not isinstance(name,str) or not re.fullmatch(r'[0-9a-f]{24}\.txt',name):raise ValueError('Invalid saved queue mask.')
            raw['mask']=(self.root/'queue-masks'/name).read_text(encoding='utf-8')
        return raw

    def enqueue(self,kind,raw,priority=5):
        with self.lock:
            _,options=self.prepare_queued(kind,raw)
            if self.removing_model and (options.get('model')==self.removing_model or (self.removing_model=='qwen21' and options.get('upscale',{}).get('enabled'))):
                raise ValueError('That model is being removed. Wait for removal to finish.')
            item=self.queue.add(kind,self.queue_options(options),priority,self.settings['output'])
            self._kick_queue()
            return item['id']

    def _kick_queue(self):
        if self.state['busy'] or self.closing:return
        while (item:=self.queue.next()) is not None:
            try:
                target,_=self.prepare_queued(item['kind'],self.hydrate_queued(item),item['output'])
            except Exception as error:
                item.update(status='failed',error=str(error),finished=time.strftime('%Y-%m-%d %H:%M:%S'))
                if not self.queue.continue_on_error:self.queue.paused=True
                self.queue.save()
                self.state.update(error=str(error),stage='Queue paused. Review the failed job.' if self.queue.paused else 'Skipped failed job. Continuing queue…')
                continue
            item.update(status='running',started=time.strftime('%Y-%m-%d %H:%M:%S'));self.queue.save()
            self.run_job(target,queue_id=item['id'])
            return

    def queue_action(self,data):
        with self.lock:
            action=data.get('action');identifier=data.get('id')
            if action in ('pause','resume'):
                self.queue.paused=action=='pause';self.queue.save()
            elif action=='failure_policy':
                value=data.get('continue_on_error')
                if not isinstance(value,bool):raise ValueError('Choose whether to continue after a failed job.')
                self.queue.continue_on_error=value;self.queue.save()
            elif action=='clear_finished':
                self.queue.jobs=[x for x in self.queue.jobs if x['status'] in ACTIVE];self.queue.save()
            elif action=='cancel_all':
                self.queue.paused=True
                for item in self.queue.jobs:
                    if item['status']=='queued':item['status']='cancelled'
                    elif item['status']=='running':
                        item['cancel_requested']=True;self.cancel.set();self.engine.cancel.set()
                self.queue.save()
            elif action=='cancel':
                item=self.queue.get(identifier)
                if item['status']=='running':
                    item['cancel_requested']=True;self.cancel.set();self.engine.cancel.set()
                elif item['status']=='queued':item['status']='cancelled'
                else:raise ValueError('That job is already finished.')
                self.queue.save()
            elif action=='move':self.queue.move(identifier,data.get('direction'))
            elif action=='update':
                item=self.queue.get(identifier)
                if item['status']!='queued':raise ValueError('Only waiting jobs can be edited.')
                options=None
                if 'options' in data:
                    _,options=self.prepare_queued(item['kind'],data['options'],item['output'])
                    options=self.queue_options(options)
                self.queue.update(identifier,options,data.get('priority'))
            elif action=='retry':
                item=self.queue.get(identifier)
                if item['status'] in ACTIVE:raise ValueError('Only finished jobs can be retried.')
                _,options=self.prepare_queued(item['kind'],self.hydrate_queued(item),item['output'])
                self.queue.add(item['kind'],self.queue_options(options),item['priority'],item['output'])
            else:raise ValueError('Unknown queue action.')
            self._kick_queue()

    def model_references(self,key):
        return [x for x in self.queue.jobs if x['status'] in ACTIVE and (x['options'].get('model')==key or
                (key=='qwen21' and x['options'].get('upscale',{}).get('enabled') and x['kind'] in ('image','edit')))]

    def remove_model(self,key,ticket):
        with self.lock:
            if self.model_references(key):raise ValueError('Cancel or finish the queued jobs using this model before uninstalling it.')
            self.removing_model=key
            try:
                def job():
                    self.engine.stop();uninstall_model(self.root,key,ticket,self.report,self.cancel)
                self.run_job(job)
            except Exception:
                self.removing_model=None;raise

    def transform_media(self,raw,action):
        source=self.find_media(raw.get('id'), 'video' if action=='frame' else 'image')
        if action=='crop':
            options=crop_options(raw)
        else:
            try:
                timestamp=float(raw.get('timestamp',0))
                if not 0 <= timestamp <= 3600: raise ValueError()
            except (ValueError,TypeError,OverflowError):
                raise ValueError('Choose a frame position between zero and 3600 seconds.') from None
            options=dict(timestamp=timestamp)
        def job():
            self.report('Saving a new library image…',None)
            info=media_record(self.root,action,source,**options)
            self.add_image(info)
            self.report('New image saved in the library.',1)
        self.run_job(job)

    def selected_loras(self, model, raw):
        return validate_selection(self.root,raw.get('loras',self.settings['model_loras'].get(model,[])),model)

    def remember_loras(self, model, adapters):
        self.settings['model_loras'][model] = adapters
        if model=='wan13':
            self.settings['wan_loras'] = adapters

    def update_loras(self, selected, model='wan13'):
        with self.lock:
            if self.state["busy"] and not any(x['status']=='running' for x in self.queue.jobs):
                raise ValueError("Finish or cancel the running operation before changing LoRAs.")
            validate_model(model)
            adapters = validate_selection(self.root, selected, model)
            self.remember_loras(model,adapters)
            for key in ('options','image_options','edit_options'):
                saved = self.settings.get(key,{})
                if saved.get('model','wan13' if key=='options' else '') == model:
                    saved['loras'] = adapters
            atomic_json(self.root / "settings.json", self.settings)

    def install_update(self, ticket, shutdown):
        with self.lock:
            if self.state['busy']:raise ValueError('Finish or cancel the current operation before installing an update.')
            info=self.updates.snapshot()
            if not info.get('can_install'):raise ValueError(info.get('install_reason'))
            if not isinstance(ticket,str) or not info.get('ticket') or not secrets.compare_digest(ticket,info['ticket']):
                raise ValueError('Check for updates again before installing.')
            self.queue.paused=True;self.queue.save()
            def job():
                try:
                    installer, request=self.updates.prepare(ticket,self.report,self.cancel)
                    if self.cancel.is_set():raise Cancelled('Update cancelled. The current app is unchanged.')
                    self.updates.launch(installer,request)
                    with self.lock:self.closing=True
                    self.report('Installing the update. The studio will close and reopen automatically.',1)
                    threading.Thread(target=shutdown,daemon=True).start()
                except Exception as error:
                    with self.updates.lock:self.updates.info.update(status='error',error=str(error))
                    raise
            self.run_job(job)

    def save_settings(self, data):
        with self.lock:
            if self.state["busy"]:
                raise ValueError("Wait for the current operation to finish before changing folders.")
            output = Path(str(data.get("output", self.settings["output"]))).expanduser()
            if not output.is_absolute():
                raise ValueError("Select a full output folder path.")
            output.mkdir(parents=True, exist_ok=True)
            self.settings["output"] = str(output.resolve())
            atomic_json(self.root / "settings.json", self.settings)


def pick_folder(initial):
    if os.name == "nt":
        # Use the shell dialog in this request thread; launching another frozen copy is
        # unnecessarily slow on machines that scan every unpacked Python executable.
        import ctypes
        from ctypes import wintypes
        shell = ctypes.windll.shell32
        ole = ctypes.windll.ole32
        user = ctypes.windll.user32
        callback_type = ctypes.WINFUNCTYPE(ctypes.c_int, wintypes.HWND, wintypes.UINT, wintypes.LPARAM, wintypes.LPARAM)
        initial_buffer = ctypes.create_unicode_buffer(initial)
        class BrowseInfo(ctypes.Structure):
            _fields_ = [("hwndOwner", wintypes.HWND), ("pidlRoot", ctypes.c_void_p),
                        ("pszDisplayName", wintypes.LPWSTR), ("lpszTitle", wintypes.LPCWSTR),
                        ("ulFlags", wintypes.UINT), ("lpfn", callback_type),
                        ("lParam", wintypes.LPARAM), ("iImage", ctypes.c_int)]
        @callback_type
        def callback(hwnd, message, _value, _context):
            if message == 1:  # BFFM_INITIALIZED
                user.SendMessageW(hwnd, 0x467, 1, ctypes.addressof(initial_buffer))
                # A background launch can carry SW_HIDE in STARTUPINFO. Explicitly
                # show this interactive dialog even when the server has no window.
                user.ShowWindow(hwnd, 5)
                user.ShowWindow(hwnd, 5)
                user.SetForegroundWindow(hwnd)
            return 0
        shell.SHBrowseForFolderW.argtypes = [ctypes.POINTER(BrowseInfo)]
        shell.SHBrowseForFolderW.restype = ctypes.c_void_p
        shell.SHGetPathFromIDListEx.argtypes = [ctypes.c_void_p, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD]
        shell.SHGetPathFromIDListEx.restype = wintypes.BOOL
        user.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        user.SendMessageW.restype = wintypes.LPARAM
        user.SetForegroundWindow.argtypes = [wintypes.HWND]
        user.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        ole.CoTaskMemFree.argtypes = [ctypes.c_void_p]
        initialized = ole.CoInitializeEx(None, 2)  # COINIT_APARTMENTTHREADED
        if initialized not in (0, 1):
            raise RuntimeError("Windows could not initialize the folder picker. Enter the output path manually.")
        try:
            display = ctypes.create_unicode_buffer(32768)
            info = BrowseInfo(None, None, ctypes.cast(display, wintypes.LPWSTR),
                              "Choose where to save your videos", 0x41, callback, 0, 0)
            selected = shell.SHBrowseForFolderW(ctypes.byref(info))
            if not selected:
                return ""
            try:
                output = ctypes.create_unicode_buffer(32768)
                if not shell.SHGetPathFromIDListEx(selected, output, len(output), 0):
                    raise ValueError("Choose a local filesystem folder.")
                return output.value
            finally:
                ole.CoTaskMemFree(selected)
        finally:
            ole.CoUninitialize()
    import tkinter as tk
    from tkinter import filedialog
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    result = filedialog.askdirectory(initialdir=initial if Path(initial).exists() else str(Path.home()), title="Choose a video output folder", parent=root)
    root.destroy()
    return result


def make_handler(studio, shutdown):
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send_json(self, value, status=200):
            body = json.dumps(value, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def valid_host(self):
            return self.headers.get("Host", "") == f"127.0.0.1:{self.server.server_port}"

        def authorized(self):
            return self.valid_host() and secrets.compare_digest(self.headers.get("X-Wan-Token", ""), studio.token)

        def do_GET(self):
            url = urllib.parse.urlsplit(self.path)
            if not self.valid_host():
                return self.send_json({"error": "Invalid host"}, 403)
            if url.path == "/api/state":
                if not self.authorized():
                    return self.send_json({"error": "Unauthorized"}, 403)
                return self.send_json(studio.snapshot())
            if url.path.startswith('/api/library/'):
                if not self.authorized():return self.send_json({'error':'Unauthorized'},403)
                try:
                    with studio.lock:
                        return self.send_json(media_details(studio.images,studio.videos,url.path.removeprefix('/api/library/')))
                except ValueError as error:return self.send_json({'error':str(error)},404)
            if url.path == '/api/library':
                if not self.authorized():
                    return self.send_json({'error':'Unauthorized'},403)
                try:
                    with studio.lock:
                        return self.send_json(catalog_page(studio.images,studio.videos,urllib.parse.parse_qs(url.query)))
                except ValueError as error:
                    return self.send_json({'error':str(error)},400)
            if url.path.startswith('/api/queue/'):
                if not self.authorized():return self.send_json({'error':'Unauthorized'},403)
                try:
                    with studio.lock:
                        item=studio.queue.get(url.path.removeprefix('/api/queue/'))
                        raw=studio.hydrate_queued(item)
                        identifiers=[raw.get('source_image'),raw.get('source_id'),*raw.get('references',[])]
                        sources=[x for x in studio.images+studio.videos if x['id'] in identifiers]
                        return self.send_json({**item,'options':raw,'sources':sources})
                except (ValueError,OSError) as error:return self.send_json({'error':str(error)},400)
            if url.path.startswith('/thumbnail/'):
                query=urllib.parse.parse_qs(url.query)
                if query.get('token',[''])[0] != studio.token:
                    return self.send_json({'error':'Unauthorized'},403)
                identifier=url.path.removeprefix('/thumbnail/')
                item=next((x for x in studio.images+studio.videos if x['id']==identifier),None)
                if not item: return self.send_json({'error':'Not found'},404)
                thumb=studio.thumbnails.get(item,'image' if item in studio.images else 'video')
                if thumb: return self.send_file(thumb,'image/jpeg')
                return self.send_json({'error':'Thumbnail pending'},202)
            if url.path.startswith("/video/"):
                query = urllib.parse.parse_qs(url.query)
                if query.get("token", [""])[0] != studio.token:
                    return self.send_json({"error": "Unauthorized"}, 403)
                identifier = url.path.removeprefix("/video/")
                record = next((v for v in studio.videos if v["id"] == identifier), None)
                if not record or not Path(record["path"]).is_file():
                    return self.send_json({"error": "Video not found"}, 404)
                return self.send_file(Path(record["path"]), "video/mp4", ranges=True)
            if url.path.startswith('/image/'):
                query = urllib.parse.parse_qs(url.query)
                if query.get('token',[''])[0] != studio.token:
                    return self.send_json({'error':'Unauthorized'},403)
                record = next((x for x in studio.images if x['id']==url.path.removeprefix('/image/')), None)
                if not record or not Path(record['path']).is_file():
                    return self.send_json({'error':'Image not found'},404)
                return self.send_file(Path(record['path']), 'image/png')
            if url.path == '/studio.js':
                return self.send_file(resource('studio.js'), 'text/javascript; charset=utf-8')
            if url.path == '/studio-tools.js':
                return self.send_file(resource('studio-tools.js'), 'text/javascript; charset=utf-8')
            if url.path == '/studio-updates.js':
                return self.send_file(resource('studio-updates.js'), 'text/javascript; charset=utf-8')
            if url.path == '/studio.css':
                return self.send_file(resource('studio.css'), 'text/css; charset=utf-8')
            if url.path == '/studio-logo.png':
                return self.send_file(resource('studio-logo.png'), 'image/png')
            if url.path == "/":
                if urllib.parse.parse_qs(url.query).get("session", [""])[0] != studio.token:
                    return self.send_json({"error": "Open Wan Video Studio from its shortcut."}, 403)
                html = resource("index.html").read_text(encoding="utf-8").replace("__API_TOKEN__", studio.token)
                body = html.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("Referrer-Policy", "no-referrer")
                self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; media-src 'self'; connect-src 'self'; img-src 'self' data:")
                self.end_headers()
                return self.wfile.write(body)
            return self.send_json({"error": "Not found"}, 404)

        def send_file(self, path, content_type, ranges=False):
            size = path.stat().st_size
            start, end = 0, size - 1
            partial = False
            if ranges and self.headers.get("Range"):
                import re
                match = re.fullmatch(r"bytes=(\d+)-(\d*)", self.headers["Range"])
                if not match:
                    return self.send_json({"error": "Invalid range"}, 416)
                start = int(match[1])
                end = min(int(match[2]) if match[2] else end, end)
                if start > end or start >= size:
                    return self.send_json({"error": "Range outside file"}, 416)
                partial = True
            self.send_response(206 if partial else 200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(end - start + 1))
            self.send_header("Accept-Ranges", "bytes")
            if partial:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.end_headers()
            try:
                with path.open("rb") as file:
                    file.seek(start)
                    remaining = end - start + 1
                    while remaining > 0:
                        chunk = file.read(min(1024 * 1024, remaining))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        remaining -= len(chunk)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_POST(self):
            if not self.authorized():
                return self.send_json({"error": "Unauthorized"}, 403)
            if self.headers.get("Origin", f"http://127.0.0.1:{self.server.server_port}") != f"http://127.0.0.1:{self.server.server_port}":
                return self.send_json({"error": "Invalid origin"}, 403)
            try:
                length = int(self.headers.get("Content-Length", "0"))
                limit = 36 * 1024**2 if self.path in ('/api/images/import','/api/images/edit','/api/queue/add','/api/queue/action') else 100000
                if not 0 <= length <= limit:
                    raise ValueError("Request is too large.")
                data = json.loads(self.rfile.read(length) or b"{}")
                if not isinstance(data, dict):
                    raise ValueError("Expected an object.")
                if self.path == '/api/updates/check':
                    return self.send_json(studio.updates.check())
                elif self.path == '/api/updates/install':
                    studio.install_update(data.get('ticket'),shutdown)
                elif self.path == "/api/generate":
                    return self.send_json({'ok':True,'id':studio.enqueue('video',data,data.get('priority',5))})
                elif self.path == '/api/images/generate':
                    return self.send_json({'ok':True,'id':studio.enqueue('image',data,data.get('priority',5))})
                elif self.path == '/api/images/import':
                    studio.import_image(data)
                elif self.path == '/api/images/edit':
                    return self.send_json({'ok':True,'id':studio.enqueue('edit',data,data.get('priority',5))})
                elif self.path == '/api/queue/add':
                    raw=data.get('options',{})
                    if not isinstance(raw,dict):raise ValueError('Expected queue options.')
                    return self.send_json({'ok':True,'id':studio.enqueue(data.get('kind'),raw,data.get('priority',5))})
                elif self.path == '/api/queue/action':
                    studio.queue_action(data)
                elif self.path == '/api/models/removal-plan':
                    return self.send_json(removal_plan(studio.root,data.get('model')))
                elif self.path == '/api/models/uninstall':
                    studio.remove_model(data.get('model'),data.get('ticket'))
                elif self.path == '/api/enhancers/install-video':
                    def install_enhancer():
                        studio.engine.stop();enhancements.install_video(studio.root,studio.report,studio.cancel)
                    studio.run_job(install_enhancer)
                elif self.path == '/api/enhancers/defaults':
                    with studio.lock:
                        if studio.state['busy']:raise ValueError('Save enhancement defaults after the current operation finishes.')
                        studio.settings['enhancement_defaults']={kind:enhancements.validate(data.get(kind,{}),kind) for kind in ('image','video')}
                        studio.settings['enhancement_defaults']['image']['seed']=str(data.get('image',{}).get('seed','')).strip()
                        atomic_json(studio.root/'settings.json',studio.settings)
                elif self.path == '/api/images/crop':
                    studio.transform_media(data,'crop')
                elif self.path == '/api/videos/frame':
                    studio.transform_media(data,'frame')
                elif self.path == '/api/packs/install':
                    keys, access = data.get('packs', []), str(data.get('token',''))
                    # Check the keys before accepting a background job.
                    from packs import catalog
                    if not isinstance(keys,list) or not keys or any(not isinstance(k,str) or (k not in catalog() and k!='wan13') for k in keys):
                        raise ValueError('Choose known model packs.')
                    def pack_job():
                        studio.engine.stop()
                        if not runtime_ready(studio.root) or 'wan13' in keys:
                            provision(studio.root, studio.report, studio.cancel, access)
                        optional=[k for k in keys if k!='wan13']
                        if optional:install_packs(studio.root, optional, studio.report, studio.cancel, access)
                    studio.run_job(pack_job)
                elif self.path == "/api/loras/select":
                    studio.update_loras(data.get('loras', []),data.get('model','wan13'))
                elif self.path == "/api/loras/import":
                    paths = data.get("paths", [])
                    model = validate_model(data.get('model','wan13'))
                    def import_job():
                        studio.engine.stop()
                        import_loras(studio.root, paths, studio.report, studio.cancel, model)
                    studio.run_job(import_job)
                elif self.path == "/api/loras/download":
                    link, access = str(data.get("url", "")), str(data.get("token", ""))
                    model = validate_model(data.get('model','wan13'))
                    def download_job():
                        studio.engine.stop()
                        download_lora(studio.root, link, access, studio.report, studio.cancel, model)
                    studio.run_job(download_job)
                elif self.path == "/api/install":
                    token = str(data.get("token", "")).strip()
                    if len(token) > 1000:
                        raise ValueError("Invalid access token.")
                    def install():
                        studio.engine.stop()
                        provision(studio.root, studio.report, studio.cancel, token)
                    studio.run_job(install)
                elif self.path == "/api/cancel":
                    studio.cancel.set()
                    studio.engine.cancel.set()
                    studio.report("Cancelling…", None)
                elif self.path == "/api/settings":
                    studio.save_settings(data)
                elif self.path == "/api/pick-folder":
                    return self.send_json({"path": pick_folder(studio.settings["output"])})
                elif self.path == "/api/open-folder":
                    kind = data.get("kind")
                    folder = lora_folder(studio.root,data.get('model','wan13')) if kind == "loras" else studio.root / "logs" if kind == "logs" else Path(studio.settings["output"])/'Images' if kind=='images' else Path(studio.settings["output"])
                    folder.mkdir(parents=True, exist_ok=True)
                    startup = subprocess.STARTUPINFO() if os.name == 'nt' else None
                    if startup:
                        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                        startup.wShowWindow = 1  # Explicitly show Explorer even from the hidden backend.
                    subprocess.Popen(['explorer.exe', str(folder.resolve())], startupinfo=startup)
                elif self.path == "/api/release":
                    if studio.state["busy"]:
                        raise ValueError("Cancel or finish the current operation first.")
                    studio.engine.stop()
                    studio.report("GPU memory released. Ready for the next video.", 0)
                elif self.path == "/api/exit":
                    self.send_json({"ok": True})
                    threading.Thread(target=shutdown, daemon=True).start()
                    return
                else:
                    return self.send_json({"error": "Not found"}, 404)
                return self.send_json({"ok": True})
            except Exception as error:
                return self.send_json({"error": str(error)}, 400)
    return Handler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root")
    parser.add_argument("--headless", action="store_true", help="Run only the local backend for diagnostics")
    parser.add_argument("--no-browser", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--pick-folder")
    args = parser.parse_args()
    if args.pick_folder is not None:
        result = pick_folder(args.pick_folder)
        # PyInstaller --windowed has no stdout; communicate via an optional temporary result file.
        if os.environ.get("WAN_PICKER_RESULT"):
            Path(os.environ["WAN_PICKER_RESULT"]).write_text(result, encoding="utf-8")
        elif sys.stdout:
            print(result)
        return
    root = Path(args.root) if args.root else app_root()
    headless = args.headless or args.no_browser
    # Reopen the existing local session if this installation is already running.
    instance = load_json(root / ".studio-instance.json", {})
    if instance:
        try:
            request = urllib.request.Request(instance["base"] + "/api/state", headers={"X-Wan-Token": instance["token"]})
            with urllib.request.urlopen(request, timeout=2) as response:
                state = json.load(response)
                if state["root"] == str(root.resolve()):
                    if headless:
                        return
                    if instance.get("mode") == "desktop" and activate_desktop(instance):
                        return
                    if state["busy"]:
                        raise RuntimeError("Finish or cancel the running operation and click Exit app before opening the desktop version.")
                    close = urllib.request.Request(instance["base"] + "/api/exit", data=b"{}",
                        headers={"X-Wan-Token": instance["token"], "Content-Type": "application/json"})
                    with urllib.request.urlopen(close, timeout=3):
                        pass
                    for _ in range(60):
                        if not (root / ".studio-instance.json").exists():
                            break
                        time.sleep(.2)
        except (OSError, ValueError, KeyError):
            pass
    studio = Studio(root)
    studio.resources.start()
    server = None
    def shutdown():
        with studio.lock:
            studio.closing=True;studio.queue.save()
        studio.cancel.set()
        studio.engine.cancel.set()
        if studio.worker and studio.worker.is_alive():
            studio.worker.join(timeout=15)
        if server:
            server.shutdown()
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), make_handler(studio, shutdown))
    server.daemon_threads = True
    base = f"http://127.0.0.1:{server.server_port}"
    url = base + "/?session=" + studio.token
    instance_path = root / ".studio-instance.json"
    instance_data = {"base": base, "url": url, "token": studio.token, "mode": "headless" if headless else "desktop"}
    atomic_json(instance_path, instance_data)
    atexit.register(studio.engine.stop)
    host = None
    server_thread = None
    try:
        if headless:
            if sys.stdout:
                print(url, flush=True)
            server.serve_forever(poll_interval=.3)
        else:
            server_thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .3}, daemon=True)
            server_thread.start()
            host = open_desktop(url, studio.token, root)
            instance_data["desktop_pid"] = host.pid
            atomic_json(instance_path, instance_data)
            while host.poll() is None and server_thread.is_alive():
                time.sleep(.2)
            if host.poll() is None:
                try:
                    host.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    host.terminate()
                    host.wait(timeout=10)
            # A deliberate backend exit may terminate the still-open host after its grace period.
            # That is a normal close, not a startup failure requiring a blocking error dialog.
            if host.returncode and not studio.closing:
                raise RuntimeError("The desktop interface could not start. Run Setup again to repair Microsoft WebView2.")
    finally:
        with studio.lock:
            studio.closing=True;studio.queue.save()
        studio.resources.stop.set()
        studio.thumbnails.stop.set()
        studio.cancel.set()
        studio.engine.cancel.set()
        if studio.worker and studio.worker.is_alive():
            studio.worker.join(timeout=15)
        if server_thread and server_thread.is_alive():
            server.shutdown()
            server_thread.join(timeout=5)
        studio.engine.stop()
        server.server_close()
        if load_json(instance_path, {}).get("token") == studio.token:
            instance_path.unlink(missing_ok=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        import tkinter as tk
        from tkinter import messagebox
        window = tk.Tk()
        window.withdraw()
        messagebox.showerror(APP_NAME, str(error))
        window.destroy()
