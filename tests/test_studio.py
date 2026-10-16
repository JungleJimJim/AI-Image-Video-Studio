import hashlib
import http.server
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from app import Studio, make_handler
from common import atomic_json, check_install_path, load_json
from downloads import Cancelled, SafeRedirect, download
from engine import build_workflow, validate_options


class WorkflowTests(unittest.TestCase):
    def test_model_and_video_inputs(self):
        opts = validate_options({"prompt": "A lighthouse", "seed": "42", "frames": 33})
        graph = build_workflow(opts, "test")
        self.assertEqual(graph["1"]["inputs"]["unet_name"], "wan_1.3B_exp_e14.safetensors")
        self.assertEqual(graph["6"]["inputs"]["length"], 33)
        self.assertEqual(graph["8"]["inputs"]["seed"], 42)
        self.assertEqual(graph["11"]["inputs"]["format"], "mp4")
        self.assertEqual(graph["11"]["inputs"]["format.codec"], "h264")

    def test_wan_shape_constraints(self):
        for bad in ({"width": 831}, {"frames": 32}, {"height": 2000}, {"steps": 4.3},
                    {"cfg": float("nan")}, {"sampler": "unknown"}, {"seed": "2.5"}, {"seed": str(2**54)}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                validate_options({"prompt": "A lighthouse", **bad})

    def test_empty_prompt_and_random_seed(self):
        with self.assertRaises(ValueError):
            validate_options({"prompt": "  "})
        opts = validate_options({"prompt": "A lighthouse", "seed": ""})
        self.assertGreaterEqual(opts["seed"], 0)
        self.assertLess(opts["seed"], 2**53)

    def test_settings_atomic_preservation(self):
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / "settings.json"
            data = {"output": "D:/Videos", "options": {"seed": 42, "prompt": "coastline"}}
            atomic_json(file, data)
            self.assertEqual(load_json(file, {}), data)
            self.assertEqual(list(Path(tmp).glob("*.tmp")), [])

    def test_install_rejects_unrelated_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "keep.txt").write_text("existing data")
            with self.assertRaises(ValueError):
                check_install_path(root)
            atomic_json(root / "studio-install.json", {"version": "1.0.0"})
            self.assertEqual(check_install_path(root), root.resolve())


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.data = bytes(range(256)) * 8192
        owner = self
        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_GET(self):
                owner.requests.append(self.headers.get("Range"))
                start = 0
                if self.headers.get("Range") and not owner.ignore_range:
                    start = int(self.headers["Range"].split("=")[1].split("-")[0])
                    self.send_response(206)
                    self.send_header("Content-Range", f"bytes {start}-{len(owner.data)-1}/{len(owner.data)}")
                else:
                    self.send_response(200)
                self.send_header("Content-Length", str(len(owner.data) - start))
                self.end_headers()
                self.wfile.write(owner.data[start:])
        self.requests = []
        self.ignore_range = False
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.tmp = tempfile.TemporaryDirectory()
        self.target = Path(self.tmp.name) / "model.safetensors"
        self.spec = {"url": f"http://127.0.0.1:{self.server.server_port}/model", "label": "test model",
                     "size": len(self.data), "sha256": hashlib.sha256(self.data).hexdigest()}

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.tmp.cleanup()

    def fetch(self):
        return download(self.spec, self.target, lambda *args: None, threading.Event())

    def test_resume_and_verified_file_reuse(self):
        self.target.with_suffix(".safetensors.part").write_bytes(self.data[:12345])
        self.fetch()
        self.assertEqual(self.requests[0], "bytes=12345-")
        self.assertTrue(all(request.startswith("bytes=") for request in self.requests))
        self.assertEqual(self.target.read_bytes(), self.data)
        count = len(self.requests)
        self.fetch()
        self.assertEqual(len(self.requests), count)

    def test_server_ignoring_range_restarts_cleanly(self):
        self.ignore_range = True
        self.target.with_suffix(".safetensors.part").write_bytes(self.data[:12345])
        self.fetch()
        self.assertEqual(self.target.read_bytes(), self.data)

    def test_same_size_corruption_is_replaced(self):
        self.target.write_bytes(b"x" * len(self.data))
        self.fetch()
        self.assertEqual(self.target.read_bytes(), self.data)

    def test_cancel_preserves_partial(self):
        partial = self.target.with_suffix(".safetensors.part")
        partial.write_bytes(self.data[:20])
        cancel = threading.Event()
        cancel.set()
        with self.assertRaises(Cancelled):
            download(self.spec, self.target, lambda *args: None, cancel)
        self.assertEqual(partial.read_bytes(), self.data[:20])

    def test_redirect_does_not_leak_token(self):
        req = urllib.request.Request("https://huggingface.co/file", headers={"Authorization": "Bearer private"})
        redirected = SafeRedirect().redirect_request(req, None, 302, "", {}, "https://cdn.example/file")
        self.assertIsNone(redirected.get_header("Authorization"))


