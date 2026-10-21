# 1.12.0

MOSS-Image Base, MOSS-Image SFT and Kromoss are available in Models and Images, each with compact INT8 or full BF16 weights. Compact packs use Qwen3.5-9B W4A8; optional INT8/BF16 encoders and the full MOSS VAE can be selected separately. Identical encoders, VAEs and LoRAs are shared by content and downloaded once. The newer full MOSS VAE has a different checksum from the existing FLUX.2 VAE and uses its own filename.

The MOSS panel supports captions, tags, raw scene-layout JSON, and a visual layout editor for objects, characters, rendered text, boxes and palettes. Color-region and depth maps can be chosen from Library or local files, with strength and start/end controls. Optional components can be installed directly from the panel. Layouts and map IDs survive queueing, editing and Library metadata.

SFT uses its requested 8-step DMD LoRA. Base/Kromoss offer DMD and DMD2, with 8-step or 4-step sampling. Full sampling exposes steps, CFG, shift and negative-branch skip settings. Compatible custom LoRAs share a MOSS library.

Image Editor supports single-image repainting and masked repainting with redraw strength. These are not multi-reference instruction edits. Control maps must be provided by the user; depth estimation is not included. Output dimensions are multiples of 16, up to 4,194,304 pixels.

MOSS uses an isolated pinned ComfyUI 0.42.0 engine and kernel package; existing engines and Torch installations are preserved. The Windows bounded tensor reader also applies to MOSS. Model weights are optional downloads, not bundled into the installer or downloaded during validation.

Validation uses Python regressions, real-engine CPU graph validation and a processing-disabled DOM UI fixture. No generated media is used. The UI development test requires `jsdom@30.1.3` and the local fixture server `research/serve_moss_ui_1120.py`; these are development dependencies only.
