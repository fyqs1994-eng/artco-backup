"""
图片浏览器模块
独立的图片查看器，支持缩放、拖拽、切换图片、旋转、删除等功能
可作为 Windows 默认图片查看器使用
"""

import os
import re
import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict
from io import BytesIO
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout, QApplication,
    QGraphicsDropShadowEffect, QPushButton, QMessageBox, QScrollArea,
    QFrame, QSlider, QSizePolicy, QFileDialog, QSplitter
)
from PySide6.QtCore import Qt, Signal, QPoint, QSize, QTimer, QRectF, QPropertyAnimation, QEasingCurve, QBuffer, QIODevice, QThread, QRunnable, QThreadPool, QObject
from PySide6.QtGui import (
    QPixmap, QGuiApplication, QPainter, QColor, QWheelEvent,
    QMouseEvent, QKeyEvent, QMovie, QImageReader, QTransform, QImage, QPen, QPainterPath
)
import qtawesome as qta


# ==================== LRU 图片缓存 ====================

class ImageCache:
    """LRU 图片缓存池 - 避免重复解码"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_cache()
        return cls._instance
    
    def _init_cache(self):
        self._cache: OrderedDict[str, QPixmap] = OrderedDict()
        self._preview_cache: OrderedDict[str, QPixmap] = OrderedDict()  # 低分辨率预览缓存
        self._max_size = 20  # 最多缓存 20 张高清图
        self._max_preview_size = 50  # 最多缓存 50 张预览图
        self._max_memory_mb = 500  # 最大内存占用 500MB
        self._current_memory = 0
    
    def _estimate_pixmap_memory(self, pixmap: QPixmap) -> int:
        """估算 QPixmap 内存占用 (bytes)"""
        if pixmap.isNull():
            return 0
        return pixmap.width() * pixmap.height() * 4  # RGBA
    
    def get(self, path: str) -> Optional[QPixmap]:
        """获取缓存的图片"""
        if path in self._cache:
            # 移到末尾（最近使用）
            self._cache.move_to_end(path)
            return self._cache[path]
        return None
    
    def get_preview(self, path: str) -> Optional[QPixmap]:
        """获取预览缓存"""
        if path in self._preview_cache:
            self._preview_cache.move_to_end(path)
            return self._preview_cache[path]
        return None
    
    def put(self, path: str, pixmap: QPixmap):
        """放入缓存"""
        if pixmap.isNull():
            return
        
        mem = self._estimate_pixmap_memory(pixmap)
        
        # 清理旧缓存
        while (len(self._cache) >= self._max_size or 
               self._current_memory + mem > self._max_memory_mb * 1024 * 1024):
            if self._cache:
                old_path, old_pixmap = self._cache.popitem(last=False)
                self._current_memory -= self._estimate_pixmap_memory(old_pixmap)
            else:
                break
        
        self._cache[path] = pixmap
        self._current_memory += mem
    
    def put_preview(self, path: str, pixmap: QPixmap):
        """放入预览缓存"""
        if pixmap.isNull():
            return
        
        if len(self._preview_cache) >= self._max_preview_size:
            self._preview_cache.popitem(last=False)
        
        self._preview_cache[path] = pixmap
    
    def clear(self):
        """清空缓存"""
        self._cache.clear()
        self._preview_cache.clear()
        self._current_memory = 0


# 全局缓存实例
image_cache = ImageCache()

# PSD 支持（可选）
try:
    from psd_tools import PSDImage
    from PIL import Image
    HAS_PSD_SUPPORT = True
except ImportError:
    HAS_PSD_SUPPORT = False


# 支持的图片格式
SUPPORTED_FORMATS = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.ico', '.tiff', '.tif', '.svg', '.psd'}

# 导入主题
from ui.theme import (
    BG_PRIMARY, BG_SECONDARY, BG_HOVER, BG_ACTIVE, BG_ELEVATED,
    BORDER_SUBTLE, BORDER_DEFAULT, BORDER_STRONG,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_TERTIARY, TEXT_MUTED,
    ACCENT_PRIMARY, ACCENT_SUBTLE, ACCENT_BORDER, ACCENT_BORDER_HOVER,
    COLOR_ERROR, COLOR_ERROR_SUBTLE,
    RADIUS_SM, RADIUS_MD, RADIUS_XL,
    SPACING_SM, SPACING_MD, SPACING_LG,
    ICON_SM, ICON_MD, ICON_DEFAULT, ICON_MUTED,
    BTN_SIZE, BTN_SIZE_SM,
    FILE_ICON_PSD,
    get_scrollbar_style
)


# 工具栏样式
TOOLBAR_RADIUS = RADIUS_XL
ICON_SIZE = ICON_MD
ICON_COLOR = ICON_DEFAULT
ICON_COLOR_LIGHT = ICON_MUTED


class ImageLoaderThread(QThread):
    """异步加载大图的线程 - 支持渐进式加载"""
    loaded = Signal(QPixmap, str, bool)  # 图片数据, 错误信息, 是否为预览
    progress = Signal(int)  # 加载进度 0-100
    
    def __init__(self, path: str, load_preview_first: bool = True):
        super().__init__()
        self.path = path
        self._is_running = True
        self.load_preview_first = load_preview_first  # 是否先加载预览
    
    def run(self):
        """在线程中加载图片 - 渐进式：先预览后高清"""
        try:
            # 检查缓存
            cached = image_cache.get(self.path)
            if cached:
                self.loaded.emit(cached, "", False)
                return
            
            self.progress.emit(5)
            
            # 使用 QImageReader 获取图片信息
            reader = QImageReader(self.path)
            reader.setAutoTransform(True)
            
            size = reader.size()
            if not size.isValid():
                self.loaded.emit(QPixmap(), f"无法读取图片: {self.path}", False)
                return
            
            self.progress.emit(10)
            
            # 步骤 1：快速加载低分辨率预览（如果需要）
            if self.load_preview_first and (size.width() > 1200 or size.height() > 1200):
                preview = image_cache.get_preview(self.path)
                if preview:
                    self.loaded.emit(preview, "", True)
                else:
                    preview_reader = QImageReader(self.path)
                    preview_reader.setAutoTransform(True)
                    # 预览尺寸：最大边 400px
                    preview_scale = min(400 / size.width(), 400 / size.height(), 1.0)
                    preview_reader.setScaledSize(QSize(
                        int(size.width() * preview_scale),
                        int(size.height() * preview_scale)
                    ))
                    preview_img = preview_reader.read()
                    if not preview_img.isNull():
                        preview_pixmap = QPixmap.fromImage(preview_img)
                        image_cache.put_preview(self.path, preview_pixmap)
                        self.loaded.emit(preview_pixmap, "", True)
            
            if not self._is_running:
                return
            
            self.progress.emit(30)
            
            # 步骤 2：加载高清图
            full_reader = QImageReader(self.path)
            full_reader.setAutoTransform(True)
            
            # 超大图片智能缩放
            if size.width() > 4000 or size.height() > 4000:
                screen = QGuiApplication.primaryScreen().geometry()
                max_dimension = max(screen.width(), screen.height()) * 2
                scale = min(max_dimension / size.width(), max_dimension / size.height(), 1.0)
                if scale < 1.0:
                    full_reader.setScaledSize(QSize(int(size.width() * scale), int(size.height() * scale)))
            
            self.progress.emit(60)
            
            if not self._is_running:
                return
            
            qimage = full_reader.read()
            
            self.progress.emit(90)
            
            if qimage.isNull():
                self.loaded.emit(QPixmap(), f"图片格式不支持或已损坏: {self.path}", False)
                return
            
            pixmap = QPixmap.fromImage(qimage)
            
            # 放入缓存
            image_cache.put(self.path, pixmap)
            
            self.progress.emit(100)
            self.loaded.emit(pixmap, "", False)
            
        except Exception as e:
            self.loaded.emit(QPixmap(), f"加载失败: {str(e)}", False)
    
    def stop(self):
        """停止加载"""
        self._is_running = False


class PSDLoaderThread(QThread):
    """异步加载PSD的线程 - 支持渐进式加载"""
    loaded = Signal(QPixmap, str, bool)  # 图片数据, 错误信息, 是否为预览
    progress = Signal(int)  # 加载进度 0-100
    
    def __init__(self, path: str, preview_only: bool = False):
        super().__init__()
        self.path = path
        self._is_running = True
        self.preview_only = preview_only  # 只加载预览（用于预加载）
    
    def run(self):
        """在线程中加载PSD - 渐进式"""
        try:
            if not HAS_PSD_SUPPORT:
                self.loaded.emit(QPixmap(), "PSD支持未安装", False)
                return
            
            # 检查缓存
            cached = image_cache.get(self.path)
            if cached:
                self.loaded.emit(cached, "", False)
                return
            
            self.progress.emit(10)
            
            psd = PSDImage.open(self.path)
            
            self.progress.emit(20)
            
            # 步骤 1：快速生成预览
            preview = image_cache.get_preview(self.path)
            if not preview:
                pil_preview = psd.composite()
                if pil_preview:
                    # 缩放到 400px 预览
                    max_preview = 400
                    if pil_preview.width > max_preview or pil_preview.height > max_preview:
                        ratio = min(max_preview / pil_preview.width, max_preview / pil_preview.height)
                        new_size = (int(pil_preview.width * ratio), int(pil_preview.height * ratio))
                        pil_preview_small = pil_preview.resize(new_size, Image.NEAREST)
                    else:
                        pil_preview_small = pil_preview
                    
                    if pil_preview_small.mode != 'RGBA':
                        pil_preview_small = pil_preview_small.convert('RGBA')
                    
                    data = pil_preview_small.tobytes('raw', 'RGBA')
                    qimage = QImage(data, pil_preview_small.width, pil_preview_small.height, QImage.Format.Format_RGBA8888)
                    preview = QPixmap.fromImage(qimage)
                    image_cache.put_preview(self.path, preview)
            
            if preview:
                self.loaded.emit(preview, "", True)
            
            self.progress.emit(40)
            
            if self.preview_only or not self._is_running:
                return
            
            # 步骤 2：加载高质量版本
            pil_image = psd.composite()
            
            if pil_image is None:
                self.loaded.emit(QPixmap(), "无法合成PSD图像", False)
                return
            
            self.progress.emit(60)
            
            # 智能缩放
            max_size = 4000
            if pil_image.width > max_size or pil_image.height > max_size:
                ratio = min(max_size / pil_image.width, max_size / pil_image.height)
                new_size = (int(pil_image.width * ratio), int(pil_image.height * ratio))
                pil_image = pil_image.resize(new_size, Image.LANCZOS)
            
            if pil_image.mode != 'RGBA':
                pil_image = pil_image.convert('RGBA')
            
            self.progress.emit(85)
            
            if not self._is_running:
                return
            
            data = pil_image.tobytes('raw', 'RGBA')
            qimage = QImage(data, pil_image.width, pil_image.height, QImage.Format.Format_RGBA8888)
            pixmap = QPixmap.fromImage(qimage)
            
            # 放入缓存
            image_cache.put(self.path, pixmap)
            
            self.progress.emit(100)
            self.loaded.emit(pixmap, "", False)
            
        except Exception as e:
            import traceback
            error_msg = f"PSD加载失败: {str(e)}"
            self.loaded.emit(QPixmap(), error_msg, False)
    
    def stop(self):
        """停止加载"""
        self._is_running = False


class ThumbnailLoaderSignals(QObject):
    """缩略图加载信号 - 用于线程池任务"""
    loaded = Signal(int, QPixmap)  # index, pixmap


class ThumbnailLoaderTask(QRunnable):
    """缩略图异步加载任务 - 使用线程池"""
    
    def __init__(self, index: int, path: Path, signals: ThumbnailLoaderSignals):
        super().__init__()
        self.index = index
        self.path = path
        self.signals = signals
        self._is_cancelled = False
    
    def run(self):
        if self._is_cancelled:
            return
        
        try:
            pixmap = None
            
            if self.path.suffix.lower() == '.psd':
                if HAS_PSD_SUPPORT:
                    psd = PSDImage.open(str(self.path))
                    pil_img = psd.composite()
                    if pil_img:
                        if pil_img.mode != 'RGBA':
                            pil_img = pil_img.convert('RGBA')
                        pil_img.thumbnail((64, 64))
                        data = pil_img.tobytes('raw', 'RGBA')
                        qimg = QImage(data, pil_img.width, pil_img.height, QImage.Format.Format_RGBA8888)
                        pixmap = QPixmap.fromImage(qimg)
            else:
                reader = QImageReader(str(self.path))
                reader.setScaledSize(QSize(64, 64))
                img = reader.read()
                if not img.isNull():
                    pixmap = QPixmap.fromImage(img)
            
            if pixmap and not self._is_cancelled:
                self.signals.loaded.emit(self.index, pixmap)
                
        except Exception:
            pass
    
    def cancel(self):
        self._is_cancelled = True


class ThumbnailItem(QWidget):
    """缩略图项 - 异步加载优化版"""
    clicked = Signal(int)
    
    # 共享线程池
    _thread_pool = None
    _loader_signals = None
    
    @classmethod
    def get_thread_pool(cls):
        if cls._thread_pool is None:
            cls._thread_pool = QThreadPool.globalInstance()
            cls._thread_pool.setMaxThreadCount(4)  # 限制并发数
        return cls._thread_pool
    
    @classmethod
    def get_loader_signals(cls):
        if cls._loader_signals is None:
            cls._loader_signals = ThumbnailLoaderSignals()
        return cls._loader_signals
    
    def __init__(self, index: int, path: Path, parent=None):
        super().__init__(parent)
        self.index = index
        self.path = path
        self.is_current = False
        self._pixmap: Optional[QPixmap] = None
        self._loader_task: Optional[ThumbnailLoaderTask] = None
        
        self.setFixedSize(64, 64)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        if self.path.suffix.lower() == '.psd':
            self.setToolTip(f"@{self.path}\nPSD")
        
        # 连接信号
        self.get_loader_signals().loaded.connect(self._on_thumbnail_loaded)
        
        # 延迟启动异步加载（错开启动时间）
        QTimer.singleShot(20 * (index % 10), self._start_async_load)
    
    def _start_async_load(self):
        """启动异步加载"""
        self._loader_task = ThumbnailLoaderTask(
            self.index, self.path, self.get_loader_signals()
        )
        self.get_thread_pool().start(self._loader_task)
    
    def _on_thumbnail_loaded(self, index: int, pixmap: QPixmap):
        """缩略图加载完成回调"""
        if index == self.index:
            self._pixmap = pixmap
            self.update()
    
    def set_current(self, is_current: bool):
        self.is_current = is_current
        self.update()
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # 背景
        if self.is_current:
            painter.setPen(QPen(QColor(ACCENT_PRIMARY), 2))
            painter.setBrush(QColor(0, 102, 255, 20))
        else:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(0, 0, 0, 10))
        painter.drawRoundedRect(self.rect().adjusted(2, 2, -2, -2), 6, 6)
        
        # 缩略图
        if self._pixmap and not self._pixmap.isNull():
            x = (self.width() - self._pixmap.width()) // 2
            y = (self.height() - self._pixmap.height()) // 2
            painter.drawPixmap(x, y, self._pixmap)
        else:
            # 加载中占位符 - 使用渐变动画效果
            painter.setPen(QColor(TEXT_TERTIARY))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "...")

        # PSD 角标
        if self.path.suffix.lower() == '.psd':
            badge_rect = QRectF(6, 6, 30, 14)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(10, 10, 10, 160))
            painter.drawRoundedRect(badge_rect, 6, 6)

            painter.setPen(QColor("white"))
            font = painter.font()
            font.setPointSize(8)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, "PSD")
    
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.index)
    
    def cleanup(self):
        """清理资源"""
        if self._loader_task:
            self._loader_task.cancel()



class ThumbnailPanelToggle(QWidget):
    """缩略图侧栏边缘折叠按钮 - 吸附在面板右边缘"""
    clicked = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(16, 48)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._is_collapsed = False
        self.setToolTip("折叠 (Tab)")
    
    def set_collapsed(self, collapsed: bool):
        self._is_collapsed = collapsed
        self.setToolTip("展开 (Tab)" if collapsed else "折叠 (Tab)")
        self.update()
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # 背景 - 右侧半圆形
        path = QPainterPath()
        rect = self.rect()
        # 左边直线，右边圆弧
        path.moveTo(0, 0)
        path.lineTo(rect.width() - 8, 0)
        path.arcTo(rect.width() - 16, 0, 16, rect.height(), 90, -180)
        path.lineTo(0, rect.height())
        path.closeSubpath()
        
        painter.setPen(QPen(QColor(BORDER_DEFAULT), 1))
        painter.setBrush(QColor(BG_SECONDARY))
        painter.drawPath(path)
        
        # 箭头图标
        icon_name = 'mdi6.chevron-right' if self._is_collapsed else 'mdi6.chevron-left'
        icon = qta.icon(icon_name, color=ICON_COLOR)
        icon_pixmap = icon.pixmap(QSize(12, 12))
        icon_x = (rect.width() - 12) // 2 - 1
        icon_y = (rect.height() - 12) // 2
        painter.drawPixmap(icon_x, icon_y, icon_pixmap)
    
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()


class ThumbnailPanel(QWidget):
    """左侧缩略图面板"""
    image_selected = Signal(int)
    collapse_toggled = Signal(bool)  # 通知父组件折叠状态变化
    
    # 尺寸常量
    EXPANDED_WIDTH = 80
    COLLAPSED_WIDTH = 0
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._collapsed = False
        self._items: List[ThumbnailItem] = []
        self._current_index = 0
        
        self.init_ui()
    
    def init_ui(self):
        self.setFixedWidth(self.EXPANDED_WIDTH)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(0)
        
        # 滚动区域（移除了折叠按钮）
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_area.setStyleSheet(f"""
            QScrollArea {{
                background-color: transparent;
                border: none;
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 6px;
            }}
            QScrollBar::handle:vertical {{
                background: {BORDER_STRONG};
                border-radius: 3px;
                min-height: 20px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
        """)
        
        self.scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setContentsMargins(0, 4, 0, 4)
        self.scroll_layout.setSpacing(4)
        self.scroll_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        
        self.scroll_area.setWidget(self.scroll_content)
        main_layout.addWidget(self.scroll_area)
    
    def set_file_list(self, file_list: List[Path], current_index: int):
        """设置文件列表"""
        # 清除旧项
        for item in self._items:
            item.deleteLater()
        self._items.clear()
        
        # 创建新项
        for i, path in enumerate(file_list):
            item = ThumbnailItem(i, path)
            item.clicked.connect(self._on_item_clicked)
            self._items.append(item)
            self.scroll_layout.addWidget(item)
        
        self.set_current_index(current_index)
    
    def set_current_index(self, index: int):
        """设置当前选中项"""
        if 0 <= self._current_index < len(self._items):
            self._items[self._current_index].set_current(False)
        
        self._current_index = index
        
        if 0 <= index < len(self._items):
            self._items[index].set_current(True)
            # 滚动到可见
            self.scroll_area.ensureWidgetVisible(self._items[index])
    
    def _on_item_clicked(self, index: int):
        self.image_selected.emit(index)
    
    def set_collapsed(self, collapsed: bool):
        """设置折叠状态（由外部按钮控制）"""
        self._collapsed = collapsed
        if collapsed:
            self.setFixedWidth(self.COLLAPSED_WIDTH)
            self.hide()
        else:
            self.setFixedWidth(self.EXPANDED_WIDTH)
            self.show()
    
    def is_collapsed(self) -> bool:
        return self._collapsed
    
    def paintEvent(self, event):
        """绘制浅色背景"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(BORDER_DEFAULT), 1))
        painter.setBrush(QColor(BG_SECONDARY))
        painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), TOOLBAR_RADIUS, TOOLBAR_RADIUS)


