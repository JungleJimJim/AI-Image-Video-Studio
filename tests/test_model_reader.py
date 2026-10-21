import contextlib
import importlib.util
import io
import os
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

workspace = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('studio_model_reader', workspace/'assets/model_reader.py')
reader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reader)
try:
    import torch
except ImportError:
    torch = None


class ExactReadTests(unittest.TestCase):
    def test_partial_reads_are_completed_and_truncation_is_an_error(self):
        class Partial(io.BytesIO):
            def readinto(self, view):
                return super().readinto(view[:3])
        target = bytearray(13)
        reader.read_exact(Partial(b'hello, world!'), memoryview(target))
        self.assertEqual(target, b'hello, world!')
        with self.assertRaisesRegex(RuntimeError, 'ended before'):
            reader.read_exact(Partial(b'short'), memoryview(target))

    def test_other_engine_profiles_do_not_get_a_hook(self):
        before = list(sys.meta_path)
        for profile in ('base','wan22','flux3','qwen_turbo'):
            self.assertFalse(reader.install(profile))
        self.assertEqual(sys.meta_path, before)


@unittest.skipIf(torch is None, 'Run the numeric tensor checks with the installed engine Python')
class TensorReadTests(unittest.TestCase):
    def make_module(self):
        module = SimpleNamespace(torch=torch, QuantizedTensor=type('Quantized', (), {}),
                                 read_tensor_file_slice_into=Mock(return_value=False))
        return module

    def fixture(self, payload, offset=19):
        tensor = torch.empty(len(payload), dtype=torch.uint8)
        tensor.untyped_storage()._comfy_tensor_file_slice = SimpleNamespace(
            file_ref=io.BytesIO(b'_' * offset + payload), lock=threading.Lock(), offset=offset, size=len(payload))
        return tensor

    def test_multichunk_exact_bytes_cpu_with_short_reads_and_no_native_calls(self):
        payload = bytes(range(256)) * (reader.CHUNK_BYTES // 256 + 13)
        tensor = self.fixture(payload)
        module = self.make_module()
        @contextlib.contextmanager
        def opener(source):
            yield source
        reader.patch_reader(module, opener)
        result = torch.empty_like(tensor)
        self.assertTrue(module.read_tensor_file_slice_into(tensor, result))
        self.assertEqual(bytes(result.tolist()), payload)
        self.assertFalse(module.read_tensor_file_slice_into(tensor, result[:-1]))
        self.assertFalse(module.read_tensor_file_slice_into(tensor[1:], result))
        self.assertFalse(module.read_tensor_file_slice_into.__wrapped__.called)
        original = module.read_tensor_file_slice_into
        reader.patch_reader(module)
        self.assertIs(original, module.read_tensor_file_slice_into)

    def test_unbacked_tensors_and_quantization_use_the_original_handler(self):
        module = self.make_module()
        original = module.read_tensor_file_slice_into
        reader.patch_reader(module)
        module.read_tensor_file_slice_into(torch.ones(1), None)
        quantized = module.QuantizedTensor()
        module.read_tensor_file_slice_into(quantized, None)
        self.assertEqual(original.call_count, 2)

    def test_truncated_backed_tensor_never_silently_falls_back(self):
        tensor = self.fixture(b'abc')
        tensor.untyped_storage()._comfy_tensor_file_slice.file_ref = io.BytesIO(b'_' * 19 + b'ab')
        module = self.make_module()
        @contextlib.contextmanager
        def opener(source):
            yield source
        reader.patch_reader(module, opener)
        with self.assertRaisesRegex(RuntimeError, 'ended before'):
            module.read_tensor_file_slice_into(tensor, torch.empty_like(tensor))
        self.assertFalse(module.read_tensor_file_slice_into.__wrapped__.called)

    @unittest.skipUnless(os.name == 'nt', 'Windows file handle regression')
    def test_reopened_native_handle_reads_above_four_gib_and_preserves_original(self):
        import msvcrt
        offset = 4 * 1024**3 + 123
        with tempfile.TemporaryFile() as file:
            # Windows sparse allocation avoids creating a four-GB fixture.
            import ctypes
            from ctypes import wintypes
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel.DeviceIoControl.argtypes = [wintypes.HANDLE,wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD,
                                               ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(wintypes.DWORD),ctypes.c_void_p]
            count = wintypes.DWORD()
            handle = msvcrt.get_osfhandle(file.fileno())
            self.assertTrue(kernel.DeviceIoControl(handle, 0x900C4, None, 0, None, 0, ctypes.byref(count), None))
            file.seek(offset);file.write(b'bounded read test');file.flush();file.seek(7)
            with reader.synchronous_file(handle) as reopened:
                reopened.seek(offset)
                self.assertEqual(reopened.read(17), b'bounded read test')
            self.assertEqual(file.tell(), 7)
            file.seek(offset)
            self.assertEqual(file.read(17), b'bounded read test')


if __name__ == '__main__':
    unittest.main()
