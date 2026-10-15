"""Run a separately installed engine with its own dependency path."""
import asyncio
import json
import os
from pathlib import Path
import runpy
import sys


def main():
    folder=Path(sys.argv[1]).resolve();code=folder/'code'
    sys.path[:0]=[str(folder/'dependencies'),str(code)]
    arguments=sys.argv[2:];os.chdir(code)
    if arguments==['--studio-probe']:
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
            for filename in ('nodes_flux.py','nodes_edit_model.py'):
                assert await nodes.load_custom_node(str(code/'comfy_extras'/filename),module_parent='comfy_extras')
        asyncio.run(relevant_nodes())
        assert hasattr(comfy.supported_models,'Flux3'), 'FLUX 3 model support is missing'
        assert 'flux3' in nodes.CLIPLoader.INPUT_TYPES()['required']['type'][0]
        assert 'ReferenceMultiLatent' in nodes.NODE_CLASS_MAPPINGS
        assert not torch.cuda.is_initialized(), 'The CPU probe unexpectedly initialized CUDA'
        print(json.dumps(dict(flux3=True,references=True,cpu_only=True)))
    else:
        sys.argv=[str(code/'main.py'),*arguments]
        runpy.run_path(str(code/'main.py'),run_name='__main__')


if __name__=='__main__':main()
