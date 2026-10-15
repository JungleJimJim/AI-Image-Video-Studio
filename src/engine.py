"""Owned ComfyUI process and model-specific image/video workflows."""
import json
from pathlib import Path
import secrets
import re
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request

from common import CREATE_NO_WINDOW, comfy_root, runtime_python
from downloads import Cancelled


DEFAULTS = {
    "prompt": "", "negative": "blurry, low quality, artifacts, distorted, subtitles, watermark, static image",
    "preset": "balanced", "width": 832, "height": 480, "frames": 49,
    "fps": 16, "steps": 30, "cfg": 6.0, "shift": 8.0,
    "seed": "", "randomize_seed": True, "sampler": "uni_pc", "scheduler": "simple", "memory": "auto", "loras": [],
    "model": "wan13", "mode": "text", "source_image": "", "audio": True,
}
MAX_VIDEO_FRAMES = 481
HISTORY_RESPONSE_GRACE = 120


def validate_options(raw):
    options = {**DEFAULTS, **{k: v for k, v in raw.items() if k in DEFAULTS}}
    if options['model'] == 'ltx2' and options['scheduler'] == 'distilled':
        options['scheduler'] = 'simple'  # Accept the saved recipe when reusing a render.
    if options['model'] not in ('wan13', 'wan22', 'ltx2') or options['mode'] not in ('text', 'image'):
        raise ValueError('Choose a supported video model and input mode.')
    if options['mode'] == 'image' and options['model'] == 'wan13':
        raise ValueError('NSFW Wan 1.3B is text-only. Choose Wan 2.2 or LTX-2 for image-to-video.')
    if not isinstance(options['source_image'], str) or len(options['source_image']) > 100:
        raise ValueError('Choose an image from the image library.')
    if options['mode'] == 'image' and not options['source_image']:
        raise ValueError('Choose or generate a starting image first.')
    if not isinstance(options['randomize_seed'], bool):
        raise ValueError('Choose whether to prepare a new seed for each job.')
    if not isinstance(options['audio'], bool):
        raise ValueError('Audio must be enabled or disabled.')
    for name, lo, hi in [("width", 144, 1024), ("height", 144, 1024), ("frames", 9, MAX_VIDEO_FRAMES),
                         ("fps", 8, 30), ("steps", 1, 80)]:
        try:
            number = float(options[name])
            if not number.is_integer() or not lo <= number <= hi:
                raise ValueError()
            options[name] = int(number)
        except (TypeError, ValueError, OverflowError):
            raise ValueError(f"{name.capitalize()} must be a whole number from {lo} to {hi}.") from None
    if options["width"] % 16 or options["height"] % 16:
        raise ValueError("Width and height must be multiples of 16.")
    if options["frames"] % 4 != 1:
        raise ValueError("Frame count must be 4n + 1, such as 33, 49 or 81.")
    if options['model'] == 'ltx2' and (options['width'] % 64 or options['height'] % 64 or options['frames'] % 8 != 1):
        raise ValueError('LTX-2 needs dimensions divisible by 64 and 8n + 1 frames (33, 49, 81, 121).')
    if options['model'] == 'wan22' and (options['width'] % 32 or options['height'] % 32):
        raise ValueError('Wan 2.2 needs dimensions divisible by 32.')
    for name, lo, hi in [("cfg", 1, 15), ("shift", 1, 15)]:
        try:
            options[name] = float(options[name])
            if not lo <= options[name] <= hi:
                raise ValueError()
        except (TypeError, ValueError, OverflowError):
            raise ValueError(f"{name.upper()} must be between {lo} and {hi}.") from None
    for name, choices in {"sampler": ("uni_pc", "euler", "dpmpp_2m"),
                          "scheduler": ("simple", "normal", "sgm_uniform"),
                          "memory": ("auto", "low")}.items():
        if options[name] not in choices:
            raise ValueError(f"Unsupported {name}.")
    for name in ("prompt", "negative"):
        if not isinstance(options[name], str) or len(options[name]) > 10000:
            raise ValueError(f"{name.capitalize()} must be text under 10,000 characters.")
    if not options["prompt"].strip():
        raise ValueError("Describe the video you want to create first.")
    seed = str(options["seed"]).strip()
    if seed in ("", "-1"):
        options["seed"] = secrets.randbelow(2**53)
    else:
        try:
            options["seed"] = int(seed)
            if not 0 <= options["seed"] <= 2**53 - 1:
                raise ValueError()
        except ValueError:
            raise ValueError("Seed must be empty for random, or a whole number from 0 to 9007199254740991.") from None
    if options['model'] == 'ltx2':
        options.update(steps=8, cfg=1.0, sampler='euler', scheduler='distilled', shift=1.0, memory='low')
    return options


