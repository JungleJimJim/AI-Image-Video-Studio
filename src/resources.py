"""Lightweight system RAM and NVIDIA resource sampling, outside UI requests."""
import ctypes
import os
from pathlib import Path
import subprocess
import threading
import time

from common import CREATE_NO_WINDOW


def ram_usage():
    class MemoryStatus(ctypes.Structure):
        _fields_ = [('length',ctypes.c_ulong),('load',ctypes.c_ulong)] + [
            (name,ctypes.c_ulonglong) for name in ('total','available','page_total','page_available','virtual_total','virtual_available','extended')]
    try:
        status = MemoryStatus()
        status.length = ctypes.sizeof(status)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return None
        return dict(used=status.total-status.available, total=status.total, percent=status.load,
                    commit_used=status.page_total-status.page_available, commit_limit=status.page_total,
                    commit_available=status.page_available)
    except (AttributeError, OSError):
        return None


def sample_gpu():
    result = subprocess.run(['nvidia-smi','--query-gpu=utilization.gpu,memory.used,memory.total','--format=csv,noheader,nounits'],
                            capture_output=True, text=True, timeout=5, creationflags=CREATE_NO_WINDOW)
    if result.returncode:
        return None
    load, used, total = [x.strip() for x in result.stdout.splitlines()[0].split(',')]
    # WDDM/drivers may report unavailable utilization while memory is still valid.
    try:
        percent = float(load)
        if not 0 <= percent <= 100:
            percent = None
    except ValueError:
        percent = None
    return dict(percent=percent, used=int(float(used)*1024**2), total=int(float(total)*1024**2), source='nvidia-smi')


class NvmlSampler:
    """Read the NVIDIA driver's telemetry without launching a process each second."""
    class Memory(ctypes.Structure):
        _fields_ = [(name, ctypes.c_ulonglong) for name in ('total', 'free', 'used')]

    class Utilization(ctypes.Structure):
        _fields_ = [('gpu', ctypes.c_uint), ('memory', ctypes.c_uint)]

    def __init__(self):
        # Absolute system path; never load a driver DLL from the app/current folder.
        system = Path(os.environ.get('SystemRoot', 'C:/Windows')) / 'System32'
        self.api = ctypes.CDLL(str(system / 'nvml.dll'))
        self.api.nvmlInit_v2.argtypes = []
        self.api.nvmlShutdown.argtypes = []
        self.api.nvmlDeviceGetHandleByIndex_v2.argtypes = [ctypes.c_uint, ctypes.POINTER(ctypes.c_void_p)]
        self.api.nvmlDeviceGetMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.POINTER(self.Memory)]
        self.api.nvmlDeviceGetUtilizationRates.argtypes = [ctypes.c_void_p, ctypes.POINTER(self.Utilization)]
        if self.api.nvmlInit_v2():
            raise OSError('NVIDIA telemetry initialization failed')
        self.handle = ctypes.c_void_p()
        if self.api.nvmlDeviceGetHandleByIndex_v2(0, ctypes.byref(self.handle)):
            self.close()
            raise OSError('NVIDIA device unavailable')

    def sample(self):
        memory, utilization = self.Memory(), self.Utilization()
        if self.api.nvmlDeviceGetMemoryInfo(self.handle, ctypes.byref(memory)):
            raise OSError('NVIDIA memory telemetry unavailable')
        status = self.api.nvmlDeviceGetUtilizationRates(self.handle, ctypes.byref(utilization))
        return dict(percent=int(utilization.gpu) if status == 0 and utilization.gpu <= 100 else None,
                    used=int(memory.used), total=int(memory.total), source='nvml')

    def close(self):
        self.api.nvmlShutdown()


class ResourceMonitor:
    def __init__(self):
        self.gpu = None
        self.updated = 0
        self.stop = threading.Event()
        self.thread = None

    def start(self):
        if self.thread:
            return
        def work():
            sampler = None
            try:
                try:
                    sampler = NvmlSampler()
                except (OSError, AttributeError):
                    pass
                while not self.stop.is_set():
                    try:
                        self.gpu = sampler.sample() if sampler else sample_gpu()
                    except (OSError, ValueError, IndexError, subprocess.TimeoutExpired):
                        self.gpu = None
                        if sampler:
                            sampler.close()
                            sampler = None
                    self.updated = time.time()
                    self.stop.wait(1)
            finally:
                if sampler:
                    sampler.close()
        self.thread = threading.Thread(target=work, daemon=True)
        self.thread.start()

    def snapshot(self):
        return dict(gpu=self.gpu, ram=ram_usage(), updated=self.updated)
