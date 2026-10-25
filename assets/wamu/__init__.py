"""Load the publisher's original Wan 2.2 Diffusers shards without a conversion copy."""
import folder_paths
import comfy.sd
import comfy.utils

SHARD_SIZES=(9969048744,9891560008,8717306128)

class WAMUShardedLoader:
    @classmethod
    def INPUT_TYPES(cls):return {"required":{"stage":(["high","low"],)}}
    RETURN_TYPES=("MODEL",)
    FUNCTION="load"
    CATEGORY="studio/loaders"

    def load(self,stage):
        if stage not in ('high','low'):raise ValueError('Choose the high or low WAMU stage.')
        state={}
        for index,size in enumerate(SHARD_SIZES,1):
            name=f'studio/wamu/{stage}/diffusion_pytorch_model-{index:05d}-of-00003.safetensors'
            path=folder_paths.get_full_path_or_raise('diffusion_models',name)
            from pathlib import Path
            if Path(path).stat().st_size!=size:raise ValueError('Install or repair WAMU in Models: '+name)
            part=comfy.utils.load_torch_file(path,safe_load=True)
            if state.keys() & part.keys():raise ValueError('WAMU contains duplicate tensor keys.')
            state.update(part)
        model=comfy.sd.load_diffusion_model_state_dict(state)
        if model is None:raise ValueError('The engine could not recognize the WAMU Diffusers checkpoint.')
        return (model,)

class WAMUSplitSigmas:
    @classmethod
    def INPUT_TYPES(cls):return {"required":{"sigmas":("SIGMAS",)}}
    RETURN_TYPES=("SIGMAS","SIGMAS")
    FUNCTION="split"
    CATEGORY="studio/sampling"

    def split(self,sigmas):
        # The publisher's boundary_ratio is 0.9. Each step uses its starting sigma.
        step=int((sigmas[:-1]>=0.9).sum().item())
        if not 0<step<len(sigmas)-1:raise ValueError('WAMU requires both noise stages; use 4-8 steps with shift 3.')
        return (sigmas[:step+1],sigmas[step:])

NODE_CLASS_MAPPINGS={'WAMUShardedLoader':WAMUShardedLoader,'WAMUSplitSigmas':WAMUSplitSigmas}
