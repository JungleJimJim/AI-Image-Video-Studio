import http.server
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from common import atomic_json, load_json
from app import Studio, make_handler
import library_actions as actions
from media_storage import metadata_path

class LibraryFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.image = dict(id='a'*24, name='image.png', path=str(self.root/'Library/Images/image.png'), kind='imported', created='2026-10-29')
        self.video = dict(id='b'*24, name='video.mp4', path=str(self.root/'Library/Videos/video.mp4'), created='2026-10-28')
        self.images = [self.image]; self.videos = [self.video]
        for item, content in [(self.image,b'image original'),(self.video,b'video original')]:
            path=Path(item['path']);path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(content)
            atomic_json(metadata_path(path), item)
        actions.index_write(self.root,self.images,self.videos)
    def tearDown(self):
        self.temp.cleanup()

class LibraryActionTests(LibraryFixture):
    def test_mixed_trash_restore_preserves_bytes_and_sidecars(self):
        result=actions.trash(self.root,self.images,self.videos,[self.image['id'],self.video['id']])
        self.assertEqual(result['count'],2);self.assertFalse(Path(self.image['path']).exists())
        self.assertFalse(metadata_path(self.image['path']).exists())
        self.assertEqual(load_json(self.root/'images.json',None),[])
        self.assertEqual(len(actions.trash_list(self.root)),1)
        restored=actions.restore(self.root,result['images'],result['videos'],result['batch'])
        self.assertEqual(Path(self.image['path']).read_bytes(),b'image original')
        self.assertEqual(Path(self.video['path']).read_bytes(),b'video original')
        self.assertEqual(load_json(metadata_path(self.image['path']),{})['id'],self.image['id'])
        self.assertEqual(restored['images'],self.images);self.assertEqual(restored['videos'],self.videos)
        self.assertEqual(actions.trash_list(self.root),[])
    def test_invalid_selection_changes_nothing(self):
        for ids in [[],['missing'],[None],['x']*501]:
            with self.assertRaises(ValueError):actions.trash(self.root,self.images,self.videos,ids)
        self.assertTrue(Path(self.image['path']).is_file())
    def test_unrelated_json_and_shared_media_are_preserved(self):
        sidecar=Path(self.image['path']).with_suffix('.json');sidecar.write_text('{"unrelated":true}')
        alias={**self.image,'id':'c'*24}
        result=actions.trash(self.root,[self.image,alias],self.videos,[self.image['id']])
        self.assertTrue(Path(self.image['path']).is_file());self.assertTrue(sidecar.is_file())
        self.assertEqual(result['images'],[alias])
    def test_restore_never_overwrites_a_replacement(self):
        result=actions.trash(self.root,self.images,self.videos,[self.image['id']])
        Path(self.image['path']).write_bytes(b'replacement')
        with self.assertRaisesRegex(ValueError,'will not be overwritten'):
            actions.restore(self.root,result['images'],result['videos'],result['batch'])
        self.assertEqual(Path(self.image['path']).read_bytes(),b'replacement')
        self.assertEqual(len(actions.trash_list(self.root)),1)
    def test_move_failure_rolls_back_files_and_indexes(self):
        rename=Path.rename;calls=0
        def fail_second(path,target):
            nonlocal calls
            calls+=1
            if calls==2:raise OSError('injected move failure')
            return rename(path,target)
        with patch.object(Path,'rename',fail_second):
            with self.assertRaisesRegex(OSError,'injected'):
                actions.trash(self.root,self.images,self.videos,[self.image['id'],self.video['id']])
        self.assertEqual(Path(self.image['path']).read_bytes(),b'image original')
        self.assertEqual(load_json(self.root/'images.json',[]),self.images)
        self.assertEqual(actions.trash_list(self.root),[])
    def test_interrupted_delete_recovers_on_startup(self):
        token='e'*32;source=Path(self.image['path']);target=source.parent/'.studio-trash'/token/'image.png'
        target.parent.mkdir(parents=True);source.rename(target)
        journal=dict(id=token,status='pending',items=[{**self.image,'media_type':'image'}],moves=[dict(source=str(source),target=str(target))],before_images=self.images,before_videos=self.videos)
        atomic_json(actions.manifest_path(self.root,token),journal)
        actions.index_write(self.root,[],self.videos)
        self.assertEqual(actions.recover(self.root),[])
        self.assertTrue(source.is_file());self.assertEqual(load_json(self.root/'images.json',[]),self.images)
    def test_zip_contains_originals_and_handles_duplicate_names(self):
        second={**self.image,'id':'c'*24,'path':str(self.root/'other/image.png')}
        Path(second['path']).parent.mkdir();Path(second['path']).write_bytes(b'second original')
        items=actions.selected([self.image,second],self.videos,[self.image['id'],second['id'],self.video['id']])
        result=actions.export_zip(self.root,items)
        with zipfile.ZipFile(result['path']) as z:
            self.assertEqual(len(z.namelist()),3);self.assertEqual(z.read('Images/image.png'),b'image original')
            self.assertEqual(z.read('Videos/video.mp4'),b'video original')
            self.assertEqual(len(set(z.namelist())),3)
        self.assertTrue(Path(self.image['path']).is_file())
    def test_missing_file_or_insufficient_space_produces_no_export(self):
        items=actions.selected(self.images,self.videos,[self.image['id']])
        with patch('library_actions.shutil.disk_usage',return_value=type('Space',(),{'free':0})()):
            with self.assertRaisesRegex(ValueError,'free space'):actions.export_zip(self.root,items)
        self.assertEqual(list((self.root/'temp/library-exports').glob('*.zip')),[])
    def test_invalid_batch_cannot_escape_trash_folder(self):
        with self.assertRaises(ValueError):actions.restore(self.root,self.images,self.videos,'../settings')
    def test_queue_reference_detection(self):
        self.assertTrue(actions.references({'options':{'references':[self.image['id']]}},{self.image['id']},set()))
        self.assertFalse(actions.references({'source':'unrelated'},{self.image['id']},set()))

