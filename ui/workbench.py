"""
工作台窗口
替代原 ArchiveWindow，采用侧栏图标导航 + 面板模式
支持归档、剪贴板等面板，便于后续扩展
"""

import qtawesome as qta
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QStackedWidget, QSizePolicy, QMessageBox
)
from PySide6.QtCore import Qt, Signal, QSize

from .archive import ArchiveGalleryPanel, ClipboardHistoryPanel, ClipboardHistoryManager


# ============================================================
# ActivityBar 按钮
# ============================================================

class WorkbenchActivityButton(QPushButton):
    """侧栏图标按钮"""
    
    def __init__(self, icon_name: str, tooltip: str, panel_id: str, parent=None):
        super().__init__(parent)
        self.panel_id = panel_id
        self._icon_name = icon_name
        self._active = False
        
        self.setFixedSize(40, 40)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(tooltip)
        self.setIcon(qta.icon(icon_name, color='#999'))
        self.setIconSize(QSize(22, 22))
        self._update_style()
    
    def set_active(self, active: bool):
        self._active = active
        if active:
            self.setIcon(qta.icon(self._icon_name, color='#6366f1'))
        else:
            self.setIcon(qta.icon(self._icon_name, color='#999'))
        self._update_style()
    
    def _update_style(self):
        if self._active:
            self.setStyleSheet("""
                QPushButton {
                    background-color: rgba(99, 102, 241, 0.1);
                    border: none;
                    border-radius: 8px;
                    border-left: 3px solid #6366f1;
                }
            """)
        else:
            self.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    border: none;
                    border-radius: 8px;
                }
                QPushButton:hover {
                    background-color: rgba(0, 0, 0, 0.04);
                }
            """)


# ============================================================
# WorkbenchWindow
# ============================================================

class WorkbenchWindow(QWidget):
    """工作台窗口 - 侧栏导航 + 面板"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Artco 工作台")
        self.setWindowIcon(qta.icon('mdi6.briefcase-outline', color='#6366f1'))
        self.setMinimumSize(960, 640)
        self.resize(980, 720)
        
        self._panels = {}        # panel_id -> QWidget
        self._buttons = {}       # panel_id -> WorkbenchActivityButton
        self._panel_titles = {}  # panel_id -> str
        self._panel_actions = {} # panel_id -> list of (icon, tooltip, callback)
        self._current_panel = None
        
        self.init_ui()
        self._register_builtin_panels()
        
        # 默认选中归档
        self._switch_panel("archive")
    
    def init_ui(self):
        self.setObjectName("workbench_window")
        
        # 主布局：水平（ActivityBar + 内容区）
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # ---- 左侧 ActivityBar ----
        self.activity_bar = QWidget()
        self.activity_bar.setObjectName("activity_bar")
        self.activity_bar.setFixedWidth(52)
        self.activity_bar_layout = QVBoxLayout(self.activity_bar)
        self.activity_bar_layout.setContentsMargins(6, 12, 6, 12)
        self.activity_bar_layout.setSpacing(4)
        self.activity_bar_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        # 底部弹性空间（用于放设置等底部按钮）
        self._activity_bar_spacer_added = False
        
        main_layout.addWidget(self.activity_bar)
        
        # ---- 右侧内容区 ----
        content_area = QWidget()
        content_area.setObjectName("content_area")
        content_layout = QVBoxLayout(content_area)
        content_layout.setContentsMargins(20, 16, 20, 16)
        content_layout.setSpacing(12)
        
        # 顶部 Header
        header_layout = QHBoxLayout()
        header_layout.setSpacing(8)
        
        self.panel_title = QLabel("归档")
        self.panel_title.setObjectName("panel_title")
        header_layout.addWidget(self.panel_title)
        
        header_layout.addStretch()
        
        # 操作按钮容器
        self.action_container = QHBoxLayout()
        self.action_container.setSpacing(8)
        header_layout.addLayout(self.action_container)
        
        content_layout.addLayout(header_layout)
        
        # 面板堆栈
        self.panel_stack = QStackedWidget()
        content_layout.addWidget(self.panel_stack)
        
        main_layout.addWidget(content_area, 1)
        
        # 全局样式
        self.setStyleSheet("""
            QWidget#workbench_window {
                background-color: #ffffff;
            }
            QWidget#activity_bar {
                background-color: #f8f9fa;
                border-right: 1px solid #e5e7eb;
            }
            QWidget#content_area {
                background-color: #ffffff;
            }
            QLabel#panel_title {
                font-size: 16px;
                font-weight: 600;
                color: #1f2937;
            }
            QWidget#card_container {
                background-color: transparent;
            }
            QPushButton#btn_action {
                background-color: #f5f5f5;
                border: 1px solid #e0e0e0;
                border-radius: 6px;
                padding: 6px 14px;
                font-size: 13px;
                color: #555;
            }
            QPushButton#btn_action:hover {
                background-color: #eee;
                border-color: #ccc;
            }
        """)
    
    def _register_builtin_panels(self):
        """注册内置面板"""
        # 归档面板
        self.archive_panel = ArchiveGalleryPanel()
        self.add_panel(
            panel_id="archive",
            panel=self.archive_panel,
            icon="mdi6.archive-outline",
            title="归档",
            tooltip="归档记录",
            actions=[
                ("mdi6.sync", "刷新", self._refresh_archive),
            ]
        )
        
        # 剪贴板面板
        self.clipboard_panel = ClipboardHistoryPanel()
        self.add_panel(
            panel_id="clipboard",
            panel=self.clipboard_panel,
            icon="mdi6.clipboard-text-outline",
            title="剪贴板",
            tooltip="剪贴板历史",
            actions=[
                ("mdi6.delete-outline", "清空", self._clear_clipboard),
            ]
        )
    
    def add_panel(self, panel_id: str, panel: QWidget, icon: str, title: str, 
                  tooltip: str, actions: list = None, position: str = "top"):
        """
        添加面板
        
        Args:
            panel_id: 面板唯一标识
            panel: 面板 QWidget
            icon: qtawesome 图标名
            title: 面板标题
            tooltip: 图标 tooltip
            actions: [(icon_name, tooltip, callback), ...] 操作按钮
            position: "top" 或 "bottom"（底部对齐）
        """
        # 创建 ActivityBar 按钮
        btn = WorkbenchActivityButton(icon, tooltip, panel_id)
        btn.clicked.connect(lambda: self._switch_panel(panel_id))
        
        if position == "bottom":
            if not self._activity_bar_spacer_added:
                self.activity_bar_layout.addStretch()
                self._activity_bar_spacer_added = True
        
        self.activity_bar_layout.addWidget(btn)
        
        # 注册面板
        self.panel_stack.addWidget(panel)
        self._panels[panel_id] = panel
        self._buttons[panel_id] = btn
        self._panel_titles[panel_id] = title
        self._panel_actions[panel_id] = actions or []
    
    def _switch_panel(self, panel_id: str):
        """切换面板"""
        if panel_id == self._current_panel:
            return
        if panel_id not in self._panels:
            return
        
        self._current_panel = panel_id
        
        # 更新按钮状态
        for pid, btn in self._buttons.items():
            btn.set_active(pid == panel_id)
        
        # 切换面板
        self.panel_stack.setCurrentWidget(self._panels[panel_id])
        
        # 更新标题
        self.panel_title.setText(self._panel_titles[panel_id])
        
        # 更新操作按钮
        self._update_action_buttons(panel_id)
    
    def _update_action_buttons(self, panel_id: str):
        """更新操作按钮区域"""
        # 清理旧按钮
        while self.action_container.count() > 0:
            item = self.action_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        # 添加新按钮
        actions = self._panel_actions.get(panel_id, [])
        for icon_name, tooltip, callback in actions:
            btn = QPushButton(f" {tooltip}")
            btn.setIcon(qta.icon(icon_name, color='#555'))
            btn.setObjectName("btn_action")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(tooltip)
            btn.clicked.connect(callback)
            self.action_container.addWidget(btn)
    
    def _refresh_archive(self):
        """刷新归档"""
        self.archive_panel.load_records()
    
    def _clear_clipboard(self):
        """清空剪贴板历史"""
        reply = QMessageBox.question(
            self, "确认清空",
            "确定要清空剪贴板历史吗？",
            QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Ok,
            QMessageBox.StandardButton.Cancel
        )
        if reply == QMessageBox.StandardButton.Ok:
            ClipboardHistoryManager.instance().clear()
