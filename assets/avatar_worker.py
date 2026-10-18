"""Isolated talking-avatar inference. Only --probe is allowed during CPU checks."""
import argparse
from collections import deque
import importlib
import inspect
import json
import math
import os
from pathlib import Path
import sys
import types
import wave


def package(name, path):
    module=types.ModuleType(name);module.__path__=[str(path)];sys.modules[name]=module
    return module


def bootstrap(root, engine, probe):
    sys.path[:0]=[str(engine/'avatar-dependencies'),str(engine/'dependencies'),str(engine/'code')]
    sys.argv=['avatar-worker','--cpu'] if probe else ['avatar-worker','--preview-method','none']
    os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1')
    import comfy.options
    comfy.options.enable_args_parsing()
    if probe:
        import comfy_kitchen
        comfy_kitchen.int8_attention_is_available=lambda *a,**k:False
    import folder_paths
    import server
    # These adapters also define ComfyUI preview routes. The worker has no HTTP
    # listener and does not use their browser previews; retain decorator semantics.
    class NoNetworkRoutes:
        def __getattr__(self,verb):return lambda *a,**k:lambda function:function
    server.PromptServer.instance=types.SimpleNamespace(routes=NoNetworkRoutes(),
        send_sync=lambda *a,**k:None,client_id=None,last_node_id=None)
    model_root=root/'runtime/ComfyUI_windows_portable/ComfyUI/models'
    old=Path(folder_paths.models_dir)
    for key,(paths,extensions) in list(folder_paths.folder_names_and_paths.items()):
        folder_paths.folder_names_and_paths[key]=([
            str(model_root/Path(path).relative_to(old)) if Path(path).is_relative_to(old) else path
            for path in paths],extensions)
    folder_paths.models_dir=str(model_root)
    sources=engine/'adapters'
    for key in ('wan','echo','soulx','dwpose'):
        package('studio_'+key,sources/key)
    # Upstream Flash refers to an omitted multi-GPU helper package. This desktop
    # workflow is single-GPU: rank 0 and world size 1 preserve its normal SDPA path.
    distributed=types.ModuleType('studio_echo.echomimic_v3.src.dist');distributed.__path__=[]
    distributed.get_sequence_parallel_rank=lambda:0
    distributed.get_sequence_parallel_world_size=lambda:1
    distributed.get_sp_group=lambda:types.SimpleNamespace(all_gather=lambda tensor,dim=1:tensor)
    def no_parallel(*args,**kwargs):raise ValueError('Multi-GPU avatar inference is not enabled in this desktop workflow.')
    distributed.xFuserLongContextAttention=no_parallel
    sys.modules[distributed.__name__]=distributed
    xfuser=types.ModuleType(distributed.__name__+'.wan_xfuser');xfuser.usp_attn_forward=no_parallel
    sys.modules[xfuser.__name__]=xfuser
    # Face cropping is disabled for SoulX: the complete selected image is used.
    # Delay its optional MediaPipe import rather than installing another detector.
    face_module=types.ModuleType('studio_soulx.flash_head.utils.cpu_face_handler')
    class UnusedFaceCrop:
        def __init__(self,*args,**kwargs):raise ValueError('Automatic SoulX face cropping is disabled; crop the image in Image Editor first.')
    face_module.CPUFaceHandler=UnusedFaceCrop
    sys.modules[face_module.__name__]=face_module
    # Echo's image-only path imports decord, although it does not use a reader.
    # Provide a portable PyAV reader for Windows rather than a missing decord DLL.
    if importlib.util.find_spec('decord') is None:
        import av
        import numpy as np
        class Array:
            def __init__(self, value):self.value=value
            def asnumpy(self):return self.value
        class Reader:
            def __init__(self,path,*args,**kwargs):
                with av.open(str(path)) as container:
                    self.fps=float(container.streams.video[0].average_rate or 25)
                    self.frames=[frame.to_ndarray(format='rgb24') for frame in container.decode(video=0)]
            def __len__(self):return len(self.frames)
            def __getitem__(self,index):return Array(self.frames[index])
            def get_batch(self,indices):return Array(np.stack([self.frames[i] for i in indices]))
            def get_avg_fps(self):return self.fps
        decord=types.ModuleType('decord');decord.__spec__=importlib.machinery.ModuleSpec('decord',loader=None)
        decord.VideoReader=Reader;decord.cpu=lambda *a:None;decord.bridge=types.SimpleNamespace(set_bridge=lambda *a:None)
        sys.modules['decord']=decord
    return model_root,sources