class LibraryActionAPITests(LibraryFixture):
    # Use only disposable media. None of these tests loads a model.
    def setUp(self):
        super().setUp()
        with patch('app.gpu_info',return_value={'name':'fixture','vram_gb':16}):self.studio=Studio(self.root)
        self.server=http.server.ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.studio,lambda:None))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.base='http://127.0.0.1:'+str(self.server.server_port)
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();super().tearDown()
    def request(self,route,data=None,auth=True,origin=None):
        headers={'X-Wan-Token':self.studio.token} if auth else {}
        if origin:headers['Origin']=origin
        req=urllib.request.Request(self.base+route,data=None if data is None else json.dumps(data).encode(),headers=headers)
        return urllib.request.urlopen(req)
    def test_authorization_confirmation_and_foreign_origin(self):
        for auth,origin,confirmed in [(False,None,True),(True,'https://example.org',True),(True,None,False)]:
            with self.assertRaises(urllib.error.HTTPError):
                self.request('/api/library/delete',dict(ids=[self.image['id']],confirmed=confirmed),auth,origin)
        self.assertTrue(Path(self.image['path']).is_file())
    def test_delete_restore_and_revision(self):
        self.studio.state['latest_media']=self.image
        with self.request('/api/library/delete',dict(ids=[self.image['id']],confirmed=True)) as r:result=json.load(r)
        self.assertEqual(self.studio.revision,1);self.assertIsNone(self.studio.state['latest_media'])
        with self.request('/api/library/restore',dict(batch=result['batch'])):pass
        self.assertEqual(self.studio.revision,2);self.assertTrue(Path(self.image['path']).is_file())
    def test_busy_or_queued_sources_cannot_be_deleted(self):
        self.studio.state['busy']=True
        with self.assertRaises(urllib.error.HTTPError):self.request('/api/library/delete',dict(ids=[self.image['id']],confirmed=True))
        self.studio.state['busy']=False
        self.studio.queue.jobs=[dict(id='job',status='queued',options=dict(source_image=self.image['id']))]
        with self.assertRaises(urllib.error.HTTPError):self.request('/api/library/delete',dict(ids=[self.image['id']],confirmed=True))
        self.assertTrue(Path(self.image['path']).is_file())
    def test_zip_download_is_authenticated_and_uses_zip_filename(self):
        with self.request('/api/library/export',dict(ids=[self.image['id'],self.video['id']])) as r:result=json.load(r)
        route='/library-export/'+result['id']
        with self.assertRaises(urllib.error.HTTPError):self.request(route,auth=False)
        with self.request(route+'?token='+self.studio.token,auth=False) as r:
            self.assertEqual(r.headers.get_content_type(),'application/zip')
            self.assertIn('.zip',r.headers['Content-Disposition']);self.assertTrue(r.read().startswith(b'PK'))
    def test_library_viewer_asset_is_served(self):
        with self.request('/studio-library-viewer.js') as r:self.assertEqual(r.read(),(Path(__file__).resolve().parents[1]/'assets/studio-library-viewer.js').read_bytes())

if __name__=='__main__':unittest.main()
