import json
from pathlib import Path
import runpy
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import wave
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import local_voices,voices
from common import atomic_json
from media import catalog_page

class LocalVoiceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
    def tearDown(self):self.temp.cleanup()
    def options(self,**extra):
        return dict(protocol='local',model='kokoro',text='Hello world',seed='123',**extra)
    def test_kokoro_cpu_defaults_and_no_stale_reference(self):
        o=voices.validate_options(self.options(reference_id='old',transcript=''))
        self.assertEqual(o['device'],'cpu');self.assertEqual(o['voice'],'af_heart');self.assertEqual(o['reference_id'],'')
    def test_qwen_clone_reference_and_optional_transcript(self):
        o=voices.validate_options(dict(protocol='local',model='qwen_tts',text='Hello',reference_id='reference',device='cuda',seed='123'))
        self.assertEqual(o['transcript'],'');self.assertEqual(o['device'],'cuda')
        with self.assertRaisesRegex(ValueError,'reference recording'):
            voices.validate_options(dict(protocol='local',model='qwen_tts',text='Hello'))
    def test_invalid_device_voice_language_and_speed(self):
        for extra in [dict(device='cuda'),dict(voice='unknown'),dict(language='French'),dict(speed='nan'),dict(speed=3)]:
            with self.assertRaises(ValueError):voices.validate_options(self.options(**extra))
    def test_local_script_limits(self):
        with self.assertRaisesRegex(ValueError,'shorter'):voices.validate_options(dict(protocol='local',model='kokoro',text='x'*4001))
    def test_native_manifest_is_pinned_and_paths_are_relative(self):
        for spec in local_voices.catalog().values():
            self.assertTrue(spec['requirements'])
            for item in spec['files']:
                self.assertEqual(len(item['sha256']),64);self.assertGreater(item['size'],0)
                self.assertFalse(Path(item['filename']).is_absolute());self.assertNotIn('..',Path(item['filename']).parts)
                self.assertTrue(item['url'].startswith('https://'))
        qwen=local_voices.catalog()['qwen_tts']
        self.assertIn('torch==2.9.1+cu128',qwen['requirements'])
        self.assertEqual(qwen['extra_index'],'https://download.pytorch.org/whl/cu128')
    def test_model_folder_rejects_unknown_model(self):
        with self.assertRaises(ValueError):local_voices.folder(self.root,'../settings')
    def test_worker_chunking_does_not_drop_words(self):
        worker=runpy.run_path(str(Path(__file__).resolve().parents[1]/'assets/local_voice_worker.py'))
        text=' '.join('word'+str(i) for i in range(250))
        chunks=worker['chunks'](text,100)
        self.assertEqual(' '.join(chunks),text);self.assertTrue(all(len(x)<=100 for x in chunks))
    def test_local_generation_uses_private_worker_and_cleans_requests(self):
        o=voices.validate_options(self.options())
        def fake_process(command,log,report,cancel,label):
            job=json.loads(Path(command[-1]).read_text())
            self.assertEqual(job['model'],'kokoro');self.assertIn('packages',job)
            with wave.open(job['target'],'wb') as wav:
                wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(24000);wav.writeframes(b'\0\0'*100)
        with patch('local_voices.check',return_value={}),patch('local_voices.process',side_effect=fake_process):
            content,seconds=voices.generate(self.root,o,None,lambda *a:None,threading.Event())
        self.assertTrue(content.startswith(b'RIFF'));self.assertEqual(list((self.root/'voice-jobs').iterdir()),[])
    def test_qwen_rejects_long_reference_before_worker(self):
        o=voices.validate_options(dict(protocol='local',model='qwen_tts',text='Hello',reference_id='id'))
        with patch('local_voices.check',return_value={}),patch('local_voices.process') as worker:
            with self.assertRaisesRegex(ValueError,'15 seconds'):
                local_voices.generate(self.root,o,dict(path='unused',duration=16),lambda *a:None,threading.Event())
            worker.assert_not_called()
    def test_library_order_remains_creation_date_not_title(self):
        older=dict(id='old',name='AAA.png',created='2026-10-28 12:00',options=dict(prompt='AAA prompt goes first alphabetically now'))
        newer=dict(id='new',name='ZZZ.png',created='2026-10-29 12:00',options=dict(prompt='ZZZ prompt goes last alphabetically now'))
        result=catalog_page([older,newer],[],{})
        self.assertEqual([x['id'] for x in result['items']],['new','old'])

if __name__=='__main__':unittest.main()
