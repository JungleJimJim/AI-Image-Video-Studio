"""OpenJutsu isolation, process lifecycle, bridge and queue checks; no inference."""
import io
import http.client
import http.server
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import MagicMock, Mock, patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import openjutsu
from app import Studio, make_handler


class OpenJutsuTests(unittest.TestCase):
    def test_loopback_origins_only(self):
        self.assertEqual(openjutsu.local_url('http://localhost:8188/'), 'http://127.0.0.1:8188')
        self.assertEqual(openjutsu.local_url('http://[::1]:8188'), 'http://[::1]:8188')
        for value in ['https://127.0.0.1:8188', 'http://example.com:8188', 'http://127.0.0.1.evil:8188',
                      'http://127.0.0.1:8188/path', 'http://x:y@127.0.0.1:8188', 'http://127.0.0.1:8188?x=1',
                      'http://127.0.0.1:8188#x', 'http://127.0.0.1:0', 'http://127.0.0.1:65536', None]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                openjutsu.local_url(value)

    def test_pinned_sources_and_proxy_dependencies(self):
        config = openjutsu.catalog()
        self.assertIn(config['revision'], config['archive']['url'])
        self.assertGreaterEqual(len(config['node_groups']), 13)
        for file in [config['archive'], config['node'], *config['wheels']]:
            self.assertRegex(file['sha256'], '^[a-f0-9]{64}$')
            self.assertGreater(file['size'], 1000)
            self.assertTrue(file['url'].startswith('https://'))
        for name in ['SolarRenderer', 'ComfyUI-H3-FaceRefine', 'Orion4D_FXMax']:
            self.assertIn(name, [group['name'] for group in config['node_groups']])

    def test_archive_cannot_escape_component(self):
        for name in ['root/../../outside.txt', '/absolute.txt', 'root/escape\\file.txt', 'root/C:/escape.txt']:
            with tempfile.TemporaryDirectory() as tmp:
                archive = Path(tmp) / 'source.zip'
                with zipfile.ZipFile(archive, 'w') as package:
                    entry = zipfile.ZipInfo('placeholder')
                    entry.filename = name
                    package.writestr(entry, b'untrusted')
                with self.subTest(name=name), self.assertRaises(ValueError):
                    openjutsu.extract(archive, Path(tmp) / 'component', threading.Event())

    def test_bridge_retains_api_guard_and_limits_parent(self):
        with tempfile.TemporaryDirectory() as tmp:
            code = Path(tmp)
            (code / 'lib').mkdir()
            (code / 'lib/model.ts').write_text('qwen3vl_32b_minimax_h3_int4_convrot.safetensors')
            (code / 'lib/picture.ts').write_text('solarRank: 384, ...solarLoraFiles(384); qwen3vl_32b_minimax_h3_int4_convrot.safetensors')
            (code / 'workflows/picture').mkdir(parents=True)
            (code / 'workflows/picture/relight.api.json').write_text('flux2-vae.safetensors qwen3vl_4b_fp8_scaled.safetensors')
            (code / 'next.config.ts').write_text('  { key: "X-Frame-Options", value: "DENY" },\n  { key: "Content-Security-Policy", value: "frame-ancestors \'none\'" },\n')
            (code / 'proxy.ts').write_text('export function proxy(request: Request) {\n  return authorize(request) ?? NextResponse.next();\n}\n')
            openjutsu.patch_bridge(code)
            source = (code / 'proxy.ts').read_text()
            self.assertIn('authorize(request)', source)
            self.assertIn('STUDIO_PARENT_ORIGIN', source)
            self.assertIn('frame-ancestors', source)
            self.assertIn('X-Frame-Options', source)
            for filename in ('model.ts', 'picture.ts'):
                self.assertIn('qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors', (code / 'lib' / filename).read_text())
                self.assertNotIn('qwen3vl_32b_minimax_h3_int4_convrot.safetensors', (code / 'lib' / filename).read_text())
            self.assertIn('solarRank: 64, ...solarLoraFiles(64)', (code / 'lib/picture.ts').read_text())
            self.assertEqual((code / 'workflows/picture/relight.api.json').read_text(), 'flux3-vae.safetensors qwen3vl_4b_int8_convrot.safetensors')
            with self.assertRaises(ValueError):
                openjutsu.patch_bridge(code)

    def test_check_reports_mode_specific_nodes_without_posting_prompt(self):
        with tempfile.TemporaryDirectory() as tmp, patch('openjutsu.request_json', side_effect=[{'system': {'comfyui_version': '0.42.0'}}, {}]) as request:
            workspace = openjutsu.Workspace(tmp)
            workspace.configure(openjutsu.DEFAULT_BACKEND)
            result = workspace.check()
            self.assertTrue(result['connected'])
            self.assertEqual(result['version'], '0.42.0')
            self.assertTrue(result['missing'])
            self.assertEqual([call.args[0].split('/')[-1] for call in request.call_args_list], ['system_stats', 'object_info'])

    def test_configuration_and_queue_freeze(self):
        with tempfile.TemporaryDirectory() as tmp, patch('app.gpu_info', return_value={}), patch('app.install_ready', return_value=False):
            studio = Studio(tmp)
            studio.openjutsu.configure('http://127.0.0.1:8200')
            self.assertEqual(json.loads((Path(tmp) / 'openjutsu-settings.json').read_text())['backend'], 'http://127.0.0.1:8200')
            process = Mock()
            process.poll.return_value = None
            studio.openjutsu.processes = [process]
            with self.assertRaisesRegex(ValueError, 'OpenJutsu'):
                studio.enqueue('video', {})
            with self.assertRaisesRegex(ValueError, 'OpenJutsu'):
                studio.queue_action({'action': 'resume'})
            with self.assertRaisesRegex(ValueError, 'Stop'):
                studio.openjutsu.configure('http://127.0.0.1:8188')
            self.assertFalse(studio.state['busy'])

    def test_stop_preserves_live_backend_job_and_external_process(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = openjutsu.Workspace(tmp)
            owned = Mock()
            owned.poll.return_value = None
            workspace.processes = [owned]
            workspace.logs = [io.StringIO()]
            with patch('openjutsu.request_json', return_value={'queue_running': [[1]], 'queue_pending': []}), patch('avatar_runtime.stop_process') as stop:
                with self.assertRaisesRegex(ValueError, 'Finish or cancel'):
                    workspace.stop()
                stop.assert_not_called()
            with patch('openjutsu.request_json', return_value={'queue_running': [], 'queue_pending': []}), patch('avatar_runtime.stop_process') as stop:
                workspace.stop()
                stop.assert_called_once_with(owned)
                self.assertFalse(workspace.processes)
                self.assertEqual(workspace.url, '')

    def test_snapshot_does_not_probe_or_autostart(self):
        with tempfile.TemporaryDirectory() as tmp, patch('openjutsu.request_json') as request, patch('openjutsu.subprocess.Popen') as launch:
            state = openjutsu.Workspace(tmp).snapshot()
            self.assertFalse(state['running'])
            self.assertFalse(state['ready'])
            self.assertEqual(state['url'], '')
            request.assert_not_called()
            launch.assert_not_called()

    def test_editor_url_is_hidden_until_http_and_proxy_are_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = openjutsu.Workspace(tmp)
            workspace.configure('http://127.0.0.1:8200', 'external')
            process = Mock()
            process.poll.return_value = None
            response = MagicMock()
            response.__enter__.return_value.status = 200
            observed = []
            opener = Mock()
            def open_editor(*args, **kwargs):
                observed.append(workspace.snapshot())
                return response
            opener.open.side_effect = open_editor
            with patch('openjutsu.ready', return_value=True), patch('openjutsu.unused_port', side_effect=[8201, 8202]), \
                    patch('openjutsu.subprocess.Popen', return_value=process), \
                    patch('openjutsu.urllib.request.build_opener', return_value=opener), \
                    patch('openjutsu.request_json', return_value={'status': 'healthy'}), patch('avatar_runtime.stop_process'):
                try:
                    workspace.start('http://127.0.0.1:9000', lambda *_:None, threading.Event())
                    self.assertTrue(observed)
                    self.assertTrue(observed[0]['owned'])
                    self.assertFalse(observed[0]['running'])
                    self.assertEqual(observed[0]['url'], '')
                    self.assertTrue(workspace.snapshot()['running'])
                    self.assertEqual(workspace.snapshot()['url'], 'http://127.0.0.1:8201')
                finally:workspace.close()
            self.assertFalse(workspace.http_ready)

    def test_http_access_and_local_editor_policy(self):
        with tempfile.TemporaryDirectory() as tmp, patch('app.gpu_info', return_value={}):
            studio = Studio(tmp)
            server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), make_handler(studio, lambda: None))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            def request(path, data=None, token=None):
                connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
                try:
                    connection.request('GET' if data is None else 'POST', path,
                        None if data is None else json.dumps(data),
                        {'X-Wan-Token': token or '', 'Content-Type': 'application/json'})
                    response = connection.getresponse()
                    return response.status, dict(response.getheaders()), response.read()
                finally:
                    connection.close()
            try:
                status, headers, body = request('/?session=' + studio.token)
                self.assertEqual(status, 200)
                self.assertIn("frame-src http://127.0.0.1:*", headers['Content-Security-Policy'])
                self.assertIn("connect-src 'self'", headers['Content-Security-Policy'])
                self.assertIn(b'/studio-openjutsu.js', body)
                self.assertEqual(request('/studio-openjutsu.js')[0], 200)
                self.assertEqual(request('/api/openjutsu/settings', {'backend': 'http://127.0.0.1:8200'})[0], 403)
                self.assertEqual(request('/api/openjutsu/settings', {'backend': 'http://example.com:8200'}, studio.token)[0], 400)
                self.assertEqual(request('/api/openjutsu/settings', {'backend': 'http://127.0.0.1:8200'}, studio.token)[0], 200)
                self.assertEqual(studio.openjutsu.backend, 'http://127.0.0.1:8200')
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

    def test_start_pauses_native_queue_without_starting_inference(self):
        with tempfile.TemporaryDirectory() as tmp, patch('app.gpu_info', return_value={}):
            studio = Studio(tmp)
            with patch.object(studio.openjutsu, 'start') as start, patch.object(studio.engine, 'stop') as stop:
                studio.openjutsu_action('start', {}, 'http://127.0.0.1:9000')
                studio.worker.join(timeout=3)
                self.assertTrue(studio.queue.paused)
                self.assertFalse(studio.state['busy'])
                stop.assert_called_once()
                start.assert_called_once()

    def test_component_port_persists_across_backend_settings_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / 'openjutsu-settings.json').write_text(json.dumps({'backend': openjutsu.DEFAULT_BACKEND, 'app_port': 34567}))
            workspace = openjutsu.Workspace(tmp)
            workspace.configure('http://127.0.0.1:8200')
            self.assertEqual(openjutsu.Workspace(tmp).app_port, 34567)


if __name__ == '__main__':
    unittest.main()
