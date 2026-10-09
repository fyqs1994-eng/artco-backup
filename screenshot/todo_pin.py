"""
截图模块 - 待办屏贴（单例看板）

设计要点：
- **单例**：所有截图待办都收纳进同一个屏贴，不会截一张新增一个
- **图片即条目**：截图作为列表项插入，每条都带复选框，可独立勾选/删除
- 图片按比例缩放展示（限宽 268、限高 240，保持原始比例），点击查看大图
- 数据 + 图片本地持久化，重启后仍在
- 可一键同步到企业微信待办：文字条目直接同步；图片条目先做 OCR，
  识别出文字的转为文字推送，无文字的跳过不推送
"""

import json
import os
import time
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QScrollArea, QSizePolicy, QApplication, QFrame,
)
from PySide6.QtCore import Qt, QPoint, QSize, Signal, QTimer, QThread
from PySide6.QtGui import QPixmap, QPainter, QColor

import qtawesome as qta

from ui.theme import (
    ACCENT_PRIMARY, BG_ELEVATED, BG_PRIMARY, BG_SECONDARY, BG_HOVER, BG_HOVER_SOFT,
    BORDER_DEFAULT, BORDER_SUBTLE, TEXT_PRIMARY, TEXT_SECONDARY,
    TEXT_TERTIARY, TEXT_MUTED,
    RADIUS_MD, RADIUS_LG, SPACING_XS, SPACING_SM, SPACING_MD,
    FONT_SIZE_SM, FONT_SIZE_MD, FONT_FAMILY,
    ICON_SM, get_scrollbar_style,
    SHADOW_MARGIN, draw_shadow,
    CHECKBOX_ICON, CHECKBOX_HIT,
)

# 持久化目录
# 支持环境变量覆盖：仅用于测试隔离，避免测试写脏用户真实待办数据
_TODO_DIR_OVERRIDE = os.environ.get("ARTCO_TODO_DIR")
TODO_DATA_DIR = Path(_TODO_DIR_OVERRIDE) if _TODO_DIR_OVERRIDE else (
    Path.home() / ".artco" / "todos")
TODO_IMAGE_DIR = TODO_DATA_DIR / "images"

# 固定看板 ID —— 保证多个屏贴不会各自存一份
BOARD_ID = "board_main"

# 尺寸
_WIN_WIDTH = 480
_THUMB_MAX_W = 400
_THUMB_MAX_H = 480
# 细长截图（聊天记录常见）按限高缩放会变得极窄，需保证最小可读宽度
_THUMB_MIN_W = 96
# 超长图的绝对高度上限，避免单条撑爆列表（与限高保持一致，否则会压制限高）
_THUMB_ABS_MAX_H = 480
_LIST_MAX_H = 520
_SHADOW_MARGIN = SHADOW_MARGIN   # 与主题规范同源，避免两处各写一份


def _thumb_size(w: int, h: int):
    """计算缩略图尺寸：保持原始比例，优先限宽，并保证细长图的最小可读宽度。

    普通图：按 限宽400 / 限高480 取小比例，不变形。
    细长图：若算出的宽度小于 96，则以 96 为宽重算高度（高度可超限高，再封顶）。
    """
    if w <= 0 or h <= 0:
        return _THUMB_MIN_W, _THUMB_MIN_W

    scale = min(_THUMB_MAX_W / w, _THUMB_MAX_H / h)
    nw, nh = w * scale, h * scale

    if nw < _THUMB_MIN_W:
        # 细长图：按最小宽度重算，高度随之按比例增长
        scale = _THUMB_MIN_W / w
        nw, nh = w * scale, h * scale
        # 高度封顶时，按同一比例回算宽度，保持比例不变形
        if nh > _THUMB_ABS_MAX_H:
            scale = _THUMB_ABS_MAX_H / h
            nw, nh = w * scale, h * scale

    return max(int(round(nw)), 1), max(int(round(nh)), 1)


# 复选框：视觉尺寸 18px（比原先 14px 明显更大更好看），
# 点击热区 24px（比视觉大一圈，保证好点中，符合触控目标下限要求）
_CHECK_ICON = CHECKBOX_ICON
_CHECK_HIT = CHECKBOX_HIT


def _dim_pixmap(pm: QPixmap) -> QPixmap:
    """生成"已完成"状态的淡化图（覆盖半透明背景色而非固定白色，以适配深色主题）

    注意：必须沿用源图的 devicePixelRatio。QPixmap(size) 默认 DPR=1.0，
    在高分屏（DPR=2）上会让物理像素直接减半，勾选后缩略图看起来像被缩小、
    发虚，像是"变灰 + 缩放"。这里显式 setDevicePixelRatio 保住分辨率。
    """
    dpr = pm.devicePixelRatio()
    out = QPixmap(pm.size())
    out.setDevicePixelRatio(dpr)
    out.fill(Qt.GlobalColor.transparent)
    painter = QPainter(out)
    painter.drawPixmap(0, 0, pm)
    c = QColor(BG_ELEVATED)
    c.setAlpha(150)
    # fillRect 用逻辑坐标，与 DPR 无关，无需换算
    painter.fillRect(out.rect(), c)
    painter.end()
    return out


