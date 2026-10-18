"""Local imports and verified Hugging Face downloads for safetensors adapters."""
import json
import os
from pathlib import Path
import re
import shutil
import struct
import urllib.parse
import urllib.request

from common import atomic_json, comfy_root, existing_parent, load_json
from downloads import Cancelled, SafeRedirect, checksum, download


def model_catalog():
    from packs import catalog
    models = {'wan13': {'name': 'NSFW Wan 1.3B · E14'}} | catalog()
    guidance = {
        'wan13': 'Use Wan 2.1 T2V 1.3B adapters compatible with E14. Wan 14B adapters do not fit.',
        'wan22': 'Use Wan 2.2 TI2V 5B adapters. The 14B high/low-noise adapters do not fit this 5B model.',
        'ltx2': 'Use standard LTX-2 19B LoRAs compatible with the distilled checkpoint. IC-LoRAs and adapters for other LTX versions need different workflows.',
        'sdxl': 'Use SDXL adapters. This library is shared by Juggernaut, DreamShaper and Illustrious; each model remembers its own enabled selection. SD 1.5 and FLUX adapters do not fit.',
        'zimage': 'Use Z-Image / Z-Image-Turbo adapters. Follow the author’s Turbo compatibility and step recommendations.',
        'fluxklein': 'Use FLUX.2 Klein 4B adapters compatible with the distilled model. FLUX.1, FLUX.2 Dev and Klein 9B adapters do not fit.',
        'flux3': 'Use FLUX 3 Image Klein 5.6B adapters explicitly compatible with the distilled checkpoint. FLUX.1 and FLUX.2 adapters do not fit. Base-model training adapters need the author’s distilled-compatibility guidance.',
        'qwenimage': 'Use Qwen-Image adapters compatible with the 2512 image generator. Check the author’s base model and sampling recommendations.',
        'qwenedit': 'Use Qwen Image Edit adapters compatible with 2511. Control and acceleration adapters may require additional workflow changes.',
        'qwen21': 'Use Qwen-Image 2.1 adapters. The detail-enhancement pass includes Elusarca’s LoRA; extra selected adapters must also match Qwen 2.1. Qwen-Image-2512 and Edit-2511 adapters do not fit.',
        'ref2va': 'Use MiniMax H3 Ref2VA-compatible adapters. The four-step Turbo LoRA and VSA gates install automatically. They are not interchangeable with Wan or FL2VA adapters.',
        'minimax_h3': 'Use MiniMax H3 FL2VA / T2VA-compatible adapters. Larry Turbo v1 and v4 install with the model and are selected in Video. Ref2VA and Wan adapters do not fit. Extra adapters apply after Turbo.',
        'viggle': 'Use Qwen Image 2.1 adapters compatible with Viggle six-step sampling. The built-in Turbo adapter stays at strength 1. Extra adapters may need different sampling recipes.',
        'bfs': 'Use Qwen Image 2.1 adapters compatible with BFS v1.1. The required BFS adapter is included automatically; adding more identity adapters can conflict.',
        'avatar_echo': 'Adapters can be stored here. The EchoMimicV3-Flash talking-avatar workflow currently uses its included weights and does not apply extra LoRAs.',
        'avatar_soulx': 'Adapters can be stored here. The SoulX-FlashHead talking-avatar workflow currently uses its included weights and does not apply extra LoRAs.',
        'avatar_longcat': 'Use LongCat-Video-Avatar 1.5 adapters. The required distillation LoRA is included automatically; extra compatible adapters apply in the talking-avatar workflow.',
        'avatar_infinite': 'Use adapters explicitly compatible with InfiniteTalk and its Wan 2.1 14B base. Wan 1.3B and Wan 2.2 5B adapters do not fit.',
        'avatar_musetalk': 'Adapters can be stored here. MuseTalk 1.5 uses its dedicated lip-sync network and does not apply extra LoRAs in this workflow.',
    }
    search = {'wan13':'Wan 1.3B', 'wan22':'Wan 2.2 5B', 'ltx2':'LTX-2', 'sdxl':'SDXL',
              'zimage':'Z-Image', 'fluxklein':'FLUX.2 Klein 4B', 'flux3':'FLUX 3 Image Klein', 'qwenimage':'Qwen-Image', 'qwenedit':'Qwen-Image-Edit-2511', 'qwen21':'Qwen-Image-2.1'}
    result = {}
    for key, pack in models.items():
        scope = 'sdxl' if pack.get('family') == 'sdxl' else key
        result[key] = dict(id=key, name=pack['name'], scope=scope, guidance=guidance.get(scope, 'Check the adapter’s exact base model.'),
            text_encoder=scope in ('sdxl','wan13'),
            civitai_url='https://civitai.com/models?types=LORA',
            hf_url='https://huggingface.co/models?other=lora&search='+urllib.parse.quote(search.get(scope,pack['name'])))
    return result


