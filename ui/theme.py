"""
Artco 统一设计系统 - 浅色模式 (Ant Design 风格)

设计原则：
1. 清晰的中性灰阶分层
2. 统一的交互状态色
3. 规范的语义色体系
4. 蓝色主强调色（Ant Design）
"""

# ============================================================
# 字体规范
# ============================================================

# 主字体栈（用于 QSS font-family）
FONT_FAMILY = "'Microsoft YaHei UI', 'Segoe UI', sans-serif"

# 等宽字体栈（用于代码、路径显示）
FONT_FAMILY_MONO = "'Cascadia Code', 'Consolas', 'Microsoft YaHei', monospace"

# QFont 使用的字体名（Qt 原生）
FONT_NAME = "Microsoft YaHei"

# 字号
FONT_SIZE_XS = 11
FONT_SIZE_SM = 12
FONT_SIZE_MD = 13
FONT_SIZE_LG = 14
FONT_SIZE_XL = 16


# ============================================================
# 核心色板
# ============================================================

# 背景层级（从浅到深）
BG_PRIMARY = "#ffffff"       # 主背景 - 纯白
BG_SECONDARY = "#f5f5f5"     # 次级背景 - 画布/侧栏
BG_ELEVATED = "#ffffff"      # 抬升元素 - 卡片/弹窗
BG_HOVER = "#f5f5f5"         # Hover 状态
BG_ACTIVE = "#f0f0f0"        # Active/Selected 状态
BG_HOVER_SOFT = "rgba(0, 0, 0, 0.03)"   # Hover 轻弱层

# 边框
BORDER_SUBTLE = "#f0f0f0"    # 微光边框
BORDER_DEFAULT = "#d9d9d9"   # 默认边框
BORDER_STRONG = "#bfbfbf"    # 强调边框

# 文字
TEXT_PRIMARY = "rgba(0, 0, 0, 0.88)"     # 主文字
TEXT_SECONDARY = "rgba(0, 0, 0, 0.65)"   # 次级文字
TEXT_TERTIARY = "rgba(0, 0, 0, 0.45)"    # 三级文字/占位符
TEXT_MUTED = "rgba(0, 0, 0, 0.25)"       # 禁用/最弱文字

# 主题色
ACCENT_PRIMARY = "#1677ff"     # 主强调色 - Ant Blue 6
ACCENT_HOVER = "#4096ff"       # Hover - Ant Blue 5
ACCENT_PRESSED = "#0958d9"     # Pressed - Ant Blue 7
ACCENT_SUBTLE = "#e6f4ff"      # 强调色背景 - Ant Blue 1
ACCENT_BORDER = "#91caff"      # 强调色边框 - Ant Blue 3

# 语义色
COLOR_SUCCESS = "#52c41a"      # 成功 - Ant Green 6
COLOR_WARNING = "#faad14"      # 警告 - Ant Gold 6
COLOR_ERROR = "#ff4d4f"        # 错误 - Ant Red 5
COLOR_INFO = "#1677ff"         # 信息 - Ant Blue 6

# 表单控件强调色（ui/fluent_controls.py 使用）
# 沿用原 qfluentwidgets 默认主题色 #009faa 及其派生色，保证去依赖后视觉不变。
FORM_ACCENT = "#009faa"          # 主色
FORM_ACCENT_LIGHT_1 = "#00a7b3"  # Hover 背景 / 主色描边
FORM_ACCENT_LIGHT_2 = "#2daab3"  # Hover 描边
FORM_ACCENT_LIGHT_3 = "#3eabb3"  # Pressed
FORM_ACCENT_DARK_1 = "#007780"   # 底部描边
FORM_FONT_FAMILIES = ["Segoe UI", "Microsoft YaHei", "PingFang SC"]
FORM_FONT_PX = 14


# ============================================================
# 尺寸规范
# ============================================================

# 圆角
RADIUS_SM = 4      # 小元素
RADIUS_MD = 8      # 中等元素（按钮、输入框）
RADIUS_LG = 12     # 大元素（卡片、面板）
RADIUS_XL = 16     # 特大元素（弹窗、工具栏）

# 间距
SPACING_XS = 4
SPACING_SM = 8
SPACING_MD = 12
SPACING_LG = 16
SPACING_XL = 24

