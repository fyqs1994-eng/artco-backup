"""
设置对话框模块
包含 AI 配置和快捷键设置
"""

import sys
import os

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QGroupBox, QTabWidget, QWidget, QLabel,
    QKeySequenceEdit, QMessageBox, QLineEdit, QPushButton,
    QScrollArea, QFrame, QComboBox
)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QKeySequence

from config import AI_MODELS, ai_config, wecom_config, workspace_config
from utils import hotkey_manager
from ui.theme import (
    get_group_box_style,
    BG_PRIMARY, BG_SECONDARY, BG_ACTIVE, BORDER_DEFAULT, RADIUS_SM, TEXT_TERTIARY
)





def get_app_path():
    """获取应用程序路径"""
    if getattr(sys, 'frozen', False):
        # PyInstaller 打包后
        return sys.executable
    else:
        # 开发环境
        return os.path.abspath(sys.argv[0])


def is_autostart_enabled():
    """检查是否已启用开机启动"""
    if sys.platform != 'win32':
        return False
    
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_READ
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
    """设置开机启动"""
    if sys.platform != 'win32':
        return False
    
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_SET_VALUE
        )
        try:
            if enable:
                app_path = get_app_path()
                winreg.SetValueEx(key, "Artco", 0, winreg.REG_SZ, f'"{app_path}"')
            else:
                try:
                    winreg.DeleteValue(key, "Artco")
                except FileNotFoundError:
                    pass  # 不存在也没关系
            return True
        finally:
            winreg.CloseKey(key)
    except Exception as e:
        print(f"设置开机启动失败: {e}")
        return False


