"""Local voice protocol tests with a fixture WAV server; no TTS model is loaded."""
import io,json,sys,tempfile,threading,unittest,wave
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import voices
from app import Studio
from downloads import Cancelled

def wav_fixture():
    stream=io.BytesIO()
    with wave.open(stream,'wb') as wav:wav.setparams((1,2,24000,0,'NONE','none'));wav.writeframes(b'\0\0'*2400)
    return stream.getvalue()

class VoiceTests(unittest.TestCase):
    def test_connection_accepts_only_explicit_loopback_and_no_redirect_credentials(self):
        self.assertEqual(voices.connection({})['endpoint'],'http://127.0.0.1:8080')
        for endpoint in ('https://example.com','http://192.168.1.2:8000','http://127.0.0.1:80/x','http://user@localhost:8000','http://localhost:8000?key=x','http://localhost'):
            with self.subTest(endpoint=endpoint),self.assertRaises(ValueError):voices.connection(dict(endpoint=endpoint))
    def test_validation_references_seed_sampling_and_protocol(self):
        for change in ({'text':''},{'reference_id':'a'},{'seed':2**32},{'temperature':float('nan')},{'top_p':2},{'randomize_seed':'yes'},{'protocol':'sglang','model':'fish_s2'}):
            with self.subTest(change=change),self.assertRaises(ValueError):voices.validate_options(dict(text='Hello')|change)
        o=voices.validate_options(dict(text='Hello',seed=42));self.assertEqual(o['seed'],42);self.assertEqual(o['temperature'],.7)
    def test_two_exact_api_payloads_and_reference_encoding(self):
        raw=dict(text='[whisper] Hello',reference_id='a',transcript='Reference transcript',seed=42)
        route,p=voices.payload(voices.validate_options(raw),b'fixture');self.assertEqual(route,'/v1/tts');self.assertEqual(p['references'][0]['audio'],'Zml4dHVyZQ==');self.assertFalse(p['streaming'])
        route,p=voices.payload(voices.validate_options(raw|dict(protocol='sglang',model='fish_drama3')),b'fixture');self.assertEqual(route,'/v1/audio/speech');self.assertTrue(p['references'][0]['audio'].startswith('data:audio/wav;base64,'));self.assertEqual(p['model'],'fishaudio/drama-3')
    def test_voice_queue_keeps_seed_and_is_editable_without_connecting(self):
        with tempfile.TemporaryDirectory() as tmp,patch('app.gpu_info',return_value={}),patch('voices.generate',side_effect=AssertionError('Must not generate')):
            studio=Studio(tmp);studio.queue.paused=True;raw=dict(text='Hello',seed=42)
            id=studio.enqueue('voice',raw,4);studio.queue_action(dict(action='update',id=id,options=raw|dict(text='Updated',seed=123),priority=9))
            self.assertEqual(studio.queue.get(id)['options']['seed'],123);self.assertEqual(studio.queue.snapshot()['jobs'][0]['prompt'],'Updated')
            studio.queue_action(dict(action='cancel',id=id));self.assertEqual(studio.queue.get(id)['status'],'cancelled')
    def test_transport_reads_status_and_wav_from_stub_server_and_cleans_private_job(self):
        calls=[];wave_bytes=wav_fixture()
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                self.send_response(200);self.end_headers();self.wfile.write(b'{"model_family":"s2"}')
            def do_POST(self):
                calls.append((self.path,json.loads(self.rfile.read(int(self.headers['Content-Length'])))))
                self.send_response(200);self.send_header('Content-Type','audio/wav');self.end_headers();self.wfile.write(wave_bytes)
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            raw=dict(text='Fixture request',seed=42,endpoint='http://127.0.0.1:'+str(server.server_port));o=voices.validate_options(raw)
            self.assertTrue(voices.check(o)['connected']);self.assertEqual(calls,[])
            with tempfile.TemporaryDirectory() as tmp,patch('voices.runtime_python',return_value=Path(sys.executable)):
                result,seconds=voices.generate(tmp,o,None,lambda *a:None,threading.Event());self.assertEqual(result,wave_bytes);self.assertEqual(list((Path(tmp)/'voice-jobs').iterdir()),[])
            self.assertEqual(calls[0][0],'/v1/tts');self.assertEqual(calls[0][1]['seed'],42)
        finally:server.shutdown();server.server_close();thread.join(5)

if __name__=='__main__':unittest.main()
