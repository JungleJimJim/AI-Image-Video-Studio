import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock,patch
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from app import Studio
from downloads import Cancelled
import video_faceswap as vf


class VideoFaceswapTests(unittest.TestCase):
    def raw(self,**changes):return dict(source_id='target',reference_id='identity')|changes

    def test_validation_and_no_arbitrary_models_or_bad_values(self):
        self.assertEqual(vf.validate(self.raw())['model'],'facefusion_video')
        for change in [dict(model='bfs'),dict(source_id='../file'),dict(reference_id=''),dict(face_position=-1),dict(reference_frame=1.5),dict(similarity=float('nan')),dict(provider='arbitrary'),dict(pixel_boost='1024x1024')]:
            with self.subTest(change=change),self.assertRaises(ValueError):vf.validate(self.raw(**change))

    def test_command_keeps_reference_target_order_and_source_audio(self):
        o=vf.validate(self.raw(face_position=2,reference_frame=51))
        command=vf.arguments(o,'C:/Reference person.png','C:/Target clip.mp4','result.mp4',Path('private'))
        self.assertEqual(command[command.index('--source-paths')+1],'C:/Reference person.png')
        self.assertEqual(command[command.index('--target-path')+1],'C:/Target clip.mp4')
        self.assertEqual(command[command.index('--reference-face-position')+1],'2')
        self.assertEqual(command[command.index('--reference-frame-number')+1],'51')
        self.assertEqual(command[command.index('--output-audio-volume')+1],'100')
        self.assertNotIn('--skip-audio',command)

    def test_queue_preserves_sources_priority_and_editing(self):
        with tempfile.TemporaryDirectory() as tmp,patch('app.gpu_info',return_value={}),patch('video_faceswap.ready',return_value=True):
            studio=Studio(tmp);studio.queue.paused=True
            for key,records in [('target',studio.videos),('identity',studio.images)]:
                file=Path(tmp)/key;file.write_bytes(b'original');records.append(dict(id=key,path=str(file),name=key,frames=100))
            id=studio.enqueue('faceswap_video',self.raw(),8)
            studio.queue_action(dict(action='update',id=id,options=self.raw(face_position=1),priority=10))
            job=studio.queue.get(id);self.assertEqual(job['priority'],10);self.assertEqual(job['options']['face_position'],1)
            with self.assertRaises(ValueError):studio.enqueue('faceswap_video',self.raw(reference_frame=100),5)
            studio.queue_action(dict(action='cancel',id=id));self.assertEqual(job['status'],'cancelled')
            for key in ('target','identity'):self.assertEqual((Path(tmp)/key).read_bytes(),b'original')

    def test_run_publishes_a_copy_and_cleans_only_private_work(self):
        with tempfile.TemporaryDirectory() as tmp,patch('video_faceswap.ready',return_value=True):
            root=Path(tmp);source=root/'original.mp4';source.write_bytes(b'original')
            reference=root/'identity.png';reference.write_bytes(b'portrait')
            def complete(command,*args,**kwargs):Path(command[command.index('--output-path')+1]).write_bytes(b'video'*100)
            with patch('video_faceswap.wait_process',side_effect=complete),patch('media.process',return_value=dict(width=640,height=480,duration=2,fps=24)):
                target,_,info=vf.run(root,dict(path=str(source)),dict(path=str(reference)),vf.validate(self.raw()),root/'Library',Mock(),threading.Event())
            self.assertTrue(target.is_file());self.assertEqual(info['fps'],24)
            self.assertEqual(source.read_bytes(),b'original');self.assertEqual(reference.read_bytes(),b'portrait')
            self.assertFalse(list((root/'video-faceswap-jobs').iterdir()))

    def test_failed_or_cancelled_job_never_publishes_partial_output(self):
        with tempfile.TemporaryDirectory() as tmp,patch('video_faceswap.ready',return_value=True):
            root=Path(tmp)
            with patch('video_faceswap.wait_process',side_effect=Cancelled('cancelled')),self.assertRaises(Cancelled):
                vf.run(root,dict(path='target.mp4'),dict(path='identity.png'),vf.validate(self.raw()),root/'Library',Mock(),threading.Event())
            self.assertFalse((root/'Library').exists());self.assertFalse(list((root/'video-faceswap-jobs').iterdir()))

    def test_source_import_copy_and_cancellation(self):
        with tempfile.TemporaryDirectory() as tmp,patch('media.process',return_value=dict(width=640,height=480,duration=2,fps=24)):
            root=Path(tmp);source=root/'clip.mp4';source.write_bytes(b'original')
            item=vf.import_video(root,source,root/'Library',Mock(),threading.Event())
            self.assertNotEqual(Path(item['path']),source);self.assertEqual(Path(item['path']).read_bytes(),source.read_bytes())
            cancel=threading.Event();cancel.set()
            with self.assertRaises(Cancelled):vf.import_video(root,source,root/'Library',Mock(),cancel)
            self.assertFalse(list((root/'Library/Videos').glob('*.importing')))

    def test_pins_include_all_runtime_models_without_reusing_or_copying_qwen(self):
        config=vf.catalog()
        self.assertEqual(config['version'],'3.9.1')
        for file in [config['archive'],*config['wheels'],*config['models'],config['ffmpeg']]:
            self.assertEqual(len(file['sha256']),64);self.assertGreater(file['size'],0)
        self.assertTrue(all('/resolve/main/' not in f['url'] for f in config['models']))
        self.assertEqual(len({f['filename'] for f in config['models']}),len(config['models']))
        self.assertTrue(any('hyperswap' in f['filename'] for f in config['models']))

    def test_archive_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'source.zip'
            with zipfile.ZipFile(path,'w') as archive:archive.writestr('top/../../escape.py','unsafe')
            with self.assertRaises(ValueError):vf.extract_code(path,Path(tmp)/'code')
