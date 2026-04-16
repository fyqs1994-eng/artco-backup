"""
截图模块 - 截图遮罩层和屏幕选择器
"""

import base64
import math
import os
import subprocess
import uuid

from PySide6.QtWidgets import QApplication, QWidget, QPushButton, QFileDialog, QMessageBox
from PySide6.QtCore import Qt, QRect, QSize, Signal, QBuffer, QIODevice, QTimer, QPoint, Property, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QColor, QPainter, QPen, QBrush, QGuiApplication, QPixmap, QFont, QKeyEvent, QCursor, QFontMetrics

from database import add_record
from ui import PromptSelectMenu, SettingsDialog
from .marks import FONT_NAME
from .utils import parse_hotkey
from .marks import MarkObject, RectMark, ArrowMark, FreehandMark, TextMark
from .toolbar import ScreenshotToolbar, ScreenshotAICapsule
from .pin import PinWindow
from .editor import EditorWindow
from .cache import get_cached_hotkeys, invalidate_hotkey_cache


def _overlay_caret_geometry(
    text: str, index: int, metrics: QFontMetrics, base_x: float, base_y: float
):
    line_height = metrics.height()
    if index < 0:
        index = 0
    if index > len(text):
        index = len(text)
    before = text[:index]
    lines = before.split('\n')
    line_idx = len(lines) - 1
    col = lines[-1]
    x = base_x + metrics.horizontalAdvance(col)
    y_top = base_y + line_idx * line_height
    return x, y_top, line_height


class ScreenSelectorWindow(QWidget):
    """单个屏幕的选择器窗口"""
    screen_selected = Signal(object)  # 改名，表示屏幕被选中（悬停或拖动）
    drag_started = Signal(object, object)  # (screen, start_pos)
    
    def __init__(self, screen):
        super().__init__()
        self.screen = screen
        self.is_hovered = False
        self._press_pos = None
        self._dragged = False
        self._font = QFont(FONT_NAME, 16, QFont.Weight.Bold)
        
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setCursor(Qt.CursorShape.CrossCursor)  # 改为十字光标，表示可以直接拖动
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        
        self.setGeometry(screen.geometry())
        self.show()
        self.activateWindow()
        self.setFocus()
        self.grabKeyboard()  # 抢占系统键盘焦点，防止按键穿透到底层应用
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # 悬停时更明显的高亮效果
        if self.is_hovered:
            painter.fillRect(self.rect(), QColor(0, 0, 0, 50))  # 更浅的遮罩
            border_width = 4
            border_color = QColor(0, 120, 215)
        else:
            painter.fillRect(self.rect(), QColor(0, 0, 0, 120))  # 较深的遮罩
            border_width = 2
            border_color = QColor(100, 100, 100, 150)
        
        painter.setPen(QPen(border_color, border_width))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        margin = border_width // 2
        painter.drawRect(self.rect().adjusted(margin, margin, -margin, -margin))
        
        # 显示提示文字
        painter.setPen(QColor(255, 255, 255))
        painter.setFont(self._font)
        if self.is_hovered:
            text = "按住拖动开始截图"
        else:
            text = f"屏幕 {self.screen.name()}"
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, text)
    
    def enterEvent(self, event):
        self.is_hovered = True
        self.screen_selected.emit(self.screen)  # 悬停时发送屏幕选择信号
        # 鼠标进入时抢占键盘焦点，确保此窗口能接收按键
        self.activateWindow()
        self.setFocus()
        self.grabKeyboard()
        self.update()
    
    def leaveEvent(self, event):
        self.is_hovered = False
        self.releaseKeyboard()
        self.update()
    
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_pos = event.pos()
            self._dragged = False
        elif event.button() == Qt.MouseButton.RightButton:
            event.accept()
            self.drag_started.emit(None, None)  # 取消

    def mouseMoveEvent(self, event):
        if self._press_pos is not None:
            delta = event.pos() - self._press_pos
            if delta.manhattanLength() > 4:  # 超过 4px 视为拖动
                self._dragged = True
                global_pos = self.mapToGlobal(self._press_pos)
                self._press_pos = None
                self.drag_started.emit(self.screen, global_pos)
                # emit 同步关闭本窗口（WA_DeleteOnClose），勿再 hide

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._press_pos is not None:
            if not self._dragged:
                # 单击：选择屏幕，不带起始位置，overlay 从头开始
                self._press_pos = None
                self.drag_started.emit(self.screen, None)
                # 同上

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            event.accept()  # 消费事件，防止穿透到底层窗口
            # 延迟发射取消信号，确保 keyRelease 仍由本窗口消费
            QTimer.singleShot(0, lambda: self.drag_started.emit(None, None))


class ScreenSelector(QWidget):
    """屏幕选择器管理器"""
    screen_selected = Signal(object)
    
    def __init__(self, parent_widget):
        super().__init__()
        self.parent_widget = parent_widget
        self.windows = []
        self.current_screen = None
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        
        screens = QGuiApplication.screens()
        
        for screen in screens:
            win = ScreenSelectorWindow(screen)
            win.screen_selected.connect(self._on_screen_hovered)
            win.drag_started.connect(self._on_drag_started)
            self.windows.append(win)
    
    def _on_screen_hovered(self, screen):
        """屏幕悬停时的处理"""
        self.current_screen = screen
        # 可以在这里添加额外的视觉反馈
    
    def _on_drag_started(self, screen, start_pos):
        """拖动开始：先关掉所有选择器窗口再抓屏，避免把提示文字/蓝框拍进截图。"""
        for win in self.windows:
            try:
                win.screen_selected.disconnect()
            except TypeError:
                pass
            try:
                win.drag_started.disconnect()
            except TypeError:
                pass
            win.close()
        self.windows.clear()

        if screen is None:
            self.screen_selected.emit(None)
            self.close()
            return

        QApplication.processEvents()

        clean_pixmap = None
        try:
            clean_pixmap = screen.grabWindow(0)
            if clean_pixmap is not None and not clean_pixmap.isNull():
                clean_pixmap.setDevicePixelRatio(1.0)
        except Exception:
            clean_pixmap = None

        self.screen_selected.emit((screen, start_pos, clean_pixmap))
        self.close()


