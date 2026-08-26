"""
归档模块
包含归档记录的展示、详情和管理组件
支持归档和剪贴板历史两个 Tab
"""

import re
import base64
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

import qtawesome as qta
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QScrollArea, QMessageBox, QGridLayout, QApplication, QLineEdit,
    QStackedWidget, QFrame
)
from PySide6.QtCore import Qt, Signal, QSize, QMimeData, QUrl, QPoint, QBuffer, QIODevice, QTimer, QEvent
from PySide6.QtGui import QPixmap, QGuiApplication, QDrag, QClipboard, QImage

from database import get_all_records, delete_record, get_image_full_path, get_all_prompts
from ui.theme import FONT_FAMILY_MONO
from .prompt_manager import PromptSelectMenu


class ArchiveDetailDialog(QWidget):
    """归档详情窗口（非模态）"""
    
    # 预定义样式（胶囊型按钮）
    _STYLE_AI_BTN_TEXT = """
        QPushButton#btn_ai_send {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 rgba(99, 102, 241, 0.9),
                stop:1 rgba(139, 92, 246, 0.9));
            border: none;
            border-radius: 18px;
            padding: 0 16px;
            color: white;
            font-size: 13px;
            font-weight: 500;
        }
        QPushButton#btn_ai_send:hover {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 rgba(79, 82, 221, 0.95),
                stop:1 rgba(119, 72, 226, 0.95));
        }
    """
    _STYLE_AI_BTN_IMAGE = """
        QPushButton#btn_ai_send {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 rgba(236, 72, 153, 0.9),
                stop:1 rgba(244, 114, 182, 0.9));
            border: none;
            border-radius: 18px;
            padding: 0 16px;
            color: white;
            font-size: 13px;
            font-weight: 500;
        }
        QPushButton#btn_ai_send:hover {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 rgba(216, 52, 133, 0.95),
                stop:1 rgba(224, 94, 162, 0.95));
        }
    """
    
    def __init__(self, record: dict, parent=None):
        super().__init__(parent)
        self.record = record
        self._pixmap = None  # 缓存原图
        self._selected_prompt_type = "text"  # 当前选中的模式
        self._prompts = self._load_prompts()  # 加载模板
        self.setWindowTitle("归档详情")
        self.setWindowFlags(Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setMinimumSize(800, 600)
        self.init_ui()
    
    def _load_prompts(self):
        """加载 Prompt 模板"""
        prompts = []
        try:
            db_prompts = get_all_prompts()
            for p in db_prompts:
                prompts.append((p["title"], p["content"], p.get("prompt_type", "text")))
        except Exception:
            pass
        if not prompts:
            prompts = [("默认", "请详细分析这张图片的内容。", "text")]
        return prompts
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)
        
        # 时间标题
        timestamp = self.record.get("timestamp", "")
        try:
            dt = datetime.fromisoformat(timestamp)
            time_str = dt.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            time_str = timestamp
        
        time_label_layout = QHBoxLayout()
        time_icon = QLabel()
        time_icon.setPixmap(qta.icon('mdi6.clock', color='#666').pixmap(16, 16))
        time_label_layout.addWidget(time_icon)
        time_text = QLabel(time_str)
        time_text.setStyleSheet("font-size: 14px; color: #666;")
        time_label_layout.addWidget(time_text)
        time_label_layout.addStretch()
        layout.addLayout(time_label_layout)
        
        # 图片区域（带悬浮复制按钮）
        image_path = get_image_full_path(self.record.get("image_path", ""))
        if image_path.exists():
            self._pixmap = QPixmap(str(image_path))
            scaled = self._pixmap.scaled(760, 400, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            
            # 图片容器
            image_container = QWidget()
            image_container.setObjectName("image_container")
            image_container.setStyleSheet("QWidget#image_container { background-color: #f5f5f5; border-radius: 8px; }")
            image_container_layout = QVBoxLayout(image_container)
            image_container_layout.setContentsMargins(10, 10, 10, 10)
            
            image_label = QLabel()
            image_label.setPixmap(scaled)
            image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            image_container_layout.addWidget(image_label)
            
            # 悬浮复制图片按钮（右上角）
            self.btn_copy_image = QPushButton(image_container)
            self.btn_copy_image.setIcon(qta.icon('mdi6.content-copy', color='#fff'))
            self.btn_copy_image.setIconSize(QSize(14, 14))
            self.btn_copy_image.setFixedSize(28, 28)
            self.btn_copy_image.setCursor(Qt.CursorShape.PointingHandCursor)
            self.btn_copy_image.setToolTip("复制图片")
            self.btn_copy_image.setObjectName("btn_copy_overlay")
            self.btn_copy_image.clicked.connect(self._copy_image)
            self.btn_copy_image.move(image_container.width() - 38, 10)
            self.btn_copy_image.hide()
            
            # 鼠标悬停显示按钮
            image_container.enterEvent = lambda e: self.btn_copy_image.show()
            image_container.leaveEvent = lambda e: self.btn_copy_image.hide()
            
            layout.addWidget(image_container)
            self._image_container = image_container
        
        # AI 文字区域（带悬浮复制按钮）
        ai_text = self.record.get("ai_text", "")
        if ai_text:
            ai_label_layout = QHBoxLayout()
            ai_icon = QLabel()
            ai_icon.setPixmap(qta.icon('mdi6.auto-fix', color='#333').pixmap(16, 16))
            ai_label_layout.addWidget(ai_icon)
            ai_label_text = QLabel("AI 分析结果")
            ai_label_text.setStyleSheet("font-size: 14px; font-weight: bold; color: #333; margin-top: 10px;")
            ai_label_layout.addWidget(ai_label_text)
            ai_label_layout.addStretch()
            layout.addLayout(ai_label_layout)
            
            # 文本框容器
            text_container = QWidget()
            text_container.setObjectName("text_container")
            text_container_layout = QVBoxLayout(text_container)
            text_container_layout.setContentsMargins(0, 0, 0, 0)
            
            text_edit = QTextEdit()
            text_edit.setPlainText(ai_text)
            text_edit.setReadOnly(True)
            text_edit.setStyleSheet(f"""
                QTextEdit {{
                    background-color: #fafafa;
                    border: 1px solid #e0e0e0;
                    border-radius: 8px;
                    font-family: {FONT_FAMILY_MONO};
                    font-size: 13px;
                    padding: 10px;
                    color: #333;
                }}
            """)
            text_edit.setMinimumHeight(150)
            text_container_layout.addWidget(text_edit)
            
            # 悬浮复制文字按钮（右上角）
            self.btn_copy_text = QPushButton(text_container)
            self.btn_copy_text.setIcon(qta.icon('mdi6.content-copy', color='#fff'))
            self.btn_copy_text.setIconSize(QSize(14, 14))
            self.btn_copy_text.setFixedSize(28, 28)
            self.btn_copy_text.setCursor(Qt.CursorShape.PointingHandCursor)
            self.btn_copy_text.setToolTip("复制文字")
            self.btn_copy_text.setObjectName("btn_copy_overlay")
            self.btn_copy_text.clicked.connect(self._copy_text)
            self.btn_copy_text.move(text_container.width() - 38, 10)
            self.btn_copy_text.hide()
            
            text_container.enterEvent = lambda e: self.btn_copy_text.show()
            text_container.leaveEvent = lambda e: self.btn_copy_text.hide()
            
            layout.addWidget(text_container)
            self._text_container = text_container
        else:
            no_text = QLabel("暂无 AI 分析结果")
            no_text.setStyleSheet("color: #999; font-size: 13px;")
            layout.addWidget(no_text)
        
        # AI 输入区域 - 类似截图界面
        ai_input_layout = QHBoxLayout()
        ai_input_layout.setSpacing(6)
        
        # 输入框容器（圆角背景）
        input_container = QWidget()
        input_container.setObjectName("ai_input_container")
        input_container_layout = QHBoxLayout(input_container)
        input_container_layout.setContentsMargins(12, 4, 4, 4)
        input_container_layout.setSpacing(4)
        
        # 输入框
        self.ai_input = QLineEdit()
        self.ai_input.setPlaceholderText("输入 Prompt / 选择模板...")
        self.ai_input.setObjectName("ai_input_field")
        self.ai_input.returnPressed.connect(self._on_custom_ai_send)
        self.ai_input.textChanged.connect(self._on_input_text_changed)
        input_container_layout.addWidget(self.ai_input, 1)
        
        # Enter 键提示标签
        self._enter_hint = QLabel("Enter 键发送", self.ai_input)
        self._enter_hint.setStyleSheet("color: rgba(0, 0, 0, 0.25); font-size: 11px; background: transparent;")
        self._enter_hint.setFixedHeight(self.ai_input.sizeHint().height())
        self._enter_hint.hide()
        self.ai_input.textChanged.connect(self._update_enter_hint)
        
        # 模式切换按钮（横条胶囊形状）
        self.btn_mode = QPushButton("文本")
        self.btn_mode.setFixedSize(48, 24)
        self.btn_mode.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_mode.setObjectName("btn_mode_text")
        self.btn_mode.setToolTip("当前：文本分析\n点击切换到图片生成")
        self.btn_mode.clicked.connect(self._toggle_mode)
        input_container_layout.addWidget(self.btn_mode)
        
        ai_input_layout.addWidget(input_container, 1)
        
        # 发送按钮（胶囊型）
        self.btn_send = QPushButton(" 发送")
        self.btn_send.setIcon(qta.icon('mdi6.creation', color='#fff'))
        self.btn_send.setIconSize(QSize(16, 16))
        self.btn_send.setFixedHeight(36)
        self.btn_send.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_send.setToolTip("发送 AI 分析")
        self.btn_send.clicked.connect(self._on_custom_ai_send)
        self.btn_send.setObjectName("btn_ai_send")
        self.btn_send.setStyleSheet(self._STYLE_AI_BTN_TEXT)
        ai_input_layout.addWidget(self.btn_send)
        
        layout.addLayout(ai_input_layout)
        
        # 下拉模板列表
        self._setup_dropdown()
        
        self.setStyleSheet("""
            QWidget { background-color: #ffffff; }
            QPushButton {
                background-color: #f5f5f5;
                border: 1px solid #ddd;
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 13px;
            }
            QPushButton:hover { background-color: #e8e8e8; }
            QPushButton#btn_copy_overlay {
                background-color: rgba(0, 0, 0, 0.5);
                border: none;
                border-radius: 14px;
                padding: 0;
            }
            QPushButton#btn_copy_overlay:hover {
                background-color: rgba(99, 102, 241, 0.9);
            }
            QWidget#ai_input_container {
                background-color: #f5f5f5;
                border: 1px solid #e0e0e0;
                border-radius: 18px;
            }
            QLineEdit#ai_input_field {
                background-color: transparent;
                border: none;
                font-size: 13px;
                color: #333;
            }
            QPushButton#btn_mode_text {
                background-color: rgba(99, 102, 241, 0.15);
                border: none;
                border-radius: 12px;
                padding: 0 8px;
                font-size: 11px;
                font-weight: 500;
                color: rgba(99, 102, 241, 0.9);
            }
            QPushButton#btn_mode_text:hover {
                background-color: rgba(99, 102, 241, 0.25);
            }
            QPushButton#btn_mode_image {
                background-color: rgba(236, 72, 153, 0.15);
                border: none;
                border-radius: 12px;
                padding: 0 8px;
                font-size: 11px;
                font-weight: 500;
                color: rgba(236, 72, 153, 0.9);
            }
            QPushButton#btn_mode_image:hover {
                background-color: rgba(236, 72, 153, 0.25);
            }
            QWidget#dropdown_widget {
                background-color: white;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
            }
            QPushButton#dropdown_item {
                background-color: transparent;
                border: none;
                border-radius: 4px;
                padding: 8px 12px;
                text-align: left;
                font-size: 13px;
                color: #333;
            }
            QPushButton#dropdown_item:hover {
                background-color: rgba(99, 102, 241, 0.1);
            }
        """)
    
    def _copy_text(self):
        QGuiApplication.clipboard().setText(self.record.get("ai_text", ""))
    
    def _copy_image(self):
        if self._pixmap:
            QGuiApplication.clipboard().setPixmap(self._pixmap)
    
    def resizeEvent(self, event):
        """窗口大小变化时重新定位悬浮按钮"""
        super().resizeEvent(event)
        # 更新图片容器的复制按钮位置
        if hasattr(self, '_image_container') and hasattr(self, 'btn_copy_image'):
            self.btn_copy_image.move(self._image_container.width() - 38, 10)
        # 更新文本容器的复制按钮位置
        if hasattr(self, '_text_container') and hasattr(self, 'btn_copy_text'):
            self.btn_copy_text.move(self._text_container.width() - 38, 10)
    
    def showEvent(self, event):
        """窗口显示时定位悬浮按钮"""
        super().showEvent(event)
        # 延迟定位，确保布局完成
        from PySide6.QtCore import QTimer
        QTimer.singleShot(50, self._update_copy_button_positions)
    
    def _update_copy_button_positions(self):
        """更新复制按钮位置"""
        if hasattr(self, '_image_container') and hasattr(self, 'btn_copy_image'):
            self.btn_copy_image.move(self._image_container.width() - 38, 10)
        if hasattr(self, '_text_container') and hasattr(self, 'btn_copy_text'):
            self.btn_copy_text.move(self._text_container.width() - 38, 10)
    
    def _setup_dropdown(self):
        """设置下拉模板列表"""
        self._dropdown = QWidget(self)
        self._dropdown.setObjectName("dropdown_widget")
        self._dropdown.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self._dropdown.hide()
        self._dropdown_selected_index = -1  # 当前高亮的模板索引
        
        dropdown_layout = QVBoxLayout(self._dropdown)
        dropdown_layout.setContentsMargins(4, 4, 4, 4)
        dropdown_layout.setSpacing(2)
        
        # 滚动区域
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setMaximumHeight(200)
        scroll_area.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.setSpacing(2)
        
        self._template_buttons = []
        for name, content, prompt_type in self._prompts:
            btn = QPushButton(name)
            btn.setObjectName("dropdown_item")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked, n=name, c=content, t=prompt_type: self._on_template_clicked(n, c, t))
            scroll_layout.addWidget(btn)
            self._template_buttons.append((name, btn))
        
        scroll_area.setWidget(scroll_content)
        dropdown_layout.addWidget(scroll_area)
        
        # 安装事件过滤器，拦截输入框的上下键
        self.ai_input.installEventFilter(self)
    
    def _on_input_text_changed(self, text: str):
        """输入框文本变化 - 输入 / 时显示模板列表"""
        if '/' in text:
            slash_idx = text.rfind('/')
            search_term = text[slash_idx + 1:].lower()
            
            visible_count = 0
            for name, btn in self._template_buttons:
                if search_term == '' or search_term in name.lower():
                    btn.show()
                    visible_count += 1
                else:
                    btn.hide()
            
            if visible_count > 0:
                self._show_dropdown()
            else:
                self._dropdown.hide()
        else:
            self._dropdown.hide()
    
    def _update_enter_hint(self, text: str):
        """输入框有文字时显示 Enter 键发送提示"""
        if text.strip():
            self._enter_hint.adjustSize()
            x = self.ai_input.width() - self._enter_hint.width() - 4
            y = (self.ai_input.height() - self._enter_hint.height()) // 2
            self._enter_hint.move(x, y)
            self._enter_hint.show()
        else:
            self._enter_hint.hide()
    
    def _show_dropdown(self):
        """显示下拉列表"""
        self._dropdown_selected_index = -1
        self._update_dropdown_highlight()
        self._dropdown.adjustSize()
        
        # 定位到输入框下方
        input_pos = self.ai_input.mapToGlobal(QPoint(0, self.ai_input.height() + 4))
        self._dropdown.move(input_pos)
        self._dropdown.setFixedWidth(self.ai_input.width())
        self._dropdown.show()
        self._dropdown.raise_()
    
    def eventFilter(self, obj, event):
        """拦截输入框的上下键和 Enter 键，用于导航下拉列表"""
        if obj is self.ai_input and event.type() == QEvent.Type.KeyPress and self._dropdown.isVisible():
            key = event.key()
            visible_items = [(i, name, btn) for i, (name, btn) in enumerate(self._template_buttons) if btn.isVisible()]
            if not visible_items:
                return super().eventFilter(obj, event)
            
            if key == Qt.Key.Key_Down:
                # 在可见项中向下移动
                current_vis_idx = -1
                for vi, (i, name, btn) in enumerate(visible_items):
                    if i == self._dropdown_selected_index:
                        current_vis_idx = vi
                        break
                next_vis_idx = min(current_vis_idx + 1, len(visible_items) - 1)
                self._dropdown_selected_index = visible_items[next_vis_idx][0]
                self._update_dropdown_highlight()
                return True
            
            elif key == Qt.Key.Key_Up:
                current_vis_idx = len(visible_items)
                for vi, (i, name, btn) in enumerate(visible_items):
                    if i == self._dropdown_selected_index:
                        current_vis_idx = vi
                        break
                next_vis_idx = max(current_vis_idx - 1, 0)
                self._dropdown_selected_index = visible_items[next_vis_idx][0]
                self._update_dropdown_highlight()
                return True
            
            elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if self._dropdown_selected_index >= 0:
                    name, btn = self._template_buttons[self._dropdown_selected_index]
                    btn.click()
                    return True
            
            elif key == Qt.Key.Key_Escape:
                self._dropdown.hide()
                return True
        
        return super().eventFilter(obj, event)
    
    def _update_dropdown_highlight(self):
        """更新下拉列表中的高亮项"""
        for i, (name, btn) in enumerate(self._template_buttons):
            if i == self._dropdown_selected_index:
                btn.setStyleSheet("QPushButton#dropdown_item { background-color: rgba(99, 102, 241, 0.12); color: #4f46e5; }")
            else:
                btn.setStyleSheet("")
    
    def _on_template_clicked(self, name: str, content: str, prompt_type: str):
        """点击模板"""
        current_text = self.ai_input.text()
        self._selected_prompt_content = content
        
        # 自动切换模式
        self._set_mode(prompt_type)
        
        # 替换 / 及其后的内容
        if '/' in current_text:
            slash_idx = current_text.rfind('/')
            new_text = current_text[:slash_idx] + f"[{name}] "
        else:
            new_text = f"[{name}] " + current_text
        
        self.ai_input.setText(new_text)
        self.ai_input.setFocus()
        self._dropdown.hide()
    
    def _toggle_mode(self):
        """切换模式"""
        if self._selected_prompt_type == "text":
            self._set_mode("image")
        else:
            self._set_mode("text")
    
    def _set_mode(self, mode: str):
        """设置模式并更新 UI"""
        self._selected_prompt_type = mode
        if mode == "text":
            self.btn_mode.setText("文本")
            self.btn_mode.setObjectName("btn_mode_text")
            self.btn_mode.setToolTip("当前：文本分析\n点击切换到图片生成")
            self.btn_send.setIcon(qta.icon('mdi6.creation', color='#ffffff'))
            self.btn_send.setStyleSheet(self._STYLE_AI_BTN_TEXT)
        else:
            self.btn_mode.setText("图片")
            self.btn_mode.setObjectName("btn_mode_image")
            self.btn_mode.setToolTip("当前：图片生成\n点击切换到文本分析")
            self.btn_send.setIcon(qta.icon('mdi6.palette-outline', color='#ffffff'))
            self.btn_send.setStyleSheet(self._STYLE_AI_BTN_IMAGE)
        # 刷新样式
        self.btn_mode.style().unpolish(self.btn_mode)
        self.btn_mode.style().polish(self.btn_mode)
    
    def _on_custom_ai_send(self):
        """发送自定义 Prompt"""
        text = self.ai_input.text().strip()
        if not text:
            return
        
        # 解析模板
        match = re.search(r'\[(.+?)\]', text)
        if match:
            template_name = match.group(1)
            prompt_content = None
            for name, content, ptype in self._prompts:
                if name == template_name:
                    prompt_content = content
                    break
            
            if prompt_content:
                extra_text = re.sub(r'\[.+?\]\s*', '', text).strip()
                if extra_text:
                    final_prompt = f"{prompt_content}\n\n用户补充要求：{extra_text}"
                else:
                    final_prompt = prompt_content
                self._do_ai_process(final_prompt, self._selected_prompt_type)
            else:
                self._do_ai_process(text, self._selected_prompt_type)
        else:
            self._do_ai_process(text, self._selected_prompt_type)
        
        self.ai_input.clear()
    
    def _do_ai_process(self, prompt: str, prompt_type: str):
        """执行 AI 处理"""
        if not self._pixmap:
            return
        
        # 转换图片为 base64
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        self._pixmap.save(buffer, "PNG")
        base64_data = base64.b64encode(buffer.data().data()).decode()
        
        # 调用胶囊进行 AI 处理
        app = QApplication.instance()
        if hasattr(app, '_capsule_widget') and app._capsule_widget:
            capsule = app._capsule_widget
            capsule.start_ai_processing(base64_data, prompt, prompt_type)


