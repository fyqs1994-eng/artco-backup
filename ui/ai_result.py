"""
AI 结果展示模块
包含 AI 分析结果的气泡窗口（支持多轮对话）、面板和图像生成结果窗口
"""

import qtawesome as qta
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QGraphicsDropShadowEffect, QFileDialog, QLineEdit,
    QScrollArea
)
from PySide6.QtCore import Qt, Signal, QTimer, QBuffer, QIODevice
from PySide6.QtGui import QColor, QPixmap, QGuiApplication

from database import add_record
from ui.theme import FONT_FAMILY_MONO


class AIImageResultWindow(QWidget):
    """AI 图像生成结果展示窗口"""
    closed = Signal()
    pin_requested = Signal(object)  # 传递 QPixmap
    
    def __init__(self, image_path: str, parent=None):
        super().__init__(parent)
        self.image_path = image_path
        self.pixmap = QPixmap(image_path)
        self._dragging = False
        self._drag_start_pos = None
        
        self._init_window()
        self._init_ui()
    
    def _init_window(self):
        """初始化窗口属性"""
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
    
    def _init_ui(self):
        """初始化 UI"""
        # 主容器
        self.container = QWidget(self)
        self.container.setObjectName("container")
        
        layout = QVBoxLayout(self.container)
        layout.setContentsMargins(16, 16, 16, 12)
        layout.setSpacing(12)
        
        # 标题栏
        title_layout = QHBoxLayout()
        title_icon = QLabel()
        title_icon.setPixmap(qta.icon('mdi6.image-auto-adjust', color='#333').pixmap(18, 18))
        title_layout.addWidget(title_icon)
        
        title_label = QLabel("AI 生成图片")
        title_label.setStyleSheet("font-weight: bold; font-size: 14px; color: #333;")
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        
        self.btn_close = QPushButton()
        self.btn_close.setIcon(qta.icon('mdi6.close', color='#999'))
        self.btn_close.setObjectName("btn_close")
        self.btn_close.setFixedSize(24, 24)
        self.btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_close.clicked.connect(self._close_window)
        title_layout.addWidget(self.btn_close)
        layout.addLayout(title_layout)
        
        # 图片显示区域
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setStyleSheet("""
            QLabel {
                background-color: #f5f5f5;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                padding: 8px;
            }
        """)
        
        # 缩放图片，最大 500x500
        max_size = 500
        scaled_pixmap = self.pixmap.scaled(
            max_size, max_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        self.image_label.setPixmap(scaled_pixmap)
        self.image_label.setFixedSize(
            scaled_pixmap.width() + 16,
            scaled_pixmap.height() + 16
        )
        layout.addWidget(self.image_label)
        
        # 图片信息
        info_label = QLabel(f"尺寸: {self.pixmap.width()} × {self.pixmap.height()}")
        info_label.setStyleSheet("color: #888; font-size: 11px;")
        info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(info_label)
        
        # 按钮区域
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        
        self.btn_save = QPushButton(" 保存")
        self.btn_save.setIcon(qta.icon('mdi6.content-save', color='#555'))
        self.btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save.clicked.connect(self._save_image)
        btn_layout.addWidget(self.btn_save)
        
        self.btn_copy = QPushButton(" 复制")
        self.btn_copy.setIcon(qta.icon('mdi6.content-copy', color='#555'))
        self.btn_copy.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_copy.clicked.connect(self._copy_image)
        btn_layout.addWidget(self.btn_copy)
        
        self.btn_pin = QPushButton(" 贴图")
        self.btn_pin.setIcon(qta.icon('mdi6.pin', color='#555'))
        self.btn_pin.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_pin.clicked.connect(self._pin_image)
        btn_layout.addWidget(self.btn_pin)
        
        layout.addLayout(btn_layout)
        
        # 样式
        self.container.setStyleSheet("""
            #container {
                background-color: white;
                border-radius: 16px;
                border: 1px solid #e0e0e0;
            }
            QPushButton {
                background-color: #f5f5f5;
                border: 1px solid #ddd;
                border-radius: 6px;
                padding: 8px 16px;
                color: #555;
                font-size: 13px;
            }
            QPushButton:hover { background-color: #e8e8e8; color: #333; }
            #btn_close { background-color: transparent; border: none; padding: 0; }
            #btn_close:hover { background-color: rgba(255,0,0,0.1); border-radius: 12px; }
        """)
        
        # 阴影效果
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(25)
        shadow.setColor(QColor(0, 0, 0, 50))
        shadow.setOffset(0, 5)
        self.container.setGraphicsEffect(shadow)
        
        # 调整窗口大小
        container_width = max(scaled_pixmap.width() + 48, 300)
        container_height = scaled_pixmap.height() + 140
        self.container.setFixedSize(container_width, container_height)
        self.setFixedSize(container_width + 40, container_height + 40)
        self.container.move(20, 20)
        
        # 居中显示
        screen = QGuiApplication.primaryScreen().geometry()
        self.move(
            (screen.width() - self.width()) // 2,
            (screen.height() - self.height()) // 2
        )
    
    def _save_image(self):
        """保存图片"""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "保存图片",
            "generated_image.png",
            "PNG 图片 (*.png);;JPEG 图片 (*.jpg);;所有文件 (*.*)"
        )
        if file_path:
            self.pixmap.save(file_path)
            self.btn_save.setIcon(qta.icon('mdi6.check', color='#4caf50'))
            self.btn_save.setText(" 已保存")
            QTimer.singleShot(2000, lambda: (
                self.btn_save.setIcon(qta.icon('mdi6.content-save', color='#555')),
                self.btn_save.setText(" 保存")
            ))
    
    def _copy_image(self):
        """复制图片到剪贴板"""
        QGuiApplication.clipboard().setPixmap(self.pixmap)
        self.btn_copy.setIcon(qta.icon('mdi6.check', color='#4caf50'))
        self.btn_copy.setText(" 已复制")
        QTimer.singleShot(2000, lambda: (
            self.btn_copy.setIcon(qta.icon('mdi6.content-copy', color='#555')),
            self.btn_copy.setText(" 复制")
        ))
    
    def _pin_image(self):
        """贴图到屏幕"""
        self.pin_requested.emit(self.pixmap)
        self._close_window()
    
    def _close_window(self):
        """关闭窗口"""
        self.closed.emit()
        self.close()
    
    def mousePressEvent(self, event):
        """鼠标按下 - 开始拖拽"""
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_start_pos = event.globalPosition().toPoint() - self.pos()
        event.accept()
    
    def mouseMoveEvent(self, event):
        """鼠标移动 - 拖拽窗口"""
        if self._dragging:
            self.move(event.globalPosition().toPoint() - self._drag_start_pos)
        event.accept()
    
    def mouseReleaseEvent(self, event):
        """鼠标释放 - 结束拖拽"""
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
        event.accept()
    
    def keyPressEvent(self, event):
        """ESC 关闭"""
        if event.key() == Qt.Key.Key_Escape:
            self._close_window()
        else:
            super().keyPressEvent(event)


