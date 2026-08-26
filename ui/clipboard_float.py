"""
剪贴板悬浮拖放面板
鼠标侧键触发，在鼠标位置显示剪贴板历史网格
支持单击粘贴或拖拽到目标应用
"""

import os
import tempfile
import time
from typing import Optional

from PySide6.QtCore import (
    Qt, Signal, QTimer, QPoint, QSize, QPropertyAnimation,
    QEasingCurve, QMimeData, QUrl
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea,
    QFrame, QApplication, QGridLayout
)
from PySide6.QtGui import QCursor, QPixmap, QDrag

from ui.theme import (
    BG_ELEVATED, BORDER_DEFAULT, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_TERTIARY,
    ACCENT_PRIMARY, ACCENT_SUBTLE, COLOR_ERROR, RADIUS_SM, RADIUS_MD, RADIUS_LG,
    FONT_FAMILY, FONT_SIZE_SM, FONT_SIZE_MD, get_scrollbar_style
)
from ui.archive import ClipboardHistoryManager, ClipboardItem, _is_probably_image_file


class ClipboardFloatCard(QFrame):
    """剪贴板历史卡片（画廊式）"""
    clicked = Signal(object)  # ClipboardItem
    drag_started = Signal(object)  # ClipboardItem
    
    def __init__(self, item: ClipboardItem, parent=None):
        super().__init__(parent)
        self.item = item
        self._drag_start_pos = None
        self._is_dragging = False
        self._temp_file_path = None
        self._cached_thumb = None  # 预缓存的缩略图（image/file 类型图片用，拖拽时避免全图编码）
        self._thumb_cached = False  # 标记是否已尝试缓存
        self.init_ui()
    
    def _ensure_thumb_cached(self):
        """延迟生成缩略图缓存（仅首次调用时执行，避免卡片重建时批量解码大图导致卡顿）"""
        if self._thumb_cached:
            return
        self._thumb_cached = True
        if self.item.content_type == "image":
            pm = self.item.content
            if pm and not pm.isNull():
                self._cached_thumb = pm.scaled(
                    200, 200,
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation
                )
        elif self.item.content_type == "file":
            paths = self.item.file_paths()
            if len(paths) == 1 and _is_probably_image_file(paths[0]):
                self._cached_thumb = self.item.try_get_thumbnail(200, 200)

    def _is_file_image(self) -> bool:
        """判断 file 类型是否为单个图片文件"""
        if self.item.content_type != "file":
            return False
        paths = self.item.file_paths()
        return len(paths) == 1 and _is_probably_image_file(paths[0])

    def _load_thumb_async(self, label: QLabel):
        """异步加载缩略图并更新到 QLabel（事件循环空闲时调用，不阻塞 UI）"""
        self._ensure_thumb_cached()
        if self._cached_thumb is not None and not self._cached_thumb.isNull():
            scaled = self._cached_thumb.scaled(
                88, 88,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation
            )
            if scaled.width() > 88 or scaled.height() > 88:
                x = (scaled.width() - 88) // 2
                y = (scaled.height() - 88) // 2
                scaled = scaled.copy(x, y, 88, 88)
            label.setPixmap(scaled)
    
    def init_ui(self):
        # 正方形卡片
        self.setFixedSize(96, 96)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setObjectName("float_card")
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(0)
        
        if self.item.content_type == "image":
            # 图片缩略图
            thumb_label = QLabel()
            thumb_label.setFixedSize(88, 88)
            thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            thumb_label.setObjectName("thumb_image")
            
            if self.item.content and not self.item.content.isNull():
                scaled = self.item.content.scaled(
                    88, 88,
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation
                )
                if scaled.width() > 88 or scaled.height() > 88:
                    x = (scaled.width() - 88) // 2
                    y = (scaled.height() - 88) // 2
                    scaled = scaled.copy(x, y, 88, 88)
                thumb_label.setPixmap(scaled)
            
            layout.addWidget(thumb_label)
        elif self.item.content_type == "file" and self._is_file_image():
            # file 类型图片（大图）：异步加载缩略图，避免复制瞬间同步解码大文件卡顿
            thumb_label = QLabel()
            thumb_label.setFixedSize(88, 88)
            thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            thumb_label.setObjectName("thumb_image")
            layout.addWidget(thumb_label)
            # 延迟到事件循环空闲时加载缩略图（不阻塞复制流程）
            QTimer.singleShot(0, lambda: self._load_thumb_async(thumb_label))
        else:
            # 文本 / 非图片文件（显示文件名或「N 个文件」）
            text_label = QLabel()
            text_label.setFixedSize(88, 88)
            text_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
            text_label.setWordWrap(True)
            text_label.setObjectName("text_preview")
            preview = self.item.get_preview_text(60)
            text_label.setText(preview)
            layout.addWidget(text_label)
        
        # 样式
        self.setStyleSheet(self._get_style())
    
    def _get_style(self) -> str:
        return f"""
            QFrame#float_card {{
                background: {BG_ELEVATED};
                border: 1px solid {BORDER_DEFAULT};
                border-radius: {RADIUS_MD}px;
            }}
            QFrame#float_card:hover {{
                border: 2px solid {ACCENT_PRIMARY};
                background: {ACCENT_SUBTLE};
            }}
            QLabel#thumb_image {{
                border-radius: {RADIUS_SM}px;
                background: #f0f0f0;
            }}
            QLabel#text_preview {{
                color: {TEXT_PRIMARY};
                font-size: 11px;
                font-family: {FONT_FAMILY};
                padding: 4px;
                background: transparent;
            }}
        """
    
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = event.pos()
            self._is_dragging = False
        super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        if not self._drag_start_pos:
            return super().mouseMoveEvent(event)
        
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return super().mouseMoveEvent(event)
        
        # 检查拖拽阈值
        if (event.pos() - self._drag_start_pos).manhattanLength() < 10:
            return super().mouseMoveEvent(event)
        
        # 开始拖拽
        self._is_dragging = True
        self._start_drag()
        self._drag_start_pos = None
    
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._drag_start_pos and not self._is_dragging:
            # 点击（非拖拽）
            self.clicked.emit(self.item)
        self._drag_start_pos = None
        self._is_dragging = False
        super().mouseReleaseEvent(event)
    
    def _start_drag(self):
        """启动拖拽操作"""
        self._ensure_thumb_cached()  # 确保缩略图已缓存（延迟加载）
        drag = QDrag(self)
        mime_data = QMimeData()
        # 判断文件来源路径（image 类型有 source_file_path，file 类型大图取 file_paths[0]）
        source_path = self.item.source_file_path if self.item.content_type == "image" else None
        if not source_path and self.item.content_type == "file":
            paths = self.item.file_paths()
            if len(paths) == 1:
                source_path = paths[0]

        if source_path and os.path.isfile(source_path):
            # 文件来源图片：URL + image MIME 双保险
            # image 类型：pixmap 已在内存，直接用全图
            # file 类型（大图）：用预缓存的缩略图，跳过 image MIME 编码，只设 URL + 预览
            file_url = QUrl.fromLocalFile(source_path)
            mime_data.setUrls([file_url])
            mime_data.setData("text/uri-list", file_url.toString().encode("utf-8"))

            if self.item.content_type == "image":
                # image 类型：用预缓存缩略图做 MIME 编码（避免全图编码卡顿）
                # 目标应用通过 file:// URL 读取原始画质文件
                thumb = self._cached_thumb
                if thumb is not None and not thumb.isNull():
                    from PySide6.QtCore import QBuffer, QIODevice
                    has_alpha = thumb.hasAlphaChannel()
                    img_fmt = "PNG" if has_alpha else "JPEG"
                    img_mime = "image/png" if has_alpha else "image/jpeg"
                    buf = QBuffer()
                    buf.open(QIODevice.OpenModeFlag.WriteOnly)
                    if thumb.save(buf, img_fmt, 85 if img_fmt == "JPEG" else -1):
                        mime_data.setData(img_mime, buf.data().data())
                    buf.close()

                    ps = min(80, thumb.width(), thumb.height())
                    scaled = thumb.scaled(
                        ps, ps,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.FastTransformation
                    )
                    drag.setPixmap(scaled)
                    drag.setHotSpot(QPoint(scaled.width() // 2, scaled.height() // 2))
            else:
                # file 类型大图：直接用缓存缩略图做拖拽预览，不编码 image MIME
                # 目标应用通过 file:// URL 读取原始文件，无需内嵌图片字节
                thumb = self._cached_thumb
                if thumb is not None and not thumb.isNull():
                    ps = min(80, thumb.width(), thumb.height())
                    scaled = thumb.scaled(
                        ps, ps,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.FastTransformation
                    )
                    drag.setPixmap(scaled)
                    drag.setHotSpot(QPoint(scaled.width() // 2, scaled.height() // 2))

            drag.setMimeData(mime_data)
            drag.exec(Qt.DropAction.CopyAction)
            return
        
        pixmap = None
        if self.item.content_type == "image":
            p = self.item.content
            pixmap = p if p and not p.isNull() else None
        else:
            pixmap = self.item.try_get_pixmap()
        
        if pixmap is not None and not pixmap.isNull():
            width, height = pixmap.width(), pixmap.height()
            
            # 1. 总是设置图片数据（Qt标准格式）
            mime_data.setImageData(pixmap.toImage())
            
            # 2. 显式设置 MIME 类型数据（浏览器需要特定的 image/png 或 image/jpeg 格式）
            # 将图片转换为 bytes 并设置对应的 MIME 类型
            from PySide6.QtCore import QBuffer, QIODevice
            
            # 选择格式：有透明通道用 PNG，否则用 JPEG
            has_alpha = pixmap.hasAlphaChannel()
            format = "PNG" if has_alpha else "JPEG"
            mime_type = "image/png" if has_alpha else "image/jpeg"
            
            # 将 pixmap 转换为 bytes
            buffer = QBuffer()
            buffer.open(QIODevice.OpenModeFlag.WriteOnly)
            quality = 85  # JPEG 质量
            success = pixmap.save(buffer, format, quality if format == "JPEG" else -1)
            
            if success:
                image_data = buffer.data().data()
                mime_data.setData(mime_type, image_data)
                
                # 3. 总是生成临时文件（浏览器上传需要文件路径）
                # 检查图片大小，大图可能优化
                estimated_size = width * height * 4
                max_size_for_temp = 20 * 1024 * 1024  # 20MB 阈值，提高以避免卡顿
                
                if estimated_size < max_size_for_temp:
                    # 正常保存
                    temp_path = self._save_temp_image(pixmap)
                else:
                    # 大图：调整大小再保存（避免卡顿）
                    # 保持宽高比，最大尺寸 2000px
                    max_dimension = 2000
                    if max(width, height) > max_dimension:
                        ratio = max_dimension / max(width, height)
                        new_width = int(width * ratio)
                        new_height = int(height * ratio)
                        optimized = pixmap.scaled(
                            new_width, new_height,
                            Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation
                        )
                        temp_path = self._save_temp_image(optimized)
                    else:
                        temp_path = self._save_temp_image(pixmap)
                
                if temp_path:
                    # 设置文件 URL（标准方式）
                    file_url = QUrl.fromLocalFile(temp_path)
                    mime_data.setUrls([file_url])
                    
                    # 显式设置 text/uri-list 格式（某些浏览器需要）
                    # text/uri-list 应该是换行符分隔的 URL 列表
                    uri_list = file_url.toString()
                    mime_data.setData("text/uri-list", uri_list.encode('utf-8'))
                    
                    # 设置浏览器特定的 MIME 类型（存 URL 而非裸路径，避免解析混乱）
                    mime_data.setData("application/x-moz-file", file_url.toString().encode('utf-8'))
                    
                    # 注意：不设置 application/octet-stream
                    # 某些 Electron 应用会优先读取该格式，把图片当未知二进制流处理导致解码失败
            
            # 设置拖拽预览（缩放小图，避免卡顿）
            preview_size = min(80, pixmap.width(), pixmap.height())
            scaled = pixmap.scaled(
                preview_size, preview_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.FastTransformation  # 快速缩放
            )
            drag.setPixmap(scaled)
            drag.setHotSpot(QPoint(scaled.width() // 2, scaled.height() // 2))
            
        elif self.item.content_type == "file":
            paths = self.item.file_paths()
            if paths:
                mime_data.setUrls([QUrl.fromLocalFile(p) for p in paths])
        else:
            text = self.item.content
            if text:
                mime_data.setText(text)
        
        drag.setMimeData(mime_data)
        drag.exec(Qt.DropAction.CopyAction)
        # 拖拽完成后延迟清理临时文件（给应用异步上传留足时间）
        # 30 秒，确保企微等 Electron 应用排队上传时文件仍可用
        self.cleanup(delay_ms=30000)
    
    def _save_temp_image(self, pixmap: QPixmap) -> Optional[str]:
        """保存图片到临时文件（用于拖拽到某些应用）"""
        try:
            temp_dir = os.path.join(tempfile.gettempdir(), "artco_drag")
            os.makedirs(temp_dir, exist_ok=True)
            
            timestamp = int(time.time() * 1000)
            # 使用 PNG 格式，兼容性更好（浏览器支持 PNG/JPEG，不支持 BMP）
            # 根据图片特性选择格式：有透明通道用 PNG，否则用 JPEG
            has_alpha = pixmap.hasAlphaChannel()
            format = "PNG" if has_alpha else "JPEG"
            ext = ".png" if has_alpha else ".jpg"
            temp_path = os.path.join(temp_dir, f"clip_{timestamp}{ext}")
            
            # 保存图片
            quality = 85  # JPEG 质量
            if pixmap.save(temp_path, format, quality if format == "JPEG" else -1):
                self._temp_file_path = temp_path
                return temp_path
        except Exception:
            pass
        return None
    
    def cleanup(self, delay_ms: int = 0):
        """清理临时文件
        
        Args:
            delay_ms: 延迟毫秒数，0表示立即清理
        """
        if not self._temp_file_path:
            return
            
        temp_path = self._temp_file_path
        self._temp_file_path = None  # 防止重复清理
        
        def remove_file():
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass
        
        if delay_ms <= 0:
            remove_file()
        else:
            QTimer.singleShot(delay_ms, remove_file)


class ClipboardFloatPanel(QWidget):
    """剪贴板悬浮面板（画廊式）"""
    
    closed = Signal()
    COLUMNS = 4  # 4 列网格
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._cards = []
        self._opacity_anim = None  # 动画对象
        self.init_ui()
    
    def init_ui(self):
        # 窗口属性 - Popup 会自动处理点击外部关闭
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Popup |
            Qt.WindowType.NoDropShadowWindowHint  # 禁用系统阴影
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(432)  # 4列 x 96px + 3×8px间距 + 2×12px边距
        self.setMaximumHeight(480)
        
        # 主容器
        self.container = QFrame(self)
        self.container.setObjectName("float_container")
        
        # 布局
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.container)
        
        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(12, 0, 12, 12)
        container_layout.setSpacing(0)
        
        # 标题栏
        header = QFrame()
        header.setObjectName("header")
        header.setFixedHeight(36)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        
        title_label = QLabel("剪贴板历史")
        title_label.setObjectName("title")
        header_layout.addWidget(title_label)
        
        hint_label = QLabel("单击粘贴 · 拖拽放置")
        hint_label.setObjectName("hint")
        header_layout.addWidget(hint_label)
        header_layout.addStretch()
        
        container_layout.addWidget(header)
        
        # 滚动区域
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_area.setObjectName("scroll_area")
        
        # 网格容器
        self.grid_widget = QWidget()
        self.grid_widget.setObjectName("grid_widget")
        self.grid_layout = QGridLayout(self.grid_widget)
        self.grid_layout.setContentsMargins(0, 4, 0, 0)
        self.grid_layout.setSpacing(8)
        self.grid_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        
        # 空状态
        self.empty_label = QLabel("剪贴板为空")
        self.empty_label.setObjectName("empty_label")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setFixedHeight(120)
        self.grid_layout.addWidget(self.empty_label, 0, 0, 1, self.COLUMNS)
        
        self.scroll_area.setWidget(self.grid_widget)
        container_layout.addWidget(self.scroll_area)
        
        # 样式
        self.setStyleSheet(self._get_style())
    
    def _get_style(self) -> str:
        return f"""
            ClipboardFloatPanel {{
                background: transparent;
                border: none;
            }}
            QFrame#float_container {{
                background: {BG_ELEVATED};
                border: 1px solid {BORDER_DEFAULT};
                border-radius: {RADIUS_LG}px;
            }}
            QFrame#header {{
                background: transparent;
                border-bottom: 1px solid {BORDER_DEFAULT};
            }}
            QLabel#title {{
                color: {TEXT_PRIMARY};
                font-size: 13px;
                font-weight: 600;
                font-family: {FONT_FAMILY};
            }}
            QLabel#hint {{
                color: {TEXT_TERTIARY};
                font-size: 11px;
                font-family: {FONT_FAMILY};
            }}
            QScrollArea#scroll_area {{
                border: none;
                background: transparent;
            }}
            QWidget#grid_widget {{
                background: transparent;
            }}
            QLabel#empty_label {{
                color: {TEXT_TERTIARY};
                font-size: 13px;
                font-family: {FONT_FAMILY};
            }}
            {get_scrollbar_style()}
        """
    
    def show_at_cursor(self):
        """在鼠标位置显示面板"""
        # 清除残留按键状态
        self._clear_keyboard_state()
        
        # 更新内容
        self._refresh_content()
        
        # 计算位置
        cursor_pos = QCursor.pos()
        screen = QApplication.screenAt(cursor_pos)
        if not screen:
            screen = QApplication.primaryScreen()
        
        screen_geometry = screen.availableGeometry()
        
        # 调整大小
        self.adjustSize()
        
        # 计算窗口位置（避免超出屏幕）
        x = cursor_pos.x()
        y = cursor_pos.y()
        
        # 右边界检测
        if x + self.width() > screen_geometry.right():
            x = screen_geometry.right() - self.width() - 10
        
        # 下边界检测
        if y + self.height() > screen_geometry.bottom():
            y = cursor_pos.y() - self.height()
        
        self.move(x, y)
        self.show()
        
        # 入场动画
        self._animate_in()
    
    def _refresh_content(self):
        """刷新剪贴板历史内容"""
        # 清理旧卡片
        for card in self._cards:
            card.cleanup()
            card.deleteLater()
        self._cards.clear()
        
        # 清空网格布局
        while self.grid_layout.count() > 0:
            item = self.grid_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setParent(None)
        
        # 获取历史
        manager = ClipboardHistoryManager.instance()
        items = manager.get_items()
        
        if not items:
            # 显示空状态
            self.grid_layout.addWidget(self.empty_label, 0, 0, 1, self.COLUMNS)
            return
        
        # 隐藏空状态
        self.empty_label.setParent(None)
        
        # 添加卡片到网格
        for i, item in enumerate(items):
            row = i // self.COLUMNS
            col = i % self.COLUMNS
            
            card = ClipboardFloatCard(item)
            card.clicked.connect(self._on_card_clicked)
            self._cards.append(card)
            self.grid_layout.addWidget(card, row, col)
    
    def _on_card_clicked(self, item: ClipboardItem):
        """卡片点击 -> 粘贴到当前窗口"""
        # 设置剪贴板内容
        clipboard = QApplication.clipboard()
        source_path = item.source_file_path if item.content_type == "image" else None
        if source_path and os.path.isfile(source_path):
            m = QMimeData()
            file_url = QUrl.fromLocalFile(source_path)
            m.setUrls([file_url])
            m.setData("text/uri-list", file_url.toString().encode("utf-8"))
            clipboard.setMimeData(m)
            pm = item.try_get_pixmap()
        else:
            pm = None
            if item.content_type == "image":
                p = item.content
                pm = p if p and not p.isNull() else None
        
        if (source_path and os.path.isfile(source_path)) is False and pm is not None and not pm.isNull():
            clipboard.setPixmap(pm)
            try:
                clipboard.setImage(pm.toImage())
            except Exception:
                pass
        elif item.content_type == "file":
            paths = item.file_paths()
            if paths:
                m = QMimeData()
                m.setUrls([QUrl.fromLocalFile(p) for p in paths])
                clipboard.setMimeData(m)
        else:
            clipboard.setText(item.content)
        
        # 关闭面板
        self.hide()
        
        # 延迟后模拟粘贴（增加延迟确保窗口切换完成）
        # 企业微信可能需要更长时间才能获得焦点
        delay_ms = 400  # 从200增加到400毫秒
        QTimer.singleShot(delay_ms, self._simulate_paste)
    
    def _simulate_paste(self):
        """模拟 Ctrl+V 粘贴"""
        try:
            import ctypes
            from ctypes import wintypes
            
            # 定义必要的常量和结构
            INPUT_KEYBOARD = 1
            KEYEVENTF_KEYUP = 0x0002
            
            VK_CONTROL = 0x11
            VK_V = 0x56
            
            class KEYBDINPUT(ctypes.Structure):
                _fields_ = [
                    ("wVk", wintypes.WORD),
                    ("wScan", wintypes.WORD),
                    ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD),
                    ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG))
                ]
            
            class MOUSEINPUT(ctypes.Structure):
                _fields_ = [
                    ("dx", wintypes.LONG),
                    ("dy", wintypes.LONG),
                    ("mouseData", wintypes.DWORD),
                    ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD),
                    ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG))
                ]
            
            class HARDWAREINPUT(ctypes.Structure):
                _fields_ = [
                    ("uMsg", wintypes.DWORD),
                    ("wParamL", wintypes.WORD),
                    ("wParamH", wintypes.WORD)
                ]
            
            class INPUT_UNION(ctypes.Union):
                _fields_ = [
                    ("mi", MOUSEINPUT),
                    ("ki", KEYBDINPUT),
                    ("hi", HARDWAREINPUT)
                ]
            
            class INPUT(ctypes.Structure):
                _fields_ = [
                    ("type", wintypes.DWORD),
                    ("union", INPUT_UNION)
                ]
            
            # 定义函数指针类型
            LPINPUT = ctypes.POINTER(INPUT)
            SendInput = ctypes.windll.user32.SendInput
            SendInput.argtypes = [wintypes.UINT, LPINPUT, ctypes.c_int]
            SendInput.restype = wintypes.UINT
            
            # 创建输入数组
            inputs = (INPUT * 4)()
            
            # 按下 Ctrl
            inputs[0].type = INPUT_KEYBOARD
            inputs[0].union.ki.wVk = VK_CONTROL
            inputs[0].union.ki.dwFlags = 0
            
            # 按下 V
            inputs[1].type = INPUT_KEYBOARD
            inputs[1].union.ki.wVk = VK_V
            inputs[1].union.ki.dwFlags = 0
            
            # 释放 V
            inputs[2].type = INPUT_KEYBOARD
            inputs[2].union.ki.wVk = VK_V
            inputs[2].union.ki.dwFlags = KEYEVENTF_KEYUP
            
            # 释放 Ctrl
            inputs[3].type = INPUT_KEYBOARD
            inputs[3].union.ki.wVk = VK_CONTROL
            inputs[3].union.ki.dwFlags = KEYEVENTF_KEYUP
            
            result = SendInput(4, ctypes.cast(inputs, LPINPUT), ctypes.sizeof(INPUT))
            
            if result != 4:
                # 如果 SendInput 失败，尝试备用方法
                self._fallback_simulate_paste()
                
        except Exception:
            # 尝试备用方法
            try:
                self._fallback_simulate_paste()
            except Exception:
                pass
    
    def _fallback_simulate_paste(self):
        """备用粘贴方法（使用 keybd_event）"""
        try:
            import ctypes
            import time
            
            VK_CONTROL = 0x11
            VK_V = 0x56
            KEYEVENTF_KEYUP = 0x0002
            
            # 按下 Ctrl
            ctypes.windll.user32.keybd_event(VK_CONTROL, 0, 0, 0)
            time.sleep(0.02)  # 短暂延迟
            
            # 按下 V
            ctypes.windll.user32.keybd_event(VK_V, 0, 0, 0)
            time.sleep(0.02)
            
            # 释放 V
            ctypes.windll.user32.keybd_event(VK_V, 0, KEYEVENTF_KEYUP, 0)
            time.sleep(0.02)
            
            # 释放 Ctrl
            ctypes.windll.user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
            
        except Exception:
            pass
    
    def _clear_keyboard_state(self):
        """清除残留的按键状态"""
        try:
            import ctypes
            KEYEVENTF_KEYUP = 0x0002
            keys_to_release = [0x11, 0x10, 0x56]  # VK_CONTROL, VK_SHIFT, VK_V
            for vk in keys_to_release:
                ctypes.windll.user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
        except Exception:
            pass
    
    def _animate_in(self):
        """入场动画"""
        self.setWindowOpacity(0)
        
        self._opacity_anim = QPropertyAnimation(self, b"windowOpacity")
        self._opacity_anim.setDuration(150)
        self._opacity_anim.setStartValue(0)
        self._opacity_anim.setEndValue(1.0)
        self._opacity_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._opacity_anim.start()
    
    def keyPressEvent(self, event):
        """按 Esc 关闭"""
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
            return
        super().keyPressEvent(event)
    
    def hideEvent(self, event):
        """隐藏时发送信号"""
        self.closed.emit()
        super().hideEvent(event)
    
    def cleanup(self):
        """清理资源"""
        for card in self._cards:
            card.cleanup()
