"""Resumable, checksum-verified installer for the pinned upstream distribution."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from common import (CREATE_NO_WINDOW, atomic_json, comfy_root, existing_parent,
                    manifest, resource, runtime_python, runtime_root)


class Cancelled(Exception):
    pass


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected and urllib.parse.urlsplit(req.full_url).hostname != urllib.parse.urlsplit(newurl).hostname:
            redirected.remove_header("Authorization")
        return redirected


def checksum(path, cancel=None, progress=None):
    digest = hashlib.sha256()
    total = Path(path).stat().st_size
    done = 0
    with open(path, "rb") as src:
        while chunk := src.read(8 * 1024 * 1024):
            if cancel and cancel.is_set():
                raise Cancelled("Cancelled. Completed downloads are kept for the next attempt.")
            digest.update(chunk)
            done += len(chunk)
            if progress:
                progress(done, total)
    return digest.hexdigest()


def download(spec, destination, report, cancel, token=""):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    label = spec["label"]
    size = spec["size"]
    report(f"Checking {label}", 0)
    if destination.exists() and destination.stat().st_size == size:
        if checksum(destination, cancel, lambda a, b: report(f"Verifying {label}", a / b)) == spec["sha256"]:
            report(f"Already verified: {label}", 1)
            return destination
    partial = destination.with_suffix(destination.suffix + ".part")
    opener = urllib.request.build_opener(SafeRedirect())
    for attempt in range(4):
        if cancel.is_set():
            raise Cancelled("Cancelled. Downloads can be resumed.")
        offset = partial.stat().st_size if partial.exists() else 0
        if offset >= size:
            if offset == size and checksum(partial, cancel) == spec["sha256"]:
                os.replace(partial, destination)
                return destination
            partial.unlink()
            offset = 0
        headers = {"User-Agent": "WanVideoStudio/1.0", "Accept-Encoding": "identity"}
        if offset:
            headers["Range"] = f"bytes={offset}-"
        if token and urllib.parse.urlsplit(spec["url"]).hostname == "huggingface.co":
            headers["Authorization"] = "Bearer " + token
        try:
            request = urllib.request.Request(spec["url"], headers=headers)
            with opener.open(request, timeout=35) as response:
                if offset and response.status != 206:
                    offset = 0  # Server ignored Range: restart rather than append a full file.
                if response.status == 206:
                    content_range = response.headers.get("Content-Range", "")
                    if not content_range.startswith(f"bytes {offset}-"):
                        raise OSError("The server returned an unexpected download range.")
                mode = "ab" if offset else "wb"
                done = offset
                last = 0.0
                start = time.monotonic()
                with partial.open(mode) as out:
                    while chunk := response.read(1024 * 1024):
                        if cancel.is_set():
                            raise Cancelled("Cancelled. Downloads can be resumed.")
                        out.write(chunk)
                        done += len(chunk)
                        now = time.monotonic()
                        if now - last >= 0.3:
                            rate = (done - offset) / max(now - start, .01) / 1024**2
                            report(f"{label}: {done / 1024**3:.2f} / {size / 1024**3:.2f} GB · {rate:.1f} MB/s", min(done / size, 1))
                            last = now
            if partial.stat().st_size != size:
                raise OSError("The download ended early; resuming automatically.")
            report(f"Verifying {label} (SHA-256)", 0)
            if checksum(partial, cancel, lambda a, b: report(f"Verifying {label} (SHA-256)", a / b)) != spec["sha256"]:
                partial.unlink()
                raise OSError(f"Checksum mismatch for {label}; retrying a clean download.")
            os.replace(partial, destination)
            report(f"Verified {label}", 1)
            return destination
        except urllib.error.HTTPError as error:
            if error.code in (401, 403):
                raise RuntimeError("Access was denied. Open the model page, accept any access conditions, then enter a read-only Hugging Face token and retry.") from None
            if error.code == 404:
                raise RuntimeError(f"The pinned file is no longer available: {label}. See the download sources in README.") from None
            if attempt == 3:
                raise RuntimeError(f"Download failed ({error.code}): {label}") from None
        except (OSError, urllib.error.URLError) as error:
            if attempt == 3:
                raise RuntimeError(f"Could not download {label}: {error}. Check your connection and retry; partial files are preserved.") from None
        report(f"Connection interrupted; resuming {label} (attempt {attempt + 2}/4)", offset / size)
        if cancel.wait(min(2 ** attempt, 8)):
            raise Cancelled("Cancelled. Downloads can be resumed.")


def provision(root, report, cancel, token=""):
    root = Path(root)
    m = manifest()
    root.mkdir(parents=True, exist_ok=True)
    runtime_marker = root / "runtime-ready.json"
    ready = False
    try:
        ready = json.loads(runtime_marker.read_text())["version"] == m["runtime_version"] and runtime_python(root).exists()
    except (OSError, ValueError, KeyError):
        pass
    remaining = sum(f["size"] for f in m["models"] if not (comfy_root(root) / "models" / f["folder"] / f["filename"]).exists())
    reserve = remaining + (18 * 1024**3 if not ready else 2 * 1024**3)
    if shutil.disk_usage(existing_parent(root)).free < reserve:
        raise RuntimeError(f"Not enough free space. This setup needs about {reserve / 1024**3:.1f} GB free in {root.drive or root}.")
    if not ready:
        archive = download(m["runtime"], root / "downloads" / m["runtime"]["filename"], report, cancel)
        extractor = resource("7zr.exe")
        if checksum(extractor) != m["extractor_sha256"]:
            raise RuntimeError("The bundled archive extractor did not pass its integrity check.")
        report("Extracting the self-contained runtime. This can take several minutes…", 0)
        (root / "runtime").mkdir(exist_ok=True)
        proc = subprocess.Popen([str(extractor), "x", str(archive), "-o" + str(root / "runtime"), "-y", "-aoa", "-bsp1"],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=CREATE_NO_WINDOW)
        tail = bytearray()
        def read_output():
            while chunk := proc.stdout.read(1024):
                tail.extend(chunk)
                if len(tail) > 16000:
                    del tail[:-8000]
                matches = re.findall(rb"(\d+)%", chunk)
                if matches:
                    report("Extracting Python, PyTorch and ComfyUI…", int(matches[-1]) / 100)
        reader = threading.Thread(target=read_output, daemon=True)
        reader.start()
        while proc.poll() is None:
            if cancel.wait(.2):
                proc.terminate()
                proc.wait(timeout=20)
                reader.join(timeout=5)
                raise Cancelled("Cancelled. Run setup again to finish extracting the runtime.")
        reader.join(timeout=5)
        if proc.returncode:
            raise RuntimeError("Runtime extraction failed: " + tail.decode("utf-8", errors="replace")[-2000:])
        report("Checking Python, CUDA, PyTorch and MP4 encoding…", .95)
        probe = subprocess.run([str(runtime_python(root)), "-s", "-c",
            "import torch,av; assert torch.cuda.is_available(), 'CUDA not available: update your NVIDIA driver'; print(torch.__version__); print(torch.cuda.get_device_name(0)); assert 'libx264' in av.codecs_available, 'H.264 encoder missing'"],
            capture_output=True, text=True, timeout=180, creationflags=CREATE_NO_WINDOW)
        if probe.returncode:
            raise RuntimeError("The GPU runtime check failed. Install a current NVIDIA driver, then retry.\n" + (probe.stderr + probe.stdout)[-3000:])
        atomic_json(runtime_marker, {"version": m["runtime_version"], "probe": probe.stdout.strip()})
        archive.unlink()  # Keep the extracted runtime; reclaim the 2 GB archive.
    for spec in m["models"]:
        download(spec, comfy_root(root) / "models" / spec["folder"] / spec["filename"], report, cancel, token)
    report("Installation complete. The model is ready to use.", 1)
