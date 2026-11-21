"""Place the Auto-C window on a secondary Windows display when available."""

import ctypes
from ctypes import wintypes


class _MonitorInfo(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("monitor", wintypes.RECT),
                ("work", wintypes.RECT), ("flags", wintypes.DWORD)]


def _work_areas(user32):
    areas = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HANDLE, wintypes.HDC,
                                       ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)

    @callback_type
    def collect(monitor, dc, rect, data):
        info = _MonitorInfo()
        info.size = ctypes.sizeof(info)
        if user32.GetMonitorInfoW(wintypes.HANDLE(monitor), ctypes.byref(info)):
            r = info.work
            if r.right > r.left and r.bottom > r.top:
                areas.append((bool(info.flags & 1), (r.left, r.top, r.right, r.bottom)))
        return True

    user32.EnumDisplayMonitors(None, None, collect, 0)
    return areas


def place_window(root):
    root.update_idletasks()
    hwnd = wintypes.HWND(int(root.wm_frame(), 0))
    user32 = ctypes.WinDLL("user32")
    # Query and move in physical pixels, including on mixed-DPI desktops.
    set_dpi_context = user32.SetThreadDpiAwarenessContext
    set_dpi_context.argtypes = [wintypes.HANDLE]
    set_dpi_context.restype = wintypes.HANDLE
    previous = set_dpi_context(-4)  # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
    try:
        areas = _work_areas(user32)
        if not areas:
            return
        _, (left, top, right, bottom) = min(areas, key=lambda area: area[0])
        # Moving across displays can change the outer window size with DPI scaling.
        for _ in range(2):
            rect = wintypes.RECT()
            if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                return
            width, height = rect.right - rect.left, rect.bottom - rect.top
            x = max(left, right - width - 20)
            y = max(top, min(top + 20, bottom - height))
            if (rect.left, rect.top) == (x, y):
                return
            # Keep size, z-order and activation while moving the decorated window.
            if not user32.SetWindowPos(hwnd, None, x, y, 0, 0, 0x0001 | 0x0004 | 0x0010):
                return
    finally:
        if previous:
            set_dpi_context(previous)
