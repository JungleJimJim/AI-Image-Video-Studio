import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from app import Studio
from common import atomic_json
from engine import build_workflow, validate_options
from loras import import_loras, installed_loras, model_catalog, validate_selection
from workflows import image_workflow, edit_workflow, validate_image_options, validate_edit_options
from test_loras import fixture


class AllModelLoRATests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.source=self.root/'style.safetensors'
        fixture(self.source)

    def tearDown(self):
        self.tmp.cleanup()

    def imported(self,model):
        import_loras(self.root,[str(self.source)],lambda *a:None,threading.Event(),model)
        return installed_loras(self.root,model)[0]['name']

    def test_every_model_has_a_library_and_shared_sdxl_files_are_deduplicated(self):
        original=self.source.read_bytes()
        for model in model_catalog():
            self.imported(model)
        self.assertEqual(len(model_catalog()),12)
        self.assertEqual(len(installed_loras(self.root)),10)
        self.assertEqual(self.source.read_bytes(),original)
        sdxl=self.imported('juggernaut')
        for model in ('juggernaut','dreamshaper','illustrious'):
            self.assertEqual(installed_loras(self.root,model)[0]['name'],sdxl)

    def test_wrong_family_selection_is_rejected_even_if_file_exists(self):
        wan=self.imported('wan13');flux=self.imported('fluxklein')
        for model,name in [('wan22',wan),('zimage',flux),('qwenedit',flux),('wan13',flux)]:
            with self.subTest(model=model),self.assertRaises(ValueError):
                validate_selection(self.root,[{'name':name,'strength':1}],model)

    def test_all_model_workflows_apply_both_adapters_before_sampling(self):
        adapters=[{'name':'first.safetensors','strength':.7,'strength_clip':.25},{'name':'second.safetensors','strength':.4,'strength_clip':0}]
        for model in model_catalog():
            if model=='qwen21':continue  # Dedicated enhancement graph is covered separately.
            opts=dict(model=model,prompt='A greenhouse',seed=42,loras=adapters,width=512,height=320,frames=33)
            if model in ('wan13','wan22','ltx2'):
                graph=build_workflow(validate_options(opts),'test')
            elif model=='qwenedit':
                o=validate_edit_options(opts|{'source_image':'a'});o.update(input_file='source.png')
                graph=edit_workflow(o,'test')
            else:
                graph=image_workflow(validate_image_options(opts),'test')
            nodes=[(k,n) for k,n in graph.items() if n['class_type'].startswith('LoraLoader')]
            with self.subTest(model=model):
                self.assertEqual(len(nodes),2)
                first,last=nodes
                self.assertEqual(last[1]['inputs']['model'],[first[0],0])
                self.assertTrue(any(n['inputs'].get('model')==[last[0],0] for k,n in graph.items() if k!=last[0]))
                if model in ('wan13','juggernaut','dreamshaper','illustrious'):
                    self.assertEqual(first[1]['inputs']['strength_clip'],.25)
                    self.assertEqual(last[1]['inputs']['clip'],[first[0],1])
                    self.assertTrue(any(n['inputs'].get('clip')==[last[0],1] for k,n in graph.items() if k!=last[0]))
                else:
                    self.assertEqual(first[1]['class_type'],'LoraLoaderModelOnly')
                    self.assertNotIn('clip',first[1]['inputs'])

    def test_editor_reference_and_mask_paths_keep_adapted_models(self):
        for model in ('juggernaut','fluxklein','qwenedit'):
            o=validate_edit_options(dict(model=model,prompt='Change the roof',source_image='a',loras=[{'name':'style.safetensors','strength':.5}]))
            o.update(input_file='source.png',mask_file='mask.png',reference_files=[])
            g=edit_workflow(o,'test')
            self.assertEqual(g['63']['class_type'],'ImageCompositeMasked')
            consumer='5' if model=='juggernaut' else '12' if model=='fluxklein' else '7'
            self.assertEqual(g[consumer]['inputs']['model'],['1000',0])

    def test_model_selections_survive_restart_without_overwriting_other_models_or_drafts(self):
        names={model:self.imported(model) for model in ('wan13','juggernaut','dreamshaper','wan22')}
        atomic_json(self.root/'settings.json',{'output':str(self.root),'options':{'model':'wan22','prompt':'Keep this video draft'},'wan_loras':[{'name':names['wan13'],'strength':.6}]})
        with patch('app.gpu_info',return_value={}):
            studio=Studio(self.root)
            for model,strength in [('juggernaut',.7),('dreamshaper',.3),('wan22',.4)]:
                studio.update_loras([{'name':names[model],'strength':strength}],model)
            reloaded=Studio(self.root)
        self.assertEqual(reloaded.settings['options']['prompt'],'Keep this video draft')
        self.assertEqual(reloaded.settings['model_loras']['wan13'][0]['strength'],.6)
        self.assertEqual(reloaded.settings['model_loras']['juggernaut'][0]['strength'],.7)
        self.assertEqual(reloaded.settings['model_loras']['dreamshaper'][0]['strength'],.3)
        self.assertEqual(reloaded.settings['options']['loras'][0]['name'],names['wan22'])

    def test_saved_profiles_are_used_for_images_editor_and_video(self):
        for model,kind in [('wan22','video'),('juggernaut','image'),('qwenedit','edit')]:
            name=self.imported(model)
            with patch('app.gpu_info',return_value={}),patch('app.install_ready',return_value=True),patch('app.pack_ready',return_value=True):
                studio=Studio(self.root)
                studio.update_loras([{'name':name,'strength':.8}],model)
                output=self.root/('result.mp4' if kind=='video' else 'result.png');output.write_bytes(b'fixture')
                source=self.root/'source.png';source.write_bytes(b'fixture')
                studio.images=[dict(id='a'*24,path=str(source),name='source.png')]
                with patch.object(studio.engine,'generate',return_value=(output,{},1)) as generate:
                    raw=dict(model=model,prompt='A greenhouse',seed=42,source_image='a'*24)
                    {'video':studio.generate,'image':studio.generate_image,'edit':studio.edit_image}[kind](raw)
                    studio.worker.join(5)
                    self.assertFalse(studio.state['error'])
                    self.assertEqual(generate.call_args.args[0]['loras'][0]['name'],name)
                    self.assertEqual(generate.call_args.args[0]['loras'][0]['strength'],.8)

    def test_independent_text_strength_and_invalid_strength_validation(self):
        name=self.imported('juggernaut')
        result=validate_selection(self.root,[{'name':name,'strength':.8,'strength_clip':0}],'juggernaut')
        self.assertEqual(result[0]['strength_clip'],0)
        for field,value in [('strength',None),('strength',float('nan')),('strength_clip',float('inf'))]:
            with self.subTest(field=field),self.assertRaises(ValueError):
                validate_selection(self.root,[{'name':name,field:value}],'juggernaut')

    def test_unknown_models_cannot_create_arbitrary_library_paths(self):
        for model in ('../outside','flux9b','',None):
            with self.subTest(model=model),self.assertRaises(ValueError):
                import_loras(self.root,[str(self.source)],lambda *a:None,threading.Event(),model)

if __name__=='__main__':unittest.main()
