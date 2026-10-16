# A.I. Image & Video Studio 1.6.0

- All 123 Python regressions pass in tests-1.6.0-final.log. New updater cases cover numeric version ordering, stable-release and asset/checksum validation, foreign URL rejection, read-only checks, session-token enforcement, busy guards, cancellation, exact process identities and PID reuse, queue pausing, failed and successful handoffs, new-session/changed-installation rejection, combined and separate data folders, and rollback of partially replaced application files.
- A transient Windows file-sharing failure appeared in the first full regression run. Atomic JSON writes now use bounded retries for transient PermissionError on Windows. Focused tests verify recovery and preservation of the previous settings on permanent failure. The final full suite passes.
- Node regressions pass for both existing studio controls and update UI confirmation, busy state, server-issued tickets, plain-text notes and retry behavior. JavaScript syntax checks pass for all three studio scripts.
- An isolated browser preview with inference and actual installation blocked confirms the new tab order, version label below the logo, all five About links, Settings fit without panel overflow at 1280x720, update confirmation, Later without an installation request, and Install update sending the confirmed ticket. No console warnings/errors were observed. Evidence: update-confirmation-ui-1.6.0.json and ui-validation-1.6.0.json.
- The packaged installer test caught a process exiting during identity inspection. The Windows helper now checks the process exit signal before and after inspection, including when a parent retains the exited process handle. A real exited-process regression passes.
- The corrected packaged installer passes an isolated Windows handoff: it waits for the captured process, replaces the app, reopens the native desktop window, and preserves six settings/model/LoRA/media/queue files byte for byte. The real application registration is unchanged. Evidence: update-smoke-1.6.0-validation.json.
- The user's two newer signed README commits were imported as ancestors. The original GitHub README bytes remain an exact prefix; only a v1.6.0 section is appended at the bottom. Evidence: readme-1.6.0-preservation.json.
- The updater is initiated manually, fetches only the program's public stable release, requires the exact Windows installer asset URL and GitHub SHA-256 digest, and downloads no model weights. The independent installer waits for the captured app/host identities and refuses to replace files if a studio session is still open. Application copying is transactional; personal data is outside the replacement payload. Program Files elevation remains limited to the existing app-copy helper.

No AI image or video was generated for this update. Inference was mocked or blocked throughout. Program Files administrator approval is covered by existing mocked installer tests; no administrator-owned installation was changed during validation.

## Previous validation

# A.I. Image & Video Studio 1.5.2

- All 106 Python regressions pass. LoRA tests reproduce the exact Windows filename-menu mismatch and verify submission with detail strength 1.7; saved portable names and adapter strengths are preserved. Both loader classes and supported combo schemas are covered. Existing serial scheduling, cancellation, media preservation and model removal checks pass.
- Native CPU-only validation reproduces the Qwen 2.1 filename rejection, then accepts the corrected graph at strength 1.7. All 17 original-engine workflows pass with native Windows LoRA names, without weight loading or CUDA initialization. Evidence: workflow-validation-1.5.2.json and native-1.5.2-final.log.
- Node UI regressions verify safe random seeds, fixed seeds, failed submissions, in-flight draft preservation, waiting-job editing, auto-enhancement seeds, seed zero, HTML escaping and source metadata. Browser checks in an isolated profile with inference blocked confirm Video / Upscale / Library order, checked seed and failure-continuation controls, a changed seed after queuing a paused fixture, and enhanced-copy details including its original FLUX 3 model and seed zero. The Library preview places image and metadata side by side on wide windows. No browser console errors were observed.
- All four FLUX 3 native graphs also pass CPU-only validation with Windows LoRA menu entries, including ten-reference masked editing. CUDA stays uninitialized. Evidence: flux3-workflow-validation-1.5.2.json. The original Windows rejection and its successful corrected validation were both observed.
- Queue failures now remain in history while subsequent jobs run by default. The persistent Continue after failed jobs option restores pause-on-failure when disabled. Regressions cover execution and preparation failures, disabled-policy pausing, preference persistence and keeping previously paused queues paused. Queued job seeds and retries remain frozen.
- Library details include model, seed, prompts, dimensions, timing, LoRAs, enhancement parameters, all saved options and complete parent history beyond the current library page. Missing legacy metadata is identified rather than guessed. Source cycles are bounded.

