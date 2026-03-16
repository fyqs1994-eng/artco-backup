"""
截图模块缓存管理 - 统一管理快捷键等配置的缓存
"""

from .utils import parse_hotkey, load_screenshot_hotkeys


class HotkeyCache:
    """快捷键缓存单例"""
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._hotkeys = None
            cls._instance._hotkey_map = None
        return cls._instance
    
    def get(self) -> tuple[dict, dict]:
        """获取缓存的快捷键配置和映射表"""
        if self._hotkeys is None:
            self._hotkeys = load_screenshot_hotkeys()
            self._hotkey_map = {}
            for category, actions in self._hotkeys.items():
                for action, hotkey_str in actions.items():
                    parsed = parse_hotkey(hotkey_str)
                    if parsed[1] is not None:
                        self._hotkey_map[parsed] = action
        return self._hotkeys, self._hotkey_map
    
    def invalidate(self):
        """使缓存失效（配置更改时调用）"""
        self._hotkeys = None
        self._hotkey_map = None


# 全局单例实例
_hotkey_cache = HotkeyCache()


def get_cached_hotkeys() -> tuple[dict, dict]:
    """获取缓存的快捷键配置"""
    return _hotkey_cache.get()


def invalidate_hotkey_cache():
    """使快捷键缓存失效"""
    _hotkey_cache.invalidate()
