"""
侧栏组件 - VS Code 风格 Activity Bar + Sidebar
"""

import os
import json
from pathlib import Path
from typing import Optional, List, Dict

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QLineEdit, QFileDialog, QStackedWidget, QMessageBox
)
from PySide6.QtCore import Qt, Signal, QTimer, QSize, QRectF
from PySide6.QtGui import QFont, QPainter, QColor, QPen
import qtawesome as qta

from config import workspace_config, RESOURCE_TYPES, wecom_config
from ui.settings import SettingsDialog
from ui.theme import (
    BG_PRIMARY, BG_SECONDARY, BG_HOVER, BG_ACTIVE, BG_HOVER_SOFT, BG_HOVER_SUBTLE,
    BORDER_SUBTLE, BORDER_DEFAULT,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_TERTIARY, TEXT_MUTED,
    ACCENT_PRIMARY, ACCENT_HOVER, ACCENT_PRESSED, ACCENT_SUBTLE, ACCENT_BORDER, COLOR_ERROR, TYPE_COLORS,
    RADIUS_SM, RADIUS_MD, RADIUS_LG,
    SPACING_XS, SPACING_SM, SPACING_MD, SPACING_LG,
    ICON_SM, ICON_MD, ICON_DEFAULT, ICON_MUTED,
    SIDEBAR_WIDTH, BTN_SIZE_SM, ACTIVITY_BAR_WIDTH, ACTIVITY_ICON_SIZE,
    ICON_FOLDER, FILE_ICON_PSD, FILE_ICON_IMAGE, FILE_ICON_GIF, BRAND_WECHAT,
    get_scrollbar_style, get_icon_button_style
)



class ActivityBarButton(QWidget):
    """Activity Bar 图标按钮"""
    clicked = Signal(str)  # 发射按钮 id
    
    def __init__(self, icon_name: str, tooltip: str, button_id: str, parent=None):
        super().__init__(parent)
        self._icon_name = icon_name
        self._tooltip = tooltip
        self._button_id = button_id
        self._is_active = False
        self._is_hovered = False
        self._badge_count = 0
        
        self.setFixedSize(ACTIVITY_BAR_WIDTH, ACTIVITY_BAR_WIDTH)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(tooltip)
    
    def set_active(self, active: bool):
        self._is_active = active
        self.update()
    
    def is_active(self) -> bool:
        return self._is_active

    def set_badge_count(self, count: int):
        count = max(0, int(count or 0))
        if self._badge_count == count:
            return
        self._badge_count = count
        self.update()
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        rect = self.rect()
        
        # 背景
        if self._is_active:
            # 激活状态：微光渐变背景
            gradient = QColor(BG_HOVER)
            painter.fillRect(rect, gradient)
            # 左侧渐变激活指示条（3px，带圆角）
            indicator_rect = QColor(ACCENT_PRIMARY)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(indicator_rect)
            painter.drawRoundedRect(0, 8, 3, rect.height() - 16, 1.5, 1.5)
        elif self._is_hovered:
            # Hover 状态：浅色背景
            hover_bg = QColor(BG_HOVER)
            painter.fillRect(rect, hover_bg)

        
        # 图标
        icon_color = ACCENT_PRIMARY if self._is_active else ICON_DEFAULT
        icon = qta.icon(self._icon_name, color=icon_color)
        icon_pixmap = icon.pixmap(QSize(ACTIVITY_ICON_SIZE, ACTIVITY_ICON_SIZE))
        icon_x = (rect.width() - ACTIVITY_ICON_SIZE) // 2
        icon_y = (rect.height() - ACTIVITY_ICON_SIZE) // 2
        painter.drawPixmap(icon_x, icon_y, icon_pixmap)

        # Badge（未读数）
        if self._badge_count > 0:
            badge_text = "99+" if self._badge_count > 99 else str(self._badge_count)
            badge_d = 16
            badge_x = rect.right() - badge_d - 6
            badge_y = rect.top() + 6

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(COLOR_ERROR))
            painter.drawEllipse(badge_x, badge_y, badge_d, badge_d)

            painter.setPen(QColor("white"))
            font = painter.font()
            font.setPointSize(8)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(QRectF(badge_x, badge_y, badge_d, badge_d), Qt.AlignmentFlag.AlignCenter, badge_text)
    
    def enterEvent(self, event):
        self._is_hovered = True
        self.update()
    
    def leaveEvent(self, event):
        self._is_hovered = False
        self.update()
    
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._button_id)


class ActivityBar(QWidget):
    """Activity Bar - VS Code 风格左侧图标栏"""
    panel_changed = Signal(str)  # 发射面板 id
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._buttons: Dict[str, ActivityBarButton] = {}
        self._current_panel: Optional[str] = None
        
        self.setFixedWidth(ACTIVITY_BAR_WIDTH)
        self._init_ui()
    
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # 顶部按钮区
        self.top_container = QVBoxLayout()
        self.top_container.setContentsMargins(0, 4, 0, 0)
        self.top_container.setSpacing(0)
        layout.addLayout(self.top_container)
        
        layout.addStretch()
        
        # 底部按钮区（预留给设置等）
        self.bottom_container = QVBoxLayout()
        self.bottom_container.setContentsMargins(0, 0, 0, 4)
        self.bottom_container.setSpacing(0)
        layout.addLayout(self.bottom_container)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # 绘制背景
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(BG_SECONDARY))
        painter.drawRect(self.rect())
        
        # 绘制右侧边框
        painter.setPen(QPen(QColor(BORDER_DEFAULT), 1))
        painter.drawLine(self.width() - 1, 0, self.width() - 1, self.height())

    
    def add_button(self, icon_name: str, tooltip: str, button_id: str, position: str = "top"):
        """添加按钮"""
        btn = ActivityBarButton(icon_name, tooltip, button_id)
        btn.clicked.connect(self._on_button_clicked)
        self._buttons[button_id] = btn
        
        if position == "top":
            self.top_container.addWidget(btn)
        else:
            self.bottom_container.addWidget(btn)
        
        # 默认激活第一个按钮
        if len(self._buttons) == 1:
            self.set_active_panel(button_id)
    
    def _on_button_clicked(self, button_id: str):
        if self._current_panel == button_id:
            # 再次点击当前面板，切换收起/展开
            self.panel_changed.emit("")  # 空字符串表示收起
            self._current_panel = None
            for btn in self._buttons.values():
                btn.set_active(False)
        else:
            self.set_active_panel(button_id)
            self.panel_changed.emit(button_id)
    
    def set_active_panel(self, button_id: str):
        """设置激活的面板"""
        self._current_panel = button_id
        for bid, btn in self._buttons.items():
            btn.set_active(bid == button_id)
    
    def get_active_panel(self) -> Optional[str]:
        return self._current_panel


