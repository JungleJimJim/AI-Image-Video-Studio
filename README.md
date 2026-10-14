# A.I. Image & Video Studio 1.3.1

A local Windows desktop app for text-to-image, image editing, text-to-video and image-to-video. The interface uses your supplied logo, short page descriptions and inline **?** help. No taglines or store credits are included.

Download the Windows installer from [GitHub Releases](https://github.com/JungleJimJim/AI-Image-Video-Studio/releases/latest). The repository contains the application source and small setup assets; model weights download separately.

## Installation

Run **outputs/release-1.3.1/AIImageVideoStudio-Setup-1.3.1.exe**. The default application location is **C:\Program Files\AI Image & Video Studio**. Setup lets you choose another location, a separate writable folder for models/data, and desktop and Start menu shortcuts. Existing studio folders can be upgraded while preserving settings and media. Finish or cancel any current render before upgrading.

The installer downloads the portable Python/PyTorch/ComfyUI runtime and NSFW Wan 1.3B E14 base model. Optional packs can be selected in setup or installed later from **Models**. Downloads resume after cancellation and use pinned revisions and SHA-256 checks. Shared encoder/VAE files are downloaded only once. Model weights are not bundled into the small installer.

## Models

| Model | Tools | Recommended starting settings |
| --- | --- | --- |
| Z-Image-Turbo | Images | 8 steps, CFG 1 |
| FLUX.2 Klein 4B distilled FP8 | Images, instruction editing, multiple references | 4 steps, CFG 1 |
| Qwen-Image-2512 FP8 | Images and typography | 40 steps, CFG 4 |
| Juggernaut XL v9 | Realistic images, redraw, masked editing | 28 steps, CFG 6 |
| Illustrious XL 2.0 | Illustration/anime, redraw, masked editing | 28 steps, CFG 5 |
| DreamShaper XL Turbo 2.1 | Fast images, redraw, masked editing | 8 steps, CFG 2 |
| Qwen Image Edit 2511 FP8 mixed | Instruction editing, multiple references | 40 steps, CFG 3 |
| NSFW Wan 1.3B E14 | Text to Video | 30 steps, CFG 6 |
| Wan 2.2 TI2V 5B | Text or Image to Video | 30 steps, CFG 6 |
| LTX-2 19B distilled FP8 | Text or Image to Video with optional audio | Fixed 8-step recipe, CFG 1 |

The five requested image families are Z-Image, FLUX.2 Klein, Qwen-Image, Juggernaut XL and Illustrious XL. Qwen Image Edit is an additional dedicated editing model. Installing the new families and editor requires about **80 GB of unique downloads**, plus Juggernaut if missing. Models has per-pack installation state and storage estimates.

Windows 10/11 x64, an NVIDIA RTX GPU and a compatible current NVIDIA driver are required for generation. Large Qwen/LTX models use disk-backed loading and RAM offloading on 16 GB cards; sufficient Windows committed memory is still required. Workflow validation does not establish performance or guarantee that every resolution/duration fits your hardware. The app does not change Windows paging settings.

## Images and Image Editor

**Images** generates a PNG and saves its seed/options/workflow beside it. **Send to editor** or **Send to video** selects the image in that tool; it does not begin another render.

**Image Editor** supports:

- Instruction edits with FLUX.2 Klein and Qwen Image Edit. The starting image is image 1; add up to two extra reference images and mention image 2/image 3 in the instruction.
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

**LoRAs** has its own tab, with all ten models as targets. Import local `.safetensors` files or download a Hugging Face file link, then enable adapters, set strengths and click **Save selection**. Images, Image Editor and Video have a **Manage LoRAs** shortcut and show how many saved adapters are enabled for their selected model. Each model remembers its own selection; switching the LoRA target also preserves unsaved drafts.

The tab links to [CivitAI](https://civitai.com/models?types=LORA) and a model-specific [Hugging Face search](https://huggingface.co/models?other=lora). Links open in your regular browser from the native app. Download a matching file from CivitAI and import it locally; direct downloads in the app accept Hugging Face file links. Access or license requirements remain those of the source site and adapter author.

Juggernaut, DreamShaper and Illustrious share an SDXL file library but retain separate enabled selections. Other model families use separate libraries; existing Wan 1.3B files and selections are preserved. SDXL and Wan 1.3B expose separate model and text encoder strengths. Other families apply model-only adapters. Up to eight adapters can be enabled per model, with strengths from -2 to 2.

Choose an adapter matching the **exact base model** described in the tab: Wan 2.2 TI2V **5B**, FLUX.2 Klein **4B distilled**, Qwen-Image **2512**, Qwen Image Edit **2511**, and LTX-2 **19B distilled** are distinct targets. The app validates file format and library assignment, not the trained weights' semantic compatibility. Check the author's trigger words, version and sampling recipe; specialized control or acceleration adapters may need a different workflow. No LoRA weights are bundled or automatically downloaded.

## Validation and source

See **outputs/VALIDATION.md** for exact checks and limitations. AI generation tests require explicit user permission. Source packages exclude downloaded weights, personal media, profiles and credentials.

Build with Python plus **requirements-build.txt**, then run **python build.py** and **python package_source.py**. Exact file revisions/sizes/hashes are in **assets/manifest.json** and **assets/packs.json**. See **outputs/THIRD-PARTY.txt** for upstream terms. The Windows installer is unsigned.

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
