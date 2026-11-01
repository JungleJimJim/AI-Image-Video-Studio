# Studio 1.17.0 — Managed OpenJutsu setup

OpenJutsu setup now installs its backend as well as its editor. A separate manually configured ComfyUI service is no longer required.

1. Install Studio's base runtime if it is not already present.
2. Open **OpenJutsu** beside Video. Leave **Managed by Studio** selected.
3. Choose a model folder with enough space and select the model packs you want. All packs are initially selected.
4. For FLUX relighting, accept the linked Hugging Face model conditions and enter your read token. It is used for downloads and is not saved.
5. Click **Install selected setup**, then **Open workspace**. **Software only** installs the backend and editor without large model downloads.

The setup downloads pinned ComfyUI, 13 node packs, isolated supplemental Python dependencies, FFmpeg, the full OpenJutsu editor, portable Node and proxy. It keeps Studio's existing generators and base PyTorch installation intact. The installation checks all 63 required node classes and deferred Metric3D/InsightFace imports on CPU without loading model weights.

| Model pack | Full download before shared-model reuse |
| --- | ---: |
| Character swaps, objects and video editing | 48.0 GiB |
| FLUX relighting and picture workflows | 20.8 GiB |
| Face detection and identity refinement | 0.7 GiB |

Matching shared Studio models are SHA-256 verified and reused without copying, moving or renaming them. New downloads are resumable and verified. The setup uses a distinct `flux3-vae.safetensors` filename to preserve older FLUX VAEs. Existing shared files with the wrong checksum are left untouched; the correct file downloads into the selected private folder. Allow about 6 GB separately for software, installation caches and production builds.

The managed engine is stored in `engines/openjutsu`; models default to `openjutsu-models` and can be placed on another drive. Inputs, profiles and temporary workspace data live in `openjutsu-data`, outside the replaceable engine. Completed output is stored in the configured video output folder under `OpenJutsu`. Install repairs preserve model folders and workspace data.

Opening the workspace pauses Studio's queue and releases Studio's engine. Use OpenJutsu's own job/cancel controls, finish jobs before stopping the workspace, and explicitly resume Studio's queue afterward. Closing Studio stops the processes it owns, including active managed renders. The optional external-backend mode preserves externally running services and existing saved external configurations.

Models retain their publishers' terms. FLUX access approval cannot be automated. InsightFace buffalo_l pretrained weights have non-commercial research restrictions; review the linked original sources for your intended use.

Validation covers installation, imports, registered nodes, process ownership, shared-model preservation and packaged Studio startup. No AI generation was run, and output quality, every workflow and GPU memory requirements have not been benchmarked.
