import importlib.util
import functools
import json
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace,ModuleType
import unittest
from unittest.mock import Mock,patch

workspace=Path(__file__).resolve().parents[1];sys.path.insert(0,str(workspace/'src'))
from app import Studio
from common import atomic_json
from engine import Engine,engine_command
import attention_support as support
spec=importlib.util.spec_from_file_location('studio_attention_worker',workspace/'assets/attention_worker.py')
worker=importlib.util.module_from_spec(spec);spec.loader.exec_module(worker)


class AttentionTests(unittest.TestCase):
    def test_native_library_is_initialized_before_consumers_cache_its_handle(self):
        control=SimpleNamespace(lib=None)
        def initialize():
            control.lib=object()
            return True
        control.init=Mock(side_effect=initialize)
        worker.initialize_native_memory(SimpleNamespace(enables_dynamic_vram=lambda:True),control)
        consumer=SimpleNamespace(lib=control.lib)
        self.assertIsNotNone(consumer.lib)
        self.assertIs(consumer.lib,control.lib)
        control.init.assert_called_once()
        control.init=Mock(return_value=False)
        with self.assertRaises(RuntimeError):
            worker.initialize_native_memory(SimpleNamespace(enables_dynamic_vram=lambda:True),control)
        control.init.reset_mock()
        worker.initialize_native_memory(SimpleNamespace(enables_dynamic_vram=lambda:False),control)
        control.init.assert_not_called()

    def test_fallback_reuses_tensors_after_single_owner_containers_are_consumed(self):
        class Container:
            def __init__(self, tensor):self.tensor=tensor
            def take(self):
                if self.tensor is None:raise RuntimeError('Container already consumed')
                value=self.tensor;self.tensor=None;return value
        def consuming_wrapper(function):
            @functools.wraps(function)
            def wrapped(q,k,v,*args,**kwargs):
                if isinstance(q,Container):q,k,v=(x.take() for x in (q,k,v))
                return function(q,k,v,*args,**kwargs)
            return wrapped
        accelerated=consuming_wrapper(Mock(side_effect=ValueError('Unsupported input')))
        standard=Mock(return_value='fallback')
        call=worker.safe_attention(accelerated,consuming_wrapper(standard),lambda x:True,Mock(),
                                   wrap=consuming_wrapper)
        self.assertEqual(call(Container('q'),Container('k'),Container('v'),8),'fallback')
        standard.assert_called_once_with('q','k','v',8)

    def test_supported_call_preserves_all_arguments_and_reports_actual_use_once(self):
        original=Mock(return_value='answer');fallback=Mock();update=Mock()
        original.container_function=Mock()
        call=worker.safe_attention(original,fallback,lambda x:True,update)
        self.assertEqual(call('q','k','v',8,mask='mask',scale=.25),'answer')
        original.assert_called_once_with('q','k','v',8,mask='mask',scale=.25)
        self.assertFalse(hasattr(call,'container_function'))
        call('q','k','v',8);self.assertEqual(update.call_count,1);fallback.assert_not_called()

    def test_failing_call_falls_back_in_place_and_disables_acceleration_for_this_engine(self):
        original=Mock(side_effect=ValueError('unsupported shape'));fallback=Mock(return_value='standard');update=Mock()
        call=worker.safe_attention(original,fallback,lambda x:True,update)
        self.assertEqual(call('q','k','v',8,mask='m'),'standard')
        fallback.assert_called_once_with('q','k','v',8,mask='m')
        call('q2','k2','v2',8);self.assertEqual(original.call_count,1);self.assertEqual(update.call_count,1)
        self.assertEqual(update.call_args.args[0],'pytorch_fallback')

    def test_nonfinite_output_falls_back_but_bad_cuda_context_or_oom_never_retries(self):
        fallback=Mock(return_value='finite');update=Mock()
        call=worker.safe_attention(Mock(return_value='nan'),fallback,lambda x:False,update)
        self.assertEqual(call('q','k','v',8),'finite')
        for error in ('CUDA out of memory','device-side assert triggered','illegal memory access','misaligned address'):
            with self.subTest(error=error):
                standard=Mock();call=worker.safe_attention(Mock(side_effect=RuntimeError(error)),standard,lambda x:True,Mock())
                with self.assertRaises(RuntimeError):call('q','k','v',8)
                standard.assert_not_called()

    def test_default_commands_are_unchanged_and_optional_engine_paths_are_forwarded(self):
        regular=engine_command('root',1234,'out','auto','wan22')
        self.assertNotIn('--use-ck-attention',regular)
        accelerated=engine_command('root',1234,'out','auto','wan22','sage','session')
        self.assertIn('attention_worker.py',accelerated[2]);self.assertIn('--session',accelerated)
        self.assertEqual(accelerated[accelerated.index('--')+1:],regular[3:])
        with patch('engine_support.command',return_value=['python.exe','-s','engine_worker.py','engine-dir','--offline']):
            accelerated=engine_command('root',1234,'out','auto','krea2','sage','id')
        self.assertIn('--engine-dir',accelerated)
        self.assertIn('qwen_turbo',accelerated[accelerated.index('--engine-dir')+1])
        self.assertNotIn('engine-dir',accelerated[accelerated.index('--')+1:])
        self.assertEqual(Path(accelerated[accelerated.index('--entry')+1]),Path('root/engines/qwen_turbo/code/main.py'))
        self.assertIn('--offline',accelerated[accelerated.index('--')+1:])
        with self.assertRaises(ValueError):engine_command('root',1234,'out','auto',attention='untrusted')

    def test_unavailable_kernel_starts_pytorch_instead_of_loading_missing_sage_package(self):
        update=Mock();kitchen=Mock();kitchen.int8_attention_is_available.return_value=False
        torch=SimpleNamespace(__version__='test')
        with tempfile.TemporaryDirectory() as tmp,patch.object(worker,'probe',return_value=dict(available=False,reason='No kernel')),\
             patch.object(sys,'argv',['test']):
            worker.configure(Path(tmp)/'main.py',['--cpu'],update,kitchen,torch)
            self.assertEqual(sys.argv[-1],'--use-pytorch-cross-attention')
        self.assertEqual(update.call_args.args[0],'pytorch_fallback')

    def test_preference_saves_during_work_without_stopping_engine_and_invalid_value_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp,patch('app.gpu_info',return_value={}):
            studio=Studio(tmp);studio.state['busy']=True
            with patch.object(studio.engine,'stop') as stop:
                studio.save_settings({'attention':'sage'});stop.assert_not_called()
            self.assertEqual(studio.engine.attention,'sage')
            self.assertEqual(json.loads((Path(tmp)/'settings.json').read_text())['attention'],'sage')
            with self.assertRaises(ValueError):studio.save_settings({'attention':'invalid'})
            self.assertEqual(studio.engine.attention,'sage')

    def test_failed_settings_write_restores_runtime_preference(self):
        with tempfile.TemporaryDirectory() as tmp,patch('app.gpu_info',return_value={}):
            studio=Studio(tmp);before=studio.settings.copy()
            with patch('app.atomic_json',side_effect=OSError('disk full')),self.assertRaises(OSError):
                studio.save_settings({'attention':'sage'})
            self.assertEqual(studio.settings,before);self.assertEqual(studio.engine.attention,'pytorch')

    def test_supported_engine_registers_guarded_backend_without_container_bypass(self):
        original=Mock();original.container_function=Mock()
        attention=SimpleNamespace(attention_comfy_kitchen_int8=original,attention_pytorch=Mock(),
                                  wrap_attn=Mock(side_effect=lambda function:function),REGISTERED_ATTENTION_FUNCTIONS={})
        comfy=ModuleType('comfy');comfy.options=SimpleNamespace(enable_args_parsing=Mock())
        comfy.cli_args=SimpleNamespace(enables_dynamic_vram=lambda:False)
        comfy.ldm=ModuleType('comfy.ldm');comfy.ldm.modules=ModuleType('comfy.ldm.modules');comfy.ldm.modules.attention=attention
        modules={'comfy':comfy,'comfy.options':comfy.options,'comfy.cli_args':comfy.cli_args,'comfy.ldm':comfy.ldm,'comfy.ldm.modules':comfy.ldm.modules,'comfy.ldm.modules.attention':attention}
        with patch.dict(sys.modules,modules),patch.object(worker,'probe',return_value=dict(available=True)),patch.object(worker,'Path') as path,patch.object(sys,'argv',['test']):
            path.return_value.is_file.return_value=True;path.return_value.read_text.return_value='--use-ck-attention'
            worker.configure('main.py',[],Mock(),Mock(),Mock())
            self.assertIn('--use-ck-attention',sys.argv)
            self.assertIs(attention.optimized_attention,attention.optimized_attention_masked)
            self.assertIs(attention.optimized_attention,attention.REGISTERED_ATTENTION_FUNCTIONS['comfy_kitchen_int8'])
            attention.wrap_attn.assert_called_once()
            self.assertFalse(hasattr(attention.optimized_attention,'container_function'))

    def test_engine_restart_signature_includes_attention_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine=Engine(tmp,Mock());engine.process=Mock();engine.process.poll.return_value=None
            engine.signature=('auto','out','wan13','pytorch')
            engine.start('auto','out','wan13')
            engine.attention='sage'
            engine.stop=Mock(side_effect=RuntimeError('restart requested'))
            with self.assertRaisesRegex(RuntimeError,'restart requested'):engine.start('auto','out','wan13')

    def test_busy_app_rejects_math_check_and_success_enables_only_attention_preference(self):
        with tempfile.TemporaryDirectory() as tmp,patch('app.gpu_info',return_value={}):
            studio=Studio(tmp);studio.state['busy']=True
            with patch('attention_support.check') as probe,self.assertRaises(ValueError):studio.check_attention(True)
            probe.assert_not_called();studio.state['busy']=False
            studio.settings['custom']='preserved'
            with patch('attention_support.check',return_value=dict(available=True)),patch.object(studio.engine,'stop'):
                studio.check_attention(True);studio.worker.join(5)
            self.assertEqual(studio.settings['attention'],'sage');self.assertEqual(studio.settings['custom'],'preserved')

    def test_failed_compatibility_check_keeps_existing_preference_and_no_models_are_downloaded(self):
        with tempfile.TemporaryDirectory() as tmp,patch('app.gpu_info',return_value={}):
            studio=Studio(tmp)
            with patch('attention_support.check',return_value=dict(available=False)),patch.object(studio.engine,'stop'):
                studio.check_attention(True);studio.worker.join(5)
            self.assertEqual(studio.settings.get('attention','pytorch'),'pytorch')

    def test_stale_status_from_an_old_engine_is_not_shown_as_current_use(self):
        with tempfile.TemporaryDirectory() as tmp:
            atomic_json(Path(tmp)/'attention-status.json',dict(session='old',active='sage'))
            engine=SimpleNamespace(process=None,attention_session='new',signature=None)
            self.assertEqual(support.snapshot(tmp,'sage',engine)['active'],'idle')
            worker.write_status(Path(tmp)/'attention-status.json',dict(session='new',active='sage'))
            engine.process=Mock();engine.process.poll.return_value=None
            self.assertEqual(support.snapshot(tmp,'sage',engine)['active'],'sage')

    def test_cancelling_math_probe_stops_only_its_own_subprocess(self):
        with tempfile.TemporaryDirectory() as tmp,patch('attention_support.runtime_python',return_value=Path(__file__)),\
             patch('attention_support.subprocess.Popen') as popen:
            process=popen.return_value;process.poll.return_value=None
            process.communicate.return_value=('','')
            cancel=threading.Event();cancel.set()
            from downloads import Cancelled
            with self.assertRaises(Cancelled):support.check(tmp,Mock(),cancel)
            process.terminate.assert_called_once()

    def test_timed_out_probe_retains_diagnostics_and_terminates_only_its_child(self):
        with tempfile.TemporaryDirectory() as tmp,patch('attention_support.runtime_python',return_value=Path(__file__)),\
             patch('attention_support.subprocess.Popen') as popen,patch('attention_support.time.monotonic',side_effect=[0,181]):
            process=popen.return_value;process.poll.return_value=None
            process.communicate.return_value=('STUDIO_ATTENTION_STAGE Loading Comfy Kitchen\n','diagnostic')
            with self.assertRaisesRegex(RuntimeError,'attention-check.log'):
                support.check(tmp,Mock(),threading.Event())
            process.terminate.assert_called_once()
            self.assertIn('Loading Comfy Kitchen',(Path(tmp)/'logs/attention-check.log').read_text())
            self.assertFalse((Path(tmp)/'attention-check.json').exists())


if __name__=='__main__':unittest.main()
