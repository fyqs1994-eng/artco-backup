"""
反馈分配对话框 - 将标注后的图片分配到企微/项目管理
"""

import base64
import hashlib
import requests
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QTextEdit, QCheckBox, QFrame,
    QButtonGroup, QRadioButton, QGroupBox, QMessageBox, QWidget
)
from PySide6.QtCore import Qt, Signal, QSize, QBuffer, QIODevice, QThread
from PySide6.QtGui import QPixmap, QFont, QColor, QPainter

import qtawesome as qta

from ui.theme import (
    BG_PRIMARY, BG_SECONDARY, BG_HOVER, BG_ACTIVE,
    BORDER_DEFAULT, BORDER_SUBTLE,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_TERTIARY,
    ACCENT_PRIMARY, COLOR_SUCCESS,
    RADIUS_MD, RADIUS_LG, RADIUS_XL,
    SPACING_SM, SPACING_MD, SPACING_LG,
    get_group_box_style, get_radio_style, get_combo_style,
    get_btn_primary_style, get_btn_secondary_style, get_text_edit_style,
    get_checkbox_style
)
from config import wecom_config


class WeComSendThread(QThread):
    """企微发送线程"""
    finished = Signal(bool, str)  # success, message
    
    def __init__(self, webhook_url: str, image_data: bytes, note: str, parent=None):
        super().__init__(parent)
        self._webhook_url = webhook_url
        self._image_data = image_data
        self._note = note
    
    def run(self):
        try:
            self._send_image()
        except requests.Timeout:
            self.finished.emit(False, "发送超时，请检查网络连接")
        except requests.RequestException as e:
            self.finished.emit(False, f"网络错误: {str(e)}")
        except Exception as e:
            self.finished.emit(False, f"发送失败: {str(e)}")
    
    def _send_image(self):
        """发送图片模式"""
        # 计算图片 MD5 和 Base64
        md5_hash = hashlib.md5(self._image_data).hexdigest()
        base64_data = base64.b64encode(self._image_data).decode('utf-8')
        
        # 先发送图片
        image_payload = {
            "msgtype": "image",
            "image": {
                "base64": base64_data,
                "md5": md5_hash
            }
        }
        
        resp = requests.post(
            self._webhook_url,
            json=image_payload,
            timeout=30
        )
        
        if resp.status_code != 200:
            self.finished.emit(False, f"发送图片失败: HTTP {resp.status_code}")
            return
        
        result = resp.json()
        if result.get("errcode") != 0:
            self.finished.emit(False, f"发送图片失败: {result.get('errmsg', '未知错误')}")
            return
        
        # 如果有备注，再发送文本
        if self._note:
            text_payload = {
                "msgtype": "text",
                "text": {
                    "content": self._note
                }
            }
            
            resp = requests.post(
                self._webhook_url,
                json=text_payload,
                timeout=10
            )
            
            # 文本发送失败不影响整体结果
            if resp.status_code != 200:
                self.finished.emit(True, "图片已发送，但备注发送失败")
                return
        
        self.finished.emit(True, "发送成功")


