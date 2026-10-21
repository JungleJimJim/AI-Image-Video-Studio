"""MOSS native image graphs, validated layouts and optional control-map inputs."""
import json
import math
import re
from pathlib import Path

ENCODERS = {'w4a8':'qwen3.5_9b_w4a8_gptq.safetensors', 'int8':'qwen3.5_9b_int8_convrot.safetensors', 'bf16':'qwen3.5_9b_bf16.safetensors'}
ADAPTERS = {'sft8':'moss_sft_8step_dmd.safetensors', 'dmd':'kromoss_8step_dmd.safetensors', 'dmd2':'kromoss_8step_dmd2.safetensors', 'control':'moss_image_color_depth_control.safetensors'}
DEFAULTS = dict(recipe='full', fast_steps=8, prompt_mode='text', layout=[], encoder='default', vae='small', shift=5.0,
                skip_layer=22, color_id='', depth_id='', control_strength=1.0, control_start=0.0, control_end=.5)


def is_model(model):
    from packs import catalog
    p=catalog().get(model,{})
    return p.get('family')=='moss_image' and p.get('kind')=='image'


def number(value, low, high, label):
    try:
        n=float(value)
        if not math.isfinite(n) or not low<=n<=high:raise ValueError()
        return n
    except (ValueError,TypeError,OverflowError):
        raise ValueError(f'{label} must be between {low} and {high}.') from None


def validate(raw, options):
    from packs import catalog
    source=raw.get('moss',{})
    if not isinstance(source,dict):raise ValueError('Choose valid MOSS settings.')
    o={**DEFAULTS,**{k:v for k,v in source.items() if k in DEFAULTS}}
    variant=catalog()[options['model']]['moss_variant']
    choices=('full','sft8') if variant=='moss_sft' else ('full','dmd','dmd2')
    if o['recipe'] not in choices:raise ValueError('Choose a fast LoRA compatible with this MOSS variant.')
    if o['fast_steps'] not in (4,8):raise ValueError('Choose 4 or 8 fast sampling steps.')
    if o['recipe']=='sft8':o['fast_steps']=8
    for key,choices in [('prompt_mode',('text','tags','layout','json')),('encoder',('default',*ENCODERS)),('vae',('small','full'))]:
        if o[key] not in choices:raise ValueError('Choose a supported MOSS '+key+'.')
    for key in ('color_id','depth_id'):
        if not isinstance(o[key],str) or len(o[key])>100:raise ValueError('Choose a Library image for the MOSS map.')
    o['shift']=number(o['shift'],.1,20,'MOSS shift')
    o['control_strength']=number(o['control_strength'],0,10,'Control strength')
    o['control_start']=number(o['control_start'],0,1,'Control start')
    o['control_end']=number(o['control_end'],0,1,'Control end')
    if o['control_start']>o['control_end']:raise ValueError('Control must end after it starts.')
    skip=number(o['skip_layer'],-1,27,'Negative-branch skip layer')
    if not skip.is_integer():raise ValueError('Skip layer must be a whole number; -1 disables it.')
    o['skip_layer']=int(skip)
    layout=o['layout']
    if not isinstance(layout,list) or len(layout)>24:raise ValueError('Use up to 24 MOSS layout elements.')
    clean=[]
    for element in layout:
        if not isinstance(element,dict) or element.get('type') not in ('object','character','text'):
            raise ValueError('Choose object, character or text for each layout element.')
        item={k:element.get(k,'') for k in ('type','caption','text','palette')}
        if any(not isinstance(item[k],str) or len(item[k])>1000 for k in ('caption','text','palette')):
            raise ValueError('Layout captions, text and colors must be under 1,000 characters.')
        for key in ('x','y','w','h'):item[key]=number(element.get(key),0 if key in ('x','y') else .1,100,'Layout '+key)
        if item['x']+item['w']>100.00001 or item['y']+item['h']>100.00001:
            raise ValueError('Keep every layout box inside the canvas.')
        if item['palette'] and any(not re.fullmatch(r'#[0-9a-fA-F]{6}',v.strip()) for v in item['palette'].split(',')):
            raise ValueError('Use comma-separated hex colors such as #ff8844, #2255aa.')
        clean.append(item)
    o['layout']=clean
    if o['prompt_mode']=='layout' and not clean:raise ValueError('Add an object or text box to the MOSS layout.')
    if o['prompt_mode']=='json':
        try:
            value=json.loads(options['prompt'])
            if not isinstance(value,dict) or not isinstance(value.get('items'),list) or not isinstance(value.get('summary'),dict):raise ValueError()
            if value.get('bbox_format')!='yxyx' or value.get('bbox_coord_space')!='abs_centralized':raise ValueError()
            for item in value['items']:
                if not isinstance(item,dict):raise ValueError()
                box=item.get('bbox',[])
                if (not isinstance(box,list) or len(box)!=4 or any(not isinstance(v,(int,float)) or not math.isfinite(v) for v in box)
                        or box[0]>=box[2] or box[1]>=box[3]):raise ValueError()
        except (ValueError,TypeError):raise ValueError('Paste a MOSS layout JSON object with summary and items.') from None
    if o['recipe']!='full':options.update(steps=o['fast_steps'],cfg=1.0,negative='')
    options['moss']=o
    return options


