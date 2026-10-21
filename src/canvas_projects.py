"""Validated editable canvas documents; all image references stay in the Library."""
import math
from pathlib import Path
import re
import secrets
import time
from common import atomic_json, load_json

MAX_PIXELS=16777216
MAX_LAYERS=64


def numeric(value, low, high, label):
    if isinstance(value,bool):raise ValueError('Invalid '+label+'.')
    try:
        number=float(value)
        if not math.isfinite(number) or not low<=number<=high:raise ValueError()
        return number
    except (ValueError,TypeError,OverflowError):raise ValueError(f'{label} must be between {low} and {high}.') from None


def identifier(value):
    if not isinstance(value,str) or not re.fullmatch('[0-9a-f]{24}',value):raise ValueError('Choose a valid canvas project or Library image.')
    return value


def validate(raw):
    if not isinstance(raw,dict):raise ValueError('Choose a valid canvas document.')
    width=numeric(raw.get('width'),64,8192,'Canvas width');height=numeric(raw.get('height'),64,8192,'Canvas height')
    if not width.is_integer() or not height.is_integer() or width*height>MAX_PIXELS:raise ValueError('Use whole canvas dimensions with up to 16,777,216 pixels.')
    name=raw.get('name','Untitled canvas')
    if not isinstance(name,str) or not 0<len(name.strip())<=100:raise ValueError('Give the canvas a name of up to 100 characters.')
    background=raw.get('background','#ffffff')
    if not isinstance(background,str) or not re.fullmatch('#[0-9a-fA-F]{6}',background):raise ValueError('Choose a canvas background color.')
    layers=raw.get('layers',[])
    if not isinstance(layers,list) or len(layers)>MAX_LAYERS:raise ValueError('Use up to 64 canvas layers.')
    cleaned=[];seen=set()
    for item in layers:
        if not isinstance(item,dict) or item.get('kind') not in ('image','text'):raise ValueError('Canvas layers must be images or text.')
        key=item.get('id')
        if not isinstance(key,str) or not re.fullmatch('[A-Za-z0-9_-]{1,64}',key) or key in seen:raise ValueError('Canvas layers need different valid IDs.')
        seen.add(key);layer=dict(id=key,kind=item['kind'])
        for field,default,limit in [('name','Layer',200),('caption','',1000),('text','',2000)]:
            value=item.get(field,default)
            if not isinstance(value,str) or len(value)>limit:raise ValueError('Canvas '+field+' is too long.')
            layer[field]=value
        for field,default,low,high in [('x',0,-32768,32768),('y',0,-32768,32768),('w',100,1,32768),('h',100,1,32768),('rotation',0,-360,360),('opacity',1,0,1),('font_size',64,1,2048)]:
            layer[field]=numeric(item.get(field,default),low,high,'Layer '+field)
        for field in ('visible','locked'):
            value=item.get(field,field=='visible')
            if not isinstance(value,bool):raise ValueError('Choose layer visibility and locking.')
            layer[field]=value
        color=item.get('color','#101820')
        if not isinstance(color,str) or not re.fullmatch('#[0-9a-fA-F]{6}',color):raise ValueError('Choose a text color.')
        layer['color']=color
        font=item.get('font','sans-serif')
        if font not in ('sans-serif','serif','monospace'):raise ValueError('Choose a supported text font.')
        layer['font']=font
        if item['kind']=='image':layer['source_id']=identifier(item.get('source_id'))
        cleaned.append(layer)
    result=dict(schema=1,name=name.strip(),width=int(width),height=int(height),background=background,layers=cleaned)
    if raw.get('id'):result['id']=identifier(raw['id'])
    return result


def folder(root):
    path=Path(root)/'canvas-projects';path.mkdir(parents=True,exist_ok=True);return path


def save(root, raw, draft=False):
    project=validate(raw);base=folder(root)
    if not draft:
        key=project.get('id') or secrets.token_hex(12)
        if project.get('id') and not (base/(key+'.json')).is_file():raise ValueError('That canvas project no longer exists. Save it as a new project.')
        project['id']=key
    project['updated']=time.strftime('%Y-%m-%d %H:%M:%S')
    atomic_json(base/('draft.json' if draft else project['id']+'.json'),project)
    return project


def load(root, key=None):
    path=folder(root)/('draft.json' if key is None else identifier(key)+'.json')
    data=load_json(path,None)
    if data is None:
        if key is None:return None
        raise ValueError('This canvas project could not be opened.')
    return validate(data)


def catalog(root):
    result=[]
    for path in folder(root).glob('*.json'):
        if path.name=='draft.json':continue
        data=load_json(path,{})
        try:
            project=validate(data)
            if project.get('id')!=path.stem:continue
            result.append({k:project[k] for k in ('id','name','width','height')}|dict(updated=data.get('updated',''),layers=len(project['layers'])))
        except ValueError:continue
    return sorted(result,key=lambda x:(x['updated'],x['id']),reverse=True)
