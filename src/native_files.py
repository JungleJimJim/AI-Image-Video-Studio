"""User-initiated native file selection without starting another Studio process."""
import ctypes
from ctypes import wintypes
import os


def pick_video():
    if os.name!='nt':raise ValueError('Local file selection requires the Windows desktop app.')
    hook_type=ctypes.WINFUNCTYPE(ctypes.c_size_t,wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM)
    class OpenFileName(ctypes.Structure):
        _fields_=[('size',wintypes.DWORD),('owner',wintypes.HWND),('instance',wintypes.HINSTANCE),
            ('filter',wintypes.LPCWSTR),('custom_filter',wintypes.LPWSTR),('custom_size',wintypes.DWORD),
            ('filter_index',wintypes.DWORD),('file',wintypes.LPWSTR),('file_size',wintypes.DWORD),
            ('title_buffer',wintypes.LPWSTR),('title_size',wintypes.DWORD),('initial',wintypes.LPCWSTR),
            ('title',wintypes.LPCWSTR),('flags',wintypes.DWORD),('file_offset',wintypes.WORD),
            ('extension_offset',wintypes.WORD),('default_extension',wintypes.LPCWSTR),
            ('data',wintypes.LPARAM),('hook',hook_type),('template',wintypes.LPCWSTR),
            ('reserved',ctypes.c_void_p),('reserved_dword',wintypes.DWORD),('flags_ex',wintypes.DWORD)]
    user=ctypes.windll.user32
    user.GetParent.argtypes=[wintypes.HWND];user.GetParent.restype=wintypes.HWND
    user.ShowWindow.argtypes=[wintypes.HWND,ctypes.c_int]
    user.SetForegroundWindow.argtypes=[wintypes.HWND]
    @hook_type
    def hook(hwnd,message,_wparam,_lparam):
        if message==0x110:
            parent=user.GetParent(hwnd);user.ShowWindow(parent,5);user.SetForegroundWindow(parent)
        return 0
    buffer=ctypes.create_unicode_buffer(32768)
    options=OpenFileName();options.size=ctypes.sizeof(options)
    options.filter='Video files\0*.mp4;*.mov;*.webm;*.mkv;*.avi\0\0';options.filter_index=1
    options.file=ctypes.cast(buffer,wintypes.LPWSTR);options.file_size=len(buffer)
    options.title='Choose a target video to copy into Studio Library'
    options.flags=0x1000|0x800|0x80000|0x2000000|0x8|0x20;options.hook=hook
    dialog=ctypes.windll.comdlg32
    dialog.GetOpenFileNameW.argtypes=[ctypes.POINTER(OpenFileName)];dialog.GetOpenFileNameW.restype=wintypes.BOOL
    if dialog.GetOpenFileNameW(ctypes.byref(options)):return buffer.value
    error=dialog.CommDlgExtendedError()
    if error:raise OSError('The Windows file picker failed: '+str(error))
    return ''
