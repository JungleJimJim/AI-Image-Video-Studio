# A.I. Image & Video Studio 1.5.1

A Windows desktop app for n00bs with local text-to-image, image editing, text-to-video and image-to-video generation. One-click downloading and installation of the top models and easy installation and managing of LoRaS.
Includes:
Wan 2.2
LTX-2
Juggernaut XL v9
Dreamshaper XL Turbo 2.1
Z-Image-Turbo
Flux.2 Klein 4B
FLUX 3 Image Klein distilled INT8
Qwen-Image-2512
Illustrious XL 2.0
Qwen Image Edit 2511
Qwen-Image 2.1 Detail Enhancer

Need more models? Or don't understand how to use LoRaS? You can download the source code of this program and feed it to Chatgpt or Claude and ask to include your github or huggingface link.

Download the Windows installer from [GitHub Releases](https://github.com/JungleJimJim/AI-Image-Video-Studio/releases/latest). The repository contains the application source and small setup assets; model weights download separately.

## Installation

Run **outputs/release-1.5.1/AIImageVideoStudio-Setup-1.5.1.exe**. The default application location is **C:\Program Files\AI Image & Video Studio**. Setup lets you choose another location, a separate writable folder for models/data, and desktop and Start menu shortcuts. Existing studio folders can be upgraded while preserving settings and media. Finish or cancel any current render before upgrading.

The installer downloads the portable Python/PyTorch/ComfyUI runtime and NSFW Wan 1.3B E14 base model. Optional packs can be selected in setup or installed later from **Models**. Downloads resume after cancellation and use pinned revisions and SHA-256 checks. Shared encoder/VAE files are downloaded only once. Model weights are not bundled into the small installer.

## Models

| Model | Tools | Recommended starting settings |
| --- | --- | --- |
| Z-Image-Turbo | Images | 8 steps, CFG 1 |
| FLUX.2 Klein 4B distilled FP8 | Images, instruction editing, multiple references | 4 steps, CFG 1 |
| FLUX 3 Image Klein distilled INT8 | Images, instruction editing, up to ten reference images | 16 steps, CFG 1 |
| Qwen-Image-2512 FP8 | Images and typography | 40 steps, CFG 4 |
| Juggernaut XL v9 | Realistic images, redraw, masked editing | 28 steps, CFG 6 |
| Illustrious XL 2.0 | Illustration/anime, redraw, masked editing | 28 steps, CFG 5 |
| DreamShaper XL Turbo 2.1 | Fast images, redraw, masked editing | 8 steps, CFG 2 |
| Qwen Image Edit 2511 FP8 mixed | Instruction editing, multiple references | 40 steps, CFG 3 |
| NSFW Wan 1.3B E14 | Text to Video | 30 steps, CFG 6 |
| Wan 2.2 TI2V 5B | Text or Image to Video | 30 steps, CFG 6 |
| LTX-2 19B distilled FP8 | Text or Image to Video with optional audio | Fixed 8-step recipe, CFG 1 |
| Qwen-Image 2.1 + Elusarca Detail Enhancer | Optional image enhancement | 25 steps, CFG 1, detail strength 1 |

The five requested image families are Z-Image, FLUX.2 Klein, Qwen-Image, Juggernaut XL and Illustrious XL. Qwen Image Edit is an additional dedicated editing model. Installing the new families and editor requires about **80 GB of unique downloads**, plus Juggernaut if missing. Models has per-pack installation state and storage estimates.

Windows 10/11 x64, an NVIDIA RTX GPU and a compatible current NVIDIA driver are required for generation. Large Qwen/LTX models use disk-backed loading and RAM offloading on 16 GB cards; sufficient Windows committed memory is still required. Workflow validation does not establish performance or guarantee that every resolution/duration fits your hardware. The app does not change Windows paging settings.

## FLUX 3 Image Klein

FLUX 3 is a separate full image model, distinct from the existing FLUX.2 Klein. In **Models**, choose **FLUX 3 Image Klein · INT8**. Its official gated weights require signing in to [the Hugging Face model page](https://huggingface.co/black-forest-labs/flux-3-image-klein-comfy), reviewing the access conditions and obtaining access. Enter a read token for that account in Settings, then return to Models to install the selected pack. Tokens are used only for the current download and are not saved. The model pack is approximately **11.0 GB** (10.3 GiB); its separate engine adds about 14 MB of downloads.

The fast distilled checkpoint uses Euler/simple sampling, 16 starting steps and fixed CFG 1; negative prompts are ignored. It is available in Images and Image Editor, and works with the existing queue, library, video handoff and optional image enhancement. The editor accepts the starting image plus nine extra references. Refer to them as `<ref_image_0>` through `<ref_image_9>` and describe the complete desired edited result. Painted edits preserve the resized original outside the mask. Studio output dimensions remain 256–1536 pixels in multiples of 64; higher native model resolutions and a graphical bounding-box editor are not exposed by this integration.

A pinned ComfyUI 0.41.0 engine is downloaded to its own folder only for this model. Its `comfy-aimdo` dependency is installed separately, with no global package upgrades. Other models retain the existing engine. FLUX 3's VAE is stored under a distinct filename because the upstream file differs from the existing FLUX.2 VAE. Its LoRA library is also separate; use adapters explicitly compatible with distilled FLUX 3 Image Klein 5.6B.

The optional prompt upsampler and slower Base checkpoint are not installed by this pack. FLUX 3 weights retain the **FLUX Kommunity License**, separate from the application's MIT license. Actual model inference and memory fit on this machine have not been tested; the new engine's CPU probe and native graph checks do not load weights.

## Images and Image Editor

**Images** generates a PNG and saves its seed/options/workflow beside it. **Send to editor** or **Send to video** selects the image in that tool; it does not begin another render.

**Image Editor** supports:

- Instruction edits with FLUX.2 Klein, FLUX 3 Image Klein and Qwen Image Edit. The starting image is image 1; add up to two extra reference images and mention image 2/image 3 in the instruction.
- SDXL redraw with Juggernaut, Illustrious or DreamShaper. Describe the full desired image and adjust redraw strength.
- Painted masks, with brush size, paint/erase, undo and clear. SDXL uses inpaint denoising. Instruction models edit the full image and composite only the painted region onto the resized original. Saved edits preserve a mask copy beside the result.
- Crop/resize using original pixel coordinates, center-square/full-image shortcuts and an aspect-ratio lock. CPU processing saves a separate PNG without loading an AI model.

Import or drag in PNG, JPEG or WebP up to 25 MB and 25 megapixels. Imports are saved as PNG copies, honor camera orientation and leave the original intact. AI output dimensions are multiples of 64 between 256 and 1536 pixels. Crop/resize exports support 64–4096 pixels.

## Library and video

**Library** combines generated videos, generated/edited images, imports, crops and extracted frames. Search, media filters and pagination include older records. Square thumbnails are cached CPU previews; original files keep their full aspect ratio and dimensions. Click an item to preview it, save a copy, or reuse available generation settings. Images can be sent to the editor or video tool.

For videos, **Use frame** lets you play/scrub the MP4, enter a timestamp and save a frame directly to the editor or image-to-video tool. This creates a PNG library entry and keeps the MP4. New crop/edit/frame entries retain their source ID.

**NSFW Wan 1.3B E14** uses the requested fine-tuned checkpoint and is text-only. Wan 2.2 and LTX-2 animate starting images. LTX-2 exports optional audio and uses its published distilled sigma schedule. Video frames are capped at 481: Wan uses 4n+1, LTX uses 8n+1. Exact duration is shown as frames/FPS. Long clips need much more memory/time and may lose consistency; begin with short clips and smaller dimensions.

## Layout, settings and LoRAs

The desktop window supports maximize and **Fullscreen / F11**; Escape exits fullscreen. Main action buttons remain visible, while advanced controls and library contents scroll inside their own panels. The resource bar shows GPU, VRAM, RAM and committed memory across the computer.

**Settings** selects output storage and opens image/video/log folders in Explorer. MP4s use the chosen output folder; AI PNGs use its Images subfolder. Imports and CPU edits use the studio data folder. Changing the output folder does not move older media.

**LoRAs** has its own tab, with all twelve model targets. Import local `.safetensors` files or download a Hugging Face file link, then enable adapters, set strengths and click **Save selection**. Images, Image Editor and Video have a **Manage LoRAs** shortcut and show how many saved adapters are enabled for their selected model. Each model remembers its own selection; switching the LoRA target also preserves unsaved drafts.

The tab links to [CivitAI](https://civitai.com/models?types=LORA) and a model-specific [Hugging Face search](https://huggingface.co/models?other=lora). Links open in your regular browser from the native app. Download a matching file from CivitAI and import it locally; direct downloads in the app accept Hugging Face file links. Access or license requirements remain those of the source site and adapter author.

Juggernaut, DreamShaper and Illustrious share an SDXL file library but retain separate enabled selections. Other model families use separate libraries; existing Wan 1.3B files and selections are preserved. SDXL and Wan 1.3B expose separate model and text encoder strengths. Other families apply model-only adapters. Up to eight adapters can be enabled per model, with strengths from -2 to 2.

Choose an adapter matching the **exact base model** described in the tab: Wan 2.2 TI2V **5B**, FLUX.2 Klein **4B distilled**, Qwen-Image **2512**, Qwen Image Edit **2511**, Qwen-Image **2.1**, distilled **FLUX 3 Image Klein 5.6B**, and LTX-2 **19B distilled** are distinct targets. The app validates file format and library assignment, not the trained weights' semantic compatibility. Check the author's trigger words, version and sampling recipe; specialized control or acceleration adapters may need a different workflow. No weights are bundled. Installing the optional Qwen 2.1 enhancer explicitly downloads its required detail LoRA; other adapters are installed by the user.

## Queue and model removal

Every AI generator now adds a job to **Queue**. Jobs run one at a time across images, edits, videos and enhancement passes. Add more while a job runs. Higher priorities (0–10) run first; arrows reorder jobs with equal priorities. A running job is never interrupted by priority changes.

Pause lets the current job finish. Cancel stops a waiting job or requests interruption of the running job. **Edit** pauses the queue and opens a waiting job's full options in its tool; save changes and resume when ready. Seeds, source images, masks, LoRAs, enhancement options and output folders are captured per job. Retry makes a new copy. Errors pause the queue, and unfinished jobs reopen paused; interrupted jobs require review and retry. Clearing queue history keeps library media.

**Models → Uninstall** previews the exact downloaded weights and disk space. Shared files needed by another installed model, runtime software, LoRAs, settings and library media are kept. Finish or cancel jobs referencing the model first. Removed weights can be downloaded again; uninstalling the original Wan model does not disable installed optional models.

## Optional enhancement

**Upscale** takes an existing library image or video and saves a separate enhanced entry. The library preview has an **Upscale / enhance** button. Alternatively, enable **Enhance after generation** in Images, Image Editor or Video. Configure its options on Upscale; each queued job captures a copy. A failed or cancelled enhancement leaves the original available.

The requested [Elusarca Qwen 2.1 Detail Enhancer](https://civitai.com/models/2956730/elusarcas-qwen-21-detail-enhancer) is a LoRA for Qwen-Image 2.1. Install its pack in Models: approximately **17.4 GB** of separate downloads, including the author's hash-matched adapter from Hugging Face. It uses instruction-conditioned generative enhancement, so fine details may change. The result is capped at roughly four megapixels and 4096 pixels per axis. Qwen 2.1 has its own **Qwen Research License**; check the terms linked in Models. Its LoRA target is distinct from Qwen 2512 and Qwen Edit 2511. The built-in detail adapter plus up to seven additional compatible adapters can be used.

[RTX video enhancement](https://github.com/tritant/ComfyUI_NVIDIA_RTX_VSR_Long_Video) uses the pinned upstream frame pipeline in an isolated worker. Install its optional component in Models (about **467 MB** of SDK/FFmpeg downloads). This preserves the existing PyTorch stack and leaves global ComfyUI custom nodes disabled. It requires an RTX GPU and a supported NVIDIA driver; NVIDIA's SDK lists Windows driver 570.65 or newer. Quality, 1–4× scale, denoise/deblur, segment size and encoder are configurable. Audio is retained where supported. It increases resolution, not duration or frame rate. H.264 NVENC outputs are limited to 4096 pixels per axis; HEVC/CPU encoder support depends on the FFmpeg build and output size. The NVIDIA SDK retains its vendor license.

New enhancement workflows have been validated without loading weights. Actual Qwen 2.1/RTX VSR inference and quality have not been tested in this release.

## Validation and source

See **outputs/VALIDATION.md** for exact checks and limitations. AI generation tests require explicit user permission. Source packages exclude downloaded weights, personal media, profiles and credentials.

Build with Python plus **requirements-build.txt**, then run **python build.py** and **python package_source.py**. Exact file revisions/sizes/hashes are in **assets/manifest.json**, **assets/packs.json**, **assets/enhancers.json** and **assets/engines.json**. See **outputs/THIRD-PARTY.txt** for upstream terms. The Windows installer is unsigned.

For a Windows source build:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-build.txt
python -m unittest discover -s tests
python build.py
python package_source.py
```

The build downloads the pinned Microsoft WebView2 SDK if it is absent and compiles the native host using the Windows .NET Framework compiler. The automated tests do not generate AI images or videos.

The app's original source code uses the [MIT license](LICENSE). Third-party components and model weights retain their upstream licenses; see [third-party notices](outputs/THIRD-PARTY.txt).
