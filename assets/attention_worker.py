"""Launch ComfyUI with optional Comfy Kitchen SageAttention and local fallback."""
import argparse
import functools
import json
import math
import os
from pathlib import Path
import runpy
import sys
import tempfile
import time

# The portable Python ._pth configuration omits the script directory.
sys.path.insert(0, str(Path(__file__).resolve().parent))


def write_status(path, value):
    if not path:
        return
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix='.attention-',dir=path.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as output:json.dump(value,output)
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)


def safe_attention(original, pytorch, finite, update, wrap=None):
    """Fallback inside the same attention call; never resubmit a generation job."""
    disabled=False
    reported=False
    @functools.wraps(original,updated=())
    def call(*args,**kwargs):
        nonlocal disabled,reported
        if not disabled:
            try:
                result=original(*args,**kwargs)
                if not finite(result):raise ValueError('SageAttention returned non-finite values')
                if not reported:
                    update('sage','SageAttention is processing this generation.')
                    reported=True
                return result
            except (RuntimeError,ValueError,NotImplementedError,TypeError) as error:
                message=str(error)
                # A damaged CUDA context or exhausted VRAM cannot be safely retried in-place.
                if any(x in message.lower() for x in ('out of memory','device-side assert','illegal memory access','misaligned address')):
                    raise
                disabled=True
                update('pytorch_fallback','SageAttention could not process this input; using PyTorch. '+message[:240])
        return pytorch(*args,**kwargs)
    # Unpack single-owner containers outside the guarded call so both backends
    # receive reusable tensors, including when the first backend raises.
    return wrap(call) if wrap is not None else call


def probe(kitchen,torch,test_kernel=False,report=None):
    report=report or (lambda message:None)
    report('Checking CUDA device support')
    available=bool(kitchen.int8_attention_is_available())
    result=dict(available=available,kitchen=getattr(kitchen,'__version__','installed'),
                torch=torch.__version__,kernel_tested=False,generation_started=False)
    if not available:
        return result|dict(reason='The installed Comfy Kitchen CUDA kernel does not support this device/runtime.')
    result['gpu']=torch.cuda.get_device_name()
    if test_kernel:
        report('Running the small SageAttention math test; the first kernel load can take longer')
        # Small numerical compatibility test only; no model or media files are loaded.
        q=torch.randn(1,2,64,64,device='cuda',dtype=torch.float16)
        k=torch.randn_like(q);v=torch.randn_like(q)
        actual=kitchen.int8_attention(q,k,v)
        report('Comparing SageAttention with PyTorch')
        expected=torch.nn.functional.scaled_dot_product_attention(q,k,v)
        error=float((actual-expected).abs().max().item())
        if not math.isfinite(error) or not bool(torch.isfinite(actual).all().item()) or error>.12:
            return result|dict(available=False,kernel_tested=True,max_error=error if math.isfinite(error) else None,
                               reason='The small attention accuracy check failed. PyTorch remains available.')
        result.update(kernel_tested=True,max_error=error)
    return result|dict(reason='Compatible SageAttention kernel found.')


def initialize_native_memory(cli,control):
    """Match main.py's native-library setup before attention imports cache its DLL."""
    if getattr(cli,'enables_dynamic_vram',lambda:False)() and not control.init():
        raise RuntimeError('Native memory initialization failed; deferring startup to the standard engine.')


