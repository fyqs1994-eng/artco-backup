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
    QProgressDialog, QFileDialog, QSlider, QSpinBox, QGridLayout,
    QGraphicsDropShadowEffect, QApplication, QTextEdit, QRadioButton, QCheckBox,
)
from PySide6.QtCore import Signal, Qt, QPoint, QSize, QTimer
from PySide6.QtGui import QKeySequence, QColor
import qtawesome as qta

# ── qfluentwidgets 集中安全导入 ──
# 该库在模块级执行 print(ALERT)，若进程无控制台句柄（pythonw / 无窗口启动）
# 会抛 OSError(WinError 6)，导致设置面板完全无法创建。
# 这里集中导入一次，失败则整体降级为 PySide6 原生控件。
_QF_AVAILABLE = False
try:
    from qfluentwidgets import (
        PushButton, PrimaryPushButton, LineEdit, TextEdit,
        RadioButton, CheckBox, ComboBox, EditableComboBox,
    )
    _QF_AVAILABLE = True
except Exception:
    # 降级：用原生控件替代，保证设置面板始终可用
    PushButton = QPushButton
    PrimaryPushButton = QPushButton
    LineEdit = QLineEdit
    TextEdit = QTextEdit          # 必须是 QTextEdit（需支持 setPlainText）
    RadioButton = QRadioButton
    CheckBox = QCheckBox
    ComboBox = QComboBox
    EditableComboBox = QComboBox

from config import AI_MODELS, ai_config, model_classifier, wecom_config, ps_config, appearance_config, PRESET_SCHEMES
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


