"""
截图模块

包含：
- 标记对象系统 (marks)
- 编辑器画布 (canvas)
- 工具栏组件 (toolbar)
- 编辑器窗口 (editor)
- 截图遮罩层 (overlay)
- 屏幕贴图窗口 (pin)
- 工具函数 (utils)
"""

from .utils import parse_hotkey, load_screenshot_hotkeys
from .cache import get_cached_hotkeys, invalidate_hotkey_cache
from .marks import MarkObject, NumberDot, RectMark, ArrowMark, FreehandMark, TextMark
from .canvas import EditorCanvas
from .toolbar import EditorToolbar, ScreenshotToolbar, ScreenshotAICapsule
from .editor import EditorWindow
from .overlay import ScreenshotOverlay, ScreenSelector, ScreenSelectorWindow
from .pin import PinWindow

__all__ = [
    # Utils
    'parse_hotkey',
    'load_screenshot_hotkeys',
    # Cache
    'get_cached_hotkeys',
    'invalidate_hotkey_cache',
    # Marks
    'MarkObject',
    'NumberDot',
    'RectMark',
    'ArrowMark',
    'FreehandMark',
    'TextMark',
    # Canvas
    'EditorCanvas',
    # Toolbar
    'EditorToolbar',
    'ScreenshotToolbar',
    'ScreenshotAICapsule',
    # Editor
    'EditorWindow',
    # Overlay
    'ScreenshotOverlay',
    'ScreenSelector',
    'ScreenSelectorWindow',
    # Pin
    'PinWindow',
]