def build_workflow(o, prefix):
    if o.get('model') == 'ltx2':
        from workflows import ltx_workflow
        return ltx_workflow(o, prefix)
    if o.get('model') == 'wan22':
        from workflows import wan22_workflow
        return wan22_workflow(o, prefix)
    def node(kind, **inputs):
        return {"class_type": kind, "inputs": inputs}
    graph = {
        "1": node("UNETLoader", unet_name="wan_1.3B_exp_e14.safetensors", weight_dtype="default"),
        "2": node("CLIPLoader", clip_name="umt5_xxl_fp8_e4m3fn_scaled.safetensors", type="wan", device="default"),
        "3": node("VAELoader", vae_name="wan_2.1_vae.safetensors"),
        "4": node("CLIPTextEncode", text=o["prompt"], clip=["2", 0]),
        "5": node("CLIPTextEncode", text=o["negative"], clip=["2", 0]),
        "6": node("EmptyHunyuanLatentVideo", width=o["width"], height=o["height"], length=o["frames"], batch_size=1),
        "7": node("ModelSamplingSD3", model=["1", 0], shift=o["shift"]),
        "8": node("KSampler", model=["7", 0], positive=["4", 0], negative=["5", 0], latent_image=["6", 0],
                  seed=o["seed"], steps=o["steps"], cfg=o["cfg"], sampler_name=o["sampler"], scheduler=o["scheduler"], denoise=1.0),
        "9": node("VAEDecode", samples=["8", 0], vae=["3", 0]),
        "10": node("CreateVideo", images=["9", 0], fps=o["fps"]),
        # ComfyUI dynamic combos arrive flattened over its prompt API, then normalize to dictionaries.
        "11": node("SaveVideo", video=["10", 0], filename_prefix=prefix, format="mp4", **{"format.codec": "h264"}),
    }
    from loras import apply_to_graph
    return apply_to_graph(graph, o, ['1',0], ['2',0], start=20)


def engine_command(root, port, output, memory, model='wan13'):
    if model=='flux3':
        from engine_support import command as optional_command
        command=optional_command(root,'flux3')
    else:command=[str(runtime_python(root)), '-s', str(comfy_root(root) / 'main.py')]
    command += ['--windows-standalone-build', '--listen', '127.0.0.1', '--port', str(port),
               '--disable-auto-launch', '--disable-all-custom-nodes', '--output-directory', str(output)]
    if model in ('ltx2', 'wan22', 'zimage', 'fluxklein', 'qwenimage', 'qwenedit', 'qwen21', 'flux3'):
        # Keep the native disk-backed loader. Legacy low-VRAM mode disables it
        # and maps entire checkpoints through safetensors on Windows. This also
        # triggered a native access violation while loading Wan 2.2 in low mode.
        command += ['--enable-dynamic-vram', '--disable-pinned-memory']
        if memory == 'low':
            command += ['--vram-headroom', '1']
    elif memory == 'low':
        command += ['--disable-dynamic-vram', '--lowvram']
    return command


def explain_engine_error(detail):
    if '1455' in detail or 'paging file is too small' in detail.lower():
        return ('Windows could not reserve enough committed memory while loading the model (error 1455). '
                'This is RAM plus paging-file capacity, not just GPU memory. '
                'LTX-2 and Wan 2.2 now use the native disk-backed loader to reduce this overhead. '
                'Close memory-heavy applications and retry. If it persists, the Windows paging file may need more capacity on a drive with free space. '
                'The app has not changed your Windows paging settings.')
    if 'out of memory' in detail.lower():
        return detail + '\nTry Quick preview or a shorter clip, and close other GPU applications.'
    if 'access violation' in detail.lower():
        return ('The local video engine crashed while accessing model memory (Windows access violation). '
                'Wan 2.2 now uses the native disk-backed loader instead of the legacy low-VRAM loader. '
                'Check that the model drive is connected. Open logs/engine.log for the crash details.')
    return detail


