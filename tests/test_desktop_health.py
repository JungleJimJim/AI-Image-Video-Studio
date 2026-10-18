"""The native heartbeat must not wait on library locks or model scans."""
import http.server
import json
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
import urllib.error
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from app import make_handler


class DesktopHealthTests(unittest.TestCase):
    def setUp(self):
        self.studio = SimpleNamespace(token='test-token', closing=False,
                                     lock=threading.Lock(), snapshot=Mock())
        self.server = http.server.ThreadingHTTPServer(
            ('127.0.0.1', 0), make_handler(self.studio, Mock()))
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()
        self.url = f'http://127.0.0.1:{self.server.server_port}/api/health'
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.worker.join(3)

    def read(self, token='test-token', **headers):
        req = urllib.request.Request(self.url, headers={'X-Wan-Token': token, **headers})
        with self.opener.open(req, timeout=1) as response:
            return json.load(response)

    def test_heartbeat_works_while_library_lock_is_held_without_snapshot(self):
        with self.studio.lock:
            self.assertEqual(self.read(), {'ok': True, 'closing': False})
        self.studio.snapshot.assert_not_called()
        self.studio.closing = True
        self.assertEqual(self.read(), {'ok': True, 'closing': True})

    def test_heartbeat_requires_session_token_and_local_host(self):
        for headers in ({'token': 'wrong'}, {'Host': 'example.com'}):
            with self.subTest(headers=headers):
                with self.assertRaises(urllib.error.HTTPError) as error:
                    self.read(**headers)
                self.assertEqual(error.exception.code, 403)
                error.exception.close()


if __name__ == '__main__':
    unittest.main()
