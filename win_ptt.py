"""Hold the C key for push-to-talk while the League match is in the foreground."""

import ctypes
from ctypes import wintypes
from contextlib import contextmanager
import ntpath
import os


class _KeyboardInput(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class _MouseInput(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class _InputData(ctypes.Union):
    # Win32 sizes INPUT for its largest member, MOUSEINPUT.
    _fields_ = [("ki", _KeyboardInput), ("mi", _MouseInput)]


class _Input(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("data", _InputData)]


def _bind(dll, name, result, *args):
    function = getattr(dll, name)
    function.restype = result
    function.argtypes = args
    return function


@contextmanager
def live_session():
    """Only one live listener may own C in this Windows session."""
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    create = _bind(kernel, "CreateMutexW", wintypes.HANDLE,
                   ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR)
    close = _bind(kernel, "CloseHandle", wintypes.BOOL, wintypes.HANDLE)
    ctypes.set_last_error(0)
    handle = create(None, False, r"Local\Auto-C.LeaguePTT")
    error = ctypes.get_last_error()
    if not handle:
        raise ctypes.WinError(error)
    try:
        if error == 183:  # ERROR_ALREADY_EXISTS
            raise RuntimeError("Auto-C is already running. Use the existing live window.")
        yield
    finally:
        close(handle)


class LeagueKey:
    _C = ord("C")
    # Shift, Control, Alt, left Windows, right Windows.
    _MODIFIERS = (0x10, 0x11, 0x12, 0x5B, 0x5C)

    def __init__(self):
        if os.name != "nt":
            raise OSError("League push-to-talk requires Windows.")
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._foreground = _bind(user32, "GetForegroundWindow", wintypes.HWND)
        self._get_pid = _bind(user32, "GetWindowThreadProcessId", wintypes.DWORD,
                              wintypes.HWND, wintypes.LPDWORD)
        self._open = _bind(kernel32, "OpenProcess", wintypes.HANDLE, wintypes.DWORD,
                           wintypes.BOOL, wintypes.DWORD)
        self._image_name = _bind(kernel32, "QueryFullProcessImageNameW", wintypes.BOOL,
                                 wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, wintypes.LPDWORD)
        self._close = _bind(kernel32, "CloseHandle", wintypes.BOOL, wintypes.HANDLE)
        self._key_state = _bind(user32, "GetAsyncKeyState", wintypes.SHORT, ctypes.c_int)
        self._layout = _bind(user32, "GetKeyboardLayout", wintypes.HKL, wintypes.DWORD)
        self._map_key = _bind(user32, "MapVirtualKeyExW", wintypes.UINT, wintypes.UINT,
                              wintypes.UINT, wintypes.HKL)
        self._send = _bind(user32, "SendInput", wintypes.UINT, wintypes.UINT,
                           ctypes.POINTER(_Input), ctypes.c_int)
        self._held_scan = 0

    @property
    def held(self) -> bool:
        return self._held_scan != 0

    def _target(self):
        if not self.held and any(self._key_state(vk) & 0x8000 for vk in (*self._MODIFIERS, self._C)):
            return None
        window = self._foreground()
        pid = wintypes.DWORD()
        thread = self._get_pid(window, ctypes.byref(pid)) if window else 0
        if not thread:
            return None
        process = self._open(0x1000, False, pid.value)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not process:
            return None
        try:
            path = ctypes.create_unicode_buffer(32768)
            length = wintypes.DWORD(len(path))
            if not self._image_name(process, 0, path, ctypes.byref(length)):
                return None
            if ntpath.basename(path.value).casefold() == "league of legends.exe" and window == self._foreground():
                return window, thread
            return None
        finally:
            self._close(process)

    def eligible(self) -> bool:
        return self._target() is not None

    def set_down(self, down: bool) -> None:
        if down == self.held:
            return
        scan = self._held_scan
        if down:
            target = self._target()
            if target is None:
                return
            window, thread = target
            layout = self._layout(thread)
            scan = self._map_key(self._C, 4, layout) if layout else 0  # MAPVK_VK_TO_VSC_EX
            if window != self._foreground():
                return
            if not scan:
                raise OSError("Windows could not map C in the League window's keyboard layout.")
        event = _Input()
        event.type = 1  # INPUT_KEYBOARD
        event.data.ki.wScan = scan & 0xFF
        flags = 0x0008  # KEYEVENTF_SCANCODE
        if scan >> 8 == 0xE0:
            flags |= 0x0001  # KEYEVENTF_EXTENDEDKEY
        if not down:
            flags |= 0x0002  # KEYEVENTF_KEYUP
        event.data.ki.dwFlags = flags
        ctypes.set_last_error(0)
        if self._send(1, ctypes.byref(event), ctypes.sizeof(event)) != 1:
            error = ctypes.get_last_error()
            if error:
                raise ctypes.WinError(error)
            raise OSError("Windows did not accept the push-to-talk key event.")
        self._held_scan = scan if down else 0