No AI image or video was generated for this update. CPU graph validation and mocked regressions establish compatibility and scheduling behavior; they do not establish image quality or GPU memory fit.

## Previous validation

# A.I. Image & Video Studio 1.5.1: token field guidance

The FLUX 3 model card now says "Enter a read token in Settings." Its help text, download-access error and README point to the existing Optional Hugging Face token field in Settings. Model installation remains in Models. JavaScript syntax and focused wording/location checks passed. No model or media-generation test was started for this text-only update.

## Previous 1.5.0 validation

# A.I. Image & Video Studio 1.5.0: FLUX 3 Image Klein

- All 97 automated regressions passed: `tests-1.5.0-final.log`. New coverage verifies the distinct distilled FLUX 3 recipe and VAE path, ten-reference edits with masks and adapter chains, FLUX.2/FLUX 3 LoRA separation, gated-download preflight, engine readiness/routing, archive traversal/cancellation, failed-install preservation and namespace-package readiness. Two native-close regressions confirm an intentional shutdown does not open a startup-error dialog and a genuine host failure still reports an error.
- The pinned separate ComfyUI 0.41.0 engine and its isolated comfy-aimdo 0.5.6 dependency were installed into a workspace validation profile. The engine's CPU probe succeeded without loading model weights. The CPU-only probe disables Kitchen's GPU-capability check; normal model execution retains its GPU backend. Original runtime packages and source were not upgraded. Evidence: `flux3-engine-install-validation.log` and the isolated install log.
- Four workflows passed native typed-graph validation against the new engine: text-to-image, text-to-image with two LoRAs, single-source instruction editing, and ten-reference masked editing with two LoRAs. Loader menus used fixture names; no graph executed, no checkpoint loaded and CUDA remained uninitialized. Evidence: `flux3-workflow-validation-1.5.0.json` and its log. This does not establish model output quality, performance or memory fit.
- App/native-host/setup builds passed. JavaScript syntax checks passed. Protected installed API state confirms the FLUX 3 model card metadata, Hugging Face access link, image/edit capabilities, ten-reference limit and twelve independent LoRA targets. Evidence: `flux3-installed-api-validation-1.5.0.json`.
- A real browser/native visual UI check could not run: the computer-use kernels failed with OS error 3. A separate DOM-test dependency fetch also failed on registry connectivity. No rendered UI or DOM-interaction pass is claimed for this release; the previously validated layout is retained and the new model uses its existing controls.
- The guarded app-only update preserved all 38 protected file hashes, including settings, queue, adapters and media. The library retained fifteen images and one video. Evidence: `upgrade-1.5.0-validation.json`. The old build's idle leftover launchers were closed only after checking identities, absent backend, no running queue item and no attached child render. The final build includes the intentional-close error-dialog fix.
- The optional pack uses the official gated distilled INT8 transformer, INT8 Qwen3-VL encoder and VAE, about 11.0 GB of downloads. The VAE is saved under a unique filename to preserve existing FLUX.2 weights. Engine source and isolated dependency add about 14 MB. No Hugging Face login was cached, so the model weights were not downloaded. The installer/UI explains requesting access and entering a read token, used only for that operation. The optional prompt upsampler and Base checkpoint are excluded.
- Model, VAE, encoder, engine archive and dependency wheel are pinned by revision, size and SHA-256 in assets/packs.json and assets/engines.json. FLUX 3 weights retain the FLUX Kommunity License; engine and dependency licenses remain separate from the app's MIT source license.

No AI image or video was generated for this update. FLUX 3 inference, LoRA appearance, speed and GPU memory fit remain untested; generation testing requires the user's explicit permission. Studio outputs retain the current 256–1536 pixel range; a graphical bounding-box editor is not included.

## Previous 1.4.0 validation

# A.I. Image & Video Studio 1.4.0: queue, removal and optional enhancement

