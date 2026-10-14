"""Lightweight system RAM and NVIDIA resource sampling, outside UI requests."""
import ctypes
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
    load, used, total = [float(x.strip()) for x in result.stdout.splitlines()[0].split(',')]
    return dict(percent=load, used=int(used*1024**2), total=int(total*1024**2))


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
            while not self.stop.is_set():
                try:
                    self.gpu = sample_gpu()
                    self.updated = time.time()
                except (OSError, ValueError, IndexError, subprocess.TimeoutExpired):
                    self.gpu = None
                self.stop.wait(3)
        self.thread = threading.Thread(target=work, daemon=True)
        self.thread.start()

    def snapshot(self):
        return dict(gpu=self.gpu, ram=ram_usage(), updated=self.updated)