class ThinkingBubble(QWidget):
    """AI 思考中占位气泡 — 三点跳动动画"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._dot_index = 0
        self._init_ui()
        
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._animate)
        self._timer.start(400)
    
    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(0)
        
        self._label = QLabel("●  ○  ○")
        self._label.setFixedHeight(32)
        self._label.setMaximumWidth(120)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setStyleSheet(f"""
            QLabel {{
                background-color: #fafafa;
                color: rgba(99, 102, 241, 0.7);
                border: none;
                border-radius: 10px;
                font-size: 13px;
                padding: 6px 16px;
                letter-spacing: 2px;
            }}
        """)
        layout.addWidget(self._label)
        layout.addStretch()
    
    def _animate(self):
        dots = ["●  ○  ○", "○  ●  ○", "○  ○  ●"]
        self._dot_index = (self._dot_index + 1) % len(dots)
        self._label.setText(dots[self._dot_index])
    
    def stop(self):
        self._timer.stop()


class ChatMessageWidget(QWidget):
    """单条聊天消息气泡 — 支持文本和 markdown 图片"""
    
    def __init__(self, role: str, text: str, parent=None):
        super().__init__(parent)
        self._role = role
        self._text = text
        self._image_labels = []  # 存储图片 QLabel 引用
        self._init_ui()
    
    def _init_ui(self):
        import re
        
        outer_layout = QHBoxLayout(self)
        outer_layout.setContentsMargins(0, 2, 0, 2)
        outer_layout.setSpacing(0)
        
        is_user = self._role == "user"
        
        if is_user:
            outer_layout.addStretch()
        
        # 内容容器（垂直排列文本和图片）
        content_widget = QWidget()
        content_widget.setMaximumWidth(320)
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(4)
        
        if is_user:
            bg_color = "rgba(99, 102, 241, 0.12)"
            text_color = "#333"
        else:
            bg_color = "#fafafa"
            text_color = "#333"
        
        # 解析 markdown 图片链接
        img_pattern = re.compile(r'!\[([^\]]*)\]\(([^)]+)\)')
        parts = img_pattern.split(self._text)
        # parts 格式：[text_before, alt1, url1, text_between, alt2, url2, ...]
        
        has_images = len(parts) > 1
        
        # 提取纯文本部分（去掉图片标记）
        plain_text = img_pattern.sub('', self._text).strip()
        
        # 显示文本部分
        if plain_text:
            label = QTextEdit()
            label.setReadOnly(True)
            label.setPlainText(plain_text)
            label.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            label.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            label.setStyleSheet(f"""
                QTextEdit {{
                    background-color: {bg_color};
                    color: {text_color};
                    border: none;
                    border-radius: 10px;
                    font-family: {FONT_FAMILY_MONO};
                    font-size: 13px;
                    padding: 8px 12px;
                }}
            """)
            label.document().setTextWidth(300)
            doc_height = label.document().size().height()
            label.setFixedHeight(max(32, int(doc_height + 20)))
            content_layout.addWidget(label)
            self._label = label
        else:
            self._label = None
        
        # 显示图片部分
        if has_images:
            # 每 3 个元素为一组：alt, url, 后续文本
            for i in range(1, len(parts), 3):
                if i + 1 < len(parts):
                    url = parts[i + 1]
                    img_label = QLabel()
                    img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    img_label.setFixedHeight(160)
                    img_label.setStyleSheet("""
                        QLabel {
                            background-color: #f0f0f0;
                            border: 1px solid #e0e0e0;
                            border-radius: 8px;
                            padding: 4px;
                            color: #999;
                            font-size: 12px;
                        }
                    """)
                    img_label.setText("图片加载中...")
                    content_layout.addWidget(img_label)
                    self._image_labels.append(img_label)
                    
                    # 异步加载图片
                    self._load_image_async(url, img_label)
        
        outer_layout.addWidget(content_widget)
        
        if not is_user:
            outer_layout.addStretch()
    
    def _load_image_async(self, url: str, label: QLabel):
        """异步下载并显示图片"""
        from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest
        from PySide6.QtCore import QUrl
        
        if not hasattr(self, '_nam'):
            self._nam = QNetworkAccessManager(self)
        
        request = QNetworkRequest(QUrl(url))
        reply = self._nam.get(request)
        reply.finished.connect(lambda: self._on_image_loaded(reply, label))
    
    def _on_image_loaded(self, reply, label: QLabel):
        """图片下载完成回调"""
        try:
            if reply.error().value != 0:
                label.setText("图片加载失败")
                return
            
            data = reply.readAll().data()
            pixmap = QPixmap()
            pixmap.loadFromData(data)
            
            if pixmap.isNull():
                label.setText("图片解析失败")
                return
            
            scaled = pixmap.scaled(
                300, 200,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            label.setPixmap(scaled)
            label.setFixedHeight(scaled.height() + 8)
        except Exception:
            label.setText("图片加载失败")
        finally:
            reply.deleteLater()
    
    def get_text(self) -> str:
        return self._text


class AIResultBubble(QWidget):
    """AI 结果气泡窗口 - 支持多轮对话"""
    closed = Signal()
    pin_image_requested = Signal(QPixmap)  # 请求贴图
    followup_requested = Signal(str)  # 追问信号（传递用户输入的文本）
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        
        self.full_text = ""
        self._image_data = None
        self._is_archived = False
        self._current_pixmap = None
        self._is_ai_generated = False
        self._is_chat_mode = False  # 是否已进入多轮对话模式
        self._is_loading = False  # 是否正在等待 AI 回复
        self._thinking_bubble = None  # 思考中占位气泡
        self._chat_messages = []  # 完整聊天记录 [{"role": ..., "text": ...}, ...]
        
        # 拖动状态
        self._dragging = False
        self._drag_start_pos = None
        
        self.init_ui()
    
    def init_ui(self):
        self.container = QWidget(self)
        self.container.setObjectName("bubble_container")
        
        layout = QVBoxLayout(self.container)
        layout.setContentsMargins(16, 16, 16, 12)
        layout.setSpacing(8)
        
        # 标题栏
        title_layout = QHBoxLayout()
        self.title_icon = QLabel()
        self.title_icon.setPixmap(qta.icon('mdi6.auto-fix', color='#333').pixmap(16, 16))
        title_layout.addWidget(self.title_icon)
        self.title_label = QLabel("AI 分析结果")
        self.title_label.setStyleSheet("font-weight: bold; font-size: 14px; color: #333;")
        title_layout.addWidget(self.title_label)
        title_layout.addStretch()
        
        self.btn_close = QPushButton()
        self.btn_close.setIcon(qta.icon('mdi6.close', color='#999'))
        self.btn_close.setObjectName("btn_bubble_close")
        self.btn_close.setFixedSize(24, 24)
        self.btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_close.clicked.connect(self._close_bubble)
        title_layout.addWidget(self.btn_close)
        layout.addLayout(title_layout)
        
        # ── 消息滚动区域（多轮对话模式使用）──
        self.chat_scroll = QScrollArea()
        self.chat_scroll.setWidgetResizable(True)
        self.chat_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.chat_scroll.setObjectName("chat_scroll")
        
        self.chat_container = QWidget()
        self.chat_layout = QVBoxLayout(self.chat_container)
        self.chat_layout.setContentsMargins(0, 0, 0, 0)
        self.chat_layout.setSpacing(4)
        self.chat_layout.addStretch()
        
        self.chat_scroll.setWidget(self.chat_container)
        self.chat_scroll.hide()
        layout.addWidget(self.chat_scroll, 1)
        
        # ── 单轮模式：文本区域 ──
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setStyleSheet(f"""
            QTextEdit {{
                background-color: #fafafa;
                color: #333;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                font-family: {FONT_FAMILY_MONO};
                font-size: 13px;
                padding: 8px;
            }}
        """)
        self.text_edit.setMinimumHeight(180)
        layout.addWidget(self.text_edit)
        
        # 图片显示区域
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setStyleSheet("""
            QLabel {
                background-color: #fafafa;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                padding: 8px;
            }
        """)
        self.image_label.setMinimumHeight(200)
        self.image_label.hide()
        layout.addWidget(self.image_label)
        
        # ── 追问输入区域 ──
        self.input_container = QWidget()
        self.input_container.setObjectName("input_container")
        input_layout = QHBoxLayout(self.input_container)
        input_layout.setContentsMargins(0, 0, 0, 0)
        input_layout.setSpacing(6)
        
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("追问...")
        self.input_field.setObjectName("chat_input")
        self.input_field.returnPressed.connect(self._on_send_followup)
        self.input_field.textChanged.connect(self._update_enter_hint)
        input_layout.addWidget(self.input_field, 1)
        
        # Enter 键提示标签
        self._enter_hint = QLabel("Enter 键发送", self.input_field)
        self._enter_hint.setStyleSheet("color: rgba(0, 0, 0, 0.25); font-size: 11px; background: transparent;")
        self._enter_hint.hide()
        
        self.btn_send = QPushButton()
        self.btn_send.setIcon(qta.icon('mdi6.send', color='#fff'))
        self.btn_send.setObjectName("btn_send")
        self.btn_send.setFixedSize(32, 32)
        self.btn_send.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_send.setToolTip("发送 (Enter)")
        self.btn_send.clicked.connect(self._on_send_followup)
        input_layout.addWidget(self.btn_send)
        
        layout.addWidget(self.input_container)
        
        # ── 按钮区域 ──
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self.btn_copy = QPushButton(" 复制内容")
        self.btn_copy.setIcon(qta.icon('mdi6.content-copy', color='#555'))
        self.btn_copy.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_copy.clicked.connect(self._copy_content)
        btn_layout.addWidget(self.btn_copy)
        
        self.btn_pin = QPushButton(" 贴到屏幕")
        self.btn_pin.setIcon(qta.icon('mdi6.pin', color='#555'))
        self.btn_pin.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_pin.clicked.connect(self._pin_image)
        self.btn_pin.hide()
        btn_layout.addWidget(self.btn_pin)
        
        self.btn_archive = QPushButton(" 归档")
        self.btn_archive.setIcon(qta.icon('mdi6.inbox', color='#555'))
        self.btn_archive.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_archive.clicked.connect(self._archive_record)
        btn_layout.addWidget(self.btn_archive)
        
        layout.addLayout(btn_layout)
        
        self.container.setStyleSheet("""
            #bubble_container {
                background-color: white;
                border-radius: 16px;
                border: 1px solid #e0e0e0;
            }
            QPushButton {
                background-color: #f5f5f5;
                border: 1px solid #ddd;
                border-radius: 6px;
                padding: 8px 16px;
                color: #555;
                font-size: 13px;
            }
            QPushButton:hover { background-color: #e8e8e8; color: #333; }
            #btn_bubble_close { background-color: transparent; border: none; padding: 0; }
            #btn_bubble_close:hover { background-color: rgba(255,0,0,0.1); border-radius: 12px; }
            QScrollArea#chat_scroll {
                border: none;
                background-color: transparent;
            }
            QScrollArea#chat_scroll > QWidget > QWidget {
                background-color: transparent;
            }
            QScrollBar:vertical {
                background: transparent;
                width: 5px;
                margin: 2px;
            }
            QScrollBar::handle:vertical {
                background: rgba(0, 0, 0, 0.15);
                border-radius: 2px;
                min-height: 20px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
            QWidget#input_container {
                background-color: transparent;
            }
            QLineEdit#chat_input {
                background-color: #f5f5f5;
                border: 1px solid #e0e0e0;
                border-radius: 16px;
                padding: 6px 14px;
                font-size: 13px;
                color: #333;
            }
            QLineEdit#chat_input:focus {
                border: 1px solid rgba(99, 102, 241, 0.5);
                background-color: #fff;
            }
            QPushButton#btn_send {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(99, 102, 241, 0.9),
                    stop:1 rgba(139, 92, 246, 0.9));
                border: none;
                border-radius: 16px;
                padding: 0;
            }
            QPushButton#btn_send:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(79, 82, 221, 0.95),
                    stop:1 rgba(119, 72, 226, 0.95));
            }
            QPushButton#btn_send:disabled {
                background: #ccc;
            }
        """)
        
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(25)
        shadow.setColor(QColor(0, 0, 0, 50))
        shadow.setOffset(0, 5)
        self.container.setGraphicsEffect(shadow)
        
        # 初始尺寸（比原来稍高，容纳输入框）
        self.container.setFixedSize(400, 380)
        self.setFixedSize(440, 420)
        self.container.move(20, 20)
    
    def _switch_to_chat_mode(self):
        """首次追问时切换到聊天列表模式"""
        if self._is_chat_mode:
            return
        self._is_chat_mode = True
        
        self.text_edit.hide()
        self.image_label.hide()
        self.chat_scroll.show()
        
        # 如果是图片模式，先添加图片缩略图到聊天列表
        if self._current_pixmap and not self._current_pixmap.isNull():
            self._add_image_to_chat(self._current_pixmap)
            self._chat_messages.append({"role": "assistant", "text": "[AI 生成图片]"})
        
        # 将当前文本结果移入聊天列表（图片模式下 full_text 可能为空）
        if self.full_text:
            self._add_chat_message("assistant", self.full_text)
        
        # 扩大气泡尺寸以容纳对话
        self.container.setFixedSize(420, 480)
        self.setFixedSize(460, 520)
        
        self.title_label.setText("AI 对话")
    
    def _add_chat_message(self, role: str, text: str):
        """添加一条聊天消息到列表"""
        # 记录到聊天历史
        self._chat_messages.append({"role": role, "text": text})
        
        msg = ChatMessageWidget(role, text)
        # 在 stretch 之前插入
        insert_pos = self.chat_layout.count() - 1
        self.chat_layout.insertWidget(insert_pos, msg)
        
        # 滚动到底部
        QTimer.singleShot(50, lambda: self.chat_scroll.verticalScrollBar().setValue(
            self.chat_scroll.verticalScrollBar().maximum()
        ))
    
    def _add_image_to_chat(self, pixmap: QPixmap):
        """将图片缩略图添加到聊天列表"""
        wrapper = QWidget()
        wrapper_layout = QHBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(0, 4, 0, 4)
        wrapper_layout.setSpacing(0)
        
        img_label = QLabel()
        scaled = pixmap.scaled(
            200, 150,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        img_label.setPixmap(scaled)
        img_label.setStyleSheet("""
            QLabel {
                background-color: #f5f5f5;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                padding: 4px;
            }
        """)
        wrapper_layout.addWidget(img_label)
        wrapper_layout.addStretch()
        
        insert_pos = self.chat_layout.count() - 1
        self.chat_layout.insertWidget(insert_pos, wrapper)
    
    def _update_enter_hint(self, text: str):
        """输入框有文字时显示 Enter 键发送提示"""
        if text.strip() and not self._is_loading:
            self._enter_hint.adjustSize()
            x = self.input_field.width() - self._enter_hint.width() - 4
            y = (self.input_field.height() - self._enter_hint.height()) // 2
            self._enter_hint.move(x, y)
            self._enter_hint.show()
        else:
            self._enter_hint.hide()
    
    def _on_send_followup(self):
        """发送追问"""
        text = self.input_field.text().strip()
        if not text or self._is_loading:
            return
        
        # 首次追问时切换到聊天模式
        self._switch_to_chat_mode()
        
        # 添加用户消息到列表
        self._add_chat_message("user", text)
        self.input_field.clear()
        
        # 显示加载状态
        self._is_loading = True
        self.btn_send.setEnabled(False)
        self.input_field.setPlaceholderText("AI 思考中...")
        self.input_field.setReadOnly(True)
        
        # 添加思考中占位气泡
        self._show_thinking_bubble()
        
        # 发送追问信号给 CapsuleWidget
        self.followup_requested.emit(text)
    
    def _show_thinking_bubble(self):
        """在聊天列表中添加思考中占位气泡"""
        self._remove_thinking_bubble()
        self._thinking_bubble = ThinkingBubble()
        insert_pos = self.chat_layout.count() - 1
        self.chat_layout.insertWidget(insert_pos, self._thinking_bubble)
        QTimer.singleShot(50, lambda: self.chat_scroll.verticalScrollBar().setValue(
            self.chat_scroll.verticalScrollBar().maximum()
        ))
    
    def _remove_thinking_bubble(self):
        """移除思考中占位气泡"""
        if self._thinking_bubble:
            self._thinking_bubble.stop()
            self._thinking_bubble.setParent(None)
            self._thinking_bubble.deleteLater()
            self._thinking_bubble = None
    
    def append_ai_reply(self, text: str):
        """追加 AI 回复到聊天列表（由外部调用）"""
        self._remove_thinking_bubble()
        self.full_text = text
        self._is_loading = False
        self.btn_send.setEnabled(True)
        self.input_field.setPlaceholderText("追问...")
        self.input_field.setReadOnly(False)
        self.input_field.setFocus()
        
        self._add_chat_message("assistant", text)
    
    def on_abort(self):
        """AI 处理被用户终止时恢复输入状态"""
        self._remove_thinking_bubble()
        self._is_loading = False
        self.btn_send.setEnabled(True)
        self.input_field.setPlaceholderText("追问...")
        self.input_field.setReadOnly(False)
        if self._is_chat_mode:
            self._add_chat_message("assistant", "⏹ 已终止")
    
    def append_ai_image(self, image_path: str):
        """追加 AI 生成的图片到聊天列表（由外部调用）"""
        self._remove_thinking_bubble()
        self._is_loading = False
        self.btn_send.setEnabled(True)
        self.input_field.setPlaceholderText("继续描述修改需求...")
        self.input_field.setReadOnly(False)
        self.input_field.setFocus()
        
        pixmap = QPixmap(image_path)
        if not pixmap.isNull():
            self._current_pixmap = pixmap
            self._add_image_to_chat(pixmap)
            # 记录到聊天历史
            self._chat_messages.append({"role": "assistant", "text": "[AI 生成图片]"})
            # 滚动到底部
            QTimer.singleShot(50, lambda: self.chat_scroll.verticalScrollBar().setValue(
                self.chat_scroll.verticalScrollBar().maximum()
            ))
        else:
            self._add_chat_message("assistant", "⚠ 图片生成失败")
    
    def show_followup_error(self, error_msg: str):
        """显示追问错误"""
        self._remove_thinking_bubble()
        self._is_loading = False
        self.btn_send.setEnabled(True)
        self.input_field.setPlaceholderText("追问...")
        self.input_field.setReadOnly(False)
        self.input_field.setFocus()
        
        self._add_chat_message("assistant", f"⚠ {error_msg}")
    
    def show_result(self, text: str):
        """显示文本结果"""
        self.full_text = text
        self._current_pixmap = None
        self._is_ai_generated = False
        self.title_icon.setPixmap(qta.icon('mdi6.auto-fix', color='#333').pixmap(16, 16))
        self.title_label.setText("AI 分析结果")
        self.text_edit.setPlainText(text)
        self.text_edit.show()
        self.chat_scroll.hide()
        self.image_label.hide()
        self.btn_copy.show()
        self.btn_pin.hide()
        self.input_container.show()
        self.show()
    
    def show_image(self, image_path: str):
        """显示图片结果"""
        self._current_pixmap = QPixmap(image_path)
        if self._current_pixmap.isNull():
            self.show_error("图片加载失败")
            return
        
        self._is_ai_generated = True
        self.title_icon.setPixmap(qta.icon('mdi6.image', color='#333').pixmap(16, 16))
        self.title_label.setText("AI 生成图片")
        
        # 缩放图片以适应气泡
        scaled = self._current_pixmap.scaled(
            360, 200, 
            Qt.AspectRatioMode.KeepAspectRatio, 
            Qt.TransformationMode.SmoothTransformation
        )
        self.image_label.setPixmap(scaled)
        
        self.text_edit.hide()
        self.chat_scroll.hide()
        self.image_label.show()
        self.btn_copy.hide()
        self.btn_pin.show()
        self.input_container.show()
        self.show()
    
    def show_error(self, error_msg: str):
        self.full_text = error_msg
        self._current_pixmap = None
        self.text_edit.setPlainText(error_msg)
        self.text_edit.show()
        self.chat_scroll.hide()
        self.image_label.hide()
        self.btn_copy.show()
        self.btn_pin.hide()
        self.input_container.hide()
        self.show()
    
    def _copy_content(self):
        QGuiApplication.clipboard().setText(self.full_text)
        self.btn_copy.setIcon(qta.icon('mdi6.check', color='#4caf50'))
        self.btn_copy.setText(" 已复制")
        QTimer.singleShot(2000, self._reset_copy_btn)
    
    def _reset_copy_btn(self):
        self.btn_copy.setIcon(qta.icon('mdi6.content-copy', color='#555'))
        self.btn_copy.setText(" 复制内容")
    
    def _pin_image(self):
        """贴图按钮点击"""
        if self._current_pixmap:
            self.pin_image_requested.emit(self._current_pixmap)
    
    def set_image_data(self, image_data: bytes):
        self._image_data = image_data
    
    def _get_full_chat_text(self) -> str:
        """获取完整的聊天记录文本"""
        if not self._chat_messages:
            return self.full_text
        
        lines = []
        for msg in self._chat_messages:
            prefix = "🧑 用户" if msg["role"] == "user" else "🤖 AI"
            lines.append(f"{prefix}：{msg['text']}")
        return "\n\n".join(lines)
    
    def _archive_record(self):
        if self._is_archived:
            return
        
        # 如果是图片模式，保存生成的图片
        if self._current_pixmap and not self._image_data:
            buffer = QBuffer()
            buffer.open(QIODevice.OpenModeFlag.WriteOnly)
            self._current_pixmap.save(buffer, "PNG")
            self._image_data = buffer.data().data()
            buffer.close()
        
        if not self._image_data:
            self.btn_archive.setIcon(qta.icon('mdi6.alert', color='#ff9800'))
            self.btn_archive.setText(" 无图片")
            return
        
        try:
            # 如果是AI生成的图片，添加标签
            tags = "ai_generated" if self._is_ai_generated else ""
            archive_text = self._get_full_chat_text()
            add_record(self._image_data, archive_text, tags)
            
            self._is_archived = True
            self.btn_archive.setIcon(qta.icon('mdi6.check', color='#4caf50'))
            self.btn_archive.setText(" 已归档")
            self.btn_archive.setEnabled(False)
            self.btn_archive.setStyleSheet("""
                QPushButton {
                    background-color: #e8f5e9;
                    border: 1px solid #4caf50;
                    border-radius: 6px;
                    padding: 8px 16px;
                    color: #4caf50;
                    font-size: 13px;
                }
            """)
        except Exception:
            self.btn_archive.setIcon(qta.icon('mdi6.close', color='#f44336'))
            self.btn_archive.setText(" 失败")
    
    def _close_bubble(self):
        self.closed.emit()
        self.close()
    
    def mousePressEvent(self, event):
        """鼠标按下 - 开始拖动"""
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_start_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        """鼠标移动 - 拖动窗口"""
        if self._dragging and self._drag_start_pos:
            self.move(event.globalPosition().toPoint() - self._drag_start_pos)
        super().mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event):
        """鼠标释放 - 结束拖动"""
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            self._drag_start_pos = None
        super().mouseReleaseEvent(event)


class AIResultPanel(QWidget):
    """AI 结果面板（用于编辑器）- 支持文本和图片，可拖拽和关闭"""
    pin_image_requested = Signal(QPixmap)  # 请求贴图
    
    def __init__(self, parent):
        super().__init__(parent)
        self._drag_pos = None
        self.init_ui()
        self.full_text = ""
        self.current_pixmap = None

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # 标题栏（可拖拽 + 关闭按钮）
        title_bar = QWidget()
        title_bar.setFixedHeight(28)
        title_bar.setStyleSheet("""
            QWidget {
                background-color: rgba(40, 40, 40, 220);
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
            }
        """)
        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(10, 4, 4, 4)
        title_layout.setSpacing(0)
        
        self.title_label = QLabel("AI 结果")
        self.title_label.setStyleSheet("color: #aaa; font-size: 12px;")
        title_layout.addWidget(self.title_label)
        title_layout.addStretch()
        
        btn_close = QPushButton("×")
        btn_close.setFixedSize(20, 20)
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.clicked.connect(self.hide)
        btn_close.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #888;
                border: none;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton:hover { color: #ff5555; background-color: rgba(255,255,255,0.1); border-radius: 10px; }
        """)
        title_layout.addWidget(btn_close)
        layout.addWidget(title_bar)
        
        # 内容区域
        content = QWidget()
        content.setStyleSheet("""
            QWidget {
                background-color: rgba(0, 0, 0, 180);
                border-bottom-left-radius: 8px;
                border-bottom-right-radius: 8px;
            }
        """)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(10, 10, 10, 10)
        
        # 文本结果区域
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setStyleSheet(f"""
            QTextEdit {{
                background-color: transparent;
                color: white;
                border: none;
                font-family: {FONT_FAMILY_MONO};
                font-size: 14px;
            }}
        """)
        content_layout.addWidget(self.text_edit)
        
        # 图片显示区域
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setStyleSheet("QLabel { background-color: transparent; }")
        self.image_label.hide()
        content_layout.addWidget(self.image_label)
        
        # 按钮区域
        self.btn_layout = QHBoxLayout()
        
        self.btn_copy = QPushButton("复制结果")
        self.btn_copy.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_copy.clicked.connect(self.copy_content)
        self.btn_copy.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 0.2);
                color: white;
                border: 1px solid rgba(255, 255, 255, 0.3);
                border-radius: 4px;
                padding: 5px;
            }
            QPushButton:hover { background-color: rgba(255, 255, 255, 0.3); }
        """)
        self.btn_layout.addWidget(self.btn_copy)
        
        self.btn_pin = QPushButton("贴到屏幕")
        self.btn_pin.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_pin.clicked.connect(self._on_pin_clicked)
        self.btn_pin.setStyleSheet("""
            QPushButton {
                background-color: rgba(76, 175, 80, 0.6);
                color: white;
                border: 1px solid rgba(76, 175, 80, 0.8);
                border-radius: 4px;
                padding: 5px;
            }
            QPushButton:hover { background-color: rgba(76, 175, 80, 0.8); }
        """)
        self.btn_pin.hide()
        self.btn_layout.addWidget(self.btn_pin)
        
        content_layout.addLayout(self.btn_layout)
        layout.addWidget(content)

        self.setFixedSize(350, 450)
        self.hide()
    
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and event.pos().y() < 28:
            self._drag_pos = event.pos()
    
    def mouseMoveEvent(self, event):
        if self._drag_pos is not None:
            new_pos = self.mapToParent(event.pos() - self._drag_pos)
            # 限制在父窗口范围内
            parent = self.parent()
            if parent:
                new_pos.setX(max(0, min(new_pos.x(), parent.width() - self.width())))
                new_pos.setY(max(0, min(new_pos.y(), parent.height() - self.height())))
            self.move(new_pos)
    
    def mouseReleaseEvent(self, event):
        self._drag_pos = None

    def show_result(self, text):
        """显示文本结果"""
        self.full_text = text
        self.current_pixmap = None
        self.text_edit.setPlainText(text)
        self.text_edit.show()
        self.image_label.hide()
        self.btn_copy.show()
        self.btn_pin.hide()
        self.show()
    
    def show_image(self, image_path: str):
        """显示图片结果"""
        self.current_pixmap = QPixmap(image_path)
        if self.current_pixmap.isNull():
            self.show_result("图片加载失败")
            return
        
        # 缩放图片以适应面板
        scaled = self.current_pixmap.scaled(
            330, 380, 
            Qt.AspectRatioMode.KeepAspectRatio, 
            Qt.TransformationMode.SmoothTransformation
        )
        self.image_label.setPixmap(scaled)
        
        self.text_edit.hide()
        self.image_label.show()
        self.btn_copy.hide()
        self.btn_pin.show()
        self.show()
    
    def _on_pin_clicked(self):
        """贴图按钮点击"""
        if self.current_pixmap:
            self.pin_image_requested.emit(self.current_pixmap)

    def copy_content(self):
        QGuiApplication.clipboard().setText(self.full_text)
        self.btn_copy.setText("已复制！")
        QTimer.singleShot(2000, lambda: self.btn_copy.setText("复制结果"))