class FeedbackDialog(QDialog):
    """反馈分配对话框"""
    
    # 信号：分配完成 (target_type, target_id, note)
    feedback_sent = Signal(str, str, str)
    
    def __init__(self, pixmap: QPixmap, parent=None):
        super().__init__(parent)
        self._pixmap = pixmap
        self._send_thread = None
        self._init_ui()
    
    def _init_ui(self):
        self.setWindowTitle("分配反馈")
        self.setMinimumWidth(420)
        self.setModal(True)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        
        # 主布局
        layout = QVBoxLayout(self)
        layout.setSpacing(SPACING_LG)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # === 图片预览区 ===
        preview_frame = QFrame()
        preview_frame.setStyleSheet(f"""
            QFrame {{
                background: {BG_SECONDARY};
                border: 1px solid {BORDER_DEFAULT};
                border-radius: {RADIUS_LG}px;
            }}
        """)
        preview_layout = QVBoxLayout(preview_frame)
        preview_layout.setContentsMargins(12, 12, 12, 12)
        
        self.preview_label = QLabel()
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumHeight(150)
        self.preview_label.setMaximumHeight(200)
        self._update_preview()
        preview_layout.addWidget(self.preview_label)
        
        # 图片信息
        if self._pixmap and not self._pixmap.isNull():
            info_text = f"{self._pixmap.width()} × {self._pixmap.height()} 像素"
            info_label = QLabel(info_text)
            info_label.setStyleSheet(f"color: {TEXT_TERTIARY}; font-size: 11px;")
            info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            preview_layout.addWidget(info_label)
        
        layout.addWidget(preview_frame)
        
        # === 反馈说明 ===
        note_group = QGroupBox("反馈说明")
        note_group.setStyleSheet(get_group_box_style())
        note_layout = QVBoxLayout(note_group)
        note_layout.setSpacing(SPACING_SM)
        
        self.note_input = QTextEdit()
        self.note_input.setPlaceholderText("输入反馈说明（可选）...")
        self.note_input.setMaximumHeight(80)
        self.note_input.setStyleSheet(get_text_edit_style())
        note_layout.addWidget(self.note_input)
        
        layout.addWidget(note_group)
        
        # === 发送目标 ===
        target_group = QGroupBox("发送到")
        target_group.setStyleSheet(get_group_box_style())
        target_layout = QVBoxLayout(target_group)
        target_layout.setSpacing(SPACING_MD)
        
        self.target_button_group = QButtonGroup(self)
        
        # 企微群 Webhook
        wecom_group_row = QHBoxLayout()
        self.radio_wecom_group = QRadioButton("企微群")
        self.radio_wecom_group.setStyleSheet(get_radio_style())
        self.target_button_group.addButton(self.radio_wecom_group, 0)
        wecom_group_row.addWidget(self.radio_wecom_group)
        
        self.combo_wecom_group = QComboBox()
        self.combo_wecom_group.setPlaceholderText("选择群聊...")
        self.combo_wecom_group.setEnabled(False)
        self.combo_wecom_group.setStyleSheet(get_combo_style())
        self._load_webhooks()
        wecom_group_row.addWidget(self.combo_wecom_group, 1)
        target_layout.addLayout(wecom_group_row)
        
        self.label_wecom_hint = QLabel("未配置 Webhook，请先在设置中配置")
        self.label_wecom_hint.setStyleSheet(f"color: {TEXT_TERTIARY}; font-size: 11px;")
        self.label_wecom_hint.setContentsMargins(100, 0, 0, 0)
        self.label_wecom_hint.setVisible(False)
        target_layout.addWidget(self.label_wecom_hint)
        
        # 仅复制到剪贴板
        self.radio_clipboard = QRadioButton("仅复制到剪贴板")
        self.radio_clipboard.setStyleSheet(get_radio_style())
        self.radio_clipboard.setChecked(True)  # 默认选中
        self.target_button_group.addButton(self.radio_clipboard, 1)
        target_layout.addWidget(self.radio_clipboard)
        
        layout.addWidget(target_group)

        
        # === 附加选项 ===
        self.check_save_history = QCheckBox("同时保存到历史记录")
        self.check_save_history.setChecked(True)
        self.check_save_history.setStyleSheet(get_checkbox_style())
        layout.addWidget(self.check_save_history)
        
        # === 按钮区 ===
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(SPACING_MD)
        
        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.setStyleSheet(get_btn_secondary_style())
        self.btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)
        
        btn_layout.addStretch()
        
        self.btn_send = QPushButton("发送反馈")
        self.btn_send.setIcon(qta.icon('mdi6.send', color='white'))
        self.btn_send.setStyleSheet(get_btn_primary_style())
        self.btn_send.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_send.clicked.connect(self._on_send)
        btn_layout.addWidget(self.btn_send)
        
        layout.addLayout(btn_layout)
        
        # 连接信号
        self.target_button_group.buttonClicked.connect(self._on_target_changed)
        self.combo_wecom_group.currentIndexChanged.connect(self._update_send_state)

        # 初始化目标状态
        if getattr(self, "_webhooks_available", False):
            self.radio_wecom_group.setChecked(True)
        else:
            self.radio_clipboard.setChecked(True)
        self._on_target_changed(self.target_button_group.checkedButton())
        
        # 应用样式
        self.setStyleSheet(f"""
            QDialog {{
                background: {BG_PRIMARY};
            }}
        """)

    
    def _load_webhooks(self):
        """加载 Webhook 配置到下拉框"""
        self.combo_wecom_group.clear()
        
        webhooks = wecom_config.get_webhooks()
        self._webhooks_available = bool(webhooks)
        if not webhooks:
            self.combo_wecom_group.addItem("(请先在设置中配置)")
            return
        
        for wh in webhooks:
            self.combo_wecom_group.addItem(wh["name"], wh["url"])
        
        # 恢复上次使用的
        last_used = wecom_config.get_last_used()
        if last_used:
            idx = self.combo_wecom_group.findText(last_used)
            if idx >= 0:
                self.combo_wecom_group.setCurrentIndex(idx)

    
    def _update_preview(self):
        """更新预览图"""
        if self._pixmap and not self._pixmap.isNull():
            # 缩放到预览尺寸
            scaled = self._pixmap.scaled(
                380, 180,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.preview_label.setPixmap(scaled)
        else:
            self.preview_label.setText("无图片")
            self.preview_label.setStyleSheet(f"color: {TEXT_TERTIARY};")
    
    def _on_target_changed(self, button):
        """目标选择变化"""
        idx = self.target_button_group.id(button)
        is_group = idx == 0
        has_webhooks = getattr(self, "_webhooks_available", False)
        
        # 启用/禁用对应的下拉框
        self.combo_wecom_group.setEnabled(is_group and has_webhooks)
        
        self.label_wecom_hint.setVisible(is_group and not has_webhooks)

        self._update_send_state()

    
    def _get_image_data(self) -> bytes:
        """获取图片二进制数据"""
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        # 使用 PNG 格式，保持质量
        self._pixmap.save(buffer, "PNG")
        data = buffer.data().data()
        buffer.close()
        return data

    def _update_send_state(self):
        """更新发送按钮状态与文案"""
        idx = self.target_button_group.checkedId()
        if idx == 0:
            has_webhook = bool(self.combo_wecom_group.currentData())
            self.btn_send.setText("发送到企微群")
            self.btn_send.setEnabled(has_webhook)
        else:
            self.btn_send.setText("复制到剪贴板")
            self.btn_send.setEnabled(True)

    
    def _on_send(self):
        """发送反馈"""
        from PySide6.QtGui import QGuiApplication
        from database import add_record
        
        target_idx = self.target_button_group.checkedId()
        note = self.note_input.toPlainText().strip()
        
        # 根据目标类型处理
        if target_idx == 0:  # 企微群 Webhook
            webhook_url = self.combo_wecom_group.currentData()
            webhook_name = self.combo_wecom_group.currentText()
            
            if not webhook_url:
                QMessageBox.warning(self, "提示", "请先在设置中配置企微群 Webhook")
                return
            
            # 获取图片数据
            image_data = self._get_image_data()
            
            # 检查图片大小 (企微限制 2MB)
            if len(image_data) > 2 * 1024 * 1024:
                QMessageBox.warning(self, "提示", "图片大小超过 2MB，请压缩后再发送")
                return
            
            # 禁用按钮，显示发送中
            self.btn_send.setEnabled(False)
            self.btn_cancel.setEnabled(False)
            
            # 记录上次使用
            wecom_config.set_last_used(webhook_name)
            
            self.btn_send.setText("发送中...")
            self._send_thread = WeComSendThread(webhook_url, image_data, note)
            self._send_thread.finished.connect(self._on_wecom_send_finished)
            self._send_thread.start()
            return
        
        elif target_idx == 1:  # 仅复制到剪贴板
            QGuiApplication.clipboard().setPixmap(self._pixmap)
            
            # 保存到历史记录
            if self.check_save_history.isChecked():
                self._save_to_history(note)
            
            self.feedback_sent.emit("clipboard", "", note)
            self.accept()

    
    def _on_wecom_send_finished(self, success: bool, message: str):
        """企微发送完成回调"""
        self.btn_send.setEnabled(True)
        self.btn_cancel.setEnabled(True)
        self.btn_send.setText("发送反馈")
        
        if success:
            # 保存到历史记录
            if self.check_save_history.isChecked():
                note = self.note_input.toPlainText().strip()
                self._save_to_history(note)
            
            QMessageBox.information(self, "成功", message)
            self.feedback_sent.emit("wecom_group", self.combo_wecom_group.currentText(), note)
            self.accept()
        else:
            QMessageBox.warning(self, "发送失败", message)
    
    def _save_to_history(self, note: str):
        """保存到历史记录"""
        from database import add_record
        try:
            buffer = QBuffer()
            buffer.open(QIODevice.OpenModeFlag.WriteOnly)
            self._pixmap.save(buffer, "JPEG", 85)
            image_data = buffer.data().data()
            buffer.close()
            add_record(image_data, note)
        except Exception as e:
            print(f"保存历史记录失败: {e}")
