"""
工具模块 - 快捷键管理和通用工具函数
"""

import json
import os
from config import HOTKEY_CONFIG_PATH


class HotkeyManager:
    """快捷键管理器"""
    
    # 默认快捷键
    DEFAULT_HOTKEYS = {
        'screenshot': 'F1',
        'clipboard_float': 'mousex1',
    }
    
    # 截图窗口默认快捷键
    DEFAULT_SCREENSHOT_HOTKEYS = {
        "基础操作": {
            "confirm": "Enter",
            "cancel": "Escape",
            "copy": "Ctrl+C",
            "save": "Ctrl+S",
            "pin": "P",
            "edit": "E",
            "undo": "Ctrl+Z",
            "redo": "Ctrl+Y",
            "select_all": "Ctrl+A",
            "toggle_toolbar": "Tab"
        },
        "选区调整": {
            "move_up": "Up",
            "move_down": "Down",
            "move_left": "Left",
            "move_right": "Right",
            "expand_up": "Shift+Up",
            "expand_down": "Shift+Down",
            "expand_left": "Shift+Left",
            "expand_right": "Shift+Right"
        },
        "标记工具": {
            "tool_freehand": "D",
            "tool_text": "T",
            "tool_none": "V"
        }
    }
    
    # 动作名称映射（用于 UI 显示）
    ACTION_NAMES = {
        "confirm": "确认复制",
        "cancel": "取消/关闭",
        "copy": "复制到剪贴板",
        "save": "保存文件",
        "pin": "屏幕贴图",
        "edit": "打开编辑器",
        "undo": "撤销",
        "redo": "重做",
        "select_all": "全屏选区",
        "toggle_toolbar": "显示/隐藏工具栏",
        "move_up": "上移选区",
        "move_down": "下移选区",
        "move_left": "左移选区",
        "move_right": "右移选区",
        "expand_up": "向上扩展",
        "expand_down": "向下扩展",
        "expand_left": "向左扩展",
        "expand_right": "向右扩展",
        "tool_freehand": "涂鸦工具",
        "tool_text": "文字工具",
        "tool_none": "取消工具"
    }
    
    def __init__(self):
        self.hotkeys = {}
        self.load()
    
    def load(self):
        """从 JSON 文件加载快捷键配置"""
        if os.path.exists(HOTKEY_CONFIG_PATH):
            try:
                with open(HOTKEY_CONFIG_PATH, 'r', encoding='utf-8') as f:
                    self.hotkeys = json.load(f)
            except Exception:
                self.hotkeys = {}
        
        # 确保所有默认快捷键都存在
        for key, value in self.DEFAULT_HOTKEYS.items():
            if key not in self.hotkeys:
                self.hotkeys[key] = value
        
        # 确保截图窗口快捷键存在
        if 'screenshot_window' not in self.hotkeys:
            self.hotkeys['screenshot_window'] = {}
        
        for category, actions in self.DEFAULT_SCREENSHOT_HOTKEYS.items():
            if category not in self.hotkeys['screenshot_window']:
                self.hotkeys['screenshot_window'][category] = {}
            for action, hotkey in actions.items():
                if action not in self.hotkeys['screenshot_window'][category]:
                    self.hotkeys['screenshot_window'][category][action] = hotkey
    
    def save(self):
        """保存快捷键配置到 JSON 文件"""
        try:
            with open(HOTKEY_CONFIG_PATH, 'w', encoding='utf-8') as f:
                json.dump(self.hotkeys, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
    
    def get(self, action: str) -> str:
        """获取指定动作的快捷键"""
        return self.hotkeys.get(action, self.DEFAULT_HOTKEYS.get(action, ''))
    
    def set(self, action: str, hotkey: str):
        """设置指定动作的快捷键"""
        self.hotkeys[action] = hotkey
        self.save()
    
    def get_screenshot_hotkeys(self) -> dict:
        """获取截图窗口快捷键配置"""
        return self.hotkeys.get('screenshot_window', self.DEFAULT_SCREENSHOT_HOTKEYS)
    
    def set_screenshot_hotkey(self, category: str, action: str, hotkey: str):
        """设置截图窗口快捷键"""
        if 'screenshot_window' not in self.hotkeys:
            self.hotkeys['screenshot_window'] = {}
        if category not in self.hotkeys['screenshot_window']:
            self.hotkeys['screenshot_window'][category] = {}
        self.hotkeys['screenshot_window'][category][action] = hotkey
        self.save()
    
    def get_action_name(self, action: str) -> str:
        """获取动作的中文名称"""
        return self.ACTION_NAMES.get(action, action)


def convert_hotkey_format(hotkey_str: str) -> str:
    """将 Qt 快捷键格式转换为 pynput 格式"""
    if not hotkey_str:
        return ''
    
    # 修饰键映射表
    modifier_mapping = {
        'Ctrl': '<ctrl>',
        'Alt': '<alt>',
        'Shift': '<shift>',
        'Meta': '<cmd>',
    }
    
    # 特殊键映射表
    special_keys = {
        'Space': '<space>',
        'Tab': '<tab>',
        'Return': '<enter>',
        'Enter': '<enter>',
        'Backspace': '<backspace>',
        'Delete': '<delete>',
        'Escape': '<esc>',
        'Esc': '<esc>',
        'Home': '<home>',
        'End': '<end>',
        'PageUp': '<page_up>',
        'PageDown': '<page_down>',
        'Up': '<up>',
        'Down': '<down>',
        'Left': '<left>',
        'Right': '<right>',
        'Insert': '<insert>',
        'CapsLock': '<caps_lock>',
        'NumLock': '<num_lock>',
        'ScrollLock': '<scroll_lock>',
        'PrintScreen': '<print_screen>',
        'Pause': '<pause>',
    }
    
    parts = hotkey_str.split('+')
    result = []
    
    for part in parts:
        part = part.strip()
        if part in modifier_mapping:
            result.append(modifier_mapping[part])
        elif part in special_keys:
            result.append(special_keys[part])
        elif part.upper().startswith('F') and part[1:].isdigit():
            # 功能键 F1-F12
            result.append(f'<{part.lower()}>')
        else:
            # 普通按键转小写
            result.append(part.lower())
    
    return '+'.join(result)


# 全局快捷键管理器实例
hotkey_manager = HotkeyManager()
