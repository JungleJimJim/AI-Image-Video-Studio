import base64
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from app import Studio
from common import atomic_json
from media import catalog_page, crop_options, details, stage_mask
from workflows import validate_edit_options, validate_image_options, image_workflow, edit_workflow
from packs import catalog, install
import threading


class LibraryEditorTests(unittest.TestCase):
    def test_details_include_complete_enhancement_lineage_and_exact_zero_seed(self):
        original=dict(id='original',kind='image',width=512,height=512,options=dict(model='flux3',seed=0,prompt='Robot'))
        enhanced=dict(id='enhanced',kind='enhanced',parent_id='original',width=1024,height=1024,
                      options=dict(model='qwen21',seed=123,detail_strength=1.7,scale=2))
        crop=dict(id='crop',kind='crop',parent_id='enhanced',width=512,height=512,options={})
        result=details([original,enhanced,crop],[], 'crop')
        self.assertEqual([x['id'] for x in result['ancestors']],['enhanced','original'])
        self.assertEqual(result['ancestors'][-1]['options']['seed'],0)
        self.assertEqual(result['ancestors'][0]['options']['detail_strength'],1.7)
        self.assertFalse(result['source_unavailable'])
        self.assertNotIn('media_type',original)

    def test_details_handle_legacy_missing_sources_and_cycles(self):
        original=dict(id='a',parent_id='b',options={})
        other=dict(id='b',parent_id='a',options={})
        self.assertEqual(len(details([original,other],[],'a')['ancestors']),1)
        self.assertTrue(details([original],[],'a')['source_unavailable'])
        with self.assertRaises(ValueError):details([original],[],'unknown')

    def test_oldest_library_items_remain_accessible_and_searchable(self):
        images=[dict(id=str(i),name=f'Image {i}',created=f'2026-10-14 12:{i:03}',options={'prompt':'greenhouse' if i==0 else 'robot'}) for i in range(123)]
        result=catalog_page(images,[],{'page':['5']})
        self.assertEqual(result['total'],123)
        self.assertIn('0',[x['id'] for x in result['items']])
        result=catalog_page(images,[dict(id='video',name='greenhouse.mp4')],{'search':['greenhouse'],'type':['image']})
        self.assertEqual([x['id'] for x in result['items']],['0'])

    def test_invalid_crop_does_not_start_a_job(self):
        for change in ({'width':float('nan')},{'x':-1},{'crop_height':0},{'height':4097}):
            with self.subTest(change=change),self.assertRaises(ValueError):
                crop_options(dict(x=0,y=0,crop_width=100,crop_height=100,width=100,height=100,**{})|change)

    def test_crop_is_saved_with_lineage_and_source_preserved(self):
        with tempfile.TemporaryDirectory() as tmp,patch('app.gpu_info',return_value={}):
            root=Path(tmp);source=root/'original.png';source.write_bytes(b'original')
            studio=Studio(root);studio.images=[dict(id='a'*24,path=str(source),name='original.png')]
            result=dict(id='b'*24,path=str(root/'crop.png'),name='crop.png',parent_id='a'*24,kind='crop')
            with patch('app.media_record',return_value=result) as transform:
                studio.transform_media(dict(id='a'*24,x=0,y=0,crop_width=10,crop_height=10,width=64,height=64),'crop')
                studio.worker.join(5)
                transform.assert_called_once()
            self.assertFalse(studio.state['error'])
            self.assertEqual(source.read_bytes(),b'original')
            self.assertEqual(json.loads((root/'images.json').read_text())[-1]['parent_id'],'a'*24)
            self.assertEqual(studio.state['latest_media']['id'],'b'*24)

    def test_instruction_edit_references_and_masks_reach_the_correct_nodes(self):
        for model in ('fluxklein','qwenedit','illustrious'):
            o=validate_edit_options(dict(model=model,prompt='Change the jacket to blue',source_image='a',references=['b','c'] if model!='illustrious' else [],seed=42))
            o.update(input_file='source.png',reference_files=['b.png','c.png'] if model!='illustrious' else [],mask_file='mask.png')
            g=edit_workflow(o,'test')
            self.assertEqual(g['62']['inputs']['channel'],'red')
            self.assertEqual(g['63']['inputs']['destination'],['21',0])
            if model=='qwenedit':self.assertIn('image3',g['4']['inputs'])
            if model=='fluxklein':self.assertEqual(sum(x['class_type']=='ReferenceLatent' for x in g.values()),6)
            if model=='illustrious':self.assertEqual(g['4']['class_type'],'VAEEncodeForInpaint')

    def test_incompatible_or_duplicate_references_rejected(self):
        for change in ({'model':'juggernaut','references':['b']},{'references':['a']},{'references':['b','b']},{'references':['b','c','d']},{'strength':float('nan')}):
            with self.subTest(change=change),self.assertRaises(ValueError):
                validate_edit_options(dict(model='fluxklein',prompt='Edit',source_image='a')|change)

    def test_every_requested_model_has_a_distinct_valid_workflow(self):
        for model in ('zimage','fluxklein','qwenimage','juggernaut','illustrious'):
            g=image_workflow(validate_image_options(dict(model=model,prompt='A robot',seed=42)),'test')
            self.assertTrue(any(n['class_type']=='SaveImage' for n in g.values()))
        self.assertEqual(image_workflow(validate_image_options(dict(model='fluxklein',prompt='A robot')),'test')['14']['class_type'],'Flux2Scheduler')

    def test_all_new_packs_can_install_together_without_duplicate_dependencies(self):
        with tempfile.TemporaryDirectory() as tmp,patch('packs.runtime_python',return_value=Path(__file__)),patch('packs.shutil.disk_usage') as disk,patch('packs.download') as download:
            disk.return_value.free=10**12
            keys=['zimage','fluxklein','qwenimage','qwenedit','illustrious','juggernaut']
            install(tmp,keys,lambda *a:None,threading.Event())
            paths=[c.args[1] for c in download.call_args_list]
            self.assertEqual(len(paths),len(set(paths)))
            self.assertEqual(len(paths),11)

    def test_invalid_mask_rejected_before_decoder(self):
        with patch('media.process') as decoder:
            for value in ('data:text/html;base64,AAAA','data:image/png;base64,???'):
                with self.assertRaises(ValueError):stage_mask('.',value,512,512)
            decoder.assert_not_called()

if __name__=='__main__':unittest.main()
