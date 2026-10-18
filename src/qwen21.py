"""Viggle six-step generation/editing and BFS two-image head replacement."""
from workflows import node,decode
from loras import apply_to_graph

FACE_PROMPT=('head_swap: start with <image1> as the base image, keeping its lighting, environment, and background. '
    'Remove its head and replace it with the head from <image2>, preserving the reference identity, hair, eye color and nose. '
    'Keep the head rotation, gaze and expression from <image1>. Sharp details, natural skin texture.')

def workflow(o,prefix):
    viggle=o['model']=='viggle'
    g={
      '1':node('UNETLoader',unet_name='qwen_image_2.1_int8_convrot.safetensors',weight_dtype='default'),
      '2':node('CLIPLoader',clip_name='qwen3vl_8b_int8_convrot.safetensors',type='qwen_image',device='default'),
      '3':node('VAELoader',vae_name='qwen_image_2.1_vae_bf16.safetensors'),
      '4':node('TextEncodeQwenImage21',clip=['2',0],vae=['3',0],prompt=o['prompt'],negative_prompt='',resolution=0),
      '6':node('EmptyLatentImage',width=o['width'],height=o['height'],batch_size=1),
      '7':node('ViggleTurboLora',model=['1',0],lora_name='studio/_qwen21_runtime/Qwen-Image-2.1-viggle-turbo-v0.3-6step-lora-r128.safetensors',strength=1) if viggle else
          node('LoraLoaderModelOnly',model=['1',0],lora_name='studio/_qwen21_runtime/bfs_head_v1.1_qwen_2.1.safetensors',strength_model=1),
      '9':decode(['8',0],['3',0]),'10':node('SaveImage',images=['9',0],filename_prefix=prefix),
    }
    if o.get('input_file'):
        g['20']=node('LoadImage',image=o['input_file'])
        g['21']=node('ImageScale',image=['20',0],upscale_method='lanczos',width=o['width'],height=o['height'],crop='disabled')
        g['4']['inputs']['images.image_1']=['21',0]
        for index,file in enumerate(o.get('reference_files',[])):
            loaded,scaled=str(30+index),str(40+index)
            g[loaded]=node('LoadImage',image=file)
            g[scaled]=node('ImageScaleToTotalPixels',image=[loaded,0],upscale_method='lanczos',megapixels=1,resolution_steps=32)
            g['4']['inputs'][f'images.image_{index+2}']=[scaled,0]
    if viggle:
        g.update({
          '8':node('SamplerCustomAdvanced',noise=['11',0],guider=['12',0],sampler=['13',0],sigmas=['14',0],latent_image=['6',0]),
          '11':node('RandomNoise',noise_seed=o['seed']),
          '12':node('BasicGuider',model=['7',0],conditioning=['4',0]),
          '13':node('KSamplerSelect',sampler_name='euler'),
          '14':node('ViggleTurboSigmas',latent=['6',0],nodes='1.0, 0.9375, 0.875, 0.75, 0.5, 0.25'),
        })
    else:
        g['8']=node('KSampler',model=['7',0],positive=['4',0],negative=['4',1],latent_image=['6',0],seed=o['seed'],steps=o['steps'],cfg=1,sampler_name='euler',scheduler='simple',denoise=1)
    g=apply_to_graph(g,o,['7',0])
    if o.get('mask_file'):
        g['60']=node('LoadImage',image=o['mask_file'])
        g['61']=node('ImageScale',image=['60',0],upscale_method='nearest-exact',width=o['width'],height=o['height'],crop='disabled')
        g['62']=node('ImageToMask',image=['61',0],channel='red')
        g['63']=node('ImageCompositeMasked',destination=['21',0],source=['9',0],x=0,y=0,resize_source=False,mask=['62',0])
        g['10']['inputs']['images']=['63',0]
    return g
