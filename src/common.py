"""Shared paths, settings and hardware information. No third-party dependencies."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

APP_NAME = "A.I. Image & Video Studio"
APP_EXE = 'AIImageVideoStudio.exe'
VERSION = "1.5.2"
INSTALL_DIR_NAME = "AI Image & Video Studio"
UNINSTALL_KEY = r'Software\Microsoft\Windows\CurrentVersion\Uninstall\WanVideoStudio'
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def resource(name):
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / "assets" / name


def manifest():
    return json.loads(resource("manifest.json").read_text(encoding="utf-8"))


def app_root():
    if getattr(sys, "frozen", False):
        installation = Path(sys.executable).resolve().parent
        return installed_data_path(installation)
    return Path(__file__).resolve().parent.parent / "dev-install"


def runtime_root(root):
    return Path(root) / "runtime" / manifest()["runtime_folder"]


def runtime_python(root):
    return runtime_root(root) / "python_embeded" / "python.exe"


def comfy_root(root):
    return runtime_root(root) / "ComfyUI"


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name, suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            json.dump(value, out, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def load_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def gpu_info():
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=12, creationflags=CREATE_NO_WINDOW,
        )
        gpus = []
        for line in result.stdout.splitlines():
            name, memory, driver = [x.strip() for x in line.split(",")]
            gpus.append({"name": name, "vram_gb": round(float(memory) / 1024, 1), "driver": driver})
        if gpus:
            return gpus[0]
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass
    return {"name": "NVIDIA GPU not detected", "vram_gb": 0, "driver": "Unavailable"}


def existing_parent(path):
    path = Path(path).resolve()
    while not path.exists() and path != path.parent:
        path = path.parent
    return path


def default_install_path():
    return Path(os.environ.get('ProgramW6432', os.environ.get('ProgramFiles', 'C:/Program Files'))) / INSTALL_DIR_NAME


def in_program_files(path):
    path = Path(path).resolve()
    for name in ('ProgramW6432', 'ProgramFiles', 'ProgramFiles(x86)'):
        folder = Path(os.environ.get(name, 'C:/Program Files' if name != 'ProgramFiles(x86)' else 'C:/Program Files (x86)')).resolve()
        if path == folder or path.is_relative_to(folder):
            return True
    return False


def local_data_path():
    return Path(os.environ.get('LOCALAPPDATA', str(Path.home() / 'AppData/Local'))) / INSTALL_DIR_NAME


def registered_installation():
    if os.name == 'nt':
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY) as key:
                root = Path(winreg.QueryValueEx(key, 'InstallLocation')[0]).resolve()
                if not (root / 'studio-install.json').is_file():
                    return None, None
                try:
                    data = Path(winreg.QueryValueEx(key, 'DataLocation')[0]).resolve()
                except OSError:
                    data = local_data_path() if in_program_files(root) else root
                return root, data
        except (OSError, ValueError):
            pass
    return None, None


def default_data_path(installation):
    installation = Path(installation).resolve()
    previous, data = registered_installation()
    if previous == installation and data:
        return data
    if in_program_files(installation):
        # Reuse existing downloads and personal work when adding a Program Files install.
        if data and not in_program_files(data) and data.is_dir():
            return data
        return local_data_path()
    return installation


def installed_data_path(installation):
    installation = Path(installation).resolve()
    registered, data = registered_installation()
    if registered == installation and data:
        return data
    return local_data_path() if in_program_files(installation) else installation


def check_data_path(path):
    path = Path(path).expanduser().resolve()
    if in_program_files(path):
        raise ValueError('Choose a writable folder outside Program Files for models and studio data.')
    return check_install_path(path, data=True)


def check_install_path(path, data=False):
    path = Path(path).expanduser().resolve()
    if path == path.parent or len(path.parts) < 2:
        raise ValueError("Choose a dedicated application folder, not the root of a drive.")
    if len(str(path)) > 140:
        raise ValueError("Choose a shorter path (under 140 characters) for the portable runtime.")
    marked = (path / 'studio-install.json').is_file() or (data and (path / 'studio-data.json').is_file())
    if path.exists() and any(path.iterdir()) and not marked:
        raise ValueError("That folder contains other files. Choose a new, empty studio folder or an existing studio installation.")
    return path


def install_ready(root):
    m = manifest()
    return bool(
        runtime_python(root).is_file()
        and (Path(root) / "runtime-ready.json").is_file()
        and all((comfy_root(root) / "models" / f["folder"] / f["filename"]).is_file()
                and (comfy_root(root) / "models" / f["folder"] / f["filename"]).stat().st_size == f["size"]
                for f in m["models"])
    )


def runtime_ready(root):
    return bool(runtime_python(root).is_file() and (Path(root)/'runtime-ready.json').is_file())