class Engine:
    def __init__(self, root, report):
        self.root = Path(root)
        self.report = report
        self.process = None
        self.port = None
        self.signature = None
        self.log_handle = None
        self.cancel = threading.Event()
        self.stop_lock = threading.Lock()

    def request(self, path, data=None, timeout=15):
        encoded = None if data is None else json.dumps(data).encode()
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=encoded, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Video engine rejected the request: {detail[:4000]}") from None

    def raise_if_failed(self, inspect_log=False):
        process = self.process
        code = process.poll() if process else 'not running'
        if code is None and not inspect_log:
            return
        log = self.root / 'logs/engine.log'
        try:
            with log.open('rb') as source:
                source.seek(max(0, log.stat().st_size - 6000))
                detail = source.read().decode('utf-8', errors='replace')
        except OSError:
            detail = ''
        fatal = 'Windows fatal exception:' in detail or 'Fatal Python error:' in detail
        if code is None and not fatal:
            return
        if code is None:
            self.stop()
        message = explain_engine_error(detail)
        reason = 'The local video engine crashed.\n' if fatal else f'The local video engine stopped unexpectedly (exit code {code}).\n'
        raise RuntimeError(reason + message[-4000:])

    def wait_for_history(self, prompt_id):
        # Only retry the read. Reposting /prompt could generate duplicate videos.
        deadline = time.monotonic() + HISTORY_RESPONSE_GRACE
        while True:
            if self.cancel.is_set():
                self.stop()
                raise Cancelled('Generation cancelled. Existing videos are preserved.')
            self.raise_if_failed()
            try:
                response = self.request('/history/' + prompt_id, timeout=10)
                if not isinstance(response, dict):
                    raise ValueError('Invalid engine history response')
                return response.get(prompt_id)
            except (OSError, urllib.error.URLError, ValueError) as error:
                if self.cancel.is_set():
                    self.stop()
                    raise Cancelled('Generation cancelled. Existing videos are preserved.') from None
                self.raise_if_failed(inspect_log=True)
                if time.monotonic() >= deadline:
                    self.stop()
                    raise RuntimeError('The local video engine did not respond for two minutes. '
                        'Its job has been stopped to prevent an untracked background render. '
                        'Open logs/engine.log for details, then retry.') from error
                self.report('Waiting for the local video engine to respond. Model loading can temporarily delay updates…', None)
                self.cancel.wait(.8)

    def stop(self):
        with self.stop_lock:
            if self.process and self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=10)
            self.process = None
            if self.log_handle:
                self.log_handle.close()
                self.log_handle = None

    def start(self, memory, output, model='wan13'):
        signature = (memory, str(output), model)
        if self.process and self.process.poll() is None and self.signature == signature:
            return
        self.stop()
        self.signature = signature
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            self.port = sock.getsockname()[1]
        log = self.root / "logs" / "engine.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        self.log_handle = log.open("w", encoding="utf-8")
        command = engine_command(self.root, self.port, output, memory, model)
        self.report("Starting the local video engine…", None)
        self.process = subprocess.Popen(command, cwd=comfy_root(self.root), stdout=self.log_handle,
                                        stderr=subprocess.STDOUT, creationflags=CREATE_NO_WINDOW)
        deadline = time.monotonic() + 240
        while time.monotonic() < deadline:
            if self.cancel.is_set():
                self.stop()
                raise Cancelled("Generation cancelled.")
            if self.process.poll() is not None:
                raise RuntimeError("The video engine could not start.\n" + log.read_text(encoding="utf-8", errors="replace")[-4000:])
            try:
                self.request("/system_stats", timeout=2)
                self.report("Video engine ready. Preparing the model…", None)
                return
            except (OSError, RuntimeError, ValueError):
                self.cancel.wait(.5)
        self.stop()
        raise RuntimeError("Video engine startup took too long. Open logs/engine.log for details.")

    def generate(self, options, output, kind='video'):
        try:
            return self._generate(options, output, kind)
        except Exception:
            # A failed request must not leave a render running behind an idle UI.
            self.stop()
            raise

    def _generate(self, options, output, kind='video'):
        output = Path(output).expanduser().resolve()
        output.mkdir(parents=True, exist_ok=True)
        self.start(options['memory'], output, options.get('model', 'wan13'))
        prefix = ({'edit':'Edit_', 'image':'Image_', 'enhance':'Enhanced_'}.get(kind, 'Video_')) + time.strftime("%Y%m%d_%H%M%S") + "_" + secrets.token_hex(3)
        if kind == 'enhance':
            from enhancements import image_workflow
            workflow = image_workflow(options, prefix)
        elif kind in ('image', 'edit'):
            from workflows import image_workflow, edit_workflow
            workflow = edit_workflow(options, prefix) if kind == 'edit' else image_workflow(options, prefix)
        else:
            workflow = build_workflow(options, prefix)
        loaders = {node['class_type'] for node in workflow.values()
                   if node['class_type'] in ('LoraLoader', 'LoraLoaderModelOnly')}
        if loaders:
            from loras import resolve_engine_names
            schemas = {}
            for loader in sorted(loaders):
                schemas.update(self.request('/object_info/' + loader))
            resolve_engine_names(workflow, schemas)
        extension = '.png' if kind in ('image', 'edit', 'enhance') else '.mp4'
        logfile = self.root / "logs" / "engine.log"
        log_start = logfile.stat().st_size
        try:
            submitted = self.request("/prompt", {"prompt": workflow, "client_id": secrets.token_hex(16)}, timeout=60)
        except (OSError, urllib.error.URLError, ValueError) as error:
            self.raise_if_failed(inspect_log=True)
            self.stop()
            raise RuntimeError('The local engine did not acknowledge the video job. '
                'It was stopped safely; no duplicate job was submitted. Open logs/engine.log and retry.') from error
        if submitted.get("node_errors") or "prompt_id" not in submitted:
            raise RuntimeError("Workflow validation failed: " + json.dumps(submitted)[:4000])
        prompt_id = submitted["prompt_id"]
        started = time.monotonic()
        # Engine log progress is supplied by PyTorch's sampler; polling history avoids extra dependencies.
        while True:
            if self.cancel.wait(.8):
                try:
                    self.request("/interrupt", {})
                except (OSError, RuntimeError):
                    pass
                self.stop()
                raise Cancelled("Generation cancelled. Existing videos are preserved.")
            self.raise_if_failed()
            history = self.wait_for_history(prompt_id)
            elapsed = int(time.monotonic() - started)
            with logfile.open("rb") as log:
                log.seek(max(log_start, logfile.stat().st_size - 12000))
                tail = log.read().decode("utf-8", errors="replace")
            progress = re.findall(r"(\d+)%\|[^\r\n]*?\s(\d+)/(\d+)\s", tail)
            if progress:
                percent, step, total = map(int, progress[-1])
                label = f"Sampling · step {step}/{total}" if percent < 100 else ('Saving the PNG image…' if kind == 'image' else 'Encoding the MP4 video…')
                self.report(f"{label} · {elapsed // 60:02d}:{elapsed % 60:02d} elapsed", min(.95, percent / 100 * .9))
            else:
                self.report(f"Loading models and preparing {kind} · {elapsed // 60:02d}:{elapsed % 60:02d} elapsed", None)
            if history:
                if history.get("status", {}).get("status_str") == "error":
                    errors = [x[1] for x in history["status"].get("messages", []) if x[0] == "execution_error"]
                    if errors:
                        detail = errors[-1].get("exception_message", str(errors[-1]))
                        raise RuntimeError(explain_engine_error(detail))
                    raise RuntimeError("Generation failed. See logs/engine.log for details.")
                if history.get("status", {}).get("completed"):
                    files = []
                    for result in history.get("outputs", {}).values():
                        for records in result.values():
                            if isinstance(records, list):
                                for record in records:
                                    if isinstance(record, dict) and str(record.get("filename", "")).endswith(extension):
                                        target = (output / record.get("subfolder", "") / record["filename"]).resolve()
                                        if target.is_relative_to(output) and target.is_file():
                                            files.append(target)
                    if not files:
                        # Some upstream video node versions report a different output UI shape.
                        files = sorted(output.glob(prefix + '*' + extension))
                    if not files:
                        raise RuntimeError(f'The engine finished but did not produce a {extension} file. See logs/engine.log.')
                    return files[0], workflow, round(time.monotonic() - started, 1)
