# Version 1.11.0

Faceswap now has Image and Video modes. Video uses an isolated, pinned FaceFusion 3.9.1 / HyperSwap pipeline. Select a Library video or import a local video, choose a reference portrait, and queue the result. The original target, portrait and audio are preserved; the result is a new Library video with source and reference metadata.

Person selection includes reference tracking (reference frame and face position), largest face per frame, and all detected faces. The advanced controls provide native 256 or boosted 512 face resolution, output quality, explicit NVIDIA/CPU processing and encoding, and queue priority. Waiting jobs can be edited or cancelled through the existing queue.

Install or repair the optional component in Faceswap or Models. Downloads use immutable source revisions and SHA-256 checks. FaceFusion's dependencies are isolated; existing Torch, Qwen, BFS, video models, settings and Library files remain in place. Upstream content checks are retained. FaceFusion and model usage licenses remain separate from the Studio MIT license.
