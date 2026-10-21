import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import moss
from packs import catalog
from loras import model_catalog
from model_files import unique_files
from workflows import validate_image_options,validate_edit_options,image_workflow,edit_workflow


class MossTests(unittest.TestCase):
    def options(self, model='moss_sft', **settings):
        return validate_image_options(dict(model=model,prompt='A lighthouse above a quiet bay',seed=42,moss=settings))

    def test_requested_models_and_adapters_are_pinned_and_shared(self):
        packs=catalog()
        models=[v for v in packs.values() if v.get('family')=='moss_image' and v['kind']=='image']
        self.assertEqual(len(models),6)
        files=unique_files(f for p in models for f in p['files'])
        self.assertEqual(len(files),9)  # Six models, two encoders and one VAE.
        for file in files+packs['moss_tools']['files']:
            self.assertNotIn('/resolve/main/',file['url']);self.assertEqual(len(file['sha256']),64)
        self.assertTrue(any('MOSS-Image-SFT-8-steps-dmd/resolve/' in f['url'] for f in packs['moss_tools']['files']))
        self.assertTrue(any('lodestones/Kromoss/resolve/' in f['url'] for f in files))
        self.assertEqual(len({model_catalog()[k]['scope'] for k in ('moss_sft','moss_base','kromoss','moss_sft_bf16')}),1)
        self.assertNotIn('moss_tools',model_catalog())

    def test_layout_uses_centered_pixel_coordinates_and_preserves_rendered_text(self):
        el=dict(type='text',caption='A sign',text='Harbor',palette='#ffaa00, #2255aa',x=0,y=0,w=50,h=50)
        o=self.options(prompt_mode='layout',layout=[el])
        o.update(width=1024,height=512)
        g=image_workflow(o,'test');layout=json.loads(g['4']['inputs']['text'])
        self.assertEqual(layout['items'][0]['bbox'],[-256,-512,0,0])
        self.assertEqual(layout['items'][0]['text'],'Harbor')
        self.assertEqual(layout['items'][0]['palette'],['#ffaa00','#2255aa'])
        self.assertEqual(layout['bbox_coord_space'],'abs_centralized')

    def test_invalid_control_layout_and_recipe_choices_are_rejected(self):
        invalid=[dict(shift=float('nan')),dict(skip_layer=22.5),dict(control_start=.9,control_end=.1),dict(encoder='path/other'),dict(recipe='dmd2'),dict(prompt_mode='layout',layout=[]),dict(color_id='a'*101)]
        for settings in invalid:
            with self.subTest(settings=settings),self.assertRaises(ValueError):self.options(**settings)
        for box in [dict(x=90,y=0,w=20,h=20),dict(x=0,y=0,w=-1,h=20)]:
            with self.assertRaises(ValueError):self.options(prompt_mode='layout',layout=[dict(type='object',caption='A house',**box)])

    def test_full_quality_keeps_negative_branch_and_native_sampling(self):
        o=self.options();g=image_workflow(o,'test')
        self.assertEqual(g['6']['class_type'],'EmptyFlux2LatentImage')
        self.assertEqual(g['2']['inputs']['type'],'moss_image')
        self.assertEqual(g['7']['inputs']['shift'],5)
        self.assertEqual(g['15']['inputs']['single_layers'],'22')
        self.assertEqual(g['8']['inputs']['steps'],50)
        o['negative']='blurry';self.assertNotIn('15',image_workflow(o,'test'))

    def test_fast_modes_select_exact_adapter_without_double_cfg_or_skip(self):
        for model,recipe in [('moss_sft','sft8'),('kromoss','dmd2'),('moss_base','dmd')]:
            o=self.options(model,recipe=recipe);g=image_workflow(o,'test')
            self.assertEqual((o['steps'],o['cfg'],o['negative']),(8,1.,''))
            self.assertTrue(g['11']['inputs']['lora_name'].endswith(moss.ADAPTERS[recipe]))
            self.assertEqual(g['11']['inputs']['strength_model'],1.)
            self.assertEqual(g['5']['class_type'],'ConditioningZeroOut');self.assertNotIn('15',g)

    def test_both_maps_reach_both_conditioning_branches_at_correct_size(self):
        o=self.options(color_id='region-map',depth_id='depth-map',control_end=.4)
        o['moss'].update(color_file='regions.png',depth_file='depth.png')
        g=image_workflow(o,'test')
        self.assertEqual(g['20']['inputs']['image'],'regions.png')
        self.assertEqual(g['22']['inputs']['image'],'depth.png')
        self.assertEqual(g['21']['inputs']['upscale_method'],'nearest-exact')
        self.assertEqual(g['23']['inputs']['upscale_method'],'bilinear')
        self.assertEqual(g['14']['inputs']['end_percent'],.4)
        self.assertEqual(g['8']['inputs']['positive'],['14',0]);self.assertEqual(g['8']['inputs']['negative'],['14',1])

    def test_maps_cannot_silently_disappear_and_unknown_staged_paths_are_not_accepted(self):
        o=self.options(color_id='region-map')
        with self.assertRaisesRegex(ValueError,'not staged'):image_workflow(o,'test')
        raw=dict(model='moss_sft',prompt='A bay',moss={'color_file':'arbitrary.png'})
        self.assertNotIn('color_file',validate_image_options(raw)['moss'])

    def test_editor_repaint_uses_source_strength_and_preserves_unpainted_pixels(self):
        o=validate_edit_options(dict(model='moss_sft',prompt='A blue lighthouse',source_image='source',strength=.4,moss={}))
        o.update(input_file='source.png',mask_file='mask.png')
        g=edit_workflow(o,'test')
        self.assertEqual(g['30']['inputs']['image'],'source.png')
        self.assertEqual(g['8']['inputs']['denoise'],.4)
        self.assertEqual(g['34']['class_type'],'SetLatentNoiseMask')
        self.assertEqual(g['35']['inputs']['destination'],['31',0])
        self.assertEqual(g['10']['inputs']['images'],['35',0])
        with self.assertRaises(ValueError):validate_edit_options(dict(model='moss_sft',prompt='A bay',source_image='source',references=['another']))

    def test_precision_and_vae_select_actual_loader_files(self):
        o=self.options(encoder='bf16',vae='full');g=image_workflow(o,'test')
        self.assertEqual(g['2']['inputs']['clip_name'],moss.ENCODERS['bf16'])
        self.assertEqual(g['3']['inputs']['vae_name'],'moss_flux2_vae_full.safetensors')

    def test_wide_dimensions_and_four_step_kromoss_keep_native_rules(self):
        o=validate_image_options(dict(model='kromoss',prompt='A bay',width=2048,height=528,moss=dict(recipe='dmd2',fast_steps=4)))
        self.assertEqual(o['steps'],4)
        with self.assertRaises(ValueError):validate_image_options(dict(model='kromoss',prompt='A bay',width=2049,height=528))
        with self.assertRaises(ValueError):validate_image_options(dict(model='kromoss',prompt='A bay',width=4096,height=4096))

    def test_raw_layout_json_rejects_wrong_coordinates_and_malformed_boxes(self):
        for item in (None, {'bbox':'bad'}, {'bbox':[1,2,0,3]}):
            prompt=json.dumps(dict(summary={},items=[item],bbox_coord_space='abs_centralized',bbox_format='yxyx'))
            with self.assertRaises(ValueError):validate_image_options(dict(model='moss_sft',prompt=prompt,moss=dict(prompt_mode='json')))


if __name__=='__main__':unittest.main()
