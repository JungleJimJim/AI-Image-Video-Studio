"""Run OpenJutsu's proxy in its private dependency directory."""
from pathlib import Path
import runpy
import sys

folder = Path(sys.argv[1]).resolve()
action = sys.argv[2]
sys.path.insert(0, str(folder / 'dependencies'))
if action == 'patch':
    sys.argv = [str(folder / 'code/patch_proxy.py')]
    runpy.run_path(sys.argv[0], run_name='__main__')
elif action == 'proxy':
    from comfy_api_proxy.cli import main
    raise SystemExit(main(sys.argv[3:]))
else:
    raise SystemExit('Unknown OpenJutsu worker action.')
