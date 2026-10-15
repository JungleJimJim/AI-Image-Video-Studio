"""Native ComfyUI graphs. Each model keeps its own architecture and sampling recipe."""
from pathlib import Path
import secrets
from packs import catalog
from loras import apply_to_graph


def node(kind, **inputs):
    return {'class_type': kind, 'inputs': inputs}


def decode(samples, vae):
    return node('VAEDecodeTiled', samples=samples, vae=vae, tile_size=512,
                overlap=64, temporal_size=32, temporal_overlap=8)


def wan22_workflow(o, prefix):
    g = {
        '1': node('UNETLoader', unet_name='wan2.2_ti2v_5B_fp16.safetensors', weight_dtype='default'),
        '2': node('CLIPLoader', clip_name='umt5_xxl_fp8_e4m3fn_scaled.safetensors', type='wan', device='default'),
        '3': node('VAELoader', vae_name='wan2.2_vae.safetensors'),
        '4': node('CLIPTextEncode', text=o['prompt'], clip=['2', 0]),
        '5': node('CLIPTextEncode', text=o['negative'], clip=['2', 0]),
        '6': node('Wan22ImageToVideoLatent', vae=['3',0], width=o['width'], height=o['height'], length=o['frames'], batch_size=1),
        '7': node('ModelSamplingSD3', model=['1', 0], shift=o['shift']),
        '8': node('KSampler', model=['7',0], positive=['4',0], negative=['5',0], latent_image=['6',0],
                  seed=o['seed'], steps=o['steps'], cfg=o['cfg'], sampler_name=o['sampler'], scheduler=o['scheduler'], denoise=1.0),
        '9': decode(['8',0], ['3',0]),
        '10': node('CreateVideo', images=['9',0], fps=o['fps']),
        '11': node('SaveVideo', video=['10',0], filename_prefix=prefix, format='mp4', **{'format.codec':'h264'}),
    }
    if o['mode'] == 'image':
        g['12'] = node('LoadImage', image=o['input_file'])
        g['6']['inputs']['start_image'] = ['12',0]
    return apply_to_graph(g, o, ['1',0])


def ltx_workflow(o, prefix):
    checkpoint = 'ltx-2-19b-distilled-fp8.safetensors'
    # The distilled checkpoint uses this published 8-step sigma schedule and CFG=1.
    # A single native pass avoids the additional upscaler and keeps 16 GB operation practical.
    g = {
        '1': node('CheckpointLoaderSimple', ckpt_name=checkpoint),
        '2': node('LTXAVTextEncoderLoader', text_encoder='gemma_3_12B_it_fp8_scaled.safetensors', ckpt_name=checkpoint, device='default'),
        '3': node('CLIPTextEncode', text=o['prompt'], clip=['2',0]),
        '4': node('ConditioningZeroOut', conditioning=['3',0]),
        '5': node('EmptyLTXVLatentVideo', width=o['width'], height=o['height'], length=o['frames'], batch_size=1),
        '6': node('LTXVAudioVAELoader', ckpt_name=checkpoint),
        '7': node('LTXVEmptyLatentAudio', frames_number=o['frames'], frame_rate=o['fps'], batch_size=1, audio_vae=['6',0]),
        '8': node('LTXVConcatAVLatent', video_latent=['5',0], audio_latent=['7',0]),
        '9': node('LTXVConditioning', positive=['3',0], negative=['4',0], frame_rate=o['fps']),
        '10': node('CFGGuider', model=['1',0], positive=['9',0], negative=['9',1], cfg=1.0),
        '11': node('KSamplerSelect', sampler_name='euler'),
        '12': node('ManualSigmas', sigmas='1, 0.99375, 0.9875, 0.98125, 0.975, 0.909375, 0.725, 0.421875, 0'),
        '13': node('RandomNoise', noise_seed=o['seed']),
        '14': node('SamplerCustomAdvanced', noise=['13',0], guider=['10',0], sampler=['11',0], sigmas=['12',0], latent_image=['8',0]),
        '15': node('LTXVSeparateAVLatent', av_latent=['14',0]),
        '16': decode(['15',0], ['1',2]),
        '17': node('CreateVideo', images=['16',0], fps=o['fps']),
        '18': node('SaveVideo', video=['17',0], filename_prefix=prefix, format='mp4', **{'format.codec':'h264'}),
    }
    if o['mode'] == 'image':
        g['19'] = node('LoadImage', image=o['input_file'])
        g['20'] = node('LTXVImgToVideoInplace', vae=['1',2], image=['19',0], latent=['5',0], strength=1.0, bypass=False)
        g['8']['inputs']['video_latent'] = ['20',0]
    if o.get('audio', True):
        g['21'] = node('LTXVAudioVAEDecode', samples=['15',1], audio_vae=['6',0])
        g['17']['inputs']['audio'] = ['21',0]
    return apply_to_graph(g, o, ['1',0])


