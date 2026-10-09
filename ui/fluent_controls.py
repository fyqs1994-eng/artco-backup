"""
表单控件（替代 qfluentwidgets）

背景：qfluentwidgets 的资源文件 `_rc/resource.py` 一导入就占约 800 MB 提交内存，
而 Artco 只用了它 8 个基础控件。这里基于 PySide6 原生控件 1:1 复刻其浅色主题外观
（QSS 取自 qfluentwidgets 原版 light 主题，绘制逻辑与原版一致），对外类名与常用 API 保持不变，
调用方只需把 `from qfluentwidgets import X` 改成 `from ui.fluent_controls import X`。

与原版的有意差异：
- ComboBox / EditableComboBox 基于 QComboBox（原版基于 QPushButton / LineEdit），
  因而 addItem(text, userData)、setEditText 等原生 API 行为正确。
- 下拉弹层为样式化的原生列表，没有原版的阴影与展开动画。
"""

from PySide6.QtCore import Qt, QRectF, QSize, QEvent, QByteArray
from PySide6.QtGui import QPainter, QPainterPath, QColor, QFont, QIcon
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QPushButton, QLineEdit, QTextEdit, QCheckBox, QRadioButton, QComboBox,
    QListView, QStyledItemDelegate, QStyle, QStyleOptionButton, QWidget,
)

from ui.theme import (
    FORM_ACCENT, FORM_ACCENT_LIGHT_1, FORM_ACCENT_LIGHT_2, FORM_ACCENT_LIGHT_3,
    FORM_ACCENT_DARK_1, FORM_FONT_FAMILIES, FORM_FONT_PX, get_scrollbar_style,
)

__all__ = [
    "PushButton", "PrimaryPushButton", "LineEdit", "TextEdit",
    "RadioButton", "CheckBox", "ComboBox", "EditableComboBox",
]

_FONT_QSS = ", ".join(f"'{f}'" for f in FORM_FONT_FAMILIES)


def _form_font() -> QFont:
    font = QFont()
    font.setFamilies(FORM_FONT_FAMILIES)
    font.setPixelSize(FORM_FONT_PX)
    font.setWeight(QFont.Weight.Normal)
    return font


def _repolish(w: QWidget):
    w.style().unpolish(w)
    w.style().polish(w)


# ── 图标（原版 SVG 路径） ─────────────────────────────────────
_CHECK_SVG = QByteArray(
    b'<svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 3500 3500">'
    b'<path fill="#ffffff" transform="translate(700, 1000)" d="M0 768 q0 -34.67 25.34 -60 '
    b'q25.34 -25.33 59.99 -25.33 q34.67 0 60 25.33 l537.34 536 l1220 -1218.67 q25.33 -25.33 60 -25.33 '
    b'q34.66 0 59.99 25.34 q25.34 25.34 25.34 59.99 q0 34.67 -25.33 60 l-1280 1280 q-25.34 25.34 -60 25.34 '
    b'q-34.67 0 -60 -25.34 l-597.34 -597.33 q-25.33 -25.33 -25.33 -60 Z"/></svg>'
)
_CHEVRON_SVG = QByteArray(
    b'<svg xmlns="http://www.w3.org/2000/svg" height="16" width="16" viewBox="0 0 16 16">'
    b'<path transform="translate(-1.8,-1.5) scale(0.0374926772114821,0.0374926772114821)" fill="#646464" '
    b'd="M106.75,170.5L111.1875,170.90625 115,172.125 118.4375,174.15625 121.75,177 256,311.25 390.25,177 '
    b'393.625,174.156265258789 397.25,172.125 401.125,170.90625 405.25,170.5 409.59375,170.9375 413.625,172.25 '
    b'417.25,174.281265258789 420.375,176.875 422.96875,180.000015258789 425,183.625 426.312469482422,187.65625 '
    b'426.75,192 426.359344482422,196.21875 425.187469482422,200.125 423.234344482422,203.71875 420.5,207 '
    b'271,356.5 267.71875,359.234375 264.125,361.1875 260.21875,362.359375 256,362.75 251.78125,362.359375 '
    b'247.875,361.1875 244.28125,359.234375 241,356.5 91.5,207 88.765625,203.71875 86.8125,200.125 '
    b'85.640625,196.21875 85.25,192 85.6875,187.65625 87,183.625 89.03125,180.000015258789 91.625,176.875 '
    b'94.75,174.281265258789 98.375,172.25 102.40625,170.9375 106.75,170.5z"/></svg>'
)
_renderers: dict = {}


