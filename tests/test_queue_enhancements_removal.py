"""Scheduling and file-preservation regressions. Engine/SDK inference is mocked."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock,patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from app import Studio
from common import atomic_json,comfy_root
from downloads import Cancelled
from job_queue import JobQueue
from model_removal import removal_plan,uninstall
import enhancements


class QueueTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.patches=[patch('app.gpu_info',return_value={}),patch('app.install_ready',return_value=True),patch('app.pack_ready',return_value=True),patch('app.play_completion_ping')]
        for p in self.patches:p.start()
        self.studio=Studio(self.root);self.studio.queue.paused=True
        self.output=self.root/'fixture.png';self.output.write_bytes(b'existing-test-fixture')
        self.studio.engine.generate=Mock(return_value=(self.output,{},.1))

    def tearDown(self):
        self.studio.closing=True;self.studio.cancel.set();self.studio.engine.cancel.set()
        if self.studio.worker:self.studio.worker.join(5)
        for p in reversed(self.patches):p.stop()
        self.temp.cleanup()

    def wait_idle(self):
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            with self.studio.lock:
                if not self.studio.state['busy']:return
            time.sleep(.01)
        self.fail('Queue did not become idle')

    def add(self,prompt,priority=5,**extra):
        return self.studio.enqueue('image',dict(model='juggernaut',prompt=prompt,**extra),priority)

    def test_priority_serial_execution_and_seed_snapshot(self):
        seen=[];active=0;maximum=0
        def generate(options,*args,**kwargs):
            nonlocal active,maximum
            active+=1;maximum=max(maximum,active);seen.append((options['prompt'],options['seed']))
            time.sleep(.01);active-=1;return self.output,{},.1
        self.studio.engine.generate=generate
        a=self.add('Low',1);b=self.add('High',10);c=self.add('Normal',5)
        seeds={x['options']['prompt']:x['options']['seed'] for x in self.studio.queue.jobs}
        self.studio.queue_action({'action':'resume'});self.wait_idle()
        self.assertEqual([x[0] for x in seen],['High','Normal','Low'])
        self.assertEqual(dict(seen),seeds);self.assertEqual(maximum,1)
        self.assertTrue(all(x['status']=='completed' for x in self.studio.queue.jobs))

    def test_paused_edit_cancel_and_equal_priority_reorder(self):
        a=self.add('First');b=self.add('Second');c=self.add('Third')
        self.studio.queue_action(dict(action='move',id=c,direction='up'))
        self.assertEqual([x['id'] for x in self.studio.queue.pending()],[a,c,b])
        self.studio.queue_action(dict(action='update',id=b,options=dict(model='juggernaut',prompt='Edited',seed=73),priority=9))
        self.studio.queue_action(dict(action='cancel',id=a))
        self.studio.queue_action(dict(action='resume'));self.wait_idle()
        prompts=[c.args[0]['prompt'] for c in self.studio.engine.generate.call_args_list]
        self.assertEqual(prompts,['Edited','Third']);self.assertEqual(self.studio.queue.get(a)['status'],'cancelled')

    def test_cancel_running_job_skips_it_and_runs_the_next(self):
        started=threading.Event()
        def generate(options,*args,**kwargs):
            if options['prompt']=='Cancel me':
                started.set();self.studio.engine.cancel.wait(3);raise Cancelled('Cancelled')
            return self.output,{},.1
        self.studio.engine.generate=generate
        a=self.add('Cancel me');b=self.add('Keep me')
        self.studio.queue_action(dict(action='resume'));self.assertTrue(started.wait(2))
        with self.assertRaises(ValueError):self.studio.queue_action(dict(action='update',id=a,priority=1))
        self.studio.queue_action(dict(action='cancel',id=a));self.wait_idle()
        self.assertEqual(self.studio.queue.get(a)['status'],'cancelled')
        self.assertEqual(self.studio.queue.get(b)['status'],'completed')

    def test_failed_enhancement_preserves_original_and_pauses_remaining_jobs(self):
        self.studio.queue.continue_on_error=False
        self.studio.enhance_record=Mock(side_effect=RuntimeError('Enhancer unavailable'))
        a=self.add('Original',upscale=dict(enabled=True,options={}))
        b=self.add('Waiting')
        self.studio.queue_action(dict(action='resume'));self.wait_idle()
        self.assertEqual(len(self.studio.images),1);self.assertTrue(Path(self.studio.images[0]['path']).is_file())
        self.assertEqual(self.studio.queue.get(a)['status'],'failed');self.assertEqual(self.studio.queue.get(b)['status'],'queued')
        self.assertTrue(self.studio.queue.paused)

    def test_failure_continues_remaining_jobs_by_default_and_preserves_error(self):
        def generate(options,*args,**kwargs):
            if options['prompt']=='Broken':raise RuntimeError('LoRA menu validation failed')
            return self.output,{},.1
        self.studio.engine.generate=generate
        a=self.add('Broken');b=self.add('Next')
        self.studio.queue_action(dict(action='resume'));self.wait_idle()
        self.assertEqual(self.studio.queue.get(a)['status'],'failed')
        self.assertIn('LoRA menu validation failed',self.studio.queue.get(a)['error'])
        self.assertEqual(self.studio.queue.get(b)['status'],'completed')
        self.assertFalse(self.studio.queue.paused)

    def test_preparation_failure_also_continues_other_jobs(self):
        a=self.add('Broken');b=self.add('Next')
        self.studio.queue.get(a)['options']['model']='unavailable-model'
        self.studio.queue_action(dict(action='resume'));self.wait_idle()
        self.assertEqual(self.studio.queue.get(a)['status'],'failed')
        self.assertEqual(self.studio.queue.get(b)['status'],'completed')

    def test_failure_policy_persists_without_resuming_a_paused_queue(self):
        self.add('Waiting')
        self.studio.queue_action(dict(action='failure_policy',continue_on_error=False))
        reopened=JobQueue(self.root)
        self.assertFalse(reopened.continue_on_error);self.assertTrue(reopened.paused)
        self.studio.engine.generate.assert_not_called()
        with self.assertRaises(ValueError):self.studio.queue_action(dict(action='failure_policy',continue_on_error='yes'))

    def test_output_and_options_are_frozen_when_added(self):
        old=self.studio.settings['output'];a=self.add('Original',seed=11)
        self.studio.save_settings(dict(output=str(self.root/'New output')))
        self.studio.queue_action(dict(action='resume'));self.wait_idle()
        self.assertEqual(str(self.studio.engine.generate.call_args.args[1]),str(Path(old)/'Images'))
        self.assertEqual(self.studio.queue.get(a)['options']['seed'],11)

    def test_random_seed_preference_does_not_change_frozen_jobs_or_retries(self):
        a=self.add('Variation',seed=123,randomize_seed=True)
        b=self.add('Fixed',seed=456,randomize_seed=False)
        self.studio.queue_action(dict(action='resume'));self.wait_idle()
        self.assertEqual([c.args[0]['seed'] for c in self.studio.engine.generate.call_args_list],[123,456])
        self.studio.queue_action(dict(action='pause'))
        self.studio.queue_action(dict(action='retry',id=a))
        self.assertEqual(self.studio.queue.pending()[0]['options']['seed'],123)
        self.assertFalse(self.studio.settings['image_options']['randomize_seed'])
        self.assertEqual(self.studio.images[0]['options']['seed'],123)

    def test_masks_are_stored_separately_and_survive_queue_reopening(self):
        source=self.root/'source.png';source.write_bytes(b'fixture')
        self.studio.images=[dict(id='source',path=str(source),name=source.name,width=512,height=512)]
        mask='data:image/png;base64,aGVsbG8='
        a=self.studio.enqueue('edit',dict(model='juggernaut',prompt='Edit',source_image='source',mask=mask))
        self.assertNotIn(mask,(self.root/'queue.json').read_text())
        reopened=JobQueue(self.root);item=reopened.get(a)
        self.assertTrue(reopened.paused);self.assertEqual(self.studio.hydrate_queued(item)['mask'],mask)

    def test_queue_model_blocks_uninstall_before_any_files_change(self):
        self.add('Pending')
        with patch('app.uninstall_model') as remove,self.assertRaises(ValueError):self.studio.remove_model('juggernaut','ticket')
        remove.assert_not_called()

    def test_recovery_requires_review_and_history_clear_keeps_media(self):
        a=self.add('Interrupted');self.studio.queue.get(a)['status']='running';self.studio.queue.save()
        reopened=JobQueue(self.root)
        self.assertEqual(reopened.get(a)['status'],'interrupted')
        self.assertIsNone(reopened.next())
        self.studio.queue_action(dict(action='clear_finished'))
        self.assertEqual(self.output.read_bytes(),b'existing-test-fixture')

    def test_invalid_priority_does_not_start_inference(self):
        for value in (-1,11,1.2,float('nan'),'high'):
            with self.subTest(value=value),self.assertRaises(ValueError):self.add('Bad',value)
        self.studio.engine.generate.assert_not_called()

    def test_mixed_image_video_and_enhancement_jobs_execute_serially(self):
        self.studio.images=[dict(id='source',path=str(self.output),width=512,height=512)]
        seen=[]
        def generate(options,*args,**kwargs):
            seen.append((kwargs.get('kind','video'),options['prompt']))
            return self.output,{},.1
        self.studio.engine.generate=generate
        self.studio.enhance_record=Mock(side_effect=lambda *a:seen.append(('enhance',a[1])))
        self.add('Image first',8)
        self.studio.enqueue('video',dict(model='wan22',mode='text',prompt='Video second'),5)
        self.studio.enqueue('enhance_image',dict(source_id='source'),1)
        self.studio.queue_action(dict(action='resume'));self.wait_idle()
        self.assertEqual(seen,[('image','Image first'),('video','Video second'),('enhance','image')])
        self.assertTrue(all(x['status']=='completed' for x in self.studio.queue.jobs))

    def test_lora_selection_for_future_jobs_does_not_mutate_running_job(self):
        started=threading.Event();finish=threading.Event();seen=[]
        def generate(options,*args,**kwargs):
            seen.append(options['loras'])
            if len(seen)==1:started.set();finish.wait(3)
            return self.output,{},.1
        self.studio.engine.generate=generate
        adapter=dict(name='studio/sdxl/new.safetensors',strength=.7)
        with patch('app.validate_selection',side_effect=lambda root,selected,model:selected):
            self.add('Running');self.studio.queue_action(dict(action='resume'))
            self.assertTrue(started.wait(2))
            self.studio.update_loras([adapter],'juggernaut')
            self.add('Next');finish.set();self.wait_idle()
        self.assertEqual(seen,[[],[adapter]])


class RemovalTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.models={'one':dict(name='One',files=[dict(folder='diffusion_models',filename='one.safetensors'),dict(folder='text_encoders',filename='shared.safetensors')]),
                     'two':dict(name='Two',files=[dict(folder='diffusion_models',filename='two.safetensors'),dict(folder='text_encoders',filename='shared.safetensors')])}
        self.patch=patch('model_removal.all_models',return_value=self.models);self.patch.start()
        for pack in self.models.values():
            for f in pack['files']:
                file=comfy_root(self.root)/'models'/f['folder']/f['filename'];file.parent.mkdir(parents=True,exist_ok=True);file.write_bytes(b'weights')
        for name in ('settings.json','library.json','images.json','loras.json'):(self.root/name).write_text('preserved')

    def tearDown(self):self.patch.stop();self.temp.cleanup()

    def test_shared_dependencies_and_private_data_are_preserved(self):
        p=removal_plan(self.root,'one');self.assertEqual([x['filename'] for x in p['files']],['one.safetensors'])
        uninstall(self.root,'one',p['ticket'],lambda *a:None,threading.Event())
        self.assertTrue((comfy_root(self.root)/'models/text_encoders/shared.safetensors').is_file())
        for name in ('settings.json','library.json','images.json','loras.json'):self.assertEqual((self.root/name).read_text(),'preserved')
        p=removal_plan(self.root,'two');self.assertEqual(len(p['files']),2)

    def test_stale_preview_and_outside_paths_are_rejected(self):
        p=removal_plan(self.root,'one');file=Path(p['files'][0]['path']);file.write_bytes(b'changed after preview')
        with self.assertRaises(ValueError):uninstall(self.root,'one',p['ticket'],lambda *a:None,threading.Event())
        self.assertTrue(file.exists())
        with patch('model_removal.model_path',return_value=self.root/'outside.safetensors'),self.assertRaises(ValueError):removal_plan(self.root,'one')

    def test_partial_other_model_keeps_its_shared_encoder(self):
        file=comfy_root(self.root)/'models/diffusion_models/two.safetensors';file.rename(file.with_name(file.name+'.part'))
        p=removal_plan(self.root,'one');self.assertEqual(len(p['shared']),1)

    def test_shared_partial_download_is_kept_for_remaining_model(self):
        file=comfy_root(self.root)/'models/text_encoders/shared.safetensors'
        file.rename(file.with_name(file.name+'.part'))
        p=removal_plan(self.root,'one')
        self.assertEqual([x['filename'] for x in p['shared']],['shared.safetensors.part'])
        uninstall(self.root,'one',p['ticket'],lambda *a:None,threading.Event())
        self.assertTrue(file.with_name(file.name+'.part').is_file())

    def test_cancel_before_removal_keeps_weights(self):
        p=removal_plan(self.root,'one');cancel=threading.Event();cancel.set()
        with self.assertRaises(Cancelled):uninstall(self.root,'one',p['ticket'],lambda *a:None,cancel)
        self.assertTrue(Path(p['files'][0]['path']).is_file())


class EnhancementTests(unittest.TestCase):
    def test_sdk_installer_is_pinned_and_preserves_dependency_stack(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);python=root/'python.exe';python.touch()
            config=dict(revision='pinned',packages=['nvidia-vfx==0.2.0.0'],files=[],
                        wheels=[dict(filename='fixture.whl',size=10,sha256='a'*64,url='https://pypi.nvidia.com/fixture.whl')])
            manifest=root/'enhancers.json';manifest.write_text(json.dumps(dict(rtx_vsr=config)))
            def download(file,dest,*args):dest.write_bytes(b'fixture');return dest
            installer=Mock(poll=Mock(return_value=0),returncode=0)
            with patch('enhancements.runtime_python',return_value=python),patch('enhancements.resource',return_value=manifest),\
                 patch('enhancements.download',side_effect=download),patch('enhancements.subprocess.Popen',return_value=installer) as launch,\
                 patch('enhancements.subprocess.run',return_value=Mock(returncode=1,stderr='Import failed')) as check,\
                 patch('enhancements.shutil.disk_usage',return_value=Mock(free=10*1024**3)):
                with self.assertRaises(RuntimeError):enhancements.install_video(root,lambda *a:None,threading.Event())
                marker=enhancements.extension_root(root)/'installed.json'
                self.assertFalse(marker.exists())
                command=launch.call_args.args[0]
                self.assertIn('--no-deps',command);self.assertIn('--no-index',command)
                check.return_value=Mock(returncode=0)
                enhancements.install_video(root,lambda *a:None,threading.Event())
                self.assertEqual(json.loads(marker.read_text())['revision'],'pinned')

    def test_image_graph_conditions_on_source_and_chains_detail_adapter(self):
        o=enhancements.validate({},'image')|dict(input_file='source.png',width=2048,height=2048,loras=[dict(name='extra.safetensors',strength=.4)])
        g=enhancements.image_workflow(o,'fixture')
        self.assertEqual(g['5']['inputs']['images.image_1'],['4',0])
        adapters=[x for x in g.values() if x['class_type']=='LoraLoaderModelOnly'];self.assertEqual(len(adapters),2)
        self.assertEqual(g['5']['inputs']['clip'],['2',0]);self.assertEqual(g['7']['inputs']['negative'],['5',1])

    def test_image_size_cap_and_nonfinite_options(self):
        for width,height in [(1024,1024),(3000,4000),(4096,256)]:
            w,h=enhancements.image_size(width,height,4);self.assertLessEqual(w*h,2048**2);self.assertLessEqual(max(w,h),4096)
        for kind,key in [('image','scale'),('image','detail_strength'),('video','strength')]:
            with self.assertRaises(ValueError):enhancements.validate({key:float('nan')},kind)

    def test_video_output_moves_only_verified_private_worker_file_and_keeps_user_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);out=root/'Videos';out.mkdir();(out/'cache').mkdir();sentinel=out/'cache/user.txt';sentinel.write_text('keep')
            source=root/'original.mp4';source.write_bytes(b'original fixture')
            def launch(command,**kwargs):
                data=json.loads(Path(command[-1]).read_text());private=Path(data['output']);private.mkdir();result=private/'result_RTXVSR.mp4';result.write_bytes(b'processed fixture')
                atomic_json(data['result'],dict(output=str(result),resolution='512x512',seconds=.1));return Mock(poll=Mock(return_value=0),returncode=0)
            with patch('enhancements.vsr_ready',return_value=True),patch('enhancements.subprocess.Popen',side_effect=launch):
                result=enhancements.run_video(root,source,out,enhancements.VIDEO_DEFAULTS,lambda *a:None,threading.Event())
            self.assertEqual(Path(result['output']).parent,out);self.assertEqual(sentinel.read_text(),'keep');self.assertEqual(source.read_bytes(),b'original fixture')


if __name__=='__main__':unittest.main()
