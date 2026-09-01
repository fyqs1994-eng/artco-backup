"""
GenCanvas - AI 生图工作台（悬浮窗口）

将"弹窗生图 + 覆盖式追问"升级为"桌面上的持久画布会话"：
- 左侧编辑工具栏：选择 / 箭头 / 框选 / 涂鸦 / 文字（复用 EditorCanvas）
- 中间画布：当前选中版本的标注/编辑区（占据最多空间，聚焦图片）
- 右侧历史版本栏：只显示缩略图，鼠标悬停再浮现操作按钮
- 底部紧凑单行 AI 输入栏：快捷指令收纳进下拉开按钮（复用截图模式 Prompt 模板）
- 会话即工作区：所有版本落盘保存，关闭不丢失，可恢复

视觉规范：uniform 遵循 ui/theme.py 统一设计系统（Ant Design 浅色）。
"""

import os
import base64
import uuid
import tempfile
from datetime import datetime

from PySide6.QtCore import Qt, Signal, QBuffer, QIODevice, QSize, QPoint, QRect, QEvent, QTimer
from PySide6.QtGui import QPixmap, QPainter, QColor, QCursor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QApplication, QLineEdit, QFileDialog,
    QTextEdit,
)

import qtawesome as qta

from config import ai_config
from ui.ai_worker import AIWorker
from ui.ai_result import ThinkingBubble
from ui.prompt_manager import PromptSelectMenu, PromptSettingsWindow
from screenshot.canvas import EditorCanvas

# ── 统一设计系统（视觉标准）──
from ui.theme import (
    FONT_FAMILY, FONT_SIZE_XS, FONT_SIZE_SM, FONT_SIZE_MD, FONT_SIZE_LG, FONT_SIZE_XL,
    BG_PRIMARY, BG_SECONDARY, BG_HOVER, BG_ACTIVE, BG_HOVER_SOFT,
    BORDER_SUBTLE, BORDER_DEFAULT, BORDER_STRONG,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_TERTIARY, TEXT_MUTED,
    ACCENT_PRIMARY, ACCENT_HOVER, ACCENT_PRESSED, ACCENT_SUBTLE, ACCENT_BORDER,
    COLOR_SUCCESS, COLOR_ERROR,
    RADIUS_SM, RADIUS_MD, RADIUS_LG, RADIUS_XL,
    SPACING_XS, SPACING_SM, SPACING_MD, SPACING_LG, SPACING_XL,
    ICON_SM, ICON_MD, ICON_LG,
    BTN_SIZE, BTN_SIZE_SM,
    ICON_DEFAULT, ICON_HOVER, ICON_ACCENT, ICON_MUTED,
    get_scrollbar_style,
)


class VersionCard(QFrame):
    """历史版本栏卡片 - 只展示图片，鼠标悬停浮现操作按钮"""

    selected = Signal(int)      # 设为当前基底
    edit_requested = Signal()   # 在外部编辑器中打开
    pin_requested = Signal()    # 贴到桌面
    keyword_requested = Signal()  # 查看/编辑关键词

    def __init__(self, index: int, pixmap: QPixmap, prompt: str, parent=None):
        super().__init__(parent)
        self.index = index
        self.prompt = prompt
        self._selected = False

        self.setObjectName("genVersionCard")
        self.setFixedSize(116, 116)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)

        # 图片层（悬停时轻微压暗）
        self._img = QLabel(self)
        self._img.setGeometry(self.rect())
        self._img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._img.setStyleSheet("background: transparent;")
        thumb = pixmap.scaled(
            112, 112,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation,
        )
        self._img.setPixmap(thumb)
        self._img.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        # 悬停遮罩（默认为透明的 paintEvent；进入时浮现半透明白 + 操作按钮）
        self._overlay = QFrame(self)
        self._overlay.setGeometry(self.rect())
        self._overlay.hide()
        self._overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        op = QVBoxLayout(self._overlay)
        op.setContentsMargins(6, 6, 6, 6)
        op.setSpacing(0)
        op.addStretch()
        row = QHBoxLayout()
        row.setSpacing(4)
        row.addStretch()
        self._btn_pin = self._op_btn("mdi6.pin", "贴到屏幕", self.pin_requested.emit)
        self._btn_edit = self._op_btn("mdi6.message-draw", "反馈编辑器", self.edit_requested.emit)
        self._btn_keyword = self._op_btn("mdi6.tag-text-outline", "关键词", self.keyword_requested.emit)
        row.addWidget(self._btn_pin)
        row.addWidget(self._btn_edit)
        row.addWidget(self._btn_keyword)
        op.addLayout(row)

        self._refresh_style()

    def _op_btn(self, icon_name: str, tip: str, slot) -> QPushButton:
        btn = QPushButton()
        btn.setIcon(qta.icon(icon_name, color=ACCENT_PRIMARY))
        btn.setIconSize(QSize(ICON_MD, ICON_MD))
        btn.setFixedSize(28, 28)
        btn.setObjectName("genCardOpBtn")
        btn.setToolTip(tip)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(slot)
        return btn

    def set_selected(self, selected: bool):
        self._selected = selected
        self._refresh_style()

    def _refresh_style(self):
        if self._selected:
            border, bg = ACCENT_BORDER, ACCENT_SUBTLE
        else:
            border, bg = BORDER_SUBTLE, BG_SECONDARY
        self.setStyleSheet("".join([
            f"#genVersionCard {{ background: {bg}; border: 2px solid {border};",
            f" border-radius: {RADIUS_MD}px; }}",
        ]))

    def paintEvent(self, event):
        super().paintEvent(event)
        # 绘制悬停遮罩背景（半透明白）
        if self._overlay.isVisible():
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setBrush(QColor(248, 249, 250, 205))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(self.rect().adjusted(2, 2, -2, -2), RADIUS_MD, RADIUS_MD)
            painter.end()

    def mousePressEvent(self, event):
        self.selected.emit(self.index)
        super().mousePressEvent(event)

    def enterEvent(self, event):
        self._overlay.show()
        self._img.setStyleSheet("background-color: rgba(255,255,255,0.06); border: none;")
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._overlay.hide()
        self._img.setStyleSheet("background: transparent;")
        super().leaveEvent(event)