class BottomToolbar(QWidget):
    """底部工具栏 - 浅色风格"""
    prev_clicked = Signal()
    next_clicked = Signal()
    zoom_in_clicked = Signal()
    zoom_out_clicked = Signal()
    fit_clicked = Signal()
    actual_clicked = Signal()
    rotate_cw_clicked = Signal()
    rotate_ccw_clicked = Signal()
    copy_clicked = Signal()
    delete_clicked = Signal()
    open_folder_clicked = Signal()
    assign_clicked = Signal()
    open_ps_clicked = Signal()
    feedback_clicked = Signal()  # 新增：反馈标注
    submit_clicked = Signal()  # 新增：提交到收件箱
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()
    
    def init_ui(self):
        self.setFixedHeight(56)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(SPACING_LG, SPACING_SM, SPACING_LG, SPACING_SM)
        layout.setSpacing(6)
        
        # === 1. 缩放区 & 旋转区 (左侧) ===
        # 缩放
        self.btn_zoom_out = self._create_btn('mdi6.minus', "缩小 (-)")
        self.btn_zoom_out.clicked.connect(self.zoom_out_clicked.emit)
        layout.addWidget(self.btn_zoom_out)
        
        self.label_scale = QLabel("100%")
        self.label_scale.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px; min-width: 42px;")
        self.label_scale.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.label_scale)
        
        self.btn_zoom_in = self._create_btn('mdi6.plus', "放大 (+)")
        self.btn_zoom_in.clicked.connect(self.zoom_in_clicked.emit)
        layout.addWidget(self.btn_zoom_in)
        
        self.btn_fit = self._create_btn('mdi6.fit-to-screen', "适应窗口 (Ctrl+0)")
        self.btn_fit.clicked.connect(self.fit_clicked.emit)
        layout.addWidget(self.btn_fit)
        
        self.btn_actual = self._create_btn('mdi6.image-size-select-actual', "原始大小 (Ctrl+1)")
        self.btn_actual.clicked.connect(self.actual_clicked.emit)
        layout.addWidget(self.btn_actual)
        
        layout.addWidget(self._create_separator())
        
        # 旋转
        self.btn_rotate_ccw = self._create_btn('mdi6.rotate-left', "逆时针旋转 (Shift+R)")
        self.btn_rotate_ccw.clicked.connect(self.rotate_ccw_clicked.emit)
        layout.addWidget(self.btn_rotate_ccw)
        
        self.btn_rotate_cw = self._create_btn('mdi6.rotate-right', "顺时针旋转 (R)")
        self.btn_rotate_cw.clicked.connect(self.rotate_cw_clicked.emit)
        layout.addWidget(self.btn_rotate_cw)
        
        # === 居中弹性空间 ===
        layout.addStretch()
        
        # === 2. 导航区 (居中) ===
        nav_container = QWidget()
        nav_layout = QHBoxLayout(nav_container)
        nav_layout.setContentsMargins(0, 0, 0, 0)
        nav_layout.setSpacing(12)
        
        self.btn_prev = self._create_btn('mdi6.chevron-left', "上一张 (←)", prominent=True)
        self.btn_prev.clicked.connect(self.prev_clicked.emit)
        nav_layout.addWidget(self.btn_prev)
        
        self.label_index = QLabel("0 / 0")
        self.label_index.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 13px; font-weight: 600; min-width: 60px;")
        self.label_index.setAlignment(Qt.AlignmentFlag.AlignCenter)
        nav_layout.addWidget(self.label_index)
        
        self.btn_next = self._create_btn('mdi6.chevron-right', "下一张 (→)", prominent=True)
        self.btn_next.clicked.connect(self.next_clicked.emit)
        nav_layout.addWidget(self.btn_next)
        
        layout.addWidget(nav_container)
        
        # === 居中弹性空间 ===
        layout.addStretch()
        
        # === 3. 操作区 (右侧) ===
        self.btn_copy = self._create_btn('mdi6.content-copy', "复制 (Ctrl+C)")
        self.btn_copy.clicked.connect(self.copy_clicked.emit)
        layout.addWidget(self.btn_copy)
        
        self.btn_folder = self._create_btn('mdi6.folder-open-outline', "打开所在文件夹 (Ctrl+E)")
        self.btn_folder.clicked.connect(self.open_folder_clicked.emit)
        layout.addWidget(self.btn_folder)
        
        self.btn_ps = self._create_btn('mdi6.palette-outline', "用 Photoshop 打开 (Ctrl+P)", color=FILE_ICON_PSD)

        self.btn_ps.clicked.connect(self.open_ps_clicked.emit)
        layout.addWidget(self.btn_ps)
        
        self.btn_feedback = self._create_btn('mdi6.message-draw', "反馈标注 (F)", color=ACCENT_PRIMARY)

        self.btn_feedback.clicked.connect(self.feedback_clicked.emit)
        layout.addWidget(self.btn_feedback)

        self.btn_submit = self._create_btn('mdi6.send', "提交到收件箱", color=ACCENT_PRIMARY)
        self.btn_submit.clicked.connect(self.submit_clicked.emit)
        layout.addWidget(self.btn_submit)
        
        layout.addWidget(self._create_separator())
        
        self.btn_assign = self._create_btn('mdi6.folder-move-outline', "分配到工作区 (Ctrl+D)", color=ACCENT_PRIMARY)
        self.btn_assign.clicked.connect(self.assign_clicked.emit)
        layout.addWidget(self.btn_assign)
        
        self.btn_delete = self._create_btn('mdi6.delete-outline', "删除 (Delete)", color=COLOR_ERROR)
        self.btn_delete.clicked.connect(self.delete_clicked.emit)
        layout.addWidget(self.btn_delete)
    
    def _create_btn(self, icon_name: str, tooltip: str, color: str = None, prominent: bool = False) -> QPushButton:
        btn = QPushButton()
        
        size = 40 if prominent else 32
        icon_size = 22 if prominent else 18
        
        btn.setIcon(qta.icon(icon_name, color=color or ICON_DEFAULT))
        btn.setIconSize(QSize(icon_size, icon_size))
        btn.setFixedSize(size, size)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setToolTip(tooltip)
        
        if color == COLOR_ERROR:
            hover_bg = COLOR_ERROR_SUBTLE
        elif color or prominent:
            hover_bg = ACCENT_SUBTLE
        else:
            hover_bg = BG_HOVER
        
        radius = RADIUS_MD if prominent else RADIUS_SM
        base_bg = ACCENT_SUBTLE if prominent else "transparent"
        base_border = f"1px solid {ACCENT_BORDER}" if prominent else "none"
        hover_border = f"border-color: {ACCENT_BORDER_HOVER};" if prominent else ""
        
        style = f"""
            QPushButton {{
                background: {base_bg};
                border: {base_border};
                border-radius: {radius}px;
            }}
            QPushButton:hover {{
                background: {hover_bg};
                {hover_border}
            }}
            QPushButton:pressed {{
                background: {BG_ACTIVE};
            }}
        """

        btn.setStyleSheet(style)
        return btn

    
    def _create_separator(self) -> QWidget:
        sep = QWidget()
        sep.setFixedSize(1, 20)
        sep.setStyleSheet(f"background: {BORDER_DEFAULT};")
        return sep
    
    def set_index(self, current: int, total: int):
        self.label_index.setText(f"{current} / {total}")
    
    def set_scale(self, scale: float):
        self.label_scale.setText(f"{int(scale * 100)}%")
    
    def paintEvent(self, event):
        """绘制浅色背景"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # 背景
        painter.setPen(QPen(QColor(BORDER_DEFAULT), 1))
        painter.setBrush(QColor(BG_PRIMARY))
        painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), TOOLBAR_RADIUS, TOOLBAR_RADIUS)


class TopBar(QWidget):
    """顶部信息栏"""
    close_clicked = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()
    
    def init_ui(self):
        self.setFixedHeight(44)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 6, 8, 6)
        layout.setSpacing(12)
        
        # 文件名
        self.label_filename = QLabel()
        self.label_filename.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 13px; font-weight: 500;")
        layout.addWidget(self.label_filename)
        
        layout.addStretch()
        
        # 关闭按钮
        self.btn_close = QPushButton()
        self.btn_close.setIcon(qta.icon('mdi6.close', color=ICON_DEFAULT))
        self.btn_close.setIconSize(QSize(18, 18))
        self.btn_close.setFixedSize(32, 32)
        self.btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_close.setToolTip("关闭 (ESC)")
        self.btn_close.clicked.connect(self.close_clicked.emit)
        self.btn_close.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                border: none;
                border-radius: 16px;
            }}
            QPushButton:hover {{
                background-color: {BG_HOVER};
            }}
        """)
        layout.addWidget(self.btn_close)
    
    def set_filename(self, name: str):
        self.label_filename.setText(name)
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(BORDER_DEFAULT), 1))
        painter.setBrush(QColor(BG_PRIMARY))
        painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), TOOLBAR_RADIUS, TOOLBAR_RADIUS)


