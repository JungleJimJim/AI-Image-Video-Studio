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
    sdk = ROOT / "research" / "webview2-sdk" / "package"
    if not (sdk / "lib/net462/Microsoft.Web.WebView2.Core.dll").is_file():
        config = manifest()["desktop"]
        archive = ROOT / "research/webview2-sdk/sdk.zip"
        archive.parent.mkdir(parents=True, exist_ok=True)
        version = config["sdk_version"]
        urllib.request.urlretrieve("https://api.nuget.org/v3-flatcontainer/microsoft.web.webview2/" + version +
            "/microsoft.web.webview2." + version + ".nupkg", archive)
        if hashlib.sha256(archive.read_bytes()).hexdigest() != config["sdk_sha256"]:
            raise RuntimeError("The WebView2 SDK did not pass its checksum check.")
        with zipfile.ZipFile(archive) as package:
            package.extractall(sdk)
    desktop = ROOT / "build" / "desktop-host"
    desktop.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "assets/desktop/MicrosoftEdgeWebview2Setup.exe", desktop)
    shutil.copy2(ROOT / "assets/desktop/WebView2-LICENSE.txt", desktop)
    csc = Path("C:/Windows/Microsoft.NET/Framework64/v4.0.30319/csc.exe")
    for name in ("Microsoft.Web.WebView2.Core.dll", "Microsoft.Web.WebView2.WinForms.dll"):
        shutil.copy2(sdk / "lib" / "net462" / name, desktop / name)
    shutil.copy2(sdk / "runtimes" / "win-x64" / "native" / "WebView2Loader.dll", desktop)
    shutil.copy2(ROOT / "src" / "DesktopHost.exe.config", desktop / "WanDesktopHost.exe.config")
    subprocess.run([str(csc), "/nologo", "/target:winexe", "/platform:x64", "/optimize+",
        "/out:" + str(desktop / "WanDesktopHost.exe"), "/win32icon:" + str(ROOT / "assets/studio.ico"),
        "/win32manifest:" + str(ROOT / "src/DesktopHost.manifest"),
        "/reference:System.Windows.Forms.dll", "/reference:System.Drawing.dll", "/reference:System.Web.Extensions.dll",
        "/reference:" + str(desktop / "Microsoft.Web.WebView2.Core.dll"),
        "/reference:" + str(desktop / "Microsoft.Web.WebView2.WinForms.dll"), str(ROOT / "src/DesktopHost.cs")], check=True)


def freeze(script, name, data):
    command = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--windowed",
               "--name", name, "--distpath", str(OUT), "--workpath", str(ROOT / "build" / name),
               "--specpath", str(ROOT / "build"), "--paths", str(ROOT / "src"),
               "--icon", str(ROOT / "assets" / "studio.ico")]
    for path, folder in data:
        command += ["--add-data", f"{path};{folder}"]
    command.append(str(ROOT / "src" / script))
    subprocess.run(command, cwd=ROOT, check=True)


build_desktop()
common = [(ROOT / "assets" / "manifest.json", "assets"), (ROOT / "assets" / "7zr.exe", "assets"),
          (ROOT / 'assets' / 'packs.json', 'assets'),
          (ROOT / 'assets' / 'enhancers.json', 'assets'),
          (ROOT / 'assets' / 'studio-logo.png', 'assets'),
          (ROOT / "build" / "desktop-host", "assets/desktop")]
freeze("app.py", Path(APP_EXE).stem, common + [(ROOT / "assets" / "index.html", "assets"), (ROOT / 'assets/studio.js', 'assets'), (ROOT / 'assets/studio-tools.js', 'assets'), (ROOT / 'assets/studio.css', 'assets'), (ROOT / 'assets/media_worker.py', 'assets'), (ROOT / 'assets/upscale_worker.py', 'assets')])
shutil.copy2(OUT / APP_EXE, ROOT / "assets" / APP_EXE)
freeze("installer.py", "AIImageVideoStudio-Setup-" + VERSION, common + [(ROOT / "assets" / APP_EXE, "assets"), (ROOT / 'assets/installer-logo.png', 'assets')])
hashes = []
for file in sorted(OUT.glob("*.exe")):
    hashes.append(hashlib.sha256(file.read_bytes()).hexdigest() + "  " + file.name)
(OUT / "SHA256SUMS.txt").write_text("\n".join(hashes) + "\n", encoding="utf-8")
print("BUILD_PASS", flush=True)
