"""
截图模块 - 工具栏组件
"""

import re

import qtawesome as qta
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QGraphicsDropShadowEffect,
    QButtonGroup, QLineEdit, QScrollArea, QLabel, QTextEdit, QFileDialog, QApplication
)
from PySide6.QtCore import Qt, QSize, Signal, QPoint, QTimer, QPropertyAnimation, QEasingCurve, Property, QEvent
from PySide6.QtGui import QColor, QPainter, QPixmap, QPainterPath, QFont

from .canvas import EditorCanvas
from database import get_all_records, get_image_full_path


# 预设颜色列表
PRESET_COLORS = [
    QColor(255, 50, 50),    # 红
    QColor(255, 165, 0),    # 橙
    QColor(255, 220, 0),    # 黄
    QColor(50, 205, 50),    # 绿
    QColor(0, 120, 215),    # 蓝
    QColor(148, 103, 189),  # 紫
    QColor(255, 255, 255),  # 白
    QColor(0, 0, 0),        # 黑
]


class ColorBubble(QWidget):
    """颜色选择气泡 - 在按钮下方弹出"""
    color_selected = Signal(QColor)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self._current_color = PRESET_COLORS[0]
        self._init_ui()
        self.hide()
    
    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)
        
        for color in PRESET_COLORS:
            btn = QPushButton()
            btn.setFixedSize(22, 22)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(color.name())
            # 用样式绘制圆形色块
            border = "2px solid rgba(0,0,0,0.3)" if color == QColor(255, 255, 255) else "2px solid transparent"
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {color.name()};
                    border: {border};
                    border-radius: 11px;
                }}
                QPushButton:hover {{
                    border: 2px solid rgba(0, 120, 215, 0.8);
                }}
            """)
            btn.clicked.connect(lambda checked, c=color: self._on_color_clicked(c))
            layout.addWidget(btn)
        
        self.setFixedHeight(38)
    
    def _on_color_clicked(self, color: QColor):
        self._current_color = color
        self.color_selected.emit(color)
        self.hide()
    
    def show_at(self, global_pos: QPoint):
        """在指定全局位置显示"""
        self.adjustSize()
        # 居中于触发点
        x = global_pos.x() - self.width() // 2
        y = global_pos.y()
        self.move(x, y)
        self.show()
        self.raise_()
    
    def paintEvent(self, event):
        """绘制气泡背景"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(255, 255, 255, 240))
        painter.drawRoundedRect(self.rect(), 12, 12)
    
    def focusOutEvent(self, event):
        self.hide()
        super().focusOutEvent(event)


