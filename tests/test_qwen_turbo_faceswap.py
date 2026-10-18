import sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from workflows import validate_image_options,validate_edit_options,image_workflow,edit_workflow
from packs import catalog
from loras import resolve_engine_names
from engine import engine_command
from app import Studio

class QwenTurboTests(unittest.TestCase):
    def raw(self,**changes):return dict(model='viggle',prompt='A studio portrait.',seed=42,width=512,height=512)|changes
    def test_shared_files_and_adapter_pins(self):
        shared=[f for f in catalog()['qwen21']['files'] if f['folder'] in ('diffusion_models','text_encoders','vae')]
        for key in ('viggle','bfs'):
            p=catalog()[key];self.assertEqual(p['files'][:3],shared);self.assertEqual(p['engine'],'qwen_turbo')
            self.assertRegex(p['files'][-1]['url'],r'/resolve/[a-f0-9]{40}/');self.assertEqual(len(p['files'][-1]['sha256']),64)
    def test_viggle_fixed_recipe_uses_unmerged_adapter_and_custom_schedule(self):
        o=validate_image_options(self.raw(steps=40,cfg=8,negative='bad'));self.assertEqual([o[k] for k in ('steps','cfg','negative')],[6,1,''])
        g=image_workflow(o,'test');self.assertEqual(g['7']['class_type'],'ViggleTurboLora');self.assertEqual(g['7']['inputs']['strength'],1)
        self.assertEqual(g['14']['inputs']['nodes'],'1.0, 0.9375, 0.875, 0.75, 0.5, 0.25');self.assertEqual(g['8']['inputs']['sigmas'],['14',0])
        self.assertEqual(g['4']['inputs']['resolution'],0);self.assertNotIn('images.image_1',g['4']['inputs'])
    def test_viggle_three_references_and_mask_compose(self):
        o=validate_edit_options(self.raw(source_image='a',references=['b','c']));o.update(input_file='a.png',reference_files=['b.png','c.png'],mask_file='mask.png')
        g=edit_workflow(o,'test');self.assertEqual(g['4']['inputs']['images.image_1'],['21',0]);self.assertEqual(g['4']['inputs']['images.image_3'],['41',0])
        self.assertEqual(g['10']['inputs']['images'],['63',0]);self.assertEqual(g['63']['inputs']['destination'],['21',0])
        with self.assertRaises(ValueError):validate_edit_options(self.raw(source_image='a',references=['b','c','d']))
    def test_bfs_order_and_no_acceleration_adapter(self):
        o=validate_edit_options(self.raw(model='bfs',source_image='target',references=['identity']));o.update(input_file='target.png',reference_files=['identity.png'])
        g=edit_workflow(o,'test');self.assertEqual(o['steps'],40);self.assertEqual(g['20']['inputs']['image'],'target.png');self.assertEqual(g['30']['inputs']['image'],'identity.png')
        self.assertEqual(g['7']['class_type'],'LoraLoaderModelOnly');self.assertIn('bfs_head_v1.1',g['7']['inputs']['lora_name']);self.assertEqual(g['8']['class_type'],'KSampler');self.assertNotIn('14',g)
    def test_bfs_requires_exactly_two_different_images(self):
        for refs in ([],['a'],['b','c']):
            with self.subTest(refs=refs),self.assertRaises(ValueError):validate_edit_options(self.raw(model='bfs',source_image='a',references=refs))
    def test_extra_adapters_after_builtin_and_windows_names(self):
        o=validate_image_options(self.raw(loras=[dict(name='style.safetensors',strength=.4)]));g=image_workflow(o,'test')
        self.assertEqual(g['1000']['inputs']['model'],['7',0]);self.assertEqual(g['12']['inputs']['model'],['1000',0])
        schemas={}
        for key in ('7','1000'):
            n=g[key];name=n['inputs']['lora_name'].replace('/','\\');schemas[n['class_type']]={'input':{'required':{'lora_name':[[name],{}]}}}
        resolve_engine_names(g,schemas);self.assertIn('\\',g['7']['inputs']['lora_name'])
    def test_faceswap_queue_is_editable_and_keeps_original_files(self):
        with tempfile.TemporaryDirectory() as tmp,patch('app.gpu_info',return_value={}),patch('app.pack_ready',return_value=True),patch('app.install_ready',return_value=True):
            studio=Studio(tmp);studio.queue.paused=True
            for key in ('target','identity'):
                path=Path(tmp)/(key+'.png');path.write_bytes(b'original');studio.images.append(dict(id=key,path=str(path),name=key))
            raw=self.raw(model='bfs',source_image='target',references=['identity']);id=studio.enqueue('faceswap',raw,8)
            studio.queue_action(dict(action='update',id=id,options=raw|dict(seed=123),priority=10))
            job=studio.queue.get(id);self.assertEqual(job['options']['references'],['identity']);self.assertEqual(job['options']['seed'],123)
            self.assertEqual(job['priority'],10);self.assertFalse(studio.state['busy']);self.assertEqual((Path(tmp)/'target.png').read_bytes(),b'original')
            studio.queue_action(dict(action='cancel',id=id));self.assertEqual(job['status'],'cancelled')
    def test_shared_engine_whitelists_only_viggle_extension(self):
        for key in ('viggle','bfs'):
            with patch('engine_support.command',return_value=['python.exe']) as command:result=engine_command('root',1234,'output','low',key)
            command.assert_called_once_with('root','qwen_turbo');self.assertEqual(result[result.index('--whitelist-custom-nodes')+1],'studio_viggle_turbo')

if __name__=='__main__':unittest.main()
