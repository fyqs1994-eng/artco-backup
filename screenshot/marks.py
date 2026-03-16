"""
截图模块 - 标记对象系统
"""

import math

from PySide6.QtCore import Qt, QRect, QPoint, QPointF
from PySide6.QtGui import QColor, QPainter, QPen, QBrush, QFont, QPainterPath, QPolygonF, QFontMetrics

FONT_NAME = "Microsoft YaHei"


class MarkObject:
    """标记对象基类"""
    def __init__(self, color=QColor(255, 50, 50)):
        self.color = color
        self.selected = False
    
    def contains(self, point: QPoint) -> bool:
        raise NotImplementedError
    
    def move_by(self, delta: QPoint):
        raise NotImplementedError
    
    def draw(self, painter: QPainter):
        raise NotImplementedError
    
    def get_bounds(self) -> QRect:
        raise NotImplementedError


class NumberDot(MarkObject):
    """序号点标记"""
    RADIUS = 16
    # 类级别缓存字体，所有实例共享
    _cached_font = None
    
    @classmethod
    def _get_font(cls):
        if cls._cached_font is None:
            cls._cached_font = QFont(FONT_NAME, 12, QFont.Weight.Bold)
        return cls._cached_font
    
    def __init__(self, center: QPoint, number: int, color=QColor(255, 50, 50)):
        super().__init__(color)
        self.center = center
        self.number = number
    
    def contains(self, point: QPoint) -> bool:
        dx = point.x() - self.center.x()
        dy = point.y() - self.center.y()
        return (dx * dx + dy * dy) <= (self.RADIUS * self.RADIUS)
    
    def move_by(self, delta: QPoint):
        self.center = self.center + delta
    
    def draw(self, painter: QPainter):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.selected:
            painter.setPen(QPen(QColor(0, 120, 215), 3))
        else:
            painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(self.color))
        painter.drawEllipse(self.center, self.RADIUS, self.RADIUS)
        painter.setPen(QPen(Qt.GlobalColor.white))
        painter.setFont(self._get_font())
        text_rect = QRect(self.center.x() - self.RADIUS, self.center.y() - self.RADIUS,
                          self.RADIUS * 2, self.RADIUS * 2)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, str(self.number))
    
    def get_bounds(self) -> QRect:
        return QRect(self.center.x() - self.RADIUS, self.center.y() - self.RADIUS,
                     self.RADIUS * 2, self.RADIUS * 2)


class RectMark(MarkObject):
    """矩形框标记"""
    def __init__(self, rect: QRect, color=QColor(255, 50, 50)):
        super().__init__(color)
        self.rect = rect
    
    def contains(self, point: QPoint) -> bool:
        r = self.rect.normalized()
        tolerance = 10
        inner = r.adjusted(tolerance, tolerance, -tolerance, -tolerance)
        return r.contains(point) and not inner.contains(point)
    
    def move_by(self, delta: QPoint):
        self.rect.translate(delta)
    
    def draw(self, painter: QPainter):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(self.color, 3)
        if self.selected:
            pen.setColor(QColor(0, 120, 215))
            pen.setWidth(4)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(self.rect)
    
    def get_bounds(self) -> QRect:
        return self.rect.normalized()


class ArrowMark(MarkObject):
    """箭头标记"""
    def __init__(self, start: QPoint, end: QPoint, color=QColor(255, 50, 50)):
        super().__init__(color)
        self.start = start
        self.end = end
    
    def contains(self, point: QPoint) -> bool:
        x0, y0 = point.x(), point.y()
        x1, y1 = self.start.x(), self.start.y()
        x2, y2 = self.end.x(), self.end.y()
        
        dx, dy = x2 - x1, y2 - y1
        length_sq = dx * dx + dy * dy
        if length_sq == 0:
            return math.sqrt((x0 - x1)**2 + (y0 - y1)**2) < 15
        
        t = max(0, min(1, ((x0 - x1) * dx + (y0 - y1) * dy) / length_sq))
        proj_x = x1 + t * dx
        proj_y = y1 + t * dy
        dist = math.sqrt((x0 - proj_x)**2 + (y0 - proj_y)**2)
        return dist < 15
    
    def move_by(self, delta: QPoint):
        self.start = self.start + delta
        self.end = self.end + delta
    
    def draw(self, painter: QPainter):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = self.color
        width = 3
        if self.selected:
            color = QColor(0, 120, 215)
            width = 4
        
        angle = math.atan2(self.end.y() - self.start.y(), self.end.x() - self.start.x())
        arrow_size = 16
        
        # 箭头三角形三个顶点
        tip = QPointF(self.end)
        p1 = QPointF(self.end.x() - arrow_size * math.cos(angle - math.pi/7),
                     self.end.y() - arrow_size * math.sin(angle - math.pi/7))
        p2 = QPointF(self.end.x() - arrow_size * math.cos(angle + math.pi/7),
                     self.end.y() - arrow_size * math.sin(angle + math.pi/7))
        
        # 线条终点停在箭头底部中点，避免线条盖住箭尖
        line_end = QPointF((p1.x() + p2.x()) / 2, (p1.y() + p2.y()) / 2)
        
        # 绘制线条（FlatCap 避免端头突出）
        pen = QPen(color, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap)
        painter.setPen(pen)
        painter.drawLine(QPointF(self.start), line_end)
        
        # 绘制实心箭头三角形
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(color))
        painter.drawPolygon(QPolygonF([tip, p1, p2]))
    
    def get_bounds(self) -> QRect:
        return QRect(self.start, self.end).normalized().adjusted(-20, -20, 20, 20)


