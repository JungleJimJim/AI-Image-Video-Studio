"""Bounded synchronous Windows reads for MiniMax's disk-backed tensor slices."""
import contextlib
import ctypes
import functools
import importlib.abc
import importlib.machinery
import io
import os
import sys
import threading

CHUNK_BYTES = 1024 * 1024
_transfer_lock = threading.RLock()


@contextlib.contextmanager
def synchronous_file(source):
    """Reopen the same file, without OVERLAPPED or changing its original pointer."""
    import msvcrt
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    reopen = kernel.ReOpenFile
    reopen.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD]
    reopen.restype = wintypes.HANDLE
    handle = source if isinstance(source, int) else msvcrt.get_osfhandle(source.fileno())
    new_handle = reopen(handle, 0x80000000, 7, 0x08000000)
    if new_handle in (None, ctypes.c_void_p(-1).value):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        fd = msvcrt.open_osfhandle(new_handle, os.O_RDONLY | os.O_BINARY)
    except BaseException:
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle(new_handle)
        raise
    with io.FileIO(fd, 'rb', closefd=True) as file:
        yield file


def read_exact(file, view):
    done = 0
    while done < len(view):
        count = file.readinto(view[done:])
        if not count:
            raise RuntimeError('The model file ended before its tensor was complete. Check the model download.')
        done += count


def patch_reader(module, opener=synchronous_file):
    if getattr(module.read_tensor_file_slice_into, '_studio_bounded_reader', False) is True:
        return
    original = module.read_tensor_file_slice_into
    torch = module.torch

    @functools.wraps(original)
    def read(tensor, destination, stream=None, destination2=None):
        # Preserve upstream's quantization metadata handling. Its recursive call
        # comes back here with the underlying, ordinary byte tensor.
        if isinstance(tensor, module.QuantizedTensor):
            return original(tensor, destination, stream=stream, destination2=destination2)
        info = getattr(tensor.untyped_storage(), '_comfy_tensor_file_slice', None)
        if info is None:
            return original(tensor, destination, stream=stream, destination2=destination2)
        if destination is not None and destination.device.type != 'cpu' and destination2 is None:
            destination2, destination = destination, None
        if (info.file_ref is None or (destination is None and destination2 is None)
                or (destination is not None and (destination.device.type != 'cpu'
                    or not destination.is_contiguous() or destination.numel() * destination.element_size() < info.size))
                or (destination2 is not None and (destination2.device.type != 'cuda'
                    or not destination2.is_contiguous() or destination2.numel() * destination2.element_size() < info.size))
                or tensor.numel() * tensor.element_size() != info.size
                or tensor.storage_offset() != 0 or not tensor.is_contiguous()):
            return False
        if not info.size:
            return True
        # One pageable MiB for the whole transfer, irrespective of tensor/model
        # size. Do not issue disk reads directly into CUDA-registered host memory.
        with _transfer_lock, info.lock, opener(info.file_ref) as file:
            staging = torch.empty(min(CHUNK_BYTES, info.size), dtype=torch.uint8, device='cpu', pin_memory=False)
            view = memoryview((ctypes.c_ubyte * staging.numel()).from_address(staging.data_ptr())).cast('B')
            try:
                file.seek(info.offset)
                gpu = destination2.view(torch.uint8).reshape(-1) if destination2 is not None else None
                with (torch.cuda.stream(stream) if gpu is not None else contextlib.nullcontext()):
                    for offset in range(0, info.size, CHUNK_BYTES):
                        count = min(CHUNK_BYTES, info.size - offset)
                        read_exact(file, view[:count])
                        if destination is not None:
                            ctypes.memmove(destination.data_ptr() + offset, staging.data_ptr(), count)
                        if gpu is not None:
                            gpu[offset:offset + count].copy_(staging[:count], non_blocking=False)
                    # Complete on the supplied offload stream before the pageable
                    # staging tensor is released or another reader reuses memory.
                    if gpu is not None:
                        (stream if stream is not None else torch.cuda.current_stream(destination2.device)).synchronize()
            except OSError as error:
                raise RuntimeError('Windows could not read the model tensor at byte '
                                   f'{info.offset}: {error}. Check the model drive and available system memory.') from error
            finally:
                view.release()
        return True

    read._studio_bounded_reader = True
    module.read_tensor_file_slice_into = read
    print('[Studio model reader] Bounded synchronous Windows tensor reads enabled (1 MiB staging).', flush=True)


def install(profile):
    """Attach after Comfy's normal DLL initialization, in either attention mode."""
    if os.name != 'nt' or profile not in ('ref2va', 'minimax_h3', 'moss', 'wamu'):
        return False
    name = 'comfy.memory_management'
    if name in sys.modules:
        patch_reader(sys.modules[name])
        return True

    class Finder(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path=None, target=None):
            if fullname != name:
                return None
            spec = importlib.machinery.PathFinder.find_spec(fullname, path)
            if spec is None or spec.loader is None:
                raise ImportError('The Studio model reader could not find Comfy memory management.')
            loader = spec.loader
            class Loader(importlib.abc.Loader):
                def create_module(self, spec):
                    return loader.create_module(spec)
                def exec_module(self, module):
                    loader.exec_module(module)
                    patch_reader(module)
                    sys.meta_path.remove(finder)
            spec.loader = Loader()
            return spec
    finder = Finder()
    sys.meta_path.insert(0, finder)
    return True
