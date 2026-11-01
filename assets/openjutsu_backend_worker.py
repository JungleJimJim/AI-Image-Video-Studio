"""Owned OpenJutsu ComfyUI process and weight-free installation probe."""
import asyncio
import importlib.abc
import importlib.machinery
import json
import os
from pathlib import Path
import runpy
import sys

base = Path(sys.argv[1]).resolve()
models = Path(sys.argv[2]).resolve()
operation = sys.argv[3]
code = base / 'code'
data = base.parent.parent / 'openjutsu-data'
models.mkdir(parents=True, exist_ok=True)
for name in ('profile', 'temp', 'yolo', 'matplotlib', 'hf-cache', 'frontend'):(data / name).mkdir(parents=True, exist_ok=True)
sys.path[:0] = [str(base / 'dependencies'), str(code), str(Path(__file__).resolve().parent)]
os.environ.update(SSLKEYLOGFILE='', PYTHONDONTWRITEBYTECODE='1', HF_HUB_OFFLINE='1',
    TRANSFORMERS_OFFLINE='1', NO_ALBUMENTATIONS_UPDATE='1', YOLO_AUTOINSTALL='false', YOLO_CONFIG_DIR=str(data / 'yolo'),
    AUX_ANNOTATOR_CKPTS_PATH=str(models / 'controlnet_aux'), AUX_USE_SYMLINKS='False',
    AUX_TEMP_DIR=str(data / 'temp'), AIOHTTP_NOSENDFILE='1')
os.environ.update(MPLCONFIGDIR=str(data / 'matplotlib'), HF_HOME=str(data / 'hf-cache'))
os.environ['PATH'] = str(base / 'tools') + os.pathsep + os.environ.get('PATH', '')
os.chdir(code)


def configure_paths():
    import folder_paths
    for name, directory, extensions in [('sams', 'sams', {'.pth', '.safetensors'}),
                                        ('ultralytics', 'ultralytics', {'.pt', '.pth', '.onnx'})]:
        paths, supported = folder_paths.folder_names_and_paths.get(name, ([], set()))
        folder_paths.folder_names_and_paths[name] = (paths, supported | extensions)
        folder_paths.add_model_folder_path(name, str(models / directory))


def after_import(name, patch):
    """Preserve Comfy's DLL/allocator setup before importing Torch dependencies."""
    if name in sys.modules:
        patch(sys.modules[name])
        return
    class Finder(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path=None, target=None):
            if fullname != name:return None
            spec = importlib.machinery.PathFinder.find_spec(fullname, path)
            if spec is None or spec.loader is None:raise ImportError('Missing backend module: ' + name)
            original = spec.loader
            class Loader(importlib.abc.Loader):
                def create_module(self, spec):return original.create_module(spec)
                def exec_module(self, module):
                    original.exec_module(module)
                    patch(module)
                    sys.meta_path.remove(finder)
            spec.loader = Loader()
            return spec
    finder = Finder()
    sys.meta_path.insert(0, finder)


def offline_identity_models():
    def installed_only(sub_dir, name, force=False, root='~/.insightface'):
        target = Path(root).expanduser() / sub_dir / name
        if force or not target.is_dir() or not any(target.glob('*.onnx')):
            raise RuntimeError('Install the OpenJutsu Face refinement model pack in Studio before using face identity matching.')
        return str(target)
    after_import('insightface.utils.storage', lambda storage: setattr(storage, 'download', installed_only))


if operation == 'probe':
    print('OpenJutsu CPU probe: checking runtime imports.', flush=True)
    os.environ['CUDA_VISIBLE_DEVICES'] = ''
    os.environ['MPLBACKEND'] = 'Agg'
    sys.argv = [str(code / 'main.py'), '--cpu', '--disable-all-custom-nodes', '--offline',
                '--disable-assets', '--disable-api-nodes', '--front-end-root', str(data / 'frontend'),
                '--models-directory', str(models), '--user-directory', str(data / 'profile')]
    import comfy.options
    comfy.options.enable_args_parsing()
    import comfy_kitchen
    comfy_kitchen.int8_attention_is_available = lambda *args, **kwargs: False
    import nodes
    import server
    import torch
    import cv2
    import scipy
    import insightface
    import ultralytics
    configure_paths()
    offline_identity_models()
    ultralytics.settings.update({'sync': False})
    print('OpenJutsu CPU probe: loading node schemas.', flush=True)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    from app.assets.manager import default_asset_manager
    server.PromptServer(loop, default_asset_manager())
    config = json.loads((base / 'backend-spec.json').read_text(encoding='utf-8'))
    async def check():
        await nodes.init_extra_nodes(init_custom_nodes=False, init_api_nodes=False)
        for plugin in config['nodes']:
            if not await nodes.load_custom_node(str(code / 'custom_nodes' / plugin['name']), module_parent='custom_nodes'):
                raise RuntimeError('Could not load ' + plugin['name'])
        missing = sorted(set(config['required_nodes']) - nodes.NODE_CLASS_MAPPINGS.keys())
        if missing:
            raise RuntimeError('Missing OpenJutsu nodes: ' + ', '.join(missing))
        # Metric3D imports these only when rendering; check them without loading weights.
        from custom_controlnet_aux.metric3d import Metric3DDetector
        from insightface.app import FaceAnalysis
        assert callable(Metric3DDetector.from_pretrained) and callable(FaceAnalysis)
    loop.run_until_complete(check())
    assert not torch.cuda.is_initialized(), 'The CPU probe initialized CUDA'
    print(json.dumps(dict(nodes=len(config['required_nodes']), cpu_only=True, generation_started=False)))
elif operation == 'run':
    sys.argv = [str(code / 'main.py'), *sys.argv[4:]]
    import comfy.options
    comfy.options.enable_args_parsing()
    configure_paths()
    offline_identity_models()
    if '--cpu' in sys.argv:
        after_import('comfy_kitchen', lambda kitchen: setattr(kitchen, 'int8_attention_is_available', lambda *a, **kw: False))
    from model_reader import install
    install('openjutsu')
    runpy.run_path(str(code / 'main.py'), run_name='__main__')
else:
    raise SystemExit('Unknown backend operation.')