def invocation_kwargs(cls, kwargs):
    schema=cls.INPUT_TYPES()
    for key,kind in schema.get('required',{}).items():
        if key in kwargs:continue
        info=kind[1] if len(kind)>1 and isinstance(kind[1],dict) else {}
        if 'default' in info:kwargs[key]=info['default']
        elif isinstance(kind[0],list) and kind[0]:kwargs[key]=kind[0][0]
        elif kind[0]=='BOOLEAN':kwargs[key]=False
        else:raise ValueError('Missing avatar interface input: '+cls.__name__+'.'+key)
    return kwargs


def invoke(cls, **kwargs):
    kwargs=invocation_kwargs(cls,kwargs)
    target=cls();function=getattr(target,cls.FUNCTION)
    result=function(**kwargs)
    return result.get('result',result) if isinstance(result,dict) else result


def clip_voice(source,target,start,duration):
    with wave.open(str(source),'rb') as voice, wave.open(str(target),'wb') as output:
        rate=voice.getframerate();voice.setpos(min(int(start*rate),voice.getnframes()))
        output.setparams(voice.getparams());output.writeframes(voice.readframes(int(duration*rate)))
    with wave.open(str(target),'rb') as voice:
        return voice.getnframes()/voice.getframerate()


def pad_voice(source,target,duration):
    with wave.open(str(source),'rb') as voice, wave.open(str(target),'wb') as output:
        rate=voice.getframerate();frames=voice.getnframes()
        output.setparams(voice.getparams());output.writeframes(voice.readframes(frames))
        extra=max(0,math.ceil(duration*rate)-frames)
        output.writeframes(b'\0'*(extra*voice.getsampwidth()*voice.getnchannels()))


def load_pixels(path,width,height,count,fps,video=False):
    import cv2
    import numpy as np
    import torch
    from PIL import Image,ImageOps
    if not video:
        with Image.open(path) as source:
            rgb=np.array(ImageOps.fit(source.convert('RGB'),(width,height),method=Image.Resampling.LANCZOS))
        return torch.from_numpy(rgb).float().unsqueeze(0)/255
    capture=cv2.VideoCapture(str(path));source_fps=capture.get(cv2.CAP_PROP_FPS) or fps
    frames=[]
    try:
        for index in range(count):
            capture.set(cv2.CAP_PROP_POS_MSEC,index/source_fps*1000*source_fps/fps)
            ok,frame=capture.read()
            if not ok:break
            frame=cv2.cvtColor(frame,cv2.COLOR_BGR2RGB)
            frames.append(np.array(ImageOps.fit(Image.fromarray(frame),(width,height),method=Image.Resampling.LANCZOS)))
    finally:capture.release()
    if not frames:raise ValueError('The selected source video could not be decoded.')
    while len(frames)<count:frames.append(frames[-1])
    return torch.from_numpy(np.stack(frames)).float()/255


def audio_tensor(path):
    import numpy as np
    import torch
    with wave.open(str(path),'rb') as source:
        samples=np.frombuffer(source.readframes(source.getnframes()),dtype='<i2').copy()
        return dict(waveform=torch.from_numpy(samples).float().reshape(1,1,-1)/32768,
                    sample_rate=source.getframerate())