def validate_model(model):
    if not isinstance(model,str) or model not in model_catalog():
        raise ValueError('Choose a supported target model for the LoRA.')
    return model


def lora_folder(root, model=None):
    base = comfy_root(root) / 'models' / 'loras'
    if model is None or validate_model(model) == 'wan13':
        return base  # Existing Wan adapters retain their paths and filenames.
    return base / 'studio' / model_catalog()[model]['scope']


def read_adapter(path):
    path = Path(path)
    if path.suffix.lower() != ".safetensors":
        raise ValueError("Choose a .safetensors LoRA file.")
    with path.open("rb") as file:
        size_bytes = file.read(8)
        if len(size_bytes) != 8:
            raise ValueError("This is not a valid safetensors file.")
        length = struct.unpack("<Q", size_bytes)[0]
        if not 2 <= length <= 16 * 1024**2:
            raise ValueError("Invalid safetensors header.")
        try:
            header = json.loads(file.read(length))
        except (ValueError, UnicodeError):
            raise ValueError("Invalid safetensors metadata.") from None
    if not isinstance(header, dict):
        raise ValueError("Invalid safetensors metadata.")
    keys = [key for key in header if key != "__metadata__"]
    if not keys or not any(any(part in key.lower() for part in ("lora", "lokr", "hada")) for key in keys):
        raise ValueError("This file does not look like a LoRA adapter. Full model checkpoints belong in model setup.")
    payload = path.stat().st_size - 8 - length
    for key in keys:
        item = header[key]
        offsets = item.get("data_offsets", []) if isinstance(item, dict) else []
        if len(offsets) != 2 or not all(isinstance(x, int) for x in offsets) or not 0 <= offsets[0] <= offsets[1] <= payload:
            raise ValueError("The LoRA file is incomplete or has invalid tensor offsets.")
    metadata = header.get("__metadata__", {})
    return metadata if isinstance(metadata, dict) else {}


def installed_loras(root, model=None):
    folder = lora_folder(root)
    notes = load_json(Path(root) / "loras.json", {})
    if not folder.exists():
        return []
    models = model_catalog()
    if model is not None:
        validate_model(model)
    result = []
    for path in sorted(folder.rglob('*.safetensors')):
        if not path.resolve().is_relative_to(folder.resolve()):
            continue
        relative = path.relative_to(folder)
        scope = relative.parts[1] if len(relative.parts)>2 and relative.parts[0]=='studio' else 'wan13'
        if scope.startswith('_'):continue  # Required runtime gates/adapters are managed by their model pack.
        if model is not None and models[model]['scope'] != scope:
            continue
        note = notes.get(relative.as_posix(), {})
        result.append(dict(name=relative.as_posix(), display_name=path.name, size=path.stat().st_size, scope=scope,
            models=[key for key, info in models.items() if info['scope']==scope],
            sha256=note.get('sha256',''), source=note.get('source','Local file'), declared_base=note.get('declared_base','')))
    return result


def save_record(root, path, digest, source, model='wan13', metadata=None):
    records = load_json(Path(root) / "loras.json", {})
    metadata = metadata or {}
    declared = ' · '.join(str(metadata[k])[:150] for k in ('ss_base_model_version','modelspec.architecture','base_model','ss_sd_model_name') if metadata.get(k))[:400]
    records[path.relative_to(lora_folder(root)).as_posix()] = {'sha256':digest, 'source':source,
        'scope':model_catalog()[validate_model(model)]['scope'], 'declared_base':declared}
    atomic_json(Path(root) / "loras.json", records)