class FreehandMark(MarkObject):
    """涂鸦/画笔标记"""
    def __init__(self, points: list, color=QColor(255, 50, 50)):
        super().__init__(color)
        self._points = points
        self._cached_path = None  # 缓存的 QPainterPath
        self._cached_bounds = None  # 缓存的边界矩形
        self._invalidate_cache()
    
    @property
    def points(self):
        return self._points
    
    @points.setter
    def points(self, value):
        self._points = value
        self._invalidate_cache()
    
    def _invalidate_cache(self):
        """使缓存失效"""
        self._cached_path = None
        self._cached_bounds = None
    
    def _get_path(self) -> QPainterPath:
        """获取缓存的路径，使用中点二次贝塞尔平滑
        
        原理：以相邻两点的中点作为曲线的起止点，以原始采样点作为控制点，
        用 quadTo 绘制二次贝塞尔曲线。无论采样点多密集都能产生圆润效果。
        """
        if self._cached_path is None:
            self._cached_path = QPainterPath()
            pts = self._points
            n = len(pts)
            if n >= 2:
                self._cached_path.moveTo(pts[0])
                if n == 2:
                    self._cached_path.lineTo(pts[1])
                else:
                    # 第一段：从起点到第一个中点
                    mid = QPointF((pts[0].x() + pts[1].x()) / 2.0,
                                  (pts[0].y() + pts[1].y()) / 2.0)
                    self._cached_path.lineTo(mid)
                    
                    # 中间段：以采样点为控制点，中点为曲线端点
                    for i in range(1, n - 1):
                        mid = QPointF((pts[i].x() + pts[i + 1].x()) / 2.0,
                                      (pts[i].y() + pts[i + 1].y()) / 2.0)
                        self._cached_path.quadTo(QPointF(pts[i].x(), pts[i].y()), mid)
                    
                    # 最后一段：到终点
                    self._cached_path.lineTo(pts[-1])
        return self._cached_path
    
    def contains(self, point: QPoint) -> bool:
        for p in self._points:
            if math.sqrt((point.x() - p.x())**2 + (point.y() - p.y())**2) < 10:
                return True
        return False
    
    def move_by(self, delta: QPoint):
        self._points = [p + delta for p in self._points]
        self._invalidate_cache()
    
    def draw(self, painter: QPainter):
        if len(self._points) < 2:
            return
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(self.color, 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        if self.selected:
            pen.setColor(QColor(0, 120, 215))
            pen.setWidth(4)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        
        # 使用缓存的路径
        painter.drawPath(self._get_path())
    
    def get_bounds(self) -> QRect:
        if not self._points:
            return QRect()
        if self._cached_bounds is None:
            xs = [p.x() for p in self._points]
            ys = [p.y() for p in self._points]
            self._cached_bounds = QRect(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))
        return self._cached_bounds


class TextMark(MarkObject):
    """文字标记 - 支持多行和动态字体大小"""
    
    # 类级别的默认字体大小，可被滚轮调整
    default_font_size = 18
    MIN_FONT_SIZE = 10
    MAX_FONT_SIZE = 72
    
    def __init__(self, pos: QPoint, text: str = "", color=QColor(255, 50, 50)):
        super().__init__(color)
        self.pos = pos
        self.text = text
        self._font_size = TextMark.default_font_size
        self.font = QFont(FONT_NAME, self._font_size, QFont.Weight.Normal)
        self._cached_metrics = None  # 缓存 QFontMetrics
        self.padding = 4
        self.is_editing = False
    
    @property
    def font_size(self):
        return self._font_size
    
    @font_size.setter
    def font_size(self, value):
        new_size = max(self.MIN_FONT_SIZE, min(self.MAX_FONT_SIZE, value))
        if new_size != self._font_size:
            self._font_size = new_size
            self.font.setPointSize(self._font_size)
            self._cached_metrics = None  # 字体大小变化时清除缓存
    
    def _get_metrics(self) -> QFontMetrics:
        """获取缓存的 QFontMetrics"""
        if self._cached_metrics is None:
            self._cached_metrics = QFontMetrics(self.font)
        return self._cached_metrics
    
    def contains(self, point: QPoint) -> bool:
        return self.get_bounds().contains(point)
    
    def move_by(self, delta: QPoint):
        self.pos = self.pos + delta
    
    def draw(self, painter: QPainter):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.setFont(self.font)
        
        display_text = self.text if self.text else ""
        if not display_text and not self.is_editing:
            return
        
        # 分割多行文本
        lines = display_text.split('\n') if display_text else [""]
        metrics = self._get_metrics()
        line_height = metrics.height()
        
        # 计算最大行宽
        max_width = max(metrics.horizontalAdvance(line) for line in lines) if lines else metrics.horizontalAdvance("A")
        total_height = line_height * len(lines)
        
        draw_rect = QRect(
            self.pos.x(), self.pos.y(),
            max_width + self.padding * 2,
            total_height + self.padding * 2
        )
        
        if self.selected:
            pen = QPen(QColor(0, 120, 215), 2, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(draw_rect.adjusted(-2, -2, 2, 2))
        
        if display_text:
            painter.setPen(self.color)
            text_x = self.pos.x() + self.padding
            for i, line in enumerate(lines):
                text_y = self.pos.y() + self.padding + metrics.ascent() + i * line_height
                painter.drawText(text_x, int(text_y), line)
    
    def get_bounds(self) -> QRect:
        metrics = self._get_metrics()
        display_text = self.text if self.text else "A"
        lines = display_text.split('\n')
        max_width = max(metrics.horizontalAdvance(line) for line in lines)
        total_height = metrics.height() * len(lines)
        return QRect(
            self.pos.x(), self.pos.y(),
            max_width + self.padding * 2,
            total_height + self.padding * 2
        )