def echo(o,image,audio,models,sources):
    import torch
    import nodes
    from PIL import Image
    module=importlib.import_module('studio_echo.echomimic_v3.infer_flash_pro')
    clip=nodes.CLIPLoader().load_clip('umt5_xxl_fp8_e4m3fn_scaled.safetensors','wan',device='cpu')[0]
    vision=nodes.CLIPVisionLoader().load_clip('clip_vision_h.safetensors')[0]
    class VisionInput:
        # Echo uses diffusion-style [-1,1] pixels; Comfy's CLIP vision expects [0,1].
        def encode_image(self,pixels):return vision.encode_image((pixels+1)/2)
    pipeline,ratio,tokenizer=module.load_v3_flash('Flow_Unipc','Wan2.1_VAE.pth','none',
        str(models/'echo_mimic'),str(sources/'echo/echomimic_v3/config/config.yaml'),
        str(models/'avatars/echo'),'None','cuda',fsdp_dit=False,block_offload=True)
    ref=Image.fromarray((image[0].numpy()*255).astype('uint8'))
    frames=4*math.ceil(o['duration']*25/4)+1
    padded=Path(audio).with_name('echo-voice.wav');pad_voice(audio,padded,frames/25)
    embeds=module.Flash_Echo_v3_predata(VisionInput(),clip,tokenizer,o['prompt'],'blurry, distorted lips, subtitles',
        ref,(o['height'],o['width']),str(padded),str(models/'echo_mimic'),25,frames,ratio,'cuda',torch.bfloat16)
    kwargs={key:embeds[key] for key in ('audio_embeds','prompt_embeds','negative_prompt_embeds','clip_context',
        'input_video','input_video_mask','sample_height','sample_width','latent_frames')}
    return module.infer_flash(pipeline=pipeline,fps=25,num_inference_steps=o['steps'],seed=o['seed'],
        video_length_actual=embeds['video_length_actual'],device='cuda',block_offload=True,guidance_scale=6,
        audio_file_prefix='studio_avatar',**kwargs)


def soulx(o,image_path,audio,models,sources):
    import numpy as np
    import torch
    import librosa
    import yaml
    pipeline_module=importlib.import_module('studio_soulx.flash_head.src.pipeline.flash_head_pipeline')
    inference=importlib.import_module('studio_soulx.flash_head.inference')
    pipeline=pipeline_module.FlashHeadPipeline(str(models/'Soul-AILab/SoulX-FlashHead-1_3B'),
        o['variant'],str(models/'wav2vec/facebook/wav2vec2-base-960h'),device='cuda',use_usp=False)
    config=yaml.safe_load((sources/'soulx/flash_head/configs/infer_params.yaml').read_text())
    motion=(config['motion_frames_latent_num']-1)*pipeline.config.vae_stride[0]+1
    pipeline.prepare_params(cond_image_path_or_dir=str(image_path),target_size=(o['height'],o['width']),
        frame_num=config['frame_num'],motion_frames_num=motion,sampling_steps=4,seed=o['seed'],
        shift=config['sample_shift'],color_correction_strength=1,use_face_crop=False)
    samples,_=librosa.load(str(audio),sr=config['sample_rate'],mono=True)
    chunk=(config['frame_num']-motion)*config['sample_rate']//25
    samples=np.pad(samples,(0,(-len(samples))%chunk))  # Preserve the final spoken syllable.
    history=deque([0.0]*(config['sample_rate']*config['cached_audio_duration']),
                  maxlen=config['sample_rate']*config['cached_audio_duration'])
    end=config['cached_audio_duration']*25;start=end-config['frame_num']
    for index,part in enumerate(samples.reshape(-1,chunk)):
        history.extend(part.tolist())
        embedding=inference.get_audio_embedding(pipeline,np.asarray(history),start,end,infer_params=config)
        frames=inference.run_pipeline(pipeline,embedding).cpu().to(torch.uint8)
        # Streaming inference returns new frames; the context remains in the pipeline.
        for frame in frames:yield frame
        print('AVATAR_CHUNK',index+1,flush=True)