class SidebarHeader(QWidget):
    """侧栏头部 - 显示面板标题和操作"""
    action_clicked = Signal(str)  # 发射操作 id
    
    def __init__(self, title: str = "", parent=None):
        super().__init__(parent)
        self._title = title
        self._subtitle = ""
        self.setFixedHeight(48)
        self._init_ui()
    
    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(SPACING_MD, SPACING_XS, SPACING_SM, SPACING_XS)
        layout.setSpacing(SPACING_SM)
        
        # 标题区域
        title_container = QVBoxLayout()
        title_container.setSpacing(0)
        title_container.setContentsMargins(0, 0, 0, 0)
        
        # 主标题
        self.label_title = QLabel(self._title)
        self.label_title.setStyleSheet(f"""
            color: {TEXT_SECONDARY};
            font-size: 11px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        """)
        title_container.addWidget(self.label_title)
        
        # 副标题（可选）
        self.label_subtitle = QLabel()
        self.label_subtitle.setStyleSheet(f"color: {TEXT_TERTIARY}; font-size: 10px;")
        self.label_subtitle.hide()
        title_container.addWidget(self.label_subtitle)
        
        layout.addLayout(title_container, 1)
        
        # 操作按钮容器
        self.actions_layout = QHBoxLayout()
        self.actions_layout.setSpacing(2)
        layout.addLayout(self.actions_layout)
        
        self.setStyleSheet(f"""
            SidebarHeader {{
                background: transparent;
                border-bottom: 1px solid {BORDER_SUBTLE};
            }}
        """)
    
    def set_title(self, title: str):
        self._title = title
        self.label_title.setText(title)
    
    def set_subtitle(self, subtitle: str):
        """设置副标题"""
        self._subtitle = subtitle
        if subtitle:
            self.label_subtitle.setText(subtitle)
            self.label_subtitle.show()
        else:
            self.label_subtitle.hide()
    
    def add_action(self, icon_name: str, tooltip: str, action_id: str):
        """添加操作按钮"""
        btn = QPushButton()
        btn.setIcon(qta.icon(icon_name, color=ICON_MUTED))
        btn.setIconSize(QSize(14, 14))
        btn.setFixedSize(22, 22)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setToolTip(tooltip)
        btn.setProperty("action_id", action_id)
        btn.clicked.connect(lambda: self.action_clicked.emit(action_id))
        btn.setStyleSheet(get_icon_button_style())
        self.actions_layout.addWidget(btn)


class SearchBox(QWidget):
    """搜索框"""
    text_changed = Signal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(44)
        self._init_ui()
    
    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(SPACING_MD, SPACING_SM, SPACING_MD, SPACING_SM)
        
        # 容器
        container = QWidget()
        container.setStyleSheet(f"""
            QWidget {{
                background: {BG_PRIMARY};
                border: 1px solid {BORDER_DEFAULT};
                border-radius: {RADIUS_MD}px;
            }}
        """)
        container_layout = QHBoxLayout(container)
        container_layout.setContentsMargins(SPACING_MD, 0, SPACING_SM, 0)
        container_layout.setSpacing(SPACING_SM)
        
        # 搜索图标
        icon_label = QLabel()
        icon_label.setPixmap(qta.icon('mdi6.magnify', color=ICON_MUTED).pixmap(ICON_SM, ICON_SM))
        icon_label.setFixedSize(ICON_SM, ICON_SM)
        container_layout.addWidget(icon_label)
        
        # 输入框
        self.input = QLineEdit()
        self.input.setPlaceholderText("搜索主题...")
        self.input.setStyleSheet(f"""
            QLineEdit {{
                background: transparent;
                border: none;
                color: {TEXT_PRIMARY};
                font-size: 13px;
                padding: 4px 0;
            }}
            QLineEdit::placeholder {{
                color: {TEXT_MUTED};
            }}
        """)
        self.input.textChanged.connect(self.text_changed.emit)
        container_layout.addWidget(self.input, 1)
        
        layout.addWidget(container)
        self.setStyleSheet("background: transparent;")


class TopicItem(QFrame):
    """主题项"""
    clicked = Signal(str)
    
    def __init__(self, topic_name: str, topic_path: str, parent=None):
        super().__init__(parent)
        self.topic_name = topic_name
        self.topic_path = topic_path
        self._expanded = False
        self._is_active = False
        self._scanned = False
        self._files: Dict[str, List[Path]] = {}
        self._hover = False
        
        self.setFixedHeight(40)
        self._init_ui()

    def scan_files(self, force: bool = False):
        """扫描当前主题目录下的资源文件。

        默认只扫描一次（懒加载），force=True 可强制重新扫描。
        """
        if self._scanned and not force:
            return

        topic_dir = Path(self.topic_path)
        if not topic_dir.exists():
            self._files.clear()
            self.label_count.setText("")
            self.label_count.setVisible(False)
            self._scanned = True
            return

        total_count = 0
        self._files.clear()

        for rtype in RESOURCE_TYPES:
            type_dir = topic_dir / rtype
            if type_dir.exists():
                files = [
                    f
                    for f in type_dir.iterdir()
                    if f.is_file() and f.suffix.lower() in {'.png', '.jpg', '.jpeg', '.psd', '.gif', '.webp'}
                ]
                if files:
                    self._files[rtype] = sorted(files, key=lambda x: x.name)
                    total_count += len(files)

        self.label_count.setText(str(total_count) if total_count > 0 else "")
        self.label_count.setVisible(total_count > 0)
        self._scanned = True
    
    def _init_ui(self):
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setObjectName("topic_item")
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(SPACING_MD, SPACING_SM, SPACING_MD, SPACING_SM)
        layout.setSpacing(SPACING_SM)
        
        # 展开图标
        self.icon_expand = QLabel()
        self.icon_expand.setPixmap(qta.icon('mdi6.chevron-right', color=ICON_MUTED).pixmap(ICON_SM, ICON_SM))
        self.icon_expand.setFixedSize(ICON_SM, ICON_SM)
        layout.addWidget(self.icon_expand)
        
        # 文件夹图标
        icon_folder = QLabel()
        icon_folder.setPixmap(qta.icon('mdi6.folder', color=ICON_FOLDER).pixmap(ICON_MD, ICON_MD))

        layout.addWidget(icon_folder)
        
        # 主题名称
        self.label_name = QLabel(self.topic_name)
        self.label_name.setStyleSheet(f"""
            color: {TEXT_PRIMARY};
            font-size: 13px;
            font-weight: 500;
        """)
        layout.addWidget(self.label_name, 1)
        
        # 文件数量
        self.label_count = QLabel()
        self.label_count.setStyleSheet(f"""
            color: {TEXT_TERTIARY};
            font-size: 11px;
            padding: 2px 6px;
            background: transparent;
        """)
        layout.addWidget(self.label_count)
        
        self._update_style()
    
    def _update_style(self):
        if self._is_active:
            bg = ACCENT_SUBTLE
            border = ACCENT_BORDER
            name_color = TEXT_PRIMARY
            font_weight = "600"
        elif self._hover:
            bg = BG_HOVER
            border = BORDER_SUBTLE
            name_color = TEXT_PRIMARY
            font_weight = "500"
        else:
            bg = "transparent"
            border = "transparent"
            name_color = TEXT_SECONDARY
            font_weight = "500"
        
        self.setStyleSheet(f"""
            TopicItem {{
                background: {bg};
                border: 1px solid {border};
                border-radius: {RADIUS_MD}px;
                margin: 1px {SPACING_SM}px 1px {SPACING_SM}px;
            }}
        """)
        # 更新展开图标
        icon_name = 'mdi6.chevron-down' if self._expanded else 'mdi6.chevron-right'
        icon_color = TEXT_PRIMARY if (self._hover or self._is_active) else ICON_MUTED
        self.icon_expand.setPixmap(qta.icon(icon_name, color=icon_color).pixmap(ICON_SM, ICON_SM))
        # 更新名称颜色
        self.label_name.setStyleSheet(f"""
            color: {name_color};
            font-size: 13px;
            font-weight: {font_weight};
        """)
    
    def enterEvent(self, event):
        self._hover = True
        self._update_style()
    
    def leaveEvent(self, event):
        self._hover = False
        self._update_style()
    
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.topic_path)
    

    
    def set_expanded(self, expanded: bool):
        self._expanded = expanded
        icon_name = 'mdi6.chevron-down' if expanded else 'mdi6.chevron-right'
        self.icon_expand.setPixmap(qta.icon(icon_name, color=ICON_MUTED).pixmap(ICON_SM, ICON_SM))

    def set_active(self, active: bool):
        if self._is_active == active:
            return
        self._is_active = active
        self._update_style()
    
    def get_files(self) -> Dict[str, List[Path]]:
        return self._files

    def is_scanned(self) -> bool:
        return self._scanned