def configure(entry,arguments,update,kitchen,torch):
    try:
        info=probe(kitchen,torch)
    except Exception as error:
        info=dict(available=False,reason='SageAttention availability check failed: '+str(error)[:240])
    flag='--use-ck-attention' if info['available'] else '--use-pytorch-cross-attention'
    cli=Path('comfy/cli_args.py')
    if not cli.is_file() or '--use-ck-attention' not in cli.read_text(encoding='utf-8'):
        info=dict(available=False,reason='This engine does not support Comfy Kitchen attention.')
        flag='--use-pytorch-cross-attention'
    sys.argv=[str(entry),*arguments,flag]
    if not info['available']:
        update('pytorch_fallback',info['reason'])
        return
    import comfy.options
    comfy.options.enable_args_parsing()
    import comfy.cli_args
    if getattr(comfy.cli_args,'enables_dynamic_vram',lambda:False)():
        import comfy_aimdo.control
        initialize_native_memory(comfy.cli_args,comfy_aimdo.control)
    import comfy.ldm.modules.attention as attention
    original=getattr(attention,'attention_comfy_kitchen_int8',None)
    if original is None:
        # Older engines cannot use this integration. Parse the standard backend instead.
        raise RuntimeError('This engine does not provide Comfy Kitchen attention support.')
    guarded=safe_attention(original,attention.attention_pytorch,
                           lambda value:bool(torch.isfinite(value).all().item()),update,
                           wrap=attention.wrap_attn)
    attention.attention_comfy_kitchen_int8=guarded
    attention.optimized_attention=guarded
    attention.optimized_attention_masked=guarded
    attention.REGISTERED_ATTENTION_FUNCTIONS['comfy_kitchen_int8']=guarded
    update('sage_ready','SageAttention selected; waiting for generation. Performance has not been benchmarked.')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--entry');parser.add_argument('--engine-dir')
    parser.add_argument('--status-file');parser.add_argument('--session',default='')
    parser.add_argument('--probe',action='store_true')
    parser.add_argument('--kernel-test',action='store_true')
    parser.add_argument('arguments',nargs=argparse.REMAINDER)
    options=parser.parse_args()
    arguments=options.arguments[1:] if options.arguments[:1]==['--'] else options.arguments
    if options.engine_dir:
        folder=Path(options.engine_dir).resolve()
        sys.path[:0]=[str(folder/'dependencies'),str(folder/'code')]
        os.chdir(folder/'code')
    elif options.entry:
        sys.path.insert(0,str(Path(options.entry).resolve().parent))
    if options.engine_dir and not options.probe:
        from model_reader import install
        install(Path(options.engine_dir).name)
    def update(active,reason):
        value=dict(session=options.session,pid=os.getpid(),requested='sage',active=active,
                   reason=reason,updated=time.time())
        try:write_status(options.status_file,value)
        except OSError as error:print('[Studio attention] Could not save status: '+str(error),flush=True)
        print('[Studio attention] '+reason,flush=True)
    try:
        def progress(message):
            print('STUDIO_ATTENTION_STAGE '+message,flush=True)
        if options.probe:progress('Loading PyTorch')
        import torch
        if options.probe:progress('Loading Comfy Kitchen')
        import comfy_kitchen as kitchen
        if options.probe:
            try:result=probe(kitchen,torch,options.kernel_test,progress)
            except Exception as error:result=dict(available=False,reason=str(error)[:500],generation_started=False)
            print('STUDIO_ATTENTION_PROBE '+json.dumps(result),flush=True)
            return
        if not options.entry:raise ValueError('The engine entry point is missing.')
        configure(options.entry,arguments,update,kitchen,torch)
    except (ImportError,OSError,RuntimeError,AttributeError) as error:
        if options.probe:
            print('STUDIO_ATTENTION_PROBE '+json.dumps(dict(available=False,reason=str(error)[:500],generation_started=False)),flush=True)
            return
        update('pytorch_fallback','SageAttention unavailable; using PyTorch. '+str(error)[:240])
        sys.argv=[options.entry,*arguments,'--use-pytorch-cross-attention']
        # If Comfy argument parsing already ran, update its shared configuration as well.
        if 'comfy.cli_args' in sys.modules:
            args=sys.modules['comfy.cli_args'].args
            args.use_ck_attention=False;args.use_pytorch_cross_attention=True
        attention=sys.modules.get('comfy.ldm.modules.attention')
        if attention and hasattr(attention,'attention_pytorch'):
            attention.optimized_attention=attention.attention_pytorch
            attention.optimized_attention_masked=attention.attention_pytorch
    runpy.run_path(options.entry,run_name='__main__')


if __name__=='__main__':main()
