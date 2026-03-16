"""
截图模块 - 屏幕贴图窗口
"""

from PySide6.QtWidgets import QWidget, QMenu, QFileDialog, QApplication
from PySide6.QtCore import Qt, QRect, QPoint, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
import qtawesome as qta


class PinWindow(QWidget):
    """屏幕贴图窗口 - 类似 Snipaste 的 Pin 功能"""
    
    # 请求编辑信号：发送当前图片的 pixmap
    edit_requested = Signal(QPixmap)
    
    def __init__(self, pixmap: QPixmap, parent=None):
        super().__init__(parent)
        
        self._original_pixmap = pixmap
        self._scale = 1.0
        self._min_scale = 0.1
        self._max_scale = 5.0
        self._opacity = 1.0
        
        # 缩略图模式（类似 Setuna）
        self._thumbnail_mode = False
        self._thumbnail_size = 64  # 缩略图方块大小
        self._saved_scale = 1.0    # 保存进入缩略图前的缩放比例
        self._saved_pos = None     # 保存进入缩略图前的位置
        
        # 获取原始 devicePixelRatio
        self._device_pixel_ratio = pixmap.devicePixelRatio()
        
        # 计算逻辑尺寸（基础尺寸）
        self._base_width = int(pixmap.width() / self._device_pixel_ratio)
        self._base_height = int(pixmap.height() / self._device_pixel_ratio)
        
        # 拖拽状态
        self._dragging = False
        self._drag_start_pos = QPoint()
        
        # 阴影边距
        self._shadow_margin = 8
        
        self._init_window()
        self._update_size()
    
    def _init_window(self):
        """初始化窗口属性"""
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        # 禁用窗口内容在调整大小时的自动更新，避免闪烁
        self.setAttribute(Qt.WidgetAttribute.WA_StaticContents)
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
    
    def _update_size(self):
        """根据缩放更新窗口大小"""
        if self._thumbnail_mode:
            # 缩略图模式：固定大小的小方块
            total_size = self._thumbnail_size + self._shadow_margin * 2
            self.setFixedSize(total_size, total_size)
        else:
            # 正常模式
            scaled_width = int(self._base_width * self._scale)
            scaled_height = int(self._base_height * self._scale)
            
            # 窗口大小 = 缩放后图片大小 + 阴影边距
            total_width = scaled_width + self._shadow_margin * 2
            total_height = scaled_height + self._shadow_margin * 2
            
            self.setFixedSize(total_width, total_height)
        
        # 强制同步重绘，避免异步导致的闪烁
        self.repaint()
    
    def _get_shadow_params(self, size: int):
        """根据尺寸动态计算阴影参数，小尺寸时阴影更柔和"""
        # 基于尺寸的缩放因子 (64px → 0.5, 200px+ → 1.0)
        scale = min(1.0, max(0.4, size / 200))
        
        # 动态阴影层：offset 和 alpha 随尺寸缩放
        layers = [
            (int(6 * scale), int(20 * scale)),   # 外层：更大范围，更淡
            (int(3 * scale), int(35 * scale)),   # 中层
            (int(1 * scale), int(15 * scale)),   # 内层：贴近边缘，柔和过渡
        ]
        # 过滤掉 offset 为 0 的层
        return [(o, a) for o, a in layers if o > 0]
    
    def paintEvent(self, event):
        """绘制图片和阴影"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        
        if self._thumbnail_mode:
            # 缩略图模式绘制
            img_rect = QRect(
                self._shadow_margin,
                self._shadow_margin,
                self._thumbnail_size,
                self._thumbnail_size
            )
            
            # 动态阴影
            shadow_layers = self._get_shadow_params(self._thumbnail_size)
            corner_radius = 6
            for offset, alpha in shadow_layers:
                shadow_rect = img_rect.adjusted(-offset, -offset, offset, offset)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(0, 0, 0, alpha))
                painter.drawRoundedRect(shadow_rect, corner_radius, corner_radius)
            
            # 设置透明度
            painter.setOpacity(self._opacity)
            
            # 绘制缩略图（裁剪为正方形并缩放）
            # 从原图中心裁剪正方形
            src_size = min(self._original_pixmap.width(), self._original_pixmap.height())
            src_x = (self._original_pixmap.width() - src_size) // 2
            src_y = (self._original_pixmap.height() - src_size) // 2
            src_rect = QRect(src_x, src_y, src_size, src_size)
            
            painter.drawPixmap(img_rect, self._original_pixmap, src_rect)
            
            # 绘制圆角边框
            painter.setOpacity(1.0)
            painter.setPen(QPen(QColor(100, 100, 100, 200), 1.5))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(img_rect, corner_radius, corner_radius)
        else:
            # 正常模式绘制
            scaled_width = int(self._base_width * self._scale)
            scaled_height = int(self._base_height * self._scale)
            
            img_rect = QRect(
                self._shadow_margin,
                self._shadow_margin,
                scaled_width,
                scaled_height
            )
            
            # 动态阴影：基于图片较小边计算
            min_side = min(scaled_width, scaled_height)
            shadow_layers = self._get_shadow_params(min_side)
            corner_radius = max(2, int(4 * min(1.0, min_side / 200)))
            
            for offset, alpha in shadow_layers:
                shadow_rect = img_rect.adjusted(-offset, -offset, offset, offset)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(0, 0, 0, alpha))
                painter.drawRoundedRect(shadow_rect, corner_radius, corner_radius)
            
            # 设置透明度
            painter.setOpacity(self._opacity)
            
            # 直接绘制原图到目标区域（让 Qt/GPU 处理缩放）
            painter.drawPixmap(img_rect, self._original_pixmap)
            
            # 绘制边框
            painter.setOpacity(1.0)
            painter.setPen(QPen(QColor(200, 200, 200, 150), 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(img_rect)
    
    def mousePressEvent(self, event):
        """鼠标按下 - 开始拖拽"""
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_start_pos = event.globalPosition().toPoint() - self.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        event.accept()
    
    def mouseMoveEvent(self, event):
        """鼠标移动 - 拖拽窗口"""
        if self._dragging:
            new_pos = event.globalPosition().toPoint() - self._drag_start_pos
            self.move(new_pos)
        event.accept()
    
    def mouseReleaseEvent(self, event):
        """鼠标释放 - 结束拖拽"""
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            self.setCursor(Qt.CursorShape.SizeAllCursor)
        event.accept()
    
    def mouseDoubleClickEvent(self, event):
        """双击 - 切换缩略图模式（类似 Setuna）"""
        if event.button() == Qt.MouseButton.LeftButton:
            if self._thumbnail_mode:
                # 从缩略图模式恢复
                self._thumbnail_mode = False
                self._scale = self._saved_scale
                
                # 计算恢复后的位置，使窗口中心保持不变
                thumb_center = self.geometry().center()
                self._update_size()
                new_geo = self.geometry()
                new_geo.moveCenter(thumb_center)
                self.move(new_geo.topLeft())
            else:
                # 进入缩略图模式
                self._saved_scale = self._scale
                self._thumbnail_mode = True
                
                # 计算缩略图位置，使窗口中心保持不变
                old_center = self.geometry().center()
                self._update_size()
                new_geo = self.geometry()
                new_geo.moveCenter(old_center)
                self.move(new_geo.topLeft())
        event.accept()
    
    def wheelEvent(self, event):
        """滚轮 - 以鼠标为中心缩放（缩略图模式下禁用）"""
        # 缩略图模式下不允许滚轮缩放
        if self._thumbnail_mode:
            event.accept()
            return
        
        # 获取鼠标在窗口中的位置
        mouse_pos = event.position()
        
        # 当前缩放后的图片尺寸
        current_width = int(self._base_width * self._scale)
        current_height = int(self._base_height * self._scale)
        
        # 计算鼠标相对于图片的位置比例
        img_x = (mouse_pos.x() - self._shadow_margin) / current_width
        img_y = (mouse_pos.y() - self._shadow_margin) / current_height
        
        # 限制在 0-1 范围内
        img_x = max(0, min(1, img_x))
        img_y = max(0, min(1, img_y))
        
        # 计算新的缩放比例
        delta = event.angleDelta().y()
        scale_factor = 1.1 if delta > 0 else 0.9
        new_scale = self._scale * scale_factor
        new_scale = max(self._min_scale, min(self._max_scale, new_scale))
        
        if abs(new_scale - self._scale) < 0.001:
            return
        
        # 记录旧的窗口位置和大小
        old_pos = self.pos()
        old_width = current_width
        old_height = current_height
        
        # 更新缩放
        self._scale = new_scale
        self._update_size()
        
        # 计算新的图片大小
        new_width = int(self._base_width * self._scale)
        new_height = int(self._base_height * self._scale)
        
        # 计算位置偏移，使鼠标指向的图片位置保持不变
        offset_x = int((old_width - new_width) * img_x)
        offset_y = int((old_height - new_height) * img_y)
        
        self.move(old_pos.x() + offset_x, old_pos.y() + offset_y)
        event.accept()
    
    def enterEvent(self, event):
        """鼠标进入 - 自动获取焦点"""
        self.setFocus()
        super().enterEvent(event)
    
    def leaveEvent(self, event):
        """鼠标离开 - 清除焦点"""
        self.clearFocus()
        super().leaveEvent(event)
    
    def keyPressEvent(self, event):
        """键盘事件 - ESC 关闭, Ctrl+C 复制, Ctrl+X 剪切, E 编辑"""
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        elif event.key() == Qt.Key.Key_C and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            self._copy_to_clipboard()
        elif event.key() == Qt.Key.Key_X and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            self._cut_to_clipboard()
        elif event.key() == Qt.Key.Key_E:
            self._request_edit()
        else:
            super().keyPressEvent(event)
    
    def _copy_to_clipboard(self):
        """复制图片到剪贴板"""
        clipboard = QApplication.clipboard()
        clipboard.setPixmap(self._original_pixmap)
    
    def _cut_to_clipboard(self):
        """剪切图片到剪贴板（复制后关闭）"""
        clipboard = QApplication.clipboard()
        clipboard.setPixmap(self._original_pixmap)
        self.close()
    
    def _request_edit(self):
        """请求编辑图片"""
        self.edit_requested.emit(self._original_pixmap)
    
    def contextMenuEvent(self, event):
        """右键菜单"""
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #ffffff;
                border: 1px solid #d0d0d0;
                border-radius: 6px;
                padding: 4px 0;
            }
            QMenu::item {
                padding: 6px 12px 6px 8px;
                margin: 0 4px;
                border-radius: 4px;
                font-size: 13px;
                color: #1d1d1f;
            }
            QMenu::item:selected {
                background-color: #007aff;
                color: #fff;
            }
            QMenu::item:disabled {
                color: #999;
            }
            QMenu::icon {
                padding-left: 4px;
                padding-right: 2px;
            }
            QMenu::separator {
                height: 1px;
                background-color: #e5e5e5;
                margin: 4px 8px;
            }
        """)
        
        # 透明度子菜单
        opacity_menu = menu.addMenu(qta.icon('mdi6.opacity', color='#555'), "透明度")
        opacity_menu.setStyleSheet(menu.styleSheet())
        opacity_actions = [
            ("100%", 1.0),
            ("80%", 0.8),
            ("50%", 0.5),
            ("30%", 0.3),
        ]
        for text, value in opacity_actions:
            action = opacity_menu.addAction(text)
            action.setCheckable(True)
            action.setChecked(abs(self._opacity - value) < 0.01)
            action.triggered.connect(lambda checked, v=value: self._set_opacity(v))
        
        # 复制 & 剪切 & 编辑
        menu.addSeparator()
        copy_action = menu.addAction(qta.icon('mdi6.content-copy', color='#555'), "复制")
        copy_action.triggered.connect(self._copy_to_clipboard)
        
        cut_action = menu.addAction(qta.icon('mdi6.content-cut', color='#555'), "剪切")
        cut_action.triggered.connect(self._cut_to_clipboard)
        
        edit_action = menu.addAction(qta.icon('mdi6.pencil-outline', color='#555'), "编辑")
        edit_action.triggered.connect(self._request_edit)
        
        # 缩略图 & 还原
        menu.addSeparator()
        if not self._thumbnail_mode:
            thumbnail_action = menu.addAction(qta.icon('mdi6.image-filter-center-focus', color='#555'), "缩略图模式")
        else:
            thumbnail_action = menu.addAction(qta.icon('mdi6.image-filter-center-focus', color='#555'), "退出缩略图")
        thumbnail_action.triggered.connect(self._toggle_thumbnail_mode)
        
        reset_action = menu.addAction(qta.icon('mdi6.backup-restore', color='#555'), "还原大小")
        reset_action.setEnabled(not self._thumbnail_mode)
        reset_action.triggered.connect(self._reset_scale)
        
        # 保存
        menu.addSeparator()
        save_action = menu.addAction(qta.icon('mdi6.content-save-outline', color='#555'), "另存为...")
        save_action.triggered.connect(self._save_image)
        
        # 关闭
        menu.addSeparator()
        close_action = menu.addAction(qta.icon('mdi6.close', color='#e53935'), "关闭")
        close_action.triggered.connect(self.close)
        
        menu.exec(event.globalPos())
    
    def _set_opacity(self, opacity: float):
        """设置透明度"""
        self._opacity = opacity
        self.update()
    
    def _reset_scale(self):
        """还原原始大小"""
        if not self._thumbnail_mode:
            self._scale = 1.0
            self._update_size()
    
    def _toggle_thumbnail_mode(self):
        """切换缩略图模式"""
        if self._thumbnail_mode:
            # 从缩略图模式恢复
            self._thumbnail_mode = False
            self._scale = self._saved_scale
            
            thumb_center = self.geometry().center()
            self._update_size()
            new_geo = self.geometry()
            new_geo.moveCenter(thumb_center)
            self.move(new_geo.topLeft())
        else:
            # 进入缩略图模式
            self._saved_scale = self._scale
            self._thumbnail_mode = True
            
            old_center = self.geometry().center()
            self._update_size()
            new_geo = self.geometry()
            new_geo.moveCenter(old_center)
            self.move(new_geo.topLeft())
    
    def _save_image(self):
        """保存图片"""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "保存图片",
            "",
            "PNG 图片 (*.png);;JPEG 图片 (*.jpg);;所有文件 (*.*)"
        )
        if file_path:
            self._original_pixmap.save(file_path)
