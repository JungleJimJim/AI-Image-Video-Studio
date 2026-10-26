# Studio 1.14.3: model VRAM descriptions and filters

Models now has All models, 8 GB VRAM and 16 GB VRAM filters. The 16 GB view includes the 8 GB candidates. All 37 downloadable model/component cards show VRAM guidance. Memory estimates are guidance for the shipped weights and workflow, not measured minimums or a guarantee for every output size. No 8 GB GPU inference was performed.

8 GB candidates: the five SDXL packs (Juggernaut, DreamShaper, Illustrious, RealVisXL and CyberRealistic), FP8 FLUX.2 Klein, FP16 MuseTalk, and conditional Wan 1.3B at small resolution/short duration with Low VRAM mode. Larger models are conservatively grouped under 16 GB with offloading guidance, or All models where fit is unknown. MiniMax/Ref2VA, WAMU, larger avatar packs, BF16 MOSS and component-only packs do not receive an unsupported 8/16 GB fit label.

Filtering preserves installation selections and survives inventory refresh. The selection count/download estimate includes selections hidden by the current filter. Fish Speech's separate setup card stays under All models. Model download sizes remain distinct from VRAM requirements.

Sources checked 2026-10-26:
- https://github.com/Wan-Video/Wan2.1 reports 8.19 GB for 1.3B; 8 GB Studio classification is conditional on lower output settings and offloading, not the upstream 480p benchmark.
- https://v7.invoke.ai/users-guide/models/local-models/flux-2/ documents FP8 Klein 4B at 8 GB+; this Studio pack also uses FP8, although the surrounding runtime differs.
- https://huggingface.co/Tongyi-MAI/Z-Image-Turbo describes its 16 GB target; the Studio pack uses BF16.
- https://github.com/TMElyralab/MuseTalk documents FP16 use on a 4 GB laptop GPU; this Studio wrapper's 8 GB tier is an estimate with extra headroom.
- https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0 documents the standalone SDXL pipeline; the 8 GB Studio tier for its fine-tunes is an engineering estimate with low-memory settings.

Validation: real headless Chrome against a processing-disabled local fixture; 37 packs, 8 candidates under 8 GB and 22 under 16 GB. Checked descriptions, filtering, excluded unknown/24 GB fits, retained selections, refresh behavior and no script errors. Screenshot: outputs/vram-filters-preview.png. No downloads or image/video generation started.

Final validation: all 287 Python regressions passed with local fixture socket access. Studio UI helper and shared-download estimate tests passed. PyInstaller app assets match source; the installer embeds that verified app. The 1.14.3 installer was built locally; no public release or installed-copy upgrade was performed.
