"""Completion notifications must never generate media or interrupt queued work."""
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch
import wave

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from app import Studio
from common import load_json
from downloads import Cancelled
from job_queue import KINDS
from notifications import play_completion_ping


class CompletionSoundTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        with patch('app.gpu_info',return_value={}):self.studio=Studio(self.root)
        self.studio.queue.paused=True
        sound=patch('app.play_completion_ping');self.ping=sound.start();self.addCleanup(sound.stop)

    def run_job(self,target=lambda:None,**options):
        self.studio.run_job(target,**options);self.studio.worker.join(3)
        self.assertFalse(self.studio.worker.is_alive())

    def test_one_ping_for_each_successful_queued_generation_kind(self):
        for kind in KINDS:
            job=self.studio.queue.add(kind,{'model':'fixture'})
            self.run_job(queue_id=job['id'])
            self.assertEqual(job['status'],'completed')
        self.assertEqual(self.ping.call_count,len(KINDS))

    def test_direct_generations_notify_but_maintenance_and_muted_jobs_do_not(self):
        self.run_job();self.ping.assert_not_called()
        self.run_job(notify_completion=True);self.ping.assert_called_once()
        self.studio.settings['completion_sound']=False
        self.run_job(notify_completion=True);self.ping.assert_called_once()
        job=self.studio.queue.add('video',{'model':'fixture'})
        self.run_job(queue_id=job['id']);self.ping.assert_called_once()

    def test_failures_and_cancellations_are_silent_and_audio_failure_cannot_stop_work(self):
        for error in (RuntimeError('fixture failure'),Cancelled('fixture cancellation')):
            def fail():raise error
            self.run_job(fail,notify_completion=True)
        self.ping.assert_not_called()
        self.ping.return_value=False
        for _ in range(2):
            job=self.studio.queue.add('image',{'model':'fixture'})
            self.run_job(queue_id=job['id']);self.assertEqual(job['status'],'completed')
        self.assertEqual(self.ping.call_count,2)

    def test_sound_preference_persists_during_render_without_changing_folder(self):
        output=self.studio.settings['output'];self.studio.state['busy']=True
        self.studio.save_settings({'completion_sound':False})
        saved=load_json(self.root/'settings.json',{})
        self.assertFalse(saved['completion_sound']);self.assertEqual(saved['output'],output)
        for bad in ('yes',1,None):
            with self.assertRaises(ValueError):self.studio.save_settings({'completion_sound':bad})
        with self.assertRaises(ValueError):self.studio.save_settings({'output':str(self.root/'other')})
        with patch('app.gpu_info',return_value={}):reopened=Studio(self.root)
        self.assertFalse(reopened.settings['completion_sound'])

    def test_windows_playback_is_asynchronous_and_missing_audio_is_nonfatal(self):
        native=SimpleNamespace(PlaySound=Mock(),SND_FILENAME=1,SND_ASYNC=2,SND_NODEFAULT=4)
        with patch.dict(sys.modules,{'winsound':native}):
            self.assertTrue(play_completion_ping())
            native.PlaySound.assert_called_once_with(str(ROOT/'assets/completion-ping.wav'),7)
            native.PlaySound.side_effect=RuntimeError('No audio device')
            self.assertFalse(play_completion_ping())

    def test_bundled_ping_is_short_mono_pcm_with_safe_levels(self):
        with wave.open(str(ROOT/'assets/completion-ping.wav'),'rb') as sound:
            self.assertEqual((sound.getnchannels(),sound.getsampwidth(),sound.getframerate()),(1,2,48000))
            self.assertAlmostEqual(sound.getnframes()/sound.getframerate(),.45)
            data=sound.readframes(sound.getnframes())
        samples=struct.unpack('<'+'h'*(len(data)//2),data)
        self.assertEqual(samples[0],0);self.assertEqual(samples[-1],0)
        self.assertGreater(max(map(abs,samples)),1000);self.assertLess(max(map(abs,samples)),32767)


if __name__=='__main__':unittest.main()
