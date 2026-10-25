"""Build both Windows executables using the local PyInstaller installation."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.request
import zipfile
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from common import APP_EXE, VERSION, manifest

ROOT = Path(__file__).resolve().parent
OUT = Path(os.environ.get('STUDIO_BUILD_OUTPUT', str(ROOT / 'outputs')))
OUT.mkdir(exist_ok=True)


def build_desktop():
    config = manifest()["desktop"]
    archive = ROOT / "research/webview2-sdk/sdk.zip"
    if not archive.is_file():
        archive.parent.mkdir(parents=True, exist_ok=True)
        version = config["sdk_version"]
        urllib.request.urlretrieve("https://api.nuget.org/v3-flatcontainer/microsoft.web.webview2/" + version +
            "/microsoft.web.webview2." + version + ".nupkg", archive)
    # Verify cached downloads on every build, and use the pinned archive's DLLs.
    if hashlib.sha256(archive.read_bytes()).hexdigest() != config["sdk_sha256"]:
        raise RuntimeError("The WebView2 SDK did not pass its checksum check.")
    desktop = ROOT / "build" / ("desktop-host-" + VERSION)
    desktop.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "assets/desktop/MicrosoftEdgeWebview2Setup.exe", desktop)
    shutil.copy2(ROOT / "assets/desktop/WebView2-LICENSE.txt", desktop)
    csc = Path("C:/Windows/Microsoft.NET/Framework64/v4.0.30319/csc.exe")
    with zipfile.ZipFile(archive) as package:
        for name in ("Microsoft.Web.WebView2.Core.dll", "Microsoft.Web.WebView2.WinForms.dll"):
            (desktop/name).write_bytes(package.read('lib/net462/'+name))
        (desktop/'WebView2Loader.dll').write_bytes(package.read('runtimes/win-x64/native/WebView2Loader.dll'))
    shutil.copy2(ROOT / "src" / "DesktopHost.exe.config", desktop / "WanDesktopHost.exe.config")
    subprocess.run([str(csc), "/nologo", "/target:winexe", "/platform:x64", "/optimize+",
        "/out:" + str(desktop / "WanDesktopHost.exe"), "/win32icon:" + str(ROOT / "assets/studio.ico"),
        "/win32manifest:" + str(ROOT / "src/DesktopHost.manifest"),
        "/reference:System.Windows.Forms.dll", "/reference:System.Drawing.dll", "/reference:System.Web.Extensions.dll",
        "/reference:" + str(desktop / "Microsoft.Web.WebView2.Core.dll"),
        "/reference:" + str(desktop / "Microsoft.Web.WebView2.WinForms.dll"), str(ROOT / "src/DesktopHost.cs")], check=True)
    return desktop


def freeze(script, name, data):
    command = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--windowed",
               "--name", name, "--distpath", str(OUT), "--workpath", str(ROOT / "build" / name),
               "--specpath", str(ROOT / "build"), "--paths", str(ROOT / "src"),
               "--icon", str(ROOT / "assets" / "studio.ico")]
    for path, folder in data:
        command += ["--add-data", f"{path};{folder}"]
    command.append(str(ROOT / "src" / script))
    subprocess.run(command, cwd=ROOT, check=True)


desktop_folder = build_desktop()
common = [(ROOT / "assets" / "manifest.json", "assets"), (ROOT / "assets" / "7zr.exe", "assets"),
          (ROOT / 'assets' / 'packs.json', 'assets'),
          (ROOT / 'assets' / 'enhancers.json', 'assets'),
          (ROOT / 'assets' / 'engines.json', 'assets'),
          (ROOT / 'assets' / 'avatar-runtime.json', 'assets'),
          (ROOT / 'assets' / 'avatar-sources.zip', 'assets'),
          (ROOT / 'assets' / 'avatar-NOTICES.txt', 'assets'),
          (ROOT / 'assets' / 'ref2va', 'assets/ref2va'),
          (ROOT / 'assets' / 'wamu', 'assets/wamu'),
          (ROOT / 'assets' / 'studio-wamu.js', 'assets'),
          (ROOT / 'assets' / 'minimax_h3', 'assets/minimax_h3'),
          (ROOT / 'assets' / 'viggle', 'assets/viggle'),
          (ROOT / 'assets' / 'engine_worker.py', 'assets'),
          (ROOT / 'assets' / 'attention_worker.py', 'assets'),
          (ROOT / 'assets' / 'model_reader.py', 'assets'),
          (ROOT / 'assets' / 'studio-moss.js', 'assets'),
          (ROOT / 'assets' / 'studio-canvas.js', 'assets'),
          (ROOT / 'assets' / 'studio-references.js', 'assets'),
          (ROOT / 'assets' / 'studio-logo.png', 'assets'),
          (ROOT / 'assets' / 'completion-ping.wav', 'assets'),
          *[(desktop_folder/name, 'assets/desktop') for name in
            ('WanDesktopHost.exe','WanDesktopHost.exe.config','WebView2Loader.dll',
             'Microsoft.Web.WebView2.Core.dll','Microsoft.Web.WebView2.WinForms.dll',
             'MicrosoftEdgeWebview2Setup.exe','WebView2-LICENSE.txt')]]
freeze("app.py", Path(APP_EXE).stem, common + [(ROOT / "assets" / "index.html", "assets"), (ROOT / 'assets/studio.js', 'assets'), (ROOT / 'assets/studio-tools.js', 'assets'), (ROOT / 'assets/studio-updates.js', 'assets'), (ROOT / 'assets/studio.css', 'assets'), (ROOT / 'assets/media_worker.py', 'assets'), (ROOT / 'assets/upscale_worker.py', 'assets'), (ROOT / 'assets/avatar_worker.py', 'assets'), (ROOT / 'assets/avatar_audio_worker.py', 'assets'), (ROOT / 'assets/studio-avatars.js', 'assets'), (ROOT / 'assets/studio-ref2va.js', 'assets'), (ROOT / 'assets/studio-minimax.js', 'assets'), (ROOT / 'assets/studio-qwen.js', 'assets'), (ROOT / 'assets/studio-voice.js', 'assets'), (ROOT / 'assets/voice_worker.py', 'assets'), (ROOT / 'assets/video_faceswap_worker.py', 'assets'), (ROOT / 'assets/video-faceswap.json', 'assets'), (ROOT / 'assets/studio-video-faceswap.js', 'assets')])
shutil.copy2(OUT / APP_EXE, ROOT / "assets" / APP_EXE)
freeze("installer.py", "AIImageVideoStudio-Setup-" + VERSION, common + [(ROOT / "assets" / APP_EXE, "assets"), (ROOT / 'assets/installer-logo.png', 'assets')])
hashes = []
for file in sorted(OUT.glob("*.exe")):
    hashes.append(hashlib.sha256(file.read_bytes()).hexdigest() + "  " + file.name)
(OUT / "SHA256SUMS.txt").write_text("\n".join(hashes) + "\n", encoding="utf-8")
print("BUILD_PASS", flush=True)
