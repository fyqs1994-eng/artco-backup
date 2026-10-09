"""
屏幕抓取

不用 QScreen.grabWindow：它在整个 GDI 拷贝期间（4K 屏约 70~90ms）都占着 GIL，
而 Artco 的全局键盘/鼠标钩子回调是 Python 写的，拿不到 GIL 就无法返回，
表现为按下截图热键瞬间整个系统的光标、键盘一起顿住。

这里用 ctypes 直接调 GDI BitBlt：ctypes 调用外部函数期间会释放 GIL，钩子照常响应；
多块屏各开一个线程并行抓取，总耗时也更短。任何一步失败都回退到 grabWindow。
"""

import ctypes
import threading
from ctypes import wintypes

from PySide6.QtGui import QImage, QPixmap

_user32 = ctypes.windll.user32
_gdi32 = ctypes.windll.gdi32

_SRCCOPY = 0x00CC0020
_CAPTUREBLT = 0x40000000  # 同时抓取分层窗口（与 Qt grabWindow 行为一致）


class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD), ("biWidth", ctypes.c_long), ("biHeight", ctypes.c_long),
        ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", ctypes.c_long),
        ("biYPelsPerMeter", ctypes.c_long), ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


_user32.GetDC.restype = wintypes.HDC
_user32.GetDC.argtypes = [wintypes.HWND]
_user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
_gdi32.CreateCompatibleDC.restype = wintypes.HDC
_gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
_gdi32.DeleteDC.argtypes = [wintypes.HDC]
_gdi32.CreateDIBSection.restype = wintypes.HBITMAP
_gdi32.CreateDIBSection.argtypes = [
    wintypes.HDC, ctypes.c_void_p, wintypes.UINT,
    ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD,
]
_gdi32.SelectObject.restype = wintypes.HGDIOBJ
_gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
_gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
_gdi32.BitBlt.argtypes = [
    wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.DWORD,
]
_gdi32.BitBlt.restype = wintypes.BOOL

_MONITORENUMPROC = ctypes.WINFUNCTYPE(
    wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.LPARAM
)


def _monitor_rects():
    """所有显示器的物理像素矩形 (x, y, w, h)。进程已是每屏 DPI 感知，返回值不被虚拟化。"""
    rects = []

    def cb(_hmon, _hdc, prc, _lp):
        r = prc.contents
        rects.append((r.left, r.top, r.right - r.left, r.bottom - r.top))
        return True

    _user32.EnumDisplayMonitors(None, None, _MONITORENUMPROC(cb), 0)
    return rects


def _physical_rect(screen, monitors):
    """把 QScreen 对应到物理矩形。

    Qt 在 PassThrough 缩放下保留屏幕原点的物理坐标、只把尺寸换算成逻辑值，
    所以用「原点相同 + 尺寸 ≈ 逻辑尺寸 × DPR」来匹配。匹配不到返回 None。
    """
    g = screen.geometry()
    dpr = screen.devicePixelRatio()
    w, h = g.width() * dpr, g.height() * dpr
    for x, y, mw, mh in monitors:
        if x == g.x() and y == g.y() and abs(mw - w) <= 2 and abs(mh - h) <= 2:
            return x, y, mw, mh
    return None


def _bitblt(x, y, w, h):
    """抓取物理矩形，返回 QImage；失败返回 None。可在工作线程调用。"""
    sdc = _user32.GetDC(None)
    if not sdc:
        return None
    mdc = _gdi32.CreateCompatibleDC(sdc)
    hbm = None
    old = None
    try:
        bmi = _BITMAPINFOHEADER(ctypes.sizeof(_BITMAPINFOHEADER), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
        bits = ctypes.c_void_p()
        hbm = _gdi32.CreateDIBSection(mdc, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0)
        if not hbm or not bits.value:
            return None
        old = _gdi32.SelectObject(mdc, hbm)
        if not _gdi32.BitBlt(mdc, 0, 0, w, h, sdc, x, y, _SRCCOPY | _CAPTUREBLT):
            return None
        # 直接包住 DIB 内存再 copy 一次，不经 string_at 中转（少一次整屏拷贝，且那次拷贝占着 GIL）
        buf = (ctypes.c_char * (w * h * 4)).from_address(bits.value)
        return QImage(buf, w, h, w * 4, QImage.Format.Format_RGB32).copy()
    finally:
        if old:
            _gdi32.SelectObject(mdc, old)
        if hbm:
            _gdi32.DeleteObject(hbm)
        _gdi32.DeleteDC(mdc)
        _user32.ReleaseDC(None, sdc)


def physical_to_local(screens, x, y):
    """物理像素坐标 → (所在屏下标, 该屏逻辑局部坐标 (lx, ly))；不在任何屏上返回 (None, None)。"""
    try:
        monitors = _monitor_rects()
    except Exception:
        return None, None
    for i, s in enumerate(screens):
        r = _physical_rect(s, monitors)
        if r and r[0] <= x < r[0] + r[2] and r[1] <= y < r[1] + r[3]:
            dpr = s.devicePixelRatio() or 1.0
            return i, (round((x - r[0]) / dpr), round((y - r[1]) / dpr))
    return None, None


def physical_to_screen_local(screen, x, y):
    """物理像素坐标换算到指定屏的逻辑局部坐标（可在屏外，由调用方裁剪）。失败返回 None。"""
    try:
        r = _physical_rect(screen, _monitor_rects())
    except Exception:
        r = None
    if r is None:
        return None
    dpr = screen.devicePixelRatio() or 1.0
    return round((x - r[0]) / dpr), round((y - r[1]) / dpr)


def grab_screens(screens):
    """并行抓取多块屏，返回与 screens 等长的 QPixmap 列表（物理像素尺寸）。"""
    try:
        monitors = _monitor_rects()
    except Exception:
        monitors = []

    images = [None] * len(screens)

    def work(i, rect):
        try:
            images[i] = _bitblt(*rect)
        except Exception:
            images[i] = None

    threads = []
    for i, s in enumerate(screens):
        rect = _physical_rect(s, monitors)
        if rect is not None:
            t = threading.Thread(target=work, args=(i, rect), daemon=True)
            t.start()
            threads.append(t)
    for t in threads:
        t.join()

    result = []
    for s, img in zip(screens, images):
        if img is not None and not img.isNull():
            result.append(QPixmap.fromImage(img))
        else:
            result.append(s.grabWindow(0))
    return result