class ColorIndicatorButton(QPushButton):
    """颜色指示器按钮 - 显示当前颜色的小圆点"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._color = PRESET_COLORS[0]
        self.setFixedSize(36, 36)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("标记颜色")
    
    def set_color(self, color: QColor):
        self._color = color
        self.update()
    
    def get_color(self) -> QColor:
        return self._color
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # 绘制中心圆形色块
        center = self.rect().center()
        radius = 8
        
        # 白色底色圈（区分白色标记色）
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(220, 220, 220))
        painter.drawEllipse(center, radius + 1, radius + 1)
        
        # 颜色圆
        painter.setBrush(self._color)
        painter.drawEllipse(center, radius, radius)


class EditorToolbar(QWidget):
    """左侧工具栏 - 浅色毛玻璃风格"""
    tool_changed = Signal(int)
    save_clicked = Signal()
    copy_clicked = Signal()
    ai_clicked = Signal()
    archive_clicked = Signal()
    undo_clicked = Signal()
    assign_clicked = Signal()  # 新增：分配反馈
    color_changed = Signal(QColor)  # 标记颜色变化
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._color_bubble = None
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 12, 8, 12)
        layout.setSpacing(4)
        
        self.button_group = QButtonGroup(self)
        self.button_group.setExclusive(True)
        
        tools = [
            ('mdi6.cursor-default', "选择/移动", EditorCanvas.TOOL_SELECT),
            ('mdi6.format-list-numbered', "序号点", EditorCanvas.TOOL_NUMBER),
            ('mdi6.vector-rectangle', "矩形框", EditorCanvas.TOOL_RECT),
            ('mdi6.arrow-right', "箭头", EditorCanvas.TOOL_ARROW),
            ('mdi6.brush', "画笔", EditorCanvas.TOOL_FREEHAND),
            ('mdi6.format-text', "文字", EditorCanvas.TOOL_TEXT),
            ('mdi6.eraser', "橡皮擦", EditorCanvas.TOOL_ERASER),
        ]
        
        for icon_name, tooltip, tool_id in tools:
            btn = QPushButton()
            btn.setIcon(qta.icon(icon_name, color='#555555'))
            btn.setIconSize(QSize(18, 18))
            btn.setFixedSize(36, 36)
            btn.setCheckable(True)
            btn.setToolTip(tooltip)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setProperty("tool_id", tool_id)
            btn.setProperty("icon_name", icon_name)
            btn.clicked.connect(lambda checked, tid=tool_id: self.tool_changed.emit(tid))
            self.button_group.addButton(btn, tool_id)
            layout.addWidget(btn, alignment=Qt.AlignmentFlag.AlignHCenter)
        
        self.button_group.button(EditorCanvas.TOOL_SELECT).setChecked(True)
        
        # 分隔线
        separator1 = QWidget()
        separator1.setFixedSize(32, 1)
        separator1.setStyleSheet("background-color: rgba(0, 0, 0, 0.1);")
        layout.addWidget(separator1, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addSpacing(2)
        
        # 颜色按钮
        self.btn_color = ColorIndicatorButton()
        self.btn_color.clicked.connect(self._on_color_btn_clicked)
        layout.addWidget(self.btn_color, alignment=Qt.AlignmentFlag.AlignHCenter)
        
        # 撤销按钮
        self.btn_undo = QPushButton()
        self.btn_undo.setIcon(qta.icon('mdi6.undo', color='#555555'))
        self.btn_undo.setIconSize(QSize(18, 18))
        self.btn_undo.setFixedSize(36, 36)
        self.btn_undo.setCheckable(False)
        self.btn_undo.setToolTip("撤销 (Ctrl+Z)")
        self.btn_undo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_undo.clicked.connect(self.undo_clicked.emit)
        self.btn_undo.setObjectName("btn_undo")
        layout.addWidget(self.btn_undo, alignment=Qt.AlignmentFlag.AlignHCenter)
        
        layout.addStretch()
        
        # 分隔线
        separator = QWidget()
        separator.setFixedSize(32, 1)
        separator.setStyleSheet("background-color: rgba(0, 0, 0, 0.1);")
        layout.addWidget(separator, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addSpacing(4)
        
        action_buttons = [
            ('mdi6.content-copy', "复制到剪贴板", self.copy_clicked, "action_btn"),
            ('mdi6.content-save', "保存为文件", self.save_clicked, "action_btn"),
            ('mdi6.auto-fix', "AI 分析", self.ai_clicked, "action_btn"),
            ('mdi6.send', "分配反馈", self.assign_clicked, "btn_assign"),
            ('mdi6.inbox-arrow-down', "归档到历史记录", self.archive_clicked, "btn_archive"),
        ]
        
        for icon_name, tooltip, signal, obj_name in action_buttons:
            btn = QPushButton()
            btn.setIcon(qta.icon(icon_name, color='#555555'))
            btn.setIconSize(QSize(18, 18))
            btn.setFixedSize(36, 36)
            btn.setCheckable(False)
            btn.setToolTip(tooltip)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(signal.emit)
            btn.setObjectName(obj_name)
            if obj_name == "btn_archive":
                self.btn_archive = btn
            elif obj_name == "btn_assign":
                self.btn_assign = btn
            layout.addWidget(btn, alignment=Qt.AlignmentFlag.AlignHCenter)
        
        self.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
                border-radius: 18px;
            }
            QPushButton:hover {
                background-color: rgba(0, 0, 0, 0.08);
            }
            QPushButton:pressed {
                background-color: rgba(0, 0, 0, 0.12);
            }
            QPushButton:checked {
                background-color: rgba(0, 120, 215, 0.15);
            }
            QPushButton#btn_archive:hover {
                background-color: rgba(46, 125, 50, 0.15);
            }
        """)
        self.setFixedWidth(52)
    
    def paintEvent(self, event):
        """绘制圆角白色半透明背景"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(255, 255, 255, 230))
        painter.drawRoundedRect(self.rect(), 16, 16)
    
    def _on_color_btn_clicked(self):
        """点击颜色按钮 - 在按钮右侧弹出气泡"""
        if self._color_bubble is None:
            self._color_bubble = ColorBubble()
            self._color_bubble.color_selected.connect(self._on_color_selected)
        
        if self._color_bubble.isVisible():
            self._color_bubble.hide()
            return
        
        # 计算按钮右侧的全局位置
        btn_pos = self.btn_color.mapToGlobal(QPoint(self.btn_color.width() + 4, 0))
        # 垂直居中于按钮
        btn_pos.setY(btn_pos.y() + self.btn_color.height() // 2 - 19)
        self._color_bubble.move(btn_pos)
        self._color_bubble.show()
        self._color_bubble.raise_()
    
    def _on_color_selected(self, color: QColor):
        """颜色被选中"""
        self.btn_color.set_color(color)
        self.color_changed.emit(color)


# ─── 下拉面板自绘组件（VS Code Command Palette 风格）───

class _DropdownItemButton(QPushButton):
    """自绘下拉选项按钮 — 左侧色条 + 文字，hover/高亮全部 paintEvent 绘制"""
    
    _COLOR_MAP = {
        "text": QColor(99, 102, 241),
        "image": QColor(236, 72, 153),
    }
    
    def __init__(self, text: str, prompt_type: str = "text", parent=None):
        super().__init__(parent)
        self.setText(text)
        self._prompt_type = prompt_type
        self._highlighted = False
        self._hovered = False
        self._accent = self._COLOR_MAP.get(prompt_type, self._COLOR_MAP["text"])
        
        self.setFixedHeight(36)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        # 清空所有 QSS，完全靠 paintEvent
        self.setStyleSheet("background: transparent; border: none;")
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
    
    def setHighlighted(self, on: bool):
        self._highlighted = on
        self.update()
    
    def enterEvent(self, event):
        self._hovered = True
        self.update()
        super().enterEvent(event)
    
    def leaveEvent(self, event):
        self._hovered = False
        self.update()
        super().leaveEvent(event)
    
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        rect = self.rect().adjusted(2, 1, -2, -1)
        
        # 背景
        if self._highlighted:
            bg = QColor(self._accent)
            bg.setAlpha(20)
            p.setBrush(bg)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(rect, 6, 6)
        elif self._hovered:
            p.setBrush(QColor(0, 0, 0, 13))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(rect, 6, 6)
        
        # 左侧色条
        bar_rect = rect.adjusted(4, 8, 0, -8)
        bar_rect.setWidth(3)
        bar_color = QColor(self._accent)
        bar_color.setAlpha(180 if self._highlighted else 100)
        p.setBrush(bar_color)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(bar_rect, 1.5, 1.5)
        
        # 文字
        text_color = QColor(self._accent).darker(130) if self._highlighted else QColor("#4b5563")
        p.setPen(text_color)
        font = QFont()
        font.setPixelSize(13)
        if self._highlighted:
            font.setWeight(QFont.Weight.Medium)
        p.setFont(font)
        text_rect = rect.adjusted(14, 0, -8, 0)
        p.drawText(text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.text())
        
        p.end()


class _DropdownPanel(QWidget):
    """自绘圆角阴影下拉面板"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        self._margin = 8  # 阴影留白
        self._radius = 12
        
        # 外层布局 — 留出阴影空间
        self._outer_layout = QVBoxLayout(self)
        self._outer_layout.setContentsMargins(self._margin, self._margin, self._margin, self._margin + 4)
        self._outer_layout.setSpacing(0)
        
        # 滚动区域
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll.setMaximumHeight(210)
        self._scroll.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QScrollArea > QWidget > QWidget { background: transparent; }
            QScrollBar:vertical { background: transparent; width: 4px; margin: 4px 1px; }
            QScrollBar::handle:vertical { background: rgba(0,0,0,0.10); border-radius: 2px; min-height: 16px; }
            QScrollBar::handle:vertical:hover { background: rgba(0,0,0,0.20); }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
        """)
        self._outer_layout.addWidget(self._scroll)
    
    def setContentLayout(self, layout):
        """设置内容布局"""
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        container.setLayout(layout)
        self._scroll.setWidget(container)
    
    def paintEvent(self, event):
        """自绘圆角背景 + 阴影"""
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # 内容区域（去掉阴影留白）
        content_rect = self.rect().adjusted(
            self._margin, self._margin, -self._margin, -self._margin
        )
        
        # 绘制阴影（多层半透明椭圆模拟）
        for i in range(4):
            shadow_color = QColor(0, 0, 0, 12 - i * 3)
            p.setBrush(shadow_color)
            p.setPen(Qt.PenStyle.NoPen)
            sr = content_rect.adjusted(-i * 2, -i + 2, i * 2, i * 2 + 2)
            p.drawRoundedRect(sr, self._radius + i, self._radius + i)
        
        # 绘制白色背景
        p.setBrush(QColor(255, 255, 255, 245))
        p.setPen(QColor(0, 0, 0, 18))
        p.drawRoundedRect(content_rect, self._radius, self._radius)
        
        p.end()


class ScreenshotAICapsule(QWidget):
    """AI 胶囊 - 初始为小按钮，点击后向左延伸成带输入框的对话框"""
    clicked = Signal()  # 点击 AI 按钮（展开时）
    send_clicked = Signal(str, str)  # 发送(输入内容, prompt_type)
    prompt_selected = Signal(str)  # 选择 Prompt 模板
    width_changed = Signal()  # 宽度变化信号，用于同步位置
    
    # 尺寸常量（与 ScreenshotToolbar 对齐）
    COLLAPSED_WIDTH = 48
    EXPANDED_WIDTH = 460
    
    # 类级别缓存 prompts
    _cached_prompts = None
    
    # 预定义样式字符串，避免重复创建
    _STYLE_AI_BTN_TEXT = """
        QPushButton#btn_ai_main {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 rgba(99, 102, 241, 0.9),
                stop:1 rgba(139, 92, 246, 0.9));
            border-radius: 18px;
        }
        QPushButton#btn_ai_main:hover {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 rgba(79, 82, 221, 0.95),
                stop:1 rgba(119, 72, 226, 0.95));
        }
    """
    _STYLE_AI_BTN_IMAGE = """
        QPushButton#btn_ai_main {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 rgba(236, 72, 153, 0.9),
                stop:1 rgba(244, 114, 182, 0.9));
            border-radius: 18px;
        }
        QPushButton#btn_ai_main:hover {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 rgba(216, 52, 133, 0.95),
                stop:1 rgba(224, 94, 162, 0.95));
        }
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ai_capsule")
        
        self._is_expanded = False
        self._height = 48
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
        # 从缓存或数据库加载 Prompt 模板
        self._prompts = self._load_prompts()
        self._selected_prompt_type = "text"  # 当前选中模板的类型
        
        self._setup_animation()
        self._init_ui()
        
        # 初始隐藏
        self.hide()
    
    @classmethod
    def _load_prompts(cls):
        """加载 Prompt 模板（带缓存）"""
        if cls._cached_prompts is not None:
            return cls._cached_prompts
        
        from database import get_all_prompts
        prompts = []
        try:
            db_prompts = get_all_prompts()
            for p in db_prompts:
                prompts.append((p["title"], p["content"], p.get("prompt_type", "text")))
        except Exception:
            pass
        if not prompts:
            prompts = [("默认", "请详细分析这张图片的内容。", "text")]
        cls._cached_prompts = prompts
        return prompts
    
    @classmethod
    def invalidate_prompts_cache(cls):
        """清除 prompts 缓存（在编辑 prompts 后调用）"""
        cls._cached_prompts = None
    
    def _setup_animation(self):
        """设置动画 - 使用单一 fixedWidth 动画避免双属性重绘"""
        self._width_anim = QPropertyAnimation(self, b"fixedWidth")
        self._width_anim.setDuration(220)
        self._width_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._width_anim.valueChanged.connect(lambda _: self.width_changed.emit())
        self._width_anim.finished.connect(self._on_anim_finished)
    
    def _get_fixed_width(self):
        return self.width()
    
    def _set_fixed_width(self, w):
        self.setFixedWidth(int(w))
    
    fixedWidth = Property(int, _get_fixed_width, _set_fixed_width)
    
    def _init_ui(self):
        self._main_layout = QHBoxLayout(self)
        self._main_layout.setContentsMargins(6, 6, 6, 6)
        self._main_layout.setSpacing(4)
        
        # AI 按钮（收起时点击展开，展开时点击发送）
        self.btn_ai = QPushButton()
        self.btn_ai.setIcon(qta.icon('mdi6.creation', color='#ffffff'))
        self.btn_ai.setIconSize(QSize(20, 20))
        self.btn_ai.setFixedSize(36, 36)
        self.btn_ai.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_ai.setToolTip("AI 分析")
        self.btn_ai.setObjectName("btn_ai_main")
        self.btn_ai.clicked.connect(self._on_ai_clicked)
        self._main_layout.addWidget(self.btn_ai)
        
        # 展开后的输入框容器（使用堆叠布局放置按钮在输入框内）
        self.expanded_container = QWidget()
        self.expanded_layout = QHBoxLayout(self.expanded_container)
        self.expanded_layout.setContentsMargins(0, 0, 0, 0)
        self.expanded_layout.setSpacing(0)
        
        # 输入框容器（用于放置输入框和内部按钮）
        self.input_container = QWidget()
        self.input_container.setObjectName("input_container")
        input_container_layout = QHBoxLayout(self.input_container)
        input_container_layout.setContentsMargins(12, 4, 4, 4)
        input_container_layout.setSpacing(4)
        
        # 输入框
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("输入 / 选择模板...")
        self.input_field.setObjectName("ai_input")
        self.input_field.returnPressed.connect(self._on_send)
        self.input_field.textChanged.connect(self._on_text_changed)
        input_container_layout.addWidget(self.input_field, 1)
        
        # Enter 键提示标签
        self._enter_hint = QLabel("Enter 键发送", self.input_field)
        self._enter_hint.setStyleSheet("color: rgba(0, 0, 0, 0.25); font-size: 11px; background: transparent;")
        self._enter_hint.setFixedHeight(self.input_field.sizeHint().height())
        self._enter_hint.hide()
        self.input_field.textChanged.connect(self._update_enter_hint)
        
        # 模式切换按钮（横条胶囊形状，放在输入框内右侧）
        self.btn_mode = QPushButton("文本")
        self.btn_mode.setFixedSize(48, 24)
        self.btn_mode.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_mode.setObjectName("btn_mode_text")
        self.btn_mode.setToolTip("当前：文本分析\n点击切换到图片生成")
        self.btn_mode.clicked.connect(self._toggle_mode)
        input_container_layout.addWidget(self.btn_mode)
        
        self.expanded_layout.addWidget(self.input_container, 1)
        
        self.expanded_container.hide()
        self._main_layout.addWidget(self.expanded_container)
        
        # ─── 下拉列表（自绘圆角悬浮卡片）───
        self._dropdown = _DropdownPanel(self.parent() if self.parent() else self)
        self._dropdown.hide()
        
        dropdown_inner_layout = QVBoxLayout()
        dropdown_inner_layout.setContentsMargins(6, 6, 6, 6)
        dropdown_inner_layout.setSpacing(2)
        
        self._template_buttons = []
        for name, content, prompt_type in self._prompts:
            btn = _DropdownItemButton(name, prompt_type)
            btn.clicked.connect(lambda checked, n=name, c=content, t=prompt_type: self._on_template_clicked(n, c, t))
            dropdown_inner_layout.addWidget(btn)
            self._template_buttons.append((name, btn, prompt_type))
        
        self._dropdown.setContentLayout(dropdown_inner_layout)
        
        self.setStyleSheet("""
            ScreenshotAICapsule {
                background-color: rgba(255, 255, 255, 240);
                border-radius: 24px;
            }
            QPushButton {
                background-color: transparent;
                border: none;
                border-radius: 16px;
            }
            QPushButton:hover {
                background-color: rgba(0, 0, 0, 0.08);
            }
            QPushButton:pressed {
                background-color: rgba(0, 0, 0, 0.12);
            }
            QPushButton#btn_ai_main {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(99, 102, 241, 0.9),
                    stop:1 rgba(139, 92, 246, 0.9));
                border-radius: 18px;
            }
            QPushButton#btn_ai_main:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(79, 82, 221, 0.95),
                    stop:1 rgba(119, 72, 226, 0.95));
            }
            QWidget#input_container {
                background-color: rgba(255, 255, 255, 0.9);
                border: 1px solid rgba(0, 0, 0, 0.1);
                border-radius: 16px;
            }
            QWidget#input_container:focus-within {
                border: 1px solid rgba(99, 102, 241, 0.5);
            }
            QLineEdit#ai_input {
                background-color: transparent;
                border: none;
                font-size: 13px;
                color: #333;
            }
            QLineEdit#ai_input::placeholder {
                color: #999;
            }
            QPushButton#btn_mode_text {
                background-color: rgba(99, 102, 241, 0.15);
                border-radius: 12px;
                font-size: 11px;
                font-weight: 500;
                color: rgba(99, 102, 241, 0.9);
                padding: 0 8px;
            }
            QPushButton#btn_mode_text:hover {
                background-color: rgba(99, 102, 241, 0.25);
            }
            QPushButton#btn_mode_image {
                background-color: rgba(236, 72, 153, 0.15);
                border-radius: 12px;
                font-size: 11px;
                font-weight: 500;
                color: rgba(236, 72, 153, 0.9);
                padding: 0 8px;
            }
            QPushButton#btn_mode_image:hover {
                background-color: rgba(236, 72, 153, 0.25);
            }
        """)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        
        self._dropdown_selected_index = -1
        self.input_field.installEventFilter(self)
        
        self.setFixedHeight(self._height)
        self.setFixedWidth(self.COLLAPSED_WIDTH)
    
    def _on_text_changed(self, text: str):
        """输入框文本变化 - 输入 / 时显示模板列表"""
        self._dropdown_selected_index = -1
        # 检查是否以 / 开头或包含 /
        if '/' in text:
            # 提取 / 后面的搜索词进行过滤
            slash_idx = text.rfind('/')
            search_term = text[slash_idx + 1:].lower()
            
            # 过滤并显示匹配的模板
            visible_count = 0
            for name, btn, ptype in self._template_buttons:
                if search_term == '' or search_term in name.lower():
                    btn.show()
                    visible_count += 1
                else:
                    btn.hide()
            
            if visible_count > 0:
                self._update_dropdown_position()
            else:
                self._dropdown.hide()
        else:
            self._dropdown.hide()
    
    def eventFilter(self, obj, event):
        """拦截输入框的键盘事件，支持上下键选择下拉列表"""
        if obj is self.input_field and event.type() == QEvent.Type.KeyPress:
            if not self._dropdown.isVisible():
                return super().eventFilter(obj, event)
            
            visible_items = [(name, btn, ptype) for name, btn, ptype in self._template_buttons if btn.isVisible()]
            if not visible_items:
                return super().eventFilter(obj, event)
            
            key = event.key()
            if key == Qt.Key.Key_Down:
                self._dropdown_selected_index = min(self._dropdown_selected_index + 1, len(visible_items) - 1)
                self._update_dropdown_highlight(visible_items)
                return True
            elif key == Qt.Key.Key_Up:
                self._dropdown_selected_index = max(self._dropdown_selected_index - 1, 0)
                self._update_dropdown_highlight(visible_items)
                return True
            elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if 0 <= self._dropdown_selected_index < len(visible_items):
                    visible_items[self._dropdown_selected_index][1].click()
                    return True
            elif key == Qt.Key.Key_Escape:
                self._dropdown.hide()
                self._dropdown_selected_index = -1
                return True
        return super().eventFilter(obj, event)
    
    def _update_dropdown_highlight(self, visible_items):
        """更新下拉列表中当前选中项的高亮"""
        for i, (name, btn, ptype) in enumerate(visible_items):
            btn.setHighlighted(i == self._dropdown_selected_index)
    
    def _toggle_mode(self):
        """切换模式（文本/图片）"""
        if self._selected_prompt_type == "text":
            self._set_mode("image")
        else:
            self._set_mode("text")
    
    def _set_mode(self, mode: str):
        """设置模式并更新 UI（使用预定义样式）"""
        self._selected_prompt_type = mode
        if mode == "text":
            self.btn_mode.setText("文本")
            self.btn_mode.setObjectName("btn_mode_text")
            self.btn_mode.setToolTip("当前：文本分析\n点击切换到图片生成")
            self.btn_ai.setIcon(qta.icon('mdi6.creation', color='#ffffff'))
            self.btn_ai.setStyleSheet(self._STYLE_AI_BTN_TEXT)
        else:
            self.btn_mode.setText("图片")
            self.btn_mode.setObjectName("btn_mode_image")
            self.btn_mode.setToolTip("当前：图片生成\n点击切换到文本分析")
            self.btn_ai.setIcon(qta.icon('mdi6.palette-outline', color='#ffffff'))
            self.btn_ai.setStyleSheet(self._STYLE_AI_BTN_IMAGE)
        # 刷新模式按钮样式
        self.btn_mode.style().unpolish(self.btn_mode)
        self.btn_mode.style().polish(self.btn_mode)
    
    def _on_template_clicked(self, name: str, content: str, prompt_type: str):
        """点击模板 - 替换 / 及其后的内容为 [模板名]，并自动切换模式"""
        current_text = self.input_field.text()
        
        # 记录选中模板的内容
        self._selected_prompt_content = content
        
        # 自动切换到模板对应的模式
        self._set_mode(prompt_type)
        
        # 找到 / 的位置并替换
        if '/' in current_text:
            slash_idx = current_text.rfind('/')
            new_text = current_text[:slash_idx] + f"[{name}] "
        else:
            new_text = f"[{name}] " + current_text
        
        self.input_field.setText(new_text)
        self.input_field.setFocus()
        self.input_field.setCursorPosition(len(new_text))
        self._dropdown.hide()
    
    def _update_dropdown_position(self):
        """更新下拉列表位置 - 智能判断向上或向下展开"""
        if not self._is_expanded:
            self._dropdown.hide()
            return
        
        # 获取屏幕信息
        from PySide6.QtGui import QGuiApplication
        screen = QGuiApplication.screenAt(self.mapToGlobal(QPoint(0, 0)))
        if screen:
            screen_rect = screen.geometry()
        else:
            screen_rect = QGuiApplication.primaryScreen().geometry()
        
        # 计算下拉框高度
        self._dropdown.adjustSize()
        dropdown_height = self._dropdown.height()
        
        # 默认向下展开的位置
        container_global_pos = self.input_container.mapToGlobal(QPoint(0, self.input_container.height() + 4))
        
        # 检查向下展开是否会超出屏幕底部
        if container_global_pos.y() + dropdown_height > screen_rect.bottom() - 10:
            # 空间不足，改为向上展开
            container_global_pos = self.input_container.mapToGlobal(QPoint(0, -dropdown_height - 4))
        
        self._dropdown.move(container_global_pos)
        self._dropdown.setFixedWidth(self.input_container.width())
        self._dropdown.show()
        self._dropdown.raise_()

    
    def _on_ai_clicked(self):
        if not self._is_expanded:
            # 收起状态：展开对话框
            self.expand()
            self.clicked.emit()
        else:
            # 展开状态：发送
            self._on_send()
    
    def expand(self):
        """展开成对话框"""
        if self._is_expanded:
            return
        self._is_expanded = True
        self.setCursor(Qt.CursorShape.ArrowCursor)
        
        self.expanded_container.show()
        
        self._width_anim.stop()
        self._width_anim.setStartValue(self.width())
        self._width_anim.setEndValue(self.EXPANDED_WIDTH)
        self._width_anim.start()
    
    def collapse(self):
        """收起成小按钮"""
        if not self._is_expanded:
            return
        self._is_expanded = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
        # 隐藏下拉列表
        self._dropdown.hide()
        
        self._width_anim.stop()
        self._width_anim.setStartValue(self.width())
        self._width_anim.setEndValue(self.COLLAPSED_WIDTH)
        self._width_anim.start()
    
    def _on_anim_finished(self):
        if not self._is_expanded:
            self.expanded_container.hide()
            self.input_field.clear()
        else:
            # 展开完成后聚焦输入框（不自动显示下拉列表，输入 / 时才显示）
            self.input_field.setFocus()
    
    def _on_send(self):
        """发送输入内容"""
        text = self.input_field.text().strip()
        if text:
            match = re.search(r'\[(.+?)\]', text)
            
            if match:
                template_name = match.group(1)
                # 查找对应模板的 content
                prompt_content = None
                for name, content, ptype in self._prompts:
                    if name == template_name:
                        prompt_content = content
                        break
                
                if prompt_content:
                    # 提取 [] 之外的额外指令
                    extra_text = re.sub(r'\[.+?\]\s*', '', text).strip()
                    if extra_text:
                        final_prompt = f"{prompt_content}\n\n用户补充要求：{extra_text}"
                    else:
                        final_prompt = prompt_content
                    # 使用当前模式（已通过 _set_mode 设置）
                    self.send_clicked.emit(final_prompt, self._selected_prompt_type)
                else:
                    # 模板不存在，当作普通文本，使用当前模式
                    self.send_clicked.emit(text, self._selected_prompt_type)
            else:
                # 没有选择模板，使用当前模式
                self.send_clicked.emit(text, self._selected_prompt_type)
            
            self.input_field.clear()
            # 不重置模式，保持用户选择
    
    def _update_enter_hint(self, text: str):
        """输入框有文字时显示 Enter 键发送提示"""
        if text.strip():
            self._enter_hint.adjustSize()
            x = self.input_field.width() - self._enter_hint.width() - 60
            y = (self.input_field.height() - self._enter_hint.height()) // 2
            self._enter_hint.move(max(0, x), y)
            self._enter_hint.show()
        else:
            self._enter_hint.hide()
    
    def is_expanded(self) -> bool:
        return self._is_expanded

    def mousePressEvent(self, event):
        """收缩状态下扩大点击区域：容器任意位置点击等同于点击 AI 按钮；
        展开状态下也拦截事件，防止穿透到底层 overlay"""
        if not self._is_expanded and event.button() == Qt.MouseButton.LeftButton:
            # 收缩状态是圆形，忽略圆角外的四角区域点击
            center = self.rect().center()
            dx = event.position().x() - center.x()
            dy = event.position().y() - center.y()
            radius = min(self.width(), self.height()) / 2
            if dx * dx + dy * dy > radius * radius:
                event.ignore()
                return
            self.btn_ai.click()
            return
        event.accept()  # 展开状态下也消费事件，防止穿透到 overlay