class APITests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        with patch("app.gpu_info", return_value={"name": "test GPU", "vram_gb": 16, "driver": "test"}):
            self.studio = Studio(Path(self.tmp.name))
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.studio, lambda: None))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.tmp.cleanup()

    def test_api_requires_per_session_token(self):
        with self.assertRaises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(self.base + "/api/state")
        self.assertEqual(error.exception.code, 403)
        req = urllib.request.Request(self.base + "/api/state", headers={"X-Wan-Token": self.studio.token})
        with urllib.request.urlopen(req) as response:
            self.assertFalse(json.load(response)["ready"])

    def test_foreign_origin_is_rejected(self):
        req = urllib.request.Request(self.base + "/api/cancel", data=b"{}", headers={"X-Wan-Token": self.studio.token, "Origin": "https://example.org"})
        with self.assertRaises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(req)
        self.assertEqual(error.exception.code, 403)

    def test_update_check_requires_token_and_can_run_while_generating(self):
        req=urllib.request.Request(self.base+'/api/updates/check',data=b'{}')
        with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(req)
        self.assertEqual(error.exception.code,403)
        self.studio.state['busy']=True
        release=dict(tag_name='v99.0.0',draft=False,prerelease=False,body='Fixture',assets=[dict(
            name='AIImageVideoStudio-Setup-99.0.0.exe',size=123,state='uploaded',digest='sha256:'+'a'*64,
            browser_download_url='https://github.com/JungleJimJim/AI-Image-Video-Studio/releases/download/v99.0.0/AIImageVideoStudio-Setup-99.0.0.exe')])
        with patch('updates.latest_release',return_value=release),patch('updates.download') as download:
            req=urllib.request.Request(self.base+'/api/updates/check',data=b'{}',headers={'X-Wan-Token':self.studio.token})
            with urllib.request.urlopen(req) as response:info=json.load(response)
        self.assertTrue(info['available']);download.assert_not_called();self.assertTrue(self.studio.state['busy'])

    def test_busy_update_install_rejects_without_stopping_the_current_job(self):
        self.studio.state['busy']=True
        req=urllib.request.Request(self.base+'/api/updates/install',data=b'{"ticket":"fixture"}',headers={'X-Wan-Token':self.studio.token})
        with patch.object(self.studio.updates,'prepare') as prepare,self.assertRaises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(req)
        self.assertEqual(error.exception.code,400);prepare.assert_not_called();self.assertFalse(self.studio.cancel.is_set())

    def test_video_range_and_missing_video(self):
        file = Path(self.tmp.name) / "video.mp4"
        file.write_bytes(bytes(range(256)))
        self.studio.videos.append({"id": "test", "path": str(file)})
        req = urllib.request.Request(self.base + "/video/test?token=" + self.studio.token, headers={"Range": "bytes=20-39"})
        with urllib.request.urlopen(req) as response:
            self.assertEqual(response.status, 206)
            self.assertEqual(response.read(), bytes(range(20, 40)))

    def test_busy_blocks_overlapping_operations(self):
        self.studio.state["busy"] = True
        with self.assertRaises(ValueError):
            self.studio.run_job(lambda: None)
        with self.assertRaises(ValueError):
            self.studio.save_settings({"output": self.tmp.name})

    def test_all_options_have_help(self):
        html = (Path(__file__).resolve().parents[1] / "assets/index.html").read_text(encoding="utf-8")
        from html.parser import HTMLParser
        class Parser(HTMLParser):
            def __init__(self): super().__init__(); self.fields = []; self.help = []
            def handle_starttag(self, tag, attrs):
                attrs = dict(attrs)
                if tag in ("input", "textarea", "select") and 'hidden' not in attrs:
                    self.fields.append(attrs["id"])
                if "data-help" in attrs:
                    self.help.append(attrs["data-help"])
        p = Parser(); p.feed(html)
        aliases = {"hftoken": "token"}
        self.assertTrue(all(aliases.get(field, field) in p.help for field in p.fields))


if __name__ == "__main__":
    unittest.main()