def wan(o,image,audio,models,longcat=False):
    import torch
    loaders=importlib.import_module('studio_wan.nodes_model_loading')
    nodes=importlib.import_module('studio_wan.nodes')
    sampler=importlib.import_module('studio_wan.nodes_sampler')
    multitalk=importlib.import_module('studio_wan.multitalk.nodes')
    block=invoke(loaders.WanVideoBlockSwap,blocks_to_swap=30)[0]
    vae=invoke(loaders.WanVideoVAELoader,model_name='wan_2.1_vae.safetensors',precision='bf16')[0]
    adapters=[]
    if longcat:
        adapters.append(dict(path=str(models/'avatars/longcat/LongCat-Avatar-15_dmd_distill_lora_rank128_bf16.safetensors'),
            strength=1.0,name='LongCat 1.5 distilled',blocks={},low_mem_load=True,merge_loras=False))
    for adapter in o.get('loras',[]):
        adapters.append(dict(path=adapter['path'],strength=adapter['strength'],name=adapter['name'],
            blocks={},low_mem_load=True,merge_loras=False))
    model_path=('avatars/longcat/LongCat-Avatar-15_comfy-Q4_K_M.gguf' if longcat else
                'avatars/infinitetalk/wan2.1-i2v-14b-480p-Q4_K_M.gguf')
    audio_model=None if longcat else invoke(multitalk.MultiTalkModelLoader,
        model='avatars/infinitetalk/Wan2_1-InfiniTetalk-Single_fp16.safetensors')[0]
    model=invoke(loaders.WanVideoModelLoader,model=model_path,base_precision='bf16',quantization='disabled',
        load_device='offload_device',attention_mode='sdpa',block_swap_args=block,
        lora=adapters or None,multitalk_model=audio_model)[0]
    text=invoke(nodes.WanVideoTextEncodeCached,model_name='umt5_xxl_fp8_e4m3fn_scaled.safetensors',
        precision='bf16',positive_prompt=o['prompt'],negative_prompt='blurry, distorted face, subtitles',device='cpu')[0]
    recording=audio_tensor(audio);count=4*math.ceil(o['duration']*25/4)+1
    if not longcat:
        wav2vec=invoke(multitalk.Wav2VecModelLoader,model='wav2vec2-chinese-base_fp16.safetensors',
            base_precision='fp16',load_device='offload_device')[0]
        embeddings=invoke(multitalk.MultiTalkWav2VecEmbeds,wav2vec_model=wav2vec,audio_1=recording,
            normalize_loudness=True,num_frames=count,fps=25,audio_scale=1,audio_cfg_scale=1,multi_audio_type='para')[0]
        import nodes as core
        vision=core.CLIPVisionLoader().load_clip('clip_vision_h.safetensors')[0]
        clip=invoke(nodes.WanVideoClipVisionEncode,clip_vision=vision,image_1=image[:1])[0]
        images=invoke(multitalk.WanVideoImageToVideoMultiTalk,vae=vae,width=o['width'],height=o['height'],
            frame_window_size=81,motion_frame=9,force_offload=True,colormatch='disabled',
            start_image=image,tiled_vae=True,clip_embeds=clip,mode='infinitetalk')[0]
        latent=invoke(sampler.WanVideoSampler,model=model,image_embeds=images,steps=o['steps'],cfg=5,
            shift=8,seed=o['seed'],scheduler='unipc',riflex_freq_index=0,force_offload=True,
            text_embeds=text,multitalk_embeds=embeddings)[0]
        return invoke(nodes.WanVideoDecode,vae=vae,samples=latent,enable_vae_tiling=True,
            tile_x=256,tile_y=256,tile_stride_x=128,tile_stride_y=128)[0]
    humo=importlib.import_module('studio_wan.HuMo.nodes')
    lc=importlib.import_module('studio_wan.LongCat.nodes')
    whisper=invoke(humo.WhisperModelLoader,model='avatar-whisper-large-v3.safetensors',
        base_precision='fp16',load_device='offload_device')[0]
    embeddings=invoke(lc.LongCatAvatarWhisperEmbeds,whisper_model=whisper,audio_1=recording,
        normalize_loudness=True,num_frames=count,fps=25,audio_scale=1,audio_cfg_scale=1,multi_audio_type='para')[0]
    ref=invoke(nodes.WanVideoEncode,vae=vae,image=image[:1],enable_vae_tiling=True,
        tile_x=256,tile_y=256,tile_stride_x=128,tile_stride_y=128)[0]
    previous=ref;previous_images=None;done=0;output=[]
    while done<count:
        overlap=13 if done else 1  # The first reference latent is one conditioning frame.
        prepared=lc.WanVideoLongCatAvatarExtendEmbeds.execute(prev_latents=previous,audio_embeds=embeddings,
            num_frames=81,overlap=overlap,if_not_enough_audio='mirror_from_end',frames_processed=done,
            ref_frame_index=10,ref_mask_frame_range=3,ref_latent=ref,prev_images=previous_images,vae=vae)[0]
        latent=invoke(sampler.WanVideoSampler,model=model,image_embeds=prepared,steps=8,cfg=1,
            shift=5,seed=o['seed']+done,scheduler='unipc',riflex_freq_index=0,
            force_offload=True,text_embeds=text)[0]
        pixels=invoke(nodes.WanVideoDecode,vae=vae,samples=latent,enable_vae_tiling=True,
            tile_x=256,tile_y=256,tile_stride_x=128,tile_stride_y=128)[0]
        fresh=pixels[overlap:] if done else pixels
        output.extend(fresh);done+=len(fresh)
        previous=latent;previous_images=pixels
        print('AVATAR_FRAMES',done,flush=True)
    return output