class ScreenshotToolbar(QWidget):
    """工具栏 - 支持快速标记，支持展开/收缩"""
    expand_requested = Signal()  # 请求展开信号
    mark_tool_changed = Signal(str)  # 标记工具切换信号: 'none', 'arrow', 'freehand', 'text'
    color_changed = Signal(QColor)  # 标记颜色变化
    width_changed = Signal()  # 宽度变化信号，用于同步位置
    
    # 尺寸常量
    EXPANDED_WIDTH = 460
    COLLAPSED_WIDTH = 48
    
    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("toolbar")
        
        self._is_collapsed = False
        self._height = 48
        self._current_mark_tool = 'none'
        self._color_bubble = None
        
        self._setup_animation()
        self.init_ui()

    def _setup_animation(self):
        """设置动画 - 使用单一 fixedWidth 动画避免双属性重绘"""
        self._width_anim = QPropertyAnimation(self, b"toolbarFixedWidth")
        self._width_anim.setDuration(220)
        self._width_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._width_anim.valueChanged.connect(lambda _: self.width_changed.emit())
    
    def _get_toolbar_fixed_width(self):
        return self.width()
    
    def _set_toolbar_fixed_width(self, w):
        self.setFixedWidth(int(w))
    
    toolbarFixedWidth = Property(int, _get_toolbar_fixed_width, _set_toolbar_fixed_width)

    def init_ui(self):
        self._main_layout = QHBoxLayout(self)
        self._main_layout.setContentsMargins(6, 6, 6, 6)
        self._main_layout.setSpacing(4)
        
        # 收缩状态的展开按钮
        self.btn_expand = QPushButton()
        self.btn_expand.setIcon(qta.icon('mdi6.tools', color='#555555'))
        self.btn_expand.setIconSize(QSize(20, 20))
        self.btn_expand.setFixedSize(36, 36)
        self.btn_expand.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_expand.setToolTip("展开工具栏")
        self.btn_expand.clicked.connect(self._on_expand_clicked)
        self.btn_expand.hide()
        self._main_layout.addWidget(self.btn_expand)
        
        # 工具按钮容器
        self.buttons_container = QWidget()
        self.buttons_layout = QHBoxLayout(self.buttons_container)
        self.buttons_layout.setContentsMargins(0, 0, 0, 0)
        self.buttons_layout.setSpacing(4)

        # 操作按钮（复制放最左侧）
        buttons_left = [
            ('mdi6.content-copy', "复制到剪贴板", "btn_confirm", self.parent().finish_screenshot),
        ]
        
        for icon_name, tooltip, obj_name, callback in buttons_left:
            btn = QPushButton()
            btn.setIcon(qta.icon(icon_name, color='#555555'))
            btn.setIconSize(QSize(18, 18))
            btn.setFixedSize(36, 36)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(tooltip)
            btn.setObjectName(obj_name)
            btn.clicked.connect(callback)
            self.buttons_layout.addWidget(btn)

        # 快速标记工具按钮（可切换状态）
        self.mark_buttons = {}
        mark_tools = [
            ('mdi6.vector-rectangle', "矩形框 (R)", 'rect'),
            ('mdi6.draw', "涂鸦 (D)", 'freehand'),
            ('mdi6.format-text', "文字 (T)", 'text'),
        ]
        
        for icon_name, tooltip, tool_id in mark_tools:
            btn = QPushButton()
            btn.setIcon(qta.icon(icon_name, color='#555555'))
            btn.setIconSize(QSize(18, 18))
            btn.setFixedSize(36, 36)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(tooltip)
            btn.setObjectName(f'btn_mark_{tool_id}')
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked, t=tool_id: self._on_mark_tool_clicked(t))
            self.mark_buttons[tool_id] = btn
            self.buttons_layout.addWidget(btn)

        # 颜色按钮（紧跟标记工具后面）
        self.btn_color = ColorIndicatorButton()
        self.btn_color.clicked.connect(self._on_color_btn_clicked)
        self.buttons_layout.addWidget(self.btn_color)

        # 其他操作按钮
        buttons_right = [
            ('mdi6.content-save', "保存文件", "btn_save", self.parent().save_screenshot),
            ('mdi6.text-recognition', "OCR 文字识别", "btn_ocr", self.parent().ocr_screenshot),
            ('mdi6.pin', "屏幕贴图", "btn_pin", self.parent().trigger_pin_action),
            ('mdi6.inbox-arrow-down', "快速归档", "btn_archive", self.parent().quick_archive),
            ('mdi6.pencil-outline', "编辑器", "btn_edit", self.parent().open_editor),
            ('mdi6.close', "取消", "btn_close", self.parent().close)
        ]

        for icon_name, tooltip, obj_name, callback in buttons_right:
            btn = QPushButton()
            btn.setIcon(qta.icon(icon_name, color='#555555'))
            btn.setIconSize(QSize(18, 18))
            btn.setFixedSize(36, 36)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(tooltip)
            btn.setObjectName(obj_name)
            btn.clicked.connect(callback)
            self.buttons_layout.addWidget(btn)
        
        self._main_layout.addWidget(self.buttons_container)

        self.setStyleSheet("""
            ScreenshotToolbar {
                background-color: rgba(255, 255, 255, 230);
                border-radius: 24px;
            }
            QPushButton {
                background-color: transparent;
                border: none;
                border-radius: 18px;
            }
            QPushButton:hover {
                background-color: rgba(0, 0, 0, 0.08);
            }
            QPushButton:pressed {
                background-color: rgba(0, 0, 0, 0.12);
            }
            QPushButton:checked {
                background-color: rgba(0, 120, 215, 0.2);
            }
        """)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(16)
        shadow.setColor(QColor(0, 0, 0, 35))
        shadow.setOffset(0, 3)
        self.setGraphicsEffect(shadow)
        
        self.setFixedHeight(self._height)
        self.setFixedWidth(self.EXPANDED_WIDTH)
        self.hide()
    
    def _on_mark_tool_clicked(self, tool_id: str):
        """标记工具按钮被点击"""
        # 如果点击的是当前工具，则取消选中
        if self._current_mark_tool == tool_id:
            self._current_mark_tool = 'none'
            self.mark_buttons[tool_id].setChecked(False)
        else:
            # 取消其他工具的选中状态
            for tid, btn in self.mark_buttons.items():
                btn.setChecked(tid == tool_id)
            self._current_mark_tool = tool_id
        
        self.mark_tool_changed.emit(self._current_mark_tool)
    
    def set_mark_tool(self, tool_id: str):
        """设置当前标记工具"""
        self._current_mark_tool = tool_id
        for tid, btn in self.mark_buttons.items():
            btn.setChecked(tid == tool_id)
    
    def get_mark_tool(self) -> str:
        return self._current_mark_tool
    
    def _on_color_btn_clicked(self):
        """点击颜色按钮 - 在按钮下方弹出气泡"""
        if self._color_bubble is None:
            self._color_bubble = ColorBubble()
            self._color_bubble.color_selected.connect(self._on_color_selected)
        
        if self._color_bubble.isVisible():
            self._color_bubble.hide()
            return
        
        # 计算按钮下方的全局位置
        btn_global = self.btn_color.mapToGlobal(QPoint(0, 0))
        bubble_x = btn_global.x() + self.btn_color.width() // 2
        bubble_y = btn_global.y() + self.btn_color.height() + 6
        self._color_bubble.show_at(QPoint(bubble_x, bubble_y))
    
    def _on_color_selected(self, color: QColor):
        """颜色被选中"""
        self.btn_color.set_color(color)
        self.color_changed.emit(color)
    
    def collapse(self):
        """收缩成小胶囊"""
        if self._is_collapsed:
            return
        self._is_collapsed = True
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
        self.buttons_container.hide()
        self.btn_expand.show()
        
        self._width_anim.stop()
        self._width_anim.setStartValue(self.width())
        self._width_anim.setEndValue(self.COLLAPSED_WIDTH)
        self._width_anim.start()
    
    def expand(self):
        """展开成长条"""
        if not self._is_collapsed:
            return
        self._is_collapsed = False
        self.setCursor(Qt.CursorShape.ArrowCursor)
        
        self.btn_expand.hide()
        self.buttons_container.show()
        
        self._width_anim.stop()
        self._width_anim.setStartValue(self.width())
        self._width_anim.setEndValue(self.EXPANDED_WIDTH)
        self._width_anim.start()
    
    def _on_expand_clicked(self):
        """点击展开按钮"""
        self.expand_requested.emit()
        self.expand()
    
    def is_collapsed(self) -> bool:
        return self._is_collapsed

    def mousePressEvent(self, event):
        """收缩状态下扩大点击区域：容器任意位置点击等同于点击展开按钮；
        展开状态下也拦截事件，防止穿透到底层 overlay"""
        if self._is_collapsed and event.button() == Qt.MouseButton.LeftButton:
            # 收缩状态是圆形，忽略圆角外的四角区域点击
            center = self.rect().center()
            dx = event.position().x() - center.x()
            dy = event.position().y() - center.y()
            radius = min(self.width(), self.height()) / 2
            if dx * dx + dy * dy > radius * radius:
                event.ignore()
                return
            self.btn_expand.click()
            return
        event.accept()  # 展开状态下也消费事件，防止穿透到 overlay


