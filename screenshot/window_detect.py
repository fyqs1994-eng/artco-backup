"""
窗口检测模块 - 在截图前预枚举所有可见窗口，支持多显示器 + HiDPI

坐标系说明（PySide6 Per-Monitor DPI Aware 模式下）：
  - QScreen.geometry() 返回的 x/y 是全局物理像素坐标，width/height 是逻辑像素
  - Win32 GetWindowRect / DwmGetWindowAttribute 返回全局物理像素坐标
  - overlay 使用 QScreen.geometry() 定位，坐标系为逻辑像素
  - 因此需要将 Win32 物理坐标 → overlay 逻辑坐标
"""

import ctypes
import ctypes.wintypes as wintypes
from PySide6.QtCore import QRect, QPoint

# Win32 常量
GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
DWMWA_EXTENDED_FRAME_BOUNDS = 9
DWMWA_CLOAKED = 14


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


# Win32 API
user32 = ctypes.windll.user32
dwmapi = ctypes.windll.dwmapi

user32.EnumWindows.restype = wintypes.BOOL
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT)]
user32.GetWindowRect.restype = wintypes.BOOL
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsWindowVisible.restype = wintypes.BOOL
user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetWindowLongW.restype = wintypes.LONG
user32.IsIconic.argtypes = [wintypes.HWND]
user32.IsIconic.restype = wintypes.BOOL

dwmapi.DwmGetWindowAttribute.argtypes = [
    wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
]
dwmapi.DwmGetWindowAttribute.restype = ctypes.HRESULT

# EnumWindows 回调类型
WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def _get_window_rect(hwnd: int) -> tuple[int, int, int, int] | None:
    """获取窗口物理像素矩形 (x, y, w, h)，优先 DWM 去阴影"""
    rect = RECT()
    try:
        hr = dwmapi.DwmGetWindowAttribute(
            hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(rect), ctypes.sizeof(rect)
        )
        if hr == 0:
            w = rect.right - rect.left
            h = rect.bottom - rect.top
            if w > 0 and h > 0:
                return (rect.left, rect.top, w, h)
    except (OSError, ctypes.ArgumentError):
        pass

    # 回退到 GetWindowRect
    try:
        if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            w = rect.right - rect.left
            h = rect.bottom - rect.top
            if w > 0 and h > 0:
                return (rect.left, rect.top, w, h)
    except (OSError, ctypes.ArgumentError):
        pass
    return None


def _is_cloaked(hwnd: int) -> bool:
    """检查窗口是否被 DWM 隐藏（虚拟桌面上不可见的窗口）"""
    cloaked = wintypes.DWORD(0)
    try:
        hr = dwmapi.DwmGetWindowAttribute(
            hwnd, DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked)
        )
        return hr == 0 and cloaked.value != 0
    except (OSError, ctypes.ArgumentError):
        return False


def _is_valid_toplevel(hwnd: int) -> bool:
    """判断是否为有效的顶级窗口"""
    try:
        if not user32.IsWindowVisible(hwnd):
            return False
        if user32.IsIconic(hwnd):
            return False
    except (OSError, ctypes.ArgumentError):
        return False

    if _is_cloaked(hwnd):
        return False

    try:
        ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        if ex_style & WS_EX_TOOLWINDOW:
            return False
    except (OSError, ctypes.ArgumentError):
        pass

    return True


def _phys_to_local(px: int, py: int, pw: int, ph: int,
                   screen_phys_x: int, screen_phys_y: int,
                   screen_phys_w: int, screen_phys_h: int,
                   screen_log_w: int, screen_log_h: int) -> QRect | None:
    """
    将物理像素全局矩形转换为 overlay 本地逻辑坐标矩形。
    
    screen_phys_x/y: 屏幕在全局物理坐标中的原点 (= geometry().x() * dpr 有误，
                     实际 geometry().x() 在 PerMonitor 模式下就是物理像素)
    """
    # 计算窗口在屏幕物理坐标中的交集
    ix1 = max(px, screen_phys_x)
    iy1 = max(py, screen_phys_y)
    ix2 = min(px + pw, screen_phys_x + screen_phys_w)
    iy2 = min(py + ph, screen_phys_y + screen_phys_h)

    iw = ix2 - ix1
    ih = iy2 - iy1
    if iw < 5 or ih < 5:
        return None

    # 物理坐标相对于屏幕原点 → 逻辑坐标
    scale_x = screen_log_w / screen_phys_w if screen_phys_w else 1.0
    scale_y = screen_log_h / screen_phys_h if screen_phys_h else 1.0

    local_x = int((ix1 - screen_phys_x) * scale_x)
    local_y = int((iy1 - screen_phys_y) * scale_y)
    local_w = int(iw * scale_x)
    local_h = int(ih * scale_y)

    if local_w < 10 or local_h < 10:
        return None

    return QRect(local_x, local_y, local_w, local_h)


