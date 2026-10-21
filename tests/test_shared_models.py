import hashlib
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from common import atomic_json, manifest
from downloads import Cancelled, download, provision
from model_files import content_id, file_status, model_path, remaining_bytes, reuse_alias, unique_files
from model_removal import removal_plan, uninstall
from packs import catalog, install
from workflows import image_workflow, validate_edit_options, validate_image_options, edit_workflow
from loras import model_catalog
from engine import engine_command


def spec(name, data=b'weights', folder='diffusion_models'):
    return dict(label=name,filename=name,folder=folder,size=len(data),
                sha256=hashlib.sha256(data).hexdigest(),url='https://example.invalid/'+name)


class SharedModelsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.cancel=threading.Event();self.report=lambda *args:None

    def tearDown(self):self.temp.cleanup()

    def write(self,f,data=b'weights'):
        path=model_path(self.root,f);path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
        return path

    def test_catalog_has_no_conflicting_paths_and_wan22_declares_shared_encoder(self):
        packs=catalog();base=manifest()['models']
        unique_files(base+[f for pack in packs.values() for f in pack['files']])
        encoder=next(f for f in base if f['folder']=='text_encoders')
        self.assertIn(encoder,packs['wan22']['files'])
        vae=next(f for f in packs['qwenimage']['files'] if f['folder']=='vae')
        self.assertEqual(packs['krea2']['files'][2],vae)

    def test_conflicting_hash_or_size_on_same_windows_path_is_rejected(self):
        f=spec('BASE.safetensors')
        for change in ({'filename':'base.safetensors','sha256':'a'*64},{'size':123}):
            with self.subTest(change=change),self.assertRaises(ValueError):unique_files([f,f|change])

    def test_download_estimate_counts_shared_content_once_and_reuses_other_filename(self):
        a=spec('a.safetensors');b=spec('b.safetensors')
        self.assertEqual(remaining_bytes(self.root,[a,b]),7)
        self.write(a)
        self.assertEqual(remaining_bytes(self.root,[b],[a,b]),0)
        self.assertEqual(file_status(self.root,[b],[a,b])[0]['id'],content_id(a))

    def test_verified_alias_has_one_physical_copy_and_survives_other_model_removal(self):
        a=spec('a.safetensors');b=spec('b.safetensors',folder='nested/vae')
        first=self.write(a)
        self.assertTrue(reuse_alias(self.root,b,[a,b],self.report,self.cancel))
        second=model_path(self.root,b);self.assertTrue(first.samefile(second))
        with patch('model_removal.all_models',return_value={'a':dict(name='A',files=[a]),'b':dict(name='B',files=[b])}):
            plan=removal_plan(self.root,'a');self.assertEqual(plan['bytes'],0)
            uninstall(self.root,'a',plan['ticket'],self.report,self.cancel)
        self.assertFalse(first.exists());self.assertEqual(second.read_bytes(),b'weights')

    def test_existing_duplicate_is_consolidated_without_changing_data(self):
        a=spec('a.safetensors');b=spec('b.safetensors');first=self.write(a);second=self.write(b)
        self.assertFalse(first.samefile(second))
        self.assertTrue(reuse_alias(self.root,b,[a,b],self.report,self.cancel))
        self.assertTrue(first.samefile(second));self.assertEqual(second.read_bytes(),b'weights')

    def test_corrupt_alias_is_not_reused_and_cancel_preserves_files(self):
        a=spec('a.safetensors');b=spec('b.safetensors');first=self.write(a,b'corrupt')
        self.assertFalse(reuse_alias(self.root,b,[a,b],self.report,self.cancel))
        self.assertFalse(model_path(self.root,b).exists())
        self.cancel.set()
        with self.assertRaises(Cancelled):reuse_alias(self.root,b,[a,b],self.report,self.cancel)
        self.assertEqual(first.read_bytes(),b'corrupt')

    def test_unsupported_hardlinks_do_not_download_a_duplicate_or_remove_existing_file(self):
        a=spec('a.safetensors');b=spec('b.safetensors');self.write(a);second=self.write(b)
        with patch('model_files.os.link',side_effect=OSError('unsupported')),self.assertRaisesRegex(RuntimeError,'No second copy'):
            reuse_alias(self.root,b,[a,b],self.report,self.cancel)
        self.assertEqual(second.read_bytes(),b'weights')
        self.assertFalse(list(second.parent.glob('.shared-*')))

    def test_two_packs_download_shared_weight_once_and_second_install_never_uses_network(self):
        f=spec('shared.safetensors');packs={'a':dict(files=[f]),'b':dict(files=[f|dict(url='https://different.invalid/base')])}
        with patch('packs.catalog',return_value=packs),patch('packs.manifest_files',return_value=[]),\
             patch('packs.runtime_python',return_value=Path(__file__)),patch('packs.shutil.disk_usage') as disk:
            disk.return_value.free=10**12
            with patch('packs.download',side_effect=lambda f,*args:self.write(f)) as get:
                install(self.root,['a','b'],self.report,self.cancel);self.assertEqual(get.call_count,1)
            with patch('packs.download',wraps=download),patch('downloads.urllib.request.build_opener') as network:
                install(self.root,['b'],self.report,self.cancel);network.assert_not_called()

    def test_different_finetunes_of_same_architecture_are_not_mistaken_for_duplicates(self):
        a=spec('one.safetensors');b=spec('two.safetensors',b'variant')
        self.write(a)
        self.assertFalse(reuse_alias(self.root,b,[a,b],self.report,self.cancel))
        self.assertEqual(remaining_bytes(self.root,[a,b]),len(b'variant'))

    def test_install_runtime_only_does_not_install_unrequested_wan_weights(self):
        marker=self.root/'runtime-ready.json';atomic_json(marker,dict(version=manifest()['runtime_version']))
        with patch('downloads.runtime_python',return_value=Path(__file__)),patch('downloads.download') as get,\
             patch('downloads.shutil.disk_usage') as disk:
            disk.return_value.free=10**12
            provision(self.root,self.report,self.cancel,include_models=False);get.assert_not_called()

    def test_wan13_uninstall_keeps_encoder_for_installed_wan22(self):
        for key in ('wan13','wan22'):
            files=manifest()['models'] if key=='wan13' else catalog()[key]['files']
            for f in files:self.write(f)
        plan=removal_plan(self.root,'wan13')
        self.assertIn('umt5_xxl_fp8_e4m3fn_scaled.safetensors',[x['filename'] for x in plan['shared']])
        self.assertNotIn('umt5_xxl_fp8_e4m3fn_scaled.safetensors',[x['filename'] for x in plan['files']])

    def test_general_image_models_have_workflows_editing_and_shared_sdxl_lora_scope(self):
        for key in ('realvisxl','cyberrealistic'):
            with self.subTest(model=key):
                options=validate_image_options(dict(model=key,prompt='A robot in a garden',seed=42))
                graph=image_workflow(options,'test')
                self.assertEqual(graph['1']['inputs']['ckpt_name'],catalog()[key]['files'][0]['filename'])
                edit=validate_edit_options(dict(model=key,prompt='A blue robot',source_image='source'))
                edit['input_file']='source.png'
                self.assertTrue(edit_workflow(edit,'test'))
                self.assertEqual(model_catalog()[key]['scope'],'sdxl')

    def test_krea2_uses_native_recipe_without_wrong_shift_or_negative_prompt(self):
        options=validate_image_options(dict(model='krea2',prompt='A robot',negative='ignored',cfg=8,seed=42))
        graph=image_workflow(options,'test')
        self.assertEqual(options['steps'],8);self.assertEqual(options['cfg'],1);self.assertEqual(options['negative'],'')
        self.assertEqual(graph['2']['inputs']['type'],'krea2')
        self.assertEqual(graph['6']['class_type'],'EmptyLatentImage')
        self.assertEqual(graph['5']['class_type'],'ConditioningZeroOut')
        self.assertNotIn('7',graph);self.assertEqual(graph['8']['inputs']['model'],['1',0])
        self.assertEqual(model_catalog()['krea2']['scope'],'krea2')
        with self.assertRaises(ValueError):validate_edit_options(dict(model='krea2',prompt='Edit',source_image='x'))
        with patch('engine_support.command',return_value=['python.exe']) as command:
            args=engine_command(self.root,1234,self.root/'output','low','krea2')
        command.assert_called_once_with(self.root,'qwen_turbo')
        self.assertIn('--enable-dynamic-vram',args);self.assertNotIn('--lowvram',args)


if __name__=='__main__':unittest.main()
