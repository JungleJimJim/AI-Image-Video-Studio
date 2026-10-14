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


if __name__ == '__main__':
    unittest.main()
