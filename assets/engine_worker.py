"""Run a separately installed engine with its own dependency path."""
import asyncio
import json
import os
from pathlib import Path
import runpy
import sys

# The portable Python ._pth configuration omits the script directory.
sys.path.insert(0, str(Path(__file__).resolve().parent))


def main():
    folder=Path(sys.argv[1]).resolve();code=folder/'code'
    sys.path[:0]=[str(folder/'dependencies'),str(code)]
    arguments=sys.argv[2:];os.chdir(code)
    if arguments and arguments[0]=='--studio-probe':
        ref2va=arguments[1:]==['ref2va']
        turbo=arguments[1:]==['minimax_h3']
        qwen=arguments[1:]==['qwen_turbo']
        moss=arguments[1:]==['moss']
        wamu=arguments[1:]==['wamu']
        os.environ['CUDA_VISIBLE_DEVICES']=''
        sys.argv=['flux3-engine-probe','--cpu','--disable-all-custom-nodes','--offline']
        import comfy.options
        comfy.options.enable_args_parsing()
        # Kitchen's capability probe initializes CUDA even with ComfyUI --cpu.
        # This installation check needs node schemas only; force the CPU backend.
        import comfy_kitchen
        comfy_kitchen.int8_attention_is_available=lambda *args,**kwargs:False
        import nodes
        import comfy.supported_models
        import torch
        async def relevant_nodes():
            for filename in (('nodes_wan.py','nodes_video.py','nodes_custom_sampler.py') if wamu else ('nodes_moss_image.py','nodes_slg.py','nodes_flux.py') if moss else ('nodes_qwen.py','nodes_custom_sampler.py') if qwen else ('nodes_minimax_h3.py','nodes_video.py','nodes_audio.py','nodes_custom_sampler.py') if ref2va or turbo else ('nodes_flux.py','nodes_edit_model.py')):
                assert await nodes.load_custom_node(str(code/'comfy_extras'/filename),module_parent='comfy_extras')
            if wamu:
                assert await nodes.load_custom_node(str(code/'custom_nodes/studio_wamu'),module_parent='custom_nodes')
            if ref2va:
                assert await nodes.load_custom_node(str(code/'custom_nodes/studio_ref2va_vsa'),module_parent='custom_nodes')
            if turbo:
                assert await nodes.load_custom_node(str(code/'custom_nodes/studio_minimax_h3_turbo'),module_parent='custom_nodes')
            if qwen:
                assert await nodes.load_custom_node(str(code/'custom_nodes/studio_viggle_turbo'),module_parent='custom_nodes')
        asyncio.run(relevant_nodes())
        if wamu:
            assert {'WAMUShardedLoader','WAMUSplitSigmas','WanImageToVideo','SamplerCustomAdvanced','DisableNoise','CreateVideo','SaveVideo'} <= nodes.NODE_CLASS_MAPPINGS.keys()
        elif moss:
            assert hasattr(comfy.supported_models,'MOSSImage'), 'MOSS model support is missing'
            assert 'moss_image' in nodes.CLIPLoader.INPUT_TYPES()['required']['type'][0]
            assert {'MOSSImageControl','MOSSImageLayoutPrompt','SkipLayerGuidanceDiTSimple','EmptyFlux2LatentImage'} <= nodes.NODE_CLASS_MAPPINGS.keys()
        elif qwen:
            assert {'TextEncodeQwenImage21','ViggleTurboSigmas','ViggleTurboLora','SamplerCustomAdvanced'} <= nodes.NODE_CLASS_MAPPINGS.keys()
            assert hasattr(comfy.supported_models,'Krea2'), 'Krea 2 model support is missing'
            assert 'krea2' in nodes.CLIPLoader.INPUT_TYPES()['required']['type'][0]
        elif turbo:
            assert 'minimax' in nodes.CLIPLoader.INPUT_TYPES()['required']['type'][0]
            assert {'MiniMaxH3ImageToVideo','MiniMaxH3SigmaShift','MiniMaxH3TurboLoRA','MiniMaxH3TurboSampler','SaveVideo','VAEDecodeAudio'} <= nodes.NODE_CLASS_MAPPINGS.keys()
            table=code/'custom_nodes/studio_minimax_h3_turbo/h3_silu_temb_grid.safetensors'
            assert table.is_file() and table.stat().st_size==5510600,'Turbo timing table missing'
        elif ref2va:
            assert 'minimax' in nodes.CLIPLoader.INPUT_TYPES()['required']['type'][0]
            assert {'MiniMaxH3ReferenceToVideo','MiniMaxH3SigmaShift','Ref2VAVSAGatePatch','CreateVideo','SaveVideo','VAEDecodeAudio','SamplerCustomAdvanced'} <= nodes.NODE_CLASS_MAPPINGS.keys()
            assert callable(comfy_kitchen.sol_attn),'The isolated kernel build is missing Sol-Attention'
        else:
            assert hasattr(comfy.supported_models,'Flux3'), 'FLUX 3 model support is missing'
            assert 'flux3' in nodes.CLIPLoader.INPUT_TYPES()['required']['type'][0]
            assert 'ReferenceMultiLatent' in nodes.NODE_CLASS_MAPPINGS
        assert not torch.cuda.is_initialized(), 'The CPU probe unexpectedly initialized CUDA'
        print(json.dumps(dict(model='wamu' if wamu else 'moss' if moss else 'qwen_turbo' if qwen else 'minimax_h3' if turbo else 'ref2va' if ref2va else 'flux3',references=True,cpu_only=True,generation_started=False)))
    else:
        sys.argv=[str(code/'main.py'),*arguments]
        from model_reader import install
        install(folder.name)
        runpy.run_path(str(code/'main.py'),run_name='__main__')


if __name__=='__main__':main()