- All 86 automated regressions passed in `tests-1.4.0-final.log`. New cases cover priority/FIFO ordering, mixed image/video/enhancement scheduling, waiting-job editing, cancellation and continuation, failure pausing, original-media preservation, seed/output/LoRA snapshots, mask persistence, interrupted recovery, queue/model removal guards, shared/partial dependency retention, stale/path rejection, Qwen 2.1 conditioning and adapter chaining, dimension/nonfinite option bounds, private RTX output paths, and SDK install/import failure handling with no dependency replacement.
- Seventeen image/editor/video/enhancement graphs passed CPU-only typed validation against installed ComfyUI v0.39.0. Loader menus were populated with catalog/fixture filenames; no weights were loaded and no graph ran. Evidence: `workflow-validation-1.4.0.json`. Qwen 2.1 uses native `TextEncodeQwenImage21` source-image conditioning. This establishes graph structure, not inference quality or GPU memory fit.
- In an isolated profile with inference blocked, the UI queued mixed image/video jobs while paused, changed priority order, edited waiting video settings, cancelled jobs into history, queued and reopened a library image enhancement with its source, and previewed model removal. The new Queue/Upscale pages had no page-level overflow at 900x640 and 1280x720; main controls remained visible and advanced settings scroll internally. Browser console warnings/errors were empty. Evidence: `ui-validation-1.4.0.json`. The inference-blocked log remained absent.
- JavaScript syntax checks passed for both studio scripts. App, native host and setup builds passed: `build-1.4.0.log`. Setup retains selectable application/data paths and optional desktop/Start menu shortcuts, with C:\Program Files\AI Image & Video Studio as default.
- The guarded app-only update to I:\AI Image & Video Studio passed after fresh idle/process checks. Installed executable SHA-256 matched the build. All 15 protected file hashes stayed unchanged; four images and one video remain. Evidence: `upgrade-1.4.0-validation.json`. The final native window visibly opened with v1.4.0 and the new tabs. Native interaction was then stopped with Escape; the app was left open.
- RTX pipeline and SDK/FFmpeg wheels are pinned by revision, size and SHA-256. Installation uses local verified wheels with `--no-index --no-deps`; the ready marker follows an import check. The worker uses a private output directory to keep upstream temporary cleanup away from user folders, and global ComfyUI custom nodes remain disabled. Dependency installation failure handling and output preservation were mocked in regressions; actual SDK installation and GPU video enhancement were not run.
- Qwen-Image 2.1 and the author's hash-matched detail LoRA are an optional approximately 17.4 GB pack. The separate RTX component requires approximately 467 MB of downloads. The app-only update did not install either component. Qwen 2.1 weights use the Qwen Research License; the NVIDIA SDK retains vendor terms. The app's MIT license does not apply to those components.

No AI images or videos were generated for this release. Actual new-enhancer output quality, driver/encoder compatibility, speed and memory fit remain untested. Inference testing still requires the user's explicit permission.

## Previous 1.3.1 validation

# A.I. Image & Video Studio 1.3.1: LoRAs for every model

- All 66 automated regression tests passed: `tests-1.3.1.log`. The eight new regressions cover all ten targets, shared SDXL storage with independent selections, wrong-library rejection, adapter chaining, model/text encoder strengths, editor masks/references, saved-selection migration, and generation dispatch using each model's saved adapters.
- Sixteen image, masked editor and video graphs with two adapters each passed CPU-only validation against the installed ComfyUI v0.39.0 node schemas. Loader filename menus were supplied with catalog/test names. No model weights were loaded and no graphs were executed. Evidence: `lora-workflow-validation-1.3.1.json` and its log. This establishes graph structure and typed connections, not compatibility with arbitrary trained adapter weights or inference quality.
- The packaged UI was checked using an isolated profile and synthetic adapter fixtures. All ten targets appear in the dedicated LoRAs tab; CivitAI and model-specific Hugging Face links have the expected HTTPS destinations. Juggernaut and DreamShaper see the same SDXL file but retain separate enabled selections and strengths. Switching away and back preserves unsaved drafts. Legacy Wan 1.3B strength 0.65 remained unchanged after saving Wan 2.2 strength 0.8. Generator shortcuts open the correct target and show its saved enabled count.
- A scoped Wan 2.2 import through the protected API succeeded and appeared only in its compatible library. Source files stayed unchanged. The native host compiled successfully and opened the final interface; an actual native file-dialog import and external-browser launch were not exercised in this validation.
- At 900 x 640, the LoRAs tab has no page-level overflow; Download LoRA, Disable all and Save selection remain visible. No browser console warnings or errors were recorded. Temporary viewport overrides were reset.
- App and installer builds passed. The installer keeps the existing selectable application/data folders and optional shortcuts. No LoRA weights are bundled or automatically downloaded. Adapter files require matching the exact model version described in the tab; control and acceleration adapters may need another workflow.
- The guarded app-only update to I:\AI Image & Video Studio passed. The installed executable SHA-256 matches the build and the native app reopened as 1.3.1 with ten LoRA targets. Hashes of all eleven protected settings/media/adapter files remained unchanged; the library retained two images and one video. Evidence: `upgrade-1.3.1-validation.json`.
- No AI image or video generation was started for this update. New adapter inference tests still require user permission. Synthetic fixtures remain isolated from the user's installation and source package.

