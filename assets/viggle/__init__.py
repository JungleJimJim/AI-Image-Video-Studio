"""Qwen-Image-2.1 viggle-turbo nodes for ComfyUI.

ViggleTurboSigmas: same schedule as diffusers QwenImage21Pipeline(sigmas=nodes): FlowMatchEulerDiscreteScheduler with
dynamic exponential shift, mu = calculate_shift(tokens, 256, 8192, 0.5, 0.9), no shift_terminal, final 0.
tokens = (H/16) * (W/16) of the image being sampled, read from the latent that goes into the sampler.

ViggleTurboLora: the LoRA as a runtime side branch, y = W x + B A x (diffusers/PEFT without fuse_lora()).
LoraLoaderModelOnly merges it into the weights instead: on bf16 weights round-to-nearest keeps only ~70% of this
LoRA's update, on int8 weights the stochastic requantization keeps all of it but adds noise ~4x its size.
"""

import json
import math

import torch
import torch.nn.functional as F

import comfy.patcher_extension
import comfy.utils
import folder_paths


class ViggleTurboSigmas:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "latent": ("LATENT", {"tooltip": "The latent passed to the sampler; its size sets the resolution shift."}),
                "nodes": ("STRING", {"default": "1.0, 0.9375, 0.875, 0.75, 0.5, 0.25",
                                     "tooltip": "Raw (unshifted) student nodes. v0.3 LoRA: 1.0, 0.9375, 0.875, 0.75, 0.5, 0.25 (6 steps). Add or remove steps at the high-noise end only (5: 1.0, 0.875, ...; 7: 1.0, 0.9583, 0.9167, 0.875, ...); keep 0.875, 0.75, 0.5, 0.25."}),
            }
        }

    RETURN_TYPES = ("SIGMAS",)
    FUNCTION = "get_sigmas"
    CATEGORY = "sampling/custom_sampling/schedulers"

    def get_sigmas(self, latent, nodes):
        s = latent["samples"]
        r = latent.get("downscale_ratio_spacial", 16) / 16   # EmptyLatentImage is /8, the sampler resizes it to /16
        tokens = round(s.shape[-2] * r) * round(s.shape[-1] * r)
        mu = 0.5 + (0.9 - 0.5) * (tokens - 256) / (8192 - 256)
        t = torch.tensor([float(x) for x in nodes.split(",")], dtype=torch.float64)
        sigmas = math.exp(mu) / (math.exp(mu) + (1 / t - 1))
        return (torch.cat([sigmas, sigmas.new_zeros(1)]).float(),)


def lora_fwd(x, ab):
    return F.linear(F.linear(x, ab[0].to(x.dtype)), ab[1].to(x.dtype))


def add_hook(mod, ab):
    return mod.register_forward_hook(lambda m, inp, out: out + lora_fwd(inp[0], ab))


def add_mlp_hooks(mlp, gate, up, down):
    # fused SwiGLU: gate_up = [gate_layer; proj], and `out` runs inside an int8/fp16 kernel that bypasses its hooks,
    # so its branch is added to the MLP output from the (LoRA'd) gate_up output
    h = {}

    def gate_up_hook(m, inp, out):
        h["gu"] = out + torch.cat([lora_fwd(inp[0], gate), lora_fwd(inp[0], up)], -1)
        return h["gu"]

    def mlp_hook(m, inp, out):
        g, u = h.pop("gu").chunk(2, -1)
        return out + lora_fwd(F.silu(g) * u, down)

    return [mlp.gate_up.register_forward_hook(gate_up_hook), mlp.register_forward_hook(mlp_hook)]


def run_with_lora(lora, executor, *args, **kwargs):
    dm = executor.class_obj
    for ab in lora.values():
        if ab[0].device != args[0].device:
            ab[0], ab[1] = ab[0].to(args[0].device), ab[1].to(args[0].device)
    hooks = []
    for name, ab in lora.items():
        parent, _, leaf = name.rpartition(".")
        if not getattr(dm.get_submodule(parent), "fused", False):
            hooks.append(add_hook(dm.get_submodule(name), ab))
        elif leaf == "out":
            hooks += add_mlp_hooks(dm.get_submodule(parent), lora[parent + ".gate_layer"], lora[parent + ".proj"], ab)
    try:   # the diffusion model is shared with other MODEL outputs, the hooks must not outlive this call
        return executor(*args, **kwargs)
    finally:
        for hk in hooks:
            hk.remove()


class ViggleTurboLora:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model": ("MODEL",),
                "lora_name": (folder_paths.get_filename_list("loras"), {"tooltip": "diffusers-format Qwen-Image-2.1 LoRA."}),
                "strength": ("FLOAT", {"default": 1.0, "min": -4.0, "max": 4.0, "step": 0.05, "tooltip": "Keep 1.0 for viggle-turbo."}),
            }
        }

    RETURN_TYPES = ("MODEL",)
    FUNCTION = "load"
    CATEGORY = "loaders"
    DESCRIPTION = "Applies the LoRA at runtime (y = Wx + BAx) instead of merging it into the weights, which is lossy on bf16 and int8."

    def load(self, model, lora_name, strength):
        sd, meta = comfy.utils.load_torch_file(folder_paths.get_full_path_or_raise("loras", lora_name), return_metadata=True)
        cfg = json.loads((meta or {}).get("lora_adapter_metadata", "{}"))
        scale = strength * cfg.get("transformer.lora_alpha", 1) / cfg.get("transformer.r", 1)
        lora = {k.removeprefix("transformer.").removesuffix(".lora_A.weight"): [sd[k], sd[k.replace("lora_A", "lora_B")] * scale]
                for k in sd if k.endswith(".lora_A.weight")}
        m = model.clone()
        m.add_wrapper_with_key(comfy.patcher_extension.WrappersMP.DIFFUSION_MODEL, "viggle_turbo_lora",
                               lambda executor, *a, **kw: run_with_lora(lora, executor, *a, **kw))
        return (m,)


NODE_CLASS_MAPPINGS = {"ViggleTurboSigmas": ViggleTurboSigmas, "ViggleTurboLora": ViggleTurboLora}
NODE_DISPLAY_NAME_MAPPINGS = {"ViggleTurboSigmas": "Qwen-Image-2.1 Viggle Turbo Sigmas",
                              "ViggleTurboLora": "Qwen-Image-2.1 Viggle Turbo LoRA (unmerged)"}
