"""WAMU dual-stage graph, validation and shard loader regressions; no inference."""
import importlib.util,json,sys,tempfile,unittest,types
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from engine import validate_options,build_workflow,engine_command
from packs import catalog
from app import Studio

class WAMUTests(unittest.TestCase):
 def options(self,**extra):return dict(model='wamu',mode='image',source_image='source',prompt='A toy robot waves',seed=42)|extra
 def graph(self,**extra):
  o=validate_options(self.options(**extra));o['input_file']='source.png';return build_workflow(o,'test')
 def test_pack_pins_all_six_shards_and_reuses_correct_wan_components(self):
  p=catalog()['wamu'];self.assertEqual(len(p['files']),8);self.assertEqual(p['engine'],'wamu')
  shards=p['files'][:6];self.assertEqual(sum(f['size'] for f in shards),57155829760)
  self.assertEqual(len({(f['folder'],f['filename']) for f in shards}),6)
  self.assertEqual(p['files'][-1]['filename'],'wan_2.1_vae.safetensors')
  for f in p['files']:
   self.assertRegex(f['url'],r'/resolve/[a-f0-9]{40}/');self.assertRegex(f['sha256'],r'^[a-f0-9]{64}$')
 def test_recipe_and_invalid_input(self):
  o=validate_options(self.options());self.assertEqual([o[k] for k in ('steps','cfg','shift','sampler','scheduler','audio','memory')],[4,1,3,'uni_pc','simple',False,'low'])
  for change in [dict(mode='text',source_image=''),dict(source_image=''),dict(steps=3),dict(steps=9),dict(frames=50),dict(width=816),dict(video_references=['other'])]:
   with self.subTest(change=change),self.assertRaises(ValueError):validate_options(self.options(**change))
  self.assertEqual(validate_options(self.options(steps=8))['steps'],8)
 def test_noise_stages_share_conditioning_and_continue_the_raw_latent_without_new_noise(self):
  g=self.graph();self.assertEqual(g['1']['inputs']['stage'],'high');self.assertEqual(g['2']['inputs']['stage'],'low')
  self.assertEqual(g['8']['class_type'],'WanImageToVideo');self.assertEqual(g['8']['inputs']['start_image'],['7',0])
  self.assertEqual(g['19']['inputs']['latent_image'],['16',0]);self.assertEqual(g['17']['class_type'],'DisableNoise')
  self.assertEqual(g['16']['inputs']['sigmas'],['12',0]);self.assertEqual(g['19']['inputs']['sigmas'],['12',1]);self.assertNotIn('audio',g['21']['inputs'])
 def test_extra_loras_are_applied_to_both_models(self):
  g=self.graph(loras=[dict(name='style.safetensors',strength=.5)])
  self.assertEqual(g['1000']['inputs']['model'],['1',0]);self.assertEqual(g['1100']['inputs']['model'],['2',0])
  self.assertEqual(g['9']['inputs']['model'],['1000',0]);self.assertEqual(g['10']['inputs']['model'],['1100',0])
 def test_engine_is_isolated_with_only_wamu_nodes_whitelisted(self):
  with patch('engine_support.command',return_value=['python','worker']) as c:r=engine_command('root',123,'output','low','wamu')
  c.assert_called_once_with('root','wamu');self.assertIn('studio_wamu',r);self.assertIn('--enable-dynamic-vram',r)
 def test_queue_preserves_source_seed_and_model(self):
  with tempfile.TemporaryDirectory() as tmp,patch('app.gpu_info',return_value={}),patch('app.pack_ready',return_value=True),patch('app.install_ready',return_value=True):
   s=Studio(tmp);s.queue.paused=True;f=Path(tmp)/'source.png';f.write_bytes(b'fixture');s.images=[dict(id='source',path=str(f),name='Reference')]
   key=s.enqueue('video',self.options(),8);o=s.queue.get(key)['options']
   self.assertEqual(o['model'],'wamu');self.assertEqual(o['source_image'],'source');self.assertEqual(o['seed'],42);self.assertFalse(o['audio'])
 def test_loader_reads_exact_shards_without_a_merged_checkpoint(self):
  utils=types.ModuleType('comfy.utils');sd=types.ModuleType('comfy.sd');comfy=types.ModuleType('comfy');comfy.utils=utils;comfy.sd=sd
  folders=types.ModuleType('folder_paths');paths=[]
  def path(kind,name):paths.append((kind,name));return name
  folders.get_full_path_or_raise=path
  utils.load_torch_file=lambda path,safe_load:{path:object()};sd.load_diffusion_model_state_dict=lambda state:dict(keys=list(state))
  with patch.dict(sys.modules,{'comfy':comfy,'comfy.utils':utils,'comfy.sd':sd,'folder_paths':folders}):
   spec=importlib.util.spec_from_file_location('test_wamu_node',Path(__file__).resolve().parents[1]/'assets/wamu/__init__.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
   sizes=[types.SimpleNamespace(st_size=n) for n in module.SHARD_SIZES]
   with patch('pathlib.Path.stat',side_effect=sizes):result=module.WAMUShardedLoader().load('high')
   self.assertEqual(len(result[0]['keys']),3);self.assertTrue(all('/high/' in name for _,name in paths))
   with self.assertRaises(ValueError):module.WAMUShardedLoader().load('../other')
   with patch('pathlib.Path.stat',return_value=types.SimpleNamespace(st_size=1)),self.assertRaisesRegex(ValueError,'repair'):module.WAMUShardedLoader().load('low')
if __name__=='__main__':unittest.main()
