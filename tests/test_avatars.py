"""Avatar validation and queue/media preservation. No model inference is run."""
import base64
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import wave

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from app import Studio
from common import load_json
from media_storage import metadata_path
import avatars
from packs import catalog

class AvatarTests(unittest.TestCase):
    def setUp(self):
        sound=patch('app.play_completion_ping');sound.start();self.addCleanup(sound.stop)
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        with patch('app.gpu_info',return_value={}):self.studio=Studio(self.root)
        self.studio.queue.paused=True
        self.image=self.root/'portrait.png';self.image.write_bytes(b'original portrait')
        self.video=self.root/'source.mp4';self.video.write_bytes(b'original video')
        self.audio=self.root/'voice.wav'
        with wave.open(str(self.audio),'wb') as voice:
            voice.setparams((1,2,48000,0,'NONE','not compressed'));voice.writeframes(b'\0\0'*48000*6)
        self.studio.images=[dict(id='portrait',path=str(self.image),name='Portrait')]
        self.studio.videos=[dict(id='video',path=str(self.video),name='Source video')]
        self.studio.recordings=[dict(id='voice',path=str(self.audio),name='ElevenLabs export.wav',duration=6)]

    def options(self,**changes):
        return dict(model='avatar_echo',source_id='portrait',source_type='image',audio_id='voice',seed=42,**changes)

    def test_all_five_download_packs_are_pinned_and_usable_with_recordings(self):
        packs=catalog()
        for key in avatars.MODELS:
            pack=packs[key];self.assertEqual(pack['kind'],'avatar');self.assertTrue(pack['avatar_runtime'])
            self.assertTrue(pack['files']);self.assertIn('image',pack['input_types'])
            for file in pack['files']:
                self.assertRegex(file['sha256'],r'^[a-f0-9]{64}$')
                self.assertRegex(file['url'],r'/resolve/[a-f0-9]{40}/')
                self.assertGreater(file['size'],0)

    def test_invalid_settings_never_start_an_engine(self):
        for change in ({'model':'unknown'},{'model':'avatar_echo','source_type':'video'},
                {'width':1024},{'duration':float('nan')},{'audio_start':-1},{'seed':'1.5'},
                {'source_id':''},{'audio_id':''},{'variant':'teacher'},{'randomize_seed':'yes'}):
            with self.subTest(change=change),self.assertRaises(ValueError):
                avatars.validate_options(self.options()|change)

    def test_avatar_queue_freezes_source_recording_seed_range_and_output(self):
        with patch('app.pack_ready',return_value=True):
            identifier=self.studio.enqueue('avatar',self.options(),9)
            self.studio.save_settings({'output':str(self.root/'different Library')})
        item=self.studio.queue.get(identifier)
        self.assertEqual(item['options']['seed'],42);self.assertEqual(item['options']['audio_id'],'voice')
        self.assertEqual(item['options']['source_id'],'portrait');self.assertEqual(item['priority'],9)
        self.assertEqual(Path(item['output']),self.root/'Library')
        self.assertFalse(self.studio.state['busy'])

    def test_generated_result_keeps_source_and_saves_model_audio_seed_metadata(self):
        target=self.root/'Library/Videos/avatar.mp4';target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(b'fixture output, not a generated video')
        result=dict(width=512,height=512,duration=5,frames=125,fps=25)
        with patch('app.pack_ready',return_value=True),patch('avatars.generate',return_value=(target,.1,result)) as generate:
            self.studio.generate_avatar(self.options())
            self.studio.worker.join(5)
        self.assertFalse(self.studio.state['error']);generate.assert_called_once()
        saved=load_json(self.root/'library.json',[])[-1]
        self.assertEqual(saved['kind'],'talking_avatar');self.assertEqual(saved['audio_name'],'ElevenLabs export.wav')
        self.assertEqual(saved['options']['model'],'avatar_echo');self.assertEqual(saved['options']['seed'],42)
        self.assertEqual(saved['parent_id'],'portrait')
        self.assertEqual(self.image.read_bytes(),b'original portrait');self.assertEqual(self.video.read_bytes(),b'original video')
        self.assertEqual(load_json(metadata_path(target),{}),saved)

    def test_missing_audio_or_range_past_end_is_rejected_before_queueing(self):
        with patch('app.pack_ready',return_value=True):
            for change in ({'audio_id':'missing'},{'audio_start':6},{'source_id':'missing'}):
                with self.subTest(change=change),self.assertRaises(ValueError):self.studio.enqueue('avatar',self.options()|change)
        self.assertEqual(self.studio.queue.jobs,[])

    def test_last_audio_range_is_clamped_and_video_models_allow_video_source(self):
        with patch('app.pack_ready',return_value=True):
            _,options=self.studio.generate_avatar(self.options()|dict(audio_start=4,duration=5),prepare=True)
            self.assertEqual(options['duration'],2)
            for model in ('avatar_infinite','avatar_musetalk'):
                _,options=self.studio.generate_avatar(self.options()|dict(model=model,source_id='video',source_type='video'),prepare=True)
                self.assertEqual(options['source_type'],'video')

    def test_voice_import_rejects_bad_data_without_launching_decoder(self):
        with patch('avatars.subprocess.run') as run:
            for value in ('not audio','data:audio/wav;base64,???','data:audio/wav;base64,'):
                with self.assertRaises(ValueError):avatars.import_audio(self.root,{'data':value},lambda *a:None,threading.Event())
            run.assert_not_called()

    def test_cancellation_stops_only_owned_avatar_process(self):
        from unittest.mock import Mock
        cancel=threading.Event();cancel.set()
        process=Mock();process.poll.return_value=None
        with patch('avatars.avatar_runtime.ready',return_value=True),patch('avatars.subprocess.Popen',return_value=process),patch('avatars.avatar_runtime.stop_process') as stop:
            with self.assertRaises(avatars.Cancelled):avatars.generate(self.root,self.studio.images[0],self.studio.recordings[0],avatars.validate_options(self.options()),self.root/'Library',lambda *a:None,cancel)
        stop.assert_called_once_with(process)

    def test_audio_clipping_preserves_sample_rate_and_final_samples(self):
        spec=importlib.util.spec_from_file_location('avatar_worker_test',ROOT/'assets/avatar_worker.py')
        worker=importlib.util.module_from_spec(spec);spec.loader.exec_module(worker)
        target=self.root/'clip.wav'
        duration=worker.clip_voice(self.audio,target,5,5)
        self.assertEqual(duration,1)
        with wave.open(str(target),'rb') as voice:
            self.assertEqual(voice.getframerate(),48000);self.assertEqual(voice.getnframes(),48000)

    def test_echo_padding_preserves_the_final_audio_and_original_recording(self):
        spec=importlib.util.spec_from_file_location('avatar_worker_padding_test',ROOT/'assets/avatar_worker.py')
        worker=importlib.util.module_from_spec(spec);spec.loader.exec_module(worker)
        original=self.audio.read_bytes();target=self.root/'padded.wav'
        worker.pad_voice(self.audio,target,6.12)
        with wave.open(str(self.audio),'rb') as source,wave.open(str(target),'rb') as padded:
            self.assertEqual(padded.getnframes(),293760)
            self.assertEqual(padded.readframes(source.getnframes()),source.readframes(source.getnframes()))
            self.assertEqual(padded.readframes(5760),b'\0\0'*5760)
        self.assertEqual(self.audio.read_bytes(),original)

    def test_fixed_sampling_recipes_are_saved_truthfully(self):
        self.assertEqual(avatars.validate_options(self.options()|dict(model='avatar_soulx',steps=60))['steps'],4)
        self.assertEqual(avatars.validate_options(self.options()|dict(model='avatar_longcat',steps=60))['steps'],8)
        self.assertNotIn('steps',avatars.validate_options(self.options()|dict(model='avatar_musetalk')))

if __name__=='__main__':unittest.main()