IMAGE_DEFAULTS = dict(model='dreamshaper', prompt='', negative='blurry, low quality, artifacts, watermark, text',
                      width=1024, height=1024, steps=8, cfg=2.0, seed='', randomize_seed=True, memory='auto', loras=[])


def validate_image_options(raw):
    defaults = catalog().get(raw.get('model', IMAGE_DEFAULTS['model']), {}).get('defaults', {})
    o = {**IMAGE_DEFAULTS, **defaults, **{k:v for k,v in raw.items() if k in IMAGE_DEFAULTS}}
    pack = catalog().get(o['model'], {})
    if pack.get('kind') not in ('image', 'editor'):
        raise ValueError('Choose an installed image model.')
    for field in ('prompt', 'negative'):
        if not isinstance(o[field], str) or len(o[field]) > 10000:
            raise ValueError('Prompts must be text under 10,000 characters.')
    if not o['prompt'].strip():
        raise ValueError('Describe the image you want first.')
    for field, lo, hi in (('width',256,1536),('height',256,1536),('steps',1,60)):
        try:
            value = float(o[field])
            if not value.is_integer() or not lo <= value <= hi:
                raise ValueError()
            o[field] = int(value)
        except (TypeError, ValueError, OverflowError):
            raise ValueError(f'{field.capitalize()} must be a whole number from {lo} to {hi}.') from None
    if o['width'] % 64 or o['height'] % 64:
        raise ValueError('Image dimensions must be divisible by 64.')
    try:
        o['cfg'] = float(o['cfg'])
        if not 1 <= o['cfg'] <= 15:
            raise ValueError()
        s = str(o['seed']).strip()
        o['seed'] = secrets.randbelow(2**53) if s in ('','-1') else int(s)
        if not 0 <= o['seed'] < 2**53:
            raise ValueError()
    except (TypeError, ValueError, OverflowError):
        raise ValueError('Use CFG 1–15 and an empty seed or a whole number up to 9007199254740991.') from None
    if o['memory'] not in ('auto','low'):
        raise ValueError('Choose a supported memory mode.')
    if not isinstance(o['randomize_seed'], bool):
        raise ValueError('Choose whether to prepare a new seed for each job.')
    if o['model']=='flux3':o.update(cfg=1.0,negative='')
    return o


def image_workflow(o, prefix):
    if catalog()[o['model']]['family'] != 'sdxl':
        return native_image_workflow(o, prefix)
    filename = catalog()[o['model']]['files'][0]['filename']
    g = {
        '1': node('CheckpointLoaderSimple', ckpt_name=filename),
        '2': node('CLIPTextEncode', text=o['prompt'], clip=['1',1]),
        '3': node('CLIPTextEncode', text=o['negative'], clip=['1',1]),
        '4': node('EmptyLatentImage', width=o['width'], height=o['height'], batch_size=1),
        '5': node('KSampler', model=['1',0], positive=['2',0], negative=['3',0], latent_image=['4',0], seed=o['seed'],
                  steps=o['steps'], cfg=o['cfg'], sampler_name='dpmpp_sde' if o['model']=='dreamshaper' else 'dpmpp_2m', scheduler='karras', denoise=1.0),
        '6': node('VAEDecode', samples=['5',0], vae=['1',2]),
        '7': node('SaveImage', images=['6',0], filename_prefix=prefix),
    }
    return apply_to_graph(g, o, ['1',0], ['1',1])