class ImageCanvas(QWidget):
    """图片画布 - 支持淡入淡出过渡"""
    file_dropped = Signal(str)  # 文件拖放信号
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap: Optional[QPixmap] = None
        self._scaled_pixmap: Optional[QPixmap] = None  # 缩放后缓存
        self._scaled_cache_scale: float = 0  # 缓存对应的缩放比例
        self._old_pixmap: Optional[QPixmap] = None  # 用于过渡动画
        self._scale = 1.0
        self._offset = QPoint(0, 0)
        self._dragging = False
        self._drag_start = QPoint()
        self._drag_offset = QPoint()
        self._has_image = False
        
        # 过渡动画
        self._transition_opacity = 1.0  # 当前图片透明度
        self._transition_timer = QTimer(self)
        self._transition_timer.timeout.connect(self._update_transition)
        self._transition_duration = 150  # 过渡时长 ms
        self._transition_step = 0.1  # 每帧增加的透明度
        
        # 延迟高质量渲染
        self._hq_render_timer = QTimer(self)
        self._hq_render_timer.setSingleShot(True)
        self._hq_render_timer.timeout.connect(self._do_hq_render)
        self._pending_hq_render = False
        
        self.setMouseTracking(True)
        self.setAcceptDrops(True)
    
    def set_pixmap(self, pixmap: QPixmap, animate: bool = True):
        """设置图片，可选淡入动画"""
        if animate and self._pixmap and pixmap and not pixmap.isNull():
            # 保存旧图用于过渡
            self._old_pixmap = self._pixmap
            self._transition_opacity = 0.0
            self._transition_timer.start(16)  # ~60fps
        else:
            self._old_pixmap = None
            self._transition_opacity = 1.0
        
        self._pixmap = pixmap
        self._scaled_pixmap = None  # 清除缩放缓存
        self._scaled_cache_scale = 0
        self._has_image = pixmap is not None and not pixmap.isNull()
        self.update()
    
    def _update_transition(self):
        """更新过渡动画"""
        self._transition_opacity += self._transition_step
        if self._transition_opacity >= 1.0:
            self._transition_opacity = 1.0
            self._transition_timer.stop()
            self._old_pixmap = None
        self.update()
    
    def _do_hq_render(self):
        """执行高质量渲染"""
        self._pending_hq_render = False
        self.update()
    
    def _request_hq_render(self):
        """请求高质量渲染（延迟执行）"""
        self._pending_hq_render = True
        self._hq_render_timer.start(100)  # 100ms 后渲染高质量版本
    
    def has_image(self) -> bool:
        return self._has_image
    
    def set_scale(self, scale: float, fast_mode: bool = False):
        """设置缩放比例
        fast_mode: 快速模式（滚轮缩放时），使用低质量渲染后延迟高质量
        """
        if scale != self._scale:
            self._scale = scale
            if fast_mode:
                # 快速模式：立即用低质量渲染，延迟高质量
                self._hq_render_timer.stop()
                self._request_hq_render()
            self.update()
    
    def get_scale(self) -> float:
        return self._scale
    
    def set_offset(self, offset: QPoint):
        self._offset = offset
        self.update()
    
    def get_offset(self) -> QPoint:
        return self._offset
    
    def reset_view(self):
        self._offset = QPoint(0, 0)
        self.update()
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # 浅灰背景
        painter.fillRect(self.rect(), QColor(BG_SECONDARY))
        
        if not self._pixmap or self._pixmap.isNull():
            # 空状态：显示欢迎界面
            self._draw_empty_state(painter)
            return
        
        # 计算绘制位置
        img_w = int(self._pixmap.width() * self._scale)
        img_h = int(self._pixmap.height() * self._scale)
        
        x = (self.width() - img_w) // 2 + self._offset.x()
        y = (self.height() - img_h) // 2 + self._offset.y()
        
        # 绘制旧图（淡出）
        if self._old_pixmap and not self._old_pixmap.isNull() and self._transition_opacity < 1.0:
            old_opacity = 1.0 - self._transition_opacity
            painter.setOpacity(old_opacity)
            old_img_w = int(self._old_pixmap.width() * self._scale)
            old_img_h = int(self._old_pixmap.height() * self._scale)
            old_x = (self.width() - old_img_w) // 2 + self._offset.x()
            old_y = (self.height() - old_img_h) // 2 + self._offset.y()
            target_rect = QRectF(old_x, old_y, old_img_w, old_img_h)
            old_source = QRectF(0, 0, self._old_pixmap.width(), self._old_pixmap.height())
            painter.drawPixmap(target_rect, self._old_pixmap, old_source)
        
        # 绘制新图（淡入）
        painter.setOpacity(self._transition_opacity)
        
        # 根据是否在快速缩放中选择渲染质量
        use_hq = not self._pending_hq_render
        
        if use_hq:
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        
        target_rect = QRectF(x, y, img_w, img_h)
        source_rect = QRectF(0, 0, self._pixmap.width(), self._pixmap.height())
        painter.drawPixmap(target_rect, self._pixmap, source_rect)
        painter.setOpacity(1.0)
    
    def _draw_empty_state(self, painter: QPainter):
        """绘制空状态欢迎界面"""
        center = self.rect().center()
        
        # 虚线框 - 浅色边框
        painter.setPen(QPen(QColor(BORDER_STRONG), 1.5, Qt.PenStyle.DashLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        box_w, box_h = 280, 160
        box_rect = QRectF(center.x() - box_w/2, center.y() - box_h/2, box_w, box_h)
        painter.drawRoundedRect(box_rect, 12, 12)
        
        # 图标区域
        icon_y = center.y() - 40
        
        # 使用 qtawesome 绘制图标
        icon = qta.icon('mdi6.image-plus', color=TEXT_TERTIARY)
        icon_pixmap = icon.pixmap(QSize(40, 40))
        painter.drawPixmap(center.x() - 20, int(icon_y) - 20, icon_pixmap)
        
        # 主文字
        painter.setPen(QColor(TEXT_SECONDARY))
        font = painter.font()
        font.setPointSize(13)
        font.setBold(False)
        painter.setFont(font)
        painter.drawText(
            QRectF(center.x() - 140, icon_y + 35, 280, 24),
            Qt.AlignmentFlag.AlignCenter,
            "拖放图片到此处"
        )
        
        # 副文字
        painter.setPen(QColor(TEXT_TERTIARY))
        font.setPointSize(11)
        painter.setFont(font)
        painter.drawText(
            QRectF(center.x() - 140, icon_y + 60, 280, 20),
            Qt.AlignmentFlag.AlignCenter,
            "或按 Ctrl+O 打开文件"
        )
        
        # 支持格式
        painter.setPen(QColor(TEXT_MUTED))
        font.setPointSize(10)
        painter.setFont(font)
        painter.drawText(
            QRectF(center.x() - 140, icon_y + 85, 280, 20),
            Qt.AlignmentFlag.AlignCenter,
            "支持 PNG, JPG, GIF, WEBP, PSD 等格式"
        )
    
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            for url in urls:
                if url.isLocalFile():
                    path = Path(url.toLocalFile())
                    if path.suffix.lower() in SUPPORTED_FORMATS:
                        event.acceptProposedAction()
                        return
        event.ignore()
    
    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            for url in urls:
                if url.isLocalFile():
                    path = Path(url.toLocalFile())
                    if path.suffix.lower() in SUPPORTED_FORMATS:
                        self.file_dropped.emit(str(path))
                        event.acceptProposedAction()
                        return
        event.ignore()
    
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_start = event.pos()
            self._drag_offset = self._offset
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
    
    def mouseMoveEvent(self, event):
        if self._dragging:
            delta = event.pos() - self._drag_start
            self._offset = self._drag_offset + delta
            self.update()
    
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            self.setCursor(Qt.CursorShape.ArrowCursor)


class ImageViewer(QWidget):
    """图片浏览器 - 带UI工具栏"""
    
    closed = Signal()
    
    def __init__(self, image_path: str = None, parent=None):
        super().__init__(parent)
        
        # 状态
        self._original_pixmap: Optional[QPixmap] = None
        self._pixmap: Optional[QPixmap] = None
        self._movie: Optional[QMovie] = None
        self._scale = 1.0
        self._min_scale = 0.1
        self._max_scale = 10.0
        self._rotation = 0
        
        # 文件列表
        self._current_path: Optional[Path] = None
        self._file_list: List[Path] = []
        self._current_index = 0
        
        # 异步加载
        self._loader_thread: Optional[ImageLoaderThread] = None
        self._psd_loader_thread: Optional[PSDLoaderThread] = None
        self._preload_threads: List[QThread] = []  # 预加载线程列表，防止被 GC
        
        # 平滑缩放动画
        self._target_scale = 1.0  # 目标缩放比例
        self._zoom_timer = QTimer(self)
        self._zoom_timer.setInterval(16)  # ~60fps
        self._zoom_timer.timeout.connect(self._animate_zoom)
        self._zoom_center = QPoint()  # 缩放中心点
        
        self.init_ui()
        self._update_empty_state()
        
        if image_path:
            self.load_image(image_path)
    
    def init_ui(self):
        self.setWindowTitle("Artco Viewer")
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(800, 600)
        
        # 设置浅色窗口背景
        self.setStyleSheet(f"background: {BG_SECONDARY};")

        
        # 默认窗口大小（屏幕的80%）
        screen = QGuiApplication.primaryScreen().geometry()
        w = int(screen.width() * 0.8)
        h = int(screen.height() * 0.8)
        x = (screen.width() - w) // 2
        y = (screen.height() - h) // 2
        self.setGeometry(x, y, w, h)
        
        # 使用无布局的方式，手动定位实现悬浮侧栏
        # 主内容区（全屏）
        self.content_container = QWidget(self)
        self.content_container.setStyleSheet("background: transparent;")
        content_layout = QVBoxLayout(self.content_container)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        
        # 图片画布
        self.canvas = ImageCanvas()
        self.canvas.file_dropped.connect(self.load_image)
        content_layout.addWidget(self.canvas, 1)
        
        # 底部工具栏（手动定位实现真正悬浮）
        self.bottom_toolbar = BottomToolbar(self)
        self._connect_toolbar_signals()
        self._add_shadow(self.bottom_toolbar)
        self.bottom_toolbar.hide()  # 初始隐藏，加载图片后显示

        
        # 悬浮侧栏（覆盖在内容上方）
        from ui.sidebar import WorkspaceSidebar
        self.sidebar = WorkspaceSidebar(self)
        self.sidebar.file_selected.connect(self._on_sidebar_file_selected)
        self.sidebar.file_opened.connect(self.load_image)
        self.sidebar.width_changed.connect(self._on_sidebar_width_changed)
        self._add_sidebar_shadow()
        
        # 右下角文件信息标签（浮动）
        self.label_info = QLabel(self)
        self.label_info.setStyleSheet(f"""
            QLabel {{
                color: {TEXT_SECONDARY};
                font-size: 11px;
                background: {BG_ELEVATED};
                padding: 4px 8px;
                border-radius: {RADIUS_SM}px;
                border: 1px solid {BORDER_SUBTLE};
            }}
        """)
        self.label_info.hide()
    
    def _add_sidebar_shadow(self):
        """为侧栏添加阴影效果（柔和版）"""
        shadow = QGraphicsDropShadowEffect(self.sidebar)
        shadow.setBlurRadius(16)          # 减小模糊半径，更精致
        shadow.setColor(QColor(0, 0, 0, 30))  # 降低透明度，更柔和
        shadow.setOffset(2, 0)          # 减小偏移，更自然
        self.sidebar.setGraphicsEffect(shadow)
    
    def _add_shadow(self, widget):
        shadow = QGraphicsDropShadowEffect(widget)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 40))
        shadow.setOffset(0, 2)
        widget.setGraphicsEffect(shadow)
    
    def _connect_toolbar_signals(self):
        tb = self.bottom_toolbar
        tb.prev_clicked.connect(self._prev_image)
        tb.next_clicked.connect(self._next_image)
        tb.zoom_in_clicked.connect(self._zoom_in)
        tb.zoom_out_clicked.connect(self._zoom_out)
        tb.fit_clicked.connect(self._fit_image)
        tb.actual_clicked.connect(self._actual_size)
        tb.rotate_cw_clicked.connect(self._rotate_cw)
        tb.rotate_ccw_clicked.connect(self._rotate_ccw)
        tb.copy_clicked.connect(self._copy_image)
        tb.delete_clicked.connect(self._delete_current)
        tb.open_folder_clicked.connect(self._open_in_explorer)
        tb.assign_clicked.connect(self._assign_to_workspace)
        tb.open_ps_clicked.connect(self._open_in_photoshop)
        tb.feedback_clicked.connect(self._open_feedback_editor)
        tb.submit_clicked.connect(self._submit_to_inbox)
    
    def _on_sidebar_file_selected(self, file_path: str):
        """侧栏文件被选中（单击预览）"""
        self.load_image(file_path)
    
    def _on_sidebar_width_changed(self, new_width: int):
        """侧栏宽度变化时更新其几何位置"""
        self.sidebar.setGeometry(0, 0, new_width, self.height())
    
    def _set_info(self, text: str):
        """设置右下角文件信息"""
        if text:
            self.label_info.setText(text)
            self.label_info.adjustSize()
            self._position_info_label()
            self.label_info.show()
        else:
            self.label_info.hide()
    
    def _position_info_label(self):
        """定位信息标签到右下角"""
        margin = 16
        x = self.width() - self.label_info.width() - margin
        y = self.height() - self.label_info.height() - margin - 72  # 避开底部工具栏
        self.label_info.move(x, y)
    
    def resizeEvent(self, event):
        super().resizeEvent(event)
        # 更新内容区域大小（全屏）
        self.content_container.setGeometry(0, 0, self.width(), self.height())
        # 更新悬浮侧栏位置（左侧对齐，全高）
        self.sidebar.setGeometry(0, 0, self.sidebar.width(), self.height())
        # 更新底部工具栏位置（水平居中，距离底部 24px）
        self._position_bottom_toolbar()
        # 更新信息标签位置
        if self.label_info.isVisible():
            self._position_info_label()
    
    def _position_bottom_toolbar(self):
        """手动定位底部工具栏"""
        if hasattr(self, 'bottom_toolbar'):
            margin_bottom = 24
            x = (self.width() - self.bottom_toolbar.width()) // 2
            y = self.height() - self.bottom_toolbar.height() - margin_bottom
            self.bottom_toolbar.move(x, y)

    
    def _update_empty_state(self):
        """更新空状态下的 UI"""
        has_image = self.canvas.has_image()
        
        if has_image:
            self.bottom_toolbar.show()
            self._position_bottom_toolbar()
        else:
            self.setWindowTitle("Artco Viewer")
            self.bottom_toolbar.set_index(0, 0)
            self.bottom_toolbar.set_scale(1.0)
            self.bottom_toolbar.hide()
            self.label_info.hide()

    
    def _open_file_dialog(self):
        """打开文件选择对话框"""
        from PySide6.QtWidgets import QFileDialog
        
        path, _ = QFileDialog.getOpenFileName(
            self, "选择图片", "",
            "Images (*.png *.jpg *.jpeg *.gif *.bmp *.webp *.psd *.ico *.tiff *.svg);;All Files (*)"
        )
        if path:
            self.load_image(path)
    
    def load_image(self, path: str):
        """加载图片 - 全异步 + 渐进式加载"""
        self._current_path = Path(path)
        
        if not self._current_path.exists():
            self.setWindowTitle("文件不存在 - Artco Viewer")
            return
        
        # 停止之前的 GIF 和加载线程
        if self._movie:
            self._movie.stop()
            self._movie = None
        
        if self._loader_thread and self._loader_thread.isRunning():
            self._loader_thread.stop()
            self._loader_thread.wait(100)  # 最多等 100ms
        
        if self._psd_loader_thread and self._psd_loader_thread.isRunning():
            self._psd_loader_thread.stop()
            self._psd_loader_thread.wait(100)
        
        # 停止所有预加载线程（切换图片时取消旧的预加载）
        for t in self._preload_threads:
            if t.isRunning():
                t.stop()
        self._preload_threads = [t for t in self._preload_threads if t.isRunning()]
        
        # 加载文件列表
        self._load_file_list()
        
        # 先检查缓存 - 命中缓存则瞬间显示
        cached = image_cache.get(str(self._current_path))
        if cached:
            self._rotation = 0
            self._original_pixmap = cached
            self._pixmap = cached
            self.canvas.set_pixmap(self._pixmap)
            self._on_image_loaded()
            return
        
        # 显示预览占位（如果有）
        preview = image_cache.get_preview(str(self._current_path))
        if preview:
            self._pixmap = preview
            self.canvas.set_pixmap(preview)
            self._set_info("加载中...")
        
        # 根据格式加载
        suffix = self._current_path.suffix.lower()
        if suffix == '.gif':
            self._load_gif(str(self._current_path))
            self._on_image_loaded()
        elif suffix == '.psd':
            self._load_psd_async(str(self._current_path))
        else:
            # 统一异步加载（包括小图）
            self._load_image_async(str(self._current_path))
    
    def _on_image_loaded(self):
        """图片加载完成后的回调"""
        # 更新 UI
        self._update_ui()
        self._fit_image()
        self._update_empty_state()
        
        # 同步侧栏选中状态
        if hasattr(self, 'sidebar'):
            self.sidebar.set_current_file(str(self._current_path))
            # 异步同步图片数据到企微面板（避免阻塞）
            if self._pixmap and not self._pixmap.isNull():
                QTimer.singleShot(100, self._sync_image_to_sidebar)
        
        # 预加载相邻图片（延迟执行，避免影响当前图片显示）
        QTimer.singleShot(300, self._preload_neighbor_images)
    
    def _load_image_async(self, path: str):
        """统一的异步图片加载方法 - 渐进式"""
        if not image_cache.get_preview(path):
            self._set_info("加载中...")
        
        self._loader_thread = ImageLoaderThread(path, load_preview_first=True)
        self._loader_thread.loaded.connect(self._on_image_loaded_progressive)
        self._loader_thread.start()
    
    def _on_image_loaded_progressive(self, pixmap: QPixmap, error: str, is_preview: bool):
        """渐进式加载回调 - 先显示预览，再显示高清"""
        if error:
            self._set_info(f"加载失败: {error}")
            return
        
        if is_preview:
            # 预览图：快速显示，等待高清版
            self._pixmap = pixmap
            self.canvas.set_pixmap(pixmap)
            self._update_ui()
            self._fit_image()
            self._update_empty_state()
            self._set_info("加载高清...")
        else:
            # 高清图：最终版本
            self._rotation = 0
            self._original_pixmap = pixmap
            self._pixmap = pixmap
            self.canvas.set_pixmap(pixmap)
            self._on_image_loaded()
    
    def _load_psd_async(self, path: str):
        """异步加载PSD - 渐进式"""
        if not HAS_PSD_SUPPORT:
            self._set_info("PSD 支持未安装")
            return
        
        if not image_cache.get_preview(path):
            self._set_info("加载 PSD...")
        
        self._psd_loader_thread = PSDLoaderThread(path, preview_only=False)
        self._psd_loader_thread.loaded.connect(self._on_psd_loaded_progressive)
        self._psd_loader_thread.start()
    
    def _on_psd_loaded_progressive(self, pixmap: QPixmap, error: str, is_preview: bool):
        """PSD 渐进式加载回调"""
        if error:
            self._set_info(f"PSD 加载失败: {error}")
            return
        
        if is_preview:
            self._pixmap = pixmap
            self.canvas.set_pixmap(pixmap)
            self._update_ui()
            self._fit_image()
            self._update_empty_state()
            self._set_info("加载高清 PSD...")
        else:
            self._rotation = 0
            self._original_pixmap = pixmap
            self._pixmap = pixmap
            self.canvas.set_pixmap(pixmap)
            self._on_image_loaded()
    
    def _sync_image_to_sidebar(self):
        """同步图片数据到侧栏（异步执行）"""
        if hasattr(self, 'sidebar') and self._pixmap and not self._pixmap.isNull():
            image_data = self._get_image_bytes()
            self.sidebar.set_current_image(image_data)
    
    def _preload_neighbor_images(self):
        """预加载相邻图片到缓存 - 智能预加载"""
        if not self._file_list or len(self._file_list) <= 1:
            return
        
        # 清理已完成的预加载线程
        self._preload_threads = [t for t in self._preload_threads if t.isRunning()]
        
        # 预加载下一张和上一张
        indices_to_preload = [
            (self._current_index + 1) % len(self._file_list),
            (self._current_index - 1) % len(self._file_list),
        ]
        
        for idx in indices_to_preload:
            path = self._file_list[idx]
            path_str = str(path)
            
            # 跳过已缓存的
            if image_cache.get(path_str):
                continue
            
            # 跳过 GIF（不预加载动图）
            if path.suffix.lower() == '.gif':
                continue
            
            # 启动后台预加载线程（保存引用防止 GC）
            if path.suffix.lower() == '.psd':
                if HAS_PSD_SUPPORT:
                    preload_thread = PSDLoaderThread(path_str, preview_only=True)
                    preload_thread.finished.connect(lambda t=preload_thread: self._on_preload_finished(t))
                    self._preload_threads.append(preload_thread)
                    preload_thread.start()
            else:
                preload_thread = ImageLoaderThread(path_str, load_preview_first=True)
                preload_thread.finished.connect(lambda t=preload_thread: self._on_preload_finished(t))
                self._preload_threads.append(preload_thread)
                preload_thread.start()
    
    def _on_preload_finished(self, thread: QThread):
        """预加载线程完成后清理"""
        if thread in self._preload_threads:
            self._preload_threads.remove(thread)
    
    def _load_static_image(self, path: str):
        """加载静态图片 - 优化大图加载性能"""
        # 使用 QImageReader 按需加载，避免一次性加载大图到内存
        reader = QImageReader(path)
        
        # 检查图片尺寸
        size = reader.size()
        if size.isValid() and (size.width() > 4000 or size.height() > 4000):
            # 超大图片：根据屏幕尺寸智能缩放
            screen = QGuiApplication.primaryScreen().geometry()
            max_dimension = max(screen.width(), screen.height()) * 2  # 保留2倍缩放空间
            
            scale = min(max_dimension / size.width(), max_dimension / size.height(), 1.0)
            if scale < 1.0:
                reader.setScaledSize(QSize(int(size.width() * scale), int(size.height() * scale)))
        
        qimage = reader.read()
        self._rotation = 0
        
        if qimage.isNull():
            self._original_pixmap = None
            self._pixmap = None
        else:
            self._original_pixmap = QPixmap.fromImage(qimage)
            self._pixmap = self._original_pixmap
        
        self.canvas.set_pixmap(self._pixmap)
    
    def _load_gif(self, path: str):
        self._movie = QMovie(path)
        self._rotation = 0
        if self._movie.isValid():
            self._movie.frameChanged.connect(self._on_gif_frame)
            self._movie.start()
            self._pixmap = self._movie.currentPixmap()
            self._original_pixmap = None
            self.canvas.set_pixmap(self._pixmap)
        else:
            self._movie = None
            self._load_static_image(path)
    
    def _on_gif_frame(self):
        if self._movie:
            self._pixmap = self._movie.currentPixmap()
            self.canvas.set_pixmap(self._pixmap)
    
    def _load_file_list(self):
        if not self._current_path:
            return
        
        directory = self._current_path.parent
        self._file_list = sorted([
            f for f in directory.iterdir()
            if f.is_file() and f.suffix.lower() in SUPPORTED_FORMATS
        ])
        
        try:
            self._current_index = self._file_list.index(self._current_path)
        except ValueError:
            self._current_index = 0
    
    def _update_ui(self):
        if not self._current_path:
            return
        
        # 窗口标题
        self.setWindowTitle(f"{self._current_path.name} - Artco Viewer")
        
        # 索引
        if self._file_list:
            self.bottom_toolbar.set_index(self._current_index + 1, len(self._file_list))
        
        # 文件信息
        if self._pixmap and not self._pixmap.isNull():
            w, h = self._pixmap.width(), self._pixmap.height()
            size_bytes = self._current_path.stat().st_size
            if size_bytes > 1024 * 1024:
                size_str = f"{size_bytes / (1024*1024):.1f} MB"
            elif size_bytes > 1024:
                size_str = f"{size_bytes / 1024:.0f} KB"
            else:
                size_str = f"{size_bytes} B"
            fmt = self._current_path.suffix.upper().lstrip('.')
            self._set_info(f"{w} × {h}  ·  {fmt}  ·  {size_str}")
    
    def _fit_image(self):
        if not self._pixmap or self._pixmap.isNull():
            return
        
        img_w, img_h = self._pixmap.width(), self._pixmap.height()
        canvas_w, canvas_h = self.canvas.width() - 40, self.canvas.height() - 40
        
        scale_w = canvas_w / img_w
        scale_h = canvas_h / img_h
        self._scale = min(scale_w, scale_h, 1.0)
        self._target_scale = self._scale  # 同步目标缩放
        
        self.canvas.set_scale(self._scale)
        self.canvas.reset_view()
        self.bottom_toolbar.set_scale(self._scale)
    
    def _actual_size(self):
        self._scale = 1.0
        self._target_scale = self._scale  # 同步目标缩放
        self.canvas.set_scale(self._scale)
        self.canvas.reset_view()
        self.bottom_toolbar.set_scale(self._scale)
    
    def _zoom_in(self):
        self._scale = min(self._scale * 1.25, self._max_scale)
        self._target_scale = self._scale  # 同步目标缩放
        self.canvas.set_scale(self._scale)
        self.bottom_toolbar.set_scale(self._scale)
    
    def _zoom_out(self):
        self._scale = max(self._scale / 1.25, self._min_scale)
        self._target_scale = self._scale  # 同步目标缩放
        self.canvas.set_scale(self._scale)
        self.bottom_toolbar.set_scale(self._scale)
    
    def _prev_image(self):
        if not self._file_list or len(self._file_list) <= 1:
            return
        self._current_index = (self._current_index - 1) % len(self._file_list)
        self.load_image(str(self._file_list[self._current_index]))
    
    def _next_image(self):
        if not self._file_list or len(self._file_list) <= 1:
            return
        self._current_index = (self._current_index + 1) % len(self._file_list)
        self.load_image(str(self._file_list[self._current_index]))
    
    def _rotate_cw(self):
        if self._movie:
            return
        if not self._original_pixmap:
            return
        
        self._rotation = (self._rotation + 90) % 360
        
        # 优化：使用 FastTransformation 加快旋转速度
        transform = QTransform().rotate(self._rotation)
        self._pixmap = self._original_pixmap.transformed(transform, Qt.TransformationMode.FastTransformation)
        self.canvas.set_pixmap(self._pixmap)
        self._fit_image()
    
    def _rotate_ccw(self):
        if self._movie:
            return
        if not self._original_pixmap:
            return
        
        self._rotation = (self._rotation - 90) % 360
        
        # 优化：使用 FastTransformation 加快旋转速度
        transform = QTransform().rotate(self._rotation)
        self._pixmap = self._original_pixmap.transformed(transform, Qt.TransformationMode.FastTransformation)
        self.canvas.set_pixmap(self._pixmap)
        self._fit_image()
    
    def _copy_image(self):
        if self._pixmap and not self._pixmap.isNull():
            QGuiApplication.clipboard().setPixmap(self._pixmap)
            self._set_info("已复制到剪贴板")
            QTimer.singleShot(1500, self._update_ui)
    
    def _get_image_bytes(self) -> bytes:
        """获取当前图片的二进制数据（PNG 格式）- 优化：只生成缩略图"""
        if not self._pixmap or self._pixmap.isNull():
            return None
        
        # 企微限制 2MB，大图需要缩放
        max_size = 1024  # 企微推荐最大边长
        pixmap = self._pixmap
        
        # 如果图片太大，生成缩略图
        if pixmap.width() > max_size or pixmap.height() > max_size:
            pixmap = pixmap.scaled(
                max_size, max_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
        
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        pixmap.save(buffer, "PNG", 85)  # 85% 质量平衡大小和清晰度
        data = buffer.data().data()
        buffer.close()
        return data
    
    def _assign_to_workspace(self):
        """打开分配面板"""
        if not self._current_path or not self._current_path.exists():
            return
        
        from .assign_panel import AssignPanel
        panel = AssignPanel(str(self._current_path), self)
        panel.assigned.connect(self._on_assigned)
        panel.exec()
    
    def _on_assigned(self, new_path: str):
        """分配完成回调"""
        self._set_info(f"已分配: {Path(new_path).name}")
        QTimer.singleShot(2000, self._update_ui)
    
    def _delete_current(self):
        if not self._current_path or not self._current_path.exists():
            return
        
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除以下文件吗？\n\n{self._current_path.name}\n\n此操作不可撤销。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply != QMessageBox.StandardButton.Yes:
            return
        
        try:
            next_path = None
            if len(self._file_list) > 1:
                if self._current_index < len(self._file_list) - 1:
                    next_path = self._file_list[self._current_index + 1]
                else:
                    next_path = self._file_list[self._current_index - 1]
            
            self._current_path.unlink()
            
            if self._current_path in self._file_list:
                self._file_list.remove(self._current_path)
            
            if next_path:
                self._current_index = min(self._current_index, len(self._file_list) - 1)
                self.load_image(str(next_path))
            else:
                self.close()
        except Exception as e:
            QMessageBox.warning(self, "删除失败", f"无法删除文件：\n{str(e)}")
    
    def _open_in_explorer(self):
        if not self._current_path or not self._current_path.exists():
            return
        try:
            subprocess.run(['explorer', '/select,', str(self._current_path)], check=False)
        except:
            pass

    def _submit_to_inbox(self):
        """供应商提交：复制当前文件到工作区 `_INBOX` 并写入元数据。"""
        if not self._current_path or not self._current_path.exists():
            QMessageBox.warning(self, "提交失败", "当前没有可提交的文件")
            return

        from config import workspace_config, RESOURCE_TYPES

        workspace_path = workspace_config.get_workspace_path()
        if not workspace_path:
            QMessageBox.warning(self, "提交失败", "请先在侧栏选择工作区")
            return

        workspace_root = Path(workspace_path)

        from PySide6.QtWidgets import QInputDialog
        from ui.theme import get_dialog_style

        def _ask_text(title: str, label: str, default: str = "") -> Optional[str]:
            dialog = QInputDialog(self)
            dialog.setWindowTitle(title)
            dialog.setLabelText(label)
            dialog.setTextValue(default)
            dialog.setOkButtonText("确定")
            dialog.setCancelButtonText("取消")
            dialog.setStyleSheet(get_dialog_style())
            if not dialog.exec():
                return None
            return (dialog.textValue() or "").strip()

        def _ask_item(title: str, label: str, items: list) -> Optional[str]:
            dialog = QInputDialog(self)
            dialog.setWindowTitle(title)
            dialog.setLabelText(label)
            dialog.setComboBoxItems(items)
            dialog.setComboBoxEditable(False)
            dialog.setOkButtonText("确定")
            dialog.setCancelButtonText("取消")
            dialog.setStyleSheet(get_dialog_style())
            if not dialog.exec():
                return None
            return (dialog.textValue() or "").strip()

        # 供应商公司名（用于分流）
        vendor = workspace_config.get_vendor_company()
        if not vendor:
            vendor = _ask_text("供应商公司", "请输入供应商公司名称（用于 _INBOX 分流）：")
            if vendor is None:
                return
            if not vendor:
                QMessageBox.warning(self, "提交失败", "供应商公司名称不能为空")
                return
            workspace_config.set_vendor_company(vendor)

        # 从路径推断 topic / rtype
        topic = ""
        rtype = ""
        try:
            rel = self._current_path.resolve().relative_to(workspace_root.resolve())
            parts = rel.parts
            if len(parts) >= 2:
                topic = parts[0]
                rtype = parts[1]
        except Exception:
            rel = None

        if not topic:
            topic = _ask_text("主题", "无法从路径推断主题，请手动输入主题：")
            if topic is None:
                return

        if not rtype or rtype not in RESOURCE_TYPES:
            rtype = _ask_item("类型", "请选择类型：", RESOURCE_TYPES)
            if rtype is None:
                return

        # 版本：优先从文件名猜（如 v1/v2），否则默认 v1
        version = "v1"
        m = re.search(r"\bv\d+\b", self._current_path.stem, flags=re.IGNORECASE)
        if m:
            version = m.group(0).lower()

        submission_id = datetime.now().strftime("%Y%m%d-%H%M%S-%f")

        inbox_dir = workspace_root / "_INBOX" / vendor / topic / rtype
        inbox_dir.mkdir(parents=True, exist_ok=True)

        dest_name = f"{submission_id}_{version}_{self._current_path.name}"
        dest_path = inbox_dir / dest_name

        try:
            shutil.copy2(self._current_path, dest_path)
        except Exception as e:
            QMessageBox.warning(self, "提交失败", f"复制文件失败：\n{e}")
            return

        meta = {
            "submission_id": submission_id,
            "vendor": vendor,
            "topic": topic,
            "rtype": rtype,
            "version": version,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "source_path": str(self._current_path),
            "source_rel": str(rel) if rel is not None else "",
            "submit_path": str(dest_path),
            "submit_rel": str(dest_path.relative_to(workspace_root)),
            "status": "submitted",
        }

        meta_path = inbox_dir / f"{submission_id}_{version}.json"
        try:
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(meta, f, indent=2, ensure_ascii=False)
        except Exception as e:
            # 文件已提交成功，元数据写失败只提示
            QMessageBox.warning(self, "提交完成（元数据写入失败）", f"文件已复制到收件箱，但写入元数据失败：\n{e}")
            return

        QMessageBox.information(self, "提交成功", f"已提交到收件箱：\n{meta['submit_rel']}")
        self._set_info("已提交到收件箱")
        QTimer.singleShot(1500, self._update_ui)
    
    def _open_in_photoshop(self):
        """用 Photoshop 打开当前图片"""
        if not self._current_path or not self._current_path.exists():
            return
        
        from config import ps_config
        
        # 获取 PS 路径（自动检测或已保存的）
        ps_exe = ps_config.get_ps_path()
        
        if ps_exe and os.path.exists(ps_exe):
            try:
                subprocess.Popen([ps_exe, str(self._current_path)])
                self._set_info("已用 Photoshop 打开")
                QTimer.singleShot(1500, self._update_ui)
            except Exception as e:
                QMessageBox.warning(self, "打开失败", f"无法启动 Photoshop：\n{e}")
        else:
            # 未找到，弹窗让用户手动选择
            self._select_photoshop_path()
    
    def _open_feedback_editor(self):
        """打开反馈标注编辑器"""
        if not self._pixmap or self._pixmap.isNull():
            return
        
        try:
            from screenshot import EditorWindow
        except ImportError:
            QMessageBox.information(self, "提示", "标注编辑器仅在 Artco 主程序中可用。")
            return
        
        # 为编辑器创建副本，并设置正确的 devicePixelRatio
        # 避免从文件加载的图片（dpr=1）在高 DPI 屏幕上显示过大
        pixmap_for_editor = self._pixmap.copy()
        screen = QGuiApplication.primaryScreen()
        if screen:
            pixmap_for_editor.setDevicePixelRatio(screen.devicePixelRatio())
        
        # 创建编辑器窗口
        editor = EditorWindow(pixmap_for_editor)
        editor.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        editor.show()
        
        # 保存到全局列表防止被回收
        app = QApplication.instance()
        if not hasattr(app, '_editor_windows'):
            app._editor_windows = []
        app._editor_windows.append(editor)
        
        def on_editor_closed():
            if editor in app._editor_windows:
                app._editor_windows.remove(editor)
        
        editor.destroyed.connect(on_editor_closed)
    
    def _select_photoshop_path(self):
        """让用户手动选择 Photoshop 路径"""
        from config import ps_config
        
        reply = QMessageBox.question(
            self, "未找到 Photoshop",
            "未能自动检测到 Photoshop 安装路径。\n\n是否手动选择 Photoshop.exe 文件？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            file_path, _ = QFileDialog.getOpenFileName(
                self,
                "选择 Photoshop.exe",
                r"C:\Program Files\Adobe",
                "可执行文件 (Photoshop.exe);;所有文件 (*.*)"
            )
            
            if file_path and os.path.exists(file_path):
                # 保存路径
                ps_config.set_ps_path(file_path)
                
                # 打开图片
                try:
                    subprocess.Popen([file_path, str(self._current_path)])
                    self._set_info("已用 Photoshop 打开")
                    QTimer.singleShot(1500, self._update_ui)
                except Exception as e:
                    QMessageBox.warning(self, "打开失败", f"无法启动 Photoshop：\n{e}")
    
    def wheelEvent(self, event: QWheelEvent):
        if not self._pixmap:
            return
        
        delta = event.angleDelta().y()
        if delta > 0:
            factor = 1.25
        else:
            factor = 1 / 1.25
        
        # 计算目标缩放（基于当前目标，支持连续滚动叠加）
        new_target = self._target_scale * factor
        new_target = max(self._min_scale, min(self._max_scale, new_target))
        
        if new_target != self._target_scale:
            self._target_scale = new_target
            self._zoom_center = event.position().toPoint()
            
            # 启动平滑动画
            if not self._zoom_timer.isActive():
                self._zoom_timer.start()
    
    def _animate_zoom(self):
        """平滑缩放动画 - 每帧插值"""
        # 缓动系数：越大越快，0.15-0.25 比较平滑
        ease = 0.18
        
        diff = self._target_scale - self._scale
        
        # 接近目标时直接到位
        if abs(diff) < 0.001:
            self._scale = self._target_scale
            self._zoom_timer.stop()
            # 最后一帧用高质量渲染
            self.canvas.set_scale(self._scale, fast_mode=False)
            self.bottom_toolbar.set_scale(self._scale)
            return
        
        # 计算这一帧的缩放比例
        old_scale = self._scale
        self._scale += diff * ease
        
        # 以鼠标位置为中心调整偏移
        canvas_center = QPoint(self.canvas.width() // 2, self.canvas.height() // 2)
        old_offset = self.canvas.get_offset()
        scale_ratio = self._scale / old_scale
        
        rel_x = self._zoom_center.x() - canvas_center.x() - old_offset.x()
        rel_y = self._zoom_center.y() - canvas_center.y() - old_offset.y()
        
        new_offset_x = old_offset.x() - rel_x * (scale_ratio - 1)
        new_offset_y = old_offset.y() - rel_y * (scale_ratio - 1)
        
        # 动画中使用快速模式
        self.canvas.set_scale(self._scale, fast_mode=True)
        self.canvas.set_offset(QPoint(int(new_offset_x), int(new_offset_y)))
        self.bottom_toolbar.set_scale(self._scale)
    
    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        modifiers = event.modifiers()
        
        if key == Qt.Key.Key_Escape:
            self.close()
        elif key == Qt.Key.Key_O and modifiers & Qt.KeyboardModifier.ControlModifier:
            self._open_file_dialog()
        elif key == Qt.Key.Key_Left:
            self._prev_image()
        elif key == Qt.Key.Key_Right:
            self._next_image()
        elif key == Qt.Key.Key_C and modifiers & Qt.KeyboardModifier.ControlModifier:
            self._copy_image()
        elif key == Qt.Key.Key_D and modifiers & Qt.KeyboardModifier.ControlModifier:
            self._assign_to_workspace()
        elif key == Qt.Key.Key_0 and modifiers & Qt.KeyboardModifier.ControlModifier:
            self._fit_image()
        elif key == Qt.Key.Key_1 and modifiers & Qt.KeyboardModifier.ControlModifier:
            self._actual_size()
        elif key == Qt.Key.Key_E and modifiers & Qt.KeyboardModifier.ControlModifier:
            self._open_in_explorer()
        elif key == Qt.Key.Key_P and modifiers & Qt.KeyboardModifier.ControlModifier:
            self._open_in_photoshop()
        elif key == Qt.Key.Key_B and modifiers & Qt.KeyboardModifier.ControlModifier:
            # Ctrl+B 切换侧栏
            self.sidebar.toggle_collapse()
        elif key == Qt.Key.Key_R:
            if modifiers & Qt.KeyboardModifier.ShiftModifier:
                self._rotate_ccw()
            else:
                self._rotate_cw()
        elif key == Qt.Key.Key_Delete:
            self._delete_current()
        elif key == Qt.Key.Key_F:
            self._open_feedback_editor()
        elif key == Qt.Key.Key_Plus or key == Qt.Key.Key_Equal:
            self._zoom_in()
        elif key == Qt.Key.Key_Minus:
            self._zoom_out()
        else:
            super().keyPressEvent(event)
    
    def closeEvent(self, event):
        if self._movie:
            self._movie.stop()
        
        # 停止所有加载线程
        if self._loader_thread and self._loader_thread.isRunning():
            self._loader_thread.stop()
            self._loader_thread.wait(200)
        
        if self._psd_loader_thread and self._psd_loader_thread.isRunning():
            self._psd_loader_thread.stop()
            self._psd_loader_thread.wait(200)
        
        # 停止所有预加载线程
        for t in self._preload_threads:
            if t.isRunning():
                t.stop()
                t.wait(100)
        self._preload_threads.clear()
        
        self.closed.emit()
        super().closeEvent(event)


# ==================== 独立测试入口 ====================

def main():
    """独立运行测试"""
    import sys
    
    app = QApplication(sys.argv)
    
    if len(sys.argv) > 1:
        image_path = sys.argv[1]
    else:
        from PySide6.QtWidgets import QFileDialog
        image_path, _ = QFileDialog.getOpenFileName(
            None, "选择图片", "",
            "Images (*.png *.jpg *.jpeg *.gif *.bmp *.webp *.psd);;All Files (*)"
        )
        if not image_path:
            print("未选择图片")
            return
    
    viewer = ImageViewer(image_path)
    viewer.closed.connect(app.quit)
    viewer.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