## Previous 1.3.0 validation

# A.I. Image & Video Studio 1.3.0: generators, editor and shared library

- All 58 automated regression tests passed in the final run: `outputs/tests-1.3.0-final.log`. Coverage includes complete-library pagination/search, source preservation/lineage, reference compatibility, RGB masks, model recipes, deduplicated shared downloads, LoRAs, installation paths, authentication and engine timeout/crash behavior.
- Eleven generation/editing graphs passed CPU-only validation against the installed ComfyUI v0.39.0 node schemas. Catalog filenames were supplied in loader menus without loading model weights. This confirms typed graph structure, required inputs and connections, not inference quality or memory fit. Evidence: `workflow-validation-1.3.0.json`.
- Actual CPU media checks passed for pixel-exact crop/resize output, unchanged source SHA-256, video frame extraction at 0.5 seconds from the existing robot test clip, 256 x 256 video thumbnails, empty-mask rejection and out-of-range timestamp rejection. Evidence: `media-validation-1.3.0.json`.
- The native Windows host opened the new logo/navigation/layout. Detailed UI interactions were then checked in a temporary background browser against the same isolated local backend. No production render was interrupted. No AI image/video was generated.
- UI checks passed for square image/video thumbnails, image-to-editor handoff, painted mask strokes, inline mask help, two extra reference images, CPU crop saving with a separate 256 x 256 result, and extracting an existing robot video frame directly into the image-to-video tool. No browser console errors were observed.
- Responsive UI checks at 900 x 640, 1280 x 720 and 1920 x 1080 found no page-level overflow and confirmed visible main action buttons. Advanced controls and library contents scroll internally. The installed native Fullscreen button was also verified at 3440 x 1440, and F11 restored the normal window with its title bar. Evidence: `ui-validation-1.3.0.json`.
- The packaged installer was visually checked with the complete logo, C:\Program Files\AI Image & Video Studio default, separate I: data folder, optional desktop/Start menu shortcuts and question-mark help. It was closed without starting another installation. See `installer-1.3.0-preview.jpg`.
- The supplied complete logo is used at the top of the app and installer. Taglines were removed; pages have brief factual descriptions. The installer keeps C:\Program Files\AI Image & Video Studio as its default, a separate data/models selector, and optional desktop/Start menu shortcuts.
- New model weights are optional downloads through setup or Models. About 80 GB of unique files is needed for the new families plus Qwen Image Edit, excluding Juggernaut if missing. We have not run inference with these new image/editor checkpoints: new generation tests require explicit user approval. Large Qwen models still depend on available GPU/RAM/committed memory.

- Final app-only update to I:\AI Image & Video Studio passed. The installed executable SHA-256 matches the build; the app reopened as 1.3.0 with two preserved images and one preserved video. Existing source media hashes stayed unchanged. The base NSFW Wan runtime is ready; the nine optional packs remain available to download in Models. See `upgrade-1.3.0-validation.json` and `studio-1.3.0-preview.jpg`.

## Earlier validation records

# A.I. Image & Video Studio 1.2.2: installation folder and supplied logo

