# Studio 1.15.1 — Library, workspace and local AI tools

Library detail views close when clicking the backdrop, with Previous/Next controls on either side. Navigation retains the current media filter and search, including across page boundaries. Clicking or dragging inside the dialog keeps it open.

Library offers selection across pages, deletion to Studio Trash, restoration from Trash, and ZIP export of the original image/video files. Delete requires confirmation. Files used by active/queued jobs cannot be deleted. File moves and index changes have rollback/recovery journals. Trash remains on disk until files are restored or managed separately.

Display titles use the first five prompt words, falling back to the filename for imported media without prompts. Actual filenames and paths are unchanged. Catalog order remains newest creation date first.

Voice adds optional managed packs:
- **Kokoro-82M ONNX:** English preset voices, speed control, CPU inference with no dedicated VRAM.
- **Qwen3-TTS 0.6B Base:** voice cloning from a 0.1–15 second recording, optional matching transcript, language selection, FP16 NVIDIA CUDA or CPU. 8 GB VRAM fit is an estimate; 16 GB gives additional headroom. This is the official FP16 checkpoint, distinct from the community GGUF runtime.
- Both use isolated package folders, pinned model revisions/checksums, cancellable setup/generation and Studio's existing queue. Recordings remain available in Talking Avatar. Existing Fish/SGLang connections are retained.

Bottom-filmstrip thumbnails can be dragged into Image Editor, Upscale, Canvas, Video, Faceswap and Talking Avatar. The current tool receives the source or reference; previews work in Images and Video. Unsupported media shows guidance without changing the current source. Internal drops never start media generation, and existing desktop file imports remain available.

The optional AI prompt enhancer uses Qwen2.5 1.5B Instruct Q4_K_M with a pinned llama.cpp CPU runtime, about a 1.1 GB download. Images, Image Editor, Video, Faceswap and Talking Avatar offer Refine wording and Add visual detail, with editable drafts and explicit Apply. Original prompts remain intact until Apply; stale drafts cannot overwrite newer manual edits. CPU prompt rewriting can run independently of the image/video queue. The authenticated runtime is bound to loopback, closes after each rewrite, and uses no dedicated VRAM.

Upscale uses Choose in Library with a selected-source label, without the duplicate source dropdown. Local image import remains available.

Enhance after generation starts unchecked in Images, Image Editor and Video, including when previous jobs used enhancement. Queued jobs retain their explicit enhancement choice.

The shared image/video startup and failure messages now refer to the generation engine.

Validation:
- 328 Python tests passed, including disposable-file deletion, rollback, restore, authenticated ZIP downloads, queued-source protection and voice option/worker validation.
- Library/voice DOM tests passed for backdrop handling, mixed photo/video navigation, pagination, filters, multi-select, cancel/delete/restore, ZIP export, titles and local voice payloads.
- Filmstrip drop tests cover Editor, Upscale image/video, video sources/previews, Avatar, Faceswap, image references, Canvas, polling stability and incompatible-drop protection.
- Prompt enhancer tests cover five contexts, optional installation, editable drafts, stale-prompt protection, cancellation, authentication, CPU-only loopback transport and process cleanup. Model replies are mocked in tests.
- A real browser drag loaded a fixture image in Image Editor. Further native browser checks ended when Computer Use could not confidently determine the active browser URL; video routing passed the DOM interaction suite.
- Existing UI helper and Canvas/reference/model integration suites were retained.
- No personal media was deleted in tests. No AI speech or prompt-output quality benchmark was run; hardware guidance does not guarantee a particular resolution, duration or concurrent workload.
