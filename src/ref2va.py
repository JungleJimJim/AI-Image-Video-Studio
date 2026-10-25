"""MiniMax H3 reference video with the pinned Kablex VSA extension."""
INTERNAL='studio/_ref2va_runtime/'


def workflow(o,prefix):
    def node(kind,**inputs):return dict(class_type=kind,inputs=inputs)
    graph={
        '1':node('UNETLoader',unet_name='minimax_h3_ref2va_pruned_int8_convrot.safetensors',weight_dtype='default'),
        '2':node('CLIPLoader',clip_name='qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors',type='minimax',device='default'),
        '4':node('VAELoader',vae_name='minimax_h3_video_vae_fp16.safetensors'),
        '5':node('VAELoader',vae_name='minimax_h3_audio_vae_fp32.safetensors'),
        '6':node('MiniMaxH3ReferenceToVideo',prompt=o['prompt'],width=o['width'],height=o['height'],length=o['frames'],
            ref_image_size='match',clip=['2',0],vae=['4',0],audio_vae=['5',0],**{'ref_images.ref_image_0':['50',0]}),
        '8':node('RandomNoise',noise_seed=o['seed']),
        '9':node('KSamplerSelect',sampler_name='euler'),
        '10':node('BasicScheduler',scheduler='simple',steps=4,denoise=1,model=['142',0]),
        '11':node('BasicGuider',model=['142',0],conditioning=['6',0]),
        '12':node('SamplerCustomAdvanced',noise=['8',0],guider=['11',0],sampler=['9',0],sigmas=['10',0],latent_image=['6',1]),
        '13':node('VAEDecode',samples=['12',0],vae=['4',0]),
        '15':node('CreateVideo',images=['13',0],fps=24),
        '16':node('SaveVideo',video=['15',0],filename_prefix=prefix,format='mp4',**{'format.codec':'h264'}),
        '50':node('LoadImage',image=o['input_file']),
        '143':node('LoraLoaderModelOnly',model=['1',0],lora_name=INTERNAL+'minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors',strength_model=1),
        '142':node('MiniMaxH3SigmaShift',model=['143',0],shift_video=12,shift_audio=3),
    }
    for index,filename in enumerate(o.get('reference_files',[]),1):
        key=str(50+index);graph[key]=node('LoadImage',image=filename)
        graph['6']['inputs']['ref_images.ref_image_'+str(index)]=[key,0]
    from loras import apply_to_graph
    graph=apply_to_graph(graph,o,['143',0])
    if o['vsa']:
        graph['144']=node('Ref2VAVSAGatePatch',model=graph['142']['inputs']['model'],
            gate_file=INTERNAL+'fasth3_vsa_gate.safetensors',sparsity=o['sparsity'])
        graph['142']['inputs']['model']=['144',0]
    if o['audio']:
        graph['14']=node('VAEDecodeAudio',samples=['12',0],vae=['5',0])
        graph['15']['inputs']['audio']=['14',0]
    return graph