class ScreenshotOverlay(QWidget):
    def __init__(self, target_screen=None, start_pos=None, prefetched_pixmap=None):
        super().__init__()
        
        if target_screen is None:
            cursor_pos = QCursor.pos()
            target_screen = QGuiApplication.screenAt(cursor_pos)
        if target_screen is None:
            target_screen = QGuiApplication.primaryScreen()
        
        self.target_screen = target_screen
        self.screen_geometry = target_screen.geometry()
        
        # 在显示窗口之前先截图，避免截取到自己的窗口
        self.full_screen_pixmap = None
        self._dimmed_background = None
        self.scale_x = 1.0
        self.scale_y = 1.0
        self._apply_screen_capture(prefetched_pixmap)
        
        # 使用缓存的快捷键配置
        self._hotkeys, self._hotkey_map = get_cached_hotkeys()
        
        # 撤销/重做栈
        self._redo_stack = []
        
        # 窗口属性
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.WindowStaysOnTopHint | 
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)  # 启用鼠标跟踪，支持悬停检测
        
        self.selection_rect = QRect()
        self.is_selecting = False
        self.is_moving = False
        self.is_resizing = False
        self.resize_handle = None
        self.handle_size = 8
        
        # 预分配 handles 字典
        self.handles = {
            'top_left': QRect(), 'top': QRect(), 'top_right': QRect(),
            'right': QRect(), 'bottom_right': QRect(), 'bottom': QRect(),
            'bottom_left': QRect(), 'left': QRect()
        }
        
        self.toolbar = None
        self._toolbar_connected = False
        
        # 快速标记状态
        self._mark_tool = 'none'  # 'none', 'rect', 'arrow', 'freehand', 'text'
        self._marks: list[MarkObject] = []
        self._is_marking = False
        self._mark_start_pos = QPoint()
        self._temp_freehand_points = []
        self._temp_freehand_mark = None  # 缓存临时涂鸦标记对象
        self._mark_color = QColor(255, 50, 50)
        
        # 即时渲染文本输入状态（临时标记）
        self._temp_text_editing = False
        self._temp_text_buffer = ""
        self._temp_text_preedit = ""
        self._temp_text_pos = QPoint()
        self._temp_text_cursor_visible = True
        self._temp_text_cursor_timer = QTimer(self)
        self._temp_text_cursor_timer.timeout.connect(self._toggle_temp_text_cursor)
        self._temp_text_font_size = 16
        self._temp_text_caret = 0
        self._temp_reedit_original: TextMark | None = None
        
        # AI 胶囊和提示菜单（懒加载）
        self.ai_capsule = None
        self.prompt_menu = None
        self._ai_quick_buttons = []
        
        # 固定比例功能
        self._aspect_ratios = [
            (None, "自由"),      # 自由模式
            (1/1, "1:1"),
            (4/3, "4:3"),
            (3/2, "3:2"),
            (16/9, "16:9"),
            (21/9, "21:9"),
        ]
        self._aspect_index = 0          # 当前选中的比例索引（0=自由）
        self._aspect_locked = False      # 是否锁定比例
        self._ratio_hint_opacity = 0.0   # 比例提示气泡透明度
        self._ratio_hint_timer = QTimer(self)
        self._ratio_hint_timer.setSingleShot(True)
        self._ratio_hint_timer.timeout.connect(self._fade_ratio_hint)
        self._ratio_fade_timer = QTimer(self)
        self._ratio_fade_timer.setInterval(16)  # ~60fps
        self._ratio_fade_timer.timeout.connect(self._do_fade_ratio_hint)

        self.setGeometry(self.screen_geometry)
        
        # 如果有起始位置，记录下来，在窗口显示后再处理
        self._pending_start_pos = start_pos
        
        self.show()
        self.activateWindow()
        self.setFocus()
        self.grabKeyboard()  # 抢占系统键盘焦点，防止按键穿透到底层应用
        
        # 下一事件循环处理起始位置（窗口已显示）
        if start_pos is not None:
            QTimer.singleShot(0, self._handle_pending_start_pos)
    
    def _handle_pending_start_pos(self):
        """处理延迟的起始位置"""
        if self._pending_start_pos is not None:
            start_pos = self._pending_start_pos
            self._pending_start_pos = None
            
            local_pos = self.mapFromGlobal(start_pos)
            self.is_selecting = True
            self.start_pos = local_pos
            self.selection_rect = QRect(local_pos, QSize(0, 0))
            self.update_handles()
            self.grabMouse()
    
    def _ensure_toolbar(self):
        """懒加载工具栏"""
        if self.toolbar is None:
            self.toolbar = ScreenshotToolbar(self)
            self.toolbar.expand_requested.connect(self._on_toolbar_expand)
            self.toolbar.mark_tool_changed.connect(self._on_mark_tool_changed)
            self.toolbar.color_changed.connect(self._on_mark_color_changed)
            self.toolbar.width_changed.connect(self._sync_positions)
        return self.toolbar

    def closeEvent(self, event):
        """关闭事件 - 确保资源正确释放"""
        # 停止临时文本编辑定时器
        if hasattr(self, '_temp_text_cursor_timer') and self._temp_text_cursor_timer.isActive():
            self._temp_text_cursor_timer.stop()
        
        # 释放鼠标抓取
        try:
            self.releaseMouse()
        except:
            pass
        
        # 释放键盘焦点
        try:
            self.releaseKeyboard()
        except:
            pass
        
        event.accept()

    def _apply_screen_capture(self, prefetched_pixmap=None):
        """使用预抓取或同步 grab；预抓取成功时可跳过遮罩首帧前的阻塞 grab。"""
        if (
            prefetched_pixmap is not None
            and not prefetched_pixmap.isNull()
            and prefetched_pixmap.width() > 0
        ):
            self.full_screen_pixmap = prefetched_pixmap
            self.full_screen_pixmap.setDevicePixelRatio(1.0)
            self.scale_x = self.full_screen_pixmap.width() / max(self.screen_geometry.width(), 1)
            self.scale_y = self.full_screen_pixmap.height() / max(self.screen_geometry.height(), 1)
            self._dimmed_background = None
            return
        self._capture_screenshot()

    def _capture_screenshot(self):
        """在窗口显示之前截取屏幕"""
        try:
            self.full_screen_pixmap = self.target_screen.grabWindow(0)
            self.full_screen_pixmap.setDevicePixelRatio(1.0)
            
            self.scale_x = self.full_screen_pixmap.width() / self.screen_geometry.width()
            self.scale_y = self.full_screen_pixmap.height() / self.screen_geometry.height()
            
            # 暗化背景懒加载，减少启动耗时
            self._dimmed_background = None
            
        except Exception as e:
            print(f"截图失败: {e}")
            self.full_screen_pixmap = QPixmap(self.screen_geometry.size())
            self.full_screen_pixmap.fill(QColor(100, 100, 100))
            self._dimmed_background = None
            self.scale_x = 1.0
            self.scale_y = 1.0

    def _get_dimmed_background(self):
        """懒加载暗化背景"""
        if self._dimmed_background is None:
            self._dimmed_background = QPixmap(self.screen_geometry.size())
            painter = QPainter(self._dimmed_background)
            painter.drawPixmap(self._dimmed_background.rect(), self.full_screen_pixmap)
            painter.fillRect(self._dimmed_background.rect(), QColor(0, 0, 0, 120))
            painter.end()
        return self._dimmed_background

    def _get_scaled_source_rect(self):
        """计算源矩形（物理像素坐标）"""
        return QRect(
            int(self.selection_rect.x() * self.scale_x),
            int(self.selection_rect.y() * self.scale_y),
            int(self.selection_rect.width() * self.scale_x) + 1,
            int(self.selection_rect.height() * self.scale_y) + 1
        )

    def update_handles(self):
        """原地更新 handles，避免重建字典"""
        if self.selection_rect.isNull():
            for h in self.handles.values():
                h.setRect(0, 0, 0, 0)
            return
        
        r = self.selection_rect
        s = self.handle_size
        hs = s // 2
        left, top, right, bottom = r.left(), r.top(), r.right(), r.bottom()
        cx, cy = (left + right) // 2, (top + bottom) // 2
        
        # 原地赋值，避免创建新对象
        self.handles['top_left'].setRect(left - hs, top - hs, s, s)
        self.handles['top'].setRect(cx - hs, top - hs, s, s)
        self.handles['top_right'].setRect(right - hs, top - hs, s, s)
        self.handles['right'].setRect(right - hs, cy - hs, s, s)
        self.handles['bottom_right'].setRect(right - hs, bottom - hs, s, s)
        self.handles['bottom'].setRect(cx - hs, bottom - hs, s, s)
        self.handles['bottom_left'].setRect(left - hs, bottom - hs, s, s)
        self.handles['left'].setRect(left - hs, cy - hs, s, s)


    def _ensure_ai_capsule(self):
        """懒加载 AI 胶囊"""
        if self.ai_capsule is None:
            self.ai_capsule = ScreenshotAICapsule(self)
            self.ai_capsule.clicked.connect(self._on_ai_clicked)
            self.ai_capsule.send_clicked.connect(self._on_ai_send)
            self.ai_capsule.prompt_selected.connect(lambda p: None)
            # 信号驱动位置同步（替代定时器轮询）
            self.ai_capsule.width_changed.connect(self._sync_positions)
        return self.ai_capsule

    def _clear_ai_quick_buttons(self):
        """清理侧边 AI 快捷按钮"""
        for btn in self._ai_quick_buttons:
            btn.hide()
            btn.deleteLater()
        self._ai_quick_buttons.clear()

    def _ensure_ai_quick_buttons(self):
        """按当前 prompts 生成侧边 AI 快捷按钮"""
        if self._ai_quick_buttons:
            return self._ai_quick_buttons

        prompts = ScreenshotAICapsule._load_prompts()
        for title, content, prompt_type in prompts:
            btn = QPushButton(title, self)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(self._build_prompt_tooltip(content))
            btn.setFixedHeight(28)
            if prompt_type == "image":
                border = "rgba(236, 72, 153, 0.95)"
                border_hover = "rgba(219, 39, 119, 1.0)"
            else:
                border = "rgba(99, 102, 241, 0.95)"
                border_hover = "rgba(79, 70, 229, 1.0)"
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: rgba(255, 255, 255, 0.98);
                    color: #1f2937;
                    border: 2px solid {border};
                    border-radius: 14px;
                    padding: 0 10px;
                    font-size: 12px;
                    font-weight: 500;
                }}
                QPushButton:hover {{
                    background: rgba(255, 255, 255, 1.0);
                    border: 2px solid {border_hover};
                }}
                QPushButton:pressed {{
                    background: rgba(229, 231, 235, 1.0);
                }}
            """)
            btn.clicked.connect(
                lambda checked=False, c=content, t=prompt_type: self._do_ai_process(c, t)
            )
            btn.hide()
            self._ai_quick_buttons.append(btn)

        return self._ai_quick_buttons

    @staticmethod
    def _build_prompt_tooltip(content: str) -> str:
        """构建短预览 tooltip，避免长 prompt 产生巨大悬浮窗。"""
        if not content:
            return ""
        text = content.strip()
        if not text:
            return ""
        max_lines = 3
        max_chars = 120
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if not lines:
            lines = [text.replace("\n", " ").strip()]
        preview_lines = lines[:max_lines]
        preview = "\n".join(preview_lines)
        if len(preview) > max_chars:
            preview = preview[:max_chars].rstrip() + "..."
        elif len(lines) > max_lines or len(text) > len(preview):
            preview = preview.rstrip() + "..."
        return preview

    def _update_ai_quick_buttons_pos(self):
        """将 AI 模版快捷按钮悬浮在选区侧边"""
        if self.selection_rect.isNull():
            self._hide_ai_quick_buttons()
            return

        buttons = self._ensure_ai_quick_buttons()
        if not buttons:
            return

        r = self.selection_rect
        screen_w = self.screen_geometry.width()
        screen_h = self.screen_geometry.height()
        gap = 8
        side_margin = 10
        y = r.top()
        max_w = 0
        total_h = 0

        for i, btn in enumerate(buttons):
            text_w = btn.fontMetrics().horizontalAdvance(btn.text())
            btn_w = max(56, min(140, text_w + 22))
            btn.setFixedWidth(btn_w)
            max_w = max(max_w, btn_w)
            total_h += btn.height() + (gap if i > 0 else 0)

        y = max(side_margin, min(y, screen_h - total_h - side_margin))
        right_x = r.right() + 12
        left_x = r.left() - max_w - 12

        if right_x + max_w <= screen_w - side_margin:
            x = right_x
        elif left_x >= side_margin:
            x = left_x
        else:
            x = max(side_margin, min(right_x, screen_w - max_w - side_margin))

        # 避让底部工具栏：小选区时快捷按钮可能与工具栏重叠
        quick_rect = QRect(x, y, max_w, total_h)
        toolbar = self.toolbar if (self.toolbar and self.toolbar.isVisible()) else None
        if toolbar is not None:
            toolbar_rect = toolbar.geometry().adjusted(-6, -6, 6, 6)
            if quick_rect.intersects(toolbar_rect):
                above_y = toolbar_rect.top() - total_h - 8
                below_y = toolbar_rect.bottom() + 8
                can_place_above = above_y >= side_margin
                can_place_below = (below_y + total_h) <= (screen_h - side_margin)
                if can_place_above:
                    y = above_y
                elif can_place_below:
                    y = below_y
                else:
                    # 两侧都不足时，退化到当前屏幕可见区内最优位置
                    y = max(side_margin, min(y, screen_h - total_h - side_margin))

        cy = y
        for btn in buttons:
            btn.move(x, cy)
            btn.show()
            cy += btn.height() + gap

    def _hide_ai_quick_buttons(self):
        for btn in self._ai_quick_buttons:
            btn.hide()
    
    def _ensure_prompt_menu(self):
        """懒加载提示菜单"""
        if self.prompt_menu is None:
            self.prompt_menu = PromptSelectMenu(self)
            self.prompt_menu.prompt_selected.connect(self._do_ai_process)
            self.prompt_menu.edit_requested.connect(self._open_prompt_editor)
        return self.prompt_menu

    def update_toolbar_pos(self):
        if self.selection_rect.isNull():
            if self.toolbar:
                self.toolbar.hide()
            if self.ai_capsule:
                self.ai_capsule.hide()
                self.ai_capsule._dropdown.hide()
            self._hide_ai_quick_buttons()
            return
        r = self.selection_rect
        screen_h = self.screen_geometry.height()
        screen_w = self.screen_geometry.width()
        
        # 懒加载工具栏和 AI 胶囊
        toolbar = self._ensure_toolbar()
        capsule = self._ensure_ai_capsule()
        
        # 重置 AI 胶囊状态（收起状态）
        if capsule.is_expanded():
            capsule.collapse()
        
        # 重置工具栏状态（展开状态）
        if toolbar.is_collapsed():
            toolbar.expand()
        
        # 使用目标宽度计算（初始状态：工具栏展开，AI胶囊收起）
        toolbar_w = ScreenshotToolbar.EXPANDED_WIDTH
        ai_w = ScreenshotAICapsule.COLLAPSED_WIDTH
        total_w = toolbar_w + 8 + ai_w  # 460 + 8 + 48 = 516
        
        # 居中于选区
        x = r.center().x() - total_w // 2
        y = r.bottom() + 10
        
        if y + toolbar.height() > screen_h:
            y = r.top() - toolbar.height() - 10
        x = max(10, min(x, screen_w - total_w - 10))
        y = max(10, min(y, screen_h - toolbar.height() - 10))
        
        # 保存基准位置
        self._toolbar_base_x = x
        self._toolbar_y = y
        
        # 定位工具栏
        toolbar.move(x, y)
        toolbar.show()
        
        # 定位 AI 胶囊（紧跟工具栏右侧）
        capsule.move(x + toolbar_w + 8, y)
        capsule.show()
        self._update_ai_quick_buttons_pos()
    
    def _on_ai_clicked(self):
        """点击 AI 按钮 - 工具栏收缩，AI胶囊已经在展开"""
        if self.toolbar:
            self.toolbar.collapse()
        # AI 输入框需要键盘输入，临时释放键盘抢占
        self.releaseKeyboard()
    
    def _on_toolbar_expand(self):
        """工具栏展开 - AI 胶囊收缩"""
        if self.ai_capsule:
            self.ai_capsule.collapse()
        # AI 收起后重新抢占键盘，防止按键穿透
        self.grabKeyboard()
    
    def _match_hotkey(self, event) -> str:
        """匹配按键事件，返回动作名称"""
        key = event.key()
        modifiers = event.modifiers() & ~Qt.KeyboardModifier.KeypadModifier  # 忽略小键盘修饰符
        
        # 精确匹配
        action = self._hotkey_map.get((modifiers, key))
        if action:
            return action
        
        # 无修饰符匹配（对于单键快捷键）
        if modifiers == Qt.KeyboardModifier.NoModifier:
            action = self._hotkey_map.get((Qt.KeyboardModifier.NoModifier, key))
            if action:
                return action
        
        return None
    
    def _on_mark_tool_changed(self, tool: str):
        """标记工具切换"""
        self._mark_tool = tool
        # 切换工具时结束当前文本输入
        self._finish_temp_text_editing()
        if tool == 'none':
            self.setCursor(Qt.CursorShape.CrossCursor)
        elif tool == 'arrow':
            self.setCursor(Qt.CursorShape.CrossCursor)
        elif tool == 'freehand':
            self.setCursor(Qt.CursorShape.CrossCursor)
        elif tool == 'text':
            self.setCursor(Qt.CursorShape.IBeamCursor)
    
    def _on_mark_color_changed(self, color):
        """标记颜色变化"""
        self._mark_color = color
    
    def _toggle_temp_text_cursor(self):
        """切换临时文本光标可见性"""
        self._temp_text_cursor_visible = not self._temp_text_cursor_visible
        if self._temp_text_editing:
            self.update()
    
    def _release_keyboard_for_ime(self):
        """释放键盘抢占，让系统输入法（Shift 切中英等）正常工作。与 AI 输入框逻辑一致。"""
        self.releaseKeyboard()

    def _restore_keyboard_grab_after_ime(self):
        """结束 IME 相关输入后恢复抢占，防止按键穿透到底层；AI 输入框展开时保持释放。"""
        if self.ai_capsule and self.ai_capsule.is_expanded() and self.ai_capsule.input_field.hasFocus():
            return
        self.grabKeyboard()

    def _start_temp_text_editing(self, pos: QPoint):
        """开始临时文本输入"""
        self._temp_text_editing = True
        self._temp_text_buffer = ""
        self._temp_text_preedit = ""
        self._temp_text_caret = 0
        self._temp_reedit_original = None
        self._temp_text_pos = pos
        self._temp_text_cursor_visible = True
        self._temp_text_cursor_timer.start(530)
        self.setAttribute(Qt.WidgetAttribute.WA_InputMethodEnabled, True)
        self._release_keyboard_for_ime()
        self.setFocus()
        self.update()
    
    def _finish_temp_text_editing(self):
        """完成临时文本输入"""
        if not self._temp_text_editing:
            return
        
        self._temp_text_cursor_timer.stop()
        self._temp_text_editing = False
        
        text = self._temp_text_buffer.strip()
        if text:
            mark = TextMark(self._temp_text_pos, text, self._mark_color)
            mark.font_size = self._temp_text_font_size
            self._marks.append(mark)
        
        self._temp_text_buffer = ""
        self._temp_text_preedit = ""
        self._temp_text_caret = 0
        self._temp_reedit_original = None
        self.update()
        self._restore_keyboard_grab_after_ime()

    def _abort_temp_text_editing(self):
        """取消临时文本编辑（不提交新 TextMark）。"""
        self._temp_text_cursor_timer.stop()
        self._temp_text_editing = False
        self._temp_text_buffer = ""
        self._temp_text_preedit = ""
        self._temp_text_caret = 0
        self._restore_keyboard_grab_after_ime()
        self.update()
    
    def _virtual_temp_edit_text(self) -> str:
        return (
            self._temp_text_buffer[: self._temp_text_caret]
            + self._temp_text_preedit
            + self._temp_text_buffer[self._temp_text_caret :]
        )

    def _temp_cursor_line_start(self, buf: str, caret: int) -> int:
        before = buf[:caret]
        i = before.rfind('\n')
        return 0 if i < 0 else i + 1

    def _temp_cursor_line_end(self, buf: str, caret: int) -> int:
        j = buf.find('\n', caret)
        return len(buf) if j < 0 else j

    def _temp_caret_move_up(self):
        buf = self._temp_text_buffer
        c = self._temp_text_caret
        line_start = self._temp_cursor_line_start(buf, c)
        col = c - line_start
        if line_start == 0:
            self._temp_text_caret = 0
            return
        prev_region = buf[: line_start - 1]
        prev_nl = prev_region.rfind('\n')
        prev_line_start = 0 if prev_nl < 0 else prev_nl + 1
        prev_line_len = line_start - 1 - prev_line_start
        self._temp_text_caret = prev_line_start + min(col, prev_line_len)

    def _temp_caret_move_down(self):
        buf = self._temp_text_buffer
        c = self._temp_text_caret
        line_end = self._temp_cursor_line_end(buf, c)
        if line_end >= len(buf):
            return
        line_start = self._temp_cursor_line_start(buf, c)
        col = c - line_start
        next_line_start = line_end + 1
        next_nl = buf.find('\n', next_line_start)
        next_line_end = len(buf) if next_nl < 0 else next_nl
        next_len = next_line_end - next_line_start
        self._temp_text_caret = next_line_start + min(col, next_len)

    def _draw_temp_editing_text(self, painter: QPainter):
        """绘制正在编辑的临时文本 — 坐标与 TextMark.draw 一致"""
        if not hasattr(self, '_cached_temp_font') or self._cached_temp_font_size != self._temp_text_font_size:
            self._cached_temp_font = QFont(FONT_NAME, self._temp_text_font_size)
            self._cached_temp_metrics = QFontMetrics(self._cached_temp_font)
            self._cached_temp_font_size = self._temp_text_font_size
        font = self._cached_temp_font
        metrics = self._cached_temp_metrics
        painter.setFont(font)
        painter.setPen(self._mark_color)
        virtual = self._virtual_temp_edit_text()
        lines = virtual.split('\n')
        line_height = metrics.height()
        padding = 4

        max_width = max((metrics.horizontalAdvance(line) for line in lines), default=0)
        if max_width == 0:
            max_width = metrics.horizontalAdvance("A")
        total_height = line_height * len(lines) if lines else line_height
        border_rect = QRect(
            self._temp_text_pos.x(),
            self._temp_text_pos.y(),
            max_width + padding * 2,
            total_height + padding * 2,
        )
        painter.save()
        painter.setPen(QPen(QColor(200, 200, 200), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(border_rect, 4, 4)
        painter.restore()
        painter.setPen(self._mark_color)

        base_x = float(self._temp_text_pos.x() + padding)
        base_y = float(self._temp_text_pos.y() + padding)

        for i, line in enumerate(lines):
            text_y = base_y + metrics.ascent() + i * line_height
            painter.drawText(int(base_x), int(text_y), line)

        if self._temp_text_preedit:
            pe = self._temp_text_preedit
            i0 = self._temp_text_caret
            i1 = i0 + len(pe)
            x0, y0, lh = _overlay_caret_geometry(virtual, i0, metrics, base_x, base_y)
            x1, _, _ = _overlay_caret_geometry(virtual, i1, metrics, base_x, base_y)
            text_y = y0 + metrics.ascent()
            painter.drawLine(int(x0), int(text_y + 2), int(x1), int(text_y + 2))

        cursor_index = self._temp_text_caret + len(self._temp_text_preedit)
        if self._temp_text_cursor_visible:
            cx, cy_top, lh = _overlay_caret_geometry(virtual, cursor_index, metrics, base_x, base_y)
            painter.setPen(QPen(self._mark_color, 2))
            painter.drawLine(int(cx), int(cy_top), int(cx), int(cy_top + lh))
    
    def _sync_positions(self):
        """信号驱动的位置同步 - 由 width_changed 触发，每帧精确跟踪"""
        if self.selection_rect.isNull():
            return
        
        # 总宽度始终保持不变: 516px (460 + 8 + 48)
        total_w = ScreenshotToolbar.EXPANDED_WIDTH + 8 + ScreenshotAICapsule.COLLAPSED_WIDTH
        
        r = self.selection_rect
        screen_w = self.screen_geometry.width()
        
        x = r.center().x() - total_w // 2
        x = max(10, min(x, screen_w - total_w - 10))
        y = self._toolbar_y if hasattr(self, '_toolbar_y') else (self.toolbar.y() if self.toolbar else 0)
        
        # 根据当前实际宽度计算位置
        toolbar_w = self.toolbar.width() if self.toolbar else ScreenshotToolbar.EXPANDED_WIDTH
        
        if self.toolbar:
            self.toolbar.move(x, y)
        if self.ai_capsule:
            self.ai_capsule.move(x + toolbar_w + 8, y)
        self._update_ai_quick_buttons_pos()
    
    def _on_ai_send(self, text: str, prompt_type: str = "text"):
        """AI 发送输入内容"""
        if self.selection_rect.isNull():
            return
        self._do_ai_process(text, prompt_type)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        
        # 如果截图还没准备好，先绘制纯黑背景
        if self.full_screen_pixmap is None:
            painter.fillRect(self.rect(), QColor(0, 0, 0, 120))
            return
        
        # 1. 绘制完整的暗色背景图（懒加载）
        painter.drawPixmap(0, 0, self._get_dimmed_background())
        
        # 归档动画模式 - 飞向图标效果
        if getattr(self, '_archive_animating', False):
            progress = getattr(self, '_archive_progress', 0.0)
            start_rect = getattr(self, '_archive_start_rect', self.selection_rect)
            target = getattr(self, '_archive_target', start_rect.center())
            
            if progress < 1.0:
                # 计算当前位置和大小（从原始矩形飞向目标点）
                # 缩放：从 1.0 缩小到 0
                scale = 1.0 - progress
                # 透明度：后半段开始淡出
                opacity = 1.0 - max(0, (progress - 0.5) * 2)
                
                # 中心点从原位置移动到目标位置
                start_center = start_rect.center()
                current_x = start_center.x() + (target.x() - start_center.x()) * progress
                current_y = start_center.y() + (target.y() - start_center.y()) * progress
                
                # 计算当前矩形
                new_w = max(1, int(start_rect.width() * scale))
                new_h = max(1, int(start_rect.height() * scale))
                current_rect = QRect(
                    int(current_x - new_w // 2),
                    int(current_y - new_h // 2),
                    new_w, new_h
                )
                
                if new_w > 2 and new_h > 2:
                    painter.save()
                    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
                    painter.setOpacity(opacity)
                    
                    # 绘制缩小的选区图片
                    source_rect = self._get_scaled_source_rect()
                    painter.drawPixmap(current_rect, self.full_screen_pixmap, source_rect)
                    painter.restore()
            return

        # 2. 如果有选区，使用剪切区域绘制原图
        if not self.selection_rect.isNull() and self.selection_rect.width() > 0 and self.selection_rect.height() > 0:
            painter.save()
            # 设置剪切区域为选区
            painter.setClipRect(self.selection_rect)
            # 启用高质量缩放
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            # 直接绘制原始高分辨率图片，让 Qt 处理 DPI 缩放
            # 目标区域是整个窗口，源区域是整个原图
            painter.drawPixmap(self.rect(), self.full_screen_pixmap, self.full_screen_pixmap.rect())
            
            # 绘制快速标记
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            for mark in self._marks:
                mark.draw(painter)
            
            # 绘制正在创建的临时标记
            if self._is_marking:
                if self._mark_tool == 'rect' and not self._mark_start_pos.isNull():
                    pos = getattr(self, '_last_mouse_pos', self._mark_start_pos)
                    temp_rect = RectMark(QRect(self._mark_start_pos, pos).normalized(), self._mark_color)
                    temp_rect.draw(painter)
                elif self._mark_tool == 'arrow' and not self._mark_start_pos.isNull():
                    pos = getattr(self, '_last_mouse_pos', self._mark_start_pos)
                    temp_arrow = ArrowMark(self._mark_start_pos, pos, self._mark_color)
                    temp_arrow.draw(painter)
                elif self._mark_tool == 'freehand' and self._temp_freehand_mark:
                    self._temp_freehand_mark.draw(painter)
            
            # 绘制正在输入的临时文本
            if self._temp_text_editing:
                self._draw_temp_editing_text(painter)
            
            painter.restore()
            
            # 绘制边框和控制点（开启抗锯齿）
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setPen(QPen(QColor(0, 120, 215), 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self.selection_rect)
            
            # 绘制控制点
            painter.setBrush(QBrush(QColor(0, 120, 215)))
            painter.setPen(Qt.PenStyle.NoPen)
            for handle_rect in self.handles.values():
                if not handle_rect.isNull():
                    painter.drawRect(handle_rect)
            
            # 绘制比例提示气泡
            if self._ratio_hint_opacity > 0 and self._aspect_locked:
                _, label = self._aspect_ratios[self._aspect_index]
                painter.save()
                painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                painter.setOpacity(self._ratio_hint_opacity)
                
                font = QFont("Segoe UI", 13, QFont.Weight.Bold)
                painter.setFont(font)
                fm = QFontMetrics(font)
                text_w = fm.horizontalAdvance(label)
                text_h = fm.height()
                
                pad_x, pad_y = 14, 8
                bubble_w = text_w + pad_x * 2
                bubble_h = text_h + pad_y * 2
                
                # 气泡位于选区中心
                bx = self.selection_rect.center().x() - bubble_w // 2
                by = self.selection_rect.center().y() - bubble_h // 2
                
                # 背景
                painter.setBrush(QColor(0, 0, 0, 160))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawRoundedRect(bx, by, bubble_w, bubble_h, 8, 8)
                
                # 文字
                painter.setPen(QColor(255, 255, 255))
                painter.drawText(bx + pad_x, by + pad_y + fm.ascent(), label)
                painter.restore()

    def _get_int_pos(self, event) -> QPoint:
        """获取强制取整的鼠标位置"""
        return QPoint(int(event.position().x()), int(event.position().y()))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            # 如果有标记工具选中，取消选中
            if self._mark_tool != 'none':
                self._mark_tool = 'none'
                self.toolbar.set_mark_tool('none')
                self.setCursor(Qt.CursorShape.CrossCursor)
                return
            self.close()
            return
        
        pos = self._get_int_pos(event)

        # AI 输入框展开时：仅允许点击工具按钮区触发收起
        if self._handle_ai_expanded_click_gate(pos):
            event.accept()
            return
        
        # 选区锚点优先级最高：即使当前选中标记工具，也先响应调整选区
        for handle, rect in self.handles.items():
            if not rect.isNull() and rect.contains(pos):
                self.is_resizing = True
                self.resize_handle = handle
                # 拖拽边锚点 → 自动解除比例锁定（用户意图是自由调整单边）
                if self._aspect_locked and handle in ('top', 'bottom', 'left', 'right'):
                    self._unlock_aspect_ratio()
                self._hide_toolbar_and_capsule()
                return
        
        # 标记工具：在选区内（且不在锚点上，锚点已上面处理）
        if self._mark_tool != 'none' and self.selection_rect.contains(pos):
            self._is_marking = True
            self._mark_start_pos = pos
            self._last_mouse_pos = pos
            
            if self._mark_tool == 'freehand':
                self._temp_freehand_points = [pos]
            elif self._mark_tool == 'text':
                self._finish_temp_text_editing()
                hit = None
                for m in reversed(self._marks):
                    if isinstance(m, TextMark) and m.contains(pos):
                        hit = m
                        break
                if hit:
                    self._marks.remove(hit)
                    self._redo_stack.clear()
                    self._temp_reedit_original = hit
                    self._temp_text_buffer = hit.text
                    self._temp_text_preedit = ""
                    self._temp_text_caret = len(hit.text)
                    self._temp_text_pos = hit.pos
                    self._temp_text_font_size = hit.font_size
                    self._temp_text_editing = True
                    self._temp_text_cursor_visible = True
                    self._temp_text_cursor_timer.start(530)
                    self.setAttribute(Qt.WidgetAttribute.WA_InputMethodEnabled, True)
                    self._release_keyboard_for_ime()
                    self.setFocus()
                    self.update()
                else:
                    self._start_temp_text_editing(pos)
                self._is_marking = False
            return
        if self.selection_rect.contains(pos):
            self.is_moving = True
            self.drag_start_pos = pos
            self._hide_toolbar_and_capsule()
        else:
            self._hide_toolbar_and_capsule()
            self._unlock_aspect_ratio()
            
            self.is_selecting = True
            self.start_pos = pos
            self.selection_rect = QRect(pos, QSize(0, 0))
            self.update_handles()
            self.update()

    def mouseMoveEvent(self, event):
        pos = self._get_int_pos(event)
        self._last_mouse_pos = pos
        
        # 正在标记
        if self._is_marking:
            if self._mark_tool == 'freehand':
                # 最小距离过滤，减少冗余点以提升平滑效果
                if self._temp_freehand_points:
                    last = self._temp_freehand_points[-1]
                    if (pos.x() - last.x())**2 + (pos.y() - last.y())**2 < 9:
                        return
                self._temp_freehand_points.append(pos)
                # 更新缓存的临时涂鸦标记
                if self._temp_freehand_mark is None:
                    self._temp_freehand_mark = FreehandMark(self._temp_freehand_points, self._mark_color)
                else:
                    self._temp_freehand_mark._points = self._temp_freehand_points
                    self._temp_freehand_mark.color = self._mark_color
                    self._temp_freehand_mark._invalidate_cache()
            self.update()
            return
        
        if self.is_selecting:
            x1, y1 = self.start_pos.x(), self.start_pos.y()
            x2, y2 = pos.x(), pos.y()
            if x1 > x2: x1, x2 = x2, x1
            if y1 > y2: y1, y2 = y2, y1
            self.selection_rect = QRect(x1, y1, x2 - x1, y2 - y1)
            self._hide_toolbar_and_capsule()
        elif self.is_moving:
            delta = pos - self.drag_start_pos
            self.selection_rect.translate(delta)
            self.drag_start_pos = pos
            self._hide_toolbar_and_capsule()
        elif self.is_resizing:
            x = self.selection_rect.x()
            y = self.selection_rect.y()
            w = self.selection_rect.width()
            h = self.selection_rect.height()
            x2 = x + w
            y2 = y + h
            
            if self.resize_handle == 'top_left':
                x, y = pos.x(), pos.y()
            elif self.resize_handle == 'top':
                y = pos.y()
            elif self.resize_handle == 'top_right':
                x2, y = pos.x(), pos.y()
            elif self.resize_handle == 'right':
                x2 = pos.x()
            elif self.resize_handle == 'bottom_right':
                x2, y2 = pos.x(), pos.y()
            elif self.resize_handle == 'bottom':
                y2 = pos.y()
            elif self.resize_handle == 'bottom_left':
                x, y2 = pos.x(), pos.y()
            elif self.resize_handle == 'left':
                x = pos.x()
            
            if x > x2:
                x, x2 = x2, x
            if y > y2:
                y, y2 = y2, y
            
            # 如果比例锁定，约束 resize
            if self._aspect_locked:
                ratio_val, _ = self._aspect_ratios[self._aspect_index]
                if ratio_val is not None:
                    new_w = x2 - x
                    new_h = y2 - y
                    cur_ratio = new_w / new_h if new_h > 0 else 1.0
                    target = ratio_val if cur_ratio >= 1.0 else 1.0 / ratio_val
                    # 角锚点：以宽度为准调整高度
                    if self.resize_handle in ('top_left', 'top_right', 'bottom_left', 'bottom_right'):
                        new_h = int(new_w / target)
                    # 左右边锚点：以宽度为准
                    elif self.resize_handle in ('left', 'right'):
                        new_h = int(new_w / target)
                    # 上下边锚点：以高度为准
                    else:
                        new_w = int(new_h * target)
                    # 根据锚点方向决定固定边
                    if 'top' in (self.resize_handle or ''):
                        y = y2 - new_h
                    else:
                        y2 = y + new_h
                    if 'left' in (self.resize_handle or ''):
                        x = x2 - new_w
                    else:
                        x2 = x + new_w
            
            self.selection_rect = QRect(x, y, x2 - x, y2 - y)
            self._hide_toolbar_and_capsule()
        else:
            # 没有拖动操作时，更新鼠标光标
            self._update_cursor_for_position(pos)
            
            return
        
        self.update_handles()
        self.update()
    
    def _update_cursor_for_position(self, pos: QPoint):
        """根据鼠标位置更新光标样式"""
        # 锚点优先：悬停在选区调整点上时始终显示调整光标（与是否选中标记工具无关）
        for handle, rect in self.handles.items():
            if not rect.isNull() and rect.contains(pos):
                if handle in ('top_left', 'bottom_right'):
                    self.setCursor(Qt.CursorShape.SizeFDiagCursor)
                elif handle in ('top_right', 'bottom_left'):
                    self.setCursor(Qt.CursorShape.SizeBDiagCursor)
                elif handle in ('top', 'bottom'):
                    self.setCursor(Qt.CursorShape.SizeVerCursor)
                elif handle in ('left', 'right'):
                    self.setCursor(Qt.CursorShape.SizeHorCursor)
                return
        
        if self._mark_tool == 'text':
            self.setCursor(Qt.CursorShape.IBeamCursor)
            return
        if self._mark_tool != 'none':
            self.setCursor(Qt.CursorShape.CrossCursor)
            return
        
        # 检查是否在选区内
        if self.selection_rect.contains(pos):
            self.setCursor(Qt.CursorShape.SizeAllCursor)
            return
        
        # 默认十字光标
        self.setCursor(Qt.CursorShape.CrossCursor)
    
    def _hide_toolbar_and_capsule(self):
        """隐藏工具栏、AI胶囊和下拉列表"""
        if self.toolbar:
            self.toolbar.hide()
        if self.ai_capsule:
            self.ai_capsule.hide()
            self.ai_capsule._dropdown.hide()
        self._hide_ai_quick_buttons()

    def _toolbar_buttons_rect(self) -> QRect:
        """工具栏按钮容器在 overlay 坐标中的矩形。"""
        if not self.toolbar or not self.toolbar.isVisible():
            return QRect()
        container = getattr(self.toolbar, "buttons_container", None)
        if container is None or not container.isVisible():
            return QRect()
        top_left = container.mapTo(self, QPoint(0, 0))
        return QRect(top_left, container.size())

    def _handle_ai_expanded_click_gate(self, pos: QPoint) -> bool:
        """AI 展开时点击门控。

        返回 True 表示事件已处理（上层应直接 return）。
        仅当点击工具按钮区时，才允许收起 AI 输入框。
        """
        if not self.ai_capsule or not self.ai_capsule.is_expanded():
            return False

        capsule_rect = self.ai_capsule.geometry().adjusted(-10, -8, 10, 8)
        if capsule_rect.contains(pos):
            return True

        dropdown = getattr(self.ai_capsule, "_dropdown", None)
        if dropdown is not None and dropdown.isVisible() and dropdown.geometry().contains(pos):
            return True

        toolbar_rect = self._toolbar_buttons_rect()
        if not toolbar_rect.isNull() and toolbar_rect.contains(pos):
            self.ai_capsule.collapse()
            self.grabKeyboard()
            return False

        # 其它区域不再误收起，也不触发选区操作
        return True

    # ── 固定比例：滚轮切换 ──────────────────────────────────

    def wheelEvent(self, event):
        """滚轮切换选区固定比例"""
        # 仅在有有效选区、且不在标记/文本编辑模式时响应
        if (self.selection_rect.isNull() or self.selection_rect.width() < 5
                or self._mark_tool != 'none' or self._temp_text_editing
                or self.is_selecting or self.is_moving or self.is_resizing):
            event.ignore()
            return

        delta = event.angleDelta().y()
        if delta == 0:
            event.ignore()
            return

        event.accept()

        if not self._aspect_locked:
            # 首次滚动：吸附到最接近当前选区的比例
            self._aspect_index = self._find_nearest_ratio_index()
            self._aspect_locked = True
        else:
            # 后续滚动：在列表中循环切换（跳过索引0"自由"）
            direction = 1 if delta < 0 else -1
            n = len(self._aspect_ratios)
            self._aspect_index = ((self._aspect_index - 1 + direction) % (n - 1)) + 1

        # 应用比例
        self._apply_aspect_ratio()
        self._show_ratio_hint()

    def _find_nearest_ratio_index(self) -> int:
        """找到与当前选区最接近的预设比例索引"""
        w = self.selection_rect.width()
        h = self.selection_rect.height()
        if h == 0:
            return 1
        current_ratio = w / h

        best_idx = 1
        best_diff = float('inf')
        for i, (ratio, _) in enumerate(self._aspect_ratios):
            if ratio is None:
                continue
            # 同时比较 ratio 和 1/ratio（横版/竖版）
            diff = min(abs(current_ratio - ratio), abs(current_ratio - 1 / ratio))
            if diff < best_diff:
                best_diff = diff
                best_idx = i
        return best_idx

    def _apply_aspect_ratio(self):
        """以中心点为锚点，保持面积近似不变地调整选区到目标比例"""
        ratio_val, _ = self._aspect_ratios[self._aspect_index]
        if ratio_val is None:
            return

        w = self.selection_rect.width()
        h = self.selection_rect.height()
        cx = self.selection_rect.x() + w / 2
        cy = self.selection_rect.y() + h / 2

        # 判断横版还是竖版：保持与当前选区方向一致
        current_ratio = w / h if h > 0 else 1.0
        if current_ratio < 1.0:
            target_ratio = 1.0 / ratio_val  # 竖版
        else:
            target_ratio = ratio_val  # 横版

        area = w * h
        new_w = int(math.sqrt(area * target_ratio))
        new_h = int(new_w / target_ratio) if target_ratio != 0 else new_w

        # 保证最小尺寸
        new_w = max(new_w, 10)
        new_h = max(new_h, 10)

        # 以中心点定位
        new_x = int(cx - new_w / 2)
        new_y = int(cy - new_h / 2)

        # 边界裁剪（不超出屏幕）
        geo = self.screen_geometry
        if new_x < 0:
            new_x = 0
        if new_y < 0:
            new_y = 0
        if new_x + new_w > geo.width():
            new_x = geo.width() - new_w
        if new_y + new_h > geo.height():
            new_y = geo.height() - new_h
        # 二次裁剪（如果比屏幕还大）
        new_x = max(new_x, 0)
        new_y = max(new_y, 0)
        new_w = min(new_w, geo.width() - new_x)
        new_h = min(new_h, geo.height() - new_y)

        self.selection_rect = QRect(new_x, new_y, new_w, new_h)
        self.update_handles()
        self.update_toolbar_pos()
        self.update()

    def _show_ratio_hint(self):
        """显示比例提示气泡"""
        self._ratio_hint_opacity = 1.0
        self._ratio_fade_timer.stop()
        self._ratio_hint_timer.start(800)  # 800ms 后开始淡出
        self.update()

    def _fade_ratio_hint(self):
        """开始淡出比例提示"""
        self._ratio_fade_timer.start()

    def _do_fade_ratio_hint(self):
        """逐帧淡出比例提示"""
        self._ratio_hint_opacity -= 0.08
        if self._ratio_hint_opacity <= 0:
            self._ratio_hint_opacity = 0.0
            self._ratio_fade_timer.stop()
        self.update()

    def _unlock_aspect_ratio(self):
        """解除比例锁定"""
        self._aspect_locked = False
        self._aspect_index = 0
        self._ratio_hint_opacity = 0.0
        self._ratio_hint_timer.stop()
        self._ratio_fade_timer.stop()

    # ── 固定比例结束 ──────────────────────────────────────

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            if not self.selection_rect.isNull() and self.selection_rect.width() > 5:
                self.trigger_pin_action()
            return
        
        # 完成标记
        if self._is_marking:
            pos = self._get_int_pos(event)
            if self._mark_tool == 'rect':
                rect = QRect(self._mark_start_pos, pos).normalized()
                if rect.width() > 5 and rect.height() > 5:
                    mark = RectMark(rect, self._mark_color)
                    self._marks.append(mark)
            elif self._mark_tool == 'arrow':
                if self._mark_start_pos != pos:
                    mark = ArrowMark(self._mark_start_pos, pos, self._mark_color)
                    self._marks.append(mark)
            elif self._mark_tool == 'freehand':
                if len(self._temp_freehand_points) > 1:
                    mark = FreehandMark(self._temp_freehand_points.copy(), self._mark_color)
                    self._marks.append(mark)
                self._temp_freehand_points = []
                self._temp_freehand_mark = None
            
            self._is_marking = False
            self._mark_start_pos = QPoint()
            self.update()
            return
        
        # 如果是从屏幕选择器拖动过来的，释放鼠标抓取
        if hasattr(self, 'start_pos') and self.is_selecting:
            self.releaseMouse()
        
        self.is_selecting = False
        self.is_moving = False
        self.is_resizing = False
        self.resize_handle = None
        if not self.selection_rect.isNull() and self.selection_rect.width() > 5:
            self.update_toolbar_pos()

    def mouseDoubleClickEvent(self, event):
        if self._temp_text_editing or self._mark_tool == 'text':
            return
        if event.button() == Qt.MouseButton.LeftButton and not self.selection_rect.isNull():
            if self.selection_rect.contains(self._get_int_pos(event)):
                self.finish_screenshot()

    def keyPressEvent(self, event):
        # 如果正在输入临时文本
        if self._temp_text_editing:
            key = event.key()
            modifiers = event.modifiers()
            
            if key == Qt.Key.Key_Return:
                if modifiers & Qt.KeyboardModifier.ControlModifier:
                    self._temp_text_buffer = (
                        self._temp_text_buffer[: self._temp_text_caret]
                        + '\n'
                        + self._temp_text_buffer[self._temp_text_caret :]
                    )
                    self._temp_text_caret += 1
                    self.update()
                else:
                    self._finish_temp_text_editing()
                return
            
            elif key == Qt.Key.Key_Escape:
                if self._temp_reedit_original is not None:
                    self._marks.append(self._temp_reedit_original)
                    self._temp_reedit_original = None
                    self._abort_temp_text_editing()
                else:
                    self._temp_text_buffer = ""
                    self._temp_text_caret = 0
                    self._finish_temp_text_editing()
                return
            
            elif key == Qt.Key.Key_Backspace:
                if self._temp_text_preedit:
                    event.ignore()
                    return
                if self._temp_text_caret > 0:
                    self._temp_text_buffer = (
                        self._temp_text_buffer[: self._temp_text_caret - 1]
                        + self._temp_text_buffer[self._temp_text_caret :]
                    )
                    self._temp_text_caret -= 1
                    self.update()
                return

            elif key == Qt.Key.Key_Delete:
                if self._temp_text_preedit:
                    event.ignore()
                    return
                if self._temp_text_caret < len(self._temp_text_buffer):
                    self._temp_text_buffer = (
                        self._temp_text_buffer[: self._temp_text_caret]
                        + self._temp_text_buffer[self._temp_text_caret + 1 :]
                    )
                    self.update()
                return

            elif key in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_Home, Qt.Key.Key_End):
                if self._temp_text_preedit:
                    event.ignore()
                    return
                if key == Qt.Key.Key_Left:
                    self._temp_text_caret = max(0, self._temp_text_caret - 1)
                elif key == Qt.Key.Key_Right:
                    self._temp_text_caret = min(len(self._temp_text_buffer), self._temp_text_caret + 1)
                elif key == Qt.Key.Key_Up:
                    self._temp_caret_move_up()
                elif key == Qt.Key.Key_Down:
                    self._temp_caret_move_down()
                elif key == Qt.Key.Key_Home:
                    self._temp_text_caret = self._temp_cursor_line_start(self._temp_text_buffer, self._temp_text_caret)
                elif key == Qt.Key.Key_End:
                    self._temp_text_caret = self._temp_cursor_line_end(self._temp_text_buffer, self._temp_text_caret)
                self._temp_text_cursor_visible = True
                self.update()
                return
            
            else:
                # 修饰键、无字符键交给系统/输入法（避免 Shift 切换中英被吞）
                if key in (
                    Qt.Key.Key_Shift, Qt.Key.Key_Control, Qt.Key_Alt,
                    Qt.Key.Key_Meta, Qt.Key.Key_AltGr, Qt.Key.Key_CapsLock,
                ):
                    event.ignore()
                    return
                text = event.text()
                if text and text.isprintable():
                    self._temp_text_buffer = (
                        self._temp_text_buffer[: self._temp_text_caret]
                        + text
                        + self._temp_text_buffer[self._temp_text_caret :]
                    )
                    self._temp_text_caret += len(text)
                    self._temp_text_cursor_visible = True
                    self.update()
                    event.accept()
                else:
                    event.ignore()
                return
        
        # 如果 AI 胶囊展开且输入框有焦点，让输入框处理键盘事件
        if self.ai_capsule and self.ai_capsule.is_expanded() and self.ai_capsule.input_field.hasFocus():
            if event.key() == Qt.Key.Key_Escape:
                event.accept()
                QTimer.singleShot(0, self.close)
            else:
                super().keyPressEvent(event)
            return
        
        # 匹配可配置快捷键
        action = self._match_hotkey(event)
        if action:
            event.accept()  # 消费事件，防止穿透到底层窗口
            self._execute_hotkey_action(action)
            return
        
        super().keyPressEvent(event)
    
    def _execute_hotkey_action(self, action: str):
        """执行快捷键动作"""
        has_selection = not self.selection_rect.isNull()
        
        # === 基础操作 ===
        if action == 'confirm':
            if has_selection:
                self.finish_screenshot()
        elif action == 'cancel':
            if self._mark_tool != 'none':
                self._mark_tool = 'none'
                self.toolbar.set_mark_tool('none')
                self.setCursor(Qt.CursorShape.CrossCursor)
            else:
                # 延迟关闭，确保 keyRelease 仍由本窗口消费，不穿透到底层应用
                QTimer.singleShot(0, self.close)
        elif action == 'copy':
            if has_selection:
                self._finish_temp_text_editing()
                pixmap = self._get_marked_pixmap()
                QGuiApplication.clipboard().setPixmap(pixmap)
                QTimer.singleShot(0, self.close)
        elif action == 'save':
            if has_selection:
                self.save_screenshot()
        elif action == 'pin':
            if has_selection:
                self.trigger_pin_action()
        elif action == 'edit':
            if has_selection:
                self.open_editor()
        elif action == 'undo':
            if self._marks:
                mark = self._marks.pop()
                self._redo_stack.append(mark)
                self.update()
        elif action == 'redo':
            if self._redo_stack:
                mark = self._redo_stack.pop()
                self._marks.append(mark)
                self.update()
        elif action == 'select_all':
            self.selection_rect = QRect(0, 0, self.width(), self.height())
            self.update_handles()
            self.update_toolbar_pos()
            self.update()
        elif action == 'toggle_toolbar':
            if self.toolbar and self.toolbar.isVisible():
                self._hide_toolbar_and_capsule()
            elif has_selection:
                self.update_toolbar_pos()
        
        # === 选区调整 ===
        elif action == 'move_up':
            if has_selection:
                self.selection_rect.translate(0, -1)
                self._update_after_selection_change()
        elif action == 'move_down':
            if has_selection:
                self.selection_rect.translate(0, 1)
                self._update_after_selection_change()
        elif action == 'move_left':
            if has_selection:
                self.selection_rect.translate(-1, 0)
                self._update_after_selection_change()
        elif action == 'move_right':
            if has_selection:
                self.selection_rect.translate(1, 0)
                self._update_after_selection_change()
        elif action == 'expand_up':
            if has_selection:
                r = self.selection_rect
                self.selection_rect = QRect(r.x(), r.y() - 1, r.width(), r.height() + 1)
                self._update_after_selection_change()
        elif action == 'expand_down':
            if has_selection:
                r = self.selection_rect
                self.selection_rect = QRect(r.x(), r.y(), r.width(), r.height() + 1)
                self._update_after_selection_change()
        elif action == 'expand_left':
            if has_selection:
                r = self.selection_rect
                self.selection_rect = QRect(r.x() - 1, r.y(), r.width() + 1, r.height())
                self._update_after_selection_change()
        elif action == 'expand_right':
            if has_selection:
                r = self.selection_rect
                self.selection_rect = QRect(r.x(), r.y(), r.width() + 1, r.height())
                self._update_after_selection_change()
        
        # === 标记工具 ===
        elif action == 'tool_none':
            self._set_mark_tool('none')
        elif action == 'tool_rect':
            if has_selection:
                self._toggle_mark_tool('rect')
        elif action == 'tool_freehand':
            if has_selection:
                self._toggle_mark_tool('freehand')
        elif action == 'tool_text':
            if has_selection:
                self._toggle_mark_tool('text')
    
    def _update_after_selection_change(self):
        """选区变化后更新"""
        self.update_handles()
        self.update()
    
    def _set_mark_tool(self, tool: str):
        """设置标记工具（不切换）"""
        self._mark_tool = tool
        self.toolbar.set_mark_tool(tool)
        self._on_mark_tool_changed(tool)
    
    def inputMethodEvent(self, event):
        """处理输入法事件（临时标记的中文输入）"""
        if self._temp_text_editing:
            self._temp_text_preedit = event.preeditString()
            commit_text = event.commitString()
            if commit_text:
                self._temp_text_buffer = (
                    self._temp_text_buffer[: self._temp_text_caret]
                    + commit_text
                    + self._temp_text_buffer[self._temp_text_caret :]
                )
                self._temp_text_caret += len(commit_text)
                self._temp_text_preedit = ""
            self._temp_text_cursor_visible = True
            self.update()
            event.accept()
        else:
            super().inputMethodEvent(event)
    
    def inputMethodQuery(self, query):
        """提供输入法查询信息"""
        from PySide6.QtCore import Qt
        if query == Qt.InputMethodQuery.ImEnabled:
            return self._temp_text_editing
        elif query == Qt.InputMethodQuery.ImCursorRectangle:
            if self._temp_text_editing:
                if not hasattr(self, '_cached_temp_font') or self._cached_temp_font_size != self._temp_text_font_size:
                    self._cached_temp_font = QFont(FONT_NAME, self._temp_text_font_size)
                    self._cached_temp_metrics = QFontMetrics(self._cached_temp_font)
                    self._cached_temp_font_size = self._temp_text_font_size
                metrics = self._cached_temp_metrics
                virtual = self._virtual_temp_edit_text()
                idx = self._temp_text_caret + len(self._temp_text_preedit)
                padding = 4
                base_x = float(self._temp_text_pos.x() + padding)
                base_y = float(self._temp_text_pos.y() + padding)
                cx, cy_top, lh = _overlay_caret_geometry(virtual, idx, metrics, base_x, base_y)
                return QRect(int(cx), int(cy_top), 2, int(lh))
        return super().inputMethodQuery(query)
    
    def _toggle_mark_tool(self, tool: str):
        """切换标记工具"""
        if self._mark_tool == tool:
            self._mark_tool = 'none'
            self.toolbar.set_mark_tool('none')
            self.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self._mark_tool = tool
            self.toolbar.set_mark_tool(tool)
            self._on_mark_tool_changed(tool)

    def save_screenshot(self):
        self._finish_temp_text_editing()  # 先结束文本编辑
        pixmap = self._get_marked_pixmap()
        file_path, _ = QFileDialog.getSaveFileName(self, "保存截图", "screenshot.png", "Images (*.png *.jpg)")
        if file_path:
            pixmap.save(file_path)
            self.close()
    
    def _get_marked_pixmap(self) -> QPixmap:
        """获取带标记的截图"""
        # 确保临时文本被提交（即使用户没按 Enter）
        if self._temp_text_editing and self._temp_text_buffer.strip():
            text = self._temp_text_buffer.strip()
            mark = TextMark(self._temp_text_pos, text, self._mark_color)
            mark.font_size = self._temp_text_font_size
            self._marks.append(mark)
            self._temp_text_buffer = ""
            self._temp_text_preedit = ""
            self._temp_text_caret = 0
            self._temp_reedit_original = None
            self._temp_text_editing = False
            self._temp_text_cursor_timer.stop()
            self._restore_keyboard_grab_after_ime()
        
        base_pixmap = self.full_screen_pixmap.copy(self._get_scaled_source_rect())
        
        if not self._marks:
            return base_pixmap
        
        # 在截图上绘制标记
        painter = QPainter(base_pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # 计算选区偏移（标记位置需要转换为截图坐标）
        offset_x = self.selection_rect.x() * self.scale_x
        offset_y = self.selection_rect.y() * self.scale_y
        
        painter.translate(-offset_x, -offset_y)
        painter.scale(self.scale_x, self.scale_y)
        
        for mark in self._marks:
            mark.draw(painter)
        
        painter.end()
        return base_pixmap

    def trigger_pin_action(self):
        """贴图到屏幕 - 工具栏按钮和中键都调用此方法"""
        if self.selection_rect.isNull():
            return
        
        self._finish_temp_text_editing()  # 先结束文本编辑
        
        # 获取带标记的截图
        pixmap = self._get_marked_pixmap()
        # 设置 devicePixelRatio 使显示尺寸与选区一致
        pixmap.setDevicePixelRatio(self.scale_x)
        
        # 计算贴图位置（与选区位置重合）
        pin_x = self.screen_geometry.x() + self.selection_rect.x()
        pin_y = self.screen_geometry.y() + self.selection_rect.y()
        
        # 创建贴图窗口
        pin_window = PinWindow(pixmap)
        pin_window.move(pin_x, pin_y)
        
        # 添加到全局列表防止被回收
        app = QApplication.instance()
        if not hasattr(app, '_pin_windows'):
            app._pin_windows = []
        app._pin_windows.append(pin_window)
        
        # 当贴图窗口关闭时从列表中移除
        def on_pin_closed():
            if pin_window in app._pin_windows:
                app._pin_windows.remove(pin_window)
        pin_window.destroyed.connect(on_pin_closed)
        
        # 连接编辑请求信号
        def on_edit_requested(edit_pixmap):
            from .editor import EditorWindow
            editor = EditorWindow(edit_pixmap)
            editor.show()
            # 保持编辑器引用
            if not hasattr(app, '_editor_windows'):
                app._editor_windows = []
            app._editor_windows.append(editor)
            def on_editor_closed():
                if editor in app._editor_windows:
                    app._editor_windows.remove(editor)
            editor.destroyed.connect(on_editor_closed)
        pin_window.edit_requested.connect(on_edit_requested)
        
        pin_window.show()
        
        # 恢复胶囊位置（但尊重强制隐藏状态）
        if hasattr(app, '_capsule_widget') and app._capsule_widget:
            capsule = app._capsule_widget
            if capsule._saved_pos is not None:
                capsule.move(capsule._saved_pos)
            # 只有非强制隐藏模式才显示
            if not capsule._force_hidden:
                capsule.reveal(animated=True)
        
        # 关闭截图窗口
        self.close()


    def quick_archive(self):
        if self.selection_rect.isNull():
            return
        
        # 立即开始收纳动画，给用户即时反馈
        self._start_archive_animation()
        
        # 异步执行实际的归档操作
        QTimer.singleShot(50, self._do_archive)
    
    def _start_archive_animation(self):
        """启动收纳动画 - 选区飞向归档图标"""
        self._archive_animating = True
        self._archive_progress = 0.0
        
        # 记录起始矩形
        self._archive_start_rect = QRect(self.selection_rect)
        
        # 计算归档图标的位置作为目标点
        btn = self.toolbar.findChild(QPushButton, "btn_archive")
        if btn:
            btn_center = btn.mapTo(self, btn.rect().center())
            self._archive_target = btn_center
        else:
            # 备用：工具栏中心
            self._archive_target = self.toolbar.geometry().center()
        
        # 隐藏工具栏
        self.toolbar.hide()
        
        # 创建进度动画（0->1）
        self._progress_anim = QPropertyAnimation(self, b"archive_progress")
        self._progress_anim.setDuration(300)
        self._progress_anim.setStartValue(0.0)
        self._progress_anim.setEndValue(1.0)
        self._progress_anim.setEasingCurve(QEasingCurve.Type.InQuad)
        self._progress_anim.start()
    
    def _get_archive_progress(self):
        return getattr(self, '_archive_progress', 0.0)
    
    def _set_archive_progress(self, value):
        self._archive_progress = value
        self.update()
    
    archive_progress = Property(float, _get_archive_progress, _set_archive_progress)
    
    def _do_archive(self):
        """实际执行归档操作"""
        pixmap = self._get_marked_pixmap()
        
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        pixmap.save(buffer, "JPEG", 85)
        image_data = buffer.data().data()
        buffer.close()
        
        try:
            add_record(image_data, "")
            # 动画完成后关闭
            QTimer.singleShot(200, self._close_after_archive)
        except Exception:
            self._archive_animating = False
            self.close()
    
    def _close_after_archive(self):
        app = QApplication.instance()
        if hasattr(app, '_capsule_widget') and app._capsule_widget:
            capsule = app._capsule_widget
            if capsule._saved_pos is not None:
                capsule.move(capsule._saved_pos)
            # 只有非强制隐藏模式才显示
            if not capsule._force_hidden:
                capsule.reveal(animated=True)
        self.close()

    def _open_prompt_editor(self):
        ScreenshotAICapsule.invalidate_prompts_cache()
        self._clear_ai_quick_buttons()
        self.prompt_settings_window = SettingsDialog(self)
        self.prompt_settings_window.show_tab('prompt')
        self.prompt_settings_window.show()
    
    def _do_ai_process(self, prompt: str = None, prompt_type: str = "text"):
        if self.selection_rect.isNull(): 
            return
        
        pixmap = self.full_screen_pixmap.copy(self._get_scaled_source_rect())
        
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        pixmap.save(buffer, "PNG")
        base64_data = base64.b64encode(buffer.data().data()).decode()
        buffer.close()
        
        app = QApplication.instance()
        if hasattr(app, '_capsule_widget') and app._capsule_widget:
            capsule = app._capsule_widget
            if capsule._saved_pos is not None:
                capsule.move(capsule._saved_pos)
            capsule.start_ai_processing(base64_data, prompt, prompt_type)
        
        self.close()

    def ocr_screenshot(self):
        """OCR 文字识别"""
        if self.selection_rect.isNull():
            return
        self._finish_temp_text_editing()
        cropped = self._get_marked_pixmap()
        
        # 在子线程中执行 OCR，避免阻塞 UI
        from PySide6.QtCore import QThread, Signal as QSignal
        
        class OcrWorker(QThread):
            finished = QSignal(str)
            error = QSignal(str)
            
            def __init__(self, pixmap):
                super().__init__()
                self._pixmap = pixmap
            
            def run(self):
                try:
                    from .ocr import recognize
                    text = recognize(self._pixmap)
                    self.finished.emit(text)
                except Exception as e:
                    self.error.emit(str(e))
        
        # 保持引用防止被回收
        self._ocr_worker = OcrWorker(cropped)
        self._ocr_worker.finished.connect(self._on_ocr_finished)
        self._ocr_worker.error.connect(self._on_ocr_error)
        self._ocr_worker.start()
    
    def _on_ocr_finished(self, text: str):
        """OCR 完成，将文本复制到剪贴板并显示结果"""
        if not text.strip():
            self._on_ocr_error("未识别到文字")
            return
        
        QGuiApplication.clipboard().setText(text)
        self._show_ocr_result(text)
    
    def _on_ocr_error(self, msg: str):
        """OCR 出错"""
        self._show_ocr_result(f"[识别失败] {msg}")
    
    def _show_ocr_result(self, text: str):
        """显示 OCR 结果浮窗"""
        from PySide6.QtWidgets import QTextEdit, QVBoxLayout, QHBoxLayout
        
        # 创建独立的结果窗口
        result_win = QWidget(None)
        result_win.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint)
        result_win.setWindowTitle("OCR 文字识别")
        result_win.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        result_win.setMinimumSize(400, 250)
        
        layout = QVBoxLayout(result_win)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        
        # 文本编辑框（可编辑、可复制）
        text_edit = QTextEdit()
        text_edit.setPlainText(text)
        text_edit.setFont(QFont(FONT_NAME, 12))
        text_edit.setStyleSheet("""
            QTextEdit {
                background: #1e1e1e;
                color: #d4d4d4;
                border: 1px solid #3c3c3c;
                border-radius: 6px;
                padding: 8px;
                selection-background-color: #264f78;
            }
        """)
        layout.addWidget(text_edit)
        
        # 底部按钮行
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)
        
        btn_copy = QPushButton("复制全部")
        btn_copy.setFixedHeight(32)
        btn_copy.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_copy.clicked.connect(lambda: (
            QGuiApplication.clipboard().setText(text_edit.toPlainText()),
            btn_copy.setText("已复制 ✓"),
            QTimer.singleShot(1500, lambda: btn_copy.setText("复制全部"))
        ))
        
        btn_close = QPushButton("关闭")
        btn_close.setFixedHeight(32)
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.clicked.connect(result_win.close)
        
        btn_style = """
            QPushButton {
                background: #0078d4;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 4px 16px;
                font-size: 13px;
            }
            QPushButton:hover { background: #1a86d9; }
            QPushButton:pressed { background: #005a9e; }
        """
        btn_copy.setStyleSheet(btn_style)
        btn_close.setStyleSheet(btn_style.replace("#0078d4", "#3c3c3c").replace("#1a86d9", "#4a4a4a").replace("#005a9e", "#2d2d2d"))
        
        btn_layout.addStretch()
        btn_layout.addWidget(btn_copy)
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)
        
        result_win.setStyleSheet("""
            QWidget {
                background: #252526;
                color: #d4d4d4;
            }
        """)
        
        result_win.resize(480, 320)
        result_win.show()
        
        # 保存引用防止回收
        app = QApplication.instance()
        if not hasattr(app, '_ocr_windows'):
            app._ocr_windows = []
        app._ocr_windows.append(result_win)
        result_win.destroyed.connect(lambda: (
            app._ocr_windows.remove(result_win) if result_win in app._ocr_windows else None
        ))
        
        self.close()

    def finish_screenshot(self):
        self._finish_temp_text_editing()  # 先结束文本编辑
        cropped = self._get_marked_pixmap()
        QGuiApplication.clipboard().setPixmap(cropped)
        self.close()

    def open_editor(self):
        if self.selection_rect.isNull():
            return
        self._finish_temp_text_editing()  # 先结束文本编辑
        cropped = self._get_marked_pixmap()
        # 设置 devicePixelRatio 使编辑器中图片尺寸与选区一致
        cropped.setDevicePixelRatio(self.scale_x)
        editor = EditorWindow(cropped)
        editor.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        editor.show()
        app = QApplication.instance()
        if not hasattr(app, '_editor_windows'):
            app._editor_windows = []
        app._editor_windows.append(editor)
        
        def on_editor_closed():
            if editor in app._editor_windows:
                app._editor_windows.remove(editor)
            if hasattr(app, '_capsule_widget') and app._capsule_widget:
                app._capsule_widget._restore_position()
        
        editor.destroyed.connect(on_editor_closed)
        self.close()

    def open_in_photoshop(self):
        """将标注后的截图临时保存为 PNG，并用 Photoshop 打开"""
        if self.selection_rect.isNull():
            return

        try:
            pixmap = self._get_marked_pixmap()
            if pixmap is None or pixmap.isNull():
                return

            pixmap.setDevicePixelRatio(self.scale_x)

            from config import ps_config
            ps_exe = ps_config.get_ps_path()

            if not ps_exe or not os.path.exists(ps_exe):
                file_path, _ = QFileDialog.getOpenFileName(
                    self,
                    "选择 Photoshop.exe",
                    r"C:\Program Files\Adobe",
                    "Photoshop.exe (*.exe);;所有文件 (*.*)",
                )
                if not file_path or not os.path.exists(file_path):
                    return
                ps_config.set_ps_path(file_path)
                ps_exe = file_path

            temp_dir = os.path.join(os.getenv("TEMP", "."), "Artco")
            os.makedirs(temp_dir, exist_ok=True)
            file_path = os.path.join(temp_dir, f"artco_ps_{uuid.uuid4().hex}.png")
            pixmap.save(file_path, "PNG")

            subprocess.Popen([ps_exe, file_path])
            self.close()
        except Exception as e:
            QMessageBox.warning(self, "打开失败", f"无法启动 Photoshop：\n{e}")
