"""
图片浏览器模块 —— 纯粹的看图工具

只做一件事：把图片显示出来，能缩放、能拖动、能拖放打开。
删除了原有的编辑/管理工作流（缩放栏按钮、旋转、PS、反馈标注、
收件箱、工作区分配、缩略图侧栏等），这些属于标注类工具的职责。

保留的核心能力：
- 异步加载 + LRU 缓存（应对上万像素大图）
- 渐进式加载：先出低清预览，再换高清
- 滚轮缩放（以光标为中心）、拖动平移、双击适应窗口
- 拖放打开、GIF 动图、PSD 首帧
"""

from pathlib import Path
from typing import Optional
from collections import OrderedDict

from PySide6.QtWidgets import QWidget, QApplication, QLabel, QPushButton
from PySide6.QtCore import Qt, Signal, QPoint, QSize, QTimer, QRectF, QThread
from PySide6.QtGui import (
    QPixmap, QPainter, QColor, QGuiApplication, QWheelEvent,
    QKeyEvent, QMovie, QImageReader, QPen,
)

import qtawesome as qta

from ui.theme import (
    BG_ACTIVE, BG_ELEVATED, BG_HOVER, BG_SECONDARY,
    BORDER_STRONG, BORDER_SUBTLE, TEXT_SECONDARY,
    TEXT_TERTIARY, RADIUS_MD, RADIUS_SM, SPACING_SM,
)

# 缩放范围
MIN_SCALE = 0.05
MAX_SCALE = 32.0
# 适应窗口时的留白
FIT_MARGIN = 24
# 超大图降采样阈值（超过此尺寸按屏幕 2 倍缩放读取，避免内存爆炸）
HUGE_IMAGE_DIM = 4000
# 窗口默认尺寸与最小尺寸（打开时按图片尺寸自适应，不超过屏幕的 88%）
DEFAULT_WINDOW_W = 900
DEFAULT_WINDOW_H = 640
MIN_WINDOW_W = 320
MIN_WINDOW_H = 240
MAX_SCREEN_RATIO = 0.88