def _render_svg(key: str, data: QByteArray, painter: QPainter, rect: QRectF):
    r = _renderers.get(key)
    if r is None:
        r = _renderers[key] = QSvgRenderer(data)
    r.render(painter, rect)


def _paint_focus_bar(widget: QWidget, rect_h: float):
    """原版聚焦态：底部 2px 主题色圆角条"""
    painter = QPainter(widget)
    painter.setRenderHints(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    m = widget.contentsMargins()
    w, h = widget.width() - m.left() - m.right(), widget.height()
    path = QPainterPath()
    path.addRoundedRect(QRectF(m.left(), h - 10, w, 10), 5, 5)
    rect_path = QPainterPath()
    rect_path.addRect(m.left(), h - 10, w, rect_h)
    painter.fillPath(path.subtracted(rect_path), QColor(FORM_ACCENT))
    painter.end()


# ── QSS（取自 qfluentwidgets light 主题） ─────────────────────
_BUTTON_QSS = f"""
PushButton {{
    color: black;
    background: rgba(255, 255, 255, 0.7);
    border: 1px solid rgba(0, 0, 0, 0.073);
    border-bottom: 1px solid rgba(0, 0, 0, 0.183);
    border-radius: 5px;
    padding: 5px 12px 6px 12px;
    outline: none;
}}
PushButton[hasIcon=true] {{
    padding: 5px 12px 6px 36px;
}}
PushButton:hover {{
    background: rgba(249, 249, 249, 0.5);
}}
PushButton:pressed {{
    color: rgba(0, 0, 0, 0.63);
    background: rgba(249, 249, 249, 0.3);
    border-bottom: 1px solid rgba(0, 0, 0, 0.073);
}}
PushButton:disabled {{
    color: rgba(0, 0, 0, 0.36);
    background: rgba(249, 249, 249, 0.3);
    border: 1px solid rgba(0, 0, 0, 0.06);
    border-bottom: 1px solid rgba(0, 0, 0, 0.06);
}}
PrimaryPushButton {{
    color: white;
    background-color: {FORM_ACCENT};
    border: 1px solid {FORM_ACCENT_LIGHT_1};
    border-bottom: 1px solid {FORM_ACCENT_DARK_1};
}}
PrimaryPushButton:hover {{
    background-color: {FORM_ACCENT_LIGHT_1};
    border: 1px solid {FORM_ACCENT_LIGHT_2};
    border-bottom: 1px solid {FORM_ACCENT_DARK_1};
}}
PrimaryPushButton:pressed {{
    color: rgba(255, 255, 255, 0.63);
    background-color: {FORM_ACCENT_LIGHT_3};
    border: 1px solid {FORM_ACCENT_LIGHT_3};
}}
PrimaryPushButton:disabled {{
    color: rgba(255, 255, 255, 0.9);
    background-color: rgb(205, 205, 205);
    border: 1px solid rgb(205, 205, 205);
}}
"""

_RADIO_QSS = f"""
RadioButton {{
    min-height: 24px;
    max-height: 24px;
    background-color: transparent;
    font: {FORM_FONT_PX}px {_FONT_QSS};
    color: black;
}}
RadioButton::indicator {{
    width: 18px;
    height: 18px;
    border-radius: 11px;
    border: 2px solid #999999;
    margin-right: 4px;
}}
RadioButton::indicator:checked {{
    height: 22px;
    width: 22px;
    border: none;
}}
RadioButton:disabled {{
    color: rgba(0, 0, 0, 110);
}}
"""

_EDIT_QSS = f"""
LineEdit, TextEdit {{
    color: black;
    background-color: rgba(255, 255, 255, 0.7);
    border: 1px solid rgba(0, 0, 0, 13);
    border-bottom: 1px solid rgba(0, 0, 0, 100);
    border-radius: 5px;
    padding: 0px 10px;
    selection-background-color: {FORM_ACCENT_LIGHT_1};
}}
TextEdit {{
    padding: 2px 3px 2px 8px;
}}
LineEdit:hover, TextEdit:hover {{
    background-color: rgba(249, 249, 249, 0.5);
    border: 1px solid rgba(0, 0, 0, 13);
    border-bottom: 1px solid rgba(0, 0, 0, 100);
}}
LineEdit:focus {{
    border-bottom: 1px solid rgba(0, 0, 0, 13);
    background-color: white;
}}
TextEdit:focus {{
    border-bottom: 1px solid {FORM_ACCENT};
    background-color: white;
}}
LineEdit:disabled, TextEdit:disabled {{
    color: rgba(0, 0, 0, 92);
    background-color: rgba(249, 249, 249, 0.3);
    border: 1px solid rgba(0, 0, 0, 13);
    border-bottom: 1px solid rgba(0, 0, 0, 13);
}}
"""

_CHECK_QSS = """
CheckBox {
    color: black;
    spacing: 8px;
    min-width: 28px;
    min-height: 22px;
    outline: none;
    margin-left: 1px;
}
CheckBox::indicator {
    width: 18px;
    height: 18px;
    border-radius: 5px;
    border: 1px solid transparent;
    background-color: transparent;
}
CheckBox:disabled {
    color: rgba(0, 0, 0, 0.36);
}
"""

# 下拉弹层：与原版 RoundMenu 一致的圆角浅灰卡片、33px 行高、6px 左右内缩
_POPUP_QSS = f"""
QFrame {{
    background: transparent;
    border: none;
}}
QAbstractItemView {{
    border: 1px solid rgba(0, 0, 0, 0.1);
    border-radius: 9px;
    background-color: rgb(249, 249, 249);
    padding: 2px 0px 6px 0px;
    outline: none;
    font: {FORM_FONT_PX}px {_FONT_QSS};
}}
QAbstractItemView::item {{
    margin: 4px 6px 0px 6px;
    padding-left: 10px;
    padding-right: 10px;
    border-radius: 5px;
    border: none;
    color: black;
}}
QAbstractItemView::item:hover,
QAbstractItemView::item:selected {{
    background-color: rgba(0, 0, 0, 9);
    color: black;
}}
QAbstractScrollArea::corner {{
    background: transparent;
    border: none;
}}
"""

# 注意：设置面板父级 QSS 有 `QComboBox {{ font-size:13px; ... }}` 等规则，
# 这里需显式覆盖字体 / 焦点边框 / drop-down，才能与原版（不命中 QComboBox 规则）一致。
_COMBO_QSS = f"""
ComboBox {{
    border: 1px solid rgba(0, 0, 0, 0.073);
    border-radius: 5px;
    border-bottom: 1px solid rgba(0, 0, 0, 0.183);
    padding: 5px 31px 6px 11px;
    color: black;
    background-color: rgba(255, 255, 255, 0.7);
    font: {FORM_FONT_PX}px {_FONT_QSS};
    min-height: 0px;
    combobox-popup: 0;
}}
ComboBox:hover {{
    background-color: rgba(249, 249, 249, 0.5);
}}
ComboBox:focus {{
    border: 1px solid rgba(0, 0, 0, 0.073);
    border-bottom: 1px solid rgba(0, 0, 0, 0.183);
}}
ComboBox:on {{
    background-color: rgba(249, 249, 249, 0.3);
    border-bottom: 1px solid rgba(0, 0, 0, 0.073);
}}
ComboBox:disabled {{
    color: rgba(0, 0, 0, 0.36);
    background: rgba(249, 249, 249, 0.3);
    border: 1px solid rgba(0, 0, 0, 0.06);
    border-bottom: 1px solid rgba(0, 0, 0, 0.06);
}}
ComboBox::drop-down {{
    width: 0px;
    border: none;
}}
ComboBox::down-arrow {{
    image: none;
    width: 0px;
    height: 0px;
}}
"""

_EDITABLE_COMBO_QSS = f"""
EditableComboBox {{
    color: black;
    background-color: rgba(255, 255, 255, 0.7);
    border: 1px solid rgba(0, 0, 0, 13);
    border-bottom: 1px solid rgba(0, 0, 0, 100);
    border-radius: 5px;
    padding: 0px 0px 0px 6px;  /* QComboBox 编辑区自带约 4px，合计与原版 LineEdit 的 10px 对齐 */
    font: {FORM_FONT_PX}px {_FONT_QSS};
    min-height: 0px;
    combobox-popup: 0;
}}
EditableComboBox:hover {{
    background-color: rgba(249, 249, 249, 0.5);
}}
EditableComboBox:focus {{
    border: 1px solid rgba(0, 0, 0, 13);
    border-bottom: 1px solid rgba(0, 0, 0, 13);
    background-color: white;
}}
EditableComboBox:disabled {{
    color: rgba(0, 0, 0, 92);
    background-color: rgba(249, 249, 249, 0.3);
    border: 1px solid rgba(0, 0, 0, 13);
    border-bottom: 1px solid rgba(0, 0, 0, 13);
}}
EditableComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: center right;
    width: 29px;
    border: none;
}}
EditableComboBox::down-arrow {{
    image: none;
    width: 0px;
    height: 0px;
}}
EditableComboBox QLineEdit {{
    background: transparent;
    border: none;
    padding: 0px;
    selection-background-color: {FORM_ACCENT_LIGHT_1};
}}
"""


# ── 按钮 ─────────────────────────────────────────────────────
class PushButton(QPushButton):
    """PushButton(text='', parent=None)，图标由自身绘制以保持原版排版（左 12px）"""

    def __init__(self, *args):
        text, parent = "", None
        if args and isinstance(args[0], str):
            text, args = args[0], args[1:]
        if args:
            parent = args[0]
        super().__init__(text, parent)
        self._icon = QIcon()
        self._is_pressed = False
        self.setProperty("hasIcon", False)
        self.setStyleSheet(_BUTTON_QSS)
        self.setIconSize(QSize(16, 16))
        self.setFont(_form_font())

    def setIcon(self, icon):
        if icon is None:
            icon = QIcon()
        elif not isinstance(icon, QIcon):
            icon = QIcon(icon)
        self._icon = icon
        self.setProperty("hasIcon", not icon.isNull())
        _repolish(self)
        self.update()

    def icon(self) -> QIcon:
        return self._icon

    def mousePressEvent(self, e):
        self._is_pressed = True
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        self._is_pressed = False
        super().mouseReleaseEvent(e)

    def paintEvent(self, e):
        super().paintEvent(e)
        if self._icon.isNull():
            return
        painter = QPainter(self)
        painter.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        if not self.isEnabled():
            painter.setOpacity(0.3628)
        elif self._is_pressed:
            painter.setOpacity(0.786)
        w, h = self.iconSize().width(), self.iconSize().height()
        y = (self.height() - h) / 2
        mw = self.minimumSizeHint().width()
        x = 12 + (self.width() - mw) // 2 if mw > 0 else 12
        self._icon.paint(painter, QRectF(x, y, w, h).toRect(), Qt.AlignmentFlag.AlignCenter)
        painter.end()


class PrimaryPushButton(PushButton):
    """主色按钮（样式由 _BUTTON_QSS 中 PrimaryPushButton 规则提供）"""


# ── 输入框 ───────────────────────────────────────────────────
class LineEdit(QLineEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("transparent", True)
        self.setStyleSheet(_EDIT_QSS)
        self.setFixedHeight(33)
        self.setAttribute(Qt.WidgetAttribute.WA_MacShowFocusRect, False)
        self.setFont(_form_font())

    def paintEvent(self, e):
        super().paintEvent(e)
        if self.hasFocus():
            _paint_focus_bar(self, 8)


class _EditLayer(QWidget):
    """TextEdit 聚焦底条层（覆盖在视口之上、鼠标穿透）"""

    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        parent.installEventFilter(self)

    def eventFilter(self, obj, e):
        if obj is self.parent() and e.type() == QEvent.Type.Resize:
            self.resize(e.size())
        return super().eventFilter(obj, e)

    def paintEvent(self, e):
        if self.parent().hasFocus():
            _paint_focus_bar(self, 7.5)


class TextEdit(QTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layer = _EditLayer(self)
        self.setStyleSheet(_EDIT_QSS + get_scrollbar_style())
        self.setFont(_form_font())

    def focusInEvent(self, e):
        super().focusInEvent(e)
        self.layer.update()

    def focusOutEvent(self, e):
        super().focusOutEvent(e)
        self.layer.update()


# ── 复选 / 单选 ──────────────────────────────────────────────
class CheckBox(QCheckBox):
    def __init__(self, *args):
        text, parent = "", None
        if args and isinstance(args[0], str):
            text, args = args[0], args[1:]
        if args:
            parent = args[0]
        super().__init__(text, parent)
        self.setFont(_form_font())
        self.setStyleSheet(_CHECK_QSS)
        self._is_pressed = False
        self._is_hover = False

    def mousePressEvent(self, e):
        self._is_pressed = True
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        self._is_pressed = False
        super().mouseReleaseEvent(e)

    def enterEvent(self, e):
        self._is_hover = True
        self.update()

    def leaveEvent(self, e):
        self._is_hover = False
        self.update()

    def _colors(self):
        """返回 (边框色, 背景色)，与原版浅色主题状态表一致"""
        if not self.isEnabled():
            if self.isChecked():
                return QColor(0, 0, 0, 0), QColor(0, 0, 0, 56)
            return QColor(0, 0, 0, 56), QColor(0, 0, 0, 0)
        if self.isChecked():
            if self._is_pressed:
                c = QColor(FORM_ACCENT_LIGHT_2)
            elif self._is_hover:
                c = QColor(FORM_ACCENT_LIGHT_1)
            else:
                c = QColor(FORM_ACCENT)
            return c, c
        if self._is_pressed:
            return QColor(0, 0, 0, 69), QColor(0, 0, 0, 31)
        if self._is_hover:
            return QColor(0, 0, 0, 143), QColor(0, 0, 0, 13)
        return QColor(0, 0, 0, 122), QColor(0, 0, 0, 6)

    def paintEvent(self, e):
        super().paintEvent(e)
        painter = QPainter(self)
        painter.setRenderHints(QPainter.RenderHint.Antialiasing)
        opt = QStyleOptionButton()
        opt.initFrom(self)
        rect = self.style().subElementRect(QStyle.SubElement.SE_CheckBoxIndicator, opt, self)
        border, bg = self._colors()
        painter.setPen(border)
        painter.setBrush(bg)
        painter.drawRoundedRect(rect, 4.5, 4.5)
        if not self.isEnabled():
            painter.setOpacity(0.8)
        if self.checkState() == Qt.CheckState.Checked:
            _render_svg("check", _CHECK_SVG, painter, QRectF(rect))
        painter.end()


class RadioButton(QRadioButton):
    def __init__(self, *args):
        text, parent = "", None
        if args and isinstance(args[0], str):
            text, args = args[0], args[1:]
        if args:
            parent = args[0]
        super().__init__(text, parent)
        self._is_hover = False
        self.setStyleSheet(_RADIO_QSS)
        self.setAttribute(Qt.WidgetAttribute.WA_MacShowFocusRect, False)

    def enterEvent(self, e):
        self._is_hover = True
        self.update()

    def leaveEvent(self, e):
        self._is_hover = False
        self.update()

    def paintEvent(self, e):
        painter = QPainter(self)
        painter.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
        self._draw_indicator(painter)
        if not self.isEnabled():
            painter.setOpacity(0.36)
        painter.setFont(self.font())
        painter.setPen(QColor(0, 0, 0))
        painter.drawText(QRectF(29, 0, self.width(), self.height()), Qt.AlignmentFlag.AlignVCenter, self.text())
        painter.end()

    def _draw_indicator(self, painter: QPainter):
        center = (11, 12)
        if self.isChecked():
            border = QColor(FORM_ACCENT) if self.isEnabled() else QColor(0, 0, 0, 55)
            thickness = 4 if (self._is_hover and not self.isDown()) else 5
            self._draw_circle(painter, center, 10, thickness, border, QColor(Qt.GlobalColor.white))
            return
        if self.isEnabled():
            border = QColor(0, 0, 0, 55) if self.isDown() else QColor(0, 0, 0, 153)
            if self.isDown():
                fill = QColor(Qt.GlobalColor.white)
            elif self._is_hover:
                fill = QColor(0, 0, 0, 15)
            else:
                fill = QColor(0, 0, 0, 6)
        else:
            fill = QColor(0, 0, 0, 0)
            border = QColor(0, 0, 0, 55)
        self._draw_circle(painter, center, 10, 1, border, fill)
        if self.isEnabled() and self.isDown():
            self._draw_circle(painter, center, 9, 4, QColor(0, 0, 0, 24), QColor(0, 0, 0, 0))

    @staticmethod
    def _draw_circle(painter, center, radius, thickness, border, fill):
        cx, cy = center
        path = QPainterPath()
        path.setFillRule(Qt.FillRule.WindingFill)
        path.addEllipse(QRectF(cx - radius, cy - radius, 2 * radius, 2 * radius))
        ir = radius - thickness
        inner = QPainterPath()
        inner.addEllipse(QRectF(cx - ir, cy - ir, 2 * ir, 2 * ir))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.fillPath(path.subtracted(inner), border)
        painter.fillPath(inner, fill)


# ── 下拉框 ───────────────────────────────────────────────────
class _IndicatorDelegate(QStyledItemDelegate):
    """当前选中项左侧 3x15 主题色指示条（同原版 IndicatorMenuItemDelegate）"""

    def __init__(self, combo: QComboBox):
        super().__init__(combo)
        self._combo = combo

    def sizeHint(self, option, index):
        hint = super().sizeHint(option, index)
        hint.setHeight(33)  # 原版 ComboBoxMenu.setItemHeight(33)，含 4px 上外边距
        return hint

    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        if index.row() != self._combo.currentIndex():
            return
        painter.save()
        painter.setRenderHints(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(FORM_ACCENT))
        painter.drawRoundedRect(QRectF(6, option.rect.y() + 11, 3, 15), 1.5, 1.5)
        painter.restore()


class _ComboMixin:
    """QComboBox 公共部分：Fluent 风格弹层 + 自绘下拉箭头"""

    def _setup_combo(self, qss: str):
        self.setFont(_form_font())
        view = QListView()
        self.setView(view)
        view.setItemDelegate(_IndicatorDelegate(self))
        view.setStyleSheet(_POPUP_QSS)
        view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        # 弹层容器去掉系统边框/阴影并透明，露出列表的 9px 圆角
        container = view.parentWidget()
        if container is not None:
            container.setWindowFlags(
                container.windowFlags()
                | Qt.WindowType.FramelessWindowHint
                | Qt.WindowType.NoDropShadowWindowHint
            )
            container.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            container.setStyleSheet(_POPUP_QSS)
            # Qt 自带的阴影效果没有外边距，会被裁成右下深色硬边，直接去掉（卡片保留 1px 描边）
            container.setGraphicsEffect(None)
        self.setStyleSheet(qss)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._is_hover = False

    def enterEvent(self, e):
        self._is_hover = True
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._is_hover = False
        self.update()
        super().leaveEvent(e)

    def showPopup(self):
        QComboBox.showPopup(self)
        # 原版菜单与下拉框间隔约 6px；仅在向下展开时下移
        container = self.view().parentWidget()
        if container is not None:
            # Windows 样式会在 polish 时重新加上无外边距的阴影（右下深色硬边），这里每次弹出后移除
            container.setGraphicsEffect(None)
            below = self.mapToGlobal(self.rect().bottomLeft()).y()
            if container.y() >= below - 1:
                container.move(container.x(), container.y() + 6)

    def _paint_arrow(self, center_x: float):
        painter = QPainter(self)
        painter.setRenderHints(QPainter.RenderHint.Antialiasing)
        if self._is_hover:
            painter.setOpacity(0.8)
        if not self.isEnabled():
            painter.setOpacity(0.36)
        _render_svg("chevron", _CHEVRON_SVG, painter, QRectF(center_x - 5, self.height() / 2 - 5, 10, 10))
        painter.end()


class ComboBox(_ComboMixin, QComboBox):
    def __init__(self, parent=None):
        QComboBox.__init__(self, parent)
        self._setup_combo(_COMBO_QSS)

    def paintEvent(self, e):
        QComboBox.paintEvent(self, e)
        self._paint_arrow(self.width() - 17)


class EditableComboBox(_ComboMixin, QComboBox):
    _ref_width = None  # 原版基于 LineEdit，默认宽度沿用其 sizeHint

    def __init__(self, parent=None):
        QComboBox.__init__(self, parent)
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self._setup_combo(_EDITABLE_COMBO_QSS)
        self.setFixedHeight(33)
        self.lineEdit().setFont(_form_font())

    def sizeHint(self):
        # QSS 在 polish 时会改写 minimumHeight，布局随后按 sizeHint 收缩高度；
        # 这里让高度始终取固定高度（默认 33，调用方 setFixedHeight 后取其值）
        hint = super().sizeHint()
        if EditableComboBox._ref_width is None:
            ref = LineEdit()
            ref.setTextMargins(0, 0, 29, 0)
            ref.ensurePolished()
            EditableComboBox._ref_width = ref.sizeHint().width()
            ref.deleteLater()
        hint.setWidth(max(hint.width(), EditableComboBox._ref_width))
        hint.setHeight(self.maximumHeight())
        return hint

    def minimumSizeHint(self):
        hint = super().minimumSizeHint()
        hint.setHeight(self.maximumHeight())
        return hint

    def setPlaceholderText(self, text: str):
        self.lineEdit().setPlaceholderText(text)

    def paintEvent(self, e):
        QComboBox.paintEvent(self, e)
        self._paint_arrow(self.width() - 19)
        if self.hasFocus():
            _paint_focus_bar(self, 8)
