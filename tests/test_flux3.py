"""FLUX 3 routing, source preservation and engine isolation; no inference."""
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import zipfile
from unittest.mock import Mock,patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from common import atomic_json,comfy_root
import engine_support
from engine import engine_command
from loras import import_loras,validate_selection
from packs import catalog,install,model_path,ready
from test_loras import fixture
from workflows import validate_image_options,validate_edit_options,image_workflow,edit_workflow


class Flux3Tests(unittest.TestCase):
    def check_desktop_exit(self, deliberate):
        import app
        with tempfile.TemporaryDirectory() as tmp,patch('app.gpu_info',return_value={}):
            studio=app.Studio(Path(tmp));studio.resources.start=Mock()
            host=Mock(returncode=1,pid=42);host.poll.return_value=None
            def open_host(*args):studio.closing=deliberate;return host
            server=Mock(server_port=12345);thread=Mock();thread.is_alive.return_value=False
            with patch('app.Studio',return_value=studio),patch('app.open_desktop',side_effect=open_host),\
                 patch('app.http.server.ThreadingHTTPServer',return_value=server),patch('app.threading.Thread',return_value=thread),\
                 patch('app.atexit.register'),patch('sys.argv',['studio','--root',tmp]):
                if deliberate:app.main()
                else:
                    with self.assertRaisesRegex(RuntimeError,'desktop interface could not start'):app.main()
            self.assertFalse((Path(tmp)/'.studio-instance.json').exists())

    def test_deliberate_desktop_shutdown_does_not_open_a_startup_error(self):
        self.check_desktop_exit(True)

    def test_unexpected_desktop_failure_still_reports_the_error(self):
        self.check_desktop_exit(False)

    def test_model_recipe_is_distilled_flux3_with_distinct_vae(self):
        o=validate_image_options(dict(model='flux3',prompt='A red toy robot',cfg=6,negative='ignore me',seed=42))
        self.assertEqual((o['steps'],o['cfg'],o['negative']),(16,1,''))
        g=image_workflow(o,'test')
        self.assertEqual(g['2']['inputs']['type'],'flux3')
        self.assertEqual(g['3']['inputs']['vae_name'],'flux3-vae.safetensors')
        self.assertEqual(g['8']['inputs']['model'],['1',0])
        self.assertFalse(any(n['class_type'] in ('Flux2Scheduler','ModelSamplingAuraFlow') for n in g.values()))
        owned={}
        for model,pack in catalog().items():
            for file in pack['files']:
                key=(file['folder'],file['filename'])
                self.assertEqual(owned.setdefault(key,file['sha256']),file['sha256'])

    def test_ten_reference_editing_and_masks_preserve_both_conditionings(self):
        o=validate_edit_options(dict(model='flux3',prompt='Change the roof of <ref_image_0>',source_image='start',references=[f'ref{i}' for i in range(9)]))
        o.update(input_file='start.png',reference_files=[f'ref{i}.png' for i in range(9)],mask_file='mask.png',loras=[dict(name='style.safetensors',strength=.5)])
        g=edit_workflow(o,'edit')
        self.assertEqual(sum(k.startswith('images.image') for k in g['22']['inputs']),10)
        self.assertEqual(g['8']['inputs']['positive'],['22',0]);self.assertEqual(g['8']['inputs']['negative'],['22',1])
        self.assertEqual(g['8']['inputs']['model'],['1000',0])
        self.assertEqual(g['63']['inputs']['destination'],['21',0]);self.assertEqual(g['10']['inputs']['images'],['63',0])
        self.assertEqual(g['38']['inputs']['image'],'ref8.png')
        with self.assertRaises(ValueError):validate_edit_options(dict(model='flux3',prompt='Edit',source_image='start',references=[str(i) for i in range(10)]))
        with self.assertRaises(ValueError):validate_edit_options(dict(model='qwenedit',prompt='Edit',source_image='start',references=['1','2','3']))

    def test_flux2_adapters_cannot_enter_flux3_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'style.safetensors';fixture(source)
            imported=import_loras(root,[str(source)],lambda *a:None,threading.Event(),'fluxklein')
            from loras import installed_loras
            name=installed_loras(root,'fluxklein')[0]['name']
            with self.assertRaises(ValueError):validate_selection(root,[dict(name=name,strength=1)],'flux3')

    def test_gated_download_fails_before_engine_or_weights_when_token_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp,patch('packs.download') as download,patch('packs.engine_support.install') as engine:
            with self.assertRaisesRegex(ValueError,'Hugging Face access'):install(Path(tmp),['flux3'],lambda *a:None,threading.Event())
            download.assert_not_called();engine.assert_not_called()

    def test_model_readiness_requires_engine_and_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            pack=dict(engine='flux3',files=[dict(folder='diffusion_models',filename='test.safetensors',size=3)])
            file=model_path(root,pack['files'][0]);file.parent.mkdir(parents=True);file.write_bytes(b'abc')
            with patch('packs.catalog',return_value={'flux3':pack}),patch('packs.runtime_python',return_value=file),patch('packs.engine_support.ready',return_value=False) as check:
                self.assertFalse(ready(root,'flux3'));check.return_value=True;self.assertTrue(ready(root,'flux3'))

    def test_engine_command_preserves_original_engine_and_shares_only_model_input_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            with patch('engine_support.ready',return_value=True):flux=engine_command(root,1234,root/'output','low','flux3')
            original=engine_command(root,1234,root/'output','low','wan22')
            self.assertIn('engine_worker.py',Path(flux[2]).name);self.assertEqual(Path(original[2]),comfy_root(root)/'main.py')
            self.assertEqual(Path(flux[flux.index('--models-directory')+1]),comfy_root(root)/'models')
            self.assertIn('--disable-all-custom-nodes',flux);self.assertIn('--enable-dynamic-vram',flux);self.assertIn('--offline',flux)
            self.assertNotIn('--models-directory',original)

    def test_archive_extraction_rejects_traversal_and_cancels(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);archive=root/'source.zip'
            with zipfile.ZipFile(archive,'w') as z:z.writestr('code/../../outside.txt','bad')
            with self.assertRaises(ValueError):engine_support.extract(archive,root/'engine',threading.Event())
            self.assertFalse((root/'outside.txt').exists())
            with zipfile.ZipFile(archive,'w') as z:z.writestr('code/main.py','# fixture')
            cancel=threading.Event();cancel.set()
            from downloads import Cancelled
            with self.assertRaises(Cancelled):engine_support.extract(archive,root/'engine',cancel)

    def test_engine_ready_accepts_the_upstream_namespace_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);folder=engine_support.engine_root(root,'flux3')
            for name in ('code/main.py','dependencies/comfy_aimdo/control.py'):
                file=folder/name;file.parent.mkdir(parents=True,exist_ok=True);file.write_text('# fixture')
            atomic_json(folder/'installed.json',dict(revision=engine_support.catalog()['flux3']['revision']))
            with patch('engine_support.runtime_python',return_value=folder/'code/main.py'):
                self.assertTrue(engine_support.ready(root,'flux3'))

    def test_engine_probe_failure_preserves_existing_engine_and_cleans_staging(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);folder=engine_support.engine_root(root,'flux3');folder.mkdir(parents=True)
            sentinel=folder/'previous.txt';sentinel.write_text('preserved')
            archive=root/'fixture.zip'
            with zipfile.ZipFile(archive,'w') as z:z.writestr('source/main.py','# test only')
            config=dict(revision='test',version='test',archive=dict(filename='test.zip'),wheels=[])
            with patch('engine_support.ready',return_value=False),patch('engine_support.runtime_python',return_value=archive),\
                 patch('engine_support.catalog',return_value={'flux3':config}),patch('engine_support.download',return_value=archive),\
                 patch('engine_support.subprocess.Popen',return_value=Mock(poll=Mock(return_value=0),returncode=0)),\
                 patch('engine_support.subprocess.run',return_value=Mock(returncode=1,stderr='probe failed',stdout='')):
                with self.assertRaises(RuntimeError):engine_support.install(root,'flux3',lambda *a:None,threading.Event())
            self.assertEqual(sentinel.read_text(),'preserved');self.assertEqual(list(folder.parent.glob('.flux3-*')),[])


if __name__=='__main__':unittest.main()
