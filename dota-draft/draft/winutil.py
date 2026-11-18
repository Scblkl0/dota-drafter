from __future__ import annotations

import ctypes
import os
from ctypes import wintypes

import numpy as np

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

H = ctypes.c_void_p
user32.FindWindowW.restype = H
user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.GetForegroundWindow.restype = H
user32.IsWindowVisible.argtypes = [H]
user32.IsIconic.argtypes = [H]
user32.GetClientRect.argtypes = [H, ctypes.POINTER(wintypes.RECT)]
user32.GetWindowRect.argtypes = [H, ctypes.POINTER(wintypes.RECT)]
user32.ClientToScreen.argtypes = [H, ctypes.POINTER(wintypes.POINT)]
user32.GetWindowThreadProcessId.argtypes = [H, ctypes.POINTER(wintypes.DWORD)]
user32.GetDC.restype = H
user32.GetDC.argtypes = [H]
user32.ReleaseDC.argtypes = [H, H]
gdi32.CreateCompatibleDC.restype = H
gdi32.CreateCompatibleDC.argtypes = [H]
gdi32.CreateCompatibleBitmap.restype = H
gdi32.CreateCompatibleBitmap.argtypes = [H, ctypes.c_int, ctypes.c_int]
gdi32.SelectObject.restype = H
gdi32.SelectObject.argtypes = [H, H]
gdi32.BitBlt.argtypes = [H, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                         H, ctypes.c_int, ctypes.c_int, wintypes.DWORD]
gdi32.DeleteObject.argtypes = [H]
gdi32.DeleteDC.argtypes = [H]

SRCCOPY = 0x00CC0020
CAPTUREBLT = 0x40000000


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", ctypes.c_long), ("biHeight", ctypes.c_long),
                ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD),
                ("biCompression", wintypes.DWORD), ("biSizeImage", wintypes.DWORD),
                ("biXPelsPerMeter", ctypes.c_long), ("biYPelsPerMeter", ctypes.c_long),
                ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]


gdi32.GetDIBits.argtypes = [H, H, wintypes.UINT, wintypes.UINT, ctypes.c_void_p,
                            ctypes.POINTER(BITMAPINFOHEADER), wintypes.UINT]


def find_dota() -> int | None:
    return user32.FindWindowW("SDL_app", "Dota 2") or user32.FindWindowW(None, "Dota 2") or None


def client_rect(hwnd) -> tuple[int, int, int, int] | None:
    if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
        return None
    r = wintypes.RECT()
    p = wintypes.POINT(0, 0)
    if not user32.GetClientRect(hwnd, ctypes.byref(r)) or not user32.ClientToScreen(hwnd, ctypes.byref(p)):
        return None
    w, h = r.right - r.left, r.bottom - r.top
    return (p.x, p.y, w, h) if w > 200 and h > 200 else None


user32.GetWindowLongW.argtypes = [H, ctypes.c_int]
user32.GetWindow.restype = H
user32.GetWindow.argtypes = [H, ctypes.c_uint]
GW_HWNDPREV = 3


def is_above(hwnd_a, hwnd_b) -> bool:
    if not hwnd_a or not hwnd_b:
        return False
    a, h, n = int(hwnd_a), user32.GetWindow(hwnd_b, GW_HWNDPREV), 0
    while h and n < 10000:
        if int(h) == a:
            return True
        h = user32.GetWindow(h, GW_HWNDPREV)
        n += 1
    return False


def describe(hwnd) -> str:
    style = user32.GetWindowLongW(hwnd, -16) & 0xFFFFFFFF
    fg = user32.GetForegroundWindow()
    return (f"visible {bool(user32.IsWindowVisible(hwnd))}, minimized {bool(user32.IsIconic(hwnd))}, "
            f"title bar {bool(style & 0x00C00000)}, popup {bool(style & 0x80000000)}, "
            f"foreground {fg == hwnd}, window rect {window_rect(hwnd)}, client rect {client_rect(hwnd)}")


def window_rect(hwnd) -> tuple[int, int, int, int] | None:
    r = wintypes.RECT()
    if not hwnd or not user32.GetWindowRect(int(hwnd), ctypes.byref(r)):
        return None
    return r.left, r.top, r.right - r.left, r.bottom - r.top


def is_active(hwnd) -> bool:
    fg = user32.GetForegroundWindow()
    if not fg:
        return False
    if fg == hwnd:
        return True
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(fg, ctypes.byref(pid))
    return pid.value == os.getpid()


def intersects(a, b) -> bool:
    return bool(a and b and a[0] < b[0] + b[2] and b[0] < a[0] + a[2]
                and a[1] < b[1] + b[3] and b[1] < a[1] + a[3])


def capture(x: int, y: int, w: int, h: int) -> np.ndarray | None:
    sdc = user32.GetDC(None)
    mdc = gdi32.CreateCompatibleDC(sdc)
    bmp = gdi32.CreateCompatibleBitmap(sdc, w, h)
    old = gdi32.SelectObject(mdc, bmp)
    try:
        if not gdi32.BitBlt(mdc, 0, 0, w, h, sdc, x, y, SRCCOPY | CAPTUREBLT):
            return None
        bi = BITMAPINFOHEADER()
        bi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bi.biWidth, bi.biHeight = w, -h
        bi.biPlanes, bi.biBitCount, bi.biCompression = 1, 32, 0
        buf = np.empty((h, w, 4), np.uint8)
        gdi32.SelectObject(mdc, old)
        if gdi32.GetDIBits(mdc, bmp, 0, h, buf.ctypes.data, ctypes.byref(bi), 0) != h:
            return None
        return np.ascontiguousarray(buf[:, :, :3])
    finally:
        gdi32.SelectObject(mdc, old)
        gdi32.DeleteObject(bmp)
        gdi32.DeleteDC(mdc)
        user32.ReleaseDC(None, sdc)
