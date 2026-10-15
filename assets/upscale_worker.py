"""Isolated adapter for tritant's pinned RTX VSR pipeline; no global custom nodes."""
from contextlib import contextmanager
import importlib
import json
import logging
from pathlib import Path
import sys
import types


def main():
    data=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
    package=types.ModuleType('studio_rtx_vsr');package.__path__=[data['extension']]
    sys.modules['studio_rtx_vsr']=package
    pipeline=importlib.import_module('studio_rtx_vsr.pipeline')
    vfx=importlib.import_module('studio_rtx_vsr.vfx')
    logging.basicConfig(level=logging.INFO)
    def save(path,value):
        path=Path(path);temp=path.with_suffix('.tmp');temp.write_text(json.dumps(value));temp.replace(path)
    @contextmanager
    def factory(*args):
        with vfx.video_transform(*args) as transform:
            count=0
            def apply(frame):
                nonlocal count
                if Path(data['cancel']).exists():raise RuntimeError('Enhancement cancelled by the studio.')
                result=transform(frame);count+=1
                if count==1 or count%8==0:save(data['progress'],dict(frames=count))
                return result
            yield apply
    result=pipeline.process_video(Path(data['source']),Path(data['output']),pipeline.Settings(**data['options']),transform_factory=factory)
    save(data['result'],result)


if __name__=='__main__':main()
