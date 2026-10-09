"""
窗口识别：截图时鼠标悬停高亮所在窗口，单击即选中整个窗口（Snipaste 式）。

做法：遮罩显示前用 EnumWindows 按 Z 序（最前在先）拍一份顶层窗口的物理像素矩形，
悬停时取「最上层且包含光标」的那个窗口；没有命中（桌面）时返回整块屏。

坐标换算复用 capture._physical_rect：Qt PassThrough 缩放下屏幕原点沿用物理坐标、
只缩放尺寸，局部逻辑坐标 = (物理坐标 - 屏幕物理原点) / DPR。
"""

import ctypes
import ctypes.wintypes as wintypes

from PySide6.QtCore import QRect, QPoint

from .capture import _monitor_rects, _physical_rect

GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
DWMWA_EXTENDED_FRAME_BOUNDS = 9
DWMWA_CLOAKED = 14
# 桌面壁纸层：命中时视为「没有窗口」，回退到整屏
_DESKTOP_CLASSES = {"Progman", "WorkerW"}
# 主屏 / 副屏任务栏
_TASKBAR_CLASSES = {"Shell_TrayWnd", "Shell_SecondaryTrayWnd"}

_user32 = ctypes.windll.user32
_dwmapi = ctypes.windll.dwmapi

_user32.IsWindowVisible.argtypes = [wintypes.HWND]
_user32.IsIconic.argtypes = [wintypes.HWND]
_user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
_user32.GetWindowLongW.restype = wintypes.LONG
_user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
_user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
_dwmapi.DwmGetWindowAttribute.argtypes = [
    wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
]
# 用 c_long 而非 ctypes.HRESULT：后者失败时直接抛 OSError，无法走返回值回退
_dwmapi.DwmGetWindowAttribute.restype = ctypes.c_long

_WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def _class_name(hwnd) -> str:
    buf = ctypes.create_unicode_buffer(64)
    _user32.GetClassNameW(hwnd, buf, 64)
    return buf.value


def _is_candidate(hwnd) -> bool:
    if not _user32.IsWindowVisible(hwnd) or _user32.IsIconic(hwnd):
        return False
    cloaked = wintypes.DWORD(0)
    # 其它虚拟桌面上的窗口、已挂起的 UWP 窗口：可见标志为真但实际不显示
    if _dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(cloaked),
                                     ctypes.sizeof(cloaked)) == 0 and cloaked.value:
        return False
    ex = _user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    if ex & WS_EX_TRANSPARENT:
        return False
    # 工具窗多为浮层、提示框，不参与识别；任务栏例外（它也是工具窗）
    return not (ex & WS_EX_TOOLWINDOW) or _class_name(hwnd) in _TASKBAR_CLASSES


def _frame_rect(hwnd):
    """窗口物理像素矩形 (x, y, w, h)。优先 DWM 可见边框（不含阴影）。"""
    r = wintypes.RECT()
    ok = _dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_EXTENDED_FRAME_BOUNDS,
                                       ctypes.byref(r), ctypes.sizeof(r)) == 0
    if not ok:
        ok = bool(_user32.GetWindowRect(hwnd, ctypes.byref(r)))
    w, h = r.right - r.left, r.bottom - r.top
    return (r.left, r.top, w, h) if ok and w > 0 and h > 0 else None


def enumerate_windows(exclude_hwnds=()) -> list:
    """按 Z 序返回 [(x, y, w, h, is_desktop)]（物理像素，最前在先）。"""
    hwnds = []

    def cb(hwnd, _lp):
        hwnds.append(hwnd)
        return True

    # 回调里只收集句柄，属性查询放到回调外，减少回调次数内的 Python 开销
    _user32.EnumWindows(_WNDENUMPROC(cb), 0)

    exclude = {int(h) for h in exclude_hwnds}
    result = []
    for hwnd in hwnds:
        try:
            if int(hwnd) in exclude or not _is_candidate(hwnd):
                continue
            rect = _frame_rect(hwnd)
            if rect:
                result.append(rect + (_class_name(hwnd) in _DESKTOP_CLASSES,))
        except Exception:
            continue
    return result


class WindowDetector:
    """单块屏的窗口识别器：构造时把物理矩形换成本屏逻辑局部坐标。"""

    def __init__(self, screen, windows):
        g = screen.geometry()
        self._screen_rect = QRect(0, 0, g.width(), g.height())
        self._rects: list = []  # [(QRect, is_desktop)]，保持 Z 序

        try:
            phys = _physical_rect(screen, _monitor_rects())
        except Exception:
            phys = None
        dpr = screen.devicePixelRatio() or 1.0
        if phys is None:
            phys = (g.x(), g.y(), round(g.width() * dpr), round(g.height() * dpr))
        sx, sy, sw, sh = phys

        for x, y, w, h, is_desktop in windows:
            # 先在物理坐标里裁到本屏，再换算，避免跨屏窗口换算出错的偏移
            x1, y1 = max(x, sx), max(y, sy)
            x2, y2 = min(x + w, sx + sw), min(y + h, sy + sh)
            if x2 - x1 < 10 or y2 - y1 < 10:
                continue
            lx1, ly1 = round((x1 - sx) / dpr), round((y1 - sy) / dpr)
            lx2, ly2 = round((x2 - sx) / dpr), round((y2 - sy) / dpr)
            self._rects.append((QRect(lx1, ly1, lx2 - lx1, ly2 - ly1), is_desktop))

    def detect(self, pos: QPoint) -> QRect:
        """光标处最上层窗口的矩形；落在桌面或无窗口时返回整块屏。"""
        for rect, is_desktop in self._rects:
            if rect.contains(pos):
                return QRect(self._screen_rect) if is_desktop else QRect(rect)
        return QRect(self._screen_rect)