class SettingsDialog(QDialog):
    """设置对话框"""
    hotkey_changed = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setFixedSize(550, 600)
        self.init_ui()
    
    def init_ui(self):
        os.environ.setdefault("QT_API", "pyside6")
        from qfluentwidgets import PushButton, PrimaryPushButton, ComboBox, LineEdit, CheckBox

        layout = QVBoxLayout(self)

        layout.setSpacing(15)
        
        # 使用标签页
        self.tab_widget = QTabWidget()
        
        # === AI 设置标签页 ===
        ai_tab = QWidget()
        ai_layout = QVBoxLayout(ai_tab)
        ai_layout.setSpacing(12)
        
        # 任务类型选择
        task_group = QGroupBox("任务类型")
        task_layout = QFormLayout(task_group)
        task_layout.setSpacing(10)
        
        self.task_type_combo = ComboBox()

        self.task_type_combo.addItem("视觉分析 (Vision)", "vision")
        self.task_type_combo.addItem("图像生成 (Image Gen)", "image_gen")
        current_task = ai_config.get("task_type", "vision")
        index = self.task_type_combo.findData(current_task)
        if index >= 0:
            self.task_type_combo.setCurrentIndex(index)
        else:
            self.task_type_combo.setCurrentIndex(0)
        self.task_type_combo.currentIndexChanged.connect(self._on_task_type_changed)
        task_layout.addRow("类型:", self.task_type_combo)
        
        # 模型选择
        self.model_combo = ComboBox()

        self._update_model_list()
        task_layout.addRow("模型:", self.model_combo)

        
        ai_layout.addWidget(task_group)
        
        # API 配置
        api_group = QGroupBox("API 配置")
        api_layout = QFormLayout(api_group)
        api_layout.setSpacing(10)
        
        # Google API Key
        self.google_key_input = LineEdit()

        self.google_key_input.setPlaceholderText("输入 Google AI API Key")
        self.google_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.google_key_input.setText(ai_config.get_api_key("google"))
        api_layout.addRow("Google Key:", self.google_key_input)
        
        # Google Base URL
        self.google_base_url = LineEdit()

        self.google_base_url.setPlaceholderText("可选，自定义 API 地址")
        self.google_base_url.setText(ai_config.get_api_base_url("google"))
        api_layout.addRow("Google URL:", self.google_base_url)
        
        # OpenAI API Key
        self.openai_key_input = LineEdit()

        self.openai_key_input.setPlaceholderText("输入 OpenAI API Key")
        self.openai_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.openai_key_input.setText(ai_config.get_api_key("openai"))
        api_layout.addRow("OpenAI Key:", self.openai_key_input)
        
        # OpenAI Base URL
        self.openai_base_url = LineEdit()

        self.openai_base_url.setPlaceholderText("可选，自定义 API 地址")
        self.openai_base_url.setText(ai_config.get_api_base_url("openai"))
        api_layout.addRow("OpenAI URL:", self.openai_base_url)
        
        # Anthropic API Key
        self.anthropic_key_input = LineEdit()

        self.anthropic_key_input.setPlaceholderText("输入 Anthropic API Key")
        self.anthropic_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.anthropic_key_input.setText(ai_config.get_api_key("anthropic"))
        api_layout.addRow("Anthropic Key:", self.anthropic_key_input)
        
        # Anthropic Base URL
        self.anthropic_base_url = LineEdit()

        self.anthropic_base_url.setPlaceholderText("可选，自定义 API 地址")
        self.anthropic_base_url.setText(ai_config.get_api_base_url("anthropic"))
        api_layout.addRow("Anthropic URL:", self.anthropic_base_url)
        
        ai_layout.addWidget(api_group)
        ai_layout.addStretch()
        
        self.tab_widget.addTab(ai_tab, "AI 设置")
        
        # === 快捷键设置标签页 ===
        hotkey_tab = QWidget()
        hotkey_layout_main = QVBoxLayout(hotkey_tab)
        hotkey_layout_main.setSpacing(10)
        
        # 全局快捷键
        global_group = QGroupBox("全局快捷键")
        global_layout = QFormLayout(global_group)
        global_layout.setSpacing(10)
        
        self.screenshot_hotkey = QKeySequenceEdit()
        self.screenshot_hotkey.setMaximumSequenceLength(1)
        self.screenshot_hotkey.setKeySequence(QKeySequence(hotkey_manager.get('screenshot')))
        global_layout.addRow("截图快捷键:", self.screenshot_hotkey)
        
        # 剪贴板悬浮面板快捷键
        clipboard_hotkey_widget = QWidget()
        clipboard_hotkey_layout = QHBoxLayout(clipboard_hotkey_widget)
        clipboard_hotkey_layout.setContentsMargins(0, 0, 0, 0)
        
        self.clipboard_float_mode = QComboBox()
        self.clipboard_float_mode.addItems(["键盘快捷键", "鼠标侧键1", "鼠标侧键2"])
        self.clipboard_float_mode.setFixedWidth(100)
        
        self.clipboard_float_hotkey = QKeySequenceEdit()
        self.clipboard_float_hotkey.setMaximumSequenceLength(1)
        
        clipboard_hotkey_layout.addWidget(self.clipboard_float_mode)
        clipboard_hotkey_layout.addWidget(self.clipboard_float_hotkey)
        
        # 根据当前设置初始化控件
        clipboard_float_key = hotkey_manager.get('clipboard_float')
        if clipboard_float_key == 'mousex1':
            self.clipboard_float_mode.setCurrentIndex(1)  # 鼠标侧键1
            self.clipboard_float_hotkey.setKeySequence(QKeySequence())
            self.clipboard_float_hotkey.setEnabled(False)
        elif clipboard_float_key == 'mousex2':
            self.clipboard_float_mode.setCurrentIndex(2)  # 鼠标侧键2
            self.clipboard_float_hotkey.setKeySequence(QKeySequence())
            self.clipboard_float_hotkey.setEnabled(False)
        else:
            self.clipboard_float_mode.setCurrentIndex(0)  # 键盘快捷键
            self.clipboard_float_hotkey.setKeySequence(QKeySequence(clipboard_float_key))
            self.clipboard_float_hotkey.setEnabled(True)
        
        # 连接信号
        self.clipboard_float_mode.currentIndexChanged.connect(self._on_clipboard_float_mode_changed)
        
        global_layout.addRow("剪贴板浮窗:", clipboard_hotkey_widget)
        
        # 说明文本
        clipboard_tip = QLabel("选择鼠标侧键或直接在键盘快捷键框中按键设置")
        clipboard_tip.setStyleSheet(f"color: {TEXT_TERTIARY}; font-size: 11px; margin-left: 10px;")
        global_layout.addRow("", clipboard_tip)
        
        hotkey_layout_main.addWidget(global_group)
        
        # 截图窗口快捷键 - 使用滚动区域
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setSpacing(10)
        
        # 存储所有快捷键输入框
        self._hotkey_edits = {}
        
        screenshot_hotkeys = hotkey_manager.get_screenshot_hotkeys()
        for category, actions in screenshot_hotkeys.items():
            group = QGroupBox(f"截图窗口 - {category}")
            form_layout = QFormLayout(group)
            form_layout.setSpacing(8)
            
            for action, hotkey in actions.items():
                edit = QKeySequenceEdit()
                edit.setMaximumSequenceLength(1)
                edit.setKeySequence(QKeySequence(hotkey))
                edit.setFixedWidth(150)
                
                action_name = hotkey_manager.get_action_name(action)
                form_layout.addRow(f"{action_name}:", edit)
                self._hotkey_edits[(category, action)] = edit
            
            scroll_layout.addWidget(group)
        
        scroll_layout.addStretch()
        scroll_area.setWidget(scroll_content)
        hotkey_layout_main.addWidget(scroll_area)
        
        # 重置按钮
        reset_btn = PushButton("恢复默认快捷键")

        reset_btn.clicked.connect(self._reset_hotkeys)
        reset_btn.setFixedWidth(120)
        
        reset_layout = QHBoxLayout()
        reset_layout.addStretch()
        reset_layout.addWidget(reset_btn)
        hotkey_layout_main.addLayout(reset_layout)
        
        self.tab_widget.addTab(hotkey_tab, "快捷键")
        
        # === 通用设置标签页 ===
        general_tab = QWidget()
        general_layout = QVBoxLayout(general_tab)
        general_layout.setSpacing(12)
        
        # 启动设置
        startup_group = QGroupBox("启动设置")
        startup_layout = QVBoxLayout(startup_group)
        startup_layout.setSpacing(10)
        
        self.autostart_checkbox = CheckBox("开机自动启动")

        self.autostart_checkbox.setChecked(is_autostart_enabled())
        startup_layout.addWidget(self.autostart_checkbox)
        
        startup_tip = QLabel("启用后，系统启动时会自动运行 Artco")
        startup_tip.setStyleSheet(f"color: {TEXT_TERTIARY}; font-size: 11px; margin-left: 20px;")

        startup_layout.addWidget(startup_tip)
        
        general_layout.addWidget(startup_group)

        # 协作设置
        collab_group = QGroupBox("协作设置")
        collab_layout = QFormLayout(collab_group)
        collab_layout.setSpacing(10)

        self.vendor_company_input = LineEdit()
        self.vendor_company_input.setPlaceholderText("供应商公司名称（用于提交到 _INBOX 分流）")
        self.vendor_company_input.setText(workspace_config.get_vendor_company())
        collab_layout.addRow("供应商公司:", self.vendor_company_input)

        general_layout.addWidget(collab_group)
        general_layout.addStretch()
        
        self.tab_widget.addTab(general_tab, "通用")
        

        
        layout.addWidget(self.tab_widget)
        
        # 按钮区域
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self.btn_save = PrimaryPushButton("保存")

        self.btn_save.setFixedWidth(80)
        self.btn_save.clicked.connect(self._save_settings)
        
        self.btn_cancel = PushButton("取消")

        self.btn_cancel.setFixedWidth(80)
        self.btn_cancel.clicked.connect(self.reject)
        
        btn_layout.addWidget(self.btn_save)
        btn_layout.addWidget(self.btn_cancel)
        layout.addLayout(btn_layout)
        
        self.setStyleSheet(get_group_box_style() + f"""
            QDialog {{
                background-color: {BG_PRIMARY};
            }}
            QTabWidget::pane {{
                border: 1px solid {BORDER_DEFAULT};
                border-radius: {RADIUS_SM}px;
                background-color: {BG_SECONDARY};
            }}
            QTabBar::tab {{
                padding: 8px 16px;
                border: 1px solid {BORDER_DEFAULT};
                border-bottom: none;
                border-radius: {RADIUS_SM}px {RADIUS_SM}px 0 0;
                background-color: {BG_ACTIVE};
            }}
            QTabBar::tab:selected {{
                background-color: {BG_SECONDARY};
                border-bottom: 1px solid {BG_SECONDARY};
            }}
        """)



    
    def _on_task_type_changed(self, index):
        """任务类型改变时更新模型列表"""
        self._update_model_list()
    
    def show_tab(self, tab_id: str):
        """切换到指定的标签页
        
        Args:
            tab_id: 标签页ID ('ai', 'hotkey', 'general', 'wecom')
        """
        tab_mapping = {
            'ai': 'AI 设置',
            'hotkey': '快捷键',
            'general': '通用'
        }
        
        tab_name = tab_mapping.get(tab_id)
        if tab_name:
            for i in range(self.tab_widget.count()):
                if self.tab_widget.tabText(i) == tab_name:
                    self.tab_widget.setCurrentIndex(i)
                    break
    
    def _update_model_list(self):
        """更新模型下拉列表"""
        self.model_combo.clear()
        task_type = self.task_type_combo.currentData() or "vision"
        models = AI_MODELS.get(task_type) or AI_MODELS.get("vision", [])
        
        for model in models:
            self.model_combo.addItem(model["name"], model["id"])
        
        # 恢复之前选择的模型
        if task_type == "vision":
            current_model = ai_config.get("vision_model", "gemini-2.5-flash")
        else:
            current_model = ai_config.get("image_gen_model", "gemini-2.5-flash")
        
        index = self.model_combo.findData(current_model)
        if index >= 0:
            self.model_combo.setCurrentIndex(index)
        elif self.model_combo.count() > 0:
            self.model_combo.setCurrentIndex(0)
    def _on_clipboard_float_mode_changed(self, index):
        """剪贴板浮窗快捷键模式改变"""
        if index == 0:  # 键盘快捷键
            self.clipboard_float_hotkey.setEnabled(True)
            # 如果之前是清空的，可以设置一个默认序列，但这里不设置
        else:  # 鼠标侧键1或2
            self.clipboard_float_hotkey.setEnabled(False)
            self.clipboard_float_hotkey.setKeySequence(QKeySequence())
    
    def _save_settings(self):
        # 保存 AI 设置
        task_type = self.task_type_combo.currentData()
        model_id = self.model_combo.currentData()
        
        ai_config.set("task_type", task_type)
        if task_type == "vision":
            ai_config.set("vision_model", model_id)
        else:
            ai_config.set("image_gen_model", model_id)
        
        # 保存 API Keys
        ai_config.set_api_key("google", self.google_key_input.text().strip())
        ai_config.set_api_key("openai", self.openai_key_input.text().strip())
        ai_config.set_api_key("anthropic", self.anthropic_key_input.text().strip())
        
        # 保存 API Base URLs
        ai_config.set_api_base_url("google", self.google_base_url.text().strip())
        ai_config.set_api_base_url("openai", self.openai_base_url.text().strip())
        ai_config.set_api_base_url("anthropic", self.anthropic_base_url.text().strip())
        
        # 保存快捷键设置
        seq = self.screenshot_hotkey.keySequence()
        hotkey_str = seq.toString() if not seq.isEmpty() else ''
        
        old_hotkey = hotkey_manager.get('screenshot')
        hotkey_manager.set('screenshot', hotkey_str)
        
        if old_hotkey != hotkey_str:
            self.hotkey_changed.emit()
        
        # 保存剪贴板浮窗快捷键
        mode_index = self.clipboard_float_mode.currentIndex()
        if mode_index == 0:  # 键盘快捷键
            seq = self.clipboard_float_hotkey.keySequence()
            clipboard_float_str = seq.toString() if not seq.isEmpty() else ''
        elif mode_index == 1:  # 鼠标侧键1
            clipboard_float_str = 'mousex1'
        else:  # 鼠标侧键2
            clipboard_float_str = 'mousex2'
        
        old_clipboard_float = hotkey_manager.get('clipboard_float')
        hotkey_manager.set('clipboard_float', clipboard_float_str)
        
        if old_clipboard_float != clipboard_float_str:
            self.hotkey_changed.emit()
        
        # 保存截图窗口快捷键
        for (category, action), edit in self._hotkey_edits.items():
            seq = edit.keySequence()
            hotkey_str = seq.toString() if not seq.isEmpty() else ''
            hotkey_manager.set_screenshot_hotkey(category, action, hotkey_str)
        
        # 使快捷键缓存失效
        try:
            from screenshot.cache import invalidate_hotkey_cache
            invalidate_hotkey_cache()
        except ImportError:
            pass
        
        # 保存开机启动设置
        autostart_enabled = self.autostart_checkbox.isChecked()
        if autostart_enabled != is_autostart_enabled():
            if not set_autostart(autostart_enabled):
                QMessageBox.warning(self, "警告", "开机启动设置失败，请以管理员权限运行")

        # 保存协作设置
        try:
            vendor_company = self.vendor_company_input.text().strip() if hasattr(self, "vendor_company_input") else ""
            workspace_config.set_vendor_company(vendor_company)
        except Exception:
            pass
        
        QMessageBox.information(self, "成功", "设置已保存")
        self.accept()
    
    def _reset_hotkeys(self):
        """恢复默认快捷键"""
        reply = QMessageBox.question(
            self, "确认", "确定要恢复所有快捷键为默认值吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        
        # 恢复全局快捷键
        default_screenshot = hotkey_manager.DEFAULT_HOTKEYS.get('screenshot', 'F1')
        self.screenshot_hotkey.setKeySequence(QKeySequence(default_screenshot))
        
        default_clipboard_float = hotkey_manager.DEFAULT_HOTKEYS.get('clipboard_float', 'mousex1')
        if default_clipboard_float == 'mousex1':
            self.clipboard_float_mode.setCurrentIndex(1)  # 鼠标侧键1
            self.clipboard_float_hotkey.setKeySequence(QKeySequence())
            self.clipboard_float_hotkey.setEnabled(False)
        elif default_clipboard_float == 'mousex2':
            self.clipboard_float_mode.setCurrentIndex(2)  # 鼠标侧键2
            self.clipboard_float_hotkey.setKeySequence(QKeySequence())
            self.clipboard_float_hotkey.setEnabled(False)
        else:
            self.clipboard_float_mode.setCurrentIndex(0)  # 键盘快捷键
            self.clipboard_float_hotkey.setKeySequence(QKeySequence(default_clipboard_float))
            self.clipboard_float_hotkey.setEnabled(True)
        
        # 恢复截图窗口快捷键
        for (category, action), edit in self._hotkey_edits.items():
            default_hotkey = hotkey_manager.DEFAULT_SCREENSHOT_HOTKEYS.get(category, {}).get(action, '')
            edit.setKeySequence(QKeySequence(default_hotkey))
    
    def _load_webhooks(self):
        """加载已配置的 Webhook"""
        # 清空列表
        while self.webhook_list_layout.count():
            item = self.webhook_list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        webhooks = wecom_config.get_webhooks()
        
        if not webhooks:
            empty_label = QLabel("暂无配置，请添加企微群 Webhook")
            empty_label.setStyleSheet("color: #888; padding: 20px; font-size: 12px;")
            empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.webhook_list_layout.addWidget(empty_label)
            return
        
        for wh in webhooks:
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(4, 4, 4, 4)
            row_layout.setSpacing(8)
            
            name_label = QLabel(wh["name"])
            name_label.setFixedWidth(120)
            name_label.setStyleSheet("font-weight: bold;")
            row_layout.addWidget(name_label)
            
            # 显示 URL（脱敏）
            url = wh["url"]
            if len(url) > 50:
                display_url = url[:30] + "..." + url[-15:]
            else:
                display_url = url
            url_label = QLabel(display_url)
            url_label.setStyleSheet("color: #666; font-size: 11px;")
            url_label.setToolTip(url)
            row_layout.addWidget(url_label, 1)
            
            # 删除按钮
            btn_del = QPushButton("删除")
            btn_del.setFixedWidth(50)
            btn_del.setProperty("webhook_name", wh["name"])
            btn_del.clicked.connect(self._remove_webhook)
            row_layout.addWidget(btn_del)
            
            self.webhook_list_layout.addWidget(row)
    
    def _add_webhook(self):
        """添加 Webhook"""
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
        
        # 清空输入
        self.webhook_name_input.clear()
        self.webhook_url_input.clear()
        
        # 刷新列表
        self._load_webhooks()
        
        QMessageBox.information(self, "成功", f"已添加 Webhook：{name}")
    
    def _remove_webhook(self):
        """删除 Webhook"""
        btn = self.sender()
        name = btn.property("webhook_name")
        
        reply = QMessageBox.question(
            self, "确认", f"确定要删除 \"{name}\" 吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        
        wecom_config.remove_webhook(name)
        self._load_webhooks()