def enumerate_windows(screen_geometry: QRect, dpi_scale_x: float = 1.0, dpi_scale_y: float = 1.0) -> list[QRect]:
    """
    枚举当前屏幕上所有可见窗口，返回相对于屏幕的逻辑坐标矩形列表。
    列表按 Z 序排列（最前面的窗口在前）。

    参数：
        screen_geometry: 屏幕的全局坐标矩形（QScreen.geometry()）
          - x()/y(): 在 PerMonitor DPI Aware 模式下实际为物理像素全局坐标
          - width()/height(): 逻辑像素
        dpi_scale_x: 物理像素/逻辑像素 水平缩放比
        dpi_scale_y: 物理像素/逻辑像素 垂直缩放比
    """
    results: list[QRect] = []

    # 屏幕的全局物理像素范围
    # geometry().x()/y() 在 PySide6 PerMonitor 模式下就是物理全局坐标
    screen_phys_x = screen_geometry.x()
    screen_phys_y = screen_geometry.y()
    # 物理尺寸 = 逻辑尺寸 * DPI
    screen_phys_w = int(screen_geometry.width() * dpi_scale_x)
    screen_phys_h = int(screen_geometry.height() * dpi_scale_y)
    screen_log_w = screen_geometry.width()
    screen_log_h = screen_geometry.height()
    screen_area = screen_log_w * screen_log_h

    def _enum_callback(hwnd, _lparam):
        try:
            if not _is_valid_toplevel(hwnd):
                return True

            phys = _get_window_rect(hwnd)
            if not phys:
                return True

            local_rect = _phys_to_local(
                phys[0], phys[1], phys[2], phys[3],
                screen_phys_x, screen_phys_y, screen_phys_w, screen_phys_h,
                screen_log_w, screen_log_h
            )
            if local_rect:
                results.append(local_rect)
        except Exception:
            pass
        return True

    callback = WNDENUMPROC(_enum_callback)
    user32.EnumWindows(callback, 0)

    return results


class WindowDetector:
    """窗口检测器 - 预枚举 + 悬停匹配"""

    def __init__(self, screen_geometry: QRect, dpi_scale_x: float = 1.0, dpi_scale_y: float = 1.0):
        self._screen_geo = screen_geometry
        self._enabled = True
        self._rects: list[QRect] = []
        self._last_rect: QRect | None = None

        # 预枚举所有窗口（必须在 overlay show() 之前调用）
        try:
            self._rects = enumerate_windows(screen_geometry, dpi_scale_x, dpi_scale_y)
        except Exception:
            self._rects = []

    def set_enabled(self, enabled: bool):
        self._enabled = enabled
        if not enabled:
            self._last_rect = None

    def detect(self, local_pos: QPoint) -> QRect | None:
        """
        根据 overlay 上的局部坐标查找最匹配的窗口矩形。
        优先返回包含该点的最小矩形（更精确的子控件）。
        """
        if not self._enabled or not self._rects:
            return None

        best: QRect | None = None
        best_area = float('inf')
        screen_area = self._screen_geo.width() * self._screen_geo.height()

        for rect in self._rects:
            if rect.contains(local_pos):
                area = rect.width() * rect.height()
                # 跳过占满整个屏幕的矩形（桌面）
                if area >= screen_area * 0.95:
                    continue
                if area < best_area:
                    best_area = area
                    best = rect

        self._last_rect = best
        return best

    def invalidate_cache(self):
        self._last_rect = None
