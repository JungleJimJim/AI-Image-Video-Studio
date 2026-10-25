"""Reference wiring and queued source ownership, without loading model weights."""
import copy
from pathlib import Path
import sys,tempfile,unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from app import Studio
from engine import validate_options,build_workflow
from workflows import validate_image_options,image_workflow
from packs import catalog

class GenerationReferenceTests(unittest.TestCase):
    def image(self,model,refs):return validate_image_options(dict(model=model,prompt='A blue toy robot on a desk',seed=42,image_references=refs))
    def video(self,refs,**extra):return validate_options(dict(model='ref2va',mode='image',source_image='primary',prompt='A blue toy robot waves',width=768,height=512,frames=124,video_references=refs,**extra))

    def test_model_limits_and_invalid_references_are_enforced(self):
        for model,limit in [('fluxklein',3),('flux3',10),('viggle',3)]:
            self.assertEqual(catalog()[model]['generation_references'],limit)
            self.assertEqual(len(self.image(model,[str(i) for i in range(limit)])['image_references']),limit)
            for refs in ([str(i) for i in range(limit+1)],['same','same'],[''],[None],'image-id'):
                with self.subTest(model=model,refs=refs),self.assertRaises(ValueError):self.image(model,refs)
        for model in ('zimage','juggernaut','qwenimage','krea2','moss_sft'):
            with self.subTest(model=model),self.assertRaisesRegex(ValueError,'does not support'):self.image(model,['a'])

    def test_image_references_condition_native_empty_output_latents(self):
        for model,count in [('fluxklein',3),('flux3',10),('viggle',3)]:
            with self.subTest(model=model):
                o=self.image(model,[str(i) for i in range(count)])
                o.update(input_file='first.png',reference_files=[str(i)+'.png' for i in range(1,count)])
                g=image_workflow(o,'test');self.assertEqual(g['21']['class_type'],'ImageScaleToTotalPixels')
                self.assertEqual(g['6']['inputs']['width'],o['width']);self.assertEqual(g['6']['inputs']['height'],o['height'])
                self.assertEqual(sum(n['class_type']=='LoadImage' for n in g.values()),count)
                if model=='fluxklein':
                    self.assertEqual(sum(n['class_type']=='ReferenceLatent' for n in g.values()),count*2)
                    self.assertNotEqual(g['12']['inputs']['positive'],['4',0])
                elif model=='flux3':self.assertEqual(sum(k.startswith('images.image') for k in g['22']['inputs']),count)
                else:self.assertEqual(sum(k.startswith('images.image_') for k in g['4']['inputs']),count)
        self.assertFalse(any(n['class_type']=='LoadImage' for n in image_workflow(self.image('fluxklein',[]),'test').values()))

    def test_ref2va_uses_primary_plus_eight_native_reference_inputs(self):
        o=self.video([str(i) for i in range(8)]);o.update(input_file='primary.png',reference_files=[str(i)+'.png' for i in range(8)])
        g=build_workflow(o,'test');inputs=g['6']['inputs']
        self.assertEqual([k for k in inputs if k.startswith('ref_images.')],['ref_images.ref_image_'+str(i) for i in range(9)])
        self.assertEqual(g['58']['inputs']['image'],'7.png')
        for refs in (['primary'],['x','x'],[str(i) for i in range(9)]):
            with self.subTest(refs=refs),self.assertRaises(ValueError):self.video(refs)
        for model in ('wan22','ltx2','minimax_h3'):
            with self.subTest(model=model),self.assertRaises(ValueError):validate_options(dict(model=model,mode='image',source_image='primary',prompt='A robot',video_references=['extra']))

    def test_prepared_image_job_freezes_ids_stages_every_reference_and_saves_names(self):
        with tempfile.TemporaryDirectory() as tmp,patch('app.gpu_info',return_value={}):
            studio=Studio(tmp);records=[]
            for key in ('first','second'):
                path=Path(tmp)/(key+'.png');path.write_bytes(b'fixture');records.append(dict(id=key,path=str(path),name=key+'.png',width=512,height=512))
            studio.images=records;raw=dict(model='fluxklein',prompt='A blue toy robot',seed=42,image_references=['first','second'])
            with patch('app.install_ready',return_value=True),patch('app.pack_ready',return_value=True),patch.object(studio,'selected_loras',return_value=[]):
                target,options=studio.generate_image(raw,prepare=True)
            queued=studio.queue.add('image',options);raw['image_references'].clear()
            self.assertEqual(queued['options']['image_references'],['first','second'])
            result=Path(tmp)/'result.png';result.write_bytes(b'fixture')
            with patch('app.stage_image',side_effect=lambda root,record:record['id']+'.png') as stage,patch.object(studio.engine,'generate',return_value=(result,{},.1)) as generate,patch.object(studio.thumbnails,'get'):
                target()
            self.assertEqual(stage.call_count,2);self.assertEqual(generate.call_args.args[0]['reference_files'],['second.png'])
            self.assertEqual(studio.images[-1]['reference_names'],['first.png','second.png'])
            self.assertEqual(studio.images[-1]['reference_ids'],['first','second'])

if __name__=='__main__':unittest.main()
