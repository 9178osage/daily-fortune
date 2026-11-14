"""Windows file and console operations for the command-line runtime."""

from contextlib import contextmanager
import ctypes
from ctypes import wintypes
import msvcrt
import os
import stat


_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_create_file = _kernel32.CreateFileW
_create_file.argtypes = (
    wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
    wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
)
_create_file.restype = wintypes.HANDLE
_close_handle = _kernel32.CloseHandle
_close_handle.argtypes = (wintypes.HANDLE,)
_close_handle.restype = wintypes.BOOL
_get_console_mode = _kernel32.GetConsoleMode
_get_console_mode.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
_get_console_mode.restype = wintypes.BOOL
_set_console_mode = _kernel32.SetConsoleMode
_set_console_mode.argtypes = (wintypes.HANDLE, wintypes.DWORD)
_set_console_mode.restype = wintypes.BOOL

_INVALID_HANDLE = wintypes.HANDLE(-1).value
_GENERIC_READ = 0x80000000
_GENERIC_WRITE = 0x40000000
_FILE_SHARE_READ = 0x1
_FILE_SHARE_WRITE = 0x2
_FILE_SHARE_DELETE = 0x4
_OPEN_EXISTING = 3
_OPEN_ALWAYS = 4
_FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
_ENABLE_PROCESSED_OUTPUT = 0x1
_ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x4


def open_state_file(path, *, writable=False):
    access = _GENERIC_READ | (_GENERIC_WRITE if writable else 0)
    sharing = _FILE_SHARE_READ | _FILE_SHARE_WRITE
    if not writable:
        sharing |= _FILE_SHARE_DELETE
    disposition = _OPEN_ALWAYS if writable else _OPEN_EXISTING
    handle = _create_file(str(path), access, sharing, None,
                          disposition, _FILE_FLAG_OPEN_REPARSE_POINT, None)
    if handle == _INVALID_HANDLE:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        flags = os.O_BINARY | os.O_NOINHERIT | (os.O_RDWR if writable else os.O_RDONLY)
        fd = msvcrt.open_osfhandle(handle, flags)
    except BaseException:
        _close_handle(handle)
        raise
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or
                info.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT):
            raise OSError("状态文件必须是普通文件，且不能是重解析点。")
    except BaseException:
        os.close(fd)
        raise
    return fd


@contextmanager
def virtual_terminal(stream):
    """Enable ANSI output for this draw when the console supports it."""
    try:
        handle = msvcrt.get_osfhandle(stream.fileno())
    except OSError:
        yield False
        return
    mode = wintypes.DWORD()
    if not _get_console_mode(handle, ctypes.byref(mode)):
        yield False
        return
    original = mode.value
    enabled = original | _ENABLE_PROCESSED_OUTPUT | _ENABLE_VIRTUAL_TERMINAL_PROCESSING
    if enabled == original:
        yield True
    elif not _set_console_mode(handle, enabled):
        yield False
    else:
        try:
            yield True
        finally:
            _set_console_mode(handle, original)