# 图标
ICON_SM = 14
ICON_MD = 18
ICON_LG = 20

# 复选框（待办条目）：图标是视觉尺寸，热区是可点击范围。
# 热区明显大于图标，保证小图标也好点中；文字条目用热区与行高之差做垂直补偿。
CHECKBOX_ICON = 18
CHECKBOX_HIT = 24

# 组件尺寸
BTN_SIZE = 32
BTN_SIZE_SM = 28


# ============================================================
# 悬浮投影规范（屏贴 / 待办板等浮窗共用）
# ============================================================

# 投影外扩留白：窗口需留出这么多像素给投影，否则会被裁掉
SHADOW_MARGIN = 12

# 投影层参数（与尺寸联动，保持视觉一致）
SHADOW_MAX_SPREAD = 8     # 最外层扩散像素
SHADOW_Y_OFFSET = 2       # 向下偏移，模拟自然光
SHADOW_MAX_ALPHA = 10     # 最内层浓度
SHADOW_LAYERS = 8         # 叠加层数（越多越平滑）


def shadow_layers(size: int):
    """按元素尺寸计算投影分层，返回 [(spread, alpha), ...]（外 → 内）。

    屏贴、截图待办板等所有浮窗统一调用，避免各处各写一套导致
    投影深浅/扩散不一致。参数由尺寸缩放，小元素自动减弱投影。
    """
    scale = min(1.0, max(0.4, size / 200))
    max_spread = int(SHADOW_MAX_SPREAD * scale)
    y_offset = int(SHADOW_Y_OFFSET * scale)
    max_alpha = int(SHADOW_MAX_ALPHA * scale)

    layers = []
    for i in range(SHADOW_LAYERS):
        t = i / max(1, SHADOW_LAYERS - 1)   # 0(外) → 1(内)
        spread = int(max_spread * (1.0 - t))
        alpha = int(max_alpha * (t ** 1.5))  # 指数衰减：外层极淡
        if alpha > 0:
            layers.append((spread, alpha))
    return layers, y_offset, max_spread


def draw_shadow(painter, rect, min_side, radius=RADIUS_LG, y_offset=None):
    """把统一投影画到 rect 外围（会向外扩画，rect 本身不填充）。

    painter 需已开启 Antialiasing；rect 为内容区（卡片）矩形。
    """
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor

    layers, y_off, _ = shadow_layers(min_side)
    if y_offset is not None:
        y_off = y_offset

    painter.setPen(Qt.PenStyle.NoPen)
    for spread, alpha in layers:
        r = rect.adjusted(-spread, -spread + y_off, spread, spread + y_off)
        painter.setBrush(QColor(0, 0, 0, alpha))
        painter.drawRoundedRect(r, radius, radius)



# ============================================================
# 组件样式生成器
# ============================================================

def get_icon_button_style(color=None, danger=False):
    """图标按钮样式"""
    if danger:
        hover_bg = "rgba(239, 68, 68, 0.1)"
    elif color:
        hover_bg = "rgba(0, 102, 255, 0.1)"
    else:
        hover_bg = BG_HOVER
    
    return f"""
        QPushButton {{
            background: transparent;
            border: none;
            border-radius: {RADIUS_SM}px;
        }}
        QPushButton:hover {{
            background: {hover_bg};
        }}
        QPushButton:pressed {{
            background: {BG_ACTIVE};
        }}
    """


def get_scrollbar_style():
    """滚动条样式"""
    return f"""
        QScrollBar:vertical {{
            background: transparent;
            width: 6px;
            margin: 0;
        }}
        QScrollBar::handle:vertical {{
            background: {BORDER_STRONG};
            border-radius: 3px;
            min-height: 30px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: {TEXT_TERTIARY};
        }}
        QScrollBar::add-line:vertical, 
        QScrollBar::sub-line:vertical {{
            height: 0;
        }}
        QScrollBar::add-page:vertical,
        QScrollBar::sub-page:vertical {{
            background: transparent;
        }}
    """


# ============================================================
# 图标颜色
# ============================================================

ICON_DEFAULT = TEXT_SECONDARY
ICON_HOVER = TEXT_PRIMARY
ICON_ACCENT = ACCENT_PRIMARY
ICON_MUTED = TEXT_TERTIARY


# ── 右键菜单统一样式 ──
MENU_STYLE = """
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
"""