class TodoItemWidget(QFrame):
    """文字待办条目：复选框 + 文本（双击改）+ 删除"""

    toggled = Signal(str, bool)
    remove_requested = Signal(str)
    text_edited = Signal(str, str)

    def __init__(self, item_id: str, text: str, checked: bool = False, parent=None):
        super().__init__(parent)
        self._item_id = item_id
        self._checked = checked
        self._synced = False
        self.setObjectName("todo_item")
        self._init_ui(text, checked)
        self._apply_style()

    def _init_ui(self, text: str, checked: bool):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(SPACING_SM, SPACING_XS, SPACING_XS, SPACING_XS)
        layout.setSpacing(SPACING_SM)

        self.checkbox = QPushButton()
        self.checkbox.setObjectName("todo_checkbox")
        # 热区 24px（好点中），图标 18px（好看）；视觉居中靠下方统一计算
        self.checkbox.setFixedSize(_CHECK_HIT, _CHECK_HIT)
        self.checkbox.setCheckable(True)
        self.checkbox.setChecked(checked)
        self.checkbox.setCursor(Qt.CursorShape.PointingHandCursor)
        self.checkbox.clicked.connect(self._on_toggle)
        # 垂直居中：热区(24)比图标(18)大，热区居中即可让图标与首行文字视觉居中。
        # 原先固定贴顶（AlignTop）导致复选框明显高于文字，即用户反馈的「没对齐」。
        # 用 AlignVCenter 而非 margin-top——后者会与 AlignTop 叠加，难以精确对齐。
        layout.addWidget(self.checkbox, alignment=Qt.AlignmentFlag.AlignVCenter)

        self.label = QLabel(text)
        self.label.setWordWrap(True)
        self.label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.label.setCursor(Qt.CursorShape.IBeamCursor)
        layout.addWidget(self.label, stretch=1)

        self.editor = QLineEdit(text)
        self.editor.setVisible(False)
        self.editor.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.editor.editingFinished.connect(self._finish_edit)
        layout.addWidget(self.editor, stretch=1)

        self.btn_del = QPushButton()
        self.btn_del.setObjectName("todo_delete")
        self.btn_del.setIcon(qta.icon('mdi6.close', color=TEXT_TERTIARY))
        self.btn_del.setIconSize(QSize(12, 12))
        self.btn_del.setFixedSize(20, 20)
        self.btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_del.clicked.connect(lambda: self.remove_requested.emit(self._item_id))
        layout.addWidget(self.btn_del, alignment=Qt.AlignmentFlag.AlignTop)

        self._refresh_check_icon()
        if checked:
            self._refresh_text_style()

    def _apply_style(self):
        self.setStyleSheet(f"""
            QFrame#todo_item {{
                background-color: transparent;
                border: none;
                border-radius: {RADIUS_MD}px;
            }}
            QFrame#todo_item:hover {{ background-color: {BG_HOVER}; }}
            QPushButton#todo_checkbox {{
                background-color: transparent; border: none; border-radius: 5px;
            }}
            QPushButton#todo_checkbox:hover {{ background-color: {BG_HOVER_SOFT}; }}
            QPushButton#todo_delete {{
                background-color: transparent; border: none; border-radius: 4px;
            }}
            QPushButton#todo_delete:hover {{ background-color: rgba(0, 0, 0, 0.10); }}
            QLineEdit {{
                background-color: {BG_PRIMARY};
                border: 1px solid {ACCENT_PRIMARY};
                border-radius: 4px; padding: 2px 4px;
                color: {TEXT_PRIMARY};
                font-family: {FONT_FAMILY}; font-size: {FONT_SIZE_SM}px;
            }}
        """)
        self.label.setStyleSheet(f"""
            QLabel {{
                color: {TEXT_PRIMARY};
                font-family: {FONT_FAMILY};
                font-size: {FONT_SIZE_SM}px;
                background: transparent; padding-top: 1px;
            }}
        """)

    def set_checked(self, checked: bool):
        """外部设置勾选状态（不发 toggled 信号，避免递归）"""
        self._checked = checked
        self.checkbox.setChecked(checked)
        self._refresh_check_icon()
        self._refresh_text_style()

    def set_synced_badge(self, synced: bool):
        """显示/隐藏「已同步」标记。

        只改样式不改 label 文本——否则后缀会污染条目内容
        （双击编辑取的是 label.text()，再次同步也会带上后缀）。
        """
        self._synced = synced
        self._refresh_text_style()

    def _refresh_check_icon(self):
        icon = 'mdi6.checkbox-marked' if self._checked else 'mdi6.checkbox-blank-outline'
        color = ACCENT_PRIMARY if self._checked else TEXT_TERTIARY
        self.checkbox.setIcon(qta.icon(icon, color=color))
        self.checkbox.setIconSize(QSize(_CHECK_ICON, _CHECK_ICON))

    def _refresh_text_style(self):
        if self._checked:
            # 已同步（已提交）用主题色淡调，手动完成用中性灰，便于区分
            color = ACCENT_PRIMARY if getattr(self, "_synced", False) else TEXT_MUTED
            self.label.setStyleSheet(f"""
                QLabel {{
                    color: {color};
                    font-family: {FONT_FAMILY};
                    font-size: {FONT_SIZE_SM}px;
                    background: transparent;
                    text-decoration: line-through; padding-top: 1px;
                }}
            """)
        else:
            self._apply_style()

    def _on_toggle(self):
        self._checked = self.checkbox.isChecked()
        self._refresh_check_icon()
        self._refresh_text_style()
        self.toggled.emit(self._item_id, self._checked)

    def mouseDoubleClickEvent(self, event):
        if not self.editor.isVisible():
            self.editor.setText(self.label.text())
            self.label.setVisible(False)
            self.editor.setVisible(True)
            self.editor.setFocus()
            self.editor.selectAll()
        super().mouseDoubleClickEvent(event)

    def _finish_edit(self):
        if not self.editor.isVisible():
            return
        new_text = self.editor.text().strip()
        if new_text:
            self.label.setText(new_text)
            self.text_edited.emit(self._item_id, new_text)
        self.editor.setVisible(False)
        self.label.setVisible(True)

    def item_id(self) -> str:
        return self._item_id

    def text(self) -> str:
        return self.label.text()

    def is_checked(self) -> bool:
        return self._checked


