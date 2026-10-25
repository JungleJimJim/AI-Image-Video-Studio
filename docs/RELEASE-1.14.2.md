# Version 1.14.2

Adds **WAMU · Wan 2.2 I2V Lightning 14B** as an optional model in Models and Video. Includes the Singularity V2 integration from 1.14.1.

- Uses the publisher's original six BF16 Diffusers shards, pinned to revision `4e7c4ac31d35d653c73df44990f3ecd01d5efd40`, with SHA-256 checks and resumable downloads. The high/low model weights total 57,155,829,760 bytes (53.2 GiB).
- Reuses the existing Wan FP8 UMT5 encoder and Wan 2.1 VAE. The 5B Wan 2.2 VAE is not used for this 14B model.
- Adds an isolated engine and shard loader. The original files load directly; no merged checkpoint or second conversion copy is required.
- Requires a starting image. Uses native Wan image conditioning, separate high/low-noise models, four steps by default (4–8 supported), CFG 1, UniPC, shift 3 and a sigma boundary of 0.9 from the repository configuration. Low-noise sampling continues the high-noise latent without adding fresh noise.
- Outputs silent video. Extra compatible Wan 2.2 I2V 14B LoRAs apply to both stages. Stage-specific LoRAs are not exposed.
- Retains the existing frame grid, queue source/seed preservation, first-frame input and aspect controls. Controls for audio and extra character references stay hidden.

The merge publisher has not specified a license. This native ComfyUI workflow may differ from Diffusers. Generation and operation on a 16 GB GPU remain unverified; allow substantial system RAM, paging and disk space.

No full model weights were downloaded and no inference was started for this update.