def validate_edit_options(raw):
    o = validate_image_options(raw)
    if not catalog()[o['model']].get('editing'):
        raise ValueError('Choose a model that supports image editing.')
    source = raw.get('source_image', '')
    refs = raw.get('references', [])
    if not isinstance(source, str) or not source:
        raise ValueError('Choose a starting image.')
    maximum=catalog()[o['model']].get('max_references',3)-1
    if not isinstance(refs, list) or len(refs) > maximum or any(not isinstance(x, str) for x in refs):
        raise ValueError(f'Use up to {maximum} extra reference images with this model.')
    if len(set([source] + refs)) != len([source] + refs):
        raise ValueError('Choose different reference images.')
    if refs and o['model'] not in ('fluxklein', 'qwenedit', 'flux3'):
        raise ValueError('Multiple references require FLUX Klein or Qwen Image Edit.')
    try:
        strength = float(raw.get('strength', .65))
        if not 0 < strength <= 1:
            raise ValueError()
    except (ValueError, TypeError, OverflowError):
        raise ValueError('Redraw strength must be greater than zero and at most one.') from None
    return {**o, 'source_image': source, 'references': refs, 'strength': strength}


def native_image_workflow(o, prefix):
    pack = catalog()[o['model']]
    family = pack['family']
    diffusion, encoder, vae = [f['filename'] for f in pack['files']]
    g = {
        '1': node('UNETLoader', unet_name=diffusion, weight_dtype='default'),
        '2': node('CLIPLoader', clip_name=encoder, type=family if family in ('flux2','flux3') else 'lumina2' if family=='zimage' else 'qwen_image', device='default'),
        '3': node('VAELoader', vae_name=vae),
        '4': node('CLIPTextEncode', text=o['prompt'], clip=['2',0]),
        '5': node('CLIPTextEncode', text=o['negative'], clip=['2',0]),
        '6': node('EmptyFlux2LatentImage' if family in ('flux2','flux3') else 'EmptySD3LatentImage', width=o['width'], height=o['height'], batch_size=1),
        '7': node('ModelSamplingAuraFlow', model=['1',0], shift=3.1 if family=='qwenedit' else 3.0),
        '8': node('KSampler', model=['7',0], positive=['4',0], negative=['5',0], latent_image=['6',0], seed=o['seed'], steps=o['steps'], cfg=o['cfg'], sampler_name='res_multistep' if family=='zimage' else 'euler', scheduler='simple', denoise=1.0),
        '9': decode(['8',0], ['3',0]),
        '10': node('SaveImage', images=['9',0], filename_prefix=prefix),
    }
    if family in ('zimage', 'flux2','flux3'):
        g['5'] = node('ConditioningZeroOut', conditioning=['4',0])
        g['8']['inputs']['cfg'] = 1.0
    if family=='flux3':
        # FLUX 3's native loader supplies its own timestep shift; the FLUX.2 scheduler is different.
        del g['7'];g['8']['inputs']['model']=['1',0]
    if family == 'flux2':
        del g['7']
        g['8'] = node('SamplerCustomAdvanced', noise=['11',0], guider=['12',0], sampler=['13',0], sigmas=['14',0], latent_image=['6',0])
        g['11'] = node('RandomNoise', noise_seed=o['seed'])
        g['12'] = node('CFGGuider', model=['1',0], positive=['4',0], negative=['5',0], cfg=1.0)
        g['13'] = node('KSamplerSelect', sampler_name='euler')
        g['14'] = node('Flux2Scheduler', steps=o['steps'], width=o['width'], height=o['height'])
    return apply_to_graph(g, o, ['1',0])


