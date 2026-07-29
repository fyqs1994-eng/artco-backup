"""
Prompt 管理模块 — Raycast 风格
左侧列表 + 右侧表单，零装饰
"""

import os
import qtawesome as qta
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QTextEdit,
    QPushButton, QListWidget, QListWidgetItem, QFormLayout,
    QMenu, QMessageBox, QFrame,
)
from PySide6.QtCore import Qt, Signal, QTimer

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

_CONTENT_BG = "#FFFFFF"
_SEC_COLOR = "rgba(0,0,0,0.40)"
_FORM_LABEL = "rgba(0,0,0,0.55)"
_ROW_H = 34


class PromptManagementPanel(QWidget):
    """可嵌入的 Prompt 管理面板 — Raycast Extensions 风格"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_prompt_id = None
        self.init_ui()
        self.load_prompts()

    def init_ui(self):
        os.environ.setdefault("QT_API", "pyside6")
        from qfluentwidgets import PushButton, PrimaryPushButton, LineEdit, TextEdit, RadioButton, CheckBox

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── 左侧：列表 ──
        left = QWidget()
        left.setObjectName("pm_left")
        left.setFixedWidth(240)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(16, 20, 12, 16)
        ll.setSpacing(8)

        self.prompt_list = QListWidget()
        self.prompt_list.setObjectName("pm_list")
        self.prompt_list.currentRowChanged.connect(self._on_prompt_selected)
        ll.addWidget(self.prompt_list, 1)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        self.btn_add = PushButton("新增")
        self.btn_add.setIcon(qta.icon('mdi6.plus', color=ACCENT_PRIMARY))
        self.btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add.setFixedHeight(_ROW_H)
        self.btn_add.clicked.connect(self._add_prompt)
        btn_row.addWidget(self.btn_add)

        self.btn_delete = PushButton("删除")
        self.btn_delete.setIcon(qta.icon('mdi6.trash-can', color=COLOR_ERROR))
        self.btn_delete.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_delete.setFixedHeight(_ROW_H)
        self.btn_delete.clicked.connect(self._delete_prompt)
        btn_row.addWidget(self.btn_delete)
        btn_row.addStretch()

        ll.addLayout(btn_row)
        layout.addWidget(left)

        # 竖分割线
        vline = QFrame()
        vline.setFrameShape(QFrame.Shape.VLine)
        vline.setFixedWidth(1)
        vline.setStyleSheet("color: #e8e8e8;")
        layout.addWidget(vline)

        # ── 右侧：编辑区 ──
        right = QWidget()
        right.setObjectName("pm_right")
        rl = QVBoxLayout(right)
        rl.setContentsMargins(28, 20, 28, 16)
        rl.setSpacing(0)

        # section: 基本信息
        sec1 = QLabel("基本信息")
        sec1.setStyleSheet(f"color:{_SEC_COLOR}; font-size:11px; font-weight:700; letter-spacing:0.5px; padding-bottom:2px;")
        rl.addWidget(sec1)
        rl.addSpacing(10)

        self.title_input = LineEdit()
        self.title_input.setPlaceholderText("输入 Prompt 标题…")
        self.title_input.setFixedHeight(_ROW_H)
        rl.addLayout(self._form_row("标题", self.title_input))
        rl.addSpacing(8)

        type_w = QWidget()
        tw_l = QHBoxLayout(type_w)
        tw_l.setContentsMargins(0, 0, 0, 0)
        tw_l.setSpacing(16)
        self.type_text_radio = RadioButton("文本/识图 (Vision)")
        self.type_text_radio.setChecked(True)
        tw_l.addWidget(self.type_text_radio)
        self.type_image_radio = RadioButton("生图/重绘 (Image Gen)")
        tw_l.addWidget(self.type_image_radio)
        tw_l.addStretch()
        rl.addLayout(self._form_row("类型", type_w))
        rl.addSpacing(8)

        self.default_checkbox = CheckBox("设为默认 Prompt")
        rl.addLayout(self._form_row("", self.default_checkbox))
        rl.addSpacing(24)

        # section: 内容
        sec2 = QLabel("Prompt 内容")
        sec2.setStyleSheet(f"color:{_SEC_COLOR}; font-size:11px; font-weight:700; letter-spacing:0.5px; padding-bottom:2px;")
        rl.addWidget(sec2)
        rl.addSpacing(10)

        self.content_input = TextEdit()
        self.content_input.setPlaceholderText("输入 Prompt 内容…")
        self.content_input.setMinimumHeight(160)
        rl.addWidget(self.content_input, 1)
        rl.addSpacing(14)

        save_row = QHBoxLayout()
        save_row.addStretch()
        self.btn_save = PrimaryPushButton("保存修改")
        self.btn_save.setIcon(qta.icon('mdi6.content-save', color='white'))
        self.btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save.setFixedHeight(_ROW_H)
        self.btn_save.setMinimumWidth(110)
        self.btn_save.clicked.connect(self._save_prompt)
        save_row.addWidget(self.btn_save)
        rl.addLayout(save_row)

        layout.addWidget(right, 1)

        self.setStyleSheet(self._qss())

    # ── 小组件 ────────────────────────────────────────────

    @staticmethod
    def _form_row(label_text: str, widget: QWidget) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(10)
        lbl = QLabel(label_text)
        lbl.setFixedWidth(48)
        lbl.setStyleSheet(f"color:{_FORM_LABEL}; font-size:13px;")
        lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(lbl)
        row.addWidget(widget, 1)
        return row

    # ── 数据 ──────────────────────────────────────────────

    def load_prompts(self):
        self.prompt_list.clear()
        self.prompts_data = get_all_prompts()
        for prompt in self.prompts_data:
            pt = prompt.get("prompt_type", "text")
            icon = qta.icon('mdi6.eye-outline', color=TEXT_TERTIARY) if pt == "text" else qta.icon('mdi6.palette-outline', color=TEXT_TERTIARY)
            title = prompt["title"]
            display = f"★ {title}" if prompt["is_default"] else title
            item = QListWidgetItem(icon, display)
            item.setData(Qt.ItemDataRole.UserRole, prompt["id"])
            self.prompt_list.addItem(item)
        if self.prompt_list.count() > 0:
            self.prompt_list.setCurrentRow(0)

    def _on_prompt_selected(self, row: int):
        if row < 0 or row >= len(self.prompts_data):
            self.current_prompt_id = None
            self.title_input.clear()
            self.content_input.clear()
            self.default_checkbox.setChecked(False)
            self.type_text_radio.setChecked(True)
            return
        prompt = self.prompts_data[row]
        self.current_prompt_id = prompt["id"]
        self.title_input.setText(prompt["title"])
        self.content_input.setPlainText(prompt["content"])
        self.default_checkbox.setChecked(prompt["is_default"])
        if prompt.get("prompt_type", "text") == "image":
            self.type_image_radio.setChecked(True)
        else:
            self.type_text_radio.setChecked(True)

    def _add_prompt(self):
        new_id = add_prompt("新建 Prompt", "请输入 Prompt 内容...", prompt_type="text")
        self.load_prompts()
        self._notify_prompts_changed()
        for i in range(self.prompt_list.count()):
            item = self.prompt_list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == new_id:
                self.prompt_list.setCurrentRow(i)
                break
        self.title_input.setFocus()
        self.title_input.selectAll()

    def _delete_prompt(self):
        if not self.current_prompt_id:
            return
        reply = QMessageBox.question(
            self, "确认删除", "确定要删除这个 Prompt 吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            delete_prompt(self.current_prompt_id)
            self.load_prompts()
            self._notify_prompts_changed()

    def _save_prompt(self):
        if not self.current_prompt_id:
            QMessageBox.warning(self, "提示", "请先选择一个 Prompt")
            return
        title = self.title_input.text().strip()
        content = self.content_input.toPlainText().strip()
        is_default = self.default_checkbox.isChecked()
        prompt_type = "image" if self.type_image_radio.isChecked() else "text"
        if not title:
            QMessageBox.warning(self, "提示", "标题不能为空")
            return
        if not content:
            QMessageBox.warning(self, "提示", "内容不能为空")
            return
        update_prompt(self.current_prompt_id, title, content, is_default, prompt_type)
        current_row = self.prompt_list.currentRow()
        self.load_prompts()
        self._notify_prompts_changed()
        if current_row < self.prompt_list.count():
            self.prompt_list.setCurrentRow(current_row)
        self.btn_save.setIcon(qta.icon('mdi6.check', color='white'))
        self.btn_save.setText("已保存")
        QTimer.singleShot(1500, self._reset_save_btn)

    def _reset_save_btn(self):
        self.btn_save.setIcon(qta.icon('mdi6.content-save', color='white'))
        self.btn_save.setText("保存修改")

    def _notify_prompts_changed(self):
        """通知所有活跃的 ScreenshotAICapsule 实例刷新 prompts 缓存和 UI"""
        try:
            from screenshot.toolbar import ScreenshotAICapsule
            ScreenshotAICapsule.refresh_all_instances()
        except Exception:
            pass

    # ── QSS ───────────────────────────────────────────────

    @staticmethod
    def _qss() -> str:
        return f"""
            PromptManagementPanel {{
                background: {_CONTENT_BG};
                font-family: {FONT_FAMILY};
            }}
            QWidget#pm_left {{
                background: {_CONTENT_BG};
            }}
            QWidget#pm_right {{
                background: {_CONTENT_BG};
            }}
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
            QLabel {{
                background: transparent;
            }}
        """


class PromptSettingsWindow(QWidget):
    """Prompt 管理独立窗口"""

    def __init__(self, parent=None, stay_on_top=False):
        super().__init__(parent)
        self.setWindowTitle("Prompt 管理")
        self.setWindowIcon(qta.icon('mdi6.pencil', color=TEXT_TERTIARY))
        if stay_on_top:
            self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        self.setMinimumSize(700, 500)
        self.resize(800, 550)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.panel = PromptManagementPanel(self)
        layout.addWidget(self.panel)


class PromptSelectMenu(QMenu):
    """Prompt 选择菜单"""
    prompt_selected = Signal(str, str)
    edit_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(MENU_STYLE)
        self._build_menu()

    def _build_menu(self):
        self.clear()
        prompts = get_all_prompts()
        if not prompts:
            no_prompt = self.addAction("暂无 Prompt")
            no_prompt.setEnabled(False)
        else:
            for prompt in prompts:
                title = prompt["title"]
                content = prompt["content"]
                prompt_type = prompt.get("prompt_type", "text")
                icon = qta.icon('mdi6.eye-outline', color=TEXT_SECONDARY) if prompt_type == "text" else qta.icon('mdi6.palette-outline', color=TEXT_SECONDARY)
                if prompt["is_default"]:
                    action = self.addAction(icon, f"★ {title}")
                else:
                    action = self.addAction(icon, title)
                action.setData({"content": content, "type": prompt_type})
                action.triggered.connect(lambda checked, c=content, t=prompt_type: self._on_prompt_selected(c, t))
        self.addSeparator()
        manage_action = self.addAction(qta.icon('mdi6.cog-outline', color=TEXT_SECONDARY), "管理 Prompt...")
        manage_action.triggered.connect(self.edit_requested.emit)

    def _on_prompt_selected(self, prompt_content: str, prompt_type: str):
        self.prompt_selected.emit(prompt_content, prompt_type)

    def showEvent(self, event):
        self._build_menu()
        super().showEvent(event)