class FileItem(QFrame):
    """文件项"""
    clicked = Signal(str)
    double_clicked = Signal(str)
    
    def __init__(self, file_path: Path, parent=None):
        super().__init__(parent)
        self.file_path = file_path
        self._is_selected = False
        self._hover = False
        
        self.setFixedHeight(32)
        self._init_ui()
    
    def _init_ui(self):
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setObjectName("file_item")
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(44, SPACING_SM, SPACING_MD, SPACING_SM)
        layout.setSpacing(SPACING_SM)
        
        # 文件图标
        icon = QLabel()
        suffix = self.file_path.suffix.lower()
        if suffix == '.psd':
            icon.setPixmap(qta.icon('mdi6.palette-outline', color=FILE_ICON_PSD).pixmap(ICON_SM, ICON_SM))
        elif suffix in {'.png', '.jpg', '.jpeg'}:
            icon.setPixmap(qta.icon('mdi6.image', color=FILE_ICON_IMAGE).pixmap(ICON_SM, ICON_SM))
        elif suffix == '.gif':
            icon.setPixmap(qta.icon('mdi6.gif', color=FILE_ICON_GIF).pixmap(ICON_SM, ICON_SM))

        else:
            icon.setPixmap(qta.icon('mdi6.file', color=ICON_MUTED).pixmap(ICON_SM, ICON_SM))
        layout.addWidget(icon)
        
        # 文件名
        name = self.file_path.stem
        if len(name) > 25:
            name = name[:22] + "..."
        self.label_name = QLabel(name)
        self.label_name.setToolTip(self.file_path.name)
        self.label_name.setObjectName("file_name")
        layout.addWidget(self.label_name, 1)
        
        self._update_style()
    
    def _update_style(self):
        if self._is_selected:
            bg = ACCENT_SUBTLE
            border = ACCENT_BORDER
            text_color = TEXT_PRIMARY
            font_weight = "600"
        elif self._hover:
            bg = BG_HOVER
            border = BORDER_SUBTLE
            text_color = TEXT_PRIMARY
            font_weight = "500"

        else:
            bg = "transparent"
            border = "transparent"
            text_color = TEXT_SECONDARY
            font_weight = "400"
        
        self.setStyleSheet(f"""
            FileItem {{
                background: {bg};
                border: 1px solid {border};
                border-radius: {RADIUS_SM}px;
                margin: 1px {SPACING_SM}px 1px {SPACING_SM}px;
            }}
        """)
        self.label_name.setStyleSheet(f"color: {text_color}; font-size: 12px; font-weight: {font_weight};")
    
    def enterEvent(self, event):
        self._hover = True
        self._update_style()
    
    def leaveEvent(self, event):
        self._hover = False
        self._update_style()
    
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(str(self.file_path))
    
    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit(str(self.file_path))
    
    def set_selected(self, selected: bool):
        if self._is_selected == selected:
            return
        self._is_selected = selected
        self._update_style()


class ResourceTypeHeader(QWidget):
    """资源类型头部"""
    def __init__(self, type_name: str, count: int, parent=None):
        super().__init__(parent)
        self.setFixedHeight(24)
        self.setProperty("rtype", type_name)
        self._base_count = count
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(44, SPACING_XS, SPACING_MD, SPACING_XS)
        layout.setSpacing(SPACING_SM)
        
        # 类型颜色标记
        color_dot = QLabel()
        color = TYPE_COLORS.get(type_name, TEXT_MUTED)
        color_dot.setFixedSize(6, 6)
        color_dot.setStyleSheet(f"""
            background: {color};
            border-radius: 3px;
        """)
        layout.addWidget(color_dot)
        
        # 类型名称
        label = QLabel(type_name)
        label.setStyleSheet(f"""
            color: {TEXT_TERTIARY};
            font-size: 11px;
            font-weight: 500;
        """)
        layout.addWidget(label)
        
        # 数量
        self.count_label = QLabel(f"{count}")
        self.count_label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        layout.addWidget(self.count_label)
        
        layout.addStretch()

    def set_count(self, count: Optional[int]):
        if count is None:
            count = self._base_count
        self.count_label.setText(str(count))


