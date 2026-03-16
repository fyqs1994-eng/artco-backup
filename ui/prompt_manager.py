"""
Prompt 管理模块
包含 Prompt 设置窗口和选择菜单
"""

import os
import qtawesome as qta
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QTextEdit,
    QPushButton, QListWidget, QListWidgetItem, QGroupBox, QFormLayout,
    QMenu, QMessageBox
)
from PySide6.QtCore import Qt, Signal, QTimer

from database import get_all_prompts, add_prompt, update_prompt, delete_prompt
from ui.theme import (
    get_group_box_style,
    BG_PRIMARY, BG_SECONDARY, BG_HOVER, BG_ACTIVE, BORDER_DEFAULT,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_TERTIARY,
    ACCENT_PRIMARY, ACCENT_HOVER, ACCENT_PRESSED, ACCENT_SUBTLE,
    COLOR_SUCCESS, COLOR_ERROR,
    RADIUS_SM, RADIUS_MD, RADIUS_LG,
    FONT_FAMILY
)




class PromptSettingsWindow(QWidget):
    """Prompt 管理窗口"""
    
    def __init__(self, parent=None, stay_on_top=False):
        super().__init__(parent)
        self.setWindowTitle("Prompt 管理")
        self.setWindowIcon(qta.icon('mdi6.pencil', color=TEXT_TERTIARY))

        if stay_on_top:
            self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        self.setMinimumSize(700, 500)
        self.resize(800, 550)
        self.current_prompt_id = None
        self.init_ui()
        self.load_prompts()
    
    def init_ui(self):
        os.environ.setdefault("QT_API", "pyside6")
        from qfluentwidgets import PushButton, PrimaryPushButton, LineEdit, TextEdit, RadioButton, CheckBox

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)
        
        # ======== 左侧：Prompt 列表 ========
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(12)
        
        list_group = QGroupBox("Prompt 列表")
        list_inner = QVBoxLayout(list_group)
        list_inner.setSpacing(10)
        
        self.prompt_list = QListWidget()
        self.prompt_list.setObjectName("prompt_list")
        self.prompt_list.currentRowChanged.connect(self._on_prompt_selected)
        list_inner.addWidget(self.prompt_list)
        
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)
        
        self.btn_add = PushButton("新增")
        self.btn_add.setIcon(qta.icon('mdi6.plus', color=ACCENT_PRIMARY))
        self.btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add.clicked.connect(self._add_prompt)
        btn_layout.addWidget(self.btn_add)
        
        self.btn_delete = PushButton("删除")
        self.btn_delete.setIcon(qta.icon('mdi6.trash-can', color=COLOR_ERROR))
        self.btn_delete.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_delete.clicked.connect(self._delete_prompt)
        btn_layout.addWidget(self.btn_delete)
        
        btn_layout.addStretch()
        list_inner.addLayout(btn_layout)
        
        left_layout.addWidget(list_group)
        left_panel.setFixedWidth(260)
        layout.addWidget(left_panel)
        
        # ======== 右侧：编辑区域 ========
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(12)
        
        # 基本信息组
        info_group = QGroupBox("基本信息")
        info_layout = QFormLayout(info_group)
        info_layout.setSpacing(10)
        
        self.title_input = LineEdit()
        self.title_input.setPlaceholderText("输入 Prompt 标题...")
        info_layout.addRow("标题:", self.title_input)
        
        # 类型选择
        type_widget = QWidget()
        type_layout = QHBoxLayout(type_widget)
        type_layout.setContentsMargins(0, 0, 0, 0)
        type_layout.setSpacing(20)
        
        self.type_text_radio = RadioButton("文本/识图 (Vision)")
        self.type_text_radio.setChecked(True)
        type_layout.addWidget(self.type_text_radio)
        
        self.type_image_radio = RadioButton("生图/重绘 (Image Gen)")
        type_layout.addWidget(self.type_image_radio)
        
        type_layout.addStretch()
        info_layout.addRow("类型:", type_widget)
        
        self.default_checkbox = CheckBox("设为默认 Prompt")
        info_layout.addRow("", self.default_checkbox)
        
        right_layout.addWidget(info_group)
        
        # 内容组
        content_group = QGroupBox("Prompt 内容")
        content_layout = QVBoxLayout(content_group)
        content_layout.setSpacing(8)
        
        self.content_input = TextEdit()
        self.content_input.setPlaceholderText("输入 Prompt 内容...")
        self.content_input.setMinimumHeight(180)
        content_layout.addWidget(self.content_input)
        
        right_layout.addWidget(content_group)
        
        # 保存按钮
        save_layout = QHBoxLayout()
        save_layout.addStretch()
        
        self.btn_save = PrimaryPushButton("保存修改")
        self.btn_save.setIcon(qta.icon('mdi6.content-save', color='white'))
        self.btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save.clicked.connect(self._save_prompt)
        save_layout.addWidget(self.btn_save)
        
        right_layout.addLayout(save_layout)
        layout.addWidget(right_panel)
        
        # 应用统一样式
        self._apply_styles()
    
    def _apply_styles(self):
        """应用与设置界面一致的样式"""
        self.setStyleSheet(get_group_box_style() + f"""
            QWidget {{
                background-color: {BG_PRIMARY};
                font-family: {FONT_FAMILY};
            }}
            
            /* Prompt 列表 */
            QListWidget#prompt_list {{
                background-color: {BG_SECONDARY};
                border: 1px solid {BORDER_DEFAULT};
                border-radius: {RADIUS_SM}px;
                padding: 4px;
                font-size: 13px;
                color: {TEXT_PRIMARY};
                outline: none;
            }}
            QListWidget#prompt_list::item {{
                padding: 8px 10px;
                border-radius: {RADIUS_SM}px;
                margin: 1px 0;
            }}
            QListWidget#prompt_list::item:selected {{
                background-color: {ACCENT_SUBTLE};
                color: {ACCENT_PRIMARY};
            }}
            QListWidget#prompt_list::item:hover:!selected {{
                background-color: {BG_HOVER};
            }}
        """)
    
    def load_prompts(self):
        self.prompt_list.clear()
        self.prompts_data = get_all_prompts()
        
        for prompt in self.prompts_data:
            # 根据类型选择图标
            prompt_type = prompt.get("prompt_type", "text")
            if prompt_type == "text":
                icon = qta.icon('mdi6.eye-outline', color=TEXT_TERTIARY)
            else:
                icon = qta.icon('mdi6.palette-outline', color=TEXT_TERTIARY)

            
            title = prompt["title"]
            if prompt["is_default"]:
                display_text = f"★ {title}"
            else:
                display_text = title
            
            item = QListWidgetItem(icon, display_text)
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
        
        # 设置类型单选按钮
        prompt_type = prompt.get("prompt_type", "text")
        if prompt_type == "image":
            self.type_image_radio.setChecked(True)
        else:
            self.type_text_radio.setChecked(True)
    
    def _add_prompt(self):
        new_id = add_prompt("新建 Prompt", "请输入 Prompt 内容...", prompt_type="text")
        self.load_prompts()
        
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
            self, "确认删除",
            "确定要删除这个 Prompt 吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            delete_prompt(self.current_prompt_id)
            self.load_prompts()
    
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
        if current_row < self.prompt_list.count():
            self.prompt_list.setCurrentRow(current_row)
        
        self.btn_save.setIcon(qta.icon('mdi6.check', color='white'))
        self.btn_save.setText("已保存")
        QTimer.singleShot(1500, self._reset_save_btn)
    
    def _reset_save_btn(self):
        self.btn_save.setIcon(qta.icon('mdi6.content-save', color='white'))
        self.btn_save.setText("保存修改")


class PromptSelectMenu(QMenu):
    """Prompt 选择菜单"""
    prompt_selected = Signal(str, str)  # (content, prompt_type)
    edit_requested = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            QMenu {{
                background-color: {BG_PRIMARY};
                border: 1px solid {BORDER_DEFAULT};
                border-radius: {RADIUS_MD}px;
                padding: 6px;
            }}
            QMenu::item {{
                padding: 10px 24px;
                border-radius: {RADIUS_SM}px;
                color: {TEXT_PRIMARY};
                font-size: 13px;
            }}
            QMenu::item:selected {{
                background-color: {ACCENT_SUBTLE};
                color: {ACCENT_PRIMARY};
            }}
            QMenu::separator {{
                height: 1px;
                background-color: {BORDER_DEFAULT};
                margin: 6px 12px;
            }}
        """)

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
                
                # 根据类型选择图标
                if prompt_type == "text":
                    icon = qta.icon('mdi6.eye-outline', color=TEXT_SECONDARY)
                else:
                    icon = qta.icon('mdi6.palette-outline', color=TEXT_SECONDARY)

                
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
