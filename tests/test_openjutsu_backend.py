"""Managed backend installation plans, model reuse and ownership; no inference."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import openjutsu
import openjutsu_backend as backend
from common import comfy_root


class BackendTests(unittest.TestCase):
    def test_complete_pinned_catalog_and_safe_shared_vae(self):
        config = backend.catalog()
        self.assertEqual(len(config['nodes']), 13)
        for spec in [config['engine'], config['ffmpeg'], *config['wheels'],
                     *[n['archive'] for n in config['nodes']],
                     *[f for g in config['groups'].values() for f in g['files']]]:
            self.assertRegex(spec['sha256'], r'^[a-f0-9]{64}$')
            self.assertGreater(spec['size'], 0)
            self.assertTrue(spec['url'].startswith('https://'))
        self.assertIn('SolarRendererModel', config['required_nodes'])
        self.assertIn('SAM3_VideoTrack', config['required_nodes'])
        self.assertIn('H3FaceTrackCrop', config['required_nodes'])
        self.assertEqual(config['defaults']['flux_vae'], 'flux3-vae.safetensors')
        self.assertEqual(config['defaults']['solar_rank'], 64)
        self.assertNotIn('torch', [f['filename'].split('-')[0] for f in config['wheels']])

    def test_external_backend_is_optional_and_managed_is_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = openjutsu.Workspace(tmp)
            self.assertEqual(workspace.mode, 'managed')
            workspace.configure(None, 'managed', str(Path(tmp) / 'weights'))
            self.assertEqual(backend.models_folder(tmp), Path(tmp) / 'weights')
            workspace.configure('http://localhost:8200', 'external')
            self.assertEqual(workspace.mode, 'external')
            self.assertEqual(workspace.backend, 'http://127.0.0.1:8200')
            with self.assertRaises(ValueError):workspace.configure(None, 'managed', str(backend.folder(tmp) / 'weights'))

    def test_invalid_selections_and_gated_access_fail_before_downloading(self):
        with tempfile.TemporaryDirectory() as tmp, patch('openjutsu_backend.download') as download:
            for keys in [None, ['missing'], ['swap', 'swap'], [{}]]:
                with self.subTest(keys=keys), self.assertRaises(ValueError):backend.preflight(tmp, keys)
            with self.assertRaisesRegex(ValueError, 'Hugging Face'):
                backend.install_models(tmp, ['relight'], lambda *_:None, threading.Event())
            download.assert_not_called()

    def test_existing_shared_model_is_verified_and_never_copied(self):
        content = b'already installed weights'
        spec = dict(label='fixture', filename='fixture.bin', folder='diffusion_models', size=len(content),
                    sha256=hashlib.sha256(content).hexdigest(), url='https://example.com/fixture.bin')
        config = dict(groups={'swap': dict(name='fixture', source='https://example.com', files=[spec])})
        with tempfile.TemporaryDirectory() as tmp, patch('openjutsu_backend.catalog', return_value=config), patch('openjutsu_backend.download') as download:
            shared = comfy_root(tmp) / 'models/diffusion_models/fixture.bin'
            shared.parent.mkdir(parents=True)
            shared.write_bytes(content)
            self.assertTrue(backend.available(tmp, spec))
            backend.install_models(tmp, ['swap'], lambda *_:None, threading.Event())
            download.assert_not_called()
            self.assertEqual(shared.read_bytes(), content)
            self.assertFalse(backend.path_for(tmp, spec).exists())

    def test_corrupt_shared_model_downloads_to_private_folder(self):
        spec = dict(label='fixture', filename='fixture.bin', folder='vae', size=3,
                    sha256=hashlib.sha256(b'new').hexdigest(), url='https://example.com/fixture.bin')
        config = dict(groups={'swap': dict(files=[spec])})
        with tempfile.TemporaryDirectory() as tmp, patch('openjutsu_backend.catalog', return_value=config), patch('openjutsu_backend.download', return_value=Path(tmp) / 'unused') as download:
            shared = comfy_root(tmp) / 'models/vae/fixture.bin'
            shared.parent.mkdir(parents=True)
            shared.write_bytes(b'old')
            backend.install_models(tmp, ['swap'], lambda *_:None, threading.Event())
            self.assertEqual(download.call_args.args[1], backend.path_for(tmp, spec))
            self.assertNotEqual(download.call_args.args[1], shared)
            self.assertEqual(shared.read_bytes(), b'old')

    def test_auxiliary_models_use_the_configured_private_cache(self):
        spec = dict(label='depth fixture', filename='depth.pth', folder='controlnet_aux/JUGGHM/Metric3D', size=3,
                    sha256=hashlib.sha256(b'new').hexdigest(), url='https://example.com/depth.pth')
        config = dict(groups={'relight': dict(files=[spec])})
        with tempfile.TemporaryDirectory() as tmp, patch('openjutsu_backend.catalog', return_value=config), patch('openjutsu_backend.download') as download:
            shared = comfy_root(tmp) / 'models' / spec['folder'] / spec['filename']
            shared.parent.mkdir(parents=True)
            shared.write_bytes(b'new')
            self.assertFalse(backend.available(tmp, spec))
            backend.install_models(tmp, ['relight'], lambda *_:None, threading.Event())
            self.assertEqual(download.call_args.args[1], backend.path_for(tmp, spec))
            self.assertEqual(shared.read_bytes(), b'new')

    def test_face_archive_rejects_unknown_files_and_extracts_verified_bundle(self):
        spec = dict(folder='insightface', filename='buffalo_l.zip', size=1, sha256='a'*64,
                    unpack=True, members=['det_10g.onnx', 'w600k_r50.onnx'])
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / 'bundle.zip'
            with zipfile.ZipFile(archive, 'w') as package:package.writestr('../unexpected.py', b'bad')
            with self.assertRaises(ValueError):backend.unpack_faces(tmp, spec, archive, threading.Event())
            with zipfile.ZipFile(archive, 'w') as package:
                for name in spec['members']:package.writestr(name, b'onnx fixture')
            backend.unpack_faces(tmp, spec, archive, threading.Event())
            self.assertTrue(backend.available(tmp, spec))
            (backend.path_for(tmp, spec).parent / 'models/buffalo_l/det_10g.onnx').unlink()
            self.assertFalse(backend.available(tmp, spec))

    def test_close_only_stops_owned_backend_process(self):
        with tempfile.TemporaryDirectory() as tmp, patch('avatar_runtime.stop_process') as stop:
            engine = backend.ManagedEngine(tmp)
            owned = Mock()
            engine.process = owned
            engine.close()
            stop.assert_called_once_with(owned)
            self.assertIsNone(engine.process)


if __name__ == '__main__':unittest.main()