class ImageCache:
    """LRU 图片缓存池 —— 避免重复解码大图"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_cache()
        return cls._instance

    def _init_cache(self):
        self._cache: OrderedDict[str, QPixmap] = OrderedDict()
        self._preview_cache: OrderedDict[str, QPixmap] = OrderedDict()
        # 阈值下调：用户常处理上万像素的大图，单张全尺寸解码即数百 MB。
        # 原先 20 张 / 500MB 的预算对超大图过于宽松，容易让缓存本身成为内存大头。
        # 预览图（已缩放，单张很小）可保留较大数量，成本低且能显著提升滚动体验。
        self._max_size = 6
        self._max_preview_size = 50
        self._max_memory_mb = 150
        self._current_memory = 0

    @staticmethod
    def _estimate_memory(pixmap: QPixmap) -> int:
        if pixmap.isNull():
            return 0
        return pixmap.width() * pixmap.height() * 4  # RGBA

    def get(self, path: str) -> Optional[QPixmap]:
        if path in self._cache:
            self._cache.move_to_end(path)
            return self._cache[path]
        return None

    def get_preview(self, path: str) -> Optional[QPixmap]:
        if path in self._preview_cache:
            self._preview_cache.move_to_end(path)
            return self._preview_cache[path]
        return None

    def put(self, path: str, pixmap: QPixmap):
        if pixmap.isNull():
            return
        mem = self._estimate_memory(pixmap)
        while (len(self._cache) >= self._max_size or
               self._current_memory + mem > self._max_memory_mb * 1024 * 1024):
            if not self._cache:
                break
            _, old = self._cache.popitem(last=False)
            self._current_memory -= self._estimate_memory(old)
        self._cache[path] = pixmap
        self._current_memory += mem

    def put_preview(self, path: str, pixmap: QPixmap):
        if pixmap.isNull():
            return
        if len(self._preview_cache) >= self._max_preview_size:
            self._preview_cache.popitem(last=False)
        self._preview_cache[path] = pixmap

    def clear(self):
        self._cache.clear()
        self._preview_cache.clear()
        self._current_memory = 0


image_cache = ImageCache()


class ImageLoaderThread(QThread):
    """异步加载大图 —— 渐进式：先预览后高清"""

    loaded = Signal(QPixmap, str, bool)  # 图片, 错误信息, 是否预览

    def __init__(self, path: str, load_preview_first: bool = True):
        super().__init__()
        self.path = path
        self.load_preview_first = load_preview_first
        self._is_running = True

    def stop(self):
        self._is_running = False

    def run(self):
        try:
            cached = image_cache.get(self.path)
            if cached:
                self.loaded.emit(cached, "", False)
                return

            reader = QImageReader(self.path)
            reader.setAutoTransform(True)
            size = reader.size()
            if not size.isValid():
                self.loaded.emit(QPixmap(), f"无法读取图片: {self.path}", False)
                return

            # 步骤 1：大图先给一张低清预览，避免白屏等待
            if self.load_preview_first and (size.width() > 1200 or size.height() > 1200):
                preview = image_cache.get_preview(self.path)
                if preview:
                    self.loaded.emit(preview, "", True)
                else:
                    pr = QImageReader(self.path)
                    pr.setAutoTransform(True)
                    s = min(400 / size.width(), 400 / size.height(), 1.0)
                    pr.setScaledSize(QSize(int(size.width() * s), int(size.height() * s)))
                    img = pr.read()
                    if not img.isNull():
                        pm = QPixmap.fromImage(img)
                        image_cache.put_preview(self.path, pm)
                        self.loaded.emit(pm, "", True)

            if not self._is_running:
                return

            # 步骤 2：高清图（超大图按屏幕尺寸降采样）
            full = QImageReader(self.path)
            full.setAutoTransform(True)
            if size.width() > HUGE_IMAGE_DIM or size.height() > HUGE_IMAGE_DIM:
                screen = QGuiApplication.primaryScreen().geometry()
                max_dim = max(screen.width(), screen.height()) * 2
                scale = min(max_dim / size.width(), max_dim / size.height(), 1.0)
                if scale < 1.0:
                    full.setScaledSize(QSize(int(size.width() * scale), int(size.height() * scale)))

            if not self._is_running:
                return

            qimage = full.read()
            if qimage.isNull():
                self.loaded.emit(QPixmap(), f"图片格式不支持或已损坏: {self.path}", False)
                return

            pixmap = QPixmap.fromImage(qimage)
            image_cache.put(self.path, pixmap)
            self.loaded.emit(pixmap, "", False)

        except Exception as e:
            self.loaded.emit(QPixmap(), f"加载失败: {e}", False)


class ImageCanvas(QWidget):
    """图片画布 —— 只负责把图画出来"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap: Optional[QPixmap] = None
        self._movie: Optional[QMovie] = None
        self._scale = 1.0
        self._offset = QPoint(0, 0)
        self._dragging = False
        self._drag_start = QPoint()
        self._drag_offset = QPoint()

        self.setMouseTracking(True)
        self.setAcceptDrops(True)

    # ── 数据 ──
    def set_pixmap(self, pixmap: QPixmap):
        self._pixmap = pixmap
        self.update()

    def set_movie(self, movie: Optional[QMovie]):
        if self._movie:
            self._movie.stop()
            self._movie.deleteLater()
        self._movie = movie
        if movie:
            movie.start()

    def pixmap(self) -> Optional[QPixmap]:
        return self._pixmap

    def set_scale(self, scale: float):
        if scale != self._scale:
            self._scale = scale
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

    # ── 绘制 ──
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(BG_SECONDARY))

        pm = self._pixmap
        if not pm or pm.isNull():
            self._draw_empty_state(painter)
            return

        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        img_w = int(pm.width() * self._scale)
        img_h = int(pm.height() * self._scale)
        x = (self.width() - img_w) // 2 + self._offset.x()
        y = (self.height() - img_h) // 2 + self._offset.y()
        painter.drawPixmap(
            QRectF(x, y, img_w, img_h), pm,
            QRectF(0, 0, pm.width(), pm.height()))

    def _draw_empty_state(self, painter: QPainter):
        center = self.rect().center()
        painter.setPen(QPen(QColor(BORDER_STRONG), 1.5, Qt.PenStyle.DashLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        box_rect = QRectF(center.x() - 140, center.y() - 80, 280, 160)
        painter.drawRoundedRect(box_rect, RADIUS_MD, RADIUS_MD)

        icon = qta.icon('mdi6.image-outline', color=TEXT_TERTIARY)
        painter.drawPixmap(center.x() - 20, center.y() - 60, icon.pixmap(QSize(40, 40)))

        font = painter.font()
        painter.setPen(QColor(TEXT_SECONDARY))
        font.setPointSize(13)
        painter.setFont(font)
        painter.drawText(QRectF(center.x() - 140, center.y() - 5, 280, 24),
                         Qt.AlignmentFlag.AlignCenter, "拖放图片到此处")

        painter.setPen(QColor(TEXT_TERTIARY))
        font.setPointSize(11)
        painter.setFont(font)
        painter.drawText(QRectF(center.x() - 140, center.y() + 20, 280, 20),
                         Qt.AlignmentFlag.AlignCenter, "或按 Ctrl+O 打开文件")

    # ── 拖动平移（转发给父窗口处理，保持单一职责）──
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_start = event.position().toPoint()
            self._drag_offset = self._offset
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging:
            delta = event.position().toPoint() - self._drag_start
            self.set_offset(self._drag_offset + delta)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._dragging = False
        self.setCursor(Qt.CursorShape.ArrowCursor)
        super().mouseReleaseEvent(event)


class ImageViewer(QWidget):
    """纯看图窗口

    可传入一组图片路径以支持上一张/下一张翻页。
    窗口会按图片实际尺寸自适应，不会一打开就是个大面板。
    """

    def __init__(self, image_path: str = None, parent=None,
                 file_list: Optional[list] = None):
        super().__init__(parent)

        self._pixmap: Optional[QPixmap] = None
        self._movie: Optional[QMovie] = None
        self._current_path: Optional[Path] = None
        self._file_list: list = []
        self._index = -1
        self._nav_buttons: list = []
        # 首次加载图片时按图片尺寸调整窗口；之后翻页不再改尺寸
        self._auto_size_pending = True

        self._scale = 1.0
        self._target_scale = 1.0
        self._zoom_center = QPoint()

        self._loader_thread: Optional[ImageLoaderThread] = None

        self._zoom_timer = QTimer(self)
        self._zoom_timer.setInterval(16)  # ~60fps
        self._zoom_timer.timeout.connect(self._animate_zoom)

        self._init_window()
        self._init_ui()

        if file_list:
            self.set_file_list(file_list, image_path)
        elif image_path:
            self.load_image(image_path)

    # ── 窗口 ──
    def _init_window(self):
        self.setWindowTitle("Artco Viewer")
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(MIN_WINDOW_W, MIN_WINDOW_H)
        self.setStyleSheet(f"background: {BG_SECONDARY};")

        # 默认尺寸适中，真正显示图片时再按图片尺寸自适应
        screen = QGuiApplication.primaryScreen().availableGeometry()
        w, h = DEFAULT_WINDOW_W, DEFAULT_WINDOW_H
        w = min(w, int(screen.width() * 0.9))
        h = min(h, int(screen.height() * 0.9))
        self.setGeometry(
            screen.x() + (screen.width() - w) // 2,
            screen.y() + (screen.height() - h) // 2, w, h)

    def _init_ui(self):
        self.canvas = ImageCanvas(self)
        self.canvas.setGeometry(0, 0, self.width(), self.height())

        # 左下角信息条：尺寸 / 缩放 / 文件名
        self.label_info = QLabel(self)
        self.label_info.setStyleSheet(f"""
            QLabel {{
                color: {TEXT_TERTIARY};
                font-size: 11px;
                background: {BG_ELEVATED};
                padding: {SPACING_SM - 2}px 8px;
                border-radius: {RADIUS_SM}px;
                border: 1px solid {BORDER_SUBTLE};
            }}
        """)
        self.label_info.hide()

        # 左右翻页按钮（仅在多于一张图片时出现）
        self._nav_buttons = []
        for icon_name, cb in (('mdi6.chevron-left', self.prev_image),
                              ('mdi6.chevron-right', self.next_image)):
            btn = self._make_nav_button(icon_name, cb)
            self._nav_buttons.append(btn)
        self._update_nav_visibility()

    def _make_nav_button(self, icon_name: str, callback) -> 'QPushButton':
        btn = QPushButton(self)
        btn.setIcon(qta.icon(icon_name, color=TEXT_SECONDARY))
        btn.setIconSize(QSize(22, 22))
        btn.setFixedSize(36, 36)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {BG_ELEVATED};
                border: 1px solid {BORDER_SUBTLE};
                border-radius: 18px;
            }}
            QPushButton:hover {{ background: {BG_HOVER}; }}
            QPushButton:pressed {{ background: {BG_ACTIVE}; }}
        """)
        btn.clicked.connect(callback)
        btn.hide()
        return btn

    def _update_nav_visibility(self):
        """只有多图时才显示翻页按钮"""
        multi = len(self._file_list) > 1
        for btn in self._nav_buttons:
            btn.setVisible(multi)
        if multi:
            self._position_nav()

    # ── 文件列表与翻页 ──
    def set_file_list(self, paths, current: str = None):
        """设置图片列表；current 为初始显示的图片路径"""
        self._file_list = [str(p) for p in paths if p and Path(str(p)).exists()]
        if current:
            cur = str(current)
            self._index = self._file_list.index(cur) if cur in self._file_list else -1
        elif self._file_list:
            self._index = 0
        else:
            self._index = -1
        self._update_nav_visibility()
        if self._index >= 0:
            self.load_image(self._file_list[self._index])
        elif current:
            self.load_image(str(current))

    def prev_image(self):
        self._step(-1)

    def next_image(self):
        self._step(1)

    def _step(self, delta: int):
        if len(self._file_list) < 2:
            return
        self._index = (self._index + delta) % len(self._file_list)
        self.load_image(self._file_list[self._index])

    def _position_nav(self):
        """翻页按钮垂直居中贴边"""
        y = (self.height() - 36) // 2
        if self._nav_buttons:
            self._nav_buttons[0].move(12, y)
            self._nav_buttons[1].move(self.width() - 36 - 12, y)

    # ── 加载 ──
    def load_image(self, path: str):
        self._current_path = Path(path)
        if not self._current_path.exists():
            self.setWindowTitle("文件不存在 - Artco Viewer")
            return

        self._stop_loading()
        self.setWindowTitle(f"{self._current_path.name} - Artco Viewer")

        # 缓存命中则直接显示
        cached = image_cache.get(str(self._current_path))
        if cached:
            self._apply_pixmap(cached)
            return

        preview = image_cache.get_preview(str(self._current_path))
        if preview:
            self._apply_pixmap(preview, fit=False)

        suffix = self._current_path.suffix.lower()
        if suffix == '.gif':
            self._load_gif(str(self._current_path))
        elif suffix == '.psd':
            self._load_psd(str(self._current_path))
        else:
            self._load_async(str(self._current_path))

    def _stop_loading(self):
        if self._movie:
            self._movie.stop()
            self._movie.deleteLater()
            self._movie = None
        if self._loader_thread and self._loader_thread.isRunning():
            self._loader_thread.stop()
            self._loader_thread.wait(100)

    def _load_async(self, path: str):
        self._loader_thread = ImageLoaderThread(path)
        self._loader_thread.loaded.connect(self._on_loaded)
        self._loader_thread.start()

    def _on_loaded(self, pixmap: QPixmap, error: str, is_preview: bool):
        if error:
            self.setWindowTitle(f"{error} - Artco Viewer")
            return
        if pixmap.isNull():
            return
        # 预览阶段不重置视图，等高清图到达再适应窗口
        self._apply_pixmap(pixmap, fit=not is_preview)

    def _load_gif(self, path: str):
        try:
            movie = QMovie(path)
            if not movie.isValid():
                return
            self._movie = movie
            self.canvas.set_movie(movie)
            movie.frameChanged.connect(self._on_gif_frame)
            movie.start()
            self._pixmap = movie.currentPixmap()
            self._fit_image()
            self._update_info()
        except Exception:
            pass

    def _on_gif_frame(self, _frame_no: int = 0):
        """GIF 每帧更新画布"""
        if not self._movie:
            return
        self.canvas.set_pixmap(self._movie.currentPixmap())

    def _load_psd(self, path: str):
        """PSD 只取合成后的首帧 —— 看图无需解析图层"""
        try:
            from psd_tools import PSDImage
            psd = PSDImage.open(path)
            img = psd.composite()
            if img is None:
                self.setWindowTitle(f"无法读取 PSD: {path}")
                return
            from PIL.ImageQt import ImageQt
            qimage = ImageQt(img)
            pixmap = QPixmap.fromImage(qimage.copy())
            image_cache.put(path, pixmap)
            self._apply_pixmap(pixmap)
        except ImportError:
            self.setWindowTitle("未安装 psd-tools，无法查看 PSD")
        except Exception as e:
            self.setWindowTitle(f"PSD 加载失败: {e}")

    def _apply_pixmap(self, pixmap: QPixmap, fit: bool = True):
        self._pixmap = pixmap
        self.canvas.set_pixmap(pixmap)
        if fit:
            self._fit_to_image()
        self._update_info()

    # ── 按图片尺寸自适应窗口 ──
    def _fit_to_image(self):
        """按图片实际尺寸调整窗口，再适应窗口缩放。

        小图不会撑出大面板；大图限制在屏幕 88% 以内。
        窗口已经显示过之后不再改动尺寸，避免翻页时窗口乱跳。
        """
        if not self._pixmap or self._pixmap.isNull():
            return
        if not self._auto_size_pending:
            self._fit_image()
            return

        self._auto_size_pending = False
        screen = QGuiApplication.primaryScreen().availableGeometry()
        max_w = int(screen.width() * MAX_SCREEN_RATIO)
        max_h = int(screen.height() * MAX_SCREEN_RATIO)

        # 图片尺寸 + 留白 = 理想窗口尺寸，再夹到 [最小, 屏幕上限]
        w = min(max(self._pixmap.width() + FIT_MARGIN * 2, MIN_WINDOW_W), max_w)
        h = min(max(self._pixmap.height() + FIT_MARGIN * 2, MIN_WINDOW_H), max_h)

        frame_w = self.frameGeometry().width() - self.width()
        frame_h = self.frameGeometry().height() - self.height()
        w = min(w + frame_w, max_w)
        h = min(h + frame_h, max_h)

        self.resize(w, h)
        self._center_on_screen()
        self._fit_image()

    def _center_on_screen(self):
        screen = QGuiApplication.primaryScreen().availableGeometry()
        fg = self.frameGeometry()
        self.move(
            screen.x() + (screen.width() - fg.width()) // 2,
            screen.y() + (screen.height() - fg.height()) // 2)

    # ── 缩放 ──
    def _fit_image(self):
        if not self._pixmap or self._pixmap.isNull():
            return
        cw = self.canvas.width() - FIT_MARGIN * 2
        ch = self.canvas.height() - FIT_MARGIN * 2
        if cw <= 0 or ch <= 0:
            return
        s = min(cw / self._pixmap.width(), ch / self._pixmap.height(), 1.0)
        self._set_scale(s)
        self.canvas.reset_view()

    def _actual_size(self):
        self._set_scale(1.0)
        self.canvas.reset_view()

    def _set_scale(self, scale: float):
        self._scale = max(MIN_SCALE, min(MAX_SCALE, scale))
        self._target_scale = self._scale
        self.canvas.set_scale(self._scale)
        self._update_info()

    def _zoom_at(self, factor: float, center: QPoint):
        if not self._pixmap:
            return
        new_target = max(MIN_SCALE, min(MAX_SCALE, self._target_scale * factor))
        if new_target == self._target_scale:
            return
        self._zoom_center = center
        self._target_scale = new_target
        if not self._zoom_timer.isActive():
            self._zoom_timer.start()

    def _animate_zoom(self):
        """平滑插值到目标缩放，并以光标为中心保持锚点"""
        diff = self._target_scale - self._scale
        if abs(diff) < 0.001:
            self._scale = self._target_scale
            self._zoom_timer.stop()
            self.canvas.set_scale(self._scale)
            self._update_info()
            return

        old_scale = self._scale
        self._scale += diff * 0.18

        center = QPoint(self.canvas.width() // 2, self.canvas.height() // 2)
        old_offset = self.canvas.get_offset()
        ratio = self._scale / old_scale
        rel_x = self._zoom_center.x() - center.x() - old_offset.x()
        rel_y = self._zoom_center.y() - center.y() - old_offset.y()
        self.canvas.set_offset(QPoint(
            int(old_offset.x() - rel_x * (ratio - 1)),
            int(old_offset.y() - rel_y * (ratio - 1))))
        self.canvas.set_scale(self._scale)
        self._update_info()

    # ── 信息条 ──
    def _update_info(self):
        if not self._pixmap or self._pixmap.isNull() or not self._current_path:
            self.label_info.hide()
            return
        w, h = self._pixmap.width(), self._pixmap.height()
        page = ""
        if len(self._file_list) > 1:
            page = f"    {self._index + 1}/{len(self._file_list)}"
        self.label_info.setText(
            f"{self._current_path.name}    {w} × {h}    {int(self._scale * 100)}%{page}")
        self.label_info.adjustSize()
        self.label_info.show()
        self._position_info()

    def _position_info(self):
        self.label_info.move(12, self.height() - self.label_info.height() - 12)

    # ── 事件 ──
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.canvas.setGeometry(0, 0, self.width(), self.height())
        self._position_info()
        self._position_nav()

    def wheelEvent(self, event: QWheelEvent):
        if not self._pixmap:
            return
        delta = event.angleDelta().y()
        factor = 1.25 if delta > 0 else 1 / 1.25
        self._zoom_at(factor, event.position().toPoint())

    def mouseDoubleClickEvent(self, event):
        """双击在 适应窗口 / 原始大小 间切换"""
        if abs(self._scale - 1.0) < 0.01:
            self._fit_image()
        else:
            self._actual_size()
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        mod = event.modifiers()
        ctrl = mod & Qt.KeyboardModifier.ControlModifier

        if key == Qt.Key.Key_Escape:
            self.close()
        elif key == Qt.Key.Key_Left:
            self.prev_image()
        elif key == Qt.Key.Key_Right:
            self.next_image()
        elif key == Qt.Key.Key_Plus or key == Qt.Key.Key_Equal:
            self._zoom_at(1.25, QPoint(self.width() // 2, self.height() // 2))
        elif key == Qt.Key.Key_Minus:
            self._zoom_at(1 / 1.25, QPoint(self.width() // 2, self.height() // 2))
        elif key == Qt.Key.Key_0 and ctrl:
            self._fit_image()
        elif key == Qt.Key.Key_1 and ctrl:
            self._actual_size()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        self._stop_loading()
        super().closeEvent(event)


def _open_viewer(image_path: str):
    app = QApplication.instance() or QApplication([])
    viewer = ImageViewer(image_path)
    viewer.show()
    return app, viewer