def musetalk(o,image,audio,models,sources):
    import cv2
    import numpy as np
    import torch
    import onnxruntime as ort
    from transformers import WhisperModel
    sys.path.insert(0,str(sources/'musetalk'))
    from musetalk.utils.utils import load_all_model,datagen
    from musetalk.utils.audio_processor import AudioProcessor
    from musetalk.utils.face_parsing import FaceParsing
    from musetalk.utils.blending import get_image
    detector=importlib.import_module('studio_dwpose.onnxdet')
    pose=importlib.import_module('studio_dwpose.onnxpose')
    model_dir=models/'avatars/musetalk';os.chdir(model_dir)
    paths=model_dir/'models'
    det=ort.InferenceSession(str(paths/'dwpose/yolox_l.onnx'),providers=['CPUExecutionProvider'])
    landmarks=ort.InferenceSession(str(paths/'dwpose/dw-ll_ucoco_384.onnx'),providers=['CPUExecutionProvider'])
    vae,unet,pe=load_all_model(str(paths/'musetalkV15/unet.pth'),'sd-vae',
        str(paths/'musetalkV15/musetalk.json'),device=torch.device('cuda'))
    vae.vae=vae.vae.half();vae._use_float16=True
    unet.model=unet.model.half();pe=pe.half().to('cuda')
    whisper=WhisperModel.from_pretrained(str(paths/'whisper'),local_files_only=True).to('cuda',dtype=torch.float16).eval()
    processor=AudioProcessor(feature_extractor_path=str(paths/'whisper'))
    feature,length=processor.get_audio_feature(str(audio))
    chunks=processor.get_whisper_chunk(feature,device='cuda',weight_dtype=torch.float16,whisper=whisper,
        librosa_length=length,fps=25,audio_padding_length_left=2,audio_padding_length_right=2)
    face_parser=FaceParsing(left_cheek_width=90,right_cheek_width=90)
    frames=[cv2.cvtColor((frame.numpy()*255).astype('uint8'),cv2.COLOR_RGB2BGR) for frame in image]
    boxes=[];latents=[];previous=None
    for frame in frames:
        bodies=detector.inference_detector(det,frame)
        points,scores=pose.inference_pose(landmarks,bodies,frame)
        if len(points):
            face=points[0,23:91];bottom=float(face[:,1].max());nose=float(face[29,1])
            previous=(max(0,int(face[:,0].min())),max(0,int(2*nose-bottom)),
                min(frame.shape[1],int(face[:,0].max())),min(frame.shape[0],int(bottom)+10))
        if previous is None:raise ValueError('No clear face was detected. Choose a front-facing portrait or clearer video.')
        x1,y1,x2,y2=previous
        if x2-x1<16 or y2-y1<16:raise ValueError('The face is too small. Crop closer in Image Editor first.')
        boxes.append(previous)
        crop=cv2.resize(frame[y1:y2,x1:x2],(256,256),interpolation=cv2.INTER_LANCZOS4)
        latents.append(vae.get_latents_for_unet(crop))
    cycle_frames=frames+frames[::-1];cycle_boxes=boxes+boxes[::-1];cycle_latents=latents+latents[::-1]
    index=0
    for embeddings,batch in datagen(chunks,cycle_latents,batch_size=4,device='cuda'):
        conditioning=pe(embeddings.to('cuda',dtype=torch.float16))
        predicted=unet.model(batch.to('cuda',dtype=torch.float16),torch.tensor([0],device='cuda'),encoder_hidden_states=conditioning).sample
        for face in vae.decode_latents(predicted):
            frame=cycle_frames[index%len(cycle_frames)];box=cycle_boxes[index%len(cycle_boxes)]
            x1,y1,x2,y2=box
            generated=cv2.resize(face.astype('uint8'),(x2-x1,y2-y1))
            blended=get_image(frame,generated,box,mode='jaw',fp=face_parser)
            yield cv2.cvtColor(blended,cv2.COLOR_BGR2RGB)
            index+=1
        print('AVATAR_FRAMES',index,flush=True)