class TodoImageItemWidget(QFrame):
    """图片待办条目：复选框 + 按比例缩放的截图 + 删除，点击查看大图"""

    toggled = Signal(str, bool)
    remove_requested = Signal(str)
    view_requested = Signal(str)

    def __init__(self, item_id: str, pixmap: QPixmap, checked: bool = False,
                 meta: str = "截图", parent=None):
        super().__init__(parent)
        self._item_id = item_id
        self._checked = checked
        self._pixmap = pixmap
        self._meta_base = meta
        self._synced = False

        self.setObjectName("todo_image_item")
        self._init_ui(meta)
        self._apply_style()
        self._refresh_thumb()

    # ── UI ──
    def _init_ui(self, meta: str):
        # 按 _thumb_size 计算：保持比例，普通图不变形
        self._crop_bottom = False
        tw, th = _thumb_size(self._pixmap.width(), self._pixmap.height())

        # 极端细长（聊天记录）：按限高缩放后宽度仍太窄，改为固定宽度 + 裁切顶部
        if tw < _THUMB_MIN_W:
            self._crop_bottom = True
            tw = _THUMB_MIN_W
            th = _THUMB_ABS_MAX_H
            src_h = int(self._pixmap.width() * th / tw)
            src_h = max(1, min(src_h, self._pixmap.height()))
            self._scaled = self._pixmap.copy(0, 0, self._pixmap.width(), src_h).scaled(
                tw, th,
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        else:
            self._scaled = self._pixmap.scaled(
                tw, th,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(SPACING_SM, SPACING_XS, SPACING_XS, SPACING_XS)
        layout.setSpacing(SPACING_SM)

        self.checkbox = QPushButton()
        self.checkbox.setObjectName("todo_checkbox")
        self.checkbox.setFixedSize(_CHECK_HIT, _CHECK_HIT)
        self.checkbox.setCheckable(True)
        self.checkbox.setChecked(self._checked)
        self.checkbox.setCursor(Qt.CursorShape.PointingHandCursor)
        self.checkbox.clicked.connect(self._on_toggle)
        # 图片条目用 AlignVCenter：热区(24)比图标(18)大，热区居中即可让图标居中，
        # 比 AlignTop + margin-top 更稳（margin 与 AlignTop 会叠加，难精确对齐）
        layout.addWidget(self.checkbox, alignment=Qt.AlignmentFlag.AlignVCenter)

        # 缩略图（用 QPushButton 承载，天然可点击）
        self.thumb = QPushButton()
        self.thumb.setObjectName("todo_thumb")
        self.thumb.setFixedSize(self._scaled.size())
        self.thumb.setIconSize(self._scaled.size())
        self.thumb.setCursor(Qt.CursorShape.PointingHandCursor)
        self.thumb.clicked.connect(lambda: self.view_requested.emit(self._item_id))
        layout.addWidget(self.thumb, alignment=Qt.AlignmentFlag.AlignTop)

        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(2)

        self.meta = QLabel(meta)
        self.meta.setStyleSheet(f"""
            QLabel {{
                color: {TEXT_TERTIARY};
                font-family: {FONT_FAMILY};
                font-size: {FONT_SIZE_SM - 1}px;
                background: transparent;
            }}
        """)
        right.addWidget(self.meta)
        right.addStretch()

        self.btn_del = QPushButton()
        self.btn_del.setObjectName("todo_delete")
        self.btn_del.setIcon(qta.icon('mdi6.close', color=TEXT_TERTIARY))
        self.btn_del.setIconSize(QSize(12, 12))
        self.btn_del.setFixedSize(20, 20)
        self.btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_del.clicked.connect(lambda: self.remove_requested.emit(self._item_id))
        right.addWidget(self.btn_del, alignment=Qt.AlignmentFlag.AlignRight)

        layout.addLayout(right, stretch=1)

        self.setFixedHeight(self._scaled.height() + SPACING_XS * 2)
        self._refresh_check_icon()

    def _apply_style(self):
        self.setStyleSheet(f"""
            QFrame#todo_image_item {{
                background-color: transparent;
                border: none;
                border-radius: {RADIUS_MD}px;
            }}
            QFrame#todo_image_item:hover {{ background-color: {BG_HOVER}; }}
            QPushButton#todo_checkbox {{
                background-color: transparent; border: none; border-radius: 5px;
            }}
            QPushButton#todo_checkbox:hover {{ background-color: {BG_HOVER_SOFT}; }}
            QPushButton#todo_thumb {{
                background-color: {BG_SECONDARY};
                border: 1px solid {BORDER_SUBTLE};
                border-radius: {RADIUS_MD}px;
                padding: 0px;
            }}
            QPushButton#todo_delete {{
                background-color: transparent; border: none; border-radius: 4px;
            }}
            QPushButton#todo_delete:hover {{ background-color: rgba(0, 0, 0, 0.10); }}
        """)

    def _refresh_check_icon(self):
        icon = 'mdi6.checkbox-marked' if self._checked else 'mdi6.checkbox-blank-outline'
        color = ACCENT_PRIMARY if self._checked else TEXT_TERTIARY
        self.checkbox.setIcon(qta.icon(icon, color=color))
        self.checkbox.setIconSize(QSize(_CHECK_ICON, _CHECK_ICON))

    def _refresh_thumb(self):
        """勾选后淡化缩略图；被裁切时底部加渐隐提示"""
        from PySide6.QtGui import QIcon
        src = self._scaled
        dpr = src.devicePixelRatio()
        if self._crop_bottom:
            overlay = QPixmap(src.size())
            overlay.setDevicePixelRatio(dpr)
            overlay.fill(Qt.GlobalColor.transparent)
            painter = QPainter(overlay)
            grad_h = 26
            for i in range(grad_h):
                t = i / grad_h
                c = QColor(BG_ELEVATED)
                c.setAlpha(int(190 * (t ** 1.6)))
                painter.fillRect(0, src.height() - grad_h + i, src.width(), 1, c)
            painter.end()
            src = QPixmap(src)
            src.setDevicePixelRatio(dpr)
            p2 = QPainter(src)
            p2.drawPixmap(0, 0, overlay)
            p2.end()
        if self._checked:
            src = _dim_pixmap(src)
        self.thumb.setIcon(QIcon(src))

    def set_checked(self, checked: bool):
        """外部设置勾选状态（不发 toggled 信号，避免递归）"""
        self._checked = checked
        self.checkbox.setChecked(checked)
        self._refresh_check_icon()
        self._refresh_thumb()
        self._refresh_meta()

    def set_synced_badge(self, synced: bool):
        """显示/隐藏「已同步」标记"""
        self._synced = synced
        self._refresh_meta()

    def _refresh_meta(self):
        """meta 文案：已同步时追加标记"""
        base = getattr(self, "_meta_base", "截图")
        self.meta.setText(f"{base} · 已同步" if getattr(self, "_synced", False) else base)

    def _on_toggle(self):
        self._checked = self.checkbox.isChecked()
        self._refresh_check_icon()
        self._refresh_thumb()
        self.toggled.emit(self._item_id, self._checked)

    def item_id(self) -> str:
        return self._item_id

    def text(self) -> str:
        return "（截图）"

    def is_checked(self) -> bool:
        return self._checked

    def mouseDoubleClickEvent(self, event):
        self.view_requested.emit(self._item_id)
        super().mouseDoubleClickEvent(event)


class _BatchOcrWorker(QThread):
    """批量对图片待办做 OCR，只保留识别出文字的条目。

    在子线程执行，避免多张图时卡住 UI。
    """

    finished = Signal(list)   # [{"id", "text"}, ...]
    progress = Signal(int, int)

    # 少于该字符数视为「无文字」（OCR 噪点/误检），不推送
    _MIN_TEXT_LEN = 2

    def __init__(self, image_items, parent=None):
        super().__init__(parent)
        self._items = image_items

    def run(self):
        from .ocr import recognize

        converted = []
        total = len(self._items)
        for idx, it in enumerate(self._items, 1):
            try:
                pixmap = QPixmap(it["image_path"])
                if pixmap.isNull():
                    continue
                text = (recognize(pixmap) or "").strip()
                # 过滤掉错误信息与过短噪点
                if not text or text.startswith("[错误]") or len(text) < self._MIN_TEXT_LEN:
                    continue
                converted.append({"id": it["id"], "text": text})
            except Exception:
                continue
            self.progress.emit(idx, total)

        self.finished.emit(converted)


class TodoPinWindow(QWidget):
    """待办屏贴看板（单例）"""

    _SHADOW_MARGIN = _SHADOW_MARGIN

    def __init__(self, parent=None):
        super().__init__(parent)

        self._dragging = False
        self._drag_start = QPoint()
        self._item_widgets = {}
        self._wecom_todo_ids = {}
        self._viewers = []

        self._data = self._load_data()

        self._init_window()
        self._init_ui()
        self._load_items()
        self._apply_content_height()

        self._apply_content_height()

    # ──────────────────────────────
    #  持久化
    # ──────────────────────────────

    @staticmethod
    def _data_file() -> Path:
        TODO_DATA_DIR.mkdir(parents=True, exist_ok=True)
        return TODO_DATA_DIR / f"{BOARD_ID}.json"

    def _load_data(self) -> dict:
        f = self._data_file()
        if f.exists():
            try:
                return json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {
            "id": BOARD_ID,
            "title": "截图待办",
            "items": [],
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }

    def _save(self):
        try:
            self._data_file().write_text(
                json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    @staticmethod
    def _save_image(item_id: str, pixmap: QPixmap) -> str:
        TODO_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
        path = TODO_IMAGE_DIR / f"{item_id}.png"
        pixmap.save(str(path), "PNG")
        return str(path)

    # ──────────────────────────────
    #  窗口与 UI
    # ──────────────────────────────

    def _init_window(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setFixedWidth(_WIN_WIDTH)

    def _init_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(
            _SHADOW_MARGIN, _SHADOW_MARGIN, _SHADOW_MARGIN, _SHADOW_MARGIN)
        outer.setSpacing(0)

        self._card = QFrame()
        self._card.setObjectName("todo_card")
        self._card.setStyleSheet(f"""
            QFrame#todo_card {{
                background-color: {BG_ELEVATED};
                border: 1px solid {BORDER_DEFAULT};
                border-radius: {RADIUS_LG}px;
            }}
        """)
        card_layout = QVBoxLayout(self._card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)

        card_layout.addWidget(self._build_header())
        card_layout.addWidget(self._build_list_area(), stretch=1)
        card_layout.addWidget(self._build_footer())

        outer.addWidget(self._card)

    def _make_icon_btn(self, icon_name: str, tooltip: str, callback):
        # 不设 tooltip：原生 QToolTip 在半透明窗口下会渲染出黑框
        btn = QPushButton()
        btn.setIcon(qta.icon(icon_name, color=TEXT_SECONDARY))
        btn.setIconSize(QSize(ICON_SM, ICON_SM))
        btn.setFixedSize(24, 24)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent; border: none; border-radius: 4px;
            }}
            QPushButton:hover {{ background-color: {BG_HOVER}; }}
        """)
        btn.clicked.connect(callback)
        return btn

    def _build_header(self):
        header = QWidget()
        header.setObjectName("todo_header")
        header.setFixedHeight(36)
        header.setCursor(Qt.CursorShape.SizeAllCursor)
        header.setStyleSheet(f"""
            QWidget#todo_header {{
                background-color: {BG_SECONDARY};
                border-top-left-radius: {RADIUS_LG}px;
                border-top-right-radius: {RADIUS_LG}px;
                border-bottom: 1px solid {BORDER_SUBTLE};
            }}
        """)
        layout = QHBoxLayout(header)
        layout.setContentsMargins(SPACING_MD, 0, SPACING_XS, 0)
        layout.setSpacing(SPACING_XS)

        self._title_label = QLabel(self._data.get("title", "截图待办"))
        self._title_label.setStyleSheet(f"""
            QLabel {{
                color: {TEXT_PRIMARY};
                font-family: {FONT_FAMILY};
                font-size: {FONT_SIZE_MD}px;
                font-weight: 600; background: transparent;
            }}
        """)
        layout.addWidget(self._title_label, stretch=1)

        self._count_label = QLabel()
        self._count_label.setStyleSheet(f"""
            QLabel {{
                color: {TEXT_TERTIARY};
                font-family: {FONT_FAMILY};
                font-size: {FONT_SIZE_SM - 1}px; background: transparent;
            }}
        """)
        layout.addWidget(self._count_label)

        self._btn_clear = self._make_icon_btn(
            'mdi6.broom', "清除已完成", self._clear_done)
        layout.addWidget(self._btn_clear)

        self._btn_sync = self._make_icon_btn(
            'mdi6.cloud-upload-outline', "同步到企业微信待办", self._on_sync)
        layout.addWidget(self._btn_sync)

        self._btn_close = self._make_icon_btn('mdi6.close', "关闭", self.close)
        layout.addWidget(self._btn_close)

        return header

    def _build_list_area(self):
        container = QWidget()
        container.setStyleSheet(f"background-color: {BG_ELEVATED};")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(SPACING_SM, SPACING_SM, SPACING_SM, SPACING_SM)
        layout.setSpacing(0)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setStyleSheet(get_scrollbar_style() + f"""
            QScrollArea {{ background-color: transparent; border: none; }}
        """)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._list_widget = QWidget()
        self._list_widget.setStyleSheet("background-color: transparent;")
        self._list_layout = QVBoxLayout(self._list_widget)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(4)
        self._list_layout.addStretch()

        self._scroll.setWidget(self._list_widget)
        layout.addWidget(self._scroll)
        return container

    def _build_footer(self):
        footer = QWidget()
        footer.setStyleSheet(f"""
            QWidget {{
                background-color: {BG_SECONDARY};
                border-bottom-left-radius: {RADIUS_LG}px;
                border-bottom-right-radius: {RADIUS_LG}px;
                border-top: 1px solid {BORDER_SUBTLE};
            }}
        """)
        layout = QHBoxLayout(footer)
        layout.setContentsMargins(SPACING_SM, SPACING_XS, SPACING_SM, SPACING_XS)
        layout.setSpacing(SPACING_XS)

        self._input = QLineEdit()
        self._input.setPlaceholderText("补充说明，回车添加")
        self._input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {BG_PRIMARY};
                border: 1px solid {BORDER_DEFAULT};
                border-radius: {RADIUS_MD}px; padding: 4px 8px;
                color: {TEXT_PRIMARY};
                font-family: {FONT_FAMILY}; font-size: {FONT_SIZE_SM}px;
            }}
            QLineEdit:focus {{ border: 1px solid {ACCENT_PRIMARY}; }}
        """)
        self._input.returnPressed.connect(self._on_add_item)
        layout.addWidget(self._input, stretch=1)

        self._btn_add = QPushButton()
        self._btn_add.setIcon(qta.icon('mdi6.plus', color='#ffffff'))
        self._btn_add.setFixedSize(28, 28)
        self._btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_add.setStyleSheet(f"""
            QPushButton {{
                background-color: {ACCENT_PRIMARY};
                border: none; border-radius: {RADIUS_MD}px;
            }}
        """)
        self._btn_add.clicked.connect(self._on_add_item)
        layout.addWidget(self._btn_add)
        return footer

    # ──────────────────────────────
    #  条目操作
    # ──────────────────────────────

    def _load_items(self):
        for item in self._data.get("items", []):
            synced = bool(item.get("synced"))
            if item.get("type") == "image":
                path = item.get("image_path")
                if path and Path(path).exists():
                    pm = QPixmap(path)
                    if not pm.isNull():
                        self._add_image_widget(
                            item["id"], pm, item.get("checked", False),
                            item.get("meta", "截图"), synced)
                        continue
                # 图片丢失则降级为文字条目
                self._add_text_widget(
                    item["id"], "（截图已丢失）", item.get("checked", False), synced)
            else:
                self._add_text_widget(
                    item["id"], item.get("text", ""), item.get("checked", False), synced)
        self._update_count()

    def _insert_widget(self, w):
        self._list_layout.insertWidget(self._list_layout.count() - 1, w)
        self._item_widgets[w.item_id()] = w

    def _connect_common(self, w):
        w.toggled.connect(self._on_item_toggled)
        w.remove_requested.connect(self._on_item_removed)

    def _add_text_widget(self, item_id: str, text: str, checked: bool, synced: bool = False):
        w = TodoItemWidget(item_id, text, checked)
        self._connect_common(w)
        w.text_edited.connect(self._on_item_edited)
        if synced:
            w.set_synced_badge(True)
        self._insert_widget(w)
        return w

    def _add_image_widget(self, item_id: str, pixmap: QPixmap, checked: bool,
                          meta: str = "截图", synced: bool = False):
        w = TodoImageItemWidget(item_id, pixmap, checked, meta)
        self._connect_common(w)
        w.view_requested.connect(self._on_view_image)
        if synced:
            w.set_synced_badge(True)
        self._insert_widget(w)
        return w

    def add_image_item(self, pixmap: QPixmap):
        """外部入口：把一张新截图作为待办条目加进看板"""
        if pixmap is None or pixmap.isNull():
            return None
        item_id = f"img_{int(time.time() * 1000)}"
        meta = f"截图 · {time.strftime('%H:%M')}"
        path = self._save_image(item_id, pixmap)
        self._data.setdefault("items", []).append({
            "id": item_id,
            "type": "image",
            "image_path": path,
            "meta": meta,
            "checked": False,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        })
        w = self._add_image_widget(item_id, pixmap, False, meta)
        self._save()
        self._apply_content_height()
        self._update_count()
        QTimer.singleShot(60, self._scroll_to_bottom)
        return w

    def _on_add_item(self):
        text = self._input.text().strip()
        if not text:
            return
        item_id = f"it_{int(time.time() * 1000)}"
        self._data.setdefault("items", []).append({
            "id": item_id, "type": "text", "text": text, "checked": False,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        })
        self._add_text_widget(item_id, text, False)
        self._input.clear()
        self._save()
        self._apply_content_height()
        self._update_count()
        QTimer.singleShot(60, self._scroll_to_bottom)

    def _scroll_to_bottom(self):
        sb = self._scroll.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_item_toggled(self, item_id: str, checked: bool):
        for it in self._data.get("items", []):
            if it["id"] == item_id:
                it["checked"] = checked
                break
        self._save()
        self._update_count()

    def _on_item_removed(self, item_id: str):
        w = self._item_widgets.pop(item_id, None)
        if w:
            self._list_layout.removeWidget(w)
            w.deleteLater()
        items = self._data.get("items", [])
        for it in items:
            if it["id"] == item_id and it.get("image_path"):
                try:
                    Path(it["image_path"]).unlink(missing_ok=True)
                except Exception:
                    pass
        self._data["items"] = [i for i in items if i["id"] != item_id]
        self._save()
        self._apply_content_height()
        self._update_count()

    def _on_item_edited(self, item_id: str, new_text: str):
        for it in self._data.get("items", []):
            if it["id"] == item_id:
                it["text"] = new_text
                break
        self._save()

    def _clear_done(self):
        done = [i for i in self._data.get("items", []) if i.get("checked")]
        for it in done:
            self._on_item_removed(it["id"])

    def _update_count(self):
        items = self._data.get("items", [])
        total = len(items)
        done = sum(1 for i in items if i.get("checked"))
        self._count_label.setText(f"{done}/{total}" if total else "")

    def _on_view_image(self, item_id: str):
        path = None
        for it in self._data.get("items", []):
            if it["id"] == item_id:
                path = it.get("image_path")
                break
        if not path or not Path(path).exists():
            return
        try:
            from ui.image_viewer import ImageViewer
            # 传入全部图片，看图器内可上一张/下一张
            images = [it.get("image_path") for it in self._data.get("items", [])
                      if it.get("image_path") and Path(it["image_path"]).exists()]
            v = ImageViewer(path, file_list=images)
            v.show()
            self._viewers.append(v)
            v.destroyed.connect(lambda _, vv=v: self._viewers.remove(vv)
                                if vv in self._viewers else None)
        except Exception:
            pass

    def _apply_content_height(self):
        """按内容自适应高度（图片条目按实际缩略图高度计）"""
        h = 0
        for w in self._item_widgets.values():
            h += max(w.sizeHint().height(), 26) + 4
        list_h = min(max(h, 48), _LIST_MAX_H)
        # 阴影 24 + 标题 36 + 列表内边距 16 + 列表 + 底栏 44 + 边框 2
        self.setFixedHeight(_SHADOW_MARGIN * 2 + 36 + 16 + list_h + 44 + 2)

    # ──────────────────────────────
    #  企微同步
    # ──────────────────────────────

    @staticmethod
    def _is_syncable(it: dict) -> bool:
        """是否可被同步：未勾选 + 未同步过。

        synced 标记会落盘，故重启后已推送的条目不会重复推送。
        """
        return (not it.get("checked")) and (not it.get("synced"))

    def _on_sync(self):
        items = self._data.get("items", [])
        pending_text = [i for i in items
                        if i.get("type", "text") == "text" and self._is_syncable(i)]
        # 图片条目：OCR 结果缓存在 image_text 上，识别不出文字的会被丢弃
        pending_images = [i for i in items
                          if i.get("type") == "image"
                          and i.get("image_path")
                          and Path(i["image_path"]).exists()
                          and self._is_syncable(i)]

        if not pending_text and not pending_images:
            self._flash_message("没有可同步的待办")
            return

        self._btn_sync.setEnabled(False)

        if not pending_images:
            self._flash_message("正在同步…", sticky=True)
            QTimer.singleShot(0, lambda: self._do_sync(pending_text, []))
            return

        # 有图片 → 先 OCR（子线程），完成后连同文字条目一起推送
        self._flash_message(f"正在识别 {len(pending_images)} 张图片…", sticky=True)
        self._ocr_worker = _BatchOcrWorker(pending_images)
        self._ocr_worker.progress.connect(
            lambda done, total: self._flash_message(
                f"正在识别图片 {done}/{total}…", sticky=True))
        self._ocr_worker.finished.connect(
            lambda converted: self._on_ocr_before_sync(pending_text, converted))
        self._ocr_worker.start()

    def _apply_synced_visuals(self, item_ids):
        """把已同步条目在界面上打勾并标记（不触发 toggled 信号）"""
        ids = set(item_ids)
        for iid, w in list(self._item_widgets.items()):
            if iid not in ids:
                continue
            try:
                w.set_synced_badge(True)
                w.set_checked(True)
            except Exception:
                pass
        self._update_count()

    def _on_ocr_before_sync(self, pending_text, converted):
        """OCR 完成回调：把识别出文字的图片条目转成文字条目一起同步"""
        if not converted and not pending_text:
            self._flash_message("图片未识别到文字")
            self._btn_sync.setEnabled(True)
            return

        self._flash_message("正在同步…", sticky=True)
        QTimer.singleShot(0, lambda: self._do_sync(pending_text, converted))

    def _do_sync(self, pending_text, pending_converted):
        """推送到企微。

        pending_text: 原有文字条目
        pending_converted: 由图片 OCR 转换而来的 [{"id", "text"}, ...]

        推送成功后给条目打上 synced 标记并落盘，避免下次重复推送。
        """
        payload = list(pending_text) + list(pending_converted)

        # 图片条目同步成功后，把 OCR 文本写回本地条目，便于下次查看
        converted_map = {c["id"]: c["text"] for c in pending_converted}

        from ui.wecom_todo import WeComTodoClient
        client = WeComTodoClient()
        ok_ids = {}
        err = ""

        try:
            ok_ids, err = client.create_todos(self._data.get("title", "截图待办"), payload)
        except Exception as e:
            err = str(e)

        if err:
            self._flash_message(f"同步失败：{err}")
            # 失败不打标记，下次仍可重试
            self._btn_sync.setEnabled(True)
            return

        self._wecom_todo_ids.update(ok_ids)
        pushed = 0
        for it in self._data.get("items", []):
            if it["id"] not in ok_ids:
                continue
            it["synced"] = True
            it["checked"] = True   # 已提交的自动打勾，符合"提交完就完成"的直觉
            pushed += 1
            if it["id"] in converted_map:
                it["image_text"] = converted_map[it["id"]]
        self._save()
        self._apply_synced_visuals(ok_ids.keys())

        if pushed == 0:
            self._flash_message("同步成功但未确认条目")
        elif pending_converted:
            self._flash_message(f"已同步 {pushed} 条（含 {len(pending_converted)} 条图片转文字）")
        else:
            self._flash_message(f"已同步 {pushed} 条")
        self._btn_sync.setEnabled(True)

    def _flash_message(self, message: str, sticky: bool = False):
        """在标题栏计数标签上临时显示反馈文字（不使用 tooltip）。

        sticky=True 时不清自动恢复，需由后续调用覆盖。
        """
        if not hasattr(self, "_count_label"):
            return
        self._count_label.setText(message)
        if sticky:
            return
        QTimer.singleShot(2500, self._update_count)

    # ──────────────────────────────
    #  交互
    # ──────────────────────────────

    def bring_to_front(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            header = self._card.findChild(QWidget, "todo_header")
            # 注意坐标系：header.geometry() 是相对 _card 的，而 event.position()
            # 是相对窗口的，两者差一个 _SHADOW_MARGIN 留白。必须把事件坐标映射
            # 到 header 自身坐标系再判定，否则命中区会整体上移，标题栏下半部分拖不动。
            if header and header.rect().contains(
                    header.mapFrom(self, event.position().toPoint())):
                self._dragging = True
                self._drag_start = (
                    event.globalPosition().toPoint() - self.frameGeometry().topLeft())
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging:
            self.move(event.globalPosition().toPoint() - self._drag_start)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._dragging = False
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        # 统一走主题投影规范，与普通屏贴保持一致
        m = _SHADOW_MARGIN
        rect = self.rect().adjusted(m, m, -m, -m)
        draw_shadow(painter, rect, min(rect.width(), rect.height()), RADIUS_LG)
        super().paintEvent(event)

    def closeEvent(self, event):
        self._save()
        super().closeEvent(event)


def get_todo_board(create: bool = False):
    """获取待办看板单例（不存在则按需创建）。

    追加截图请统一调用返回的 `add_image_item(pixmap)`，
    工厂本身不负责加图，避免与构造流程重复。
    """
    app = QApplication.instance()
    board = getattr(app, "_todo_board", None)

    if board is not None:
        try:
            board.isVisible()  # 探测 C++ 对象是否仍存活
        except RuntimeError:
            board = None

    if board is None and create:
        board = TodoPinWindow()
        app._todo_board = board
        board.destroyed.connect(lambda: setattr(app, "_todo_board", None))

    return board