- The default app folder is now C:\Program Files\AI Image & Video Studio, including when a previous installation was on I:. Browse and optional desktop/Start menu shortcuts remain available.
- Only copying/removing the application files under Program Files uses a Windows administrator helper. Models, runtime, settings, output and WebView2 profile use a separately selectable writable data folder. Per-user registry registration maps the installed app to this folder. Existing writable studio data can be reused without moving files. Other users fall back to their own Local AppData folder.
- The exact supplied JPEG was converted to a lossless PNG for display. The complete image appears above every app page in a responsive white header, and at the top of setup at its original aspect ratio. Setup scrolls when necessary and keeps its action buttons visible in a fixed footer.
- All 42 automated checks passed, including seven new regressions for the Program Files default, per-user data resolution, reuse, preserving personal data, and cancelled elevation. Python compilation and both PyInstaller builds passed.
- The packaged 1.2.2 app opened its native host, served its branded HTML and returned logo bytes identical to the packaged source asset. The installer opened with its normal window title; its source GUI loaded the 238 x 144 logo and was checked for the correct default path and optional shortcuts. See branding-validation-1.2.2.json.
- Native screenshot inspection was unavailable: the computer-use Node kernel failed to write its assets with OS error 3, including after reset. No installation, UAC approval, model downloads or media generation were started for this update. A full Program Files installation has not been executed by this validation.

## Earlier 1.2.1 memory and duration update

## User-approved LTX-2 GPU test, 14 October 2026

- Executed the installed 1.2.1 binary in a separate diagnostic profile, sharing the existing models. Text-to-video: a red toy robot in a greenhouse, 512 x 320, 33 frames at 24 fps, 8 distilled steps, seed 20261014, audio enabled. No extra generation tests were submitted.
- The full render succeeded without error 1455. Generation took 993.7 seconds; including engine startup, the test took about 18 minutes. First loading and early sampling were slow on the Seagate USB hard drive. The final four sampler steps took approximately 1.6 seconds each after the weights had loaded.
- PyAV decoded all 33 H.264 frames and the AAC audio track. Video duration: 1.375 seconds; audio: 1.33 seconds, 24 kHz. The preview frames show a recognizable red robot and greenhouse, rather than undecoded noise or basic color blocks. The audio is very quiet (about -71 dBFS RMS); audio-track decodability does not establish useful sound quality.
- Observed system peaks: GPU memory 14.22 GiB, RAM 18.85 GiB, committed memory 35.82 GiB. The minimum committed-memory headroom was 16.20 GiB. Windows paging configuration was not changed.
- SHA-256 hashes of the user's installed settings.json, library.json and images.json remained unchanged. The diagnostic app and its engine exited after the test. Evidence: ltx-gpu-validation-1.2.1.json, ltx-gpu-test-1.2.1/logs/engine.log and LTX-2-test-1.2.1.mp4.
- This establishes one short text-to-video render on the current hardware. Longer videos, LTX-2 image-to-video, and meaningful audio quality remain unverified by this test.

## Implementation and earlier checks

- Diagnosed the user's error 1455 from the installed LTX-2 audio-VAE loader, in safetensors.safe_open, before sampling began. The 1.2.0 launch path forced --disable-dynamic-vram / --lowvram for LTX-2, selecting legacy full-checkpoint memory mapping.
- Corrected LTX-2 to explicitly retain --enable-dynamic-vram and disable pinned memory. Its Low VRAM setting adds one GB of GPU headroom. Other models retain their existing memory behavior. Engine reuse is keyed by model as well as memory mode and output folder.
- CPU-only native-loader validation opened three simultaneous views of the actual 27,078,716,346-byte checkpoint, with 6,404 tensor entries per view. The observed system commit increase was 265,826,304 bytes, about 254 MB. No model inference or media generation was performed. See ltx-memory-validation-1.2.1.json.
- Added clear error-1455 guidance and Windows committed-memory used/limit in the live usage bar. Windows paging settings were not changed.
- Added duration choices for 5/10/15/20 seconds and custom frame counts through 481. Duration labels use the actual fps and choices honor model frame alignment. Larger renders remain subject to real GPU/memory capacity and temporal-coherence limitations.
- Thirteen focused creative-mode, memory-loader, error-guidance and long-frame regressions passed. JavaScript and Python syntax checks passed. Full new-duration video rendering remains untested pending user permission.

## Installed 1.2.1 verification

- The headless app-only installer completed successfully. The installed executable hash matches the final build, and the installation marker reports 1.2.1. Settings, image library and video library hashes were preserved. No generation or Windows paging changes were performed.
- Native window inspection timed out, so the duration controls still require an interactive check. The checkpoint mapping and regression checks above completed successfully.