def choose_destination(root, name, digest, model='wan13'):
    name = re.sub(r'[<>:"/\\|?*]', "_", name).rstrip(" .")
    if not name.lower().endswith(".safetensors") or len(name) > 180 or Path(name).stem.upper() in ("CON", "PRN", "AUX", "NUL"):
        raise ValueError("Choose a valid .safetensors filename.")
    folder = lora_folder(root, model)
    folder.mkdir(parents=True, exist_ok=True)
    destination = folder / name
    number = 2
    while destination.exists():
        if checksum(destination) == digest:
            return destination
        destination = folder / f"{Path(name).stem} ({number}).safetensors"
        number += 1
    return destination


def import_loras(root, paths, report, cancel, model='wan13'):
    validate_model(model)
    if not isinstance(paths, list) or not 1 <= len(paths) <= 20:
        raise ValueError("Choose between 1 and 20 LoRA files.")
    for text in paths:
        source = Path(str(text)).expanduser().resolve()
        metadata = read_adapter(source)
        digest = checksum(source, cancel)
        destination = choose_destination(root, source.name, digest, model)
        if destination.exists():
            report("Already installed: " + destination.name, 1)
            continue
        if shutil.disk_usage(existing_parent(destination)).free < source.stat().st_size + 100 * 1024**2:
            raise ValueError("There is not enough space on the model drive for this LoRA.")
        partial = destination.with_suffix(".safetensors.importing")
        try:
            total = source.stat().st_size
            done = 0
            with source.open("rb") as src, partial.open("wb") as output:
                while chunk := src.read(8 * 1024**2):
                    if cancel.is_set():
                        raise Cancelled("LoRA import cancelled. Your original file is preserved.")
                    output.write(chunk)
                    done += len(chunk)
                    report("Importing " + source.name, done / max(total, 1))
            if checksum(partial, cancel) != digest:
                raise ValueError("The LoRA copy did not pass its checksum check. Retry the import.")
            os.replace(partial, destination)
            save_record(root, destination, digest, 'Local file', model, metadata)
        finally:
            partial.unlink(missing_ok=True)
    report("LoRA files installed. Enable the ones you want to use below.", 1)


def hf_spec(url, token=""):
    parsed = urllib.parse.urlsplit(url.strip())
    if parsed.scheme != "https" or parsed.hostname != "huggingface.co" or parsed.username or parsed.password:
        raise ValueError("Paste a Hugging Face .safetensors file link, starting with https://huggingface.co/.")
    parts = [urllib.parse.unquote(x) for x in parsed.path.strip("/").split("/")]
    if len(parts) < 5 or parts[2] not in ("blob", "resolve"):
        raise ValueError("Open the LoRA's Files tab on Hugging Face and paste the link to a specific .safetensors file.")
    repo = "/".join(parts[:2])
    revision = parts[3]
    filename = "/".join(parts[4:])
    if not filename.lower().endswith(".safetensors") or any(x in ("..", ".", "") for x in parts):
        raise ValueError("The link must point to a .safetensors file.")
    headers = {"User-Agent": "WanVideoStudio/1.1"}
    if token:
        headers["Authorization"] = "Bearer " + token
    request = urllib.request.Request("https://huggingface.co/api/models/" + urllib.parse.quote(repo, safe="/") +
                                     "/revision/" + urllib.parse.quote(revision, safe="") + "?blobs=true", headers=headers)
    opener = urllib.request.build_opener(SafeRedirect())
    with opener.open(request, timeout=30) as response:
        info = json.load(response)
    record = next((x for x in info.get("siblings", []) if x["rfilename"] == filename), None)
    lfs = record.get("lfs", {}) if record else {}
    digest = lfs.get("sha256", "")
    size = lfs.get("size", record.get("size", 0) if record else 0)
    if not re.fullmatch(r"[a-fA-F0-9]{64}", digest) or not 0 < size <= 8 * 1024**3:
        raise ValueError("This file has no supported SHA-256 download metadata, or exceeds 8 GB. Download it yourself and use Add local files.")
    return {"label": "LoRA " + Path(filename).name, "filename": Path(filename).name, "size": size, "sha256": digest.lower(),
            "url": "https://huggingface.co/" + urllib.parse.quote(repo, safe="/") + "/resolve/" + info["sha"] + "/" + urllib.parse.quote(filename, safe="/")}


