# Version 1.10.5

The header has a larger logo and one version number immediately before Fullscreen.

Video's Aspect ratio follows the starting image selected from Library or imported from a local file. Dimensions respect each model's alignment, size limits and usual pixel budget; small rounding differences may be necessary. Presets and custom dimensions remain available. An × beside the starting image clears its saved selection without deleting the Library file.

GPU activity is read directly from NVIDIA's driver every second, with nvidia-smi as a fallback. Unsupported or stale activity readings show a dash rather than 0%. VRAM remains a separate allocation reading: high allocated memory can coexist with low activity during loading, CPU work or offloading.

Restoring a selected starting image now activates Image → Video, switching away from text-only Wan 1.3B when necessary. Text-only jobs omit unused image IDs, and the backend rejects conflicting text/image requests. The Video tab explains whether the image is a starting frame or an appearance reference.

The SageAttention launcher initializes ComfyUI’s native memory library before importing consumers that cache its DLL handle. This fixes Ref2VA’s `hostbuf_allocate` / `vbars_reset_watermark_limits` errors while preserving native disk-backed loading.