class WeComGroupItem(QFrame):
    """企微群项 - 显示群信息"""
    send_requested = Signal(str, str)  # webhook_url, group_name
    
    def __init__(self, webhook_name: str, webhook_url: str, parent=None):
        super().__init__(parent)
        self.webhook_name = webhook_name
        self.webhook_url = webhook_url
        self._hover = False
        
        self.setFixedHeight(48)
        self._init_ui()
    
    def _init_ui(self):
        os.environ.setdefault("QT_API", "pyside6")
        from qfluentwidgets import PrimaryPushButton

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setObjectName("wecom_group_item")
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(SPACING_MD, SPACING_SM, SPACING_MD, SPACING_SM)
        layout.setSpacing(SPACING_MD)
        
        # 企微图标
        icon_label = QLabel()
        icon_label.setPixmap(qta.icon('mdi6.wechat', color=BRAND_WECHAT).pixmap(20, 20))

        layout.addWidget(icon_label)
        
        # 群名称
        self.label_name = QLabel(self.webhook_name)
        self.label_name.setStyleSheet(f"""
            color: {TEXT_PRIMARY};
            font-size: 13px;
            font-weight: 500;
        """)
        layout.addWidget(self.label_name, 1)
        
        # 发送按钮
        self.btn_send = PrimaryPushButton("发送")
        self.btn_send.setFixedSize(60, 28)
        self.btn_send.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_send.clicked.connect(self._on_send)
        layout.addWidget(self.btn_send)
        
        self._update_style()
    
    def _update_style(self):
        # 群名称颜色 hover 变化
        name_color = TEXT_PRIMARY if self._hover else TEXT_SECONDARY
        
        self.label_name.setStyleSheet(f"""
            color: {name_color};
            font-size: 13px;
            font-weight: 500;
        """)

    
    def _on_send(self):
        self.send_requested.emit(self.webhook_url, self.webhook_name)
    
    def enterEvent(self, event):
        self._hover = True
        self._update_style()
    
    def leaveEvent(self, event):
        self._hover = False
        self._update_style()
    
    def set_sending(self, sending: bool):
        """设置发送状态"""
        if sending:
            self.btn_send.setText("发送中...")
            self.btn_send.setEnabled(False)
        else:
            self.btn_send.setText("发送")
            self.btn_send.setEnabled(True)
            self._update_style()


