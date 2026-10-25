"""Singularity routing, shared downloads and queue regression checks; no inference."""
import test_ref2va
from unittest.mock import patch
from packs import catalog
from engine import engine_command,validate_options

class SingularityTests(test_ref2va.Ref2VATests):
    def options(self,**changes):return super().options(**({'model':'singularity'}|changes))
    def test_pack_has_all_six_pinned_components(self):
        p=catalog()['singularity'];base=catalog()['ref2va']
        self.assertEqual(p['engine'],'ref2va');self.assertEqual(len(p['files']),5)
        self.assertEqual(p['files'][0]['size'],20967647456)
        for f in p['files']:
            self.assertRegex(f['url'],r'/resolve/[a-f0-9]{40}/');self.assertRegex(f['sha256'],r'^[a-f0-9]{64}$')
        self.assertEqual(p['files'][1:],[f for f in base['files'][1:] if 'fasth3_vsa_gate' not in f['filename']])
    def test_dense_defaults_and_checkpoint_routing(self):
        o=validate_options(self.options());self.assertFalse(o['vsa']);self.assertEqual(o['steps'],4)
        g=self.graph();self.assertEqual(g['1']['inputs']['unet_name'],catalog()['singularity']['files'][0]['filename'])
        self.assertNotIn('144',g);self.assertIn('ref2v_turbo',g['143']['inputs']['lora_name'])
        with self.assertRaisesRegex(ValueError,'VSA gates'):validate_options(self.options(vsa=True))
    def test_optional_engine_routes_to_existing_ref2va(self):
        with patch('engine_support.command',return_value=['python.exe','worker.py']) as command:
            result=engine_command('root',1234,'output','low','singularity')
        command.assert_called_once_with('root','ref2va')
        self.assertIn('--enable-dynamic-vram',result);self.assertIn('studio_ref2va_vsa',result)

    def test_reference_audio_gate_and_sigma_wiring(self):
        g=self.graph();self.assertEqual(g['6']['inputs']['ref_images.ref_image_0'],['50',0])
        self.assertEqual(g['15']['inputs']['audio'],['14',0]);self.assertNotIn('144',g)
    def test_extra_adapters_chain_after_turbo_before_gate(self):
        g=self.graph(loras=[dict(name='style.safetensors',strength=.4)])
        self.assertEqual(g['1000']['inputs']['model'],['143',0]);self.assertEqual(g['142']['inputs']['model'],['1000',0])
    def test_windows_gate_and_lora_names_match_engine_enumerations(self):
        from loras import resolve_engine_names
        g=self.graph();name=g['143']['inputs']['lora_name'].replace('/','\\')
        resolve_engine_names(g,{'LoraLoaderModelOnly':{'input':{'required':{'lora_name':[[name],{}]}}}})
        self.assertEqual(g['143']['inputs']['lora_name'],name)
