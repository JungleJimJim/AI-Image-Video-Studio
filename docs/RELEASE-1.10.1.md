# Version 1.10.1

Settings now includes an optional SageAttention backend with automatic PyTorch fallback. It uses the Sage-style INT8 implementation already bundled with Comfy Kitchen; no additional package, compiler or model download is required on the included runtime.

Choose **Settings → Generation acceleration → Check & enable SageAttention** to run a small GPU math compatibility test and enable the preference if it passes. This test does not load models or create an image or video. The check is unavailable while another operation is running. New installations retain PyTorch as the standard preference until SageAttention is selected or enabled.

The preference applies to the next regular image, edit, video, faceswap or image enhancement job. Switching preferences does not interrupt an active generation. Dedicated talking-avatar workers, voice services and RTX VSR retain their existing backends.

Settings distinguishes the requested backend from the running engine's actual status. SageAttention is marked as in use only after a successful attention call. The engine switches to PyTorch if the kernel is unavailable, rejects an input or produces non-finite values. Fallback happens inside the existing call: it does not submit a duplicate generation. Fatal CUDA context errors and memory exhaustion still stop the job. Different quantization can change output; finite-value checks cannot guarantee identical image quality.

Generated metadata records the attention backend. Existing model weights, settings and Library files are retained by the application-only update. No render-speed claim is made without measuring a representative generation.

The Settings notification section now sits inside the storage/settings column. This fixes an overlapping grid area that could intercept clicks on other controls.

References:

- [Comfy Kitchen](https://github.com/Comfy-Org/comfy-kitchen)
- [SageAttention Windows integration guidance](https://github.com/woct0rdho/SageAttention#installation)
- [Original SageAttention implementation](https://github.com/thu-ml/SageAttention)
