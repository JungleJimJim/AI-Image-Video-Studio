"""MiniMax Turbo integration regressions; no inference or model downloads."""
import json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from engine import validate_options,build_workflow,engine_command
from packs import catalog
from loras import resolve_engine_names,installed_loras
from app import Studio

class MiniMaxTests(unittest.TestCase):
    def options(self,**changes):
        return dict(model='minimax_h3',prompt='A robot waves.',width=960,height=544,frames=124,seed=42)|changes
    def graph(self,**changes):
        o=validate_options(self.options(**changes));o.update(input_file='first.png',last_input_file='last.png');return build_workflow(o,'test')
    def test_pack_is_pinned_and_shares_existing_encoder_and_decoders(self):
        p=catalog()['minimax_h3'];shared=[f for f in catalog()['ref2va']['files'] if f['folder'] in ('text_encoders','vae')]
        self.assertEqual(p['engine'],'minimax_h3');self.assertEqual(len(p['files']),6)
        for f in shared:self.assertIn(f,p['files'])
        for f in p['files']:
            self.assertRegex(f['url'],r'/resolve/[a-f0-9]{40}/');self.assertRegex(f['sha256'],r'^[a-f0-9]{64}$')
    def test_default_recipe_is_space_larry_six_steps(self):
        o=validate_options(self.options());self.assertEqual(o['turbo'],'larry850');self.assertEqual(o['steps'],6)
        self.assertEqual([o[k] for k in ('cfg','fps','shift','sampler','scheduler','seed')],[1,24,12,'euler','simple',42])
    def test_text_graph_has_no_images_or_vsa_and_correct_av_wiring(self):
        g=self.graph();self.assertEqual(g['6']['class_type'],'MiniMaxH3ImageToVideo');self.assertNotIn('50',g);self.assertNotIn('144',g)
        self.assertEqual(g['9']['class_type'],'MiniMaxH3TurboSampler');self.assertEqual(g['143']['class_type'],'MiniMaxH3TurboLoRA')
        self.assertEqual(g['142']['inputs']['model'],['143',0]);self.assertEqual(g['15']['inputs']['audio'],['14',0])
    def test_first_last_and_silent_clip(self):
        g=self.graph(mode='image',source_image='a',last_image='b',audio=False)
        self.assertEqual(g['6']['inputs']['first_frame'],['50',0]);self.assertEqual(g['6']['inputs']['last_frame'],['51',0])
        self.assertNotIn('14',g);self.assertNotIn('audio',g['15']['inputs'])
    def test_v4_strength_memory_and_extra_loras_are_applied(self):
        g=self.graph(turbo='larryv4',turbo_strength=.9,turbo_low_vram=False,loras=[dict(name='style.safetensors',strength=.4)])
        self.assertIn('v4_step600',g['143']['inputs']['lora_name']);self.assertEqual(g['143']['inputs']['strength'],.9)
        self.assertFalse(g['143']['inputs']['low_vram']);self.assertEqual(g['1000']['inputs']['model'],['143',0]);self.assertEqual(g['142']['inputs']['model'],['1000',0])
    def test_base_mode_removes_turbo_but_keeps_user_adapter(self):
        g=self.graph(turbo='off',steps=28,loras=[dict(name='style.safetensors',strength=.4)])
        self.assertNotIn('143',g);self.assertEqual(g['9']['class_type'],'KSamplerSelect');self.assertEqual(g['1000']['inputs']['model'],['1',0]);self.assertEqual(g['10']['inputs']['steps'],28)
    def test_rejects_invalid_grid_and_bad_turbo_values(self):
        for value in (dict(frames=121),dict(width=752),dict(width=1344,height=1344),dict(turbo='random'),dict(steps=3),dict(steps=9),
            dict(turbo_strength=float('nan')),dict(turbo_strength=3),dict(turbo_low_vram='yes'),dict(last_image='b'),dict(last_image=[]),dict(mode='image',source_image='')):
            with self.subTest(value=value),self.assertRaises(ValueError):validate_options(self.options(**value))
    def test_windows_combo_name_is_exact(self):
        g=self.graph();n=g['143']['inputs']['lora_name'].replace('/','\\')
        resolve_engine_names(g,{'MiniMaxH3TurboLoRA':{'input':{'required':{'lora_name':[[n],{}]}}}})
        self.assertEqual(g['143']['inputs']['lora_name'],n)
    def test_queue_keeps_both_keyframes_seed_and_adapter_and_rejects_missing_end(self):
        with tempfile.TemporaryDirectory() as tmp,patch('app.gpu_info',return_value={}),patch('app.pack_ready',return_value=True),patch('app.install_ready',return_value=True):
            studio=Studio(tmp);studio.queue.paused=True
            for key in ('a','b'):
                f=Path(tmp)/(key+'.png');f.write_bytes(b'source fixture');studio.images.append(dict(id=key,path=str(f),name=key))
            raw=self.options(mode='image',source_image='a',last_image='b',turbo='larryv4')
            identifier=studio.enqueue('video',raw,8);o=studio.queue.get(identifier)['options']
            self.assertEqual([o[k] for k in ('source_image','last_image','seed','turbo')],['a','b',42,'larryv4'])
            studio.queue_action(dict(action='update',id=identifier,options=raw|dict(turbo='larry850',seed=123),priority=9))
            self.assertEqual(studio.queue.get(identifier)['options']['seed'],123)
            with self.assertRaisesRegex(ValueError,'last image'):studio.enqueue('video',raw|dict(last_image='missing'))
            self.assertFalse(studio.state['busy'])
    def test_optional_engine_is_isolated_and_whitelisted(self):
        with patch('engine_support.command',return_value=['python.exe','worker.py']) as command:
            result=engine_command('root',1234,'output','low','minimax_h3')
        command.assert_called_once_with('root','minimax_h3');self.assertIn('--enable-dynamic-vram',result)
        self.assertEqual(result[result.index('--whitelist-custom-nodes')+1],'studio_minimax_h3_turbo')

if __name__=='__main__':unittest.main()
