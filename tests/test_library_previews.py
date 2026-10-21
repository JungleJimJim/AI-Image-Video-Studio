"""Preview requests must reuse completed files and never hold the Studio lock."""
import http.server
import json
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import urllib.error
import urllib.request

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from app import make_handler
from media import Thumbnails


class PreviewTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.source=self.root/'source.png';self.source.write_bytes(b'existing media fixture')
        self.item=dict(id='picture',path=str(self.source),name='picture',created='2026-10-18')
        self.cache=Thumbnails(self.root)
        self.cache.work=Mock()  # No decoder or generation is needed for HTTP contracts.

    def test_cache_is_reused_and_source_changes_invalidate_it(self):
        first=self.cache.describe(self.item,'image')
        self.assertEqual(first['status'],'pending')
        self.cache.describe(self.item,'image')
        self.assertEqual(len(self.cache.pending),1)
        target=self.root/'thumbnails'/(first['key']+'.jpg')
        target.parent.mkdir();target.write_bytes(b'completed preview')
        self.assertEqual(self.cache.get(self.item,'image'),target)
        self.assertEqual(self.cache.describe(self.item,'image')['status'],'ready')
        self.source.write_bytes(b'a changed source file')
        changed=self.cache.describe(self.item,'image')
        self.assertNotEqual(changed['key'],first['key'])
        self.assertEqual(changed['status'],'pending')
        self.source.unlink()
        self.assertEqual(self.cache.describe(self.item,'image'),{'status':'unavailable'})

    def test_incomplete_worker_result_does_not_leave_previews_pending_forever(self):
        cache=Thumbnails(self.root)
        cache.queue.put(('key',{}));cache.pending.add('key')
        def incomplete(*args,**kwargs):cache.stop.set();return []
        with patch('media.process',side_effect=incomplete):cache.work()
        self.assertFalse(cache.pending)
        self.assertIn('key',cache.failed)

    def test_batch_readiness_authentication_and_immutable_http_cache(self):
        lock=threading.Lock()
        studio=SimpleNamespace(token='test-token',lock=lock,images=[self.item],videos=[],thumbnails=self.cache)
        server=http.server.ThreadingHTTPServer(('127.0.0.1',0),make_handler(studio,Mock()))
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        base=f'http://127.0.0.1:{server.server_port}'
        def get(route,**headers):
            return opener.open(urllib.request.Request(base+route,headers={'X-Wan-Token':'test-token',**headers}),timeout=2)
        original=self.cache.describe
        def unlocked(*args):
            acquired=lock.acquire(blocking=False)
            self.assertTrue(acquired,'Thumbnail disk access held the Studio lock')
            if acquired:lock.release()
            return original(*args)
        try:
            # A status/model scan may hold this lock for seconds during a render.
            with lock:
                with get('/api/library?count=24') as r:page=json.load(r)
            with patch.object(self.cache,'describe',side_effect=unlocked):
                with get('/api/library?count=24') as r:page=json.load(r)
            thumb=page['items'][0]['thumbnail']
            self.assertEqual(thumb['status'],'pending')
            with get('/api/thumbnails?ids=picture,missing') as r:
                status=json.load(r);self.assertEqual(status['missing']['status'],'unavailable')
                self.assertEqual(status['picture']['status'],'pending')
            target=self.root/'thumbnails'/(thumb['key']+'.jpg');target.parent.mkdir();target.write_bytes(b'JPEG fixture')
            route='/thumbnail/picture?token=test-token&v='+thumb['key']
            with get(route) as r:
                self.assertEqual(r.read(),b'JPEG fixture')
                self.assertIn('immutable',r.headers['Cache-Control']);etag=r.headers['ETag']
            with self.assertRaises(urllib.error.HTTPError) as error:get(route,**{'If-None-Match':etag})
            self.assertEqual(error.exception.code,304);error.exception.close()
            for route in ('/api/thumbnails?ids=picture','/thumbnail/picture?token=wrong'):
                with self.assertRaises(urllib.error.HTTPError) as error:get(route,**{'X-Wan-Token':'wrong','If-None-Match':etag})
                self.assertEqual(error.exception.code,403);error.exception.close()
        finally:
            server.shutdown();server.server_close();worker.join(3)


if __name__=='__main__':unittest.main()
