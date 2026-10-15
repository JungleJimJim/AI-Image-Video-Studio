"""Regression coverage for native crashes and temporary local-engine stalls."""
from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from downloads import Cancelled
from engine import Engine, engine_command, validate_options
from enhancements import validate as validate_enhancement
from loras import apply_to_graph, resolve_engine_names


class EngineResilienceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / 'logs').mkdir()
        self.log = self.root / 'logs/engine.log'
        self.log.write_text('Loading models\n')
        self.report = Mock()
        self.engine = Engine(self.root, self.report)
        self.engine.process = Mock()
        self.engine.process.poll.return_value = None

    def tearDown(self):
        self.tmp.cleanup()

    def test_wan22_auto_and_low_use_native_loader_without_pinned_cache(self):
        for mode in ('auto', 'low'):
            command = engine_command(self.root, 12345, self.root, mode, 'wan22')
            self.assertIn('--enable-dynamic-vram', command)
            self.assertIn('--disable-pinned-memory', command)
            self.assertNotIn('--disable-dynamic-vram', command)
            self.assertNotIn('--lowvram', command)
            self.assertEqual('--vram-headroom' in command, mode == 'low')
        self.assertIn('--lowvram', engine_command(self.root, 12345, self.root, 'low', 'wan13'))

    def test_polling_recovers_from_timeout_without_resubmitting_job(self):
        completed = {'status': {'completed': True}}
        self.engine.request = Mock(side_effect=[TimeoutError('timed out'), {'same-job': completed}])
        self.engine.cancel.wait = Mock(return_value=False)
        self.assertEqual(self.engine.wait_for_history('same-job'), completed)
        self.assertEqual([call.args for call in self.engine.request.call_args_list],
                         [('/history/same-job',), ('/history/same-job',)])
        self.report.assert_called_once()

    def test_empty_response_is_retried_without_losing_the_job(self):
        self.engine.request = Mock(side_effect=[json.JSONDecodeError('Expecting value', '', 0), {'job': {'outputs': {}}}])
        self.engine.cancel.wait = Mock(return_value=False)
        self.assertEqual(self.engine.wait_for_history('job'), {'outputs': {}})

    def test_exit_during_timeout_shows_actual_crash_instead_of_timed_out(self):
        self.log.write_text('Windows fatal exception: access violation\nStack: load_torch_file\n')
        self.engine.process.poll.side_effect = [None, -1073741819]
        self.engine.request = Mock(side_effect=TimeoutError('timed out'))
        with self.assertRaisesRegex(RuntimeError, 'Windows access violation'):
            self.engine.wait_for_history('job')

    def test_fatal_crash_log_is_detected_before_windows_finishes_teardown(self):
        self.log.write_text('Windows fatal exception: access violation\n')
        self.engine.request = Mock(side_effect=TimeoutError('timed out'))
        with patch.object(self.engine, 'stop') as stop, self.assertRaisesRegex(RuntimeError, 'Windows access violation'):
            self.engine.wait_for_history('job')
        stop.assert_called_once()

    def test_long_unresponsive_engine_stops_owned_job_before_reporting_failure(self):
        self.engine.request = Mock(side_effect=TimeoutError('timed out'))
        with patch('engine.time.monotonic', side_effect=[0, 121]), \
                patch.object(self.engine, 'stop') as stop, self.assertRaisesRegex(RuntimeError, 'two minutes'):
            self.engine.wait_for_history('job')
        stop.assert_called_once()

    def test_cancel_remains_available_during_polling_retries(self):
        self.engine.request = Mock(side_effect=TimeoutError('timed out'))
        self.engine.cancel.wait = Mock(side_effect=lambda _: self.engine.cancel.set())
        with patch.object(self.engine, 'stop') as stop, self.assertRaises(Cancelled):
            self.engine.wait_for_history('job')
        stop.assert_called_once()
        self.assertEqual(self.engine.request.call_count, 1)

    def test_job_submission_timeout_never_submits_a_second_job_or_leaves_engine_running(self):
        process = self.engine.process
        self.engine.request = Mock(side_effect=TimeoutError('timed out'))
        with patch.object(self.engine, 'start'), self.assertRaisesRegex(RuntimeError, 'no duplicate job'):
            self.engine.generate(validate_options({'prompt': 'A toy robot'}), self.root)
        self.assertEqual(self.engine.request.call_count, 1)
        self.assertEqual(self.engine.request.call_args.args[0], '/prompt')
        process.terminate.assert_called_once()
        self.assertIsNone(self.engine.process)

    def test_enhancer_submits_exact_windows_lora_menu_names_with_strength_above_one(self):
        builtin = 'studio/qwen21/elusarcas-qwen2-1-detailer-v1.safetensors'
        extra = 'studio/qwen21/extra.safetensors'
        options = validate_enhancement({'detail_strength': 1.7}, 'image')
        options.update(model='qwen21', input_file='source.png', width=1024, height=1024,
                       loras=[dict(name=extra, strength=.4)])
        output = self.root / 'fixture.png'
        output.write_bytes(b'mocked output; no inference')
        def request(path, data=None, **kwargs):
            if path == '/object_info/LoraLoaderModelOnly':
                return {'LoraLoaderModelOnly': {'input': {'required': {
                    'lora_name': [[builtin.replace('/', '\\'), extra.replace('/', '\\')]]}}}}
            self.assertEqual(path, '/prompt')
            loaders = [n['inputs'] for n in data['prompt'].values() if n['class_type']=='LoraLoaderModelOnly']
            self.assertEqual([n['lora_name'] for n in loaders], [builtin.replace('/', '\\'), extra.replace('/', '\\')])
            self.assertEqual([n['strength_model'] for n in loaders], [1.7, .4])
            return {'prompt_id': 'mocked'}
        self.engine.request = Mock(side_effect=request)
        self.engine.cancel.wait = Mock(return_value=False)
        history = dict(status={'completed': True}, outputs={'9': {'images': [{'filename': output.name}]}})
        with patch.object(self.engine, 'start'), patch.object(self.engine, 'wait_for_history', return_value=history):
            result, _, _ = self.engine.generate(options, self.root, kind='enhance')
        self.assertEqual(result, output)
        self.assertEqual(options['loras'][0]['name'], extra)
        self.assertEqual(self.engine.request.call_count, 2)

    def test_lora_menu_resolution_supports_both_loaders_and_combo_schemas(self):
        options = {'loras': [dict(name='studio/family/style.safetensors', strength=1.5)]}
        for clip in (None, ['2', 0]):
            for native in ('studio/family/style.safetensors', 'studio\\family\\style.safetensors'):
                for schema in ([native], 'COMBO'):
                    with self.subTest(clip=clip, native=native, schema=schema):
                        graph = apply_to_graph({}, options, ['1', 0], clip)
                        loader = graph['1000']['class_type']
                        info = {loader: {'input': {'required': {'lora_name': [schema, {'options': [native]}]}}}}
                        resolve_engine_names(graph, info)
                        self.assertEqual(graph['1000']['inputs']['lora_name'], native)
                        self.assertEqual(graph['1000']['inputs']['strength_model'], 1.5)
        self.assertEqual(options['loras'][0]['name'], 'studio/family/style.safetensors')

    def test_missing_lora_is_not_replaced_by_a_different_file_with_the_same_basename(self):
        graph = apply_to_graph({}, {'loras': [dict(name='studio/qwen21/style.safetensors', strength=1)]}, ['1', 0])
        info = {'LoraLoaderModelOnly': {'input': {'required': {'lora_name': [['studio\\flux3\\style.safetensors']]}}}}
        with self.assertRaisesRegex(ValueError, 'cannot find the selected LoRA'):
            resolve_engine_names(graph, info)


if __name__ == '__main__':
    unittest.main()
