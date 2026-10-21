"""Headless FaceFusion bridge. Original upstream processors and safeguards are retained."""
import argparse
import importlib
import json
import os
from pathlib import Path
import runpy
import sys


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--folder',required=True)
    parser.add_argument('--probe',action='store_true')
    parser.add_argument('arguments',nargs=argparse.REMAINDER)
    options=parser.parse_args()
    folder=Path(options.folder).resolve()
    sys.path[:0]=[str(folder/'dependencies'),str(folder/'code')]
    os.chdir(folder/'code')
    import onnxruntime
    # Reuse the already-installed CUDA/cuDNN libraries; never replace PyTorch.
    torch_lib=Path(sys.executable).parent/'Lib/site-packages/torch/lib'
    if hasattr(onnxruntime,'preload_dlls') and torch_lib.is_dir():
        onnxruntime.preload_dlls(directory=str(torch_lib))
    arguments=options.arguments[1:] if options.arguments[:1]==['--'] else options.arguments
    sys.argv=[str(folder/'code/facefusion.py'),*arguments]
    if options.probe:
        from facefusion.program import create_program
        from facefusion.args import apply_args
        from facefusion import state_manager
        from facefusion.processors.modules.face_swapper import core as swapper
        args=vars(create_program().parse_args())
        apply_args(args,state_manager.init_item)
        downloads={}
        for module in [*swapper.get_common_modules(),swapper]:
            if hasattr(module,'collect_model_downloads'):
                hashes,sources=module.collect_model_downloads()
                groups=[hashes,sources]
            elif hasattr(module,'get_model_options'):
                model=module.get_model_options();groups=[model['hashes'],model['sources']]
            else:
                groups=[group for model in module.create_static_model_set('full').values() for group in (model['hashes'],model['sources'])]
            for group in groups:
                for item in group.values():downloads[Path(item['path']).name]=item
        print('STUDIO_FACEFUSION_PROBE '+json.dumps(dict(arguments_accepted=True,
            providers=onnxruntime.get_available_providers(),downloads=list(downloads.values()),
            generation_started=False)),flush=True)
        return
    runpy.run_path(str(folder/'code/facefusion.py'),run_name='__main__')


if __name__=='__main__':main()