def edit_workflow(o, prefix):
    family = catalog()[o['model']]['family']
    if family=='flux3':return flux3_edit_workflow(o,prefix)
    g = image_workflow(o, prefix)
    g['20'] = node('LoadImage', image=o['input_file'])
    g['21'] = node('ImageScale', image=['20',0], upscale_method='lanczos', width=o['width'], height=o['height'], crop='disabled')
    source = ['21',0]
    vae = ['1',2] if family=='sdxl' else ['3',0]
    refs = [source]
    for index, filename in enumerate(o.get('reference_files', [])):
        key = str(30+index)
        g[key] = node('LoadImage', image=filename)
        g[str(32+index)] = node('ImageScaleToTotalPixels', image=[key,0], upscale_method='lanczos', megapixels=1.0, resolution_steps=1)
        refs.append([str(32+index),0])
    if family=='sdxl':
        g['4'] = node('VAEEncode', pixels=source, vae=vae)
        g['5']['inputs']['denoise'] = o['strength']
        output, save_key = ['6',0], '7'
    else:
        output, save_key = ['9',0], '10'
        if family=='flux2':
            positive, negative = ['4',0], ['5',0]
            for index, pixels in enumerate(refs):
                base = 40 + index*3
                g[str(base)] = node('VAEEncode', pixels=pixels, vae=vae)
                g[str(base+1)] = node('ReferenceLatent', conditioning=positive, latent=[str(base),0])
                g[str(base+2)] = node('ReferenceLatent', conditioning=negative, latent=[str(base),0])
                positive, negative = [str(base+1),0], [str(base+2),0]
            g['12']['inputs'].update(positive=positive, negative=negative)
        elif family=='qwenedit':
            images = {f'image{i+1}':ref for i,ref in enumerate(refs)}
            g['4'] = node('TextEncodeQwenImageEditPlus', clip=['2',0], vae=vae, prompt=o['prompt'], **images)
            g['5'] = node('TextEncodeQwenImageEditPlus', clip=['2',0], vae=vae, prompt=o['negative'], **images)
            g['22'] = node('FluxKontextMultiReferenceLatentMethod', conditioning=['4',0], reference_latents_method='index_timestep_zero')
            g['23'] = node('FluxKontextMultiReferenceLatentMethod', conditioning=['5',0], reference_latents_method='index_timestep_zero')
            g['24'] = node('CFGNorm', model=['7',0], strength=1.0)
            g['6'] = node('VAEEncode', pixels=source, vae=vae)
            g['8']['inputs'].update(model=['24',0], positive=['22',0], negative=['23',0])
    if o.get('mask_file'):
        g['60'] = node('LoadImage', image=o['mask_file'])
        g['61'] = node('ImageScale', image=['60',0], upscale_method='nearest-exact', width=o['width'], height=o['height'], crop='disabled')
        # Canvas masks are opaque RGB; LoadImage's alpha mask would be empty.
        g['62'] = node('ImageToMask', image=['61',0], channel='red')
        if family=='sdxl':
            g['4'] = node('VAEEncodeForInpaint', pixels=source, vae=vae, mask=['62',0], grow_mask_by=6)
        # Instruction models edit the full image; composite only the painted area.
        g['63'] = node('ImageCompositeMasked', destination=source, source=output, x=0, y=0, resize_source=False, mask=['62',0])
        g[save_key]['inputs']['images'] = ['63',0]
    return g


def flux3_edit_workflow(o,prefix):
    g=image_workflow(o,prefix)
    g['20']=node('LoadImage',image=o['input_file'])
    g['21']=node('ImageScale',image=['20',0],upscale_method='lanczos',width=o['width'],height=o['height'],crop='disabled')
    refs={'images.image0':['21',0]}
    for index,filename in enumerate(o.get('reference_files',[])):
        loaded,scaled=str(30+index),str(50+index)
        g[loaded]=node('LoadImage',image=filename)
        g[scaled]=node('ImageScaleToTotalPixels',image=[loaded,0],upscale_method='lanczos',megapixels=1.0,resolution_steps=1)
        refs[f'images.image{index+1}']=[scaled,0]
    g['22']=node('ReferenceMultiLatent',positive=['4',0],negative=['5',0],vae=['3',0],resolution='keep resolution',**refs)
    g['8']['inputs'].update(positive=['22',0],negative=['22',1])
    if o.get('mask_file'):
        g['60']=node('LoadImage',image=o['mask_file'])
        g['61']=node('ImageScale',image=['60',0],upscale_method='nearest-exact',width=o['width'],height=o['height'],crop='disabled')
        g['62']=node('ImageToMask',image=['61',0],channel='red')
        g['63']=node('ImageCompositeMasked',destination=['21',0],source=['9',0],x=0,y=0,resize_source=False,mask=['62',0])
        g['10']['inputs']['images']=['63',0]
    return g
