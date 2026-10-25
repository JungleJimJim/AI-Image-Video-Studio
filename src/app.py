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

from common import (APP_NAME, CREATE_NO_WINDOW, VERSION, app_root, installed_app_for_copy, atomic_json, runtime_ready,
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
import avatars
import voices
from updates import UpdateManager
from model_removal import removal_plan, uninstall as uninstall_model
from media_storage import media_folder, migrate_library, metadata_path, migrate_metadata
from notifications import play_completion_ping
import attention_support
import video_faceswap
import moss
import canvas_projects


class Studio:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.token = secrets.token_urlsafe(32)
        self.settings = migrate_library(self.root, load_json(self.root / "settings.json",
            {"output": str(self.root / "Library"), "options": DEFAULTS.copy()}))
        self.settings.setdefault("output", str(self.root / "Library"))
        self.settings.setdefault("options", DEFAULTS.copy())
        self.settings.setdefault('wan_loras', self.settings['options'].get('loras', [])
                                 if self.settings['options'].get('model','wan13')=='wan13' else [])
        self.settings.setdefault('model_loras', {})
        self.settings['model_loras'].setdefault('wan13', self.settings['wan_loras'])
        for key in ('options','image_options','edit_options','face_options'):
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
        self.events.extend(migrate_metadata(self.images,self.videos))
        self.recordings = load_json(self.root / 'recordings.json', [])
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
            from model_files import file_status
            base_status=file_status(self.root,base)
            base_info=dict(id='wan13',name='NSFW Wan 1.3B · E14',kind='video',family='wan13',
                description='The original text-to-video model. Runtime software remains available if these weights are removed.',
                ready=install_ready(self.root),size=sum(f['size'] for f in base),
                remaining=sum(x['remaining'] for x in base_status),download_files=base_status)
            return {**self.state, "ready": install_ready(self.root), "gpu": self.gpu,
                    'base_model':base_info,
                    "settings": self.settings, "library": self.videos[-30:][::-1],
                    "loras": installed_loras(self.root),
                    'lora_models': list(lora_models().values()),
                    'packs': pack_inventory(self.root), 'images': self.images[-60:][::-1],
                    'runtime_ready': runtime_ready(self.root), 'queue': self.queue.snapshot(),
                    'recordings': self.recordings,
                    'enhancers': enhancements.inventory(self.root),
                    'video_faceswap':video_faceswap.inventory(self.root),
                    'updates': self.updates.snapshot(),
                    'resources': self.resources.snapshot(),
                    'attention':attention_support.snapshot(self.root,self.settings.get('attention','pytorch'),self.engine),
                    'library_revision': self.revision, 'library_count': len(self.images)+len(self.videos),
                    "log": self.events[-40:], "root": str(self.root), "version": VERSION}

    def run_job(self, target, queue_id=None, notify_completion=False):
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
                    if outcome=='completed' and (queue_id or notify_completion) and self.settings.get('completion_sound',True):
                        play_completion_ping()
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
            raise ValueError('Install the selected video model pack in Models first.')
        source = None
        if options['mode'] == 'image':
            source = next((x for x in self.images if x['id']==options['source_image']), None)
            if not source or not Path(source['path']).is_file():
                raise ValueError('Choose an existing image from the image library.')
        video_refs=[self.find_media(key) for key in options.get('video_references',[])]
        last_source=None
        if options.get('last_image'):
            last_source=next((x for x in self.images if x['id']==options['last_image']),None)
            if not last_source or not Path(last_source['path']).is_file():raise ValueError('The selected last image is missing from the Library.')
        if options['model'] == 'ltx2':
            options.update(steps=8, cfg=1.0, sampler='euler', scheduler='distilled', shift=1.0)
        def job():
            if source:
                options['input_file'] = stage_image(self.root, source)
            if last_source:options['last_input_file']=stage_image(self.root,last_source)
            if video_refs:options['reference_files']=[stage_image(self.root,x) for x in video_refs]
            with self.lock:
                self.remember_loras(options['model'],options['loras'])
                self.settings["options"] = {**options, "seed": raw.get("seed", "")}
                atomic_json(self.root / "settings.json", self.settings)
            file, workflow, seconds = self.engine.generate(options, media_folder(self.root,'video',output))
            info = {"id": secrets.token_hex(12), "path": str(file), "name": file.name,
                    "created": time.strftime("%Y-%m-%d %H:%M"), "options": options, "seconds": seconds,
                    'width':options['width'],'height':options['height']}
            atomic_json(metadata_path(file), {**info, "workflow": workflow})
            self.thumbnails.get(info,'video')
            with self.lock:
                self.videos.append(info)
                self.revision += 1
                atomic_json(self.root / "library.json", self.videos)
                self.state["result"] = info
                self.state['latest_media']={**info,'media_type':'video'}
            self.report(f"Video saved · {seconds:.0f} seconds to generate · seed {options['seed']}", 1)
            if options['upscale']['enabled']:self.enhance_record(info,'video',options['upscale']['options'],output)
        if prepare:return job,options
        self.run_job(job,notify_completion=True)

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
        image_refs=[self.find_media(key) for key in options.get('image_references',[])]
        moss_maps=moss.prepare(self,options) if moss.is_model(options['model']) else {}
        def job():
            if moss_maps:moss.stage(self,options,moss_maps)
            if image_refs:
                options['input_file']=stage_image(self.root,image_refs[0])
                options['reference_files']=[stage_image(self.root,x) for x in image_refs[1:]]
            with self.lock:
                self.remember_loras(options['model'],options['loras'])
                self.settings['image_options'] = {**options, 'seed': raw.get('seed','')}
                atomic_json(self.root / 'settings.json', self.settings)
            folder = media_folder(self.root,'image',output)
            file, workflow, seconds = self.engine.generate(options, folder, kind='image')
            info = dict(id=secrets.token_hex(12), path=str(file), name=file.name, kind='generated',
                        created=time.strftime('%Y-%m-%d %H:%M'), options=options, seconds=seconds,
                        width=options['width'], height=options['height'])
            if image_refs:info.update(reference_ids=[x['id'] for x in image_refs],reference_names=[x['name'] for x in image_refs])
            atomic_json(metadata_path(file), {**info, 'workflow':workflow})
            self.thumbnails.get(info,'image')
            with self.lock:
                self.images.append(info)
                self.revision += 1
                atomic_json(self.root / 'images.json', self.images)
                self.state['image_result'] = info
                self.state['latest_media'] = {**info, 'media_type':'image'}
            self.report(f'Image saved · {seconds:.0f} seconds · seed {options["seed"]}', 1)
            if options['upscale']['enabled']:self.enhance_record(info,'image',options['upscale']['options'],output)
        if prepare:return job,options
        self.run_job(job,notify_completion=True)

    def import_image(self, data):
        def job():
            info = import_image(self.root, data, self.report)
            info['created'] = time.strftime('%Y-%m-%d %H:%M')
            self.thumbnails.get(info,'image')
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

    def canvas_image(self, data, composite=False):
        project=canvas_projects.validate(data.get('project',{})) if composite else None
        return self._library_import(data,'canvas_composite' if composite else 'canvas_source',not composite,project)

    def source_image(self, data):
        return self._library_import(data,'imported')

    def _library_import(self, data, kind, preserve_alpha=False, project=None):
        info=import_image(self.root,data,lambda *_:None,preserve_alpha=preserve_alpha)
        if project and (info['width'],info['height'])!=(project['width'],project['height']):
            Path(info['path']).unlink(missing_ok=True)
            raise ValueError('Exported image dimensions do not match the canvas.')
        info.update(created=time.strftime('%Y-%m-%d %H:%M'),kind=kind)
        if project:
            info['options']=dict(tool='canvas',width=project['width'],height=project['height'])
            info['canvas_project']=project
            info['reference_ids']=list(dict.fromkeys(x['source_id'] for x in project['layers'] if x['kind']=='image'))
        atomic_json(metadata_path(info['path']),info)
        self.thumbnails.get(info,'image')
        # CPU imports do not replace a running generator's progress/result.
        with self.lock:
            atomic_json(self.root/'images.json',[*self.images,info]);self.images.append(info);self.revision+=1
        return {**info,'media_type':'image'}

    def open_library_folder(self, identifier):
        with self.lock:
            item = next((x for x in (*self.images, *self.videos) if x['id'] == identifier), None)
        if not item or not Path(item['path']).is_file():
            raise ValueError('This library file is missing. Choose another item or import it again.')
        path = Path(item['path']).resolve()
        startup = subprocess.STARTUPINFO() if os.name == 'nt' else None
        if startup:
            startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startup.wShowWindow = 1
        # Explorer expects the /select comma immediately before the quoted path.
        # Use no shell; the path comes only from a saved library record.
        subprocess.Popen(f'explorer.exe /select,"{path}"', startupinfo=startup)

    def add_image(self, info, workflow=None):
        atomic_json(metadata_path(info['path']), {**info, **({'workflow':workflow} if workflow else {})})
        self.thumbnails.get(info,'image')
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
        moss_maps=moss.prepare(self,options) if moss.is_model(options['model']) else {}
        def job():
            if moss_maps:moss.stage(self,options,moss_maps)
            options['input_file']=stage_image(self.root,source)
            options['reference_files']=[stage_image(self.root,x) for x in refs]
            try:
                if mask:
                    options['mask_file']=stage_mask(self.root,mask,options['width'],options['height'])
                with self.lock:
                    self.remember_loras(options['model'],options['loras'])
                    settings_key='face_options' if options['model']=='bfs' else 'edit_options'
                    self.settings[settings_key]={k:v for k,v in options.items() if k not in ('input_file','reference_files','mask_file')}
                    self.settings[settings_key]['seed']=raw.get('seed','')
                    atomic_json(self.root/'settings.json',self.settings)
                file,workflow,seconds=self.engine.generate(options,media_folder(self.root,'image',output),kind='edit')
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
        self.run_job(job,notify_completion=True)

    def import_recording(self,raw):
        def job():
            info=avatars.import_audio(self.root,raw,self.report,self.cancel)
            with self.lock:
                self.recordings.append(info)
                atomic_json(self.root/'recordings.json',self.recordings)
                self.state['audio_result']=info
            self.report('Voice recording imported. Choose a Library image or video.',1)
        self.run_job(job)

    def generate_voice(self,raw,prepare=False,output=None):
        options=voices.validate_options(raw)
        reference=next((x for x in self.recordings if x['id']==options['reference_id']),None) if options['reference_id'] else None
        if options['reference_id'] and (not reference or not Path(reference['path']).is_file()):raise ValueError('The reference recording is missing.')
        if reference and not .1<=reference.get('duration',0)<=60:raise ValueError('Choose a reference recording no longer than 60 seconds.')
        def job():
            self.engine.stop()
            content,seconds=voices.generate(self.root,options,reference,self.report,self.cancel)
            import base64
            info=avatars.import_audio(self.root,dict(data='data:audio/wav;base64,'+base64.b64encode(content).decode(),name='Voice_'+time.strftime('%Y%m%d_%H%M%S')+'.wav'),self.report,self.cancel)
            info.update(kind='generated_voice',options=options,seconds=seconds)
            atomic_json(Path(info['path']).with_suffix('.json'),info)
            with self.lock:
                self.recordings.append(info);atomic_json(self.root/'recordings.json',self.recordings)
                self.settings['voice_options']=options;atomic_json(self.root/'settings.json',self.settings)
                self.state.update(audio_result=info,voice_result=info)
            self.report('Voice saved in Library/Audio and available in Talking Avatar.',1)
        return (job,options) if prepare else self.run_job(job,notify_completion=True)

    def generate_avatar(self,raw,prepare=False,output=None):
        options=avatars.validate_options(raw)
        if not pack_ready(self.root,options['model']):
            raise ValueError('Install the selected talking-avatar model in Models first.')
        source=self.find_media(options['source_id'],options['source_type'])
        audio=next((x for x in self.recordings if x['id']==options['audio_id']),None)
        if not audio or not Path(audio['path']).is_file():
            raise ValueError('Import an existing voice recording in Talking Avatar first.')
        remaining=audio['duration']-options['audio_start']
        if remaining<.5:raise ValueError('Choose an audio start time before the end of the recording.')
        options['duration']=min(options['duration'],remaining)
        options['loras']=self.selected_loras(options['model'],raw) if options['model'] in ('avatar_longcat','avatar_infinite') else []
        def job():
            self.engine.stop()
            with self.lock:
                self.settings['avatar_options']=dict(options)
                self.remember_loras(options['model'],options['loras'])
                atomic_json(self.root/'settings.json',self.settings)
            file,seconds,result=avatars.generate(self.root,source,audio,options,output or self.settings['output'],self.report,self.cancel)
            info=dict(id=secrets.token_hex(12),path=str(file),name=file.name,kind='talking_avatar',
                parent_id=source['id'],audio_id=audio['id'],audio_name=audio['name'],
                created=time.strftime('%Y-%m-%d %H:%M'),options=options,seconds=seconds,
                width=result['width'],height=result['height'],duration=result['duration'],fps=result['fps'])
            atomic_json(metadata_path(file),info)
            self.thumbnails.get(info,'video')
            with self.lock:
                self.videos.append(info);self.revision+=1
                atomic_json(self.root/'library.json',self.videos)
                self.state['result']=info
                self.state['avatar_result']=info
                self.state['latest_media']={**info,'media_type':'video'}
            self.report('Talking avatar saved with your recording. The source is preserved.',1)
        return (job,options) if prepare else self.run_job(job,notify_completion=True)

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
            file,workflow,seconds=self.engine.generate(o,media_folder(self.root,'image',output),kind='enhance')
            info=dict(id=secrets.token_hex(12),path=str(file),name=file.name,kind='enhanced',parent_id=source['id'],
                      created=time.strftime('%Y-%m-%d %H:%M'),options=o,seconds=seconds,width=w,height=h)
            self.add_image(info,workflow)
        else:
            self.engine.stop()
            result=enhancements.run_video(self.root,source['path'],media_folder(self.root,'video',output),options,self.report,self.cancel)
            file=Path(result['output']);w,h=map(int,result['resolution'].split('x'))
            info=dict(id=secrets.token_hex(12),path=str(file),name=file.name,kind='enhanced',parent_id=source['id'],
                      created=time.strftime('%Y-%m-%d %H:%M'),options=options,seconds=result['seconds'],width=w,height=h)
            atomic_json(metadata_path(file),info)
            self.thumbnails.get(info,'video')
            with self.lock:
                self.videos.append(info);self.revision+=1;atomic_json(self.root/'library.json',self.videos)
                self.state['result']=info;self.state['latest_media']={**info,'media_type':'video'}
        self.report('Enhanced copy saved. The original remains in the library.',1)

    def upscale(self,raw,kind,prepare=False,output=None):
        source=self.find_media(raw.get('source_id'),kind)
        wrapper=self.auto_enhancement(dict(enabled=True,options=raw),kind)
        options={**wrapper['options'],'source_id':source['id'],'model':'qwen21' if kind=='image' else 'rtx_vsr'}
        def job():self.enhance_record(source,kind,wrapper['options'],output or self.settings['output'])
        return (job,options) if prepare else self.run_job(job,notify_completion=True)

    def generate_video_faceswap(self,raw,prepare=False,output=None):
        options=video_faceswap.validate(raw)
        if not video_faceswap.ready(self.root):raise ValueError('Install video faceswap in Faceswap or Models first.')
        source=self.find_media(options['source_id'],'video')
        reference=self.find_media(options['reference_id'],'image')
        frames=source.get('frames') or source.get('options',{}).get('frames')
        if frames and options['reference_frame']>=frames:raise ValueError('Choose a reference frame inside the target video.')
        def job():
            self.engine.stop()
            file,seconds,result=video_faceswap.run(self.root,source,reference,options,output or self.settings['output'],self.report,self.cancel)
            info=dict(id=secrets.token_hex(12),path=str(file),name=file.name,kind='video_faceswap',
                parent_id=source['id'],reference_id=reference['id'],reference_name=reference['name'],
                created=time.strftime('%Y-%m-%d %H:%M'),options=options,seconds=seconds,**result)
            atomic_json(metadata_path(file),info);self.thumbnails.get(info,'video')
            with self.lock:
                self.videos.append(info);self.revision+=1;atomic_json(self.root/'library.json',self.videos)
                self.settings['video_face_options']=options;atomic_json(self.root/'settings.json',self.settings)
                self.state.update(result=info,latest_media={**info,'media_type':'video'})
            self.report('Faceswapped video saved. The target video and reference image are preserved.',1)
        return (job,options) if prepare else self.run_job(job,notify_completion=True)

    def import_local_video(self,path):
        def job():
            info=video_faceswap.import_video(self.root,path,self.settings['output'],self.report,self.cancel)
            atomic_json(metadata_path(info['path']),info);self.thumbnails.get(info,'video')
            with self.lock:
                self.videos.append(info);self.revision+=1;atomic_json(self.root/'library.json',self.videos)
                self.state['latest_media']={**info,'media_type':'video'}
            self.report('Video copied into Library. The original file is preserved.',1)
        self.run_job(job)

    def prepare_queued(self,kind,raw,output=None):
        if kind=='faceswap_video':return self.generate_video_faceswap(raw,prepare=True,output=output)
        if kind=='voice':return self.generate_voice(raw,prepare=True,output=output)
        if kind=='faceswap':
            if raw.get('model')!='bfs':raise ValueError('Choose the BFS face-swap model.')
            return self.edit_image(raw,prepare=True,output=output)
        if kind=='avatar':return self.generate_avatar(raw,prepare=True,output=output)
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
        from packs import catalog
        if catalog().get(key,{}).get('kind')=='addon' and catalog()[key].get('family')=='moss_image':
            return [x for x in self.queue.jobs if x['status'] in ACTIVE and moss.is_model(x['options'].get('model'))]
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
            for key in ('options','image_options','edit_options','face_options'):
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
            if 'video_source_image' in data:
                identifier=data['video_source_image']
                if not isinstance(identifier,str) or len(identifier)>100:
                    raise ValueError('Choose a valid starting image from Library.')
                if identifier:self.find_media(identifier)
            if 'attention' in data:attention_support.validate(data['attention'])
            if 'completion_sound' in data and not isinstance(data['completion_sound'],bool):
                raise ValueError('Choose whether to play the completion sound.')
            previous=self.settings.copy();previous_attention=self.engine.attention
            if 'output' in data:
                if self.state["busy"]:
                    raise ValueError("Wait for the current operation to finish before changing folders.")
                output = Path(str(data['output'])).expanduser()
                if not output.is_absolute():
                    raise ValueError("Select a full output folder path.")
                for kind in ('image','video'):
                    media_folder(self.root,kind,output).mkdir(parents=True, exist_ok=True)
                self.settings["output"] = str(output.resolve())
            if 'completion_sound' in data:self.settings['completion_sound']=data['completion_sound']
            if 'video_source_image' in data:self.settings['video_source_image']=data['video_source_image']
            if 'attention' in data:
                self.settings['attention']=data['attention']
                self.engine.attention=data['attention']
            try:atomic_json(self.root / "settings.json", self.settings)
            except Exception:
                self.settings.clear();self.settings.update(previous)
                self.engine.attention=previous_attention
                raise

    def check_attention(self, enable=False):
        if not isinstance(enable,bool):raise ValueError('Choose whether to enable SageAttention after checking.')
        def job():
            self.engine.stop()
            result=attention_support.check(self.root,self.report,self.cancel)
            if enable and result.get('available'):
                self.save_settings({'attention':'sage'})
        self.run_job(job)


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
                              "Choose your Library folder (Images and Videos)", 0x41, callback, 0, 0)
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
    result = filedialog.askdirectory(initialdir=initial if Path(initial).exists() else str(Path.home()), title="Choose a library folder", parent=root)
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
            if url.path == '/api/health':
                if not self.authorized():
                    return self.send_json({'error': 'Unauthorized'}, 403)
                # The native window must remain responsive while a library request
                # holds the studio lock or the model drive is slow. No disk scans.
                return self.send_json({'ok': True, 'closing': studio.closing})
            if url.path == "/api/state":
                if not self.authorized():
                    return self.send_json({"error": "Unauthorized"}, 403)
                return self.send_json(studio.snapshot())
            if url.path.startswith('/api/canvas/'):
                if not self.authorized():return self.send_json({'error':'Unauthorized'},403)
                try:
                    if url.path=='/api/canvas/projects':return self.send_json({'items':canvas_projects.catalog(studio.root)})
                    if url.path=='/api/canvas/draft':project=canvas_projects.load(studio.root)
                    elif url.path.startswith('/api/canvas/project/'):project=canvas_projects.load(studio.root,url.path.removeprefix('/api/canvas/project/'))
                    else:raise ValueError('Unknown canvas request.')
                    ids={x['source_id'] for x in (project or {}).get('layers',[]) if x['kind']=='image'}
                    return self.send_json({'project':project,'sources':[{**x,'media_type':'image'} for x in list(studio.images) if x['id'] in ids]})
                except (ValueError,OSError) as error:return self.send_json({'error':str(error)},400)
            if url.path.startswith('/api/library/'):
                if not self.authorized():return self.send_json({'error':'Unauthorized'},403)
                try:
                    return self.send_json(media_details(list(studio.images),list(studio.videos),url.path.removeprefix('/api/library/')))
                except ValueError as error:return self.send_json({'error':str(error)},404)
            if url.path == '/api/library':
                if not self.authorized():
                    return self.send_json({'error':'Unauthorized'},403)
                try:
                    # Saved histories only append. Copy without waiting for a slow
                    # model/status scan that currently owns the Studio lock.
                    images,videos=list(studio.images),list(studio.videos)
                    page=catalog_page(images,videos,urllib.parse.parse_qs(url.query))
                    for item in page['items']:
                        item['thumbnail']=studio.thumbnails.describe(item,item['media_type'])
                    return self.send_json(page)
                except ValueError as error:
                    return self.send_json({'error':str(error)},400)
            if url.path == '/api/thumbnails':
                if not self.authorized():return self.send_json({'error':'Unauthorized'},403)
                ids=urllib.parse.parse_qs(url.query).get('ids',[''])[0].split(',')
                if len(ids)>100:return self.send_json({'error':'Too many preview requests'},400)
                records={x['id']:(x,kind) for items,kind in ((studio.images,'image'),(studio.videos,'video')) for x in items}
                return self.send_json({key:studio.thumbnails.describe(*records[key]) if key in records else {'status':'unavailable'} for key in ids})
            if url.path.startswith('/api/queue/'):
                if not self.authorized():return self.send_json({'error':'Unauthorized'},403)
                try:
                    with studio.lock:
                        item=studio.queue.get(url.path.removeprefix('/api/queue/'))
                        raw=studio.hydrate_queued(item)
                        identifiers=[raw.get('source_image'),raw.get('last_image'),raw.get('source_id'),raw.get('reference_id'),*raw.get('references',[])]
                        identifiers += [raw.get('moss',{}).get('color_id'),raw.get('moss',{}).get('depth_id')]
                        identifiers += raw.get('image_references',[])+raw.get('video_references',[])
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
                info=studio.thumbnails.describe(item,'image' if item in studio.images else 'video')
                if info['status']=='ready':
                    thumb=studio.thumbnails.root/'thumbnails'/(info['key']+'.jpg')
                    immutable=query.get('v',[''])[0]==info['key']
                    return self.send_file(thumb,'image/jpeg',cache_key=info['key'],immutable=immutable)
                if info['status']=='unavailable':return self.send_json({'error':'Preview unavailable'},404)
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
            if url.path.startswith('/audio/'):
                query=urllib.parse.parse_qs(url.query)
                if query.get('token',[''])[0]!=studio.token:return self.send_json({'error':'Unauthorized'},403)
                record=next((x for x in studio.recordings if x['id']==url.path.removeprefix('/audio/')),None)
                if not record or not Path(record['path']).is_file():return self.send_json({'error':'Recording not found'},404)
                return self.send_file(Path(record['path']),'audio/wav',ranges=True)
            if url.path == '/studio.js':
                return self.send_file(resource('studio.js'), 'text/javascript; charset=utf-8')
            if url.path == '/studio-tools.js':
                return self.send_file(resource('studio-tools.js'), 'text/javascript; charset=utf-8')
            if url.path == '/studio-updates.js':
                return self.send_file(resource('studio-updates.js'), 'text/javascript; charset=utf-8')
            if url.path == '/studio-avatars.js':
                return self.send_file(resource('studio-avatars.js'), 'text/javascript; charset=utf-8')
            if url.path == '/studio-video-faceswap.js':
                return self.send_file(resource('studio-video-faceswap.js'), 'text/javascript; charset=utf-8')
            if url.path == '/studio-moss.js':
                return self.send_file(resource('studio-moss.js'), 'text/javascript; charset=utf-8')
            if url.path == '/studio-canvas.js':
                return self.send_file(resource('studio-canvas.js'), 'text/javascript; charset=utf-8')
            if url.path == '/studio-references.js':
                return self.send_file(resource('studio-references.js'), 'text/javascript; charset=utf-8')
            if url.path == '/studio-ref2va.js':
                return self.send_file(resource('studio-ref2va.js'), 'text/javascript; charset=utf-8')
            if url.path == '/studio-minimax.js':
                return self.send_file(resource('studio-minimax.js'), 'text/javascript; charset=utf-8')
            if url.path == '/studio-qwen.js':
                return self.send_file(resource('studio-qwen.js'), 'text/javascript; charset=utf-8')
            if url.path == '/studio-voice.js':
                return self.send_file(resource('studio-voice.js'), 'text/javascript; charset=utf-8')
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

        def send_file(self, path, content_type, ranges=False, cache_key=None, immutable=False):
            if cache_key and self.headers.get('If-None-Match')=='"'+cache_key+'"':
                self.send_response(304)
                self.send_header('ETag','"'+cache_key+'"')
                self.send_header('Cache-Control','private, max-age=31536000, immutable' if immutable else 'private, no-cache')
                self.end_headers()
                return
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
            if cache_key:
                self.send_header('ETag','"'+cache_key+'"')
                self.send_header('Cache-Control','private, max-age=31536000, immutable' if immutable else 'private, no-cache')
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
                limit = 84*1024**2 if self.path=='/api/avatars/audio/import' else 36 * 1024**2 if self.path in ('/api/images/import','/api/images/import-source','/api/images/edit','/api/queue/add','/api/queue/action','/api/canvas/import','/api/canvas/export') else 512*1024 if self.path in ('/api/canvas/project','/api/canvas/draft') else 100000
                if not 0 <= length <= limit:
                    raise ValueError("Request is too large.")
                data = json.loads(self.rfile.read(length) or b"{}")
                if not isinstance(data, dict):
                    raise ValueError("Expected an object.")
                if self.path == '/api/updates/check':
                    return self.send_json(studio.updates.check())
                elif self.path in ('/api/canvas/import','/api/canvas/export'):
                    return self.send_json({'ok':True,'item':studio.canvas_image(data,self.path.endswith('/export'))})
                elif self.path in ('/api/canvas/project','/api/canvas/draft'):
                    return self.send_json({'ok':True,'project':canvas_projects.save(studio.root,data.get('project'),self.path.endswith('/draft'))})
                elif self.path == '/api/updates/install':
                    studio.install_update(data.get('ticket'),shutdown)
                elif self.path == "/api/generate":
                    return self.send_json({'ok':True,'id':studio.enqueue('video',data,data.get('priority',5))})
                elif self.path == '/api/avatars/audio/import':
                    studio.import_recording(data)
                elif self.path == '/api/voice/check':
                    return self.send_json(voices.check(data))
                elif self.path == '/api/attention/check':
                    studio.check_attention(data.get('enable',False))
                elif self.path == '/api/voice/settings':
                    connection=voices.connection(data)
                    with studio.lock:
                        studio.settings['voice_connection']=connection;atomic_json(studio.root/'settings.json',studio.settings)
                    return self.send_json({'ok':True})
                elif self.path == '/api/avatars/generate':
                    return self.send_json({'ok':True,'id':studio.enqueue('avatar',data,data.get('priority',5))})
                elif self.path == '/api/images/generate':
                    return self.send_json({'ok':True,'id':studio.enqueue('image',data,data.get('priority',5))})
                elif self.path == '/api/images/import':
                    studio.import_image(data)
                elif self.path == '/api/images/import-source':
                    return self.send_json({'ok':True,'item':studio.source_image(data)})
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
                elif self.path == '/api/faceswap/install-video':
                    def install_faceswap():
                        studio.engine.stop();video_faceswap.install(studio.root,studio.report,studio.cancel)
                    studio.run_job(install_faceswap)
                elif self.path == '/api/videos/import-local':
                    if studio.state['busy']:raise ValueError('Wait for the current operation to finish before importing a video.')
                    from native_files import pick_video
                    path=pick_video()
                    if not path:return self.send_json({'ok':True,'cancelled':True})
                    studio.import_local_video(path)
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
                            provision(studio.root, studio.report, studio.cancel, access, include_models='wan13' in keys)
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
                elif self.path == '/api/notifications/test':
                    if not play_completion_ping():raise ValueError('Windows could not play the ping. Check your audio output and volume.')
                elif self.path == "/api/pick-folder":
                    return self.send_json({"path": pick_folder(studio.settings["output"])})
                elif self.path == '/api/library/open-folder':
                    studio.open_library_folder(data.get('id'))
                elif self.path == "/api/open-folder":
                    kind = data.get("kind")
                    folder = lora_folder(studio.root,data.get('model','wan13')) if kind == "loras" else studio.root / "logs" if kind == "logs" else media_folder(studio.root,'image' if kind=='images' else 'video',studio.settings['output'])
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
    if not args.root:
        installed = installed_app_for_copy()
        if installed:
            subprocess.Popen([str(installed), *sys.argv[1:]], cwd=installed.parent,
                             creationflags=CREATE_NO_WINDOW)
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