class NumberAnnotationPanel(QWidget):
    """序号注释侧栏 - 自动弹出"""
    
    PANEL_WIDTH = 260
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._annotations: dict[int, str] = {}  # {序号: 注释文字}
        self._images: dict[int, QPixmap] = {}  # {序号: 附加图片}
        self._text_edits: dict[int, QLineEdit] = {}  # {序号: 输入框}
        self._image_labels: dict[int, QLabel] = {}  # {序号: 图片预览标签}
        self._visible_count = 0
        self.init_ui()
        self.hide()  # 默认隐藏
    
    def init_ui(self):
        self.setFixedWidth(self.PANEL_WIDTH)
        self.setObjectName("annotation_panel")
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 14, 12, 14)
        layout.setSpacing(12)
        
        # 滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical {
                background: transparent;
                width: 4px;
                border-radius: 2px;
            }
            QScrollBar::handle:vertical {
                background: rgba(0, 0, 0, 0.12);
                border-radius: 2px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(0, 0, 0, 0.2);
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)
        
        self.content_widget = QWidget()
        self.content_widget.setStyleSheet("background: transparent;")
        scroll.viewport().setStyleSheet("background: transparent;")
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(2)
        self.content_layout.addStretch(1)
        
        scroll.setWidget(self.content_widget)
        layout.addWidget(scroll)
        
        self.setStyleSheet("""
            QWidget#annotation_panel {
                background-color: transparent;
            }
        """)
    
    def paintEvent(self, event):
        """绘制真正的圆角背景"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(self.rect().toRectF(), 12, 12)
        painter.setClipPath(path)
        painter.fillPath(path, QColor(255, 255, 255, 242))  # rgba(255,255,255,0.95)
        super().paintEvent(event)
    
    def add_annotation(self, number: int):
        """添加序号注释输入框"""
        if number in self._text_edits:
            return
        
        # 创建输入框容器（极简无背景）
        container = QWidget()
        container.setObjectName(f"annotation_container_{number}")
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 6, 0, 6)
        container_layout.setSpacing(4)
        
        # 第一行：序号 + 文字输入
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(10)
        row_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        # 序号标签（小圆点）
        number_label = QLabel(str(number))
        number_label.setFixedSize(20, 20)
        number_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        number_label.setStyleSheet("""
            QLabel {
                background-color: #ff4757;
                color: white;
                font-size: 10px;
                font-weight: bold;
                border-radius: 10px;
            }
        """)
        row_layout.addWidget(number_label, 0, Qt.AlignmentFlag.AlignTop)
        
        # 输入框（极简透明背景）
        text_edit = QTextEdit()
        text_edit.setPlaceholderText("输入注释...")
        text_edit.setObjectName(f"annotation_edit_{number}")
        text_edit.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        text_edit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        text_edit.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        text_edit.setStyleSheet("""
            QTextEdit {
                background-color: transparent;
                border: none;
                border-bottom: 1px solid rgba(0, 0, 0, 0.06);
                border-radius: 0px;
                padding: 0px;
                margin: 0px;
                font-size: 13px;
                color: #333;
            }
            QTextEdit:focus {
                border-bottom: 1px solid #ff4757;
            }
        """)
        
        # 自适应高度：根据内容调整，无上限
        def adjust_height():
            doc = text_edit.document()
            doc.setTextWidth(text_edit.viewport().width())
            doc_height = doc.size().height()
            # 获取文档边距
            margins = text_edit.contentsMargins()
            frame_width = text_edit.frameWidth() * 2
            # 最小高度26，紧凑计算避免底部空白
            new_height = max(26, int(doc_height + margins.top() + margins.bottom() + frame_width))
            text_edit.setFixedHeight(new_height)
        
        text_edit.textChanged.connect(adjust_height)
        text_edit.textChanged.connect(lambda n=number: self._on_text_changed(n, self._text_edits[n].toPlainText() if n in self._text_edits else ""))
        
        # 初始高度
        text_edit.setFixedHeight(26)
        
        row_layout.addWidget(text_edit, 1)
        container_layout.addWidget(row_widget)
        
        # 图片预览区（初始隐藏）
        image_label = QLabel()
        image_label.setObjectName(f"annotation_image_{number}")
        image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        image_label.setFixedHeight(0)
        image_label.setStyleSheet("""
            QLabel {
                background-color: rgba(0, 0, 0, 0.03);
                border-radius: 6px;
                margin-left: 30px;
            }
        """)
        image_label.hide()
        image_label.setCursor(Qt.CursorShape.PointingHandCursor)
        image_label.mousePressEvent = lambda e, n=number: self._on_image_clicked(n)
        container_layout.addWidget(image_label)
        
        # 操作按钮行：粘贴图片 / 选择文件
        btn_row = QWidget()
        btn_row_layout = QHBoxLayout(btn_row)
        btn_row_layout.setContentsMargins(30, 0, 0, 0)
        btn_row_layout.setSpacing(4)
        
        btn_paste = QPushButton()
        btn_paste.setIcon(qta.icon('mdi6.content-paste', color='#999'))
        btn_paste.setIconSize(QSize(14, 14))
        btn_paste.setFixedSize(24, 20)
        btn_paste.setToolTip("从剪贴板粘贴图片 (Ctrl+V)")
        btn_paste.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_paste.setStyleSheet("""
            QPushButton { background: transparent; border: none; border-radius: 4px; }
            QPushButton:hover { background: rgba(0,0,0,0.06); }
        """)
        btn_paste.clicked.connect(lambda checked, n=number: self._paste_image(n))
        btn_row_layout.addWidget(btn_paste)
        
        btn_file = QPushButton()
        btn_file.setIcon(qta.icon('mdi6.image-plus', color='#999'))
        btn_file.setIconSize(QSize(14, 14))
        btn_file.setFixedSize(24, 20)
        btn_file.setToolTip("选择图片文件")
        btn_file.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_file.setStyleSheet("""
            QPushButton { background: transparent; border: none; border-radius: 4px; }
            QPushButton:hover { background: rgba(0,0,0,0.06); }
        """)
        btn_file.clicked.connect(lambda checked, n=number: self._pick_image_file(n))
        btn_row_layout.addWidget(btn_file)
        
        btn_archive = QPushButton()
        btn_archive.setIcon(qta.icon('mdi6.archive-outline', color='#999'))
        btn_archive.setIconSize(QSize(14, 14))
        btn_archive.setFixedSize(24, 20)
        btn_archive.setToolTip("从归档记录选择")
        btn_archive.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_archive.setStyleSheet("""
            QPushButton { background: transparent; border: none; border-radius: 4px; }
            QPushButton:hover { background: rgba(0,0,0,0.06); }
        """)
        btn_archive.clicked.connect(lambda checked, n=number: self._pick_from_archive(n))
        btn_row_layout.addWidget(btn_archive)
        
        btn_delete = QPushButton()
        btn_delete.setIcon(qta.icon('mdi6.close-circle-outline', color='#999'))
        btn_delete.setIconSize(QSize(14, 14))
        btn_delete.setFixedSize(24, 20)
        btn_delete.setToolTip("删除图片")
        btn_delete.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_delete.setStyleSheet("""
            QPushButton { background: transparent; border: none; border-radius: 4px; }
            QPushButton:hover { background: rgba(255,0,0,0.08); }
        """)
        btn_delete.clicked.connect(lambda checked, n=number: self._remove_image(n))
        btn_row_layout.addWidget(btn_delete)
        
        btn_row_layout.addStretch()
        container_layout.addWidget(btn_row)
        
        # 插入到 stretch 之前（stretch 在最后一个位置）
        insert_pos = self.content_layout.count() - 1
        self.content_layout.insertWidget(insert_pos, container)
        
        self._text_edits[number] = text_edit
        self._image_labels[number] = image_label
        self._annotations[number] = ""
        self._visible_count += 1
        
        # 自动聚焦到新输入框
        text_edit.setFocus()
        
        # 显示面板
        if self._visible_count == 1:
            self.show()
    
    def remove_annotation(self, number: int):
        """移除序号注释"""
        if number not in self._text_edits:
            return
        
        # 找到并删除容器
        container = self.content_widget.findChild(QWidget, f"annotation_container_{number}")
        if container:
            container.deleteLater()
        
        del self._text_edits[number]
        if number in self._annotations:
            del self._annotations[number]
        if number in self._images:
            del self._images[number]
        if number in self._image_labels:
            del self._image_labels[number]
        
        self._visible_count -= 1
        
        # 隐藏面板
        if self._visible_count == 0:
            self.hide()
    
    def renumber(self, old_to_new: dict[int, int]):
        """重新编号（当序号点被删除后调整）"""
        # 保存旧数据
        old_annotations = self._annotations.copy()
        old_images = self._images.copy()
        
        # 清空所有
        for number in list(self._text_edits.keys()):
            self.remove_annotation(number)
        
        # 按新编号重建
        for old_num, new_num in sorted(old_to_new.items(), key=lambda x: x[1]):
            self.add_annotation(new_num)
            if old_num in old_annotations:
                self._text_edits[new_num].setPlainText(old_annotations[old_num])
            if old_num in old_images:
                self._set_image(new_num, old_images[old_num])
    
    def sync_with_marks(self, number_dots: list):
        """与画布上的序号点同步"""
        current_numbers = set(self._text_edits.keys())
        mark_numbers = {dot.number for dot in number_dots}
        
        # 添加新的
        for num in mark_numbers - current_numbers:
            self.add_annotation(num)
        
        # 删除多余的
        for num in current_numbers - mark_numbers:
            self.remove_annotation(num)
        
        # 重新排序（如果需要）
        if mark_numbers != current_numbers:
            self._reorder_widgets(number_dots)
    
    def _reorder_widgets(self, number_dots: list):
        """按序号顺序重新排列输入框"""
        # 获取所有容器（不包括 stretch）
        containers = []
        for i in range(self.content_layout.count() - 1):  # -1 排除末尾的 stretch
            item = self.content_layout.itemAt(i)
            if item and item.widget():
                containers.append(item.widget())
        
        # 按序号排序
        sorted_numbers = sorted(dot.number for dot in number_dots)
        
        # 重新插入（在 stretch 之前）
        for container in containers:
            self.content_layout.removeWidget(container)
        
        for num in sorted_numbers:
            container = self.content_widget.findChild(QWidget, f"annotation_container_{num}")
            if container:
                insert_pos = self.content_layout.count() - 1
                self.content_layout.insertWidget(insert_pos, container)
    
    def _on_text_changed(self, number: int, text: str):
        """文本变化"""
        self._annotations[number] = text
    
    def get_annotations(self) -> dict[int, str]:
        """获取所有注释"""
        return self._annotations.copy()
    
    def has_annotations(self) -> bool:
        """是否有注释内容（文字或图片）"""
        has_text = any(text.strip() for text in self._annotations.values())
        has_images = bool(self._images)
        return has_text or has_images
    
    def clear(self):
        """清空所有注释"""
        for number in list(self._text_edits.keys()):
            self.remove_annotation(number)
    
    def get_annotation_images(self) -> dict[int, QPixmap]:
        """获取所有注释图片 {序号: QPixmap}"""
        return self._images.copy()
    
    def _set_image(self, number: int, pixmap: QPixmap):
        """为指定序号设置图片"""
        if number not in self._image_labels:
            return
        
        self._images[number] = pixmap
        label = self._image_labels[number]
        
        # 缩略图：宽度适配面板（减去左侧缩进 30px + 边距）
        max_w = self.PANEL_WIDTH - 30 - 24
        max_h = 120
        scaled = pixmap.scaled(
            max_w, max_h,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        label.setPixmap(scaled)
        label.setFixedHeight(scaled.height() + 4)
        label.show()
    
    def _remove_image(self, number: int):
        """移除指定序号的图片"""
        if number in self._images:
            del self._images[number]
        if number in self._image_labels:
            self._image_labels[number].clear()
            self._image_labels[number].setFixedHeight(0)
            self._image_labels[number].hide()
    
    def _paste_image(self, number: int):
        """从剪贴板粘贴图片"""
        clipboard = QApplication.clipboard()
        mime = clipboard.mimeData()
        if mime and mime.hasImage():
            image = clipboard.image()
            if not image.isNull():
                self._set_image(number, QPixmap.fromImage(image))
                return
        # 检查剪贴板是否有 pixmap
        pixmap = clipboard.pixmap()
        if pixmap and not pixmap.isNull():
            self._set_image(number, pixmap)
    
    def _pick_image_file(self, number: int):
        """选择图片文件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择图片", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.webp)"
        )
        if file_path:
            pixmap = QPixmap(file_path)
            if not pixmap.isNull():
                self._set_image(number, pixmap)
    
    def _on_image_clicked(self, number: int):
        """点击图片 - 再次点击移除"""
        if number in self._images:
            self._remove_image(number)
    
    def _pick_from_archive(self, number: int):
        """从归档记录选择图片"""
        dialog = ArchivePickerDialog(self)
        if dialog.exec() == dialog.DialogCode.Accepted and dialog.selected_pixmap:
            self._set_image(number, dialog.selected_pixmap)