## Previous release validation

# A.I. Image & Video Studio 1.2.0 validation

- Windows app and installer built successfully. Name, native window title, new shortcuts and installer identify A.I. Image & Video Studio.
- All 32 automated cases passed across the final run and a focused retry: 31 passed in the final batch; one loopback download hit a connection reset and passed its isolated retry. Ten focused creative-mode regressions and seven LoRA regressions also passed after the final settings-preservation changes.
- Seven native workflows passed the installed ComfyUI's CPU-only validate_prompt: Wan 1.3B text; Wan 2.2 text/image; LTX-2 text/image; Juggernaut XL; DreamShaper XL Turbo. See workflow-validation-1.2.0.json. No graph was executed by that check.
- All four optional model packs downloaded into I:/WanVideoStudio-Validation-1.0.0 and passed their pinned SHA-256 checks. See model-pack-downloads.log. The UI confirmed all four packs ready using the actual files.
- New packaged app opened in an isolated profile with the shared runtime/models. GPU load, VRAM and RAM usage were visually verified and matched backend resource readings.
- Clicking Open video folder in the packaged native UI opened Explorer at the configured profile output folder. This was confirmed by the actual Explorer window title.
- Imported the existing ComfyUI example.png through the protected API. Its normalized PNG appeared in the local image library and was automatically selected in Image → Video with Wan 2.2. Import and decoding use the CPU, not generation.
- The user began using the preview window during validation. It was left open. The agent did not submit an image or video generation job. GPU generation testing of new models remains subject to the user's explicit permission.
- LTX-2 uses the fixed distilled 8-step sigma schedule and CFG 1, its own text/audio/video components, low-VRAM mode and tiled decode. This version uses single-pass generation. Runtime quality, speed and memory fit of LTX-2/Wan 2.2 are not yet established by an agent-triggered render.
- Original installation settings and video library were not overwritten by the isolated UI checks. The preview profile now contains user activity and must be preserved.

## Completed upgrade

- The user generated a Juggernaut image and a Wan 2.2 image-to-video clip in the preview. The video completed successfully in 546 seconds, including initial model loading. These jobs were submitted by the user, not by the agent.
- After explicit permission and completion of the running video, the preview was closed, the final installer was run in app-only upgrade mode, and one new image plus one new video were copied into the installed studio. Original media and settings were preserved, with backup JSON files retained.
- Installed executable SHA-256 matches the final build, the install marker and Windows app registration show version 1.2.0 / A.I. Image & Video Studio, and the final app reopened from I:/WanVideoStudio-Validation-1.0.0.
- Final installed state confirmed all four optional packs ready, one image and four videos in its combined library, and the output folder on I:. The preview files also remain preserved. See upgrade-1.2.0-validation.json.
- Agent-triggered DreamShaper and LTX-2 generation tests remain unperformed pending user permission.

## Previous release validation

# Wan Video Studio validation

## 1.1.0 desktop window and LoRAs

Validated 2026-10-13 on Windows 11, RTX 4080 SUPER 16 GB, driver 616.92.

- Built a native Windows Forms/WebView2 window. Default launch opens no external browser. Existing WebView2 is reused; the signed Microsoft bootstrapper is bundled for machines missing it.
- Upgraded `I:\WanVideoStudio-Validation-1.0.0` to 1.1.0. The installed binary matches the release SHA-256. Settings and video library remained byte-for-byte unchanged; no model files were downloaded again.
- All 22 regression tests passed. Seven cover LoRA import, original-file preservation, duplicate and conflicting-name handling, malformed/truncated-file rejection, selection/strength validation, model/text-encoder chain wiring, HF file-link revision pinning, and concurrent engine cleanup. The seven were rerun after the final settings-isolation fix and passed.
- Visually verified the native window, help overlay, LoRA-manager screen, and native multi-file safetensors picker in the packaged application.
- Imported a small zero-weight test adapter through the packaged app's local API into a separate test profile. The original file was preserved, SHA-256 recorded, and enable/strength controls appeared in the manager. Test adapters were not added to the user's real model installation.
- Verified that closing the desktop window removed its backend instance marker. LoRA selection and close-cleanup evidence is in `desktop-lora-state-validation.json`.
- Both user render sidecars explicitly loaded `wan_1.3B_exp_e14.safetensors` from NSFW-API. The flat-colored result used 12 steps at 512 × 288; the subsequent 40-step 832 × 480 result had normal detail. Quick preview now uses 24 steps, and the UI explicitly labels NSFW-API and E14.

