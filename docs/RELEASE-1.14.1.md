# Version 1.14.1

Adds WarmBloodAban/Minimax-h3_Singularity as **MiniMax H3 · Singularity V2 INT8** in Models and Video.

- Pins the V2 pruned INT8 checkpoint (20,967,647,456 bytes) to revision `1259cf16cd0b655ba691a32fb46a409142762972`, with SHA-256 verification and resumable downloads.
- Reuses the Ref2VA engine, shared MiniMax encoder/VAEs and publisher-recommended four-step Turbo LoRA. No duplicate shared-component download is needed.
- Supports a primary appearance reference plus eight extra references, optional generated audio, saved queue settings and extra compatible Ref2VA LoRAs.
- Uses dense attention; VSA gates are not validated for this fine-tune and are disabled. This Studio integration exposes reference-to-video; other upstream modes are not exposed.
- Uses the existing MiniMax frame/dimension constraints, 24 fps, four steps and low-memory profile. Start at 768 × 512 with a short clip. 16 GB GPU inference remains unverified.

Checkpoint metadata and quantization headers were checked. No model weights were downloaded and no video was generated during integration validation.