class GenCanvas(QWidget):
    """AI 生图工作台悬浮窗口"""

    # 对外信号（供 main 挂载贴屏 / 编辑等）
    canvas_pin_requested = Signal(QPixmap)
    canvas_edit_requested = Signal(QPixmap)
    followup_generated = Signal(str)  # 生成新版本后，发出当前选中版本路径
    keyword_edit_requested = Signal(int, str)  # (index, prompt) 关键词编辑完成

    # 左侧编辑工具（与 EditorCanvas 工具常量对应）
    _TOOL_DEFS = [
        ("mdi6.cursor-default", "选择/移动", EditorCanvas.TOOL_SELECT),
        ("mdi6.arrow-right", "箭头", EditorCanvas.TOOL_ARROW),
        ("mdi6.vector-rectangle", "框选", EditorCanvas.TOOL_RECT),
        ("mdi6.signature-freehand", "涂鸦", EditorCanvas.TOOL_FREEHAND),
        ("mdi6.format-text", "文字", EditorCanvas.TOOL_TEXT),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("genCanvas")
        self.setWindowTitle("AI 工作台")
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        # 留出外层阴影/描边空间
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)          # 边缘悬停检测需要鼠标追踪
        self.resize(780, 560)
        self.setMinimumSize(680, 460)

        self.session_id = uuid.uuid4().hex[:8]
        self._versions = []          # list of QPixmap
        self._prompts = []           # list of str
        self._paths = []             # list of str (落盘路径)
        self._cards = []             # list of VersionCard
        self._selected_index = -1

        self._worker = None
        self._working = False

        self._build_ui()

        # 无边框窗口：边缘拖拽调整大小
        self._resize_active = False
        self._resize_edges_flag = (False, False, False, False)
        self._resize_start_global = QPoint()
        self._resize_start_geom = self.frameGeometry()

        # 安装事件过滤器到所有子对象，确保鼠标在子控件上移动时光标也能实时更新
        self._install_resize_event_filter(self)

    # ───────────────────────── UI 构建 ─────────────────────────
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(SPACING_LG, SPACING_LG, SPACING_LG, SPACING_MD)
        root.setSpacing(0)

        self._outer = QFrame()
        self._outer.setObjectName("genCanvasOuter")
        outer_layout = QVBoxLayout(self._outer)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        # 标题栏
        title = QHBoxLayout()
        title.setContentsMargins(SPACING_LG, SPACING_SM, SPACING_SM, SPACING_SM)
        self.title_label = QLabel("AI 工作台")
        self.title_label.setObjectName("genCanvasTitle")
        title.addWidget(self.title_label)
        title.addStretch()
        self.btn_min = self._title_icon_btn("mdi6.window-minimize", "最小化")
        self.btn_close = self._title_icon_btn("mdi6.close", "关闭")
        self.btn_min.clicked.connect(self.showMinimized)
        self.btn_close.clicked.connect(self.close)
        title.addWidget(self.btn_min)
        title.addWidget(self.btn_close)
        outer_layout.addLayout(title)

        # 主体：左工具 | 中画布 | 右版本
        body = QHBoxLayout()
        body.setContentsMargins(SPACING_LG, SPACING_XS, SPACING_LG, SPACING_LG)
        body.setSpacing(SPACING_MD)

        body.addWidget(self._build_toolbar())

        self.canvas_scroll = QScrollArea()
        self.canvas_scroll.setObjectName("genCanvasScroll")
        self.canvas_scroll.setWidgetResizable(True)
        self.canvas_scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.canvas_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.canvas_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.canvas_scroll.setStyleSheet("".join([
            f"#genCanvasScroll {{ background: {BG_SECONDARY}; border: 1px solid {BORDER_SUBTLE};",
            f" border-radius: {RADIUS_MD}px; }}",
        ]))
        self._canvas_view = None
        self._canvas_placeholder = QLabel("从右侧选择一个版本，或在下方输入指令生成")
        self._canvas_placeholder.setObjectName("genCanvasPlaceholder")
        self._canvas_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.canvas_scroll.setWidget(self._canvas_placeholder)
        body.addWidget(self.canvas_scroll, 1)

        # 当前基底悬浮标签（半透明，置顶于画布左上角）
        self.base_hint = QLabel("")
        self.base_hint.setObjectName("genBaseHint")
        self.base_hint.setParent(self.canvas_scroll.viewport())
        self.base_hint.adjustSize()
        self.base_hint.move(SPACING_MD, SPACING_MD)
        self.base_hint.show()
        self.base_hint.raise_()

        body.addWidget(self._build_history_panel())

        outer_layout.addLayout(body, 1)

        # 底部（紧凑）
        outer_layout.addLayout(self._build_footer())

        root.addWidget(self._outer)

        # ── 全局视觉样式（Ant Design 浅色，统一字体/间距/圆角/hover 反馈）──
        self.setStyleSheet("""
            QWidget {
                font-family: """ + FONT_FAMILY + """;
                font-size: """ + str(FONT_SIZE_MD) + """px;
                color: """ + TEXT_PRIMARY + """;
            }

            #genCanvasOuter {
                background: """ + BG_PRIMARY + """;
                border-radius: """ + str(RADIUS_XL) + """px;
                border: 1px solid """ + BORDER_SUBTLE + """;
                box-shadow: 0 12px 32px 0 rgba(0, 0, 0, 0.12), 0 4px 12px 0 rgba(0, 0, 0, 0.08);
            }

            #genCanvasTitle {
                font-size: """ + str(FONT_SIZE_LG) + """px;
                font-weight: 600;
                color: """ + TEXT_PRIMARY + """;
            }

            QPushButton#genTitleBtn {
                background: transparent; border: none;
                color: """ + TEXT_TERTIARY + """;
                border-radius: """ + str(RADIUS_SM) + """px;
            }
            QPushButton#genTitleBtn:hover { background: """ + BG_HOVER + """; color: """ + TEXT_PRIMARY + """; }
            QPushButton#genTitleBtn:pressed { background: """ + BG_ACTIVE + """; }

            #genCanvasPlaceholder {
                color: """ + TEXT_TERTIARY + """;
                font-size: """ + str(FONT_SIZE_MD) + """px;
            }

            /* 左侧工具栏 */
            #genToolPanel {
                background: """ + BG_SECONDARY + """;
                border: 1px solid """ + BORDER_SUBTLE + """;
                border-radius: """ + str(RADIUS_LG) + """px;
            }
            QPushButton#genToolBtn {
                background: transparent; border: none;
                border-radius: """ + str(RADIUS_MD) + """px;
                margin: 2px 0;
            }
            QPushButton#genToolBtn:hover { background: """ + BG_ACTIVE + """; }
            QPushButton#genToolBtn:pressed { background: #d9d9d9; }

            /* 右侧历史栏 */
            #genHistoryPanel {
                background: """ + BG_SECONDARY + """;
                border: 1px solid """ + BORDER_SUBTLE + """;
                border-radius: """ + str(RADIUS_LG) + """px;
            }
            #genHistoryTitle {
                font-size: """ + str(FONT_SIZE_SM) + """px;
                font-weight: 600;
                color: """ + TEXT_SECONDARY + """;
                padding: """ + str(SPACING_XS) + """px """ + str(SPACING_XS) + """px;
            }
            #genWallScroll {
                background: transparent; border: none; border-radius: 0;
            }
            #genWallPlaceholder {
                color: """ + TEXT_TERTIARY + """;
                font-size: """ + str(FONT_SIZE_SM) + """px;
            }
            QPushButton#genCardOpBtn {
                background: """ + BG_PRIMARY + """; border: none;
                border-radius: """ + str(RADIUS_SM) + """px; padding: 0; margin: 0;
            }
            QPushButton#genCardOpBtn:hover { background: """ + ACCENT_SUBTLE + """; }
            QPushButton#genCardOpBtn:pressed { background: #c5e6ff; }

            /* 底部输入 */
            QPushButton#genQuickBtn {
                background: """ + BG_PRIMARY + """;
                border: 1px solid """ + BORDER_DEFAULT + """;
                border-radius: """ + str(RADIUS_MD) + """px;
                padding: 0 """ + str(SPACING_MD) + """px;
                font-size: """ + str(FONT_SIZE_SM) + """px;
                color: """ + TEXT_SECONDARY + """;
            }
            QPushButton#genQuickBtn:hover {
                border-color: """ + ACCENT_PRIMARY + """; color: """ + ACCENT_PRIMARY + """;
            }

            #genInput {
                background: """ + BG_PRIMARY + """;
                border: 1px solid """ + BORDER_DEFAULT + """;
                border-radius: """ + str(RADIUS_MD) + """px;
                padding: 5px """ + str(SPACING_MD) + """px;
                font-size: """ + str(FONT_SIZE_MD) + """px;
                color: """ + TEXT_PRIMARY + """;
                selection-background-color: """ + ACCENT_PRIMARY + """;
            }
            #genInput:focus { border-color: """ + ACCENT_PRIMARY + """; }
            #genInput:disabled { background: """ + BG_SECONDARY + """; color: """ + TEXT_TERTIARY + """; }
            #genInput::placeholder { color: """ + TEXT_TERTIARY + """; }

            #genGenerateBtn {
                background: """ + ACCENT_PRIMARY + """;
                color: #fff; border: none;
                border-radius: """ + str(RADIUS_MD) + """px;
                padding: 0 20px;
                font-size: """ + str(FONT_SIZE_MD) + """px;
                font-weight: 600;
            }
            #genGenerateBtn:hover { background: """ + ACCENT_HOVER + """; }
            #genGenerateBtn:pressed { background: """ + ACCENT_PRESSED + """; }
            #genGenerateBtn:disabled { background: """ + ACCENT_BORDER + """; }

            #genBaseHint {
                background: rgba(17, 24, 39, 0.55);
                color: #ffffff;
                font-size: """ + str(FONT_SIZE_SM) + """px;
                border-radius: """ + str(RADIUS_SM) + """px;
                padding: 3px 10px;
            }
        """)

    def _build_toolbar(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("genToolPanel")
        panel.setFixedWidth(BTN_SIZE + SPACING_LG)
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(SPACING_SM, SPACING_MD, SPACING_SM, SPACING_MD)
        lay.setSpacing(SPACING_XS)
        lay.addStretch()

        self._tool_buttons = {}
        for icon_name, tooltip, tool_id in self._TOOL_DEFS:
            btn = QPushButton()
            btn.setObjectName("genToolBtn")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setIcon(qta.icon(icon_name, color=ICON_DEFAULT))
            btn.setIconSize(QSize(ICON_MD, ICON_MD))
            btn.setFixedSize(BTN_SIZE, BTN_SIZE)
            btn.setToolTip(tooltip)
            btn.toggled.connect(lambda checked, b=btn, name=icon_name: self._on_tool_toggled(b, checked, name))
            btn.clicked.connect(lambda checked, tid=tool_id: self._on_tool_clicked(tid))
            self._tool_buttons[tool_id] = btn
            lay.insertWidget(lay.count() - 1, btn)

        self._current_tool = EditorCanvas.TOOL_SELECT
        self._tool_buttons[self._current_tool].setChecked(True)

        lay.addStretch(2)

        # 底部操作：屏贴 / 外部编辑 / 复制 / 保存原图（收纳进侧边工具栏）
        self.btn_pin = self._toolbar_icon_btn("mdi6.pin", "贴到屏幕", self._pin_selected)
        self.btn_edit = self._toolbar_icon_btn("mdi6.message-draw", "反馈编辑器", self._edit_selected)
        self.btn_copy = self._toolbar_icon_btn("mdi6.content-copy", "复制当前版本", self._copy_selected)
        self.btn_save = self._toolbar_icon_btn("mdi6.content-save", "保存原图", self._save_selected)
        lay.addWidget(self.btn_pin)
        lay.addWidget(self.btn_edit)
        lay.addWidget(self.btn_copy)
        lay.addWidget(self.btn_save)

        lay.addSpacing(SPACING_XS)
        return panel

    def _toolbar_icon_btn(self, icon_name: str, tip: str, slot) -> QPushButton:
        btn = QPushButton()
        btn.setObjectName("genToolBtn")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setIcon(qta.icon(icon_name, color=ICON_DEFAULT))
        btn.setIconSize(QSize(ICON_MD, ICON_MD))
        btn.setFixedSize(BTN_SIZE, BTN_SIZE)
        btn.setToolTip(tip)
        btn.clicked.connect(slot)
        return btn

    def _on_tool_toggled(self, btn: QPushButton, checked: bool, icon_name: str):
        """选中工具时切换成品牌蓝图标，未选中恢复默认色，兼顾对比度。"""
        color = ICON_ACCENT if checked else ICON_DEFAULT
        btn.setIcon(qta.icon(icon_name, color=color))

    def _build_history_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("genHistoryPanel")
        panel.setFixedWidth(148)
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(SPACING_SM, SPACING_SM, SPACING_SM, SPACING_SM)
        lay.setSpacing(SPACING_SM)

        title = QLabel("历史版本")
        title.setObjectName("genHistoryTitle")
        lay.addWidget(title)

        self.wall_scroll = QScrollArea()
        self.wall_scroll.setObjectName("genWallScroll")
        self.wall_scroll.setWidgetResizable(True)
        self.wall_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.wall_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.wall_scroll.setStyleSheet(get_scrollbar_style())

        self.wall_container = QWidget()
        self.wall_layout = QVBoxLayout(self.wall_container)
        self.wall_layout.setContentsMargins(0, 0, 0, 0)
        self.wall_layout.setSpacing(SPACING_SM)
        self.wall_layout.addStretch()
        self.wall_scroll.setWidget(self.wall_container)
        self._wall_placeholder = QLabel("还没有版本")
        self._wall_placeholder.setObjectName("genWallPlaceholder")
        self._wall_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._wall_placeholder.setFixedHeight(60)
        self.wall_layout.insertWidget(0, self._wall_placeholder)
        lay.addWidget(self.wall_scroll, 1)

        return panel

    def _build_footer(self):
        """底部：单行 AI 输入 + 轻量状态行"""
        input_area = QVBoxLayout()
        input_area.setContentsMargins(SPACING_LG, SPACING_XS, SPACING_LG, SPACING_LG)
        input_area.setSpacing(SPACING_XS)

        # 输入行：快捷指令下拉 + 输入框 + 生成
        row = QHBoxLayout()
        row.setSpacing(SPACING_SM)
        self.btn_quick = QPushButton(" 快捷指令")
        self.btn_quick.setObjectName("genQuickBtn")
        self.btn_quick.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_quick.setToolTip("选择截图模式已配置的指令模板")
        self.btn_quick.clicked.connect(self._show_quick_menu)
        row.addWidget(self.btn_quick)
        self.btn_quick.setFixedHeight(32)
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("在当前版本上输入调整指令…（Enter 生成）")
        self.input_field.setObjectName("genInput")
        self.input_field.setFixedHeight(32)
        self.input_field.returnPressed.connect(self._on_generate)
        row.addWidget(self.input_field, 1)

        self.btn_generate = QPushButton("生成")
        self.btn_generate.setObjectName("genGenerateBtn")
        self.btn_generate.setFixedHeight(32)
        self.btn_generate.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_generate.clicked.connect(self._on_generate)
        row.addWidget(self.btn_generate)

        # 生成中动画：三点跳动
        self._thinking = ThinkingBubble()
        self._thinking.setFixedHeight(32)
        self._thinking.setFixedWidth(68)
        self._thinking.hide()
        row.addWidget(self._thinking)

        input_area.addLayout(row)

        return input_area

    def _title_btn(self, text: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setObjectName("genTitleBtn")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFixedSize(28, 28)
        return btn

    def _title_icon_btn(self, icon_name: str, tip: str) -> QPushButton:
        btn = QPushButton()
        btn.setObjectName("genTitleBtn")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFixedSize(28, 28)
        btn.setIcon(qta.icon(icon_name, color=TEXT_TERTIARY))
        btn.setIconSize(QSize(ICON_MD, ICON_MD))
        btn.setToolTip(tip)
        return btn

    # ───────────────────────── 快捷指令（复用截图模式模板）─────────────────────────
    def _show_quick_menu(self):
        menu = PromptSelectMenu(self)
        menu.prompt_selected.connect(self._apply_quick_prompt)
        menu.edit_requested.connect(self._open_prompt_editor)
        pos = self.btn_quick.mapToGlobal(QPoint(0, self.btn_quick.height() + 2))
        menu.exec(pos)

    def _apply_quick_prompt(self, prompt_content: str, prompt_type: str):
        """选中快捷指令：填入输入框并立即生成"""
        self.input_field.setText(prompt_content)
        self._on_generate()

    def _open_prompt_editor(self):
        win = PromptSettingsWindow(self)
        win.exec()

    # ───────────────────────── 编辑工具 ─────────────────────────
    def _on_tool_clicked(self, tool_id: int):
        if self._current_tool != tool_id:
            if self._current_tool in self._tool_buttons:
                self._tool_buttons[self._current_tool].setChecked(False)
            self._current_tool = tool_id
            self._tool_buttons[tool_id].setChecked(True)
        if self._canvas_view is not None:
            self._canvas_view.set_tool(tool_id)

    # ───────────────────────── 会话数据 ─────────────────────────
    def _session_dir(self) -> str:
        d = os.path.join(tempfile.gettempdir(), "artco_generated", f"session_{self.session_id}")
        os.makedirs(d, exist_ok=True)
        return d

    def add_initial_version(self, pixmap: QPixmap, prompt: str = "原始生成"):
        self._append_version(pixmap, prompt)
        self._select_index(0)

    # ───────────────────────── 历史版本维护 ─────────────────────────
    def _append_version(self, pixmap: QPixmap, prompt: str):
        path = os.path.join(self._session_dir(),
                            f"v{len(self._versions) + 1}_{datetime.now().strftime('%H%M%S')}.png")

        self._versions.append(pixmap)
        self._prompts.append(prompt)
        self._paths.append(path)

        # 延迟落盘：让 UI 先渲染，磁盘写入放到下一个事件循环
        QTimer.singleShot(0, lambda: pixmap.save(path, "PNG"))

        self._wall_placeholder.hide()

        index = len(self._versions) - 1
        card = VersionCard(index, pixmap, prompt)
        card.selected.connect(self._select_index)
        card.pin_requested.connect(lambda: self._pin_version(index))
        card.edit_requested.connect(lambda: self._edit_version(index))
        card.keyword_requested.connect(lambda: self._show_keyword_editor(index))
        self._cards.append(card)
        self.wall_layout.insertWidget(self.wall_layout.count() - 1, card)

        bar = self.wall_scroll.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _select_index(self, index: int):
        if index < 0 or index >= len(self._versions):
            return
        for card in self._cards:
            card.set_selected(card.index == index)
        self._selected_index = index
        self.base_hint.setText(f"v{index + 1}")
        self.base_hint.adjustSize()
        self.base_hint.raise_()
        self._load_canvas(self._versions[index])

    def _load_canvas(self, pixmap: QPixmap):
        if self._canvas_view is not None:
            self._canvas_view.setParent(None)
            self._canvas_view.deleteLater()
        self._canvas_view = None
        canvas = EditorCanvas(pixmap)
        canvas.set_tool(self._current_tool)
        canvas.pan_requested.connect(self._on_canvas_pan)
        self._canvas_view = canvas
        self.canvas_scroll.setWidget(canvas)
        try:
            self._auto_fit_canvas()
        except Exception:
            pass
        # 确保 base_hint 始终置顶于画布之上
        self.base_hint.raise_()

    def _auto_fit_canvas(self):
        if not self.canvas_scroll or not self._canvas_view:
            return
        viewport = self.canvas_scroll.viewport().size()
        base = self._canvas_view.base_size
        if base.width() <= 0 or base.height() <= 0:
            return
        margin = SPACING_XL
        avail_w = max(1, viewport.width() - margin * 2)
        avail_h = max(1, viewport.height() - margin * 2)
        scale = min(avail_w / base.width(), avail_h / base.height(), 1.0)
        scale *= 0.92
        if scale < 0.98:
            self._canvas_view.set_scale(scale)

    def _current_pixmap(self):
        if 0 <= self._selected_index < len(self._versions):
            return self._versions[self._selected_index]
        if self._versions:
            return self._versions[-1]
        return None

    # ───────────────────────── 生成调度 ─────────────────────────
    def _pixmap_to_base64(self, pixmap) -> str:
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        pixmap.save(buffer, "PNG")
        data = buffer.data().data()
        buffer.close()
        return base64.b64encode(data).decode()

    def _on_generate(self):
        text = self.input_field.text().strip()
        if not text:
            return
        if self._working:
            return
        base = self._current_pixmap()
        if base is None:
            self._set_status("还没有基底图片，请先生成一张", warn=True)
            return
        ai_config.set("task_type", "image_gen")

        self._last_prompt = text
        # 传 QImage 到子线程，PNG→base64 编码在 worker 线程完成（避免主线程卡顿）
        self._worker = AIWorker(qimage=base.toImage(), prompt=text)
        self._worker.finished_image.connect(self._on_generated)
        self._worker.error.connect(self._on_error)
        self._worker.finished.connect(self._on_text_reply)
        self._set_working(True, text)
        self._worker.start()

    def _set_working(self, working: bool, prompt: str = ""):
        self._working = working
        self.btn_generate.setEnabled(not working)
        self.input_field.setEnabled(not working)
        if working:
            self.btn_generate.hide()
            self._thinking.show()
        else:
            self._thinking.hide()
            self.btn_generate.show()

    def _on_generated(self, image_path: str):
        pixmap = QPixmap(image_path)
        if pixmap.isNull():
            self._set_status("生成结果为空", warn=True)
            self._set_working(False)
            return
        self._append_version(pixmap, self._last_prompt)
        self._select_index(len(self._versions) - 1)
        self._set_working(False)
        self.input_field.clear()
        self._set_status(f"已生成 v{len(self._versions)}", warn=False)
        self.followup_generated.emit(image_path)

    def _on_text_reply(self, result: str):
        self._set_working(False)

    def _on_error(self, error_msg: str):
        self._set_working(False)
        self._set_status(f"❌ {error_msg}", warn=True)

    def _set_status(self, text: str, warn: bool = False):
        pass  # 状态行已移除

    # ───────────────────────── 版本操作 ─────────────────────────
    def _pin_version(self, index: int):
        if 0 <= index < len(self._versions):
            self.canvas_pin_requested.emit(self._versions[index])

    def _edit_version(self, index: int):
        if 0 <= index < len(self._versions):
            self.canvas_edit_requested.emit(self._versions[index])

    def _show_keyword_editor(self, index: int):
        """在画布上层展开一个可编辑的关键词文本框"""
        if index < 0 or index >= len(self._prompts):
            return
        # 如果已有编辑器打开，先关闭
        if hasattr(self, "_keyword_overlay") and self._keyword_overlay is not None:
            self._keyword_overlay.close()
            self._keyword_overlay.deleteLater()
            self._keyword_overlay = None

        viewport = self.canvas_scroll.viewport()
        overlay = QFrame(viewport)
        overlay.setObjectName("genKeywordOverlay")
        lay = QVBoxLayout(overlay)
        lay.setContentsMargins(SPACING_MD, SPACING_MD, SPACING_MD, SPACING_MD)
        lay.setSpacing(SPACING_SM)

        title = QLabel(f"关键词 · v{index + 1}")
        title.setObjectName("genKeywordTitle")
        title.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: {FONT_SIZE_SM}px; font-weight: 600; border: none;")
        lay.addWidget(title)

        editor = QTextEdit()
        editor.setObjectName("genKeywordEditor")
        editor.setPlainText(self._prompts[index])
        editor.setStyleSheet("".join([
            f"background: {BG_PRIMARY}; border: 1px solid {BORDER_DEFAULT};",
            f" border-radius: {RADIUS_SM}px; padding: 8px;",
            f" font-size: {FONT_SIZE_SM}px; color: {TEXT_PRIMARY};",
        ]))
        lay.addWidget(editor)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(SPACING_SM)
        btn_row.addStretch()
        btn_save = QPushButton("保存")
        btn_save.setObjectName("genKeywordSaveBtn")
        btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_save.setStyleSheet("".join([
            f"background: {ACCENT_PRIMARY}; color: #fff; border: none;",
            f" border-radius: {RADIUS_SM}px; padding: 4px 16px; font-weight: 600;",
        ]))
        btn_close = QPushButton("关闭")
        btn_close.setObjectName("genKeywordCloseBtn")
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.setStyleSheet("".join([
            f"background: {BG_PRIMARY}; border: 1px solid {BORDER_DEFAULT};",
            f" border-radius: {RADIUS_SM}px; padding: 4px 16px; color: {TEXT_SECONDARY};",
        ]))
        btn_row.addWidget(btn_close)
        btn_row.addWidget(btn_save)
        lay.addLayout(btn_row)

        # 居中覆盖在 viewport 上
        vw = viewport.width()
        vh = viewport.height()
        ow = min(420, vw - SPACING_LG * 2)
        oh = min(220, vh - SPACING_LG * 2)
        overlay.setGeometry(
            (vw - ow) // 2, (vh - oh) // 2, ow, oh
        )

        overlay.setStyleSheet("".join([
            f"#genKeywordOverlay {{",
            f"  background: {BG_PRIMARY};",
            f"  border: 1px solid {BORDER_STRONG};",
            f"  border-radius: {RADIUS_MD}px;",
            f"  box-shadow: 0 8px 24px rgba(0,0,0,0.18);",
            f"}}",
        ]))
        overlay.show()
        overlay.raise_()
        editor.setFocus()

        def _save():
            new_text = editor.toPlainText().strip()
            if new_text:
                self._prompts[index] = new_text
                self.keyword_edit_requested.emit(index, new_text)
            overlay.close()
            overlay.deleteLater()
            self._keyword_overlay = None

        def _close():
            overlay.close()
            overlay.deleteLater()
            self._keyword_overlay = None

        btn_save.clicked.connect(_save)
        btn_close.clicked.connect(_close)
        self._keyword_overlay = overlay

    def _pin_selected(self):
        pm = self._current_pixmap()
        if pm:
            self.canvas_pin_requested.emit(pm)

    def _edit_selected(self):
        pm = self._current_pixmap()
        if pm:
            self.canvas_edit_requested.emit(pm)

    def _copy_selected(self):
        pm = self._current_pixmap()
        if pm:
            QApplication.clipboard().setPixmap(pm)
            self._set_status("已复制", warn=False)

    def _save_selected(self):
        pm = self._current_pixmap()
        if pm is None:
            return
        default_name = os.path.join(
            os.path.expanduser("~"), "Pictures",
            f"artco_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
        path, _ = QFileDialog.getSaveFileName(self, "保存图片", default_name, "PNG (*.png)")
        if path:
            pm.save(path, "PNG")
            self._set_status(f"已保存到 {os.path.basename(path)}", warn=False)

# ───────────────────────── 画布平移（中键滚轮 / 空格）─────────────────────────
    def _on_canvas_pan(self, dx: int, dy: int):
        h = self.canvas_scroll.horizontalScrollBar()
        v = self.canvas_scroll.verticalScrollBar()
        h.setValue(h.value() - dx)
        v.setValue(v.value() - dy)

    # ───────────────────────── 拖拽标题栏 / 边缘调整窗口大小 ─────────────────────────
    _RESIZE_MARGIN = 16   # 匹配外层透明边距 SPACING_LG，覆盖视觉边框区域

    def _hit_test(self, pos: QPoint) -> tuple:
        """判断鼠标所在边缘，返回 (left, right, top, bottom)。基于 _outer 实际几何位置。"""
        rect = self._outer.rect()
        outer_top_left = self._outer.mapTo(self, rect.topLeft())
        r = QRect(outer_top_left, rect.size())
        m = self._RESIZE_MARGIN
        return (
            abs(pos.x() - r.left()) <= m,
            abs(pos.x() - r.right()) <= m,
            abs(pos.y() - r.top()) <= m,
            abs(pos.y() - r.bottom()) <= m,
        )

    def _edge_cursor(self, left, right, top, bottom):
        if (left and bottom) or (right and top):
            return Qt.CursorShape.SizeBDiagCursor
        if (left and top) or (right and bottom):
            return Qt.CursorShape.SizeFDiagCursor
        if left or right:
            return Qt.CursorShape.SizeHorCursor
        if top or bottom:
            return Qt.CursorShape.SizeVerCursor
        return Qt.CursorShape.ArrowCursor

    def _do_resize(self, global_pos: QPoint):
        left, right, top, bottom = self._resize_edges_flag
        orig = self._resize_start_geom
        start = self._resize_start_global
        dx = global_pos.x() - start.x()
        dy = global_pos.y() - start.y()
        geom = QRect(orig)
        if right:
            geom.setWidth(max(self.minimumWidth(), orig.width() + dx))
        if bottom:
            geom.setHeight(max(self.minimumHeight(), orig.height() + dy))
        if left:
            w = max(self.minimumWidth(), orig.width() - dx)
            geom.setLeft(orig.right() - w + 1)
        if top:
            h = max(self.minimumHeight(), orig.height() - dy)
            geom.setTop(orig.bottom() - h + 1)
        self.setGeometry(geom)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            edges = self._hit_test(event.position().toPoint())
            if any(edges):
                self._resize_active = True
                self._resize_edges_flag = edges
                self._resize_start_global = event.globalPosition().toPoint()
                self._resize_start_geom = self.frameGeometry()
                event.accept()
                return
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if getattr(self, "_resize_active", False):
            self._do_resize(event.globalPosition().toPoint())
            event.accept()
            return
        if hasattr(self, "_drag_offset") and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            edges = self._hit_test(event.position().toPoint())
            self.setCursor(self._edge_cursor(*edges))
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._resize_active = False
        self.setCursor(Qt.CursorShape.ArrowCursor)
        super().mouseReleaseEvent(event)

    # ───────────────────────── 事件过滤器（光标实时更新）─────────────────────────
    def _install_resize_event_filter(self, widget):
        """仅给窗口自身和外层 Frame 安装事件过滤器，避免递归全部子控件造成卡顿。"""
        self.installEventFilter(self)
        self._outer.installEventFilter(self)
        self._outer.setMouseTracking(True)

    def eventFilter(self, obj, event):
        """拦截子控件的鼠标移动事件，在非拖拽状态下实时更新边缘光标。"""
        if not getattr(self, "_resize_active", False) and event.type() == QEvent.Type.MouseMove:
            if not (event.buttons() & Qt.MouseButton.LeftButton):
                # 将子控件坐标转换为窗口坐标
                global_pos = event.globalPosition().toPoint()
                local_pos = self.mapFromGlobal(global_pos)
                edges = self._hit_test(local_pos)
                self.setCursor(self._edge_cursor(*edges))
        elif event.type() == QEvent.Type.HoverMove:
            if not getattr(self, "_resize_active", False):
                global_pos = event.globalPosition().toPoint()
                local_pos = self.mapFromGlobal(global_pos)
                edges = self._hit_test(local_pos)
                self.setCursor(self._edge_cursor(*edges))
        return super().eventFilter(obj, event)

