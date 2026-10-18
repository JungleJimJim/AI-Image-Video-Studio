"""Local MiniMax H3 FL2VA + Larry Turbo, using the pinned upstream extension."""
INTERNAL='studio/_minimax_h3_runtime/'
TURBO_FILES={'larry850':'minimax_h3_turbo_4step_ema_ckpt850.safetensors',
             'larryv4':'minimax_h3_turbo_v4_step600_ema.safetensors'}


def workflow(o,prefix):
    def node(kind,**inputs):return dict(class_type=kind,inputs=inputs)
    graph={
        '1':node('UNETLoader',unet_name='minimax_h3_fl2va_pruned_int8_convrot.safetensors',weight_dtype='default'),
        '2':node('CLIPLoader',clip_name='qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors',type='minimax',device='default'),
        '4':node('VAELoader',vae_name='minimax_h3_video_vae_fp16.safetensors'),
        '5':node('VAELoader',vae_name='minimax_h3_audio_vae_fp32.safetensors'),
        '6':node('MiniMaxH3ImageToVideo',prompt=o['prompt'],width=o['width'],height=o['height'],length=o['frames'],clip=['2',0],vae=['4',0]),
        '8':node('RandomNoise',noise_seed=o['seed']),
        '9':node('MiniMaxH3TurboSampler') if o['turbo']!='off' else node('KSamplerSelect',sampler_name='euler'),
        '10':node('BasicScheduler',scheduler='simple',steps=o['steps'],denoise=1,model=['142',0]),
        '11':node('BasicGuider',model=['142',0],conditioning=['6',0]),
        '12':node('SamplerCustomAdvanced',noise=['8',0],guider=['11',0],sampler=['9',0],sigmas=['10',0],latent_image=['6',1]),
        '13':node('VAEDecode',samples=['12',0],vae=['4',0]),
        '15':node('CreateVideo',images=['13',0],fps=24),
        '16':node('SaveVideo',video=['15',0],filename_prefix=prefix,format='mp4',**{'format.codec':'h264'}),
        '142':node('MiniMaxH3SigmaShift',model=['1',0],shift_video=12,shift_audio=3),
    }
    if o['turbo']!='off':
        graph['143']=node('MiniMaxH3TurboLoRA',model=['1',0],lora_name=INTERNAL+TURBO_FILES[o['turbo']],
            strength=o['turbo_strength'],low_vram=o['turbo_low_vram'])
        graph['142']['inputs']['model']=['143',0]
    from loras import apply_to_graph
    graph=apply_to_graph(graph,o,['143',0] if o['turbo']!='off' else ['1',0])
    if o['mode']=='image':
        graph['50']=node('LoadImage',image=o['input_file'])
        graph['6']['inputs']['first_frame']=['50',0]
        if o['last_image']:
            graph['51']=node('LoadImage',image=o['last_input_file'])
            graph['6']['inputs']['last_frame']=['51',0]
    if o['audio']:
        graph['14']=node('VAEDecodeAudio',samples=['12',0],vae=['5',0])
        graph['15']['inputs']['audio']=['14',0]
    return graph
