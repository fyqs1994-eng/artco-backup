"""
设置对话框 — Raycast Preferences 风格
顶部 icon+text 工具栏 · 白底单列表单 · 零装饰
所有详情页共用 _section / _form_row 布局规则
"""

import sys
import os
import json

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QWidget, QLabel, QKeySequenceEdit, QMessageBox,
    QLineEdit, QPushButton, QScrollArea, QFrame,
    QComboBox, QMenu, QStackedWidget, QToolButton,
    QListWidget, QListWidgetItem, QSizePolicy,
    QProgressDialog,
)
from PySide6.QtCore import Signal, Qt, QPoint, QSize, QTimer
from PySide6.QtGui import QKeySequence
import qtawesome as qta

from config import AI_MODELS, ai_config, wecom_config, ps_config
from utils import hotkey_manager
from database import get_all_prompts, add_prompt, update_prompt, delete_prompt
from ui.theme import (
    FONT_FAMILY,
    BG_HOVER, BORDER_DEFAULT,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_TERTIARY,
    ACCENT_PRIMARY, ACCENT_SUBTLE,
    RADIUS_SM, RADIUS_MD,
    COLOR_ERROR,
    MENU_STYLE,
)


# ── helper utilities ──────────────────────────────────────────

def get_app_path():
    if getattr(sys, 'frozen', False):
        return sys.executable
    return os.path.abspath(sys.argv[0])


def is_autostart_enabled():
    if sys.platform != 'win32':
        return False
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_READ,
        )
        try:
            winreg.QueryValueEx(key, "Artco")
            return True
        except FileNotFoundError:
            return False
        finally:
            winreg.CloseKey(key)
    except Exception:
        return False


def set_autostart(enable: bool):
    if sys.platform != 'win32':
        return False
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_SET_VALUE,
        )
        try:
            if enable:
                app_path = get_app_path()
                winreg.SetValueEx(key, "Artco", 0, winreg.REG_SZ, f'"{app_path}"')
            else:
                try:
                    winreg.DeleteValue(key, "Artco")
                except FileNotFoundError:
                    pass
            return True
        finally:
            winreg.CloseKey(key)
    except Exception as e:
        print(f"设置开机启动失败: {e}")
        return False


# ── 视觉常量 ──────────────────────────────────────────────────
_TOOLBAR_BG  = "#ECECEC"
_CONTENT_BG  = "#FFFFFF"
_SEPARATOR   = "#DCDCDC"
_TAB_CHECKED = "rgba(0,0,0,0.08)"
_TAB_HOVER   = "rgba(0,0,0,0.04)"
_SEC_COLOR   = "rgba(0,0,0,0.40)"
_FORM_LABEL  = "rgba(0,0,0,0.55)"
_ROW_H       = 34
_LABEL_W     = 120
_PAGE_LR     = 48
_PAGE_TB     = 28
_SEC_GAP     = 10
_ROW_GAP     = 10
_BLOCK_GAP   = 24


