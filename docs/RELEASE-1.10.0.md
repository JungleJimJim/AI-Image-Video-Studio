# Version 1.10.0

## Optional image models

- Krea 2 Turbo: eight-step local image generation using the official Comfy-Org FP8 conversion. Includes a dedicated Krea 2 LoRA library and uses the existing compatible engine. Shares its VAE with Qwen-Image. The initial pack provides text-to-image generation, without instruction editing or the separate style-reference adapter.
- RealVisXL v5 and CyberRealistic XL v11VAE: general-purpose photorealistic SDXL checkpoints mirrored on NSFW-API. Available in Images and Image Editor, including masked redraws. They use the shared SDXL LoRA library while retaining separate per-model selections.

All downloads are optional and pinned to upstream revisions, file sizes and SHA-256 checksums. Model links and license information are shown in Models. Dedicated explicit sexual-content adapters from the NSFW-API catalogue are not included.

Sources:

- <https://huggingface.co/krea/Krea-2-Turbo>
- <https://huggingface.co/Comfy-Org/Krea-2>
- <https://huggingface.co/NSFW-API/RealVisXL>
- <https://huggingface.co/NSFW-API/CyberRealism>

## Shared model storage

The downloader compares exact SHA-256 checksums and sizes. Files at the same destination are downloaded once, even when selected in several packs or supplied by different mirrors. An installed file is verified before it is reused.

When identical bytes are required under different filenames or folders, the installer creates hard links on supported local drives, keeping one physical copy. Existing duplicates can be consolidated when reinstalling the affected pack. If the drive cannot create the required links, installation stops with an explanation instead of downloading another copy. This does not automatically reorganize existing downloads at application startup.

The Models selection and setup disk estimate count shared content once. Distinct fine-tuned checkpoints and different quantizations remain separate: sharing an architecture does not make their weights identical.

Wan 2.2 now explicitly includes its UMT5 dependency in the catalogue. Uninstall previews preserve dependencies needed by other complete or partially installed packs and account for files whose storage is shared through hard links. Installing an optional pack into a new runtime no longer also downloads unrequested Wan 1.3B weights.

## Build checks

Desktop builds verify the pinned WebView2 SDK archive even when it is cached, take their dependency DLLs directly from that verified archive, and package only the expected desktop files. Each release rebuilds the launcher from source in a versioned build directory.

For this release, Windows Defender definitions were updated and custom scans completed for the freshly compiled launcher, app and installer without new detections. The older launcher detection remains quarantined; no exclusions or protection changes were made. A clean scan is not a guarantee against future detections.

## Validation

- 204 Python regression tests passed, including shared downloads, hard links, corrupt-file checks, cancellation and protected uninstall behaviour.
- JavaScript checks passed, including the shared download estimate and existing library, notification, queue and update controls.
- CPU-only engine schema validation passed for the three new image workflows. No weights were loaded and no AI generation was run.
- Isolated browser checks verified Krea defaults, SDXL editing controls, the new model cards and shared download totals.

Generation quality and performance for the newly added checkpoints have not been tested. Install the desired weights from Models before selecting them for a generation job.
