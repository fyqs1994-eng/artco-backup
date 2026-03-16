"""
截图模块 - 工具函数
"""

from PySide6.QtCore import Qt


def parse_hotkey(hotkey_str: str) -> tuple:
    """解析快捷键字符串，返回 (modifiers, key)"""
    if not hotkey_str:
        return (Qt.KeyboardModifier.NoModifier, None)
    
    parts = hotkey_str.split('+')
    modifiers = Qt.KeyboardModifier.NoModifier
    key = None
    
    key_map = {
        'Enter': Qt.Key.Key_Return, 'Return': Qt.Key.Key_Return,
        'Escape': Qt.Key.Key_Escape, 'Esc': Qt.Key.Key_Escape,
        'Tab': Qt.Key.Key_Tab, 'Space': Qt.Key.Key_Space,
        'Backspace': Qt.Key.Key_Backspace, 'Delete': Qt.Key.Key_Delete,
        'Up': Qt.Key.Key_Up, 'Down': Qt.Key.Key_Down,
        'Left': Qt.Key.Key_Left, 'Right': Qt.Key.Key_Right,
        'Home': Qt.Key.Key_Home, 'End': Qt.Key.Key_End,
        'PageUp': Qt.Key.Key_PageUp, 'PageDown': Qt.Key.Key_PageDown,
    }
    
    for part in parts:
        part = part.strip()
        upper = part.upper()
        if upper == 'CTRL':
            modifiers |= Qt.KeyboardModifier.ControlModifier
        elif upper == 'SHIFT':
            modifiers |= Qt.KeyboardModifier.ShiftModifier
        elif upper == 'ALT':
            modifiers |= Qt.KeyboardModifier.AltModifier
        elif part in key_map:
            key = key_map[part]
        elif len(part) == 1:
            key = getattr(Qt.Key, f'Key_{part.upper()}', None)
        else:
            # F1-F12 等
            key = getattr(Qt.Key, f'Key_{part}', None)
    
    return (modifiers, key)


def load_screenshot_hotkeys() -> dict:
    """加载截图窗口快捷键配置"""
    from utils import hotkey_manager
    return hotkey_manager.get_screenshot_hotkeys()