def layout_prompt(caption, elements, width, height):
    items=[]
    for el in elements:
        item=dict(label=el['type'],caption=el['caption'],bbox=[
            math.floor(el['y']*height/100)-height//2, math.floor(el['x']*width/100)-width//2,
            math.ceil((el['y']+el['h'])*height/100)-height//2,math.ceil((el['x']+el['w'])*width/100)-width//2])
        if el['type']=='text':item['text']=el['text']
        if el['palette']:item['palette']=[v.strip() for v in el['palette'].split(',')]
        items.append(item)
    return json.dumps(dict(summary=dict(caption=caption.strip()),items=items,bbox_coord_space='abs_centralized',bbox_format='yxyx'),ensure_ascii=False,separators=(',',':'))


def prepare(studio, options):
    """Validate feature files and Library IDs before queueing; stage only at run time."""
    from common import comfy_root
    from packs import catalog
    c=options['moss'];specs=catalog()
    encoder=c['encoder'] if c['encoder']!='default' else specs[options['model']]['moss_encoder']
    required=[('text_encoders',ENCODERS[encoder])]
    if c['vae']=='full':required.append(('vae','moss_flux2_vae_full.safetensors'))
    if c['recipe']!='full':required.append(('loras/studio/moss_image',ADAPTERS[c['recipe']]))
    maps={key:studio.find_media(c[key]) for key in ('color_id','depth_id') if c[key]}
    if maps:required.append(('loras/studio/moss_image',ADAPTERS['control']))
    for _,filename in required:
        found=next(f for p in specs.values() for f in p['files'] if f['filename']==filename)
        path=comfy_root(studio.root)/'models'/found['folder']/filename
        if not path.is_file() or path.stat().st_size!=found['size']:
            name='MOSS fast LoRAs & color/depth control' if filename in ADAPTERS.values() else 'MOSS full VAE' if filename=='moss_flux2_vae_full.safetensors' else 'MOSS text encoder · '+encoder.upper()
            raise ValueError('Install '+name+' using Install selected components in the MOSS controls, or open Models.')
    for lora in options.get('loras',[]):
        if lora['name'].replace('\\','/').rsplit('/',1)[-1] in ADAPTERS.values():
            raise ValueError('Configure built-in MOSS adapters using its Acceleration and Control map options, rather than adding them again as custom LoRAs.')
    return maps


def stage(studio, options, maps):
    from images import stage_image
    for key,item in maps.items():options['moss'][key.replace('_id','_file')]=stage_image(studio.root,item)


def workflow(o, prefix):
    from packs import catalog
    from workflows import node, decode
    from loras import apply_to_graph
    pack=catalog()[o['model']];c=o['moss'];model=pack['files'][0]['filename']
    encoder=ENCODERS[pack['moss_encoder'] if c['encoder']=='default' else c['encoder']]
    prompt=layout_prompt(o['prompt'],c['layout'],o['width'],o['height']) if c['prompt_mode']=='layout' else o['prompt']
    g={'1':node('UNETLoader',unet_name=model,weight_dtype='default'),
       '2':node('CLIPLoader',clip_name=encoder,type='moss_image',device='default'),
       '3':node('VAELoader',vae_name='flux2-vae_small.safetensors' if c['vae']=='small' else 'moss_flux2_vae_full.safetensors'),
       '4':node('CLIPTextEncode',clip=['2',0],text=prompt),
       '5':node('CLIPTextEncode',clip=['2',0],text=o['negative']),
       '6':node('EmptyFlux2LatentImage',width=o['width'],height=o['height'],batch_size=1),
       '7':node('ModelSamplingAuraFlow',model=['1',0],shift=c['shift']),
       '8':node('KSampler',model=['7',0],positive=['4',0],negative=['5',0],latent_image=['6',0],seed=o['seed'],steps=o['steps'],cfg=o['cfg'],sampler_name='euler',scheduler='simple',denoise=1.),
       '9':decode(['8',0],['3',0]),'10':node('SaveImage',images=['9',0],filename_prefix=prefix)}
    loaded=['1',0]
    if c['recipe']!='full':
        g['11']=node('LoraLoaderModelOnly',model=loaded,lora_name='studio/moss_image/'+ADAPTERS[c['recipe']],strength_model=1.0);loaded=['11',0]
        g['5']=node('ConditioningZeroOut',conditioning=['4',0])
    if c['color_id'] or c['depth_id']:
        g['12']=node('LoraLoaderModelOnly',model=loaded,lora_name='studio/moss_image/'+ADAPTERS['control'],strength_model=1.0);loaded=['12',0]
        maps={}
        for index,key in enumerate(('color','depth')):
            if not c[key+'_id']:continue
            if not c.get(key+'_file'):raise ValueError('The MOSS control image was not staged.')
            load,scale=str(20+index*2),str(21+index*2)
            g[load]=node('LoadImage',image=c[key+'_file'])
            g[scale]=node('ImageScale',image=[load,0],upscale_method='nearest-exact' if key=='color' else 'bilinear',width=o['width'],height=o['height'],crop='disabled')
            maps[key+'_map']=[scale,0]
        g['14']=node('MOSSImageControl',positive=['4',0],negative=['5',0],vae=['3',0],strength=c['control_strength'],start_percent=c['control_start'],end_percent=c['control_end'],**maps)
        g['8']['inputs'].update(positive=['14',0],negative=['14',1])
    g['7']['inputs']['model']=loaded
    if c['recipe']=='full' and c['skip_layer']>=0 and not o['negative'].strip():
        g['15']=node('SkipLayerGuidanceDiTSimple',model=['7',0],double_layers='',single_layers=str(c['skip_layer']),start_percent=0.,end_percent=1.)
        g['8']['inputs']['model']=['15',0]
    if o.get('input_file'):
        g['30']=node('LoadImage',image=o['input_file'])
        g['31']=node('ImageScale',image=['30',0],upscale_method='lanczos',width=o['width'],height=o['height'],crop='disabled')
        g['6']=node('VAEEncode',pixels=['31',0],vae=['3',0]);g['8']['inputs']['denoise']=o['strength']
        if o.get('mask_file'):
            g['32']=node('LoadImage',image=o['mask_file'])
            g['33']=node('ImageToMask',image=['32',0],channel='red')
            g['34']=node('SetLatentNoiseMask',samples=['6',0],mask=['33',0]);g['8']['inputs']['latent_image']=['34',0]
            g['35']=node('ImageCompositeMasked',destination=['31',0],source=['9',0],x=0,y=0,resize_source=False,mask=['33',0]);g['10']['inputs']['images']=['35',0]
    return apply_to_graph(g,o,['1',0],start=1000)
