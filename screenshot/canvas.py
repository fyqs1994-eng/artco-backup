"""
截图模块 - 编辑器画布
"""

import math

from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QRect, QSize, Signal, QPoint, QPointF, QTimer
from PySide6.QtGui import QColor, QPainter, QPen, QBrush, QPixmap, QKeyEvent, QFont, QPainterPath, QFontMetrics, QPolygonF

from .marks import MarkObject, NumberDot, RectMark, ArrowMark, FreehandMark, TextMark, FONT_NAME


class EditorCanvas(QWidget):
    """可交互画布"""
    
    TOOL_SELECT = 0
    TOOL_NUMBER = 1
    TOOL_RECT = 2
    TOOL_ARROW = 3
    TOOL_FREEHAND = 4
    TOOL_TEXT = 5
    TOOL_ERASER = 6
    
    # 信号：缩放变化、平移请求、序号点变化
    scale_changed = Signal(float)
    pan_requested = Signal(int, int)  # delta_x, delta_y
    number_dots_changed = Signal()  # 序号点增删时触发
    
    def __init__(self, pixmap: QPixmap):
        super().__init__()
        self.original_pixmap = pixmap
        # 获取 devicePixelRatio，用于计算逻辑尺寸
        self._device_pixel_ratio = pixmap.devicePixelRatio()
        # 使用逻辑尺寸作为基础尺寸
        self.base_size = QSize(
            int(pixmap.width() / self._device_pixel_ratio),
            int(pixmap.height() / self._device_pixel_ratio)
        )
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        
        # 缩放相关
        self._scale = 1.0
        self._min_scale = 0.25
        self._max_scale = 4.0
        self._update_canvas_size()
        
        self.marks: list[MarkObject] = []
        self.current_tool = self.TOOL_SELECT
        self.number_counter = 1
        
        # 撤销栈
        self._undo_stack: list[tuple] = []  # [(action, data), ...]
        self._max_undo = 50
        
        # 中键平移
        self._is_panning = False
        self._pan_start = QPoint()
        
        self.selected_mark: MarkObject = None
        self.is_drawing = False
        self.draw_start = QPoint()
        self.temp_points = []
        self._mark_color = QColor(255, 50, 50)  # 当前标记颜色
        
        # 即时渲染文本输入状态
        self._text_font_size = TextMark.default_font_size
        self._text_editing = False  # 是否正在输入文字
        self._text_buffer = ""  # 输入的文字缓冲
        self._text_preedit = ""  # IME 预编辑文本（拼音等）
        self._text_cursor_visible = True  # 光标闪烁状态
        self._text_cursor_timer = QTimer(self)
        self._text_cursor_timer.timeout.connect(self._toggle_text_cursor)
        self.editing_text_mark: TextMark = None
    
    def _update_canvas_size(self):
        """根据缩放更新画布大小"""
        new_width = int(self.base_size.width() * self._scale)
        new_height = int(self.base_size.height() * self._scale)
        self.setFixedSize(new_width, new_height)
    
    def set_scale(self, scale: float):
        """设置缩放比例"""
        scale = max(self._min_scale, min(self._max_scale, scale))
        if abs(scale - self._scale) < 0.01:
            return
        self._scale = scale
        self._update_canvas_size()
        self.scale_changed.emit(self._scale)
        self.update()
    
    def zoom_in(self):
        """放大"""
        self.set_scale(self._scale * 1.2)
    
    def zoom_out(self):
        """缩小"""
        self.set_scale(self._scale / 1.2)
    
    def zoom_reset(self):
        """重置缩放"""
        self.set_scale(1.0)
    
    def _push_undo(self, action: str, data):
        """添加撤销记录"""
        self._undo_stack.append((action, data))
        if len(self._undo_stack) > self._max_undo:
            self._undo_stack.pop(0)
    
    def undo(self):
        """撤销操作"""
        if not self._undo_stack:
            return
        action, data = self._undo_stack.pop()
        
        if action == 'add':
            # 撤销添加 -> 删除
            mark = data
            if mark in self.marks:
                self.marks.remove(mark)
                # 如果是序号点，需要重新编号
                if isinstance(mark, NumberDot):
                    self._renumber_dots()
        elif action == 'delete':
            # 撤销删除 -> 恢复
            mark, index = data
            self.marks.insert(min(index, len(self.marks)), mark)
            # 如果是序号点，需要重新编号
            if isinstance(mark, NumberDot):
                self._renumber_dots()
        elif action == 'move':
            # 撤销移动 -> 恢复位置
            mark, old_pos = data
            if isinstance(mark, NumberDot):
                mark.center = old_pos
            elif isinstance(mark, RectMark):
                mark.rect = old_pos
            elif isinstance(mark, ArrowMark):
                mark.start, mark.end = old_pos
            elif isinstance(mark, FreehandMark):
                mark.points = old_pos
            elif isinstance(mark, TextMark):
                mark.pos = old_pos
        
        self._deselect_all()
        self.update()
    
    def _renumber_dots(self):
        """重新编号所有序号点"""
        dots = [m for m in self.marks if isinstance(m, NumberDot)]
        for i, dot in enumerate(dots, 1):
            dot.number = i
        self.number_counter = len(dots) + 1
        self.number_dots_changed.emit()  # 通知序号点变化
    
    def set_mark_color(self, color: QColor):
        """设置当前标记颜色"""
        self._mark_color = color
    
    def set_tool(self, tool: int):
        self.current_tool = tool
        self._finish_text_editing()
        self._deselect_all()
        # 橡皮擦工具使用特殊光标
        if tool == self.TOOL_ERASER:
            self.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)
        self.update()
    
    def _deselect_all(self):
        for m in self.marks:
            m.selected = False
        self.selected_mark = None
    
    def _find_mark_at(self, pos: QPoint) -> MarkObject:
        for mark in reversed(self.marks):
            if mark.contains(pos):
                return mark
        return None
    
    def _screen_to_canvas(self, pos: QPoint) -> QPoint:
        """屏幕坐标转画布坐标（考虑缩放）"""
        return QPoint(int(pos.x() / self._scale), int(pos.y() / self._scale))
    
    def _canvas_to_screen(self, pos: QPoint) -> QPoint:
        """画布坐标转屏幕坐标"""
        return QPoint(int(pos.x() * self._scale), int(pos.y() * self._scale))
    
    def delete_selected(self):
        if self.selected_mark and self.selected_mark in self.marks:
            index = self.marks.index(self.selected_mark)
            self._push_undo('delete', (self.selected_mark, index))
            self.marks.remove(self.selected_mark)
            # 如果删除的是序号点，重新编号
            if isinstance(self.selected_mark, NumberDot):
                self._renumber_dots()
            self.selected_mark = None
            self.update()
    
    def _erase_mark_at(self, pos: QPoint):
        """橡皮擦：删除指定位置的标记"""
        mark = self._find_mark_at(pos)
        if mark:
            index = self.marks.index(mark)
            self._push_undo('delete', (mark, index))
            self.marks.remove(mark)
            # 如果删除的是序号点，重新编号
            if isinstance(mark, NumberDot):
                self._renumber_dots()
            self.update()
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)  # 高质量缩放
        
        # 绘制背景图 - 直接绘制到当前画布大小，忽略 devicePixelRatio
        # 因为画布大小已经是逻辑尺寸 * _scale
        painter.drawPixmap(self.rect(), self.original_pixmap)
        
        # 应用缩放变换绘制标记
        painter.scale(self._scale, self._scale)
        
        for mark in self.marks:
            # 正在编辑的文本标记不绘制（由即时渲染绘制）
            if mark == self.editing_text_mark and self._text_editing:
                continue
            mark.draw(painter)
        
        # 即时渲染正在输入的文本
        if self._text_editing and self.editing_text_mark:
            self._draw_editing_text(painter)
        
        if self.is_drawing:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            
            if self.current_tool == self.TOOL_RECT:
                pen = QPen(self._mark_color, 3)
                painter.setPen(pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(QRect(self.draw_start, self.draw_end).normalized())
            elif self.current_tool == self.TOOL_ARROW:
                # 与 ArrowMark.draw() 保持一致的绘制
                angle = math.atan2(self.draw_end.y() - self.draw_start.y(), 
                                   self.draw_end.x() - self.draw_start.x())
                arrow_size = 16
                tip = QPointF(self.draw_end)
                p1 = QPointF(self.draw_end.x() - arrow_size * math.cos(angle - math.pi/7),
                             self.draw_end.y() - arrow_size * math.sin(angle - math.pi/7))
                p2 = QPointF(self.draw_end.x() - arrow_size * math.cos(angle + math.pi/7),
                             self.draw_end.y() - arrow_size * math.sin(angle + math.pi/7))
                line_end = QPointF((p1.x() + p2.x()) / 2, (p1.y() + p2.y()) / 2)
                pen = QPen(self._mark_color, 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap)
                painter.setPen(pen)
                painter.drawLine(QPointF(self.draw_start), line_end)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(self._mark_color)
                painter.drawPolygon(QPolygonF([tip, p1, p2]))
            elif self.current_tool == self.TOOL_FREEHAND and len(self.temp_points) > 1:
                # 与 FreehandMark.draw() 保持一致的中点二次贝塞尔平滑
                pen = QPen(self._mark_color, 3, Qt.PenStyle.SolidLine, 
                          Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
                painter.setPen(pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                path = QPainterPath()
                pts = self.temp_points
                n = len(pts)
                path.moveTo(pts[0])
                if n == 2:
                    path.lineTo(pts[1])
                else:
                    mid = QPointF((pts[0].x() + pts[1].x()) / 2.0,
                                  (pts[0].y() + pts[1].y()) / 2.0)
                    path.lineTo(mid)
                    for i in range(1, n - 1):
                        mid = QPointF((pts[i].x() + pts[i + 1].x()) / 2.0,
                                      (pts[i].y() + pts[i + 1].y()) / 2.0)
                        path.quadTo(QPointF(pts[i].x(), pts[i].y()), mid)
                    path.lineTo(pts[-1])
                painter.drawPath(path)
    
    def _draw_editing_text(self, painter: QPainter):
        """绘制正在编辑的文本（即时渲染）"""
        mark = self.editing_text_mark
        # 缓存字体和 metrics，避免每帧重建
        if not hasattr(self, '_cached_edit_font') or self._cached_edit_font_size != mark.font_size:
            self._cached_edit_font = QFont(FONT_NAME, mark.font_size, QFont.Weight.Normal)
            self._cached_edit_metrics = QFontMetrics(self._cached_edit_font)
            self._cached_edit_font_size = mark.font_size
        font = self._cached_edit_font
        metrics = self._cached_edit_metrics
        painter.setFont(font)
        painter.setPen(mark.color)
        # 合并已输入文本和预编辑文本
        display_text = self._text_buffer + self._text_preedit
        lines = display_text.split('\n')
        line_height = metrics.height()
        
        x, y = mark.pos.x(), mark.pos.y()
        
        # 计算光标应该在的位置（在已确认文本之后，预编辑文本之前）
        confirmed_lines = self._text_buffer.split('\n')
        
        for i, line in enumerate(lines):
            text_y = y + (i + 1) * line_height
            
            # 检查这行是否包含预编辑文本
            if i == len(confirmed_lines) - 1 and self._text_preedit:
                # 先绘制确认的文本
                confirmed_part = confirmed_lines[-1] if confirmed_lines else ""
                painter.drawText(x, text_y, confirmed_part)
                
                # 绘制预编辑文本（带下划线）
                preedit_x = x + metrics.horizontalAdvance(confirmed_part)
                painter.drawText(preedit_x, text_y, self._text_preedit)
                # 绘制下划线表示预编辑状态
                preedit_width = metrics.horizontalAdvance(self._text_preedit)
                painter.drawLine(int(preedit_x), int(text_y + 2), 
                               int(preedit_x + preedit_width), int(text_y + 2))
                
                # 光标在预编辑文本之后
                if self._text_cursor_visible:
                    cursor_x = preedit_x + preedit_width
                    cursor_y1 = y + i * line_height + 2
                    cursor_y2 = cursor_y1 + line_height
                    painter.setPen(QPen(mark.color, 2))
                    painter.drawLine(int(cursor_x), int(cursor_y1), int(cursor_x), int(cursor_y2))
            else:
                painter.drawText(x, text_y, line)
                
                # 绘制光标（在最后一行末尾，且没有预编辑文本时）
                if i == len(lines) - 1 and self._text_cursor_visible and not self._text_preedit:
                    cursor_x = x + metrics.horizontalAdvance(line)
                    cursor_y1 = y + i * line_height + 2
                    cursor_y2 = cursor_y1 + line_height
                    painter.setPen(QPen(mark.color, 2))
                    painter.drawLine(int(cursor_x), int(cursor_y1), int(cursor_x), int(cursor_y2))
    
    def _toggle_text_cursor(self):
        """切换光标可见性"""
        self._text_cursor_visible = not self._text_cursor_visible
        if self._text_editing:
            self.update()
    
    def mousePressEvent(self, event):
        # 中键按下 - 开始平移
        if event.button() == Qt.MouseButton.MiddleButton:
            self._is_panning = True
            self._pan_start = event.globalPosition().toPoint()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return
        
        if event.button() != Qt.MouseButton.LeftButton:
            return
        
        screen_pos = event.pos()
        pos = self._screen_to_canvas(screen_pos)  # 转换为画布坐标
        self._finish_text_editing()
        
        if self.current_tool == self.TOOL_SELECT:
            self._deselect_all()
            mark = self._find_mark_at(pos)
            if mark:
                mark.selected = True
                self.selected_mark = mark
                self.drag_start = pos
                # 记录移动前的位置用于撤销
                if isinstance(mark, NumberDot):
                    self._move_start_pos = QPoint(mark.center)
                elif isinstance(mark, RectMark):
                    self._move_start_pos = QRect(mark.rect)
                elif isinstance(mark, ArrowMark):
                    self._move_start_pos = (QPoint(mark.start), QPoint(mark.end))
                elif isinstance(mark, FreehandMark):
                    self._move_start_pos = [QPoint(p) for p in mark.points]
                elif isinstance(mark, TextMark):
                    self._move_start_pos = QPoint(mark.pos)
            self.update()
        
        elif self.current_tool == self.TOOL_ERASER:
            self._erase_mark_at(pos)
        
        elif self.current_tool == self.TOOL_NUMBER:
            dot = NumberDot(pos, self.number_counter, self._mark_color)
            self.marks.append(dot)
            self._push_undo('add', dot)
            self.number_counter += 1
            self.number_dots_changed.emit()  # 通知序号点变化
            self.update()
        
        elif self.current_tool in (self.TOOL_RECT, self.TOOL_ARROW):
            self.is_drawing = True
            self.draw_start = pos
            self.draw_end = pos
        
        elif self.current_tool == self.TOOL_FREEHAND:
            self.is_drawing = True
            self.temp_points = [pos]
        
        elif self.current_tool == self.TOOL_TEXT:
            text_mark = TextMark(pos, "", self._mark_color)
            self.marks.append(text_mark)
            self._push_undo('add', text_mark)
            self.editing_text_mark = text_mark
            self._start_text_editing()
    
    def mouseMoveEvent(self, event):
        # 中键平移
        if self._is_panning and event.buttons() & Qt.MouseButton.MiddleButton:
            current_pos = event.globalPosition().toPoint()
            delta = current_pos - self._pan_start
            self._pan_start = current_pos
            self.pan_requested.emit(delta.x(), delta.y())
            return
        
        screen_pos = event.pos()
        pos = self._screen_to_canvas(screen_pos)  # 转换为画布坐标
        
        if self.current_tool == self.TOOL_SELECT and self.selected_mark and event.buttons() & Qt.MouseButton.LeftButton:
            delta = pos - self.drag_start
            self.selected_mark.move_by(delta)
            self.drag_start = pos
            self.update()
        
        elif self.current_tool == self.TOOL_ERASER and event.buttons() & Qt.MouseButton.LeftButton:
            self._erase_mark_at(pos)
        
        elif self.is_drawing:
            if self.current_tool in (self.TOOL_RECT, self.TOOL_ARROW):
                self.draw_end = pos
            elif self.current_tool == self.TOOL_FREEHAND:
                # 最小距离过滤，减少冗余点以提升平滑效果
                if self.temp_points:
                    last = self.temp_points[-1]
                    if (pos.x() - last.x())**2 + (pos.y() - last.y())**2 < 9:
                        return
                self.temp_points.append(pos)
            self.update()
    
    def mouseReleaseEvent(self, event):
        # 中键释放 - 结束平移
        if event.button() == Qt.MouseButton.MiddleButton:
            self._is_panning = False
            # 恢复光标
            if self.current_tool == self.TOOL_ERASER:
                self.setCursor(Qt.CursorShape.CrossCursor)
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)
            return
        
        if event.button() != Qt.MouseButton.LeftButton:
            return
        
        screen_pos = event.pos()
        pos = self._screen_to_canvas(screen_pos)  # 转换为画布坐标
        
        # 选择工具：记录移动操作到撤销栈
        if self.current_tool == self.TOOL_SELECT and self.selected_mark and hasattr(self, '_move_start_pos'):
            mark = self.selected_mark
            moved = False
            if isinstance(mark, NumberDot) and mark.center != self._move_start_pos:
                moved = True
            elif isinstance(mark, RectMark) and mark.rect != self._move_start_pos:
                moved = True
            elif isinstance(mark, ArrowMark):
                old_start, old_end = self._move_start_pos
                if mark.start != old_start or mark.end != old_end:
                    moved = True
            elif isinstance(mark, FreehandMark) and mark.points != self._move_start_pos:
                moved = True
            elif isinstance(mark, TextMark) and mark.pos != self._move_start_pos:
                moved = True
            
            if moved:
                self._push_undo('move', (mark, self._move_start_pos))
            delattr(self, '_move_start_pos')
        
        if self.is_drawing:
            if self.current_tool == self.TOOL_RECT:
                rect = QRect(self.draw_start, pos).normalized()
                if rect.width() > 5 and rect.height() > 5:
                    mark = RectMark(rect, self._mark_color)
                    self.marks.append(mark)
                    self._push_undo('add', mark)
            
            elif self.current_tool == self.TOOL_ARROW:
                if (pos - self.draw_start).manhattanLength() > 10:
                    mark = ArrowMark(self.draw_start, pos, self._mark_color)
                    self.marks.append(mark)
                    self._push_undo('add', mark)
            
            elif self.current_tool == self.TOOL_FREEHAND:
                if len(self.temp_points) > 2:
                    mark = FreehandMark(self.temp_points.copy(), self._mark_color)
                    self.marks.append(mark)
                    self._push_undo('add', mark)
                self.temp_points = []
            
            self.is_drawing = False
            self.update()
    
    def wheelEvent(self, event):
        """滚轮事件"""
        # 文本输入时 Ctrl+滚轮调整字体大小
        if self._text_editing and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = 2 if event.angleDelta().y() > 0 else -2
            self._change_text_font_size(delta)
            event.accept()
            return
        
        # 普通滚轮缩放
        delta = event.angleDelta().y()
        if delta > 0:
            self.zoom_in()
        else:
            self.zoom_out()
        event.accept()
    
    def _start_text_editing(self):
        """开始文本即时渲染输入"""
        self._text_editing = True
        self._text_buffer = ""
        self._text_preedit = ""  # IME 预编辑文本
        self._text_cursor_visible = True
        self._text_cursor_timer.start(530)  # 光标闪烁间隔
        if self.editing_text_mark:
            self.editing_text_mark.is_editing = True
            self.editing_text_mark.font_size = self._text_font_size
        # 启用输入法
        self.setAttribute(Qt.WidgetAttribute.WA_InputMethodEnabled, True)
        self.setFocus()
        self.update()
    
    def _finish_text_editing(self):
        """完成文本输入"""
        if not self._text_editing:
            return
        
        self._text_cursor_timer.stop()
        self._text_editing = False
        self._text_preedit = ""  # 清空预编辑
        
        if self.editing_text_mark:
            text = self._text_buffer.strip()
            if text:
                self.editing_text_mark.text = text
            else:
                # 没有输入文字，删除标记
                if self.editing_text_mark in self.marks:
                    self.marks.remove(self.editing_text_mark)
                    # 撤销栈也移除
                    if self._undo_stack and self._undo_stack[-1] == ('add', self.editing_text_mark):
                        self._undo_stack.pop()
            self.editing_text_mark.is_editing = False
            self.editing_text_mark = None
        
        self._text_buffer = ""
        self.update()
    
    def _change_text_font_size(self, delta: int):
        """调整文本字体大小"""
        old_size = self._text_font_size
        self._text_font_size = max(TextMark.MIN_FONT_SIZE, 
                                    min(TextMark.MAX_FONT_SIZE, self._text_font_size + delta))
        if self._text_font_size != old_size:
            TextMark.default_font_size = self._text_font_size
            if self.editing_text_mark:
                self.editing_text_mark.font_size = self._text_font_size
            self.update()
    
    def keyPressEvent(self, event: QKeyEvent):
        """键盘事件 - 处理即时渲染文本输入"""
        # 如果正在输入文本
        if self._text_editing:
            key = event.key()
            modifiers = event.modifiers()
            
            if key == Qt.Key.Key_Return:
                if modifiers & Qt.KeyboardModifier.ControlModifier:
                    # Ctrl+Enter 换行
                    self._text_buffer += '\n'
                    self.update()
                else:
                    # Enter 确认
                    self._finish_text_editing()
                return
            
            elif key == Qt.Key.Key_Escape:
                # 取消输入
                self._text_buffer = ""
                self._finish_text_editing()
                return
            
            elif key == Qt.Key.Key_Backspace:
                # 删除
                if self._text_buffer:
                    self._text_buffer = self._text_buffer[:-1]
                    self.update()
                return
            
            else:
                # 普通字符输入
                text = event.text()
                if text and text.isprintable():
                    self._text_buffer += text
                    # 显示光标
                    self._text_cursor_visible = True
                    self.update()
                return
        
        # 非文本输入状态的快捷键
        if event.key() == Qt.Key.Key_Delete or event.key() == Qt.Key.Key_Backspace:
            self.delete_selected()
        elif event.key() == Qt.Key.Key_Z and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.undo()
        else:
            super().keyPressEvent(event)
    
    def inputMethodEvent(self, event):
        """处理输入法事件（中文等IME输入）"""
        if self._text_editing:
            # 获取预编辑文本（正在输入的拼音等）
            self._text_preedit = event.preeditString()
            # 获取确认的文本
            commit_text = event.commitString()
            if commit_text:
                self._text_buffer += commit_text
                self._text_preedit = ""
            self._text_cursor_visible = True
            self.update()
            event.accept()
        else:
            super().inputMethodEvent(event)
    
    def inputMethodQuery(self, query):
        """提供输入法查询信息（光标位置等）"""
        from PySide6.QtCore import Qt
        if query == Qt.InputMethodQuery.ImEnabled:
            return self._text_editing
        elif query == Qt.InputMethodQuery.ImCursorRectangle:
            # 返回输入光标位置
            if self._text_editing and self.editing_text_mark:
                mark = self.editing_text_mark
                font = QFont(FONT_NAME, mark.font_size)
                metrics = QFontMetrics(font)
                lines = self._text_buffer.split('\n')
                line_height = metrics.height()
                
                # 计算光标位置
                canvas_x = mark.pos.x()
                canvas_y = mark.pos.y()
                if lines:
                    last_line = lines[-1]
                    canvas_x += metrics.horizontalAdvance(last_line)
                    canvas_y += (len(lines) - 1) * line_height
                
                # 转换为屏幕坐标
                screen_pos = self._canvas_to_screen(QPointF(canvas_x, canvas_y))
                return QRect(int(screen_pos.x()), int(screen_pos.y()), 2, line_height)
        return super().inputMethodQuery(query)
