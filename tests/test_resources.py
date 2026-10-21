import ctypes
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from resources import NvmlSampler, sample_gpu


class ResourceTests(unittest.TestCase):
    def test_unavailable_activity_preserves_memory_without_fabricating_zero(self):
        for value in ('[N/A]', 'N/A', 'nan', '-1', '101'):
            with self.subTest(value=value), patch('resources.subprocess.run') as run:
                run.return_value.returncode = 0
                run.return_value.stdout = f'{value}, 4096, 16384\n'
                sample = sample_gpu()
                self.assertIsNone(sample['percent'])
                self.assertEqual(sample['used'], 4*1024**3)

    def test_real_zero_is_not_unavailable(self):
        with patch('resources.subprocess.run') as run:
            run.return_value.returncode = 0
            run.return_value.stdout = '0, 4096, 16384\n'
            self.assertEqual(sample_gpu()['percent'], 0)

    def test_driver_telemetry_and_unsupported_utilization(self):
        api = Mock()
        api.nvmlInit_v2.return_value = api.nvmlDeviceGetHandleByIndex_v2.return_value = 0
        def memory(handle, output):
            value = ctypes.cast(output, ctypes.POINTER(NvmlSampler.Memory)).contents
            value.total, value.used = 16*1024**3, 8*1024**3
            return 0
        def utilization(handle, output):
            ctypes.cast(output, ctypes.POINTER(NvmlSampler.Utilization)).contents.gpu = 87
            return 0
        api.nvmlDeviceGetMemoryInfo.side_effect = memory
        api.nvmlDeviceGetUtilizationRates.side_effect = utilization
        with patch('resources.ctypes.CDLL', return_value=api) as load:
            sampler = NvmlSampler()
            self.assertTrue(str(load.call_args.args[0]).lower().endswith('system32\\nvml.dll'))
            sample = sampler.sample()
            self.assertEqual(sample['percent'], 87)
            self.assertEqual(sample['used'], 8*1024**3)
            api.nvmlDeviceGetUtilizationRates.side_effect = None
            api.nvmlDeviceGetUtilizationRates.return_value = 3
            self.assertIsNone(sampler.sample()['percent'])
            sampler.close()
            api.nvmlShutdown.assert_called_once()

    def test_device_loss_does_not_reuse_an_old_reading(self):
        api = Mock()
        api.nvmlInit_v2.return_value = api.nvmlDeviceGetHandleByIndex_v2.return_value = 0
        api.nvmlDeviceGetMemoryInfo.return_value = 15
        with patch('resources.ctypes.CDLL', return_value=api):
            sampler = NvmlSampler()
            with self.assertRaises(OSError):
                sampler.sample()
            sampler.close()
