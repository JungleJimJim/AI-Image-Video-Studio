"""Create a small, reproducible source package without model weights or test profiles."""
import hashlib
from pathlib import Path
import zipfile
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from common import VERSION

root = Path(__file__).resolve().parent
output = root / "outputs" / ("AIImageVideoStudio-Source-" + VERSION + ".zip")
files = [root / name for name in ("README.md", "build.py", "package_source.py", "requirements-build.txt", ".gitignore")]
files.extend(root / name for name in ('.gitattributes', 'LICENSE') if (root / name).is_file())
for folder in ("src", "tests", "assets"):
    files.extend(path for path in (root / folder).rglob("*")
                 if path.is_file() and "__pycache__" not in path.parts and path.suffix not in (".pyc",)
                 and path.name not in ("WanVideoStudio.exe", 'AIImageVideoStudio.exe'))
with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=8) as archive:
    for file in sorted(files):
        archive.write(file, file.relative_to(root))
    for name in ("7zip-license.txt", "THIRD-PARTY.txt", "VALIDATION.md"):
        file = root / "outputs" / name
        if file.exists():
            archive.write(file, "notices/" + name)
hashes = []
for file in sorted((root / "outputs").iterdir()):
    if file.suffix.lower() in (".exe", ".zip"):
        hashes.append(hashlib.sha256(file.read_bytes()).hexdigest() + "  " + file.name)
(root / "outputs" / "SHA256SUMS.txt").write_text("\n".join(hashes) + "\n", encoding="utf-8")
print(str(output))