class _PromptRow(QWidget):
    """Prompt list row: show checkbox on hover, always show if checked."""

    def __init__(self, is_default: bool, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background:transparent;")
        self.cb = None
        self._is_default = is_default

    def enterEvent(self, event):
        if self.cb and not self.cb.isChecked():
            self.cb.setVisible(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        if self.cb and not self.cb.isChecked():
            self.cb.setVisible(False)
        super().leaveEvent(event)


# ══════════════════════════════════════════════════════════════
class SettingsDialog(QDialog):
    """设置对话框 — Raycast 风格"""
    hotkey_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.resize(820, 600)
        self.setMinimumSize(780, 540)
        self._current_provider_detail = None
        self._prompt_current_id = None
        self._prompt_data: list = []
        self.init_ui()

    # ══════════════════════════════════════════════════════
    #  UI 主体
    # ══════════════════════════════════════════════════════

    def init_ui(self):
        os.environ.setdefault("QT_API", "pyside6")
        from qfluentwidgets import PushButton, PrimaryPushButton

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── 1. 顶部工具栏 ──
        toolbar = QWidget()
        toolbar.setObjectName("rc_toolbar")
        toolbar.setFixedHeight(64)
        tb = QHBoxLayout(toolbar)
        tb.setContentsMargins(0, 6, 0, 2)
        tb.setSpacing(2)
        tb.addStretch()

        tab_defs = [
            ("mdi6.creation-outline",     "AI 设置"),
            ("mdi6.text-box-edit-outline", "Prompt"),
            ("mdi6.keyboard-outline",      "快捷键"),
            ("mdi6.tune-vertical",         "通用"),
        ]
        self._tab_btns: list[QToolButton] = []
        for i, (icon_name, label) in enumerate(tab_defs):
            btn = QToolButton()
            btn.setObjectName("rc_tab")
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            btn.setIcon(qta.icon(icon_name, color="#555"))
            btn.setIconSize(QSize(20, 20))
            btn.setText(label)
            btn.setCheckable(True)
            btn.setAutoExclusive(True)
            btn.setFixedSize(76, 52)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _, idx=i: self._switch_tab(idx))
            tb.addWidget(btn)
            self._tab_btns.append(btn)
        tb.addStretch()
        root.addWidget(toolbar)

        self._add_sep(root)

        # ── 2. 内容区 ──
        self._pages = QStackedWidget()
        self._pages.setObjectName("rc_pages")
        self._pages.addWidget(self._build_ai_page())
        self._pages.addWidget(self._build_prompt_page())
        self._pages.addWidget(self._build_hotkey_page())
        self._pages.addWidget(self._build_general_page())
        root.addWidget(self._pages, 1)

        self._add_sep(root)

        # ── 3. 底栏 ──
        bottom = QWidget()
        bottom.setObjectName("rc_toolbar")
        blay = QHBoxLayout(bottom)
        blay.setContentsMargins(20, 10, 20, 10)
        blay.addStretch()
        self.btn_cancel = PushButton("取消")
        self.btn_cancel.setFixedSize(88, 32)
        self.btn_cancel.clicked.connect(self.reject)
        blay.addWidget(self.btn_cancel)
        self.btn_save = PrimaryPushButton("保存")
        self.btn_save.setFixedSize(88, 32)
        self.btn_save.clicked.connect(self._save_settings)
        blay.addWidget(self.btn_save)
        root.addWidget(bottom)

        # ── 4. 全局 QSS ──
        self.setStyleSheet(self._stylesheet())
        self._tab_btns[0].setChecked(True)
        self._pages.setCurrentIndex(0)

    # ── Tab 切换 ──────────────────────────────────────────
    def _switch_tab(self, idx: int):
        self._pages.setCurrentIndex(idx)
        for i, b in enumerate(self._tab_btns):
            b.setChecked(i == idx)

    def show_tab(self, tab_id: str):
        mapping = {'ai': 0, 'prompt': 1, 'hotkey': 2, 'general': 3, 'wecom': 0}
        self._switch_tab(mapping.get(tab_id, 0))

    # ══════════════════════════════════════════════════════
    #  共用 widget 工厂
    # ══════════════════════════════════════════════════════

    @staticmethod
    def _section(text: str) -> QWidget:
        box = QWidget()
        box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        h = QHBoxLayout(box)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(10)
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"color:{_SEC_COLOR}; font-size:13px; font-weight:600;"
        )
        h.addWidget(lbl)
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFixedHeight(1)
        line.setStyleSheet(f"background:{_SEPARATOR}; border:none;")
        h.addWidget(line, 1)
        return box

    @staticmethod
    def _form_row(label_text: str, widget: QWidget, label_w: int = _LABEL_W) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(12)
        lbl = QLabel(label_text)
        lbl.setFixedWidth(label_w)
        lbl.setStyleSheet(f"color:{_FORM_LABEL}; font-size:13px;")
        lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(lbl)
        row.addWidget(widget, 1)
        return row

    @staticmethod
    def _tip(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(f"color:{TEXT_TERTIARY}; font-size:11px; padding-left:2px;")
        return lbl

    @staticmethod
    def _fix_key_edit(edit: QKeySequenceEdit):
        """Remove internal layout margins so inner QLineEdit fills the full widget."""
        lo = edit.layout()
        if lo:
            lo.setContentsMargins(0, 0, 0, 0)
            lo.setSpacing(0)

    @staticmethod
    def _add_sep(layout: QVBoxLayout):
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background:{_SEPARATOR};")
        layout.addWidget(sep)

    @staticmethod
    def _scroll_page() -> tuple:
        """返回 (page=QScrollArea, body_layout=QVBoxLayout)，统一页面骨架。"""
        page = QScrollArea()
        page.setWidgetResizable(True)
        page.setFrameShape(QFrame.Shape.NoFrame)
        page.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer = QWidget()
        oh = QHBoxLayout(outer)
        oh.setContentsMargins(0, 0, 0, 0)
        oh.setSpacing(0)
        oh.addStretch(1)
        body = QWidget()
        body.setFixedWidth(650)
        lay = QVBoxLayout(body)
        lay.setContentsMargins(_PAGE_LR, _PAGE_TB, _PAGE_LR, _PAGE_TB)
        lay.setSpacing(0)
        oh.addWidget(body)
        oh.addStretch(1)
        page.setWidget(outer)
        return page, lay

    # ══════════════════════════════════════════════════════
    #  PAGE 0 — AI 设置
    # ══════════════════════════════════════════════════════

    def _build_ai_page(self):
        from qfluentwidgets import PushButton, ComboBox

        page, lay = self._scroll_page()

        # section: 服务商
        lay.addWidget(self._section("服务商"))
        lay.addSpacing(_SEC_GAP)

        combo_w = QWidget()
        ch = QHBoxLayout(combo_w)
        ch.setContentsMargins(0, 0, 0, 0)
        ch.setSpacing(8)
        self.provider_combo = ComboBox()
        self.provider_combo.setMinimumWidth(180)
        self.provider_combo.setFixedHeight(_ROW_H)
        self._refresh_provider_combo()
        self.provider_combo.currentIndexChanged.connect(self._on_provider_changed)
        ch.addWidget(self.provider_combo, 1)

        self.btn_add_provider = PushButton("+")
        self.btn_add_provider.setFixedSize(_ROW_H, _ROW_H)
        self.btn_add_provider.setToolTip("添加服务商")
        self.btn_add_provider.clicked.connect(self._add_provider)
        ch.addWidget(self.btn_add_provider)
        self.btn_remove_provider = PushButton("−")
        self.btn_remove_provider.setFixedSize(_ROW_H, _ROW_H)
        self.btn_remove_provider.setToolTip("删除服务商")
        self.btn_remove_provider.clicked.connect(self._remove_provider)
        ch.addWidget(self.btn_remove_provider)

        lay.addLayout(self._form_row("当前服务商", combo_w))
        lay.addSpacing(_ROW_GAP)

        # 动态详情容器
        self._ai_detail = QWidget()
        self._ai_detail_lay = QVBoxLayout(self._ai_detail)
        self._ai_detail_lay.setContentsMargins(0, 0, 0, 0)
        self._ai_detail_lay.setSpacing(0)
        lay.addWidget(self._ai_detail)

        lay.addStretch()

        enabled = ai_config.get_enabled_providers()
        if enabled:
            self.provider_combo.setCurrentIndex(0)
            self._on_provider_changed(0)

        return page

    # ══════════════════════════════════════════════════════
    #  PAGE 1 — Prompt（内联构建，不嵌入外部组件）
    # ══════════════════════════════════════════════════════

    def _build_prompt_page(self):
        from qfluentwidgets import PushButton, PrimaryPushButton, LineEdit, TextEdit, RadioButton, CheckBox

        page = QScrollArea()
        page.setWidgetResizable(True)
        page.setFrameShape(QFrame.Shape.NoFrame)
        page.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        outer = QWidget()
        outer.setObjectName("rc_page_bg")
        oh = QHBoxLayout(outer)
        oh.setContentsMargins(0, 0, 0, 0)
        oh.setSpacing(0)
        oh.addStretch(1)

        wrapper = QWidget()
        wrapper.setFixedWidth(650)
        h = QHBoxLayout(wrapper)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)

        oh.addWidget(wrapper)
        oh.addStretch(1)

        # ── 左栏：列表 ──
        left = QWidget()
        left.setFixedWidth(220)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(16, _PAGE_TB, 12, 16)
        ll.setSpacing(8)

        self._prompt_list = QListWidget()
        self._prompt_list.setObjectName("pm_list")
        self._prompt_list.currentRowChanged.connect(self._on_prompt_selected)
        ll.addWidget(self._prompt_list, 1)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        btn_add = PushButton("新增")
        btn_add.setIcon(qta.icon('mdi6.plus', color=ACCENT_PRIMARY))
        btn_add.setFixedHeight(_ROW_H)
        btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_add.clicked.connect(self._add_prompt)
        btn_row.addWidget(btn_add)
        btn_del = PushButton("删除")
        btn_del.setIcon(qta.icon('mdi6.trash-can', color=COLOR_ERROR))
        btn_del.setFixedHeight(_ROW_H)
        btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_del.clicked.connect(self._delete_prompt)
        btn_row.addWidget(btn_del)
        btn_row.addStretch()
        ll.addLayout(btn_row)
        h.addWidget(left)

        # 竖分割线
        vline = QFrame()
        vline.setFrameShape(QFrame.Shape.VLine)
        vline.setFixedWidth(1)
        vline.setStyleSheet(f"color:{_SEPARATOR};")
        h.addWidget(vline)

        # ── 右栏：编辑表单 ──
        right_body = QWidget()
        rl = QVBoxLayout(right_body)
        rl.setContentsMargins(_PAGE_LR, _PAGE_TB, _PAGE_LR, _PAGE_TB)
        rl.setSpacing(0)

        # section: 标题
        rl.addWidget(self._section("标题"))
        rl.addSpacing(_SEC_GAP)

        self._prompt_title = LineEdit()
        self._prompt_title.setPlaceholderText("输入 Prompt 标题…")
        self._prompt_title.setFixedHeight(_ROW_H)
        rl.addWidget(self._prompt_title)
        rl.addSpacing(_ROW_GAP)

        lbl_tp = QLabel("类型")
        lbl_tp.setStyleSheet(f"color:{_FORM_LABEL}; font-size:12px;")
        rl.addWidget(lbl_tp)
        rl.addSpacing(4)
        type_w = QWidget()
        tw = QHBoxLayout(type_w)
        tw.setContentsMargins(0, 0, 0, 0)
        tw.setSpacing(16)
        self._prompt_type_text = RadioButton("文本/识图 (Vision)")
        self._prompt_type_text.setChecked(True)
        tw.addWidget(self._prompt_type_text)
        self._prompt_type_image = RadioButton("生图/重绘 (Image Gen)")
        tw.addWidget(self._prompt_type_image)
        tw.addStretch()
        rl.addWidget(type_w)
        rl.addSpacing(_BLOCK_GAP)


        # section: Prompt 内容
        rl.addWidget(self._section("Prompt 内容"))
        rl.addSpacing(_SEC_GAP)

        self._prompt_content = TextEdit()
        self._prompt_content.setPlaceholderText("输入 Prompt 内容…")
        self._prompt_content.setMinimumHeight(140)
        rl.addWidget(self._prompt_content, 1)
        rl.addSpacing(8)

        self._prompt_status_lbl = QLabel()
        self._prompt_status_lbl.setStyleSheet(f"color:{TEXT_TERTIARY}; font-size:11px;")
        self._prompt_status_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        rl.addWidget(self._prompt_status_lbl)

        self._prompt_save_timer = QTimer(self)
        self._prompt_save_timer.setSingleShot(True)
        self._prompt_save_timer.setInterval(1000)
        self._prompt_save_timer.timeout.connect(self._auto_save_prompt)

        self._prompt_title.textChanged.connect(self._prompt_edit_changed)
        self._prompt_content.textChanged.connect(self._prompt_edit_changed)
        self._prompt_type_text.toggled.connect(self._on_prompt_type_toggled)
        self._prompt_type_image.toggled.connect(self._on_prompt_type_toggled)

        h.addWidget(right_body, 1)

        page.setWidget(outer)
        self._load_prompts()
        return page

    # ══════════════════════════════════════════════════════
    #  PAGE 2 — 快捷键
    # ══════════════════════════════════════════════════════

    def _build_hotkey_page(self):
        from qfluentwidgets import PushButton

        page, lay = self._scroll_page()

        # section: 全局快捷键
        lay.addWidget(self._section("全局快捷键"))
        lay.addSpacing(_SEC_GAP)

        self.screenshot_hotkey = QKeySequenceEdit()
        self.screenshot_hotkey.setMaximumSequenceLength(1)
        self.screenshot_hotkey.setKeySequence(QKeySequence(hotkey_manager.get('screenshot')))
        self.screenshot_hotkey.setFixedWidth(180)
        self.screenshot_hotkey.setFixedHeight(_ROW_H)
        self._fix_key_edit(self.screenshot_hotkey)
        lay.addLayout(self._form_row("截图快捷键", self.screenshot_hotkey))
        lay.addSpacing(_ROW_GAP)

        self.clipboard_float_mode = QComboBox()
        self.clipboard_float_mode.addItems(["键盘快捷键", "鼠标侧键1", "鼠标侧键2"])
        self.clipboard_float_mode.setFixedWidth(180)
        self.clipboard_float_mode.setFixedHeight(_ROW_H)
        lay.addLayout(self._form_row("剪贴板浮窗", self.clipboard_float_mode))
        lay.addSpacing(_ROW_GAP)

        self.clipboard_float_hotkey = QKeySequenceEdit()
        self.clipboard_float_hotkey.setMaximumSequenceLength(1)
        self.clipboard_float_hotkey.setFixedWidth(180)
        self.clipboard_float_hotkey.setFixedHeight(_ROW_H)
        self._fix_key_edit(self.clipboard_float_hotkey)
        lay.addLayout(self._form_row("浮窗快捷键", self.clipboard_float_hotkey))
        lay.addLayout(self._form_row("", self._tip("选择鼠标侧键或直接在键盘快捷键框中按键设置")))

        cfk = hotkey_manager.get('clipboard_float')
        if cfk == 'mousex1':
            self.clipboard_float_mode.setCurrentIndex(1)
            self.clipboard_float_hotkey.setKeySequence(QKeySequence())
            self.clipboard_float_hotkey.setEnabled(False)
        elif cfk == 'mousex2':
            self.clipboard_float_mode.setCurrentIndex(2)
            self.clipboard_float_hotkey.setKeySequence(QKeySequence())
            self.clipboard_float_hotkey.setEnabled(False)
        else:
            self.clipboard_float_mode.setCurrentIndex(0)
            self.clipboard_float_hotkey.setKeySequence(QKeySequence(cfk))
            self.clipboard_float_hotkey.setEnabled(True)
        self.clipboard_float_mode.currentIndexChanged.connect(self._on_clipboard_float_mode_changed)
        lay.addSpacing(_BLOCK_GAP)

        # 截图窗口快捷键
        self._hotkey_edits = {}
        for category, actions in hotkey_manager.get_screenshot_hotkeys().items():
            lay.addWidget(self._section(f"截图窗口 · {category}"))
            lay.addSpacing(_SEC_GAP)
            for action, hotkey in actions.items():
                edit = QKeySequenceEdit()
                edit.setMaximumSequenceLength(1)
                edit.setKeySequence(QKeySequence(hotkey))
                edit.setFixedWidth(180)
                edit.setFixedHeight(_ROW_H)
                self._fix_key_edit(edit)
                lay.addLayout(self._form_row(hotkey_manager.get_action_name(action), edit))
                lay.addSpacing(6)
                self._hotkey_edits[(category, action)] = edit
            lay.addSpacing(18)

        reset_btn = PushButton("恢复默认快捷键")
        reset_btn.setFixedHeight(_ROW_H)
        reset_btn.clicked.connect(self._reset_hotkeys)
        lay.addWidget(reset_btn, alignment=Qt.AlignmentFlag.AlignLeft)
        lay.addStretch()
        return page

    # ══════════════════════════════════════════════════════
    #  PAGE 3 — 通用
    # ══════════════════════════════════════════════════════

    def _build_general_page(self):
        from qfluentwidgets import CheckBox, ComboBox

        page, lay = self._scroll_page()

        # section: 启动
        lay.addWidget(self._section("启动"))
        lay.addSpacing(_SEC_GAP)
        self.autostart_checkbox = CheckBox("开机自动启动")
        self.autostart_checkbox.setChecked(is_autostart_enabled())
        lay.addWidget(self.autostart_checkbox)
        lay.addSpacing(4)
        tip1 = self._tip("启用后，系统启动时会自动运行 Artco")
        tip1.setContentsMargins(24, 0, 0, 0)
        lay.addWidget(tip1)
        lay.addSpacing(_BLOCK_GAP)

        # section: 屏幕贴图
        lay.addWidget(self._section("屏幕贴图"))
        lay.addSpacing(_SEC_GAP)
        self.crop_shrink_checkbox = CheckBox("双击时启用裁剪缩小（参考 Setuna）")
        self.crop_shrink_checkbox.setToolTip("双击屏幕贴图时，使用鼠标拖拽选择区域进行裁剪，而非整体缩小")
        self.crop_shrink_checkbox.setChecked(ps_config.get_crop_shrink_enabled())
        lay.addWidget(self.crop_shrink_checkbox)
        lay.addSpacing(4)
        tip2 = self._tip("启用后，双击屏幕贴图会进入裁剪模式")
        tip2.setContentsMargins(24, 0, 0, 0)
        lay.addWidget(tip2)
        lay.addSpacing(14)

        lbl_sz = QLabel("缩略图大小")
        lbl_sz.setStyleSheet(f"color:{_FORM_LABEL}; font-size:12px;")
        lay.addWidget(lbl_sz)
        lay.addSpacing(4)
        self.thumbnail_size_combo = ComboBox()
        self.thumbnail_size_combo.addItems(["32x32", "48x48", "64x64", "96x96", "128x128"])
        cur = ps_config.get_thumbnail_size()
        self.thumbnail_size_combo.setCurrentIndex({32: 0, 48: 1, 64: 2, 96: 3, 128: 4}.get(cur, 2))
        self.thumbnail_size_combo.setFixedHeight(_ROW_H)
        self.thumbnail_size_combo.setFixedWidth(140)
        lay.addWidget(self.thumbnail_size_combo)

        lay.addSpacing(_BLOCK_GAP)

        # section: 关于 / 更新
        lay.addWidget(self._section("关于"))
        lay.addSpacing(_SEC_GAP)

        from version import APP_VERSION
        version_label = QLabel(f"Artco v{APP_VERSION}")
        version_label.setStyleSheet(f"color:{TEXT_PRIMARY}; font-size:14px; font-weight:500;")
        lay.addWidget(version_label)
        lay.addSpacing(8)

        from qfluentwidgets import PushButton as QFPushButton
        self.btn_check_update = QFPushButton("检查更新")
        self.btn_check_update.setIcon(qta.icon('mdi6.cloud-download-outline', color=ACCENT_PRIMARY))
        self.btn_check_update.setFixedHeight(_ROW_H)
        self.btn_check_update.setFixedWidth(120)
        self.btn_check_update.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_check_update.clicked.connect(self._check_update_from_settings)
        lay.addWidget(self.btn_check_update)
        lay.addSpacing(4)
        tip3 = self._tip("检查是否有新版本可用")
        tip3.setContentsMargins(24, 0, 0, 0)
        lay.addWidget(tip3)

        lay.addStretch()
        return page

    # ══════════════════════════════════════════════════════
    #  AI 服务商
    # ══════════════════════════════════════════════════════

    def _refresh_provider_combo(self):
        from config import AI_PROVIDERS
        self.provider_combo.blockSignals(True)
        self.provider_combo.clear()
        for pid in ai_config.get_enabled_providers():
            if pid in AI_PROVIDERS:
                self.provider_combo.addItem(AI_PROVIDERS[pid]["name"], pid)
        self.provider_combo.blockSignals(False)

    def _on_provider_changed(self, index: int):
        enabled = ai_config.get_enabled_providers()
        if index < 0 or index >= len(enabled):
            return
        pid = enabled[index]
        self._current_provider_detail = pid
        self._show_provider_detail(pid)

    def _show_provider_detail(self, provider_id):
        from config import AI_PROVIDERS
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl
        from qfluentwidgets import LineEdit, PushButton, ComboBox

        self._clear_layout(self._ai_detail_lay)

        provider = AI_PROVIDERS.get(provider_id)
        if not provider:
            return

        L = self._ai_detail_lay
        is_current = provider_id == ai_config.get_current_provider_selected()

        # 默认状态
        if is_current:
            st = QLabel("✓ 当前默认服务商")
            st.setStyleSheet("color:#52c41a; font-size:13px; font-weight:500;")
            L.addLayout(self._form_row("", st))
        else:
            self._btn_set_default = PushButton("设为默认服务商")
            self._btn_set_default.setFixedHeight(_ROW_H)
            self._btn_set_default.clicked.connect(lambda: self._set_default_provider(provider_id))
            L.addLayout(self._form_row("", self._btn_set_default))

        L.addSpacing(_BLOCK_GAP)

        # section: 连接
        L.addWidget(self._section("连接"))
        L.addSpacing(_SEC_GAP)

        key_w = QWidget()
        kh = QHBoxLayout(key_w)
        kh.setContentsMargins(0, 0, 0, 0)
        kh.setSpacing(8)
        self._provider_key_input = LineEdit()
        self._provider_key_input.setPlaceholderText(f"输入 {provider['name']} API Key")
        self._provider_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._provider_key_input.setText(ai_config.get_api_key(provider_id))
        self._provider_key_input.setFixedHeight(_ROW_H)
        kh.addWidget(self._provider_key_input, 1)
        self._btn_verify_key = PushButton("验证")
        self._btn_verify_key.setFixedHeight(_ROW_H)
        self._btn_verify_key.setFixedWidth(72)
        self._btn_verify_key.clicked.connect(self._verify_provider_key)
        kh.addWidget(self._btn_verify_key)
        L.addLayout(self._form_row("API Key", key_w))
        L.addSpacing(_ROW_GAP)

        self._provider_base_url = LineEdit()
        self._provider_base_url.setPlaceholderText("自定义 API 地址（可选）")
        self._provider_base_url.setText(ai_config.get_api_base_url(provider_id))
        self._provider_base_url.setFixedHeight(_ROW_H)
        L.addLayout(self._form_row("Base URL", self._provider_base_url))
        L.addSpacing(_BLOCK_GAP)

        # section: 模型
        L.addWidget(self._section("模型"))
        L.addSpacing(_SEC_GAP)

        all_vision = ai_config.get(f"{provider_id}_vision_models", [])
        if not all_vision:
            all_vision = [m.get("name", m["id"]) for m in AI_MODELS.get("vision", []) if m.get("provider") == provider_id]

        self._vision_model_combo = ComboBox()
        self._vision_model_combo.setFixedHeight(_ROW_H)
        for mid in all_vision:
            dn = mid
            for m in AI_MODELS.get("vision", []):
                if m["id"] == mid:
                    dn = m.get("name", mid)
                    break
            self._vision_model_combo.addItem(dn)
            self._vision_model_combo.setItemData(self._vision_model_combo.count() - 1, mid)
        saved_v = ai_config.get("vision_model", provider.get("default_vision"))
        idx = self._vision_model_combo.findData(saved_v)
        self._vision_model_combo.setCurrentIndex(max(idx, 0))
        L.addLayout(self._form_row("视觉分析模型", self._vision_model_combo))
        L.addSpacing(_ROW_GAP)

        all_img = ai_config.get(f"{provider_id}_image_gen_models", [])
        if not all_img:
            defs = [m for m in AI_MODELS.get("image_gen", []) if m.get("provider") == provider_id]
            if defs:
                all_img = [m["id"] for m in defs]

        self._image_gen_model_combo = ComboBox()
        self._image_gen_model_combo.setFixedHeight(_ROW_H)
        if all_img:
            for mid in all_img:
                dn = mid
                for m in AI_MODELS.get("image_gen", []):
                    if m["id"] == mid:
                        dn = m.get("name", mid)
                        break
                self._image_gen_model_combo.addItem(dn)
                self._image_gen_model_combo.setItemData(self._image_gen_model_combo.count() - 1, mid)
            saved_ig = ai_config.get("image_gen_model", provider.get("default_image_gen"))
            idx = self._image_gen_model_combo.findData(saved_ig)
            self._image_gen_model_combo.setCurrentIndex(max(idx, 0))
        else:
            self._image_gen_model_combo.addItem("无可用模型", "")
            self._image_gen_model_combo.setEnabled(False)
        L.addLayout(self._form_row("图像生成模型", self._image_gen_model_combo))
        L.addSpacing(_BLOCK_GAP)

        # 获取 key 链接
        self._key_url = provider["key_url"]
        link = PushButton(f"获取 {provider['name']} API Key →")
        link.setFixedHeight(_ROW_H)
        link.setCursor(Qt.CursorShape.PointingHandCursor)
        link.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(self._key_url)))
        L.addLayout(self._form_row("", link))
        L.addStretch()

    def _add_provider(self):
        from config import AI_PROVIDERS
        enabled = ai_config.get_enabled_providers()
        available = [p for p in AI_PROVIDERS if p not in enabled]
        if not available:
            QMessageBox.information(self, "提示", "所有服务商已添加")
            return
        menu = QMenu(self)
        menu.setStyleSheet(MENU_STYLE)
        for pid in available:
            a = menu.addAction(AI_PROVIDERS[pid]["name"])
            a.setData(pid)
        pos = self.btn_add_provider.mapToGlobal(QPoint(0, self.btn_add_provider.height()))
        a = menu.exec(pos)
        if a:
            ai_config.add_provider(a.data())
            self._refresh_provider_combo()
            self.provider_combo.setCurrentIndex(self.provider_combo.count() - 1)

    def _remove_provider(self):
        idx = self.provider_combo.currentIndex()
        if idx < 0:
            return
        enabled = ai_config.get_enabled_providers()
        if idx >= len(enabled):
            return
        pid = enabled[idx]
        from config import AI_PROVIDERS
        name = AI_PROVIDERS.get(pid, {}).get("name", pid)
        if QMessageBox.question(
            self, "确认删除", f'确定要删除服务商 "{name}" 吗？',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes:
            ai_config.remove_provider(pid)
            self._refresh_provider_combo()
            if self.provider_combo.count() > 0:
                self.provider_combo.setCurrentIndex(0)

    def _set_default_provider(self, provider_id):
        from config import AI_PROVIDERS
        ai_config.set_current_provider_selected(provider_id)
        self._show_provider_detail(provider_id)
        QMessageBox.information(self, "成功", f"已将 {AI_PROVIDERS[provider_id]['name']} 设为默认服务商")

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                self._clear_layout(item.layout())

    # ══════════════════════════════════════════════════════
    #  Prompt 数据操作
    # ══════════════════════════════════════════════════════

    def _load_prompts(self, select_id: str | None = None, refresh_form: bool = True):
        from PySide6.QtWidgets import QCheckBox
        # clear() 会把当前行置为 -1；若不在此前 blockSignals，会发出 currentRowChanged(-1)，
        # 进而 _on_prompt_selected 清空表单并丢掉 _prompt_current_id（编辑中新模板会被打断）。
        row = -1
        self._prompt_list.blockSignals(True)
        try:
            self._prompt_list.clear()
            self._prompt_data = get_all_prompts()
            self._prompt_default_cbs = []

            cb_style = (
                f"QCheckBox {{ spacing: 0px; }}"
                f"QCheckBox::indicator {{ width: 14px; height: 14px; }}"
            )

            for p in self._prompt_data:
                pt = p.get("prompt_type", "text")
                icon_name = 'mdi6.text-box-outline' if pt == "text" else 'mdi6.image-outline'

                item = QListWidgetItem()
                item.setData(Qt.ItemDataRole.UserRole, p["id"])
                item.setSizeHint(QSize(0, 42))
                self._prompt_list.addItem(item)

                row_w = _PromptRow(p["is_default"])
                rl = QHBoxLayout(row_w)
                rl.setContentsMargins(10, 0, 8, 0)
                rl.setSpacing(8)

                icon_lbl = QLabel()
                icon_lbl.setPixmap(qta.icon(icon_name, color=TEXT_TERTIARY).pixmap(QSize(18, 18)))
                icon_lbl.setFixedSize(18, 18)
                rl.addWidget(icon_lbl)

                title_lbl = QLabel(p["title"])
                title_lbl.setStyleSheet(f"color:{TEXT_PRIMARY}; font-size:14px;")
                rl.addWidget(title_lbl, 1)

                cb = QCheckBox()
                cb.setChecked(p["is_default"])
                cb.setCursor(Qt.CursorShape.PointingHandCursor)
                cb.setToolTip("默认")
                cb.setStyleSheet(cb_style)
                cb.setFixedSize(18, 18)
                if not p["is_default"]:
                    cb.setVisible(False)
                pid = p["id"]
                cb.toggled.connect(lambda checked, _pid=pid: self._toggle_default(_pid, checked))
                rl.addWidget(cb)
                row_w.cb = cb
                self._prompt_default_cbs.append((pid, cb))

                self._prompt_list.setItemWidget(item, row_w)

            if select_id is not None:
                for i in range(self._prompt_list.count()):
                    it = self._prompt_list.item(i)
                    if it is not None and it.data(Qt.ItemDataRole.UserRole) == select_id:
                        row = i
                        break
            if row < 0 and self._prompt_list.count() > 0:
                row = 0
            if row >= 0:
                self._prompt_list.setCurrentRow(row)
        finally:
            self._prompt_list.blockSignals(False)

        if row >= 0:
            if refresh_form:
                self._on_prompt_selected(row)
        else:
            self._on_prompt_selected(-1)

    def _row_snapshot_for_update(self, p: dict) -> tuple[str, str, str]:
        """写库用：当前选中行用右侧表单，其余行用内存条（避免未自动保存时把类型改回旧值）。"""
        if p["id"] == self._prompt_current_id:
            title = self._prompt_title.text().strip()
            content = self._prompt_content.toPlainText().strip()
            pt = "image" if self._prompt_type_image.isChecked() else "text"
            return title, content, pt
        return p["title"], p["content"], p.get("prompt_type", "text")

    def _toggle_default(self, prompt_id, checked):
        if not checked:
            for p in self._prompt_data:
                if p["id"] == prompt_id:
                    p["is_default"] = False
                    title, content, pt = self._row_snapshot_for_update(p)
                    update_prompt(p["id"], title, content, False, pt)
                    break
            return
        for pid, cb in self._prompt_default_cbs:
            if pid != prompt_id:
                cb.blockSignals(True)
                cb.setChecked(False)
                cb.setVisible(False)
                cb.blockSignals(False)
        for p in self._prompt_data:
            title, content, pt = self._row_snapshot_for_update(p)
            if p["id"] == prompt_id:
                p["is_default"] = True
                update_prompt(p["id"], title, content, True, pt)
            elif p["is_default"]:
                p["is_default"] = False
                update_prompt(p["id"], title, content, False, pt)
        self._notify_prompts_changed()

    def _on_prompt_type_toggled(self, checked: bool):
        if not checked:
            return
        if not self._prompt_current_id:
            return
        if getattr(self, "_prompt_loading", False):
            return
        pt = "image" if self._prompt_type_image.isChecked() else "text"
        update_prompt(self._prompt_current_id, prompt_type=pt)
        for p in self._prompt_data:
            if p["id"] == self._prompt_current_id:
                p["prompt_type"] = pt
                break
        self._load_prompts(select_id=self._prompt_current_id, refresh_form=False)
        self._notify_prompts_changed()

    def _on_prompt_selected(self, row: int):
        self._prompt_save_timer.stop()
        self._prompt_loading = True
        if row < 0 or row >= len(self._prompt_data):
            self._prompt_current_id = None
            self._prompt_title.clear()
            self._prompt_content.clear()
            self._prompt_type_text.setChecked(True)
            self._prompt_loading = False
            return
        p = self._prompt_data[row]
        self._prompt_current_id = p["id"]
        self._prompt_title.setText(p["title"])
        self._prompt_content.setPlainText(p["content"])
        if p.get("prompt_type", "text") == "image":
            self._prompt_type_image.setChecked(True)
        else:
            self._prompt_type_text.setChecked(True)
        self._prompt_loading = False
        self._prompt_status_lbl.setText("")

    def _add_prompt(self):
        new_id = add_prompt("新建 Prompt", "请输入 Prompt 内容...", prompt_type="text")
        self._load_prompts(select_id=new_id)
        self._notify_prompts_changed()
        self._prompt_title.setFocus()
        self._prompt_title.selectAll()

    def _delete_prompt(self):
        if not self._prompt_current_id:
            return
        if QMessageBox.question(
            self, "确认删除", "确定要删除这个 Prompt 吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes:
            delete_prompt(self._prompt_current_id)
            self._load_prompts()
            self._notify_prompts_changed()

    def _prompt_edit_changed(self):
        if not self._prompt_current_id:
            return
        if getattr(self, '_prompt_loading', False):
            return
        self._prompt_save_timer.start()

    def _auto_save_prompt(self):
        if not self._prompt_current_id:
            return
        title = self._prompt_title.text().strip()
        content = self._prompt_content.toPlainText().strip()
        if not title or not content:
            return
        is_default = False
        for p in self._prompt_data:
            if p["id"] == self._prompt_current_id:
                is_default = p["is_default"]
                break
        pt = "image" if self._prompt_type_image.isChecked() else "text"
        update_prompt(self._prompt_current_id, title, content, is_default, pt)
        self._load_prompts(select_id=self._prompt_current_id, refresh_form=False)
        self._notify_prompts_changed()
        self._prompt_status_lbl.setText("已自动保存")
        QTimer.singleShot(2000, lambda: self._prompt_status_lbl.setText(""))

    def _notify_prompts_changed(self):
        """通知所有活跃的 ScreenshotAICapsule 和 ScreenshotOverlay 实例刷新 prompts 缓存和 UI"""
        try:
            from screenshot.toolbar import ScreenshotAICapsule
            ScreenshotAICapsule.refresh_all_instances()
        except Exception:
            pass

    # ══════════════════════════════════════════════════════
    # ══════════════════════════════════════════════════════

    def _verify_provider_key(self):
        if not self._current_provider_detail:
            return
        provider_id = self._current_provider_detail
        api_key = self._provider_key_input.text().strip()
        if not api_key:
            QMessageBox.warning(self, "验证失败", "请输入 API Key")
            return
        self._btn_verify_key.setEnabled(False)
        self._btn_verify_key.setText("验证中…")
        try:
            verify_map = {
                "google": self._verify_google_key,
                "openai": self._verify_openai_key,
                "anthropic": self._verify_anthropic_key,
                "seedream": self._verify_seedream_key,
            }
            fn = verify_map.get(provider_id)
            if fn:
                success, message, models = fn(api_key)
            else:
                success, message, models = False, f"未知服务商: {provider_id}", []

            if success:
                QMessageBox.information(self, "验证成功", f"API Key 验证通过！\n{message}")
                ai_config.set_api_key(provider_id, api_key)
                if hasattr(self, '_provider_base_url'):
                    ai_config.set_api_base_url(provider_id, self._provider_base_url.text().strip())
                ai_config.set(f"{provider_id}_vision_models", models.get("vision", []))
                ai_config.set(f"{provider_id}_image_gen_models", models.get("image_gen", []))
                self._show_provider_detail(provider_id)
            else:
                QMessageBox.warning(self, "验证失败", f"API Key 无效：\n{message}")
        except Exception as e:
            QMessageBox.critical(self, "验证错误", f"验证过程出错：\n{str(e)}")
        finally:
            self._btn_verify_key.setEnabled(True)
            self._btn_verify_key.setText("验证")

    def _verify_google_key(self, api_key):
        try:
            from google import genai
            client = genai.Client(api_key=api_key)
            all_models = []
            for model in client.models.list():
                fn = model.name if hasattr(model, 'name') else str(model)
                all_models.append(fn[7:] if fn.startswith("models/") else fn)
            return True, f"有效 Key，共发现 {len(all_models)} 个模型", {"vision": all_models, "image_gen": all_models}
        except Exception as e:
            import requests
            try:
                resp = requests.get(f"https://generativelanguage.googleapis.com/v1/models?key={api_key}", timeout=10)
                if resp.status_code == 200:
                    models = resp.json().get("models", [])
                    all_m = [m.get("name", "").removeprefix("models/") for m in models]
                    return True, f"有效 Key，共发现 {len(all_m)} 个模型", {"vision": all_m, "image_gen": all_m}
                if resp.status_code == 401:
                    return False, "无效的 API Key", {}
                return False, f"API 返回错误: {resp.status_code}", {}
            except Exception:
                return False, f"验证失败: {e}", {}

    def _verify_openai_key(self, api_key):
        import requests
        try:
            resp = requests.get("https://api.openai.com/v1/models", headers={"Authorization": f"Bearer {api_key}"}, timeout=10)
            if resp.status_code == 200:
                all_m = [m.get("id") for m in resp.json().get("data", [])]
                return True, f"有效 Key，共发现 {len(all_m)} 个模型", {"vision": all_m, "image_gen": all_m}
            if resp.status_code == 401:
                return False, "无效的 API Key", {}
            return False, f"API 返回错误: {resp.status_code}", {}
        except Exception as e:
            return False, str(e), {}

    def _verify_anthropic_key(self, api_key):
        import requests
        try:
            resp = requests.get("https://api.anthropic.com/v1/models", headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"}, timeout=10)
            if resp.status_code == 200:
                all_m = [m.get("id") for m in resp.json().get("data", [])]
                return True, f"有效 Key，共发现 {len(all_m)} 个模型", {"vision": all_m, "image_gen": all_m}
            if resp.status_code == 401:
                return False, "无效的 API Key", {}
            return False, f"API 返回错误: {resp.status_code}", {}
        except Exception as e:
            return False, str(e), {}

    def _verify_seedream_key(self, api_key):
        import requests
        try:
            resp = requests.get("https://api.seedream.io/v1/models", headers={"Authorization": f"Bearer {api_key}"}, timeout=10)
            if resp.status_code == 200:
                all_m = [m.get("id") for m in resp.json().get("data", [])]
                return True, f"有效 Key，共发现 {len(all_m)} 个模型", {"vision": all_m, "image_gen": all_m}
            if resp.status_code == 401:
                return False, "无效的 API Key", {}
            return False, f"API 返回错误: {resp.status_code}", {}
        except Exception as e:
            return False, str(e), {}

    # ══════════════════════════════════════════════════════
    #  保存 / 重置
    # ══════════════════════════════════════════════════════

    def _on_clipboard_float_mode_changed(self, index):
        if index == 0:
            self.clipboard_float_hotkey.setEnabled(True)
        else:
            self.clipboard_float_hotkey.setEnabled(False)
            self.clipboard_float_hotkey.setKeySequence(QKeySequence())

    def _save_settings(self):
        # AI
        if self._current_provider_detail and hasattr(self, '_provider_key_input'):
            pid = self._current_provider_detail
            ai_config.set_api_key(pid, self._provider_key_input.text().strip())
            if hasattr(self, '_provider_base_url'):
                ai_config.set_api_base_url(pid, self._provider_base_url.text().strip())
            if hasattr(self, '_vision_model_combo'):
                v = self._vision_model_combo.currentData()
                if v:
                    ai_config.set("vision_model", v)
            if hasattr(self, '_image_gen_model_combo'):
                v = self._image_gen_model_combo.currentData()
                if v:
                    ai_config.set("image_gen_model", v)

        # 快捷键
        seq = self.screenshot_hotkey.keySequence()
        hs = seq.toString() if not seq.isEmpty() else ''
        old = hotkey_manager.get('screenshot')
        hotkey_manager.set('screenshot', hs)
        if old != hs:
            self.hotkey_changed.emit()

        mi = self.clipboard_float_mode.currentIndex()
        if mi == 0:
            seq = self.clipboard_float_hotkey.keySequence()
            cfs = seq.toString() if not seq.isEmpty() else ''
        elif mi == 1:
            cfs = 'mousex1'
        else:
            cfs = 'mousex2'
        old_cf = hotkey_manager.get('clipboard_float')
        hotkey_manager.set('clipboard_float', cfs)
        if old_cf != cfs:
            self.hotkey_changed.emit()

        for (cat, act), edit in self._hotkey_edits.items():
            seq = edit.keySequence()
            hotkey_manager.set_screenshot_hotkey(cat, act, seq.toString() if not seq.isEmpty() else '')

        try:
            from screenshot.cache import invalidate_hotkey_cache
            invalidate_hotkey_cache()
        except ImportError:
            pass

        ae = self.autostart_checkbox.isChecked()
        if ae != is_autostart_enabled():
            if not set_autostart(ae):
                QMessageBox.warning(self, "警告", "开机启动设置失败，请以管理员权限运行")

        try:
            ps_config.set_crop_shrink_enabled(self.crop_shrink_checkbox.isChecked())
            ps_config.set_thumbnail_size({0: 32, 1: 48, 2: 64, 3: 96, 4: 128}.get(self.thumbnail_size_combo.currentIndex(), 64))
        except Exception:
            pass

        QMessageBox.information(self, "成功", "设置已保存")
        self._notify_prompts_changed()
        self.accept()

    def _reset_hotkeys(self):
        if QMessageBox.question(
            self, "确认", "确定要恢复所有快捷键为默认值吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        self.screenshot_hotkey.setKeySequence(QKeySequence(hotkey_manager.DEFAULT_HOTKEYS.get('screenshot', 'F1')))
        dcf = hotkey_manager.DEFAULT_HOTKEYS.get('clipboard_float', 'mousex1')
        if dcf == 'mousex1':
            self.clipboard_float_mode.setCurrentIndex(1)
            self.clipboard_float_hotkey.setKeySequence(QKeySequence())
            self.clipboard_float_hotkey.setEnabled(False)
        elif dcf == 'mousex2':
            self.clipboard_float_mode.setCurrentIndex(2)
            self.clipboard_float_hotkey.setKeySequence(QKeySequence())
            self.clipboard_float_hotkey.setEnabled(False)
        else:
            self.clipboard_float_mode.setCurrentIndex(0)
            self.clipboard_float_hotkey.setKeySequence(QKeySequence(dcf))
            self.clipboard_float_hotkey.setEnabled(True)
        for (cat, act), edit in self._hotkey_edits.items():
            dh = hotkey_manager.DEFAULT_SCREENSHOT_HOTKEYS.get(cat, {}).get(act, '')
            edit.setKeySequence(QKeySequence(dh))

    # ══════════════════════════════════════════════════════
    #  自动更新
    # ══════════════════════════════════════════════════════

    def _check_update_from_settings(self):
        """从设置页检查更新"""
        import threading
        import updater as updater_mod
        self.btn_check_update.setEnabled(False)
        self.btn_check_update.setText("检查中…")

        def do_check():
            has_update, info = updater_mod.check_for_update()
            updater_mod._save_check_time()
            QTimer.singleShot(0, lambda: self._on_check_result(has_update, info))

        threading.Thread(target=do_check, daemon=True).start()

    def _on_check_result(self, has_update: bool, info):
        """检查结果回调"""
        self.btn_check_update.setEnabled(True)
        self.btn_check_update.setText("检查更新")

        if not has_update:
            QMessageBox.information(self, "检查更新", "已是最新版本 ✓")
            return

        version = info.get("version", "?")
        changelog = info.get("changelog", "")

        from version import APP_VERSION
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setWindowTitle(f"发现新版本 v{version}")
        msg.setText(f"<h3>Artco v{version} 已发布</h3>")
        changes = changelog if changelog else "暂无更新说明"
        msg.setInformativeText(f"<b>更新内容：</b><br>{changes}<br><br>当前版本：v{APP_VERSION}")
        btn_update = msg.addButton("立即更新", QMessageBox.ButtonRole.AcceptRole)
        msg.addButton("稍后提醒", QMessageBox.ButtonRole.RejectRole)
        msg.addButton("跳过此版本", QMessageBox.ButtonRole.DestructiveRole)
        msg.setDefaultButton(btn_update)
        msg.exec()

        if msg.clickedButton() == btn_update:
            self._start_download_from_settings(info)

    def _start_download_from_settings(self, info):
        """从设置页开始下载更新"""
        import threading
        import updater as updater_mod

        self._update_progress = QProgressDialog("正在下载更新…", "取消", 0, 100, self)
        self._update_progress.setWindowTitle("Artco 更新")
        self._update_progress.setMinimumWidth(400)
        self._update_progress.setWindowModality(Qt.WindowModality.ApplicationModal)
        self._update_progress.setAutoClose(False)
        self._update_cancelled = False
        self._update_info = info
        self._update_progress.canceled.connect(lambda: setattr(self, '_update_cancelled', True))
        self._update_progress.show()

        def download_thread():
            try:
                new_path = updater_mod.download_update(
                    info,
                    progress_callback=lambda r: QTimer.singleShot(0, lambda: self._update_progress.setValue(int(r * 100)))
                )
                if self._update_cancelled:
                    return
                QTimer.singleShot(0, lambda: self._on_download_done(new_path))
            except Exception as e:
                QTimer.singleShot(0, lambda: self._on_download_fail(str(e)))

        threading.Thread(target=download_thread, daemon=True).start()

    def _on_download_done(self, new_path):
        self._update_progress.setValue(100)
        self._update_progress.setLabelText("下载完成，正在应用更新…")
        QMessageBox.information(self, "更新", "下载完成，程序将重启以完成更新。")
        import updater as updater_mod
        updater_mod.apply_update(new_path)

    def _on_download_fail(self, err):
        if hasattr(self, '_update_progress'):
            self._update_progress.close()
        QMessageBox.warning(self, "更新失败", f"下载失败：\n{err}")

    # ══════════════════════════════════════════════════════
    #  Webhook（保留接口）
    # ══════════════════════════════════════════════════════

    def _load_webhooks(self):
        if not hasattr(self, 'webhook_list_layout'):
            return
        while self.webhook_list_layout.count():
            item = self.webhook_list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        webhooks = wecom_config.get_webhooks()
        if not webhooks:
            el = QLabel("暂无配置，请添加企微群 Webhook")
            el.setStyleSheet("color:#888;padding:20px;font-size:12px;")
            el.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.webhook_list_layout.addWidget(el)
            return
        for wh in webhooks:
            row = QWidget()
            rl = QHBoxLayout(row)
            rl.setContentsMargins(4, 4, 4, 4)
            rl.setSpacing(8)
            nl = QLabel(wh["name"])
            nl.setFixedWidth(120)
            nl.setStyleSheet("font-weight:bold;")
            rl.addWidget(nl)
            url = wh["url"]
            disp = url[:30] + "..." + url[-15:] if len(url) > 50 else url
            ul = QLabel(disp)
            ul.setStyleSheet("color:#666;font-size:11px;")
            ul.setToolTip(url)
            rl.addWidget(ul, 1)
            bd = QPushButton("删除")
            bd.setFixedWidth(50)
            bd.setProperty("webhook_name", wh["name"])
            bd.clicked.connect(self._remove_webhook)
            rl.addWidget(bd)
            self.webhook_list_layout.addWidget(row)

    def _add_webhook(self):
        name = self.webhook_name_input.text().strip()
        url = self.webhook_url_input.text().strip()
        if not name:
            QMessageBox.warning(self, "提示", "请输入群名称")
            return
        if not url:
            QMessageBox.warning(self, "提示", "请输入 Webhook URL")
            return
        if not url.startswith("https://qyapi.weixin.qq.com/cgi-bin/webhook/send"):
            QMessageBox.warning(self, "提示", "Webhook URL 格式不正确\n应以 https://qyapi.weixin.qq.com/cgi-bin/webhook/send 开头")
            return
        wecom_config.add_webhook(name, url)
        self.webhook_name_input.clear()
        self.webhook_url_input.clear()
        self._load_webhooks()
        QMessageBox.information(self, "成功", f"已添加 Webhook：{name}")

    def _remove_webhook(self):
        btn = self.sender()
        name = btn.property("webhook_name")
        if QMessageBox.question(
            self, "确认", f'确定要删除 "{name}" 吗？',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes:
            wecom_config.remove_webhook(name)
            self._load_webhooks()

    # ══════════════════════════════════════════════════════
    #  全局 QSS
    # ══════════════════════════════════════════════════════

    @staticmethod
    def _stylesheet() -> str:
        return f"""
            /* ── window ── */
            QDialog {{
                background: {_TOOLBAR_BG};
                font-family: {FONT_FAMILY};
                font-size: 13px;
            }}

            /* ── toolbar / bottom bar ── */
            QWidget#rc_toolbar {{
                background: {_TOOLBAR_BG};
            }}
            QToolButton#rc_tab {{
                background: transparent;
                border: none;
                border-radius: 8px;
                color: #666;
                font-size: 11px;
                padding: 4px 0;
            }}
            QToolButton#rc_tab:checked {{
                background: {_TAB_CHECKED};
                color: #222;
                font-weight: 600;
            }}
            QToolButton#rc_tab:hover:!checked {{
                background: {_TAB_HOVER};
            }}

            /* ── content pages ── */
            QStackedWidget#rc_pages,
            QWidget#rc_page_bg {{
                background: {_CONTENT_BG};
            }}
            QScrollArea {{
                background: {_CONTENT_BG};
                border: none;
            }}
            QScrollArea > QWidget > QWidget {{
                background: {_CONTENT_BG};
            }}

            /* ── form controls ── */

            /* QKeySequenceEdit: outer frame is invisible container */
            QKeySequenceEdit {{
                background: transparent;
                border: none;
                padding: 0px;
            }}
            /* real border lives on the inner QLineEdit */
            QKeySequenceEdit QLineEdit {{
                background: {_CONTENT_BG};
                border: 1px solid {BORDER_DEFAULT};
                border-radius: {RADIUS_MD}px;
                padding: 4px 10px;
                font-size: 13px;
                color: {TEXT_PRIMARY};
            }}
            QKeySequenceEdit QLineEdit:focus {{
                border-color: {ACCENT_PRIMARY};
            }}

            QComboBox {{
                background: {_CONTENT_BG};
                border: 1px solid {BORDER_DEFAULT};
                border-radius: {RADIUS_MD}px;
                padding: 4px 10px;
                font-size: 13px;
                color: {TEXT_PRIMARY};
                min-height: 24px;
            }}
            QComboBox:focus {{
                border-color: {ACCENT_PRIMARY};
            }}
            QComboBox::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: center right;
                width: 20px;
                border: none;
            }}

            /* hotkey page: combo styled identically to QKeySequenceEdit inner QLineEdit */
            QComboBox#hotkey_combo {{
                min-height: 0px;
            }}
            QComboBox#hotkey_combo::drop-down {{
                width: 0px;
                border: none;
            }}

            /* ── prompt list (left panel) ── */
            QListWidget#pm_list {{
                background: transparent;
                border: none;
                outline: none;
                font-size: 13px;
                color: {TEXT_PRIMARY};
            }}
            QListWidget#pm_list::item {{
                padding: 9px 10px;
                border-radius: {RADIUS_SM}px;
                margin: 1px 0;
            }}
            QListWidget#pm_list::item:selected {{
                background: {ACCENT_SUBTLE};
                color: {ACCENT_PRIMARY};
                font-weight: 600;
            }}
            QListWidget#pm_list::item:hover:!selected {{
                background: {BG_HOVER};
            }}

            /* ── misc ── */
            QLabel {{
                background: transparent;
            }}

            /* ── scrollbar ── */
            QScrollBar:vertical {{
                background: transparent;
                width: 6px;
            }}
            QScrollBar::handle:vertical {{
                background: rgba(0,0,0,0.15);
                border-radius: 3px;
                min-height: 30px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: rgba(0,0,0,0.25);
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: transparent;
            }}
        """
