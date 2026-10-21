import sys
from pathlib import Path
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from engine import validate_options, build_workflow, engine_command, explain_engine_error
from workflows import validate_image_options, image_workflow
from resources import sample_gpu
from packs import catalog
from images import import_image
from app import Studio
from common import atomic_json
import tempfile

class CreativeModesTests(unittest.TestCase):
    def test_text_only_checkpoint_rejects_image_input(self):
        with self.assertRaises(ValueError):
            validate_options(dict(prompt='A greenhouse',mode='image',model='wan13',source_image='example'))

    def test_ltx_rejects_wan_size_and_frame_rules(self):
        for change in ({'height':480},{'frames':37},{'source_image':'','mode':'image'}):
            with self.subTest(change=change),self.assertRaises(ValueError):
                validate_options({**dict(prompt='A greenhouse',model='ltx2',width=512,height=320,frames=33),**change})

    def test_wan_image_guidance_uses_correct_architecture(self):
        o=validate_options(dict(prompt='A greenhouse',model='wan22',mode='image',source_image='source'))
        o['input_file']='reference.png'
        g=build_workflow(o,'example')
        self.assertEqual(g['6']['class_type'],'Wan22ImageToVideoLatent')
        self.assertEqual(g['6']['inputs']['start_image'],['12',0])
        self.assertEqual(g['3']['inputs']['vae_name'],'wan2.2_vae.safetensors')

    def test_ltx_audio_export_is_optional_and_distilled_recipe_stable(self):
        o=validate_options(dict(prompt='A greenhouse',model='ltx2',width=512,height=320,frames=33))
        a=build_workflow(o,'example'); b=build_workflow({**o,'audio':False},'example')
        self.assertIn('audio',a['17']['inputs']);self.assertNotIn('audio',b['17']['inputs'])
        self.assertEqual(a['10']['inputs']['cfg'],1)
        self.assertEqual(len(a['12']['inputs']['sigmas'].split(',')),9)

    def test_sdxl_models_have_their_own_sampler_and_complete_checkpoint(self):
        for model,sampler in [('dreamshaper','dpmpp_sde'),('juggernaut','dpmpp_2m')]:
            o=validate_image_options(dict(model=model,prompt='A greenhouse',seed=42))
            graph=image_workflow(o,'example')
            self.assertEqual(graph['5']['inputs']['sampler_name'],sampler)
            self.assertEqual(graph['6']['inputs']['vae'],['1',2])

    def test_image_dimension_and_nan_validation(self):
        for change in ({'width':1000},{'steps':3.1},{'cfg':float('nan')},{'seed':str(2**54)}):
            with self.subTest(change=change),self.assertRaises(ValueError):
                validate_image_options(dict(prompt='A greenhouse',**change))

    def test_gpu_readings_are_memory_bytes_and_processing_load(self):
        with patch('resources.subprocess.run') as run:
            run.return_value.returncode=0;run.return_value.stdout='65, 4096, 16384\n'
            value=sample_gpu()
            self.assertEqual(value,dict(percent=65,used=4*1024**3,total=16*1024**3,source='nvidia-smi'))

    def test_import_rejects_non_images_before_launching_decoder(self):
        with patch('images.subprocess.run') as decoder,self.assertRaises(ValueError):
            import_image('.',{'data':'data:text/html;base64,PHNjcmlwdD4='},lambda *args:None)
        decoder.assert_not_called()

    def test_model_downloads_are_pinned_and_hashed(self):
        for p in catalog().values():
            for f in p['files']:
                self.assertEqual(len(f['sha256']),64)
                self.assertNotIn('/resolve/main/',f['url'])
                # Avatar packs also pin small architecture and tokenizer configs.
                self.assertGreater(f['size'],0)
                if f['filename'].endswith(('.safetensors','.gguf','.onnx','.pth','.pt','.bin')):
                    self.assertGreater(f['size'],1000000)

    def test_wan_lora_settings_are_preserved_while_another_model_is_selected(self):
        with tempfile.TemporaryDirectory() as tmp, patch('app.gpu_info',return_value={}), patch('app.validate_selection',return_value=[{'name':'wan.safetensors','strength':0.7}]):
            atomic_json(Path(tmp)/'settings.json',{'output':tmp,'options':{'model':'ltx2','loras':[]}})
            studio=Studio(tmp)
            studio.update_loras([{'name':'wan.safetensors','strength':0.7}])
            self.assertEqual(studio.settings['options']['loras'],[])
            self.assertEqual(studio.settings['wan_loras'][0]['strength'],0.7)

    def test_ltx_never_uses_the_legacy_memory_loader(self):
        for mode in ('auto','low'):
            command=engine_command(Path('example'),12345,Path('output'),mode,'ltx2')
            self.assertIn('--enable-dynamic-vram',command)
            self.assertIn('--disable-pinned-memory',command)
            self.assertNotIn('--disable-dynamic-vram',command)
            self.assertNotIn('--lowvram',command)

    def test_long_clips_keep_model_frame_rules_and_workflow_length(self):
        for model in ('wan13','wan22','ltx2'):
            o=validate_options(dict(prompt='A greenhouse',model=model,width=512,height=320,frames=481))
            graph=build_workflow(o,'example')
            lengths=[n['inputs']['length'] for n in graph.values() if 'length' in n['inputs']]
            self.assertIn(481,lengths)
        for frames in (482,1001):
            with self.assertRaises(ValueError): validate_options(dict(prompt='A greenhouse',frames=frames))
        with self.assertRaises(ValueError):
            validate_options(dict(prompt='A greenhouse',model='ltx2',width=512,height=320,frames=245))

    def test_paging_error_explains_commit_without_claiming_a_system_change(self):
        message=explain_engine_error('OSError: The paging file is too small (os error 1455)')
        self.assertIn('committed memory',message)
        self.assertIn('has not changed',message)
        self.assertEqual(explain_engine_error('Different error'),'Different error')

if __name__=='__main__': unittest.main()
