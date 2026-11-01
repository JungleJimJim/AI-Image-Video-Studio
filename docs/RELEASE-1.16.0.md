# 1.16.0 — Full OpenJutsu workspace

The OpenJutsu tool hosts the complete upstream editor rather than reimplementing individual workflows. Its interface includes Simple and Advanced character swaps, per-person passes, Montage/Find people, mask checks, object Change/Remove/Add/Background, From picture and relighting, face refinement and colour finishing. Availability of each operation depends on its backend nodes and models.

## Setup

1. Install Studio's base runtime if needed. Open **OpenJutsu** beside Video, or use **Models → OpenJutsu → Open setup**.
2. Click **Install OpenJutsu app**. This downloads verified source/runtime/proxy files and runs `npm ci` against the upstream lockfile before building the production app. Allow 3 GB free for build files. JavaScript package integrity is checked against the upstream lockfile; the source, Node archive and Python wheels have pinned SHA-256 checksums. Existing working installations are retained until the replacement build succeeds.
3. Prepare a **separate local ComfyUI 0.41.2+ backend** following [OpenJutsu's requirements and model list](https://github.com/D3voz/openjutsu#requirements) and [custom-node installation notes](https://github.com/D3voz/openjutsu/blob/7fe118bb5a61fcfac0148e1bfea3dd29884dbf26/CUSTOM_NODES_REPORT.md). This release does **not** automatically install that backend, its nodes or model weights. Studio's regular ComfyUI engine is not sufficient.
4. Save its loopback address (normally `http://127.0.0.1:8188`) and click **Check backend**. This reads registered nodes without loading model weights or submitting inference. Some reported gaps, such as Spectrum, affect optional features only. OpenJutsu performs the more specific node/model check for each selected operation. Registered nodes do not establish dependency health, weight integrity or available GPU memory.
5. Click **Open workspace**. Finish its Welcome & models selection or choose Set up later. Generation starts only through OpenJutsu's own controls.

Upstream reports a 16 GB RTX 4060 Ti with 64 GB system RAM. Studio has not benchmarked the complete workflow. Model requirements, dependencies and their licenses remain those of the upstream projects.

## Queues and files

Starting OpenJutsu pauses Studio's queue and stops Studio's owned generation engine. Studio refuses new generation jobs or queue resumption while the workspace is open. Its jobs run in the separate ComfyUI backend, with OpenJutsu's own progress and cancel controls. Finish or cancel them before stopping the workspace. Stop refuses when that backend reports running or pending jobs. If the backend is unreachable, the web app can still close; Studio leaves its queue paused and reports that backend jobs could not be checked. Inspect ComfyUI before resuming.

Closing Studio stops only the Node app and proxy processes that Studio started. It does not terminate the external ComfyUI service or its jobs. Finish jobs and download results before exiting. Reopening Studio does not auto-start the editor or resume generation.

Sources are selected through OpenJutsu's upload controls. Studio Library originals can be located using **Open folder** or downloaded as copies. Download a finished OpenJutsu video, then click **Import finished video** to copy it into Studio's Library. Source uploads, results and job history remain managed by upstream OpenJutsu/ComfyUI; automatic transfer to Studio's Library and Studio queue editing are not part of this release.

## Isolation and attribution

- OpenJutsu revision: `7fe118bb5a61fcfac0148e1bfea3dd29884dbf26`, by D3voz, MIT license.
- Portable Node.js 24.18.0 and `comfy-api-proxy` 0.1.6 have separate runtime/dependency folders. No global Node, Python, PyTorch, model or custom-node updates are performed.
- App/proxy listen on IPv4 loopback ports. The app reuses its assigned port when available so browser preferences persist; an occupied port gets a new assignment. The proxy uses a random port and requires an ephemeral bearer token. Its durable job state stays in `extensions/openjutsu/proxy-state`.
- The integration adapts upstream framing headers to permit only the exact owning Studio origin at runtime. Other parents are denied. Upstream API origin/authentication checks stay in place. The Studio API token is never passed into the editor or its URL, and the frame sends no parent referrer.
- Source and dependency licenses remain in the downloaded installation; the app includes `openjutsu-NOTICES.txt`.

## Validation

339 Python regression tests passed, including authenticated HTTP routes, local URL restrictions, queue isolation, component framing and process lifecycle checks. Four existing JavaScript regression checks and the new script's syntax check also passed.

The full upstream app installed and built successfully with its isolated runtime/proxy. Its relocated production build started, its protected proxy rejected unauthenticated job access, and the editor rendered inside Studio in a real browser. Object editing, From picture and the relighting presets were inspected; an 800-pixel-wide layout check found no page overflow. The final frozen Studio executable started successfully in an isolated data folder, served the exact new UI script and included all component resources. App and installer builds passed.

No model weights were loaded and no generation was run. AI generation quality, GPU memory use and all-mode inference remain unvalidated. The installed Studio, its models, settings and Library were not upgraded by these checks. Test app/runtime/cache files were removed after validation.

Startup exceptions now also write `logs/startup.log` when possible; headless startup failures exit instead of waiting on a hidden error dialog.
