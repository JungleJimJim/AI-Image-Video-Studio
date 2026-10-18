"""Ref2VA graph, frame grid, queue and Windows path checks; no inference."""
import json
from pathlib import Path
import sys,tempfile,unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from engine import validate_options,build_workflow,engine_command
from loras import installed_loras,resolve_engine_names
from packs import catalog
from app import Studio

class Ref2VATests(unittest.TestCase):
    def options(self,**changes):
        return dict(model='ref2va',mode='image',source_image='source',prompt='The person in <Picture 1> smiles.',
            width=768,height=512,frames=124,seed=42)|changes

    def graph(self,**changes):
        options=validate_options(self.options(**changes));options['input_file']='reference.png'
        return build_workflow(options,'test')

    def test_pack_has_all_six_pinned_components(self):
        pack=catalog()['ref2va'];self.assertEqual(pack['engine'],'ref2va');self.assertEqual(len(pack['files']),6)
        self.assertEqual(pack['recommended_vram_gb'],24)
        for file in pack['files']:
            self.assertRegex(file['url'],r'/resolve/[a-f0-9]{40}/');self.assertRegex(file['sha256'],r'^[a-f0-9]{64}$')
            self.assertGreater(file['size'],1000000)

    def test_ref2va_grid_does_not_inherit_wan_or_ltx_grid(self):
        for frames in (22,124,243,362):self.assertEqual(validate_options(self.options(frames=frames))['frames'],frames)
        for change in ({'frames':121},{'frames':481},{'mode':'text'},{'source_image':''},{'width':1344,'height':1344},
                {'width':752},{'vsa':'yes'},{'sparsity':float('nan')},{'sparsity':1}):
            with self.subTest(change=change),self.assertRaises(ValueError):validate_options(self.options(**change))

    def test_fixed_recipe_and_seed_are_saved_truthfully(self):
        value=validate_options(self.options(steps=40,cfg=9,fps=16,shift=2))
        self.assertEqual([value[k] for k in ('steps','cfg','fps','shift','sampler','scheduler','seed')],[4,1,24,12,'euler','simple',42])

    def test_reference_audio_gate_and_sigma_wiring(self):
        graph=self.graph(sparsity=.65)
        self.assertEqual(graph['6']['inputs']['ref_images.ref_image_0'],['50',0])
        self.assertEqual(graph['6']['inputs']['audio_vae'],['5',0])
        self.assertEqual(graph['144']['inputs']['model'],['143',0]);self.assertEqual(graph['144']['inputs']['sparsity'],.65)
        self.assertEqual(graph['142']['inputs']['model'],['144',0])
        self.assertEqual(graph['15']['inputs']['audio'],['14',0]);self.assertEqual(graph['15']['inputs']['fps'],24)

    def test_dense_and_silent_exports_are_explicit(self):
        graph=self.graph(vsa=False,audio=False)
        self.assertNotIn('144',graph);self.assertNotIn('14',graph);self.assertNotIn('audio',graph['15']['inputs'])
        self.assertEqual(graph['142']['inputs']['model'],['143',0])

    def test_extra_adapters_chain_after_turbo_before_gate(self):
        graph=self.graph(loras=[dict(name='style.safetensors',strength=.4)])
        self.assertEqual(graph['1000']['inputs']['model'],['143',0]);self.assertEqual(graph['144']['inputs']['model'],['1000',0])
        self.assertEqual(graph['143']['inputs']['model'],['1',0])

    def test_windows_gate_and_lora_names_match_engine_enumerations(self):
        graph=self.graph();schemas={}
        for kind,key,field in [('Ref2VAVSAGatePatch','144','gate_file'),('LoraLoaderModelOnly','143','lora_name')]:
            name=graph[key]['inputs'][field].replace('/','\\')
            schemas[kind]={'input':{'required':{field:[[name],{}]}}}
        resolve_engine_names(graph,schemas)
        self.assertIn('\\',graph['144']['inputs']['gate_file']);self.assertIn('\\',graph['143']['inputs']['lora_name'])

    def test_internal_gate_and_turbo_are_not_user_lora_choices(self):
        with tempfile.TemporaryDirectory() as tmp:
            from common import comfy_root
            file=comfy_root(tmp)/'models/loras/studio/_ref2va_runtime/gate.safetensors'
            file.parent.mkdir(parents=True);file.write_bytes(b'internal fixture')
            self.assertEqual(installed_loras(tmp),[])

    def test_separate_engine_whitelists_only_the_pinned_plugin(self):
        with patch('engine_support.command',return_value=['python.exe','worker.py']) as command:
            result=engine_command('root',1234,'output','low','ref2va')
        command.assert_called_once_with('root','ref2va')
        self.assertIn('--enable-dynamic-vram',result);self.assertNotIn('--lowvram',result)
        self.assertEqual(result[result.index('--whitelist-custom-nodes')+1],'studio_ref2va_vsa')

    def test_queue_freezes_reference_seed_and_vsa_settings(self):
        with tempfile.TemporaryDirectory() as tmp,patch('app.gpu_info',return_value={}),patch('app.pack_ready',return_value=True),patch('app.install_ready',return_value=True):
            studio=Studio(tmp);studio.queue.paused=True
            source=Path(tmp)/'source.png';source.write_bytes(b'original source')
            studio.images=[dict(id='source',path=str(source),name='Reference')]
            identifier=studio.enqueue('video',self.options(vsa=False,sparsity=.5),8)
            item=studio.queue.get(identifier)
            self.assertEqual(item['options']['seed'],42);self.assertFalse(item['options']['vsa']);self.assertEqual(item['options']['sparsity'],.5)
            self.assertEqual(item['options']['source_image'],'source');self.assertEqual(item['priority'],8)
            self.assertEqual(source.read_bytes(),b'original source');self.assertFalse(studio.state['busy'])

if __name__=='__main__':unittest.main()