class WeComPanel(QWidget):
    """企微快捷发送面板"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._groups: List[WeComGroupItem] = []
        self._current_image_data: Optional[bytes] = None
        self._send_threads = []  # 保持线程引用，防止被垃圾回收
        
        self._init_ui()
        QTimer.singleShot(100, self._load_webhooks)
    
    def _init_ui(self):
        self.setStyleSheet("background: transparent;")
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # 头部
        self.header = SidebarHeader("企微快捷发送")
        self.header.add_action('mdi6.refresh', '刷新', 'refresh')
        self.header.add_action('mdi6.cog-outline', '设置', 'settings')
        self.header.action_clicked.connect(self._on_header_action)
        layout.addWidget(self.header)
        
        # 说明文本
        info_label = QLabel("点击发送将当前图片发送到企微群")
        info_label.setStyleSheet(f"""
            color: {TEXT_TERTIARY};
            font-size: 11px;
            padding: {SPACING_SM}px {SPACING_MD}px;
            border-bottom: 1px solid {BORDER_SUBTLE};
        """)
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        # 群列表容器
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet(f"""
            QScrollArea {{
                background: transparent;
                border: none;
            }}
            {get_scrollbar_style()}
        """)
        
        self.content_widget = QWidget()
        self.content_widget.setStyleSheet("background: transparent;")
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(0)
        self.content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        self.scroll_area.setWidget(self.content_widget)
        layout.addWidget(self.scroll_area, 1)
    
    def _on_header_action(self, action_id: str):
        if action_id == 'refresh':
            self._load_webhooks()
        elif action_id == 'settings':
            # 打开设置对话框的企微配置
            from ui.settings import SettingsDialog
            dialog = SettingsDialog(self)
            dialog.show_tab('wecom')
            dialog.exec()
            self._load_webhooks()
    
    def _load_webhooks(self):
        """加载 webhook 配置"""
        webhooks = wecom_config.get_webhooks()
        
        self._clear_content()
        
        if not webhooks:
            self._show_empty_state()
            return
        
        for wh in webhooks:
            group_item = WeComGroupItem(wh["name"], wh["url"])
            group_item.send_requested.connect(self._on_send_to_group)
            self.content_layout.addWidget(group_item)
            self._groups.append(group_item)
    
    def _clear_content(self):
        """清空内容"""
        for group in self._groups:
            group.deleteLater()
        self._groups.clear()
        
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
    
    def _show_empty_state(self):
        """显示空状态"""
        empty_widget = QWidget()
        empty_widget.setStyleSheet(f"""
            background: {BG_PRIMARY};
            border: 1px solid {BORDER_SUBTLE};
            border-radius: {RADIUS_MD}px;
        """)
        empty_layout = QVBoxLayout(empty_widget)
        empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.setSpacing(SPACING_SM)
        empty_layout.setContentsMargins(SPACING_MD, 48, SPACING_MD, 48)
        
        icon_label = QLabel()
        icon_label.setPixmap(qta.icon('mdi6.wechat', color=ICON_MUTED).pixmap(32, 32))
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(icon_label)
        
        title = QLabel("暂未配置企微群")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 13px; font-weight: 600;")
        empty_layout.addWidget(title)
        
        subtitle = QLabel("请在设置中添加 Webhook")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet(f"color: {TEXT_TERTIARY}; font-size: 12px;")
        empty_layout.addWidget(subtitle)
        
        self.content_layout.addWidget(empty_widget)
    
    def set_current_image(self, image_data: bytes):
        """设置当前图片数据"""
        self._current_image_data = image_data
    
    def _on_send_to_group(self, webhook_url: str, group_name: str):
        """发送到企微群"""
        if not self._current_image_data:
            from ui.theme import get_dialog_style
            msg_box = QMessageBox(QMessageBox.Icon.Warning, "提示", "没有可发送的图片", QMessageBox.StandardButton.Ok, self)
            msg_box.setOption(QMessageBox.Option.DontUseNativeDialog, True)
            msg_box.setStyleSheet(get_dialog_style())
            msg_box.exec()
            return
        
        # 弹出备注输入框
        from PySide6.QtWidgets import QInputDialog
        from ui.theme import get_dialog_style
        
        # 创建对话框并应用样式
        dialog = QInputDialog(self)
        dialog.setWindowTitle("发送备注")
        dialog.setLabelText(f"发送到 [{group_name}]")
        dialog.setTextValue("")
        dialog.setStyleSheet(get_dialog_style())
        dialog.setOkButtonText("发送")
        dialog.setCancelButtonText("取消")
        
        if not dialog.exec():
            return
            
        note = dialog.textValue()

        
        # 查找对应的群项并设置发送状态
        target_group = None
        for group in self._groups:
            if group.webhook_url == webhook_url:
                group.set_sending(True)
                target_group = group
                break
        
        if not target_group:
            return
        
        # 创建发送线程
        from ui.feedback_dialog import WeComSendThread
        send_thread = WeComSendThread(webhook_url, self._current_image_data, note)
        self._send_threads.append(send_thread)  # 添加到列表保持引用
        
        def on_finished(success, msg, g=target_group, t=send_thread):
            self._on_send_finished(success, msg, g, webhook_url)
            if t in self._send_threads:
                self._send_threads.remove(t)
                
        send_thread.finished.connect(on_finished)
        send_thread.start()
    
    def _on_send_finished(self, success: bool, message: str, group: WeComGroupItem, webhook_url: str):
        """发送完成回调"""
        group.set_sending(False)
        
        from ui.theme import get_dialog_style
        if success:
            msg_box = QMessageBox(QMessageBox.Icon.Information, "发送成功", message, QMessageBox.StandardButton.Ok, self)
            msg_box.setOption(QMessageBox.Option.DontUseNativeDialog, True)
            msg_box.setStyleSheet(get_dialog_style())
            msg_box.exec()
            
            # 记录上次使用
            group_name = group.webhook_name
            wecom_config.set_last_used(group_name)
        else:
            msg_box = QMessageBox(QMessageBox.Icon.Warning, "发送失败", message, QMessageBox.StandardButton.Ok, self)
            msg_box.setOption(QMessageBox.Option.DontUseNativeDialog, True)
            msg_box.setStyleSheet(get_dialog_style())
            msg_box.exec()



class ExplorerPanel(QWidget):
    """资源管理器面板 - 显示工作区文件"""
    file_selected = Signal(str)
    file_opened = Signal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._topics: List[TopicItem] = []
        self._current_file: Optional[str] = None
        self._expanded_topics: set = set()
        self._active_topic_path: Optional[str] = None
        self._filter_text: str = ""
        self._filter_timer = QTimer(self)
        self._filter_timer.setSingleShot(True)
        self._filter_timer.timeout.connect(self._apply_filter)
        
        self._init_ui()
        QTimer.singleShot(100, self._load_workspace)
    
    def _init_ui(self):
        self.setStyleSheet("background: transparent;")
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # 头部
        self.header = SidebarHeader("资源管理器")
        self.header.add_action('mdi6.folder-swap-outline', '切换工作区', 'change_workspace')
        self.header.add_action('mdi6.refresh', '刷新', 'refresh')
        self.header.action_clicked.connect(self._on_header_action)
        layout.addWidget(self.header)
        
        # 工作区名称栏
        self.workspace_bar = QWidget()
        self.workspace_bar.setFixedHeight(28)
        self.workspace_bar.setStyleSheet(f"background: transparent;")
        ws_layout = QHBoxLayout(self.workspace_bar)
        ws_layout.setContentsMargins(SPACING_MD, 4, SPACING_MD, 4)
        ws_layout.setSpacing(SPACING_SM)
        
        ws_icon = QLabel()
        ws_icon.setPixmap(qta.icon('mdi6.folder', color=ICON_FOLDER).pixmap(16, 16))

        ws_layout.addWidget(ws_icon)
        
        self.label_workspace = QLabel("WORKSPACE")
        self.label_workspace.setStyleSheet(f"""
            color: {TEXT_PRIMARY};
            font-size: 11px;
            font-weight: 600;
        """)
        ws_layout.addWidget(self.label_workspace, 1)
        
        # 展开/收起图标
        self.icon_expand = QLabel()
        self.icon_expand.setPixmap(qta.icon('mdi6.chevron-down', color=ICON_MUTED).pixmap(14, 14))
        ws_layout.addWidget(self.icon_expand)
        
        layout.addWidget(self.workspace_bar)

        # 搜索框（联动过滤）
        self.search_box = SearchBox()
        self.search_box.text_changed.connect(self._on_search_text_changed)
        layout.addWidget(self.search_box)
        
        # 文件列表容器
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet(f"""
            QScrollArea {{
                background: transparent;
                border: none;
            }}
            {get_scrollbar_style()}
        """)
        
        self.content_widget = QWidget()
        self.content_widget.setStyleSheet("background: transparent;")
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, SPACING_SM)
        self.content_layout.setSpacing(0)
        self.content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        self.scroll_area.setWidget(self.content_widget)
        layout.addWidget(self.scroll_area, 1)
    
    def _on_header_action(self, action_id: str):
        if action_id == 'change_workspace':
            self._change_workspace()
        elif action_id == 'refresh':
            self.refresh()

    def _on_search_text_changed(self, text: str):
        # debounce，避免每个字符都触发大量 UI 更新
        self._filter_text = (text or "").strip().lower()
        self._filter_timer.start(120)

    def _apply_filter(self):
        query = (self._filter_text or "").strip().lower()

        # topic_path -> widget
        topic_map = {t.topic_path: t for t in self._topics}

        def file_matches(fi: FileItem) -> bool:
            if not query:
                return True
            name = fi.file_path.name.lower()
            stem = fi.file_path.stem.lower()
            return query in name or query in stem

        def topic_matches(ti: TopicItem) -> bool:
            if not query:
                return True
            if query in ti.topic_name.lower():
                return True
            # 只在已扫描主题里做文件名匹配，避免全量扫描带来卡顿
            if ti.is_scanned():
                for files in ti.get_files().values():
                    for p in files:
                        n = p.name.lower()
                        s = p.stem.lower()
                        if query in n or query in s:
                            return True
            return False

        # 1) 过滤主题可见性
        for ti in self._topics:
            ti.setVisible(topic_matches(ti))

        topic_visible = {tp: w.isVisible() for tp, w in topic_map.items()}

        # 2) 过滤已展开的文件与类型头，并更新头部计数
        visible_counts: Dict[tuple, int] = {}

        for i in range(self.content_layout.count()):
            item = self.content_layout.itemAt(i)
            w = item.widget() if item else None
            if not w:
                continue

            if isinstance(w, FileItem):
                tp = w.property("topic_path")
                if not tp or not topic_visible.get(tp, True):
                    w.setVisible(False)
                    continue

                show = file_matches(w)
                w.setVisible(show)

                if show:
                    # rtype 目录名：.../<topic>/<rtype>/<file>
                    try:
                        rtype = w.file_path.parent.name
                    except Exception:
                        rtype = ""
                    key = (tp, rtype)
                    visible_counts[key] = visible_counts.get(key, 0) + 1

        for i in range(self.content_layout.count()):
            item = self.content_layout.itemAt(i)
            w = item.widget() if item else None
            if not w:
                continue

            if isinstance(w, ResourceTypeHeader):
                tp = w.property("topic_path")
                rtype = w.property("rtype")

                if not tp or not topic_visible.get(tp, True):
                    w.setVisible(False)
                    continue

                if not query:
                    w.setVisible(True)
                    w.set_count(None)
                else:
                    cnt = visible_counts.get((tp, rtype), 0)
                    w.setVisible(cnt > 0)
                    w.set_count(cnt)
    
    def _load_workspace(self):
        workspace_path = workspace_config.get_workspace_path()
        
        if workspace_path:
            name = Path(workspace_path).name.upper()
            self.label_workspace.setText(name)
            self.label_workspace.setToolTip(workspace_path)
        else:
            self.label_workspace.setText("未设置工作区")
        
        if not workspace_path or not os.path.isdir(workspace_path):
            self._show_empty_state()
            return
        
        self._scan_workspace(workspace_path)
    
    def _scan_workspace(self, workspace_path: str):
        self._clear_content()
        self._topics.clear()
        self._set_active_topic(None)
        
        workspace_dir = Path(workspace_path)
        topics = []
        
        for item in workspace_dir.iterdir():
            if item.is_dir() and not item.name.startswith('.'):
                topics.append((item.name, str(item)))
        
        topics.sort(key=lambda x: x[0].lower())
        
        for topic_name, topic_path in topics:
            topic_item = TopicItem(topic_name, topic_path)
            topic_item.clicked.connect(self._on_topic_clicked)
            self.content_layout.addWidget(topic_item)
            self._topics.append(topic_item)
    
    def _clear_content(self):
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
    
    def _show_empty_state(self):
        self._clear_content()
        
        empty_widget = QWidget()
        empty_widget.setStyleSheet(f"""
            background: {BG_PRIMARY};
            border: 1px solid {BORDER_SUBTLE};
            border-radius: {RADIUS_MD}px;
        """)
        empty_layout = QVBoxLayout(empty_widget)
        empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.setSpacing(SPACING_SM)
        empty_layout.setContentsMargins(SPACING_MD, 48, SPACING_MD, 48)
        
        icon_label = QLabel()
        icon_label.setPixmap(qta.icon('mdi6.folder-plus-outline', color=ICON_MUTED).pixmap(32, 32))
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(icon_label)
        
        title = QLabel("未设置工作区")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 13px; font-weight: 600;")
        empty_layout.addWidget(title)
        
        subtitle = QLabel("点击上方图标选择工作区")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet(f"color: {TEXT_TERTIARY}; font-size: 12px;")
        empty_layout.addWidget(subtitle)
        
        self.content_layout.addWidget(empty_widget)
    
    def _on_topic_clicked(self, topic_path: str):
        topic_item = None
        for item in self._topics:
            if item.topic_path == topic_path:
                topic_item = item
                break
        
        if not topic_item:
            return

        # 选中文件夹时：高亮文件夹，并清除文件选中态（避免“文件/文件夹同时选中”的视觉冲突）
        self._set_active_topic(topic_path)
        if self._current_file is not None:
            self._current_file = None
            self._update_file_selection()
        
        if topic_path in self._expanded_topics:
            self._expanded_topics.discard(topic_path)
            topic_item.set_expanded(False)
            self._collapse_topic(topic_item)
        else:
            self._expanded_topics.add(topic_path)
            topic_item.set_expanded(True)
            self._expand_topic(topic_item)
    
    def _expand_topic(self, topic_item: TopicItem):
        # 懒加载：展开时才扫描文件
        topic_item.scan_files()
        files = topic_item.get_files()
        if not files:
            return
        
        index = self.content_layout.indexOf(topic_item)
        insert_index = index + 1
        
        for rtype in RESOURCE_TYPES:
            if rtype in files:
                header = ResourceTypeHeader(rtype, len(files[rtype]))
                header.setProperty("topic_path", topic_item.topic_path)
                self.content_layout.insertWidget(insert_index, header)
                insert_index += 1
                
                for file_path in files[rtype]:
                    file_item = FileItem(file_path)
                    file_item.setProperty("topic_path", topic_item.topic_path)
                    file_item.clicked.connect(self._on_file_clicked)
                    file_item.double_clicked.connect(self._on_file_double_clicked)
                    
                    if self._current_file and str(file_path) == self._current_file:
                        file_item.set_selected(True)
                    
                    self.content_layout.insertWidget(insert_index, file_item)
                    insert_index += 1

        # 展开完成后，应用当前过滤条件（只影响已展开的内容）
        if self._filter_text.strip():
            self._apply_filter()
    
    def _collapse_topic(self, topic_item: TopicItem):
        items_to_remove = []
        for i in range(self.content_layout.count()):
            item = self.content_layout.itemAt(i)
            if item and item.widget():
                widget = item.widget()
                if widget.property("topic_path") == topic_item.topic_path:
                    items_to_remove.append(widget)
        
        for widget in items_to_remove:
            self.content_layout.removeWidget(widget)
            widget.deleteLater()
    
    def _on_file_clicked(self, file_path: str):
        self._current_file = file_path

        sender = self.sender()
        topic_path = None
        if sender is not None:
            try:
                topic_path = sender.property("topic_path")
            except Exception:
                topic_path = None

        if not topic_path:
            topic_path = str(Path(file_path).parent.parent)

        # 选中文件时：只保留文件选中态，不高亮文件夹
        self._set_active_topic(None)
        self._update_file_selection()
        self.file_selected.emit(file_path)
    
    def _on_file_double_clicked(self, file_path: str):
        self._current_file = file_path

        sender = self.sender()
        topic_path = None
        if sender is not None:
            try:
                topic_path = sender.property("topic_path")
            except Exception:
                topic_path = None

        if not topic_path:
            topic_path = str(Path(file_path).parent.parent)

        # 双击打开文件时：只保留文件选中态，不高亮文件夹
        self._set_active_topic(None)
        self._update_file_selection()
        self.file_opened.emit(file_path)
    
    def _update_file_selection(self):
        for i in range(self.content_layout.count()):
            item = self.content_layout.itemAt(i)
            if item and item.widget():
                widget = item.widget()
                if isinstance(widget, FileItem):
                    widget.set_selected(str(widget.file_path) == self._current_file)

    def _set_active_topic(self, topic_path: Optional[str]):
        if self._active_topic_path == topic_path:
            return

        # 先取消旧的 active
        if self._active_topic_path is not None:
            for item in self._topics:
                if item.topic_path == self._active_topic_path:
                    item.set_active(False)
                    break

        self._active_topic_path = topic_path

        # 再激活新的 active
        if topic_path is not None:
            for item in self._topics:
                if item.topic_path == topic_path:
                    item.set_active(True)
                    break
    
    def _change_workspace(self):
        current = workspace_config.get_workspace_path()
        path = QFileDialog.getExistingDirectory(
            self, "选择工作区目录", current or ""
        )
        if path:
            workspace_config.set_workspace_path(path)
            self._load_workspace()
    
    def refresh(self):
        self._expanded_topics.clear()
        self._load_workspace()
    
    def set_current_file(self, file_path: str):
        self._current_file = file_path
        self._set_active_topic(None)
        self._update_file_selection()
        
        if file_path:
            file_dir = Path(file_path).parent.parent
            topic_path = str(file_dir)
            
            if topic_path not in self._expanded_topics:
                for topic_item in self._topics:
                    if topic_item.topic_path == topic_path:
                        self._expanded_topics.add(topic_path)
                        topic_item.set_expanded(True)
                        self._expand_topic(topic_item)
                        break




class InboxItem(QFrame):
    """收件箱条目"""
    open_requested = Signal(str)

    def __init__(self, meta: dict, workspace_root: Path, parent=None):
        super().__init__(parent)
        self.meta = meta
        self.workspace_root = workspace_root
        self._hover = False

        self.setFixedHeight(56)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setObjectName("inbox_item")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(SPACING_MD, SPACING_SM, SPACING_MD, SPACING_SM)
        layout.setSpacing(SPACING_MD)

        # 图标
        icon_label = QLabel()
        icon_label.setPixmap(qta.icon('mdi6.inbox', color=ACCENT_PRIMARY).pixmap(20, 20))
        layout.addWidget(icon_label)

        # 文本
        content = QVBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(2)

        topic = (meta.get("topic") or "").strip()
        rtype = (meta.get("rtype") or "").strip()
        vendor = (meta.get("vendor") or "").strip()
        version = (meta.get("version") or "").strip()
        filename = Path(meta.get("submit_path") or meta.get("submit_rel") or "").name

        title = f"{topic}/{rtype}  {filename}".strip()
        if len(title) > 42:
            title = title[:39] + "..."

        self.label_title = QLabel(title)
        self.label_title.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 13px; font-weight: 600;")

        subtitle = f"{vendor}  {version}"
        self.label_subtitle = QLabel(subtitle)
        self.label_subtitle.setStyleSheet(f"color: {TEXT_TERTIARY}; font-size: 11px;")

        content.addWidget(self.label_title)
        content.addWidget(self.label_subtitle)

        layout.addLayout(content, 1)

        self._update_style()

    def _update_style(self):
        if self._hover:
            bg = BG_HOVER
            border = BORDER_SUBTLE
        else:
            bg = "transparent"
            border = "transparent"

        self.setStyleSheet(f"""
            InboxItem {{
                background: {bg};
                border: 1px solid {border};
                border-radius: {RADIUS_MD}px;
                margin: 1px {SPACING_SM}px 1px {SPACING_SM}px;
            }}
        """)

    def enterEvent(self, event):
        self._hover = True
        self._update_style()

    def leaveEvent(self, event):
        self._hover = False
        self._update_style()

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return

        submit_path = self.meta.get("submit_path")
        submit_rel = self.meta.get("submit_rel")
        if submit_path:
            self.open_requested.emit(str(submit_path))
        elif submit_rel:
            self.open_requested.emit(str(self.workspace_root / submit_rel))


class InboxPanel(QWidget):
    """收件箱面板 - 监听 `_INBOX` 目录并展示提交列表"""

    file_opened = Signal(str)
    count_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: List[InboxItem] = []
        self._last_count = 0
        self._read_count = 0  # 已读数量（用户最后一次查看时的数量）

        self._init_ui()

        # 定时刷新未读数（轻量）；面板可见时再刷新列表
        self._timer = QTimer(self)
        self._timer.setInterval(1500)
        self._timer.timeout.connect(self._refresh_count)
        self._timer.start()

        QTimer.singleShot(200, self.refresh)

    def _init_ui(self):
        self.setStyleSheet("background: transparent;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.header = SidebarHeader("收件箱")
        self.header.add_action('mdi6.refresh', '刷新', 'refresh')
        self.header.add_action('mdi6.folder-open-outline', '打开 _INBOX', 'open_inbox')
        self.header.action_clicked.connect(self._on_header_action)
        layout.addWidget(self.header)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet(f"""
            QScrollArea {{
                background: transparent;
                border: none;
            }}
            {get_scrollbar_style()}
        """)

        self.content_widget = QWidget()
        self.content_widget.setStyleSheet("background: transparent;")
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, SPACING_SM, 0, SPACING_SM)
        self.content_layout.setSpacing(0)
        self.content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.scroll_area.setWidget(self.content_widget)
        layout.addWidget(self.scroll_area, 1)

    def _on_header_action(self, action_id: str):
        if action_id == 'refresh':
            self.refresh()
        elif action_id == 'open_inbox':
            self._open_inbox_folder()

    def _get_inbox_root(self) -> Optional[Path]:
        workspace_path = workspace_config.get_workspace_path()
        if not workspace_path:
            return None
        return Path(workspace_path) / "_INBOX"

    def _open_inbox_folder(self):
        inbox_root = self._get_inbox_root()
        if not inbox_root:
            return
        inbox_root.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(str(inbox_root))
        except Exception:
            pass

    def _clear(self):
        for it in self._items:
            it.deleteLater()
        self._items.clear()

        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _refresh_count(self):
        inbox_root = self._get_inbox_root()
        if not inbox_root or not inbox_root.exists():
            count = 0
        else:
            try:
                count = sum(1 for p in inbox_root.rglob("*.json") if p.is_file())
            except Exception:
                count = 0

        if count != self._last_count:
            self._last_count = count
            # badge 只显示新增数量（当前数量 - 已读数量）
            unread = max(0, count - self._read_count)
            self.count_changed.emit(unread)
            # 面板正在显示时，顺便刷新列表
            if self.isVisible():
                self.refresh()

    def refresh(self):
        inbox_root = self._get_inbox_root()
        if not inbox_root:
            self._show_empty("未配置工作区")
            self.count_changed.emit(0)
            return

        inbox_root.mkdir(parents=True, exist_ok=True)

        metas = []
        try:
            for meta_path in inbox_root.rglob("*.json"):
                if not meta_path.is_file():
                    continue
                try:
                    with open(meta_path, "r", encoding="utf-8") as f:
                        meta = json.load(f)
                    meta["_meta_path"] = str(meta_path)
                    metas.append(meta)
                except Exception:
                    continue
        except Exception:
            metas = []

        # 最新在前
        metas.sort(key=lambda m: (m.get("created_at") or ""), reverse=True)

        self._clear()

        if not metas:
            self._show_empty("暂无提交")
            self.count_changed.emit(0)
            return

        workspace_root = Path(workspace_config.get_workspace_path())
        for meta in metas:
            it = InboxItem(meta, workspace_root)
            it.open_requested.connect(self.file_opened.emit)
            self.content_layout.addWidget(it)
            self._items.append(it)

        # refresh 后不自动发 count_changed，由 mark_as_read 控制

    def mark_as_read(self):
        """标记当前所有项目为已读，清除 badge"""
        self._read_count = self._last_count
        self.count_changed.emit(0)

    def _show_empty(self, text: str):
        self._clear()

        empty = QWidget()
        empty_layout = QVBoxLayout(empty)
        empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.setContentsMargins(SPACING_MD, 48, SPACING_MD, 48)
        empty_layout.setSpacing(SPACING_SM)

        icon_label = QLabel()
        icon_label.setPixmap(qta.icon('mdi6.inbox', color=ICON_MUTED).pixmap(32, 32))
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(icon_label)

        title = QLabel(text)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 13px; font-weight: 600;")
        empty_layout.addWidget(title)

        subtitle = QLabel("提交的文件可放入工作区 _INBOX 目录")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet(f"color: {TEXT_TERTIARY}; font-size: 12px;")
        empty_layout.addWidget(subtitle)

        self.content_layout.addWidget(empty)


class CombinedSidebar(QWidget):
    """组合侧栏 - Activity Bar + 侧栏面板"""
    file_selected = Signal(str)
    file_opened = Signal(str)
    width_changed = Signal(int)  # 通知父组件宽度变化
    
    # 面板宽度常量
    PANEL_WIDTH = SIDEBAR_WIDTH - ACTIVITY_BAR_WIDTH
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._panel_visible = True
        self._previous_panel = None
        
        self._init_ui()
    
    def _init_ui(self):
        self.setStyleSheet(f"""
            CombinedSidebar {{
                background: {BG_SECONDARY};
            }}
        """)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Activity Bar
        self.activity_bar = ActivityBar()
        self.activity_bar.add_button('mdi6.folder-outline', '资源管理器', 'explorer', 'top')
        self.activity_bar.add_button('mdi6.inbox', '收件箱', 'inbox', 'top')

        # 预留扩展位置
        # self.activity_bar.add_button('mdi6.magnify', '搜索', 'search', 'top')
        self.activity_bar.add_button('mdi6.cog-outline', '设置', 'settings', 'bottom')
        self.activity_bar.panel_changed.connect(self._on_panel_changed)
        layout.addWidget(self.activity_bar)
        
        # 面板容器
        self.panel_container = QWidget()
        self.panel_container.setFixedWidth(self.PANEL_WIDTH)
        self.panel_container.setStyleSheet(f"""
            QWidget {{
                background: {BG_SECONDARY};
                border-right: 1px solid {BORDER_DEFAULT};
            }}
        """)
        panel_layout = QVBoxLayout(self.panel_container)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(0)
        
        # 堆叠面板
        self.panel_stack = QStackedWidget()
        self.panel_stack.setStyleSheet("background: transparent; border: none;")
        
        # 资源管理器面板
        self.explorer_panel = ExplorerPanel()
        self.explorer_panel.file_selected.connect(self.file_selected.emit)
        self.explorer_panel.file_opened.connect(self.file_opened.emit)
        self.panel_stack.addWidget(self.explorer_panel)
        
        # 收件箱面板
        self.inbox_panel = InboxPanel()
        self.inbox_panel.file_opened.connect(self.file_opened.emit)
        self.inbox_panel.count_changed.connect(self._on_inbox_count_changed)
        self.panel_stack.addWidget(self.inbox_panel)

        # 后续可扩展：搜索面板、设置面板等
        # self.search_panel = SearchPanel()
        # self.panel_stack.addWidget(self.search_panel)
        
        panel_layout.addWidget(self.panel_stack)
        layout.addWidget(self.panel_container)
        
        self._update_width()
    
    def _on_hotkey_changed(self):
        """占位方法，处理快捷键变化"""
        pass

    def _on_inbox_count_changed(self, count: int):
        btn = self.activity_bar._buttons.get('inbox')
        if btn:
            btn.set_badge_count(count)

    def _on_panel_changed(self, panel_id: str):
        if panel_id == 'settings':
            # 打开设置对话框
            dialog = SettingsDialog(self)
            dialog.exec()
            
            # 对话框关闭后，重置活动面板为之前的面板（如果有的话）
            if self._previous_panel:
                self.activity_bar.set_active_panel(self._previous_panel)
            else:
                # 如果没有之前的面板，取消激活所有按钮
                for btn in self.activity_bar._buttons.values():
                    btn.set_active(False)
                self.activity_bar._current_panel = None
                self._panel_visible = False
                self.panel_container.hide()
            
            self._update_width()
            return
        
        # 处理常规面板切换
        if not panel_id:
            # 收起面板
            self._panel_visible = False
            self.panel_container.hide()
        else:
            # 展开对应面板
            self._panel_visible = True
            self.panel_container.show()
            
            if panel_id == 'explorer':
                self.panel_stack.setCurrentWidget(self.explorer_panel)
            elif panel_id == 'inbox':
                self.panel_stack.setCurrentWidget(self.inbox_panel)
                self.inbox_panel.refresh()
                # 打开收件箱时标记为已读
                self.inbox_panel.mark_as_read()

            # 后续扩展
            # elif panel_id == 'search':
            #     self.panel_stack.setCurrentWidget(self.search_panel)
        
        # 更新之前的面板（如果不是settings）
        if panel_id != 'settings':
            self._previous_panel = panel_id if panel_id else None
        
        self._update_width()
    
    def _update_width(self):
        if self._panel_visible:
            new_width = ACTIVITY_BAR_WIDTH + self.PANEL_WIDTH
        else:
            new_width = ACTIVITY_BAR_WIDTH
        self.setFixedWidth(new_width)
        self.width_changed.emit(new_width)
    
    def toggle_panel(self):
        """切换面板显示状态"""
        current = self.activity_bar.get_active_panel()
        if self._panel_visible:
            self._panel_visible = False
            self.panel_container.hide()
            for btn in self.activity_bar._buttons.values():
                btn.set_active(False)
            self.activity_bar._current_panel = None
        else:
            self._panel_visible = True
            self.panel_container.show()
            if current:
                self.activity_bar.set_active_panel(current)
            else:
                self.activity_bar.set_active_panel('explorer')
        
        self._update_width()
    
    def is_panel_visible(self) -> bool:
        return self._panel_visible
    
    def refresh(self):
        self.explorer_panel.refresh()
        if hasattr(self, 'inbox_panel'):
            self.inbox_panel.refresh()
    
    def set_current_file(self, file_path: str):
        self.explorer_panel.set_current_file(file_path)
    
    def set_current_image(self, image_data: bytes):
        """设置当前图片数据（用于企微发送）"""
        pass  # 企微功能已移除


# 保留旧的 WorkspaceSidebar 作为兼容
class WorkspaceSidebar(CombinedSidebar):
    """工作区侧栏 - 兼容旧接口"""
    visibility_changed = Signal(bool)
    
    def toggle_collapse(self):
        self.toggle_panel()
        self.visibility_changed.emit(self._panel_visible)
