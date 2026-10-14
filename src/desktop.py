"""Small native Windows host for the existing studio UI."""
import os
from pathlib import Path
import subprocess

from common import CREATE_NO_WINDOW, manifest, resource
from downloads import checksum


def desktop_host():
    return resource("desktop/WanDesktopHost.exe")


def runtime_available():
    return subprocess.run([str(desktop_host()), "--check-runtime"], timeout=20,
                          creationflags=CREATE_NO_WINDOW).returncode == 0


def ensure_desktop_runtime(report=lambda *_: None):
    if runtime_available():
        return
    report("Installing Microsoft WebView2 for the desktop interface…", None)
    bootstrapper = resource("desktop/MicrosoftEdgeWebview2Setup.exe")
    if checksum(bootstrapper) != manifest()["desktop"]["bootstrapper_sha256"]:
        raise RuntimeError("The bundled Microsoft WebView2 installer did not pass its integrity check.")
    result = subprocess.run([str(bootstrapper), "/silent", "/install"], timeout=600,
                            creationflags=CREATE_NO_WINDOW)
    if result.returncode not in (0, 3010) or not runtime_available():
        raise RuntimeError("Microsoft WebView2 setup could not finish. Install the WebView2 Evergreen Runtime from Microsoft, then retry Setup.")


def activate_desktop(instance):
    pid = instance.get("desktop_pid")
    if not isinstance(pid, int):
        return False
    return subprocess.run([str(desktop_host()), "--activate", str(pid)], timeout=10,
                          creationflags=CREATE_NO_WINDOW).returncode == 0


def open_desktop(url, token, root):
    ensure_desktop_runtime()
    logs = Path(root) / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    # WinForms is a native GUI executable and does not open a console or browser.
    return subprocess.Popen([str(desktop_host()), url, token, str(root)],
                            cwd=desktop_host().parent, creationflags=CREATE_NO_WINDOW)