No third-party artistic LoRA was supplied. File import, selection, graph integration, URL metadata and download infrastructure were checked; third-party LoRA appearance was not benchmarked. Adapters still need to match Wan 2.1 T2V 1.3B.

Evidence: `tests-desktop-loras.log`, `tests-loras-final.log`, `desktop-upgrade-validation.json`, `lora-import-validation.json`, and `desktop-lora-state-validation.json`.

## Earlier 1.0.0 model and runtime checks

Validated on 2026-10-13, Windows 11 x64, NVIDIA GeForce RTX 4080 SUPER (16 GB VRAM), driver 616.92, 32 GB system RAM.

## Passed

- Built self-contained Windows application and setup executables with Python 3.14.6 and PyInstaller 6.22.3.
- Downloaded and SHA-256 verified the exact pinned ComfyUI NVIDIA portable archive, epoch-14 checkpoint, FP8 UMT5 encoder and Wan VAE.
- Extracted the runtime and confirmed Python 3.13.14, PyTorch 2.14.0+cu130, working CUDA and H.264 encoding.
- Tested the packaged install and full repair path in `I:\WanVideoStudio-Validation-1.0.0`. Existing Settings remained byte-for-byte unchanged. Installed app matched the built app's SHA-256.
- Created and inspected a temporary Windows shortcut with the correct target and working directory; no desktop or Start menu test shortcuts were left behind.
- Passed 15 focused regression tests. Coverage includes HTTP download resume, servers ignoring Range, replacing same-size corrupted downloads, download cancellation, token removal on cross-host redirects, Wan dimensions/frame constraints, local API session authentication, rejecting foreign origins, video byte ranges, concurrent-operation prevention, atomic settings writes, and help coverage for every option.
- Tested the “?” overlay and Quality preset in the packaged browser UI. Reviewed the installer and application visually at a desktop width, with a narrow layout check as well.
- Generated a real landscape clip through the packaged application's Generate button: 512 × 288, 33 frames, 16 fps, 12 steps, CFG 6, flow shift 8, UniPC/Simple, seed 42. The prompt described a lighthouse and empty coastline. The app reported 124.9 seconds after engine startup and saved the MP4 plus complete JSON metadata.
- Verified the actual MP4 with ffprobe: H.264, 512 × 288, 33 frames, 16/1 fps, 2.0625 seconds. Played it through the local preview UI.
- Verified the direct Windows folder-picker dialog and its existing-folder selection. Background launches explicitly show this interactive dialog. The picker was changed from a separate frozen-process launch to a direct shell dialog.

## Fixes found during validation

- ComfyUI v0.39.0's nested SaveVideo controls require flattened API inputs (`format: mp4`, `format.codec: h264`). Corrected this after the initial render reached export, then verified both cached-frame export and a full packaged render.
- Low VRAM must disable dynamic VRAM in this runtime for `--lowvram` to take effect. The launcher supplies both flags.
- Replaced the slow/hidden frozen folder helper with a directly shown Windows shell dialog.

## Scope

This is a validated short text-to-video render, not an exhaustive quality or performance benchmark. Larger resolutions, longer videos, different GPUs and Low VRAM inference were not benchmarked. AMD, Intel and CPU-only setups are not supported by this NVIDIA release. Uninstall logic was reviewed; removal of the retained model installation was not performed.

Test downloads are retained in the validation installation so they can be reused. The application can be opened directly from `I:\WanVideoStudio-Validation-1.0.0\WanVideoStudio.exe`, or Setup can be rerun against that same folder to avoid downloading another copy. Closing the browser tab leaves the app running; use Exit app to stop it.

Evidence: `tests.log`, `packaged-install-validation.json`, `shortcut-validation.json`, `studio-preview.png`, `installer-preview.png`, `Validation-Coastline.mp4`, and `SHA256SUMS.txt` in this folder.