class _CapsulePreview(QWidget):
    """浮窗预览组件 — 与桌面浮窗同尺寸（116×40），带截图/手柄/归档图标"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("capsule_preview")
        self.setFixedSize(136, 60)  # 外框（含阴影空间），与 main.py 一致

        self._container = QWidget(self)
        self._container.setObjectName("preview_container")
        self._container.setFixedSize(116, 40)
        self._container.move(10, 10)

        layout = QHBoxLayout(self._container)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # 截图按钮
        btn_shot = QPushButton()
        btn_shot.setIcon(qta.icon('mdi6.crop', color='#666666'))
        btn_shot.setIconSize(QSize(18, 18))
        btn_shot.setFixedSize(42, 32)
        btn_shot.setEnabled(False)
        layout.addWidget(btn_shot)

        # 拖动手柄
        handle = QLabel()
        handle.setFixedSize(20, 32)
        handle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        handle.setPixmap(qta.icon('mdi6.drag-vertical', color='#888888').pixmap(QSize(20, 20)))
        layout.addWidget(handle)

        # 归档按钮
        btn_arch = QPushButton()
        btn_arch.setIcon(qta.icon('mdi6.archive', color='#666666'))
        btn_arch.setIconSize(QSize(16, 16))
        btn_arch.setFixedSize(42, 32)
        btn_arch.setEnabled(False)
        layout.addWidget(btn_arch)

        # 阴影效果
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(15)
        shadow.setColor(QColor(0, 0, 0, 40))
        shadow.setOffset(0, 3)
        self._container.setGraphicsEffect(shadow)

        self.refresh_background()

    def refresh_background(self):
        """从 appearance_config 刷新背景样式"""
        border_radius = appearance_config.get_border_radius()
        border = appearance_config.get_border_css()
        bg = appearance_config.get_background_css(border_radius=border_radius)

        # 按钮基础样式
        btn_style = """
            QPushButton {
                background-color: transparent;
                border: none;
                border-radius: 8px;
            }
        """

        self._container.setStyleSheet(f"""
            #preview_container {{
                {bg}
                border-radius: {border_radius}px;
                border: {border};
            }}
            {btn_style}
        """)


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


class _ProviderRow(QWidget):
    """服务商列表行：状态圆点 + 名称 + 默认标记"""

    def __init__(self, name: str, has_key: bool, is_default: bool, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background:transparent;")
        rl = QHBoxLayout(self)
        rl.setContentsMargins(10, 0, 8, 0)
        rl.setSpacing(8)

        # 状态圆点
        dot_color = "#52c41a" if has_key else "#d9d9d9"
        self._dot = QLabel()
        self._dot.setFixedSize(8, 8)
        self._dot.setStyleSheet(f"background:{dot_color}; border-radius:4px;")
        rl.addWidget(self._dot)

        name_lbl = QLabel(name)
        name_lbl.setStyleSheet(f"color:{TEXT_PRIMARY}; font-size:13px;")
        rl.addWidget(name_lbl, 1)

        if is_default:
            badge = QLabel("默认")
            badge.setStyleSheet(
                f"color:{ACCENT_PRIMARY}; font-size:10px;"
                f"border:1px solid {ACCENT_PRIMARY}; border-radius:3px; padding:1px 4px;"
            )
            rl.addWidget(badge)


# ══════════════════════════════════════════════════════════════
class SettingsDialog(QDialog):
    """设置对话框 — Raycast 风格"""
    hotkey_changed = Signal()
    update_check_result = Signal(bool, object)
    # 下载进度用信号跨线程回传：普通 threading.Thread 没有 Qt 事件循环，
    # 在该线程里调用 QTimer.singleShot(0, ...) 永远不会触发。
    update_download_progress = Signal(float)  # >=0 为 0.0~1.0 比例；<0 为已下载字节数取负（不确定模式）
    update_download_done = Signal(str)  # 下载完成，参数为新 exe 路径
    update_download_failed = Signal(str)  # 下载失败原因

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.resize(820, 600)
        self.setMinimumSize(780, 540)
        self._current_provider_detail = None
        self._prompt_current_id = None
        self._prompt_data: list = []
        self._update_check_timer = None
        self.update_check_result.connect(self._on_check_result)
        self.update_download_progress.connect(self._on_download_progress)
        self.update_download_done.connect(self._on_download_done)
        self.update_download_failed.connect(self._on_download_fail)
        # 异步拉取 OpenRouter 模型缓存（后台线程，不阻塞 UI）
        model_classifier.ensure_cache_ready()
        self.init_ui()

    def _ensure_on_screen(self):
        """确保对话框完整可见：取消最小化/最大化，并夹紧到屏幕可用区域内"""
        try:
            # 清除 reject()/close() 残留的隐藏状态，否则后续 show() 可能为空操作
            try:
                self.setAttribute(Qt.WidgetAttribute.WA_WState_Hidden, False)
            except Exception:
                pass

            if self.isMinimized():
                self.showNormal()
            if self.windowState() == Qt.WindowState.WindowFullScreen:
                self.showNormal()

            screen = QApplication.primaryScreen()
            if screen is None:
                return
            avail = screen.availableGeometry()

            # 窗口尺寸不超过可用区域
            w = min(self.width(), avail.width())
            h = min(self.height(), avail.height())
            self.resize(w, h)

            geo = self.frameGeometry()
            # 计算目标位置，使其居中于可用区域
            x = avail.x() + max(0, (avail.width() - w) // 2)
            y = avail.y() + max(0, (avail.height() - h) // 2)

            # 若窗口已基本在屏幕内则保留原位置，否则移到居中位置
            inside = (
                geo.x() >= avail.x() - 40
                and geo.y() >= avail.y() - 40
                and geo.right() <= avail.right() + 40
                and geo.bottom() <= avail.bottom() + 40
            )
            if not inside:
                self.move(x, y)

            self.show()
            self.raise_()
            self.activateWindow()

            # ── 兜底：Qt 的 isVisible() 与操作系统的真实状态可能撕裂。
            #    实测复用同一实例时出现 Qt isVisible()=True 但
            #    IsWindowVisible()=False：Qt 自认为已显示，于是把 show()
            #    当空操作跳过，从未向系统下发真正的显示指令，用户看不到窗口。
            #    因此判断依据必须是操作系统的事实，而非 Qt 的自述。
            try:
                if sys.platform == 'win32':
                    import ctypes
                    hwnd = int(self.winId())
                    user32 = ctypes.windll.user32
                    if not user32.IsWindowVisible(hwnd):
                        SW_RESTORE, SW_SHOW = 9, 5
                        if user32.IsIconic(hwnd):
                            user32.ShowWindow(hwnd, SW_RESTORE)
                        user32.ShowWindow(hwnd, SW_SHOW)
                        user32.SetWindowPos(
                            hwnd, 0, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0040)
                        user32.SetForegroundWindow(hwnd)
            except Exception:
                pass
        except Exception:
            import traceback
            traceback.print_exc()

    # ══════════════════════════════════════════════════════
    #  UI 主体
    # ══════════════════════════════════════════════════════

    def init_ui(self):
        # 说明：qfluentwidgets 已在模块顶部集中安全导入（见文件头），
        # 此处直接使用模块级 PushButton / PrimaryPushButton，
        # 避免在函数内重复导入触发无控制台时的 OSError(WinError 6)。
        os.environ.setdefault("QT_API", "pyside6")

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
            ("mdi6.palette-outline",       "外观"),
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
        self._pages.addWidget(self._build_appearance_page())
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
        mapping = {'ai': 0, 'prompt': 1, 'hotkey': 2, 'appearance': 3, 'general': 4, 'wecom': 0}
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
        # PushButton 已在模块顶部集中安全导入

        page = QScrollArea()
        page.setWidgetResizable(True)
        page.setFrameShape(QFrame.Shape.NoFrame)
        page.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        page.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)

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

        # ── 左栏：服务商列表 ──
        left = QWidget()
        left.setFixedWidth(180)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(16, _PAGE_TB, 12, 16)
        ll.setSpacing(8)

        # section label
        sec_lbl = QLabel("服务商")
        sec_lbl.setStyleSheet(f"color:{_SEC_COLOR}; font-size:13px; font-weight:600; padding-left:4px;")
        ll.addWidget(sec_lbl)

        self._provider_list = QListWidget()
        self._provider_list.setObjectName("ai_provider_list")
        self._provider_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._provider_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._provider_list.currentRowChanged.connect(self._on_provider_list_changed)
        ll.addWidget(self._provider_list, 1)

        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.setSpacing(6)
        self.btn_add_provider = QToolButton()
        self.btn_add_provider.setObjectName("icon_btn")
        self.btn_add_provider.setIcon(qta.icon('mdi6.plus', color=ACCENT_PRIMARY))
        self.btn_add_provider.setIconSize(QSize(16, 16))
        self.btn_add_provider.setFixedSize(_ROW_H, _ROW_H)
        self.btn_add_provider.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add_provider.setToolTip("添加")
        self.btn_add_provider.clicked.connect(self._add_provider)
        btn_row.addWidget(self.btn_add_provider)
        self.btn_remove_provider = QToolButton()
        self.btn_remove_provider.setObjectName("icon_btn")
        self.btn_remove_provider.setIcon(qta.icon('mdi6.trash-can', color=COLOR_ERROR))
        self.btn_remove_provider.setIconSize(QSize(16, 16))
        self.btn_remove_provider.setFixedSize(_ROW_H, _ROW_H)
        self.btn_remove_provider.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_remove_provider.setToolTip("删除")
        self.btn_remove_provider.clicked.connect(self._remove_provider)
        btn_row.addWidget(self.btn_remove_provider)
        btn_row.addStretch()
        ll.addLayout(btn_row)

        h.addWidget(left)

        # 竖分割线
        vline = QFrame()
        vline.setFrameShape(QFrame.Shape.VLine)
        vline.setFixedWidth(1)
        vline.setStyleSheet(f"color:{_SEPARATOR};")
        h.addWidget(vline)

        # ── 右栏：详情面板 ──
        self._ai_detail = QWidget()
        self._ai_detail_lay = QVBoxLayout(self._ai_detail)
        self._ai_detail_lay.setContentsMargins(_PAGE_LR, _PAGE_TB, _PAGE_LR, _PAGE_TB)
        self._ai_detail_lay.setSpacing(0)
        h.addWidget(self._ai_detail, 1)

        oh.addWidget(wrapper)
        oh.addStretch(1)
        page.setWidget(outer)

        self._refresh_provider_list()
        # 进入界面时默认选中当前默认供应商
        default_pid = ai_config.get_current_provider_selected()
        default_row = -1
        for i in range(self._provider_list.count()):
            if self._provider_list.item(i).data(Qt.ItemDataRole.UserRole) == default_pid:
                default_row = i
                break
        if default_row >= 0:
            self._provider_list.setCurrentRow(default_row)
        elif self._provider_list.count() > 0:
            self._provider_list.setCurrentRow(0)

        return page

    # ══════════════════════════════════════════════════════
    #  PAGE 1 — Prompt（内联构建，不嵌入外部组件）
    # ══════════════════════════════════════════════════════

    def _build_prompt_page(self):
        # PushButton/PrimaryPushButton/LineEdit/TextEdit/RadioButton/CheckBox
        # 已在模块顶部集中安全导入

        page = QScrollArea()
        page.setWidgetResizable(True)
        page.setFrameShape(QFrame.Shape.NoFrame)
        page.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        page.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)

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
        left.setFixedWidth(180)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(16, _PAGE_TB, 12, 16)
        ll.setSpacing(8)

        sec_lbl = QLabel("Prompt")
        sec_lbl.setStyleSheet(f"color:{_SEC_COLOR}; font-size:13px; font-weight:600; padding-left:4px;")
        ll.addWidget(sec_lbl)

        self._prompt_list = QListWidget()
        self._prompt_list.setObjectName("pm_list")
        self._prompt_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._prompt_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._prompt_list.currentRowChanged.connect(self._on_prompt_selected)
        ll.addWidget(self._prompt_list, 1)

        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.setSpacing(6)
        btn_add = QToolButton()
        btn_add.setObjectName("icon_btn")
        btn_add.setIcon(qta.icon('mdi6.plus', color=ACCENT_PRIMARY))
        btn_add.setIconSize(QSize(16, 16))
        btn_add.setFixedSize(_ROW_H, _ROW_H)
        btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_add.setToolTip("新增")
        btn_add.clicked.connect(self._add_prompt)
        btn_row.addWidget(btn_add)
        btn_del = QToolButton()
        btn_del.setObjectName("icon_btn")
        btn_del.setIcon(qta.icon('mdi6.trash-can', color=COLOR_ERROR))
        btn_del.setIconSize(QSize(16, 16))
        btn_del.setFixedSize(_ROW_H, _ROW_H)
        btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_del.setToolTip("删除")
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
        # PushButton 已在模块顶部集中安全导入

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
    #  PAGE 3 — 外观（浮窗背景自定义）
    # ══════════════════════════════════════════════════════

    def _build_appearance_page(self):
        # PushButton / PrimaryPushButton 已在模块顶部集中安全导入

        page, lay = self._scroll_page()

        # ── section: 浮窗背景 ──
        lay.addWidget(self._section("浮窗背景"))
        lay.addSpacing(_SEC_GAP)

        # ── 主区域：QGridLayout 保证两行跨列对齐 ──
        grid = QGridLayout()
        grid.setVerticalSpacing(8)
        grid.setHorizontalSpacing(24)
        grid.setAlignment(Qt.AlignmentFlag.AlignTop)

        # Row 0 — Col 0: 地址栏（top margin 10px 补偿右侧浮窗阴影留白）
        self._appearance_img_edit = QLineEdit()
        self._appearance_img_edit.setPlaceholderText("选择图片文件作为浮窗背景…")
        self._appearance_img_edit.setFixedHeight(_ROW_H)
        cur_cfg = appearance_config.get_config()
        cur_type = cur_cfg.get("type", "gradient")
        cur_img = appearance_config.get("image_path", "")
        if cur_type == "image":
            self._appearance_img_edit.setText(cur_img)

        addr_wrap = QWidget()
        addr_lay = QVBoxLayout(addr_wrap)
        addr_lay.setContentsMargins(0, 10, 0, 0)   # top=10 对齐浮窗可视区
        addr_lay.addWidget(self._appearance_img_edit)
        grid.addWidget(addr_wrap, 0, 0, Qt.AlignmentFlag.AlignTop)

        # Row 0 — Col 1: 浮窗预览（136×60，含阴影留白）
        self._appearance_preview = _CapsulePreview()
        grid.addWidget(self._appearance_preview, 0, 1, Qt.AlignmentFlag.AlignTop)

        # Row 1 — Col 0: 浏览 / 清除按钮
        btn_widget = QWidget()
        btn_row = QHBoxLayout(btn_widget)
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.setSpacing(8)
        browse_btn = PushButton("浏览…")
        browse_btn.setFixedHeight(_ROW_H)
        browse_btn.setFixedWidth(80)
        browse_btn.clicked.connect(self._browse_image)
        btn_row.addWidget(browse_btn)

        clear_btn = PushButton("清除图片")
        clear_btn.setFixedHeight(_ROW_H)
        clear_btn.setFixedWidth(80)
        clear_btn.clicked.connect(self._clear_appearance_image)
        btn_row.addWidget(clear_btn)
        btn_row.addStretch()
        grid.addWidget(btn_widget, 1, 0, Qt.AlignmentFlag.AlignTop)

        # Row 1 — Col 1: 预览效果按钮
        preview_btn_wrap = QWidget()
        pv_lay = QVBoxLayout(preview_btn_wrap)
        pv_lay.setContentsMargins(0, 0, 0, 0)
        preview_btn = PrimaryPushButton("预览效果")
        preview_btn.setFixedHeight(_ROW_H)
        preview_btn.setFixedWidth(100)
        preview_btn.clicked.connect(self._preview_appearance)
        pv_lay.addWidget(preview_btn, 0, Qt.AlignmentFlag.AlignHCenter)
        grid.addWidget(preview_btn_wrap, 1, 1, Qt.AlignmentFlag.AlignTop)

        lay.addLayout(grid)
        lay.addSpacing(8)

        tip = self._tip("预览效果与桌面浮窗保持一致。选择图片后点击预览即可应用到桌面浮窗。")
        lay.addWidget(tip)
        lay.addStretch()

        # 初始更新预览
        self._update_capsule_preview()
        return page

    @staticmethod
    def _wrap_hbox(layout: QHBoxLayout) -> QWidget:
        """将一个 QHBoxLayout 包装为 QWidget，便于嵌入 _form_row"""
        w = QWidget()
        w.setLayout(layout)
        return w

    def _clear_appearance_image(self):
        """清除图片背景，恢复为渐变"""
        self._appearance_img_edit.clear()
        appearance_config.set_gradient(
            appearance_config.get("direction", "diagonal"),
            appearance_config.get("stops", [])
        )
        self._update_capsule_preview()

    def _browse_image(self):
        """浏览选择图片文件"""
        path, _ = QFileDialog.getOpenFileName(
            self, "选择背景图片", "", "图片文件 (*.png *.jpg *.jpeg *.bmp)"
        )
        if path:
            self._appearance_img_edit.setText(path)

    def _preview_appearance(self):
        """预览当前外观设置 — 应用到桌面浮窗"""
        img_path = self._appearance_img_edit.text().strip()
        if img_path:
            appearance_config.set_image(img_path)
        else:
            appearance_config.set_gradient(
                appearance_config.get("direction", "diagonal"),
                appearance_config.get("stops", [])
            )
        # 更新设置页内的预览
        self._update_capsule_preview()
        # 发信号通知桌面浮窗刷新
        if hasattr(self, '_appearance_preview_callback'):
            self._appearance_preview_callback()

    def _update_capsule_preview(self):
        """更新设置页内的浮窗预览"""
        if hasattr(self, '_appearance_preview'):
            self._appearance_preview.refresh_background()

    # ══════════════════════════════════════════════════════
    #  PAGE 4 — 通用
    # ══════════════════════════════════════════════════════

    def _build_general_page(self):
        # CheckBox / ComboBox 已在模块顶部集中安全导入

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

        self.btn_check_update = PushButton("检查更新")
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

    def _get_provider_info(self, provider_id):
        """统一获取服务商信息（预设 + 自定义），返回 dict 或 None"""
        from config import AI_PROVIDERS
        if provider_id in AI_PROVIDERS:
            p = AI_PROVIDERS[provider_id]
            return {
                "name": p["name"],
                "models": p.get("models", []),
                "key_url": p.get("key_url", ""),
                "default_vision": p.get("default_vision", ""),
                "default_image_gen": p.get("default_image_gen", ""),
                "is_custom": False,
            }
        custom = ai_config.get_custom_provider_info(provider_id)
        if custom:
            return {
                "name": custom["name"],
                "models": [],
                "key_url": custom.get("key_url", ""),
                "default_vision": custom.get("vision_models", [""])[0] if custom.get("vision_models") else "",
                "default_image_gen": custom.get("image_gen_models", [""])[0] if custom.get("image_gen_models") else "",
                "is_custom": True,
                "base_url": custom.get("base_url", ""),
                "vision_models": custom.get("vision_models", []),
                "image_gen_models": custom.get("image_gen_models", []),
            }
        return None

    def _refresh_provider_list(self):
        """刷新左侧服务商列表"""
        current_pid = self._current_provider_detail
        self._provider_list.blockSignals(True)
        self._provider_list.clear()

        enabled = ai_config.get_enabled_providers()
        current_selected = ai_config.get_current_provider_selected()
        restore_row = -1

        # 按是否有 API key 分组：有 key 的在上（按新建顺序），无 key 的在下（按新建顺序）
        with_key = []
        without_key = []
        for pid in enabled:
            if ai_config.get_api_key(pid):
                with_key.append(pid)
            else:
                without_key.append(pid)
        ordered = with_key + without_key

        for i, pid in enumerate(ordered):
            info = self._get_provider_info(pid)
            if not info:
                continue
            name = info["name"]
            has_key = bool(ai_config.get_api_key(pid))
            is_default = pid == current_selected

            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, pid)
            item.setSizeHint(QSize(0, 42))
            self._provider_list.addItem(item)

            row_w = _ProviderRow(name, has_key, is_default)
            self._provider_list.setItemWidget(item, row_w)

            if pid == current_pid:
                restore_row = i

        self._provider_list.blockSignals(False)

        if restore_row >= 0:
            self._provider_list.setCurrentRow(restore_row)
        elif self._provider_list.count() > 0:
            self._provider_list.setCurrentRow(0)

    def _on_provider_list_changed(self, row: int):
        """列表选中行变化时，显示对应服务商详情"""
        if row < 0:
            return
        item = self._provider_list.item(row)
        if not item:
            return
        pid = item.data(Qt.ItemDataRole.UserRole)
        if not pid:
            return
        self._current_provider_detail = pid
        self._show_provider_detail(pid)

    def _show_provider_detail(self, provider_id):
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl
        # LineEdit / PushButton / ComboBox / EditableComboBox 已在模块顶部集中安全导入

        self._clear_layout(self._ai_detail_lay)

        provider = self._get_provider_info(provider_id)
        if not provider:
            return

        L = self._ai_detail_lay
        is_current = provider_id == ai_config.get_current_provider_selected()

        # 服务商标题行：名称 + 默认徽章 + 右侧紧凑按钮
        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        title_lbl = QLabel(provider["name"])
        title_lbl.setStyleSheet(f"color:{TEXT_PRIMARY}; font-size:16px; font-weight:600;")
        title_row.addWidget(title_lbl)
        if is_current:
            badge = QLabel("默认")
            badge.setStyleSheet(
                f"color:{ACCENT_PRIMARY}; font-size:10px;"
                f"background:{ACCENT_SUBTLE}; border-radius:3px; padding:2px 6px;"
            )
            title_row.addWidget(badge)
        title_row.addStretch()
        # 紧凑设为默认按钮（右上角）
        if is_current:
            self._btn_set_default = QToolButton()
            self._btn_set_default.setObjectName("icon_btn")
            self._btn_set_default.setProperty("locked", True)
            self._btn_set_default.setIcon(qta.icon('mdi6.star', color='#FFB800'))
            self._btn_set_default.setIconSize(QSize(16, 16))
            self._btn_set_default.setFixedSize(_ROW_H, _ROW_H)
            self._btn_set_default.setToolTip("当前默认服务商")
            title_row.addWidget(self._btn_set_default)
        else:
            self._btn_set_default = QToolButton()
            self._btn_set_default.setObjectName("icon_btn")
            self._btn_set_default.setIcon(qta.icon('mdi6.star-outline', color=TEXT_TERTIARY))
            self._btn_set_default.setIconSize(QSize(16, 16))
            self._btn_set_default.setFixedSize(_ROW_H, _ROW_H)
            self._btn_set_default.setCursor(Qt.CursorShape.PointingHandCursor)
            self._btn_set_default.setToolTip("设为默认")
            self._btn_set_default.clicked.connect(lambda: self._set_default_provider(provider_id))
            title_row.addWidget(self._btn_set_default)
        # 获取 key 链接按钮（问号图标，放在设为默认按钮右侧）
        self._key_url = provider.get("key_url", "")
        if self._key_url:
            self._btn_get_key = QToolButton()
            self._btn_get_key.setObjectName("icon_btn")
            self._btn_get_key.setIcon(qta.icon('mdi6.help-circle-outline', color=TEXT_TERTIARY))
            self._btn_get_key.setIconSize(QSize(16, 16))
            self._btn_get_key.setFixedSize(_ROW_H, _ROW_H)
            self._btn_get_key.setCursor(Qt.CursorShape.PointingHandCursor)
            self._btn_get_key.setToolTip(f"获取 {provider['name']} API Key")
            self._btn_get_key.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(self._key_url)))
            title_row.addWidget(self._btn_get_key)
        L.addLayout(title_row)
        L.addSpacing(_BLOCK_GAP)

        # section: 连接
        L.addWidget(self._section("连接"))
        L.addSpacing(_SEC_GAP)

        # API Key（堆叠式）
        lbl_key = QLabel("API Key")
        lbl_key.setStyleSheet(f"color:{_FORM_LABEL}; font-size:12px;")
        L.addWidget(lbl_key)
        L.addSpacing(4)
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
        self._btn_verify_key.setFixedWidth(64)
        self._btn_verify_key.clicked.connect(self._verify_provider_key)
        kh.addWidget(self._btn_verify_key)
        L.addWidget(key_w)
        L.addSpacing(6)

        # 内联验证状态标签
        self._verify_status_lbl = QLabel()
        self._verify_status_lbl.setStyleSheet("color:transparent; font-size:11px;")
        self._verify_status_lbl.setFixedHeight(16)
        L.addWidget(self._verify_status_lbl)
        L.addSpacing(_ROW_GAP)

        # Base URL（堆叠式）
        lbl_url = QLabel("Base URL")
        lbl_url.setStyleSheet(f"color:{_FORM_LABEL}; font-size:12px;")
        L.addWidget(lbl_url)
        L.addSpacing(4)
        self._provider_base_url = LineEdit()
        self._provider_base_url.setPlaceholderText("自定义 API 地址（可选）")
        self._provider_base_url.setText(ai_config.get_api_base_url(provider_id))
        self._provider_base_url.setFixedHeight(_ROW_H)
        L.addWidget(self._provider_base_url)
        L.addSpacing(_BLOCK_GAP)

        # section: 模型
        L.addWidget(self._section("模型"))
        L.addSpacing(_SEC_GAP)

        # 视觉分析模型
        all_vision = ai_config.get(f"{provider_id}_vision_models", [])
        if not all_vision:
            if provider.get("is_custom"):
                all_vision = provider.get("vision_models", [])
            else:
                all_vision = [m.get("name", m["id"]) for m in AI_MODELS.get("vision", []) if m.get("provider") == provider_id]

        # 视觉分析模型（堆叠式）
        lbl_v = QLabel("视觉分析模型")
        lbl_v.setStyleSheet(f"color:{_FORM_LABEL}; font-size:12px;")
        L.addWidget(lbl_v)
        L.addSpacing(4)
        # 自定义服务商使用可编辑下拉框，支持手动输入模型名
        is_custom = provider.get("is_custom", False)
        if is_custom and EditableComboBox is not None:
            self._vision_model_combo = EditableComboBox()
            self._vision_model_combo.setPlaceholderText("输入或选择模型名")
        else:
            self._vision_model_combo = ComboBox()
        self._vision_model_combo.setFixedHeight(_ROW_H)
        if all_vision:
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
        else:
            if is_custom and EditableComboBox is not None:
                self._vision_model_combo.addItem("", "")
                # 保持可用，用户可手动输入
            else:
                self._vision_model_combo.addItem("无可用模型", "")
                self._vision_model_combo.setEnabled(False)
        L.addWidget(self._vision_model_combo)
        L.addSpacing(_ROW_GAP)

        # 图像生成模型
        all_img = ai_config.get(f"{provider_id}_image_gen_models", [])
        if not all_img:
            if provider.get("is_custom"):
                all_img = provider.get("image_gen_models", [])
            else:
                defs = [m for m in AI_MODELS.get("image_gen", []) if m.get("provider") == provider_id]
                if defs:
                    all_img = [m["id"] for m in defs]

        # 图像生成模型（堆叠式）
        lbl_ig = QLabel("图像生成模型")
        lbl_ig.setStyleSheet(f"color:{_FORM_LABEL}; font-size:12px;")
        L.addWidget(lbl_ig)
        L.addSpacing(4)
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
        L.addWidget(self._image_gen_model_combo)
        L.addSpacing(_BLOCK_GAP)

        L.addStretch()

    def _add_provider(self):
        from config import AI_PROVIDERS
        enabled = ai_config.get_enabled_providers()
        available = [p for p in AI_PROVIDERS if p not in enabled]
        menu = QMenu(self)
        menu.setStyleSheet(MENU_STYLE)

        # 预设服务商
        for pid in available:
            a = menu.addAction(AI_PROVIDERS[pid]["name"])
            a.setData(pid)

        # 自定义选项（始终可选）
        if available:
            menu.addSeparator()
        custom_action = menu.addAction("＋ 自定义服务商…")
        custom_action.setData("__custom__")

        pos = self.btn_add_provider.mapToGlobal(QPoint(0, self.btn_add_provider.height()))
        a = menu.exec(pos)
        if not a:
            return

        if a.data() == "__custom__":
            self._show_custom_provider_dialog()
        else:
            ai_config.add_provider(a.data())
            self._refresh_provider_list()
            for i in range(self._provider_list.count()):
                item = self._provider_list.item(i)
                if item and item.data(Qt.ItemDataRole.UserRole) == a.data():
                    self._provider_list.setCurrentRow(i)
                    break

    def _delete_provider_by_id(self, provider_id):
        """通过详情面板的删除按钮删除指定服务商"""
        info = self._get_provider_info(provider_id)
        name = info["name"] if info else provider_id
        if QMessageBox.question(
            self, "确认删除", f'确定要删除服务商 "{name}" 吗？',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes:
            ai_config.remove_provider(provider_id)
            # 如果是自定义服务商，同时清理记录
            if ai_config.is_custom_provider(provider_id):
                ai_config.remove_custom_provider(provider_id)
            self._refresh_provider_list()

    def _remove_provider(self):
        """通过左栏删除按钮删除当前选中的服务商"""
        row = self._provider_list.currentRow()
        if row < 0:
            return
        item = self._provider_list.item(row)
        if not item:
            return
        pid = item.data(Qt.ItemDataRole.UserRole)
        if pid:
            self._delete_provider_by_id(pid)

    def _set_default_provider(self, provider_id):
        from config import AI_PROVIDERS
        ai_config.set_current_provider_selected(provider_id)
        self._refresh_provider_list()
        self._show_provider_detail(provider_id)

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
            self._verify_status_lbl.setStyleSheet(f"color:{COLOR_ERROR}; font-size:11px;")
            self._verify_status_lbl.setText("⚠ 请输入 API Key")
            return
        self._btn_verify_key.setEnabled(False)
        self._btn_verify_key.setText("验证中…")
        self._verify_status_lbl.setStyleSheet(f"color:{TEXT_TERTIARY}; font-size:11px;")
        self._verify_status_lbl.setText("正在验证…")
        # 触发异步拉取 OpenRouter 模型缓存（不阻塞验证流程）
        model_classifier.ensure_cache_ready()
        try:
            # 自定义服务商走通用 OpenAI 兼容验证
            if ai_config.is_custom_provider(provider_id):
                base_url = ai_config.get_api_base_url(provider_id)
                success, message, models = self._verify_custom_key(api_key, base_url)
            else:
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
                    success, message, models = False, f"未知服务商: {provider_id}", {}

            if success:
                self._verify_status_lbl.setStyleSheet(f"color:#52c41a; font-size:11px;")
                self._verify_status_lbl.setText(f"✓ {message}")
                ai_config.set_api_key(provider_id, api_key)
                if hasattr(self, '_provider_base_url'):
                    ai_config.set_api_base_url(provider_id, self._provider_base_url.text().strip())
                ai_config.set(f"{provider_id}_vision_models", models.get("vision", []))
                ai_config.set(f"{provider_id}_image_gen_models", models.get("image_gen", []))
                self._refresh_provider_list()
                self._show_provider_detail(provider_id)
            else:
                self._verify_status_lbl.setStyleSheet(f"color:{COLOR_ERROR}; font-size:11px;")
                self._verify_status_lbl.setText(f"✗ {message}")
        except Exception as e:
            self._verify_status_lbl.setStyleSheet(f"color:{COLOR_ERROR}; font-size:11px;")
            self._verify_status_lbl.setText(f"✗ 验证出错: {str(e)}")
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
            classified = model_classifier.classify_batch(all_models)
            return True, f"有效 Key，共发现 {len(all_models)} 个模型（视觉 {len(classified['vision'])} / 图像生成 {len(classified['image_gen'])}）", classified
        except Exception as e:
            import requests
            try:
                resp = requests.get(f"https://generativelanguage.googleapis.com/v1/models?key={api_key}", timeout=10)
                if resp.status_code == 200:
                    models = resp.json().get("models", [])
                    all_m = [m.get("name", "").removeprefix("models/") for m in models]
                    classified = model_classifier.classify_batch(all_m)
                    return True, f"有效 Key，共发现 {len(all_m)} 个模型（视觉 {len(classified['vision'])} / 图像生成 {len(classified['image_gen'])}）", classified
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
                classified = model_classifier.classify_batch(all_m)
                return True, f"有效 Key，共发现 {len(all_m)} 个模型（视觉 {len(classified['vision'])} / 图像生成 {len(classified['image_gen'])}）", classified
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
                classified = model_classifier.classify_batch(all_m)
                return True, f"有效 Key，共发现 {len(all_m)} 个模型（视觉 {len(classified['vision'])} / 图像生成 {len(classified['image_gen'])}）", classified
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
                classified = model_classifier.classify_batch(all_m)
                return True, f"有效 Key，共发现 {len(all_m)} 个模型（视觉 {len(classified['vision'])} / 图像生成 {len(classified['image_gen'])}）", classified
            if resp.status_code == 401:
                return False, "无效的 API Key", {}
            return False, f"API 返回错误: {resp.status_code}", {}
        except Exception as e:
            return False, str(e), {}

    def _verify_custom_key(self, api_key, base_url):
        """验证自定义服务商（OpenAI 兼容协议）
        尝试多种常见端点路径，适配不同代理（如 Venus /llmproxy/ 路径）。
        """
        import requests

        if not base_url:
            base_url = "https://api.openai.com"
        base_url = base_url.rstrip("/")

        # 按优先级尝试的模型列表端点
        model_endpoints = [
            f"{base_url}/v1/models",
            f"{base_url}/llmproxy/models",
            f"{base_url}/models",
        ]
        headers = {"Authorization": f"Bearer {api_key}"}

        # 1) 先尝试 GET models 端点
        for url in model_endpoints:
            try:
                resp = requests.get(url, headers=headers, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    all_m = [m.get("id") for m in data.get("data", [])] if isinstance(data, dict) else []
                    if not all_m and isinstance(data, dict):
                        all_m = [m.get("name", "").removeprefix("models/") for m in data.get("models", [])]
                    if not all_m:
                        all_m = [m.get("id", "") for m in data] if isinstance(data, list) else []
                    all_m = [m for m in all_m if m]
                    classified = model_classifier.classify_batch(all_m)
                    return True, f"有效 Key，共发现 {len(all_m)} 个模型（视觉 {len(classified['vision'])} / 图像生成 {len(classified['image_gen'])}）", classified
                # 401/403 = Key 问题，直接返回（不继续尝试其他端点）
                if resp.status_code in (401, 403):
                    return False, f"无效的 API Key（HTTP {resp.status_code}）", {}
                # 400/404/其他 = 此端点不可用，尝试下一个
            except Exception:
                continue

        # 2) models 端点全部不可用，尝试发一个最简 chat 请求验证 Key 有效性
        chat_endpoints = [
            f"{base_url}/v1/chat/completions",
            f"{base_url}/llmproxy/chat/completions",
            f"{base_url}/chat/completions",
        ]
        test_payload = {
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 1,
        }
        for url in chat_endpoints:
            try:
                resp = requests.post(url, headers={**headers, "Content-Type": "application/json"},
                                     json=test_payload, timeout=15)
                if resp.status_code in (200, 400):
                    # 200 = Key 有效且请求成功；400 = Key 有效但模型名等参数不对
                    return True, "Key 验证通过（无法自动获取模型列表，请手动填写）", {"vision": [], "image_gen": []}
                if resp.status_code in (401, 403):
                    # 401/403 = Key 无效或账户问题
                    try:
                        err_msg = resp.json().get("msg", "")
                    except Exception:
                        err_msg = ""
                    return False, f"无效的 API Key（{err_msg}）" if err_msg else f"无效的 API Key（HTTP {resp.status_code}）", {}
                # 404 = 此端点不存在，尝试下一个
            except Exception:
                continue

        return False, "无法连接到服务，请检查 Base URL 是否正确", {}

    def _show_custom_provider_dialog(self):
        """添加自定义服务商对话框"""
        # LineEdit / PushButton 已在模块顶部集中安全导入

        dlg = QDialog(self)
        dlg.setWindowTitle("添加自定义服务商")
        dlg.setFixedWidth(420)
        dlg.setStyleSheet(f"QDialog {{ background:{BG_HOVER}; }}")

        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(24, 24, 24, 24)
        lay.setSpacing(12)

        # 名称
        lbl_name = QLabel("服务商名称")
        lbl_name.setStyleSheet(f"color:{_FORM_LABEL}; font-size:12px;")
        lay.addWidget(lbl_name)
        name_edit = LineEdit()
        name_edit.setPlaceholderText("如：DeepSeek、Ollama、我的中转站")
        name_edit.setFixedHeight(_ROW_H)
        lay.addWidget(name_edit)
        lay.addSpacing(4)

        # Base URL
        lbl_url = QLabel("Base URL")
        lbl_url.setStyleSheet(f"color:{_FORM_LABEL}; font-size:12px;")
        lay.addWidget(lbl_url)
        url_edit = LineEdit()
        url_edit.setPlaceholderText("如：https://api.deepseek.com（可选，默认 OpenAI）")
        url_edit.setFixedHeight(_ROW_H)
        lay.addWidget(url_edit)
        lay.addSpacing(4)

        # API Key（可选，可稍后在详情页填写）
        lbl_key = QLabel("API Key（可选，可稍后填写）")
        lbl_key.setStyleSheet(f"color:{_FORM_LABEL}; font-size:12px;")
        lay.addWidget(lbl_key)
        key_edit = LineEdit()
        key_edit.setPlaceholderText("粘贴 API Key")
        key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        key_edit.setFixedHeight(_ROW_H)
        lay.addWidget(key_edit)
        lay.addSpacing(4)

        # 模型列表（可选）
        lbl_models = QLabel("模型列表（可选，逗号分隔，可验证后自动获取）")
        lbl_models.setStyleSheet(f"color:{_FORM_LABEL}; font-size:12px;")
        lay.addWidget(lbl_models)
        models_edit = LineEdit()
        models_edit.setPlaceholderText("如：deepseek-chat, deepseek-coder")
        models_edit.setFixedHeight(_ROW_H)
        lay.addWidget(models_edit)
        lay.addSpacing(16)

        # 按钮行
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = PushButton("取消")
        cancel_btn.setFixedHeight(_ROW_H)
        cancel_btn.setFixedWidth(80)
        cancel_btn.clicked.connect(dlg.reject)
        btn_row.addWidget(cancel_btn)
        ok_btn = PushButton("添加")
        ok_btn.setFixedHeight(_ROW_H)
        ok_btn.setFixedWidth(80)
        ok_btn.clicked.connect(dlg.accept)
        btn_row.addWidget(ok_btn)
        lay.addLayout(btn_row)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        name = name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "提示", "请输入服务商名称")
            return

        # 生成唯一 ID
        import uuid
        provider_id = f"custom_{uuid.uuid4().hex[:8]}"
        base_url = url_edit.text().strip()
        api_key = key_edit.text().strip()
        models_text = models_edit.text().strip()
        vision_models = [m.strip() for m in models_text.split(",") if m.strip()] if models_text else []

        # 添加到配置
        ai_config.add_custom_provider(
            provider_id=provider_id,
            name=name,
            base_url=base_url,
            key_url="",
            vision_models=vision_models,
            image_gen_models=[],
        )
        if api_key:
            ai_config.set_api_key(provider_id, api_key)
        if base_url:
            ai_config.set_api_base_url(provider_id, base_url)

        self._refresh_provider_list()
        # 选中新添加的项
        for i in range(self._provider_list.count()):
            item = self._provider_list.item(i)
            if item and item.data(Qt.ItemDataRole.UserRole) == provider_id:
                self._provider_list.setCurrentRow(i)
                break

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
                # 可编辑下拉框：data 为空时取用户输入的文本
                if not v:
                    v = self._vision_model_combo.currentText().strip()
                if v:
                    ai_config.set("vision_model", v)
            if hasattr(self, '_image_gen_model_combo'):
                v = self._image_gen_model_combo.currentData()
                if not v:
                    v = self._image_gen_model_combo.currentText().strip()
                if v:
                    ai_config.set("image_gen_model", v)
                    # 同时记录图像生成模型所属的 provider
                    ai_config.set("image_gen_provider", pid)

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

        # 兜底定时器：15 秒后强制恢复按钮状态（防止网络挂死导致 UI 卡死）
        self._update_check_timer = QTimer(self)
        self._update_check_timer.setSingleShot(True)
        self._update_check_timer.timeout.connect(self._on_check_timeout)
        self._update_check_timer.start(15000)

        def do_check():
            has_update, info = updater_mod.check_for_update()
            updater_mod._save_check_time()
            self.update_check_result.emit(has_update, info)

        threading.Thread(target=do_check, daemon=True).start()

    def _on_check_timeout(self):
        """检查超时兜底：恢复按钮状态并提示"""
        if self._update_check_timer:
            self._update_check_timer.stop()
            self._update_check_timer = None
        self.btn_check_update.setEnabled(True)
        self.btn_check_update.setText("检查更新")
        QMessageBox.warning(self, "检查更新", "网络超时，请稍后重试。")

    def _on_check_result(self, has_update: bool, info):
        """检查结果回调"""
        if self._update_check_timer:
            self._update_check_timer.stop()
            self._update_check_timer = None
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
        self._update_progress.setAutoReset(False)  # 到达 100% 时不要自动清零
        self._update_cancelled = False
        self._update_info = info
        self._update_progress.canceled.connect(lambda: setattr(self, '_update_cancelled', True))
        self._update_progress.show()

        def download_thread():
            # 普通 threading.Thread 无 Qt 事件循环，QTimer.singleShot(0, ...) 不会触发，
            # 必须用信号回传主线程，否则进度条永远不动。
            try:
                new_path = updater_mod.download_update(
                    info,
                    progress_callback=self.update_download_progress.emit,
                    should_cancel=lambda: self._update_cancelled,
                )
                if self._update_cancelled:
                    return
                self.update_download_done.emit(new_path)
            except Exception as e:
                self.update_download_failed.emit(str(e))

        threading.Thread(target=download_thread, daemon=True).start()

    def _on_download_progress(self, ratio: float):
        """下载进度（信号投递，运行在主线程，可直接操作 UI）"""
        if not hasattr(self, '_update_progress') or self._update_progress is None:
            return
        if ratio >= 0:
            self._update_progress.setValue(int(ratio * 100))
        else:
            self._update_progress.setLabelText(f"正在下载… 已下载 {-ratio / (1024 * 1024):.1f} MB")

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

            /* ── icon action buttons (add/delete/set-default) ── */
            QToolButton#icon_btn {{
                background: {_CONTENT_BG};
                border: 1px solid {BORDER_DEFAULT};
                border-radius: {RADIUS_SM}px;
                padding: 0px;
            }}
            QToolButton#icon_btn:hover {{
                background: {BG_HOVER};
                border-color: {ACCENT_PRIMARY};
            }}
            QToolButton#icon_btn:pressed {{
                background: {ACCENT_SUBTLE};
            }}
            QToolButton#icon_btn:disabled {{
                background: transparent;
                border: 1px solid {BORDER_DEFAULT};
            }}

            /* ── 当前默认服务商的星星按钮（不禁用，仅视觉锁定）── */
            QToolButton#icon_btn[locked="true"] {{
                background: {_CONTENT_BG};
                border: 1px solid {BORDER_DEFAULT};
                border-radius: {RADIUS_SM}px;
                padding: 0px;
            }}

            /* ── prompt list (left panel) ── */
            QListWidget#pm_list,
            QListWidget#ai_provider_list {{
                background: transparent;
                border: none;
                outline: none;
                font-size: 13px;
                color: {TEXT_PRIMARY};
            }}
            QListWidget#pm_list::item,
            QListWidget#ai_provider_list::item {{
                padding: 9px 10px;
                border-radius: {RADIUS_SM}px;
                margin: 1px 0;
            }}
            QListWidget#pm_list::item:selected,
            QListWidget#ai_provider_list::item:selected {{
                background: {ACCENT_SUBTLE};
                color: {ACCENT_PRIMARY};
                font-weight: 600;
            }}
            QListWidget#pm_list::item:hover:!selected,
            QListWidget#ai_provider_list::item:hover:!selected {{
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