class ArchivePickerDialog(QWidget):
    """归档图片选择弹窗 - 网格缩略图选择"""
    
    def __init__(self, parent=None):
        # 使用 QWidget + WindowFlags 模拟 dialog，避免模态阻塞问题
        from PySide6.QtWidgets import QDialog, QGridLayout
        
        # 实际用 QDialog
        self._dialog = QDialog(parent)
        self._dialog.setWindowTitle("从归档选择图片")
        self._dialog.setMinimumSize(480, 400)
        self._dialog.resize(520, 440)
        self._dialog.setStyleSheet("""
            QDialog {
                background-color: #fafafa;
            }
        """)
        
        self.selected_pixmap = None
        self.DialogCode = self._dialog.DialogCode
        
        layout = QVBoxLayout(self._dialog)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        
        # 标题
        title = QLabel("选择归档图片")
        title.setStyleSheet("font-size: 14px; font-weight: bold; color: #333; padding: 4px 0;")
        layout.addWidget(title)
        
        # 滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical { width: 6px; background: transparent; }
            QScrollBar::handle:vertical { background: rgba(0,0,0,0.15); border-radius: 3px; min-height: 30px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        """)
        
        grid_widget = QWidget()
        self._grid_layout = QGridLayout(grid_widget)
        self._grid_layout.setContentsMargins(0, 0, 0, 0)
        self._grid_layout.setSpacing(8)
        
        scroll.setWidget(grid_widget)
        layout.addWidget(scroll)
        
        # 加载归档记录
        self._load_records()
    
    def _load_records(self):
        records = get_all_records()
        if not records:
            empty_label = QLabel("暂无归档记录")
            empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_label.setStyleSheet("color: #999; font-size: 13px; padding: 40px;")
            self._grid_layout.addWidget(empty_label, 0, 0, 1, 4)
            return
        
        cols = 4
        for i, record in enumerate(records):
            row, col = divmod(i, cols)
            card = self._create_card(record)
            if card:
                self._grid_layout.addWidget(card, row, col)
    
    def _create_card(self, record: dict):
        image_path = get_image_full_path(record.get("image_path", ""))
        if not image_path.exists():
            return None
        
        pixmap = QPixmap(str(image_path))
        if pixmap.isNull():
            return None
        
        thumb = pixmap.scaled(
            110, 90,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        
        card = QPushButton()
        card.setFixedSize(116, 96)
        card.setIcon(thumb)
        card.setIconSize(QSize(110, 90))
        card.setCursor(Qt.CursorShape.PointingHandCursor)
        card.setToolTip(record.get("timestamp", "")[:16])
        card.setStyleSheet("""
            QPushButton {
                background: white;
                border: 1px solid #e0e0e0;
                border-radius: 6px;
                padding: 2px;
            }
            QPushButton:hover {
                border: 2px solid #ff4757;
                background: #fff5f5;
            }
        """)
        card.clicked.connect(lambda checked, p=pixmap: self._select(p))
        return card
    
    def _select(self, pixmap: QPixmap):
        self.selected_pixmap = pixmap
        self._dialog.accept()
    
    def exec(self):
        return self._dialog.exec()
