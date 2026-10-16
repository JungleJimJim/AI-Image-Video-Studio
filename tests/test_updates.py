"""Update validation, handoff and rollback. Never starts inference or a real installer."""
import hashlib
import json
import os
from pathlib import Path
import sys
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from common import APP_EXE, APP_NAME, VERSION, atomic_json
from app import Studio
from downloads import Cancelled
from installer import copy_application
from updates import UpdateManager, apply_update, process_identity, release_offer, wait_for_exit


def release(version='1.6.0'):
    name='AIImageVideoStudio-Setup-'+version+'.exe'
    url='https://github.com/JungleJimJim/AI-Image-Video-Studio/releases/download/v'+version+'/'+name
    return dict(tag_name='v'+version,draft=False,prerelease=False,body='Update fixture',assets=[
        dict(name=name,browser_download_url=url,state='uploaded',size=64,digest='sha256:'+'a'*64)])


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)/'Studio';self.root.mkdir()
        self.app=self.root/APP_EXE;self.app.write_bytes(b'old application')
        atomic_json(self.root/'studio-install.json',dict(app=APP_NAME,version='1.5.2'))
        atomic_json(self.root/'studio-data.json',dict(app=APP_NAME))
        self.manager=UpdateManager(self.root,current='1.5.2',installation=self.root)
        self.report=Mock();self.cancel=threading.Event()

    def tearDown(self):self.temp.cleanup()

    def offered(self):
        with patch('updates.latest_release',return_value=release()):return self.manager.check()

    def test_versions_compare_numerically_and_stale_release_does_not_require_installer(self):
        self.assertTrue(release_offer(release('1.10.0'),'1.9.9')[0]['available'])
        data=release('1.5.2');data['assets']=[]
        public,spec=release_offer(data,'1.6.0')
        self.assertFalse(public['available']);self.assertIsNone(spec)

    def test_rejects_prereleases_missing_checksum_and_foreign_installers(self):
        for field,value in [('draft',True),('prerelease',True),('tag_name','v1.7.0-beta')]:
            data=release();data[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):release_offer(data,'1.5.2')
        for field,value in [('digest',None),('digest','sha256:bad'),('browser_download_url','https://example.org/installer.exe'),('size',-1),('state','new')]:
            data=release();data['assets'][0][field]=value
            with self.subTest(field=field,value=value),self.assertRaises(ValueError):release_offer(data,'1.5.2')

    def test_check_does_not_download_and_network_failure_clears_the_old_offer(self):
        with patch('updates.download') as download:
            info=self.offered();self.assertTrue(info['available']);self.assertTrue(info['can_install'])
            download.assert_not_called()
            with patch('updates.latest_release',side_effect=ValueError('Offline')):info=self.manager.check()
            self.assertEqual(info['status'],'error');self.assertFalse(info['available']);self.assertIsNone(self.manager.offer)
            with self.assertRaises(ValueError):self.manager.prepare('old-ticket',self.report,self.cancel)
            download.assert_not_called()

    def test_prepare_uses_only_the_confirmed_server_offer_and_captures_exact_processes(self):
        info=self.offered()
        atomic_json(self.root/'.studio-instance.json',dict(desktop_pid=999))
        def identity(pid):return dict(pid=pid,created=123,path=str(self.app if pid!=999 else self.root/'host.exe'))
        def download(spec,destination,*args):
            self.assertEqual(spec['sha256'],'a'*64);destination.write_bytes(b'verified fixture');return destination
        with patch('updates.download',side_effect=download),patch('updates.process_identity',side_effect=identity):
            installer,request=self.manager.prepare(info['ticket'],self.report,self.cancel)
        data=json.loads(request.read_text())
        self.assertEqual(data['installation'],str(self.root));self.assertEqual(data['data'],str(self.root))
        self.assertEqual({x['pid'] for x in data['processes']},{os.getpid(),os.getppid(),999})
        self.assertEqual(installer.parent,self.root/'updates/1.6.0')
        self.assertEqual(self.app.read_bytes(),b'old application')

    def test_download_cancel_does_not_create_a_handoff_or_change_app(self):
        info=self.offered()
        with patch('updates.download',side_effect=Cancelled('Cancelled')):
            with self.assertRaises(Cancelled):self.manager.prepare(info['ticket'],self.report,self.cancel)
        self.assertEqual(self.app.read_bytes(),b'old application')
        self.assertFalse((self.root/'updates/1.6.0/apply-update.json').exists())

    def test_process_wait_ignores_reused_pid_and_never_terminates_anything(self):
        old=dict(pid=42,created=123,path='old.exe')
        with patch('updates.process_identity',return_value=old|dict(created=456)),patch('updates.time.sleep') as sleep:
            wait_for_exit([old]);sleep.assert_not_called()
        with patch('updates.process_identity',return_value=old),self.assertRaisesRegex(RuntimeError,'not finished closing'):
            wait_for_exit([old],timeout=0)

    def test_windows_process_identity_can_read_its_own_process(self):
        identity=process_identity(os.getpid())
        self.assertEqual(identity['pid'],os.getpid());self.assertGreater(identity['created'],0)
        self.assertEqual(Path(identity['path']),Path(sys.executable).resolve())

    def test_exited_process_is_not_running_even_when_parent_keeps_its_handle(self):
        process=subprocess.Popen([sys.executable,'-c','pass'])
        self.assertEqual(process.wait(timeout=10),0)
        self.assertIsNone(process_identity(process.pid))
        wait_for_exit([dict(pid=process.pid,created=123,path=str(Path(sys.executable).resolve()))],timeout=0)

    def manifest(self,data_root=None):
        data_root=data_root or self.root
        folder=data_root/'updates'/VERSION;folder.mkdir(parents=True,exist_ok=True)
        file=folder/'apply-update.json'
        atomic_json(file,dict(schema=1,installation=str(self.root),data=str(data_root),current='1.5.2',version=VERSION,processes=[]))
        return file

    def test_apply_preserves_settings_models_media_loras_and_queue_in_both_folder_layouts(self):
        for separate in (False,True):
            with self.subTest(separate=separate):
                atomic_json(self.root/'studio-install.json',dict(app=APP_NAME,version='1.5.2'))
                data=Path(self.temp.name)/'Data' if separate else self.root;data.mkdir(exist_ok=True)
                atomic_json(data/'studio-data.json',dict(app=APP_NAME))
                originals={'settings.json':b'{"keep":"settings"}','queue.json':b'{"paused":true,"jobs":[]}',
                    'runtime/models/model.safetensors':b'weight fixture','loras/style.safetensors':b'lora fixture',
                    'Images/original.png':b'image fixture','Videos/original.mp4':b'video fixture'}
                for name,content in originals.items():
                    file=data/name;file.parent.mkdir(parents=True,exist_ok=True);file.write_bytes(content)
                bundle=Path(self.temp.name)/'Bundle';bundle.mkdir(exist_ok=True);(bundle/APP_EXE).write_bytes(b'new application')
                with (patch('updates.installed_data_path',return_value=data),patch('updates.wait_for_exit') as wait,
                     patch('installer.resource',side_effect=lambda name:bundle/name)):
                    apply_update(self.manifest(data),copy_application,Mock(),relaunch=False)
                wait.assert_called_once();self.assertEqual(self.app.read_bytes(),b'new application')
                for name,content in originals.items():self.assertEqual((data/name).read_bytes(),content)

    def test_new_session_and_changed_installation_prevent_replacement(self):
        copy=Mock();request=self.manifest()
        atomic_json(self.root/'.studio-instance.json',dict(mode='desktop'))
        with self.assertRaisesRegex(RuntimeError,'session is still open'):apply_update(request,copy,Mock(),relaunch=False)
        copy.assert_not_called();(self.root/'.studio-instance.json').unlink()
        atomic_json(self.root/'studio-install.json',dict(app=APP_NAME,version='1.5.3'))
        with self.assertRaisesRegex(ValueError,'changed after'):apply_update(request,copy,Mock(),relaunch=False)
        copy.assert_not_called()

    def test_partial_binary_replacement_rolls_back_app_uninstaller_and_marker(self):
        setup=Path(self.temp.name)/'Setup.exe';setup.write_bytes(b'new setup')
        uninstaller=self.root/'UninstallWanVideoStudio.exe';uninstaller.write_bytes(b'old setup')
        bundle=Path(self.temp.name)/'Bundle';bundle.mkdir();(bundle/APP_EXE).write_bytes(b'new app')
        marker=(self.root/'studio-install.json').read_bytes();replace=os.replace
        def locked(source,dest):
            if Path(dest)==uninstaller:raise PermissionError('locked fixture')
            return replace(source,dest)
        with (patch('installer.resource',side_effect=lambda name:bundle/name),patch.object(sys,'frozen',True,create=True),
             patch.object(sys,'executable',str(setup)),patch('installer.os.replace',side_effect=locked),
             self.assertRaisesRegex(RuntimeError,'files are in use')):
            copy_application(self.root)
        self.assertEqual(self.app.read_bytes(),b'old application');self.assertEqual(uninstaller.read_bytes(),b'old setup')
        self.assertEqual((self.root/'studio-install.json').read_bytes(),marker)
        self.assertFalse(list(self.root.glob('.studio-app-update-*')))

    def test_atomic_save_retries_transient_windows_file_lock(self):
        file=self.root/'settings.json';atomic_json(file,dict(original=True));replace=os.replace
        calls=0
        def transient(source,target):
            nonlocal calls
            calls+=1
            if calls<3:raise PermissionError('transient Windows scanner lock')
            return replace(source,target)
        with patch('common.os.replace',side_effect=transient),patch('common.time.sleep'):
            atomic_json(file,dict(updated=True))
        self.assertEqual(json.loads(file.read_text()),dict(updated=True));self.assertEqual(calls,3)

    def test_permanent_save_failure_keeps_the_previous_settings(self):
        file=self.root/'settings.json';atomic_json(file,dict(original=True));original=file.read_bytes()
        with patch('common.os.replace',side_effect=PermissionError('locked')),patch('common.time.sleep'),self.assertRaises(PermissionError):
            atomic_json(file,dict(updated=True))
        self.assertEqual(file.read_bytes(),original);self.assertFalse(list(self.root.glob('settings.json*.tmp')))

    def test_studio_busy_blocks_update_and_failed_launch_keeps_app_open(self):
        with patch('app.gpu_info',return_value={}):studio=Studio(self.root)
        studio.updates=self.manager;info=self.offered();shutdown=Mock()
        studio.state['busy']=True
        with patch.object(self.manager,'prepare') as prepare,self.assertRaisesRegex(ValueError,'current operation'):
            studio.install_update(info['ticket'],shutdown)
        prepare.assert_not_called();studio.state['busy']=False
        with (patch.object(self.manager,'prepare',return_value=(self.root/'fixture.exe',self.root/'request.json')),
             patch.object(self.manager,'launch',side_effect=OSError('fixture start failed'))):
            studio.install_update(info['ticket'],shutdown);studio.worker.join(3)
        shutdown.assert_not_called();self.assertFalse(studio.closing);self.assertTrue(studio.queue.paused)
        self.assertIn('fixture start failed',studio.state['error'])

    def test_successful_handoff_shuts_down_only_after_download_and_pauses_queue(self):
        with patch('app.gpu_info',return_value={}):studio=Studio(self.root)
        studio.updates=self.manager;info=self.offered();closed=threading.Event()
        with (patch.object(self.manager,'prepare',return_value=(self.root/'fixture.exe',self.root/'request.json')),
             patch.object(self.manager,'launch') as launch):
            studio.install_update(info['ticket'],closed.set);studio.worker.join(3)
        self.assertTrue(closed.wait(1));self.assertTrue(studio.closing);self.assertTrue(studio.queue.paused)
        launch.assert_called_once()


if __name__=='__main__':unittest.main()
