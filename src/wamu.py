"""Two-stage WAMU Lightning image-to-video workflow for original Diffusers shards."""
from workflows import node,decode
from loras import apply_to_graph

def workflow(o,prefix):
    g={
      '1':node('WAMUShardedLoader',stage='high'),
      '2':node('WAMUShardedLoader',stage='low'),
      '3':node('CLIPLoader',clip_name='umt5_xxl_fp8_e4m3fn_scaled.safetensors',type='wan',device='default'),
      '4':node('VAELoader',vae_name='wan_2.1_vae.safetensors'),
      '5':node('CLIPTextEncode',clip=['3',0],text=o['prompt']),
      '6':node('CLIPTextEncode',clip=['3',0],text=o['negative']),
      '7':node('LoadImage',image=o['input_file']),
      '8':node('WanImageToVideo',positive=['5',0],negative=['6',0],vae=['4',0],width=o['width'],height=o['height'],length=o['frames'],batch_size=1,start_image=['7',0]),
      '9':node('ModelSamplingSD3',model=['1',0],shift=3),
      '10':node('ModelSamplingSD3',model=['2',0],shift=3),
      '11':node('BasicScheduler',model=['9',0],scheduler='simple',steps=o['steps'],denoise=1),
      '12':node('WAMUSplitSigmas',sigmas=['11',0]),
      '13':node('KSamplerSelect',sampler_name='uni_pc'),
      '14':node('RandomNoise',noise_seed=o['seed']),
      '15':node('CFGGuider',model=['9',0],positive=['8',0],negative=['8',1],cfg=1),
      '16':node('SamplerCustomAdvanced',noise=['14',0],guider=['15',0],sampler=['13',0],sigmas=['12',0],latent_image=['8',2]),
      '17':node('DisableNoise'),
      '18':node('CFGGuider',model=['10',0],positive=['8',0],negative=['8',1],cfg=1),
      '19':node('SamplerCustomAdvanced',noise=['17',0],guider=['18',0],sampler=['13',0],sigmas=['12',1],latent_image=['16',0]),
      '20':decode(['19',0],['4',0]),
      '21':node('CreateVideo',images=['20',0],fps=o['fps']),
      '22':node('SaveVideo',video=['21',0],filename_prefix=prefix,format='mp4',**{'format.codec':'h264'}),
    }
    g=apply_to_graph(g,o,['1',0],start=1000)
    return apply_to_graph(g,o,['2',0],start=1100)