def download_lora(root, url, token, report, cancel, model='wan13'):
    validate_model(model)
    report("Checking the Hugging Face LoRA file…", 0)
    spec = hf_spec(url, token)
    destination = choose_destination(root, spec["filename"], spec["sha256"], model)
    if shutil.disk_usage(existing_parent(destination)).free < spec["size"] + 100 * 1024**2 and not destination.exists():
        raise ValueError("There is not enough space on the model drive for this LoRA.")
    downloaded = download(spec, destination, report, cancel, token)
    try:
        metadata = read_adapter(downloaded)
    except ValueError:
        # Keep invalid downloads outside the active LoRA directory for inspection.
        quarantine = Path(root) / "downloads" / (downloaded.name + ".invalid")
        quarantine.parent.mkdir(exist_ok=True)
        os.replace(downloaded, quarantine)
        raise
    save_record(root, downloaded, spec['sha256'], spec['url'], model, metadata)
    report("Installed " + destination.name + ". Enable it below to use it.", 1)


def validate_selection(root, selection, model='wan13'):
    validate_model(model)
    if not isinstance(selection, list) or len(selection) > 8:
        raise ValueError("Choose at most eight enabled LoRAs.")
    available = {record['name'] for record in installed_loras(root, model)}
    result = []
    for item in selection:
        if not isinstance(item, dict) or item.get("name") not in available:
            raise ValueError('A selected LoRA is not installed for this model. Choose a matching adapter in LoRAs.')
        try:
            strength = float(item.get('strength', 1))
            clip = float(item.get('strength_clip', strength))
            if not -2 <= strength <= 2 or not -2 <= clip <= 2:
                raise ValueError()
        except (ValueError,TypeError,OverflowError):
            raise ValueError('LoRA strengths must be numbers between -2 and 2.') from None
        if any(x["name"] == item["name"] for x in result):
            raise ValueError("A LoRA can only be enabled once.")
        result.append({"name": item["name"], "strength": strength})
        if 'strength_clip' in item and model_catalog()[model]['text_encoder']:
            result[-1]['strength_clip'] = clip
    return result


def resolve_engine_names(graph, object_info):
    """Use the engine's exact combo values while keeping saved names portable."""
    for node in graph.values():
        kind = node['class_type']
        if kind not in ('LoraLoader', 'LoraLoaderModelOnly','Ref2VAVSAGatePatch','MiniMaxH3TurboLoRA','ViggleTurboLora'):
            continue
        field='gate_file' if kind=='Ref2VAVSAGatePatch' else 'lora_name'
        schema = object_info[kind]['input']['required'][field]
        choices = schema[1].get('options', []) if schema[0] == 'COMBO' else schema[0]
        name = node['inputs'][field]
        if name in choices:
            continue
        matches = [value for value in choices if value.replace('\\', '/') == name.replace('\\', '/')]
        if len(matches) != 1:
            raise ValueError(f'The engine cannot find the selected LoRA: {name}. Check its installation in LoRAs.')
        node['inputs'][field] = matches[0]
    return graph


def apply_to_graph(graph, options, model, clip=None, start=1000):
    """Patch the loaded model before sampling; only SDXL/Wan legacy patch text too."""
    adapters = options.get('loras', [])
    if not adapters:
        return graph
    loaded_model, loaded_clip = model, clip
    additions = {}
    for index, adapter in enumerate(adapters, start=start):
        key = str(index)
        if key in graph:
            raise ValueError('LoRA node ID conflicts with the workflow.')
        inputs = dict(model=loaded_model, lora_name=adapter['name'], strength_model=adapter['strength'])
        if clip is not None:
            inputs.update(clip=loaded_clip, strength_clip=adapter.get('strength_clip',adapter['strength']))
        additions[key] = dict(class_type='LoraLoader' if clip is not None else 'LoraLoaderModelOnly', inputs=inputs)
        loaded_model = [key,0]
        if clip is not None:
            loaded_clip = [key,1]
    for node in graph.values():
        for name, value in node['inputs'].items():
            if value == model:
                node['inputs'][name] = loaded_model
            elif clip is not None and value == clip:
                node['inputs'][name] = loaded_clip
    graph.update(additions)
    return graph
