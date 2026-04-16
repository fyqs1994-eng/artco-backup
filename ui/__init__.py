"""
UI 组件模块 - 解耦后的统一导出

模块结构：
- ai_worker.py      : AI 工作线程
- settings.py       : 设置对话框
- prompt_manager.py : Prompt 管理相关组件
- archive.py        : 归档相关组件（ArchiveGalleryPanel, ClipboardHistoryPanel 等）
- workbench.py      : 工作台窗口（侧栏导航 + 面板）
- ai_result.py      : AI 结果展示组件
- image_viewer.py   : 图片浏览器（独立入口 viewer_main.py 使用）
- assign_panel.py   : 分配面板
"""

from .ai_worker import AIWorker
from .settings import SettingsDialog
from .prompt_manager import PromptSettingsWindow, PromptSelectMenu
from .archive import ArchiveDetailDialog, ArchiveCard, ArchiveGalleryPanel, ClipboardHistoryManager
from .workbench import WorkbenchWindow
from .ai_result import AIResultBubble, AIResultPanel, AIImageResultWindow
from .assign_panel import AssignPanel
from .clipboard_float import ClipboardFloatPanel

__all__ = [
    # AI 工作线程
    'AIWorker',
    
    # 设置
    'SettingsDialog',
    
    # Prompt 管理
    'PromptSettingsWindow',
    'PromptSelectMenu',
    
    # 归档
    'ArchiveDetailDialog',
    'ArchiveCard',
    'ArchiveGalleryPanel',
    'ClipboardHistoryManager',
    
    # 工作台
    'WorkbenchWindow',
    
    # AI 结果展示
    'AIResultBubble',
    'AIResultPanel',
    'AIImageResultWindow',
    
    # 分配面板
    'AssignPanel',
    
    # 剪贴板悬浮面板
    'ClipboardFloatPanel',
]