def write_video(frames,silent,fps,limit):
    import imageio.v2 as imageio
    import numpy as np
    import torch
    count=0
    with imageio.get_writer(str(silent),fps=fps,codec='libx264',quality=8,macro_block_size=1) as writer:
        for frame in frames:
            if count>=limit:break
            if isinstance(frame,torch.Tensor):frame=frame.detach().cpu().numpy()
            frame=np.asarray(frame)
            if frame.ndim==3 and frame.shape[0] in (1,3,4) and frame.shape[-1] not in (1,3,4):frame=frame.transpose(1,2,0)
            if frame.dtype!=np.uint8:frame=np.clip(frame*255,0,255).astype('uint8')
            writer.append_data(frame[...,:3]);count+=1
    if not count:raise ValueError('The avatar model returned no frames.')
    return count


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',required=True);parser.add_argument('--job');parser.add_argument('--probe',action='store_true');parser.add_argument('--engine')
    args=parser.parse_args();root=Path(args.root).resolve();engine=Path(args.engine).resolve() if args.engine else root/'engines/avatar'
    models,sources=bootstrap(root,engine,args.probe)
    if args.probe:
        import torch
        import onnxruntime,librosa,diffusers,transformers,cv2
        for module in ('studio_echo.echomimic_v3.infer_flash_pro',
            'studio_soulx.flash_head.src.pipeline.flash_head_pipeline','studio_soulx.flash_head.inference',
            'studio_wan.nodes_model_loading','studio_wan.nodes','studio_wan.nodes_sampler',
            'studio_wan.multitalk.nodes','studio_wan.LongCat.nodes','studio_wan.HuMo.nodes',
            'studio_dwpose.onnxdet','studio_dwpose.onnxpose'):
            importlib.import_module(module)
        sys.path.insert(0,str(sources/'musetalk'))
        import musetalk.utils.audio_processor,musetalk.utils.face_parsing
        # Check actual invocation signatures without calling any loader/sampler.
        import ast
        modules={name:importlib.import_module(path) for name,path in {
            'loaders':'studio_wan.nodes_model_loading','nodes':'studio_wan.nodes',
            'sampler':'studio_wan.nodes_sampler','multitalk':'studio_wan.multitalk.nodes',
            'humo':'studio_wan.HuMo.nodes','lc':'studio_wan.LongCat.nodes'}.items()}
        calls=0
        for call in ast.walk(ast.parse(Path(__file__).read_text(encoding='utf-8'))):
            if not isinstance(call,ast.Call) or not isinstance(call.func,ast.Name) or call.func.id!='invoke':continue
            cls_expr=call.args[0]
            if not isinstance(cls_expr,ast.Attribute) or not isinstance(cls_expr.value,ast.Name):continue
            cls=getattr(modules[cls_expr.value.id],cls_expr.attr)
            values=invocation_kwargs(cls,{key.arg:None for key in call.keywords})
            inspect.signature(getattr(cls(),cls.FUNCTION)).bind(**values)
            calls+=1
        assert not torch.cuda.is_initialized(),'The avatar CPU probe initialized CUDA'
        print(json.dumps(dict(avatar_models=5,validated_node_calls=calls,cpu_only=True,generation_started=False)))
        return
    if not args.job:raise ValueError('Choose a queued avatar job.')
    import torch
    import numpy as np
    import imageio_ffmpeg
    import subprocess
    job_path=Path(args.job).resolve();job=json.loads(job_path.read_text());o=job['options'];work=job_path.parent
    import folder_paths
    folder_paths.set_output_directory(str(work))
    duration=clip_voice(job['audio']['path'],work/'voice.wav',o['audio_start'],o['duration']);o['duration']=duration
    if duration<.5:raise ValueError('The selected audio range is empty. Choose an earlier start time.')
    count=math.ceil(duration*25)
    image=load_pixels(job['source']['path'],o['width'],o['height'],count,25,o['source_type']=='video')
    from PIL import Image
    portrait=work/'portrait.png';Image.fromarray((image[0].numpy()*255).astype('uint8')).save(portrait)
    torch.manual_seed(o['seed']);np.random.seed(o['seed']%(2**32))
    with torch.inference_mode():
        if o['model']=='avatar_echo':frames=echo(o,image,work/'voice.wav',models,sources)
        elif o['model']=='avatar_soulx':frames=soulx(o,portrait,work/'voice.wav',models,sources)
        elif o['model']=='avatar_longcat':frames=wan(o,image,work/'voice.wav',models,True)
        elif o['model']=='avatar_infinite':frames=wan(o,image,work/'voice.wav',models)
        elif o['model']=='avatar_musetalk':frames=musetalk(o,image,work/'voice.wav',models,sources)
        else:raise ValueError('Unknown avatar model.')
        rendered=write_video(frames,work/'silent.mp4',25,count)
    result=subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-y','-loglevel','error','-i',str(work/'silent.mp4'),
        '-i',str(work/'voice.wav'),'-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','aac','-b:a','192k',
        '-t',str(duration),'-shortest',str(job['destination'])],capture_output=True,text=True,timeout=180)
    if result.returncode:raise RuntimeError('Could not attach the voice recording: '+result.stderr[-1000:])
    Path(job['result']).write_text(json.dumps(dict(path=job['destination'],width=o['width'],height=o['height'],
        duration=min(duration,rendered/25),frames=rendered,fps=25)),encoding='utf-8')
    for name in ('voice.wav','portrait.png','silent.mp4'):(work/name).unlink(missing_ok=True)


if __name__=='__main__':main()