class ArchiveCard(QWidget):
    """单条归档记录卡片 - 画廊模式"""
    clicked = Signal(dict)
    delete_requested = Signal(str)
    
    def __init__(self, record: dict, parent=None):
        super().__init__(parent)
        self.record = record
        self._drag_start_pos = None
        self.init_ui()
    
    def init_ui(self):
        self.setFixedSize(160, 160)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setObjectName("archive_card")
        
        # 主布局
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # 封面容器
        self.cover_container = QWidget()
        self.cover_container.setFixedSize(160, 130)
        self.cover_container.setObjectName("cover_container")
        cover_layout = QVBoxLayout(self.cover_container)
        cover_layout.setContentsMargins(0, 0, 0, 0)
        cover_layout.setSpacing(0)
        
        # 缩略图 - 懒加载，先显示占位符
        image_path = get_image_full_path(self.record.get("image_path", ""))
        self._image_path = str(image_path) if image_path.exists() else None
        
        self.thumb_label = QLabel()
        self.thumb_label.setFixedSize(160, 130)
        self.thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb_label.setObjectName("thumb_label")
        self.thumb_label.setStyleSheet("background: #f5f5f5;")
        
        if self._image_path:
            # 分散延迟加载，避免同时加载
            import random
            delay = random.randint(50, 300)
            QTimer.singleShot(delay, self._lazy_load_thumb)
        else:
            self.thumb_label.setText("图片缺失")
        
        cover_layout.addWidget(self.thumb_label)
        layout.addWidget(self.cover_container)
        
        # 删除按钮 - 右上角悬浮
        self.btn_delete = QPushButton(self.cover_container)
        self.btn_delete.setIcon(qta.icon('mdi6.close', color='#fff'))
        self.btn_delete.setIconSize(QSize(14, 14))
        self.btn_delete.setFixedSize(24, 24)
        self.btn_delete.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_delete.clicked.connect(self._request_delete)
        self.btn_delete.setObjectName("btn_delete_overlay")
        self.btn_delete.move(132, 4)
        self.btn_delete.hide()
        
        # AI角标 - 左上角
        ai_text = self.record.get("ai_text", "")
        tags = self.record.get("tags", "")
        has_ai = bool(ai_text.strip())
        is_ai_generated = "ai_generated" in tags.lower() if tags else False
        
        if has_ai or is_ai_generated:
            self.badge = QLabel(self.cover_container)
            self.badge.setObjectName("ai_badge")
            if is_ai_generated:
                self.badge.setText("AI生成")
                self.badge.setStyleSheet("""
                    QLabel#ai_badge {
                        background-color: rgba(236, 72, 153, 0.9);
                        color: white;
                        font-size: 10px;
                        font-weight: bold;
                        padding: 2px 6px;
                        border-radius: 3px;
                    }
                """)
            else:
                self.badge.setText("AI")
                self.badge.setStyleSheet("""
                    QLabel#ai_badge {
                        background-color: rgba(99, 102, 241, 0.9);
                        color: white;
                        font-size: 10px;
                        font-weight: bold;
                        padding: 2px 6px;
                        border-radius: 3px;
                    }
                """)
            self.badge.adjustSize()
            self.badge.move(6, 6)
        
        # 时间标签
        timestamp = self.record.get("timestamp", "")
        try:
            dt = datetime.fromisoformat(timestamp)
            time_str = dt.strftime("%m-%d %H:%M")
        except ValueError:
            time_str = timestamp[:11] if len(timestamp) > 11 else timestamp
        
        time_label = QLabel(time_str)
        time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        time_label.setObjectName("time_label")
        time_label.setFixedHeight(30)
        layout.addWidget(time_label)
        
        self.setStyleSheet("""
            QWidget#archive_card {
                background-color: #fff;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
            }
            QWidget#archive_card:hover {
                border: 1px solid #0078d7;
            }
            QLabel#thumb_label {
                background-color: #f5f5f5;
                border-radius: 8px 8px 0 0;
            }
            QLabel#time_label {
                color: #666;
                font-size: 11px;
                background-color: transparent;
            }
            QPushButton#btn_delete_overlay {
                background-color: rgba(0, 0, 0, 0.5);
                border: none;
                border-radius: 12px;
            }
            QPushButton#btn_delete_overlay:hover {
                background-color: rgba(239, 68, 68, 0.9);
            }
        """)
    
    def enterEvent(self, event):
        self.btn_delete.show()
        super().enterEvent(event)
    
    def leaveEvent(self, event):
        self.btn_delete.hide()
        super().leaveEvent(event)
    
    def _lazy_load_thumb(self):
        """延迟加载缩略图 - 使用 QImageReader 高效加载"""
        if not self._image_path:
            return
        try:
            from PySide6.QtGui import QImageReader
            reader = QImageReader(self._image_path)
            if reader.canRead():
                # 直接读取缩放后的尺寸，避免加载原图
                reader.setScaledSize(QSize(160, 130))
                image = reader.read()
                if not image.isNull():
                    pixmap = QPixmap.fromImage(image)
                    self.thumb_label.setPixmap(pixmap)
                    self.thumb_label.setStyleSheet("")
        except Exception:
            pass
    
    def _request_delete(self):
        self.delete_requested.emit(self.record.get("id", ""))
    
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            child = self.childAt(event.pos())
            if child and isinstance(child, QPushButton):
                return super().mousePressEvent(event)
            self._drag_start_pos = event.pos()
        super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        if not self._drag_start_pos:
            return super().mouseMoveEvent(event)
        
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return super().mouseMoveEvent(event)
        
        # 检查是否超过拖拽阈值
        if (event.pos() - self._drag_start_pos).manhattanLength() < 10:
            return super().mouseMoveEvent(event)
        
        # 开始拖拽
        if self._image_path:
            drag = QDrag(self)
            mime_data = QMimeData()
            mime_data.setUrls([QUrl.fromLocalFile(self._image_path)])
            drag.setMimeData(mime_data)
            
            # 设置拖拽预览图
            pixmap = self.thumb_label.pixmap()
            if pixmap:
                scaled = pixmap.scaled(80, 65, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                drag.setPixmap(scaled)
                drag.setHotSpot(QPoint(scaled.width() // 2, scaled.height() // 2))
            
            drag.exec(Qt.DropAction.CopyAction)
        
        self._drag_start_pos = None
    
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._drag_start_pos:
            # 没有拖拽，视为点击
            child = self.childAt(event.pos())
            if not (child and isinstance(child, QPushButton)):
                self.clicked.emit(self.record)
        self._drag_start_pos = None
        super().mouseReleaseEvent(event)


# ============================================================
# 剪贴板历史相关类
# ============================================================

# 资源管理器里「复制」单个图片文件时，剪贴板多为 URL/路径；按扩展名加载为位图，历史里存图片而非路径
_CLIPBOARD_IMAGE_FILE_EXTENSIONS = frozenset({
    ".png", ".jpg", ".jpeg", ".jfif", ".webp", ".bmp", ".gif", ".tif", ".tiff", ".ico",
})
_MAX_CLIPBOARD_IMAGE_FILE_BYTES = 256 * 1024 * 1024  # 超过则仍按「文件」记录，避免内存爆
_MAX_CLIPBOARD_IMAGE_PIXELS = 50_000_000  # 解码后像素数上限（≈200MB @ 4字节/像素），超过则不加载全图


def _is_probably_image_file(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in _CLIPBOARD_IMAGE_FILE_EXTENSIONS


def _load_pixmap_from_local_image_file(path: str) -> Optional[QPixmap]:
    if not path or not os.path.isfile(path):
        return None
    try:
        if os.path.getsize(path) > _MAX_CLIPBOARD_IMAGE_FILE_BYTES:
            return None
    except OSError:
        return None
    # 像素维度检查：用 QImageReader 读取尺寸，避免解码超大像素图导致内存爆炸
    # 例如 11000×7000 = 7700万像素 ≈ 308MB 解码内存，文件可能仅 17MB
    from PySide6.QtGui import QImageReader
    reader = QImageReader(path)
    if reader.canRead():
        size = reader.size()
        if size.width() * size.height() > _MAX_CLIPBOARD_IMAGE_PIXELS:
            return None
    pm = QPixmap(path)
    if pm.isNull():
        return None
    return pm


class ClipboardItem:
    """剪贴板历史项"""
    def __init__(
        self,
        content_type: str,
        content: Any,
        timestamp: datetime = None,
        source_file_path: Optional[str] = None,
    ):
        self.content_type = content_type  # "image" | "text" | "file"
        self.content = content  # QPixmap | str | List[str]（本地路径）
        self.timestamp = timestamp or datetime.now()
        self.id = f"{self.timestamp.timestamp():.6f}"
        self.source_file_path = os.path.normpath(source_file_path) if source_file_path else None
    
    def file_paths(self) -> List[str]:
        """file 类型：本地路径列表（其它类型为空）"""
        if self.content_type != "file":
            return []
        c = self.content
        if isinstance(c, list):
            return [p for p in c if p]
        return [c] if c else []
    
    def get_detail_plain_text(self) -> str:
        """详情弹窗展示的纯文本"""
        if self.content_type == "file":
            return "\n".join(self.file_paths())
        if self.content_type == "text":
            return self.content
        return ""
    
    def get_preview_text(self, max_len: int = 100) -> str:
        """获取预览文本"""
        if self.content_type == "text":
            text = self.content.replace('\n', ' ').strip()
            return text[:max_len] + "..." if len(text) > max_len else text
        if self.content_type == "file":
            paths = self.file_paths()
            if not paths:
                return ""
            if len(paths) == 1:
                s = os.path.basename(paths[0])
            else:
                s = f"{len(paths)} 个文件"
            return s[:max_len] + "..." if len(s) > max_len else s
        return ""
    
    def try_get_pixmap(self) -> Optional[QPixmap]:
        """image 直接返回；file 为单个图片路径时尝试加载（用于写入剪贴板为图片而非路径）"""
        if self.content_type == "image":
            pm = self.content
            return pm if pm and not pm.isNull() else None
        if self.content_type == "file":
            paths = self.file_paths()
            if len(paths) == 1 and _is_probably_image_file(paths[0]):
                return _load_pixmap_from_local_image_file(paths[0])
        return None

    def try_get_thumbnail(self, width: int = 152, height: int = 122) -> Optional[QPixmap]:
        """高效获取缩略图（使用 QImageReader 解码阶段缩放，不受 256MB 限制，内存占用极低）。
        image 类型直接缩放返回；file 类型为单个图片文件时用 QImageReader 按需解码。
        非图片或解码失败返回 None。"""
        if self.content_type == "image":
            pm = self.content
            if pm and not pm.isNull():
                return pm.scaled(width, height, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                 Qt.TransformationMode.SmoothTransformation)
            return None
        if self.content_type == "file":
            paths = self.file_paths()
            if len(paths) == 1 and _is_probably_image_file(paths[0]):
                from PySide6.QtGui import QImageReader
                reader = QImageReader(paths[0])
                if reader.canRead():
                    reader.setScaledSize(QSize(width, height))
                    img = reader.read()
                    if not img.isNull():
                        return QPixmap.fromImage(img)
            return None
        return None


class ClipboardHistoryManager:
    """剪贴板历史管理器（单例）"""
    _instance = None
    _items: List[ClipboardItem] = []
    _max_items = 40
    _listeners: List[callable] = []
    
    @classmethod
    def instance(cls) -> "ClipboardHistoryManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def __init__(self):
        if ClipboardHistoryManager._instance is not None:
            return
        self._items = []
        self._listeners = []
        self._last_content_hash = None
        self._monitoring = False
    
    def start_monitoring(self):
        """开始监听剪贴板"""
        if self._monitoring:
            return
        self._monitoring = True
        clipboard = QApplication.clipboard()
        clipboard.dataChanged.connect(self._on_clipboard_changed)
    
    def stop_monitoring(self):
        """停止监听"""
        if not self._monitoring:
            return
        self._monitoring = False
        try:
            clipboard = QApplication.clipboard()
            clipboard.dataChanged.disconnect(self._on_clipboard_changed)
        except RuntimeError:
            pass
    
    def _on_clipboard_changed(self):
        """剪贴板内容变化（防抖：企微等应用可能连续触发多次，只处理最终状态）"""
        if not hasattr(self, '_debounce_timer') or self._debounce_timer is None:
            self._debounce_timer = QTimer()
            self._debounce_timer.setSingleShot(True)
            self._debounce_timer.timeout.connect(self._process_clipboard)
        self._debounce_timer.start(150)

    def _process_clipboard(self):
        """实际处理剪贴板内容（防抖后调用，读取最终状态）"""
        clipboard = QApplication.clipboard()
        mime_data = clipboard.mimeData()

        # 优先级1：图片数据
        # 企微等 Electron 应用复制图片时会同时附带 file:// 文本，
        # 优先取图片，避免把 file:// 地址当文本塞进历史格子
        # 但超大图（>256MB）仍走文件路径，避免内存爆炸
        if mime_data.hasImage():
            # 大图守卫：如果同时有本地文件 URL 且文件超 256MB 或像素数超 5000万，跳过图片加载
            _skip_image = False
            _skip_file_path = None
            if mime_data.hasUrls():
                for u in mime_data.urls():
                    if u.isLocalFile():
                        fp = u.toLocalFile()
                        if os.path.isfile(fp):
                            if os.path.getsize(fp) > _MAX_CLIPBOARD_IMAGE_FILE_BYTES:
                                _skip_image = True
                                _skip_file_path = fp
                                break
                            # 像素维度检查：文件可能很小但像素数巨大（如 11000×7000 JPEG 仅 17MB 但解码 308MB）
                            from PySide6.QtGui import QImageReader
                            ir = QImageReader(fp)
                            if ir.canRead():
                                sz = ir.size()
                                if sz.width() * sz.height() > _MAX_CLIPBOARD_IMAGE_PIXELS:
                                    _skip_image = True
                                    _skip_file_path = fp
                                    break
            if _skip_image and _skip_file_path:
                # 超大图直接创建 file 条目，避免落入优先级2重复 QImageReader 检查
                content_hash = hash(tuple([os.path.normcase(_skip_file_path)]))
                if content_hash != self._last_content_hash:
                    self._last_content_hash = content_hash
                    self._add_item(ClipboardItem("file", [_skip_file_path]))
                return
            # 正常图片（非超大图）：加载 pixmap 并添加到历史
            pixmap = self._get_image_from_mime_data(mime_data, clipboard)
            if pixmap is not None and not pixmap.isNull():
                content_hash = self._compute_image_hash(pixmap)
                if content_hash and content_hash != self._last_content_hash:
                    self._last_content_hash = content_hash
                    self._add_item(ClipboardItem("image", pixmap))
                return

        # 优先级2：本地文件 URL
        if mime_data.hasUrls():
            local_paths: List[str] = []
            seen = set()
            for u in mime_data.urls():
                if u.isLocalFile():
                    p = os.path.normpath(u.toLocalFile())
                    if p and p not in seen:
                        seen.add(p)
                        local_paths.append(p)
            if local_paths:
                if len(local_paths) == 1 and _is_probably_image_file(local_paths[0]):
                    pm = _load_pixmap_from_local_image_file(local_paths[0])
                    if pm is not None and not pm.isNull():
                        content_hash = self._compute_image_hash(pm)
                        if content_hash and content_hash != self._last_content_hash:
                            self._last_content_hash = content_hash
                            self._add_item(ClipboardItem("image", pm, source_file_path=local_paths[0]))
                        return
                content_hash = hash(tuple(local_paths))
                if content_hash != self._last_content_hash:
                    self._last_content_hash = content_hash
                    self._add_item(ClipboardItem("file", local_paths))
                return

        # 优先级3：文本（过滤纯 file:// 地址）
        if mime_data.hasText():
            text = clipboard.text()
            if text.strip():
                stripped = text.strip()
                lines = [l.strip() for l in stripped.split('\n') if l.strip()]
                if lines and all(l.startswith('file://') for l in lines):
                    return
                content_hash = hash(text)
                if content_hash != self._last_content_hash:
                    self._last_content_hash = content_hash
                    self._add_item(ClipboardItem("text", text))
    
    def _compute_image_hash(self, pixmap: QPixmap) -> int:
        """计算图片内容哈希（用于去重）"""
        if pixmap.isNull():
            return 0
        try:
            # 缩放到小图后计算哈希（平衡性能和准确性）
            small = pixmap.scaled(32, 32, Qt.AspectRatioMode.KeepAspectRatio,
                                  Qt.TransformationMode.FastTransformation)
            image = small.toImage()
            if image.isNull():
                return 0
            
            # 获取图片数据
            bits = image.bits()
            if bits:
                # 计算整个图片数据的哈希（32x32 图片很小，性能可接受）
                byte_count = image.sizeInBytes()
                # 尝试不同方法获取字节数据
                if hasattr(bits, 'tobytes'):
                    data = bits.tobytes(byte_count)
                elif hasattr(bits, 'asstring'):
                    data = bits.asstring(byte_count)
                elif hasattr(bits, '__getitem__'):
                    data = bytes(bits[:byte_count])
                else:
                    # 回退：使用图片尺寸和格式
                    return hash((image.width(), image.height(), image.format()))
                return hash(data)
        except Exception:
            pass
        # 回退：使用图片尺寸和格式（避免使用 cacheKey，因为每次创建都不同）
        return hash((pixmap.width(), pixmap.height(), pixmap.hasAlphaChannel()))
    
    def _compute_item_hash(self, item: ClipboardItem) -> int:
        """计算剪贴板项的哈希值"""
        if item.content_type == "image":
            return self._compute_image_hash(item.content)
        if item.content_type == "file":
            return hash(tuple(os.path.normcase(p) for p in item.file_paths()))
        return hash(item.content)
    
    def _get_image_from_mime_data(self, mime_data, clipboard) -> QPixmap:
        """从 MIME 数据中获取图片（多方式尝试）"""
        # 方式1: 直接获取 pixmap
        pixmap = clipboard.pixmap()
        if not pixmap.isNull():
            return pixmap
        
        # 方式2: 从 imageData 获取
        if mime_data.hasImage():
            image_variant = mime_data.imageData()
            if image_variant:
                from PySide6.QtGui import QImage
                if isinstance(image_variant, QImage):
                    return QPixmap.fromImage(image_variant)
        
        # 方式3: 从 image() 获取
        image = clipboard.image()
        if not image.isNull():
            return QPixmap.fromImage(image)
        
        # 方式4: 从 URLs 获取（某些应用会把图片保存为临时文件）
        if mime_data.hasUrls():
            for url in mime_data.urls():
                if url.isLocalFile():
                    file_path = url.toLocalFile()
                    # 过滤掉我们自己的拖拽临时文件
                    if 'artco_drag' in file_path.lower():
                        continue
                    if os.path.exists(file_path):
                        pixmap = QPixmap(file_path)
                        if not pixmap.isNull():
                            return pixmap
        
        # 方式5: 从 bytes 加载（尝试常见格式）
        for fmt in ['image/png', 'image/bmp', 'image/jpeg', 'image/x-png']:
            if mime_data.hasFormat(fmt):
                data = mime_data.data(fmt)
                if data:
                    pixmap = QPixmap()
                    if pixmap.loadFromData(data):
                        return pixmap
        
        return None
    

    
    def _add_item(self, item: ClipboardItem):
        """添加历史项（自动去重）"""
        # 计算新项的哈希值
        new_hash = self._compute_item_hash(item)
        
        # 移除所有具有相同哈希值的旧项
        self._items = [existing for existing in self._items if self._compute_item_hash(existing) != new_hash]
        
        # 将新项插入到开头
        self._items.insert(0, item)
        
        # 限制数量
        if len(self._items) > self._max_items:
            self._items = self._items[:self._max_items]
        
        # 通知监听者
        for listener in self._listeners:
            try:
                listener()
            except Exception:
                pass
    
    def add_listener(self, callback: callable):
        """添加更新监听"""
        if callback not in self._listeners:
            self._listeners.append(callback)
    
    def remove_listener(self, callback: callable):
        """移除监听"""
        if callback in self._listeners:
            self._listeners.remove(callback)
    
    def get_items(self) -> List[ClipboardItem]:
        """获取所有历史项"""
        return self._items.copy()
    
    def get_item(self, item_id: str) -> Optional[ClipboardItem]:
        """根据 ID 获取项"""
        for item in self._items:
            if item.id == item_id:
                return item
        return None
    
    def delete_item(self, item_id: str) -> bool:
        """删除指定项"""
        for i, item in enumerate(self._items):
            if item.id == item_id:
                self._items.pop(i)
                for listener in self._listeners:
                    try:
                        listener()
                    except Exception:
                        pass
                return True
        return False
    
    def clear(self):
        """清空历史"""
        self._items.clear()
        for listener in self._listeners:
            try:
                listener()
            except Exception:
                pass


class ClipboardCard(QWidget):
    """剪贴板历史卡片"""
    clicked = Signal(str)  # item_id
    delete_requested = Signal(str)  # item_id
    
    def __init__(self, item: ClipboardItem, parent=None):
        super().__init__(parent)
        self.item = item
        self.init_ui()
    
    def init_ui(self):
        self.setFixedSize(160, 160)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setObjectName("clipboard_card")
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # 内容容器
        self.content_container = QWidget()
        self.content_container.setFixedSize(160, 130)
        self.content_container.setObjectName("content_container")
        content_layout = QVBoxLayout(self.content_container)
        content_layout.setContentsMargins(4, 4, 4, 4)
        content_layout.setSpacing(0)
        
        if self.item.content_type == "image":
            # 图片类型
            thumb_label = QLabel()
            thumb_label.setFixedSize(152, 122)
            thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            pixmap = self.item.content
            if pixmap and not pixmap.isNull():
                scaled = pixmap.scaled(152, 122, Qt.AspectRatioMode.KeepAspectRatioByExpanding, 
                                       Qt.TransformationMode.SmoothTransformation)
                if scaled.width() > 152 or scaled.height() > 122:
                    x = (scaled.width() - 152) // 2
                    y = (scaled.height() - 122) // 2
                    scaled = scaled.copy(x, y, 152, 122)
                thumb_label.setPixmap(scaled)
            content_layout.addWidget(thumb_label)
            
            # 图片角标
            self.type_badge = QLabel(self.content_container)
            self.type_badge.setText("图片")
            self.type_badge.setObjectName("type_badge_image")
            self.type_badge.adjustSize()
            self.type_badge.move(6, 6)
        elif self.item.content_type == "file":
            # 如果是单个图片文件，尝试用 QImageReader 高效加载缩略图
            thumb = self.item.try_get_thumbnail(152, 122)
            if thumb is not None and not thumb.isNull():
                thumb_label = QLabel()
                thumb_label.setFixedSize(152, 122)
                thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                scaled = thumb.scaled(152, 122, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                      Qt.TransformationMode.SmoothTransformation)
                if scaled.width() > 152 or scaled.height() > 122:
                    x = (scaled.width() - 152) // 2
                    y = (scaled.height() - 122) // 2
                    scaled = scaled.copy(x, y, 152, 122)
                thumb_label.setPixmap(scaled)
                content_layout.addWidget(thumb_label)
                self.type_badge = QLabel(self.content_container)
                self.type_badge.setText("图片")
                self.type_badge.setObjectName("type_badge_image")
                self.type_badge.adjustSize()
                self.type_badge.move(6, 6)
            else:
                text_label = QLabel()
                text_label.setFixedSize(152, 122)
                text_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
                text_label.setWordWrap(True)
                text_label.setObjectName("text_preview")
                text_label.setText(self.item.get_preview_text(150))
                content_layout.addWidget(text_label)
                self.type_badge = QLabel(self.content_container)
                self.type_badge.setText("文件")
                self.type_badge.setObjectName("type_badge_file")
                self.type_badge.adjustSize()
                self.type_badge.move(6, 6)
        else:
            # 文本类型
            text_label = QLabel()
            text_label.setFixedSize(152, 122)
            text_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
            text_label.setWordWrap(True)
            text_label.setObjectName("text_preview")
            preview_text = self.item.get_preview_text(150)
            text_label.setText(preview_text)
            content_layout.addWidget(text_label)
            
            # 文本角标
            self.type_badge = QLabel(self.content_container)
            self.type_badge.setText("文本")
            self.type_badge.setObjectName("type_badge_text")
            self.type_badge.adjustSize()
            self.type_badge.move(6, 6)
        
        layout.addWidget(self.content_container)
        
        # 删除按钮
        self.btn_delete = QPushButton(self.content_container)
        self.btn_delete.setIcon(qta.icon('mdi6.close', color='#fff'))
        self.btn_delete.setIconSize(QSize(14, 14))
        self.btn_delete.setFixedSize(24, 24)
        self.btn_delete.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_delete.clicked.connect(lambda: self.delete_requested.emit(self.item.id))
        self.btn_delete.setObjectName("btn_delete_overlay")
        self.btn_delete.move(132, 4)
        self.btn_delete.hide()
        
        # 时间标签
        time_str = self.item.timestamp.strftime("%H:%M:%S")
        time_label = QLabel(time_str)
        time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        time_label.setObjectName("time_label")
        time_label.setFixedHeight(30)
        layout.addWidget(time_label)
        
        self.setStyleSheet("""
            QWidget#clipboard_card {
                background-color: #fff;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
            }
            QWidget#clipboard_card:hover {
                border: 1px solid #10b981;
            }
            QWidget#content_container {
                background-color: #f9fafb;
                border-radius: 8px 8px 0 0;
            }
            QLabel#text_preview {
                color: #374151;
                font-size: 12px;
                padding: 4px;
                background: transparent;
            }
            QLabel#time_label {
                color: #666;
                font-size: 11px;
                background-color: transparent;
            }
            QLabel#type_badge_image {
                background-color: rgba(99, 102, 241, 0.9);
                color: white;
                font-size: 10px;
                font-weight: bold;
                padding: 2px 6px;
                border-radius: 3px;
            }
            QLabel#type_badge_text {
                background-color: rgba(16, 185, 129, 0.9);
                color: white;
                font-size: 10px;
                font-weight: bold;
                padding: 2px 6px;
                border-radius: 3px;
            }
            QLabel#type_badge_file {
                background-color: rgba(245, 158, 11, 0.95);
                color: white;
                font-size: 10px;
                font-weight: bold;
                padding: 2px 6px;
                border-radius: 3px;
            }
            QPushButton#btn_delete_overlay {
                background-color: rgba(0, 0, 0, 0.5);
                border: none;
                border-radius: 12px;
            }
            QPushButton#btn_delete_overlay:hover {
                background-color: rgba(239, 68, 68, 0.9);
            }
        """)
    
    def enterEvent(self, event):
        self.btn_delete.show()
        super().enterEvent(event)
    
    def leaveEvent(self, event):
        self.btn_delete.hide()
        super().leaveEvent(event)
    
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            child = self.childAt(event.pos())
            if child and isinstance(child, QPushButton):
                return super().mousePressEvent(event)
        super().mousePressEvent(event)
    
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            child = self.childAt(event.pos())
            if not (child and isinstance(child, QPushButton)):
                self.clicked.emit(self.item.id)
        super().mouseReleaseEvent(event)


class ClipboardTextDetailDialog(QWidget):
    """剪贴板文本详情窗口"""
    
    def __init__(self, item: ClipboardItem, parent=None):
        super().__init__(parent)
        self.item = item
        self.setWindowTitle("文件详情" if item.content_type == "file" else "文本详情")
        self.setWindowFlags(Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setMinimumSize(500, 400)
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)
        
        # 顶部信息
        header_layout = QHBoxLayout()
        
        # 时间
        time_icon = QLabel()
        time_icon.setPixmap(qta.icon('mdi6.clock', color='#666').pixmap(16, 16))
        header_layout.addWidget(time_icon)
        
        time_str = self.item.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        time_label = QLabel(time_str)
        time_label.setStyleSheet("font-size: 13px; color: #666;")
        header_layout.addWidget(time_label)
        
        header_layout.addStretch()
        
        # 复制按钮
        btn_copy = QPushButton(" 复制")
        btn_copy.setIcon(qta.icon('mdi6.content-copy', color='#555'))
        btn_copy.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_copy.clicked.connect(self._copy_text)
        header_layout.addWidget(btn_copy)
        
        layout.addLayout(header_layout)
        
        detail_text = self.item.get_detail_plain_text()
        # 文本内容
        self.text_edit = QTextEdit()
        self.text_edit.setPlainText(detail_text)
        self.text_edit.setReadOnly(True)
        self.text_edit.setStyleSheet(f"""
            QTextEdit {{
                background-color: #fafafa;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                font-family: {FONT_FAMILY_MONO};
                font-size: 13px;
                padding: 12px;
                color: #333;
            }}
        """)
        layout.addWidget(self.text_edit)
        
        # 字符统计
        if self.item.content_type == "file":
            n = len(self.item.file_paths())
            stats_label = QLabel(f"共 {n} 个文件")
        else:
            char_count = len(detail_text)
            line_count = detail_text.count('\n') + 1
            stats_label = QLabel(f"共 {char_count} 个字符，{line_count} 行")
        stats_label.setStyleSheet("color: #999; font-size: 12px;")
        stats_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        layout.addWidget(stats_label)
        
        self.setStyleSheet("""
            QWidget { background-color: #ffffff; }
            QPushButton {
                background-color: #f5f5f5;
                border: 1px solid #ddd;
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 13px;
            }
            QPushButton:hover { background-color: #e8e8e8; }
        """)
    
    def _copy_text(self):
        """复制到剪贴板（优先图片数据，否则文件 URL 或纯文本）"""
        pm = self.item.try_get_pixmap()
        if pm is not None and not pm.isNull():
            QGuiApplication.clipboard().setPixmap(pm)
            try:
                QGuiApplication.clipboard().setImage(pm.toImage())
            except Exception:
                pass
            return
        if self.item.content_type == "file":
            paths = self.item.file_paths()
            mime = QMimeData()
            mime.setUrls([QUrl.fromLocalFile(p) for p in paths])
            QGuiApplication.clipboard().setMimeData(mime)
        else:
            QGuiApplication.clipboard().setText(self.item.content)


class ClipboardImageViewer(QWidget):
    """剪贴板图片查看器"""
    
    def __init__(self, item: ClipboardItem, parent=None):
        super().__init__(parent)
        self.item = item
        self._pixmap = item.content
        self._scale = 1.0
        self._offset = QPoint(0, 0)
        self._dragging = False
        self._drag_start = QPoint()
        
        self.setWindowTitle("图片预览")
        self.setWindowFlags(Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setMinimumSize(600, 500)
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # 工具栏
        toolbar = QWidget()
        toolbar.setFixedHeight(44)
        toolbar.setStyleSheet("background-color: #f8f9fa; border-bottom: 1px solid #e0e0e0;")
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(12, 0, 12, 0)
        toolbar_layout.setSpacing(8)
        
        # 时间
        time_str = self.item.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        time_label = QLabel(time_str)
        time_label.setStyleSheet("font-size: 12px; color: #666;")
        toolbar_layout.addWidget(time_label)
        
        toolbar_layout.addStretch()
        
        # 尺寸信息
        size_label = QLabel(f"{self._pixmap.width()} × {self._pixmap.height()}")
        size_label.setStyleSheet("font-size: 12px; color: #888;")
        toolbar_layout.addWidget(size_label)
        
        # 适应窗口
        btn_fit = QPushButton()
        btn_fit.setIcon(qta.icon('mdi6.fit-to-screen', color='#555'))
        btn_fit.setFixedSize(32, 32)
        btn_fit.setToolTip("适应窗口")
        btn_fit.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_fit.clicked.connect(self._fit_image)
        toolbar_layout.addWidget(btn_fit)
        
        # 原始大小
        btn_actual = QPushButton()
        btn_actual.setIcon(qta.icon('mdi6.image-size-select-actual', color='#555'))
        btn_actual.setFixedSize(32, 32)
        btn_actual.setToolTip("原始大小")
        btn_actual.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_actual.clicked.connect(self._actual_size)
        toolbar_layout.addWidget(btn_actual)
        
        # 复制
        btn_copy = QPushButton()
        btn_copy.setIcon(qta.icon('mdi6.content-copy', color='#555'))
        btn_copy.setFixedSize(32, 32)
        btn_copy.setToolTip("复制图片")
        btn_copy.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_copy.clicked.connect(self._copy_image)
        toolbar_layout.addWidget(btn_copy)
        
        layout.addWidget(toolbar)
        
        # 图片画布
        self.canvas = QLabel()
        self.canvas.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.canvas.setStyleSheet("background-color: #e5e7eb;")
        self.canvas.setMouseTracking(True)
        layout.addWidget(self.canvas)
        
        self.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: 1px solid #ddd;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #e8e8e8; }
        """)
        
        # 初始适应窗口
        QTimer.singleShot(50, self._fit_image)
    
    def _fit_image(self):
        """适应窗口"""
        if not self._pixmap or self._pixmap.isNull():
            return
        
        canvas_w = self.canvas.width() - 40
        canvas_h = self.canvas.height() - 40
        if canvas_w <= 0 or canvas_h <= 0:
            return
        
        scale_w = canvas_w / self._pixmap.width()
        scale_h = canvas_h / self._pixmap.height()
        self._scale = min(scale_w, scale_h, 1.0)
        self._offset = QPoint(0, 0)
        self._update_canvas()
    
    def _actual_size(self):
        """原始大小"""
        self._scale = 1.0
        self._offset = QPoint(0, 0)
        self._update_canvas()
    
    def _copy_image(self):
        """复制图片"""
        if self._pixmap:
            QGuiApplication.clipboard().setPixmap(self._pixmap)
    
    def _update_canvas(self):
        """更新画布"""
        if not self._pixmap or self._pixmap.isNull():
            return
        
        scaled_w = int(self._pixmap.width() * self._scale)
        scaled_h = int(self._pixmap.height() * self._scale)
        
        scaled_pixmap = self._pixmap.scaled(
            scaled_w, scaled_h,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        self.canvas.setPixmap(scaled_pixmap)
    
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_image()
    
    def wheelEvent(self, event):
        """滚轮缩放"""
        delta = event.angleDelta().y()
        if delta > 0:
            self._scale = min(self._scale * 1.15, 10.0)
        else:
            self._scale = max(self._scale / 1.15, 0.1)
        self._update_canvas()


class ClipboardHistoryPanel(QWidget):
    """剪贴板历史面板"""
    
    COLUMNS = 5
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.cards: List[ClipboardCard] = []
        self.manager = ClipboardHistoryManager.instance()
        self._viewers: List[QWidget] = []  # 保存查看器引用，防止 GC
        self.init_ui()
        self.manager.add_listener(self._on_history_changed)
        self.manager.start_monitoring()
        self._refresh_cards()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # 滚动区域
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet("""
            QScrollArea { border: none; background-color: transparent; }
            QScrollBar:vertical {
                background: #f0f0f0;
                width: 8px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background: #c0c0c0;
                border-radius: 4px;
                min-height: 30px;
            }
            QScrollBar::handle:vertical:hover { background: #a0a0a0; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        """)
        
        self.card_container = QWidget()
        self.card_container.setObjectName("card_container")
        self.grid_layout = QGridLayout(self.card_container)
        self.grid_layout.setContentsMargins(0, 0, 8, 0)
        self.grid_layout.setSpacing(12)
        self.grid_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        
        self.scroll_area.setWidget(self.card_container)
        layout.addWidget(self.scroll_area)
        
        # 空状态
        self.empty_label = QLabel("剪贴板历史为空\n\n复制图片、文本或文件后将自动记录")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet("color: #999; font-size: 14px;")
        self.empty_label.hide()
        layout.addWidget(self.empty_label)
    
    def _on_history_changed(self):
        """历史变化回调"""
        self._refresh_cards()
    
    def _refresh_cards(self):
        """刷新卡片列表"""
        # 清理旧卡片
        for card in self.cards:
            card.deleteLater()
        self.cards.clear()
        
        while self.grid_layout.count() > 0:
            item = self.grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        items = self.manager.get_items()
        
        if not items:
            self.scroll_area.hide()
            self.empty_label.show()
            return
        
        self.scroll_area.show()
        self.empty_label.hide()
        
        for i, item in enumerate(items):
            row = i // self.COLUMNS
            col = i % self.COLUMNS
            
            card = ClipboardCard(item)
            card.clicked.connect(self._on_card_clicked)
            card.delete_requested.connect(self._on_delete_requested)
            self.grid_layout.addWidget(card, row, col)
            self.cards.append(card)
    
    def _on_card_clicked(self, item_id: str):
        """点击卡片 - 打开预览"""
        item = self.manager.get_item(item_id)
        if not item:
            return
        
        # 清理已关闭的查看器（安全检查，避免访问已删除的 C++ 对象）
        valid_viewers = []
        for v in self._viewers:
            try:
                if v.isVisible():
                    valid_viewers.append(v)
            except RuntimeError:
                pass  # C++ 对象已删除，跳过
        self._viewers = valid_viewers
        
        if item.content_type == "image":
            viewer = ClipboardImageViewer(item)
            viewer.show()
            self._viewers.append(viewer)
        else:
            dialog = ClipboardTextDetailDialog(item)
            dialog.show()
            self._viewers.append(dialog)
    
    def _on_delete_requested(self, item_id: str):
        """删除请求"""
        self.manager.delete_item(item_id)


# ============================================================
# ArchiveGalleryPanel（归档网格面板，可嵌入任意容器）
# ============================================================

class ArchiveGalleryPanel(QWidget):
    """归档网格面板 - 独立的画廊组件"""
    
    COLUMNS = 5
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.cards = []
        self.init_ui()
        self.load_records()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet("""
            QScrollArea { border: none; background-color: transparent; }
            QScrollBar:vertical {
                background: #f0f0f0;
                width: 8px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background: #c0c0c0;
                border-radius: 4px;
                min-height: 30px;
            }
            QScrollBar::handle:vertical:hover { background: #a0a0a0; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        """)
        
        self.card_container = QWidget()
        self.card_container.setObjectName("card_container")
        self.grid_layout = QGridLayout(self.card_container)
        self.grid_layout.setContentsMargins(0, 0, 8, 0)
        self.grid_layout.setSpacing(12)
        self.grid_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        
        self.scroll_area.setWidget(self.card_container)
        layout.addWidget(self.scroll_area)
        
        self.empty_label = QLabel("暂无归档记录\n\n使用截图编辑器的「归档」按钮保存记录")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet("color: #999; font-size: 14px;")
        self.empty_label.hide()
        layout.addWidget(self.empty_label)
    
    def load_records(self):
        """加载/刷新归档记录"""
        for card in self.cards:
            card.deleteLater()
        self.cards.clear()
        
        while self.grid_layout.count() > 0:
            item = self.grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        records = get_all_records()
        
        if not records:
            self.scroll_area.hide()
            self.empty_label.show()
            return
        
        self.scroll_area.show()
        self.empty_label.hide()
        
        for i, record in enumerate(records):
            row = i // self.COLUMNS
            col = i % self.COLUMNS
            
            card = ArchiveCard(record)
            card.clicked.connect(self._show_detail)
            card.delete_requested.connect(self._delete_record)
            self.grid_layout.addWidget(card, row, col)
            self.cards.append(card)
    
    def _show_detail(self, record: dict):
        dialog = ArchiveDetailDialog(record, self)
        dialog.show()
    
    def _delete_record(self, record_id: str):
        reply = QMessageBox.question(
            self, "确认删除",
            "确定要删除这条归档记录吗？\n此操作不可撤销。",
            QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Ok,
            QMessageBox.StandardButton.Cancel
        )
        
        if reply == QMessageBox.StandardButton.Ok:
            if delete_record(record_id):
                self.load_records()
            else:
                QMessageBox.warning(self, "删除失败", "无法删除该记录")
