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
FONT_FAMILY = "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Microsoft YaHei', Roboto, sans-serif"

# 等宽字体栈（用于代码、路径显示）
FONT_FAMILY_MONO = "'Cascadia Code', 'Consolas', 'Microsoft YaHei', monospace"

# QFont 使用的字体名（Qt 原生）
FONT_NAME = "Microsoft YaHei"
FONT_NAME_MONO = "Cascadia Code"

# 字号
FONT_SIZE_XS = 11
FONT_SIZE_SM = 12
FONT_SIZE_MD = 13
FONT_SIZE_LG = 14
FONT_SIZE_XL = 16
FONT_SIZE_XXL = 18


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
BG_HOVER_SUBTLE = "rgba(0, 0, 0, 0.04)" # Hover 次级层

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
ACCENT_BORDER_HOVER = "#69b1ff" # 强调色边框 Hover - Ant Blue 4

# 语义色
COLOR_SUCCESS = "#52c41a"      # 成功 - Ant Green 6
COLOR_WARNING = "#faad14"      # 警告 - Ant Gold 6
COLOR_ERROR = "#ff4d4f"        # 错误 - Ant Red 5
COLOR_INFO = "#1677ff"         # 信息 - Ant Blue 6
COLOR_SUCCESS_SUBTLE = "#f6ffed" # 成功背景 - Ant Green 1
COLOR_WARNING_SUBTLE = "#fffbe6" # 警告背景 - Ant Gold 1
COLOR_ERROR_SUBTLE = "#fff1f0"   # 错误背景 - Ant Red 1
COLOR_INFO_SUBTLE = "#e6f4ff"    # 信息背景 - Ant Blue 1


# 品牌/文件图标
ICON_FOLDER = COLOR_WARNING
FILE_ICON_PSD = "#31A8FF"
FILE_ICON_IMAGE = COLOR_SUCCESS
FILE_ICON_GIF = COLOR_ERROR
BRAND_WECHAT = "#07c160"


# 资源类型颜色（与 config.py RESOURCE_TYPES 保持一致）
TYPE_COLORS = {
    "KV": COLOR_ERROR,         # 红
    "拍脸": "#13c2c2",         # 青
    "海报": COLOR_INFO,         # 蓝
    "界面": COLOR_SUCCESS,      # 绿
}



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

# 组件尺寸
SIDEBAR_WIDTH = 260
ACTIVITY_BAR_WIDTH = 48
ACTIVITY_ICON_SIZE = 24
TOOLBAR_HEIGHT = 52
BTN_SIZE = 32
BTN_SIZE_SM = 28



# ============================================================
# 组件样式生成器
# ============================================================

def get_sidebar_style():
    """侧栏样式"""
    return f"""
        QWidget#sidebar {{
            background: {BG_SECONDARY};
            border-right: 1px solid {BORDER_DEFAULT};
        }}
    """


def get_sidebar_header_style():
    """侧栏头部样式"""
    return f"""
        QWidget#sidebar_header {{
            background: transparent;
            border-bottom: 1px solid {BORDER_DEFAULT};
        }}
        QLabel#workspace_name {{
            color: {TEXT_PRIMARY};
            font-size: 13px;
            font-weight: 600;
        }}
    """


def get_search_box_style():
    """搜索框样式"""
    return f"""
        QLineEdit#search_input {{
            background: {BG_PRIMARY};
            border: 1px solid {BORDER_DEFAULT};
            border-radius: {RADIUS_MD}px;
            padding: 8px 12px 8px 32px;
            color: {TEXT_PRIMARY};
            font-size: 13px;
            selection-background-color: {ACCENT_PRIMARY};
        }}
        QLineEdit#search_input:focus {{
            border-color: {ACCENT_PRIMARY};
            background: {BG_PRIMARY};
        }}
        QLineEdit#search_input::placeholder {{
            color: {TEXT_TERTIARY};
        }}
    """


def get_topic_item_style(hover=False, selected=False):
    """主题项样式"""
    if selected:
        bg = BG_ACTIVE
    elif hover:
        bg = BG_HOVER
    else:
        bg = "transparent"
    
    return f"""
        QFrame#topic_item {{
            background: {bg};
            border-radius: {RADIUS_MD}px;
            border: none;
        }}
    """


def get_file_item_style(hover=False, selected=False):
    """文件项样式"""
    if selected:
        bg = BG_ACTIVE
        text_color = TEXT_PRIMARY
    elif hover:
        bg = BG_HOVER
        text_color = TEXT_PRIMARY
    else:
        bg = "transparent"
        text_color = TEXT_SECONDARY
    
    return f"""
        QFrame#file_item {{
            background: {bg};
            border-radius: {RADIUS_SM}px;
            border: none;
        }}
        QLabel#file_name {{
            color: {text_color};
            font-size: 12px;
        }}
    """


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


def get_toolbar_style():
    """工具栏样式（浅色）"""
    return f"""
        QWidget#toolbar {{
            background: {BG_PRIMARY};
            border: 1px solid {BORDER_DEFAULT};
            border-radius: {RADIUS_XL}px;
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


def get_canvas_style():
    """画布样式"""
    return f"""
        QWidget#canvas {{
            background: {BG_SECONDARY};
        }}
    """


def get_empty_state_style():
    """空状态样式"""
    return f"""
        QLabel#empty_title {{
            color: {TEXT_SECONDARY};
            font-size: 15px;
            font-weight: 500;
        }}
        QLabel#empty_subtitle {{
            color: {TEXT_TERTIARY};
            font-size: 13px;
        }}
    """


# ============================================================
# 图标颜色
# ============================================================

ICON_DEFAULT = TEXT_SECONDARY
ICON_HOVER = TEXT_PRIMARY
ICON_ACCENT = ACCENT_PRIMARY
ICON_MUTED = TEXT_TERTIARY


# ============================================================
# 通用表单组件样式
# ============================================================

def get_group_box_style():
    """QGroupBox 样式"""
    return f"""
        QGroupBox {{
            font-weight: 600;
            font-size: 13px;
            color: {TEXT_PRIMARY};
            border: 1px solid {BORDER_DEFAULT};
            border-radius: {RADIUS_LG}px;
            margin-top: 16px;
            padding: 16px 12px 12px 12px;
            background: {BG_PRIMARY};
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            subcontrol-position: top left;
            left: 12px;
            top: 4px;
            padding: 0 6px;
            background: {BG_PRIMARY};
        }}
    """


def get_radio_style():
    """QRadioButton 样式"""
    return f"""
        QRadioButton {{
            color: {TEXT_SECONDARY};
            font-size: 13px;
            padding: 4px;
        }}
        QRadioButton:hover {{
            color: {TEXT_PRIMARY};
        }}
        QRadioButton::indicator {{
            width: 18px;
            height: 18px;
            border: 1px solid {BORDER_DEFAULT};
            border-radius: 9px;
            background: {BG_PRIMARY};
        }}
        QRadioButton::indicator:hover {{
            border-color: {ACCENT_PRIMARY};
        }}
        QRadioButton::indicator:checked {{
            background: {ACCENT_PRIMARY};
            border-color: {ACCENT_PRIMARY};
            image: url(ui/resources/radio_checked.svg); /* 需要确保图标存在或使用绘制方式 */
        }}
    """


def get_checkbox_style():
    """QCheckBox 样式"""
    return f"""
        QCheckBox {{
            color: {TEXT_SECONDARY};
            font-size: 13px;
            padding: 4px;
        }}
        QCheckBox:hover {{
            color: {TEXT_PRIMARY};
        }}
        QCheckBox::indicator {{
            width: 18px;
            height: 18px;
            border: 1px solid {BORDER_DEFAULT};
            border-radius: 4px;
            background: {BG_PRIMARY};
        }}
        QCheckBox::indicator:hover {{
            border-color: {ACCENT_PRIMARY};
        }}
        QCheckBox::indicator:checked {{
            background: {ACCENT_PRIMARY};
            border-color: {ACCENT_PRIMARY};
            image: url(ui/resources/checkbox_checked.svg);
        }}
    """



def get_combo_style():
    """QComboBox 样式"""
    return f"""
        QComboBox {{
            padding: 6px 10px;
            border: 1px solid {BORDER_DEFAULT};
            border-radius: {RADIUS_MD}px;
            background: {BG_PRIMARY};
            min-height: 24px;
            font-size: 13px;
            color: {TEXT_PRIMARY};
        }}
        QComboBox:disabled {{
            background: {BG_SECONDARY};
            color: {TEXT_TERTIARY};
        }}
        QComboBox:focus {{
            border-color: {ACCENT_PRIMARY};
        }}
        QComboBox::drop-down {{
            subcontrol-origin: padding;
            subcontrol-position: center right;
            width: 20px;
            border: none;
        }}
    """


def get_btn_primary_style():
    """主要按钮样式"""
    return f"""
        QPushButton {{
            background: {ACCENT_PRIMARY};
            color: white;
            border: none;
            border-radius: {RADIUS_MD}px;
            padding: 10px 20px;
            font-size: 13px;
            font-weight: 500;
        }}
        QPushButton:hover {{
            background: {ACCENT_HOVER};
        }}
        QPushButton:pressed {{
            background: #004099;
        }}
        QPushButton:disabled {{
            background: {TEXT_TERTIARY};
        }}
    """


def get_btn_secondary_style():
    """次要按钮样式"""
    return f"""
        QPushButton {{
            background: {BG_PRIMARY};
            color: {TEXT_SECONDARY};
            border: 1px solid {BORDER_DEFAULT};
            border-radius: {RADIUS_MD}px;
            padding: 10px 20px;
            font-size: 13px;
        }}
        QPushButton:hover {{
            background: {BG_HOVER};
            border-color: {BORDER_DEFAULT};
        }}
        QPushButton:pressed {{
            background: {BG_ACTIVE};
        }}
    """


def get_line_edit_style():
    """QLineEdit & QKeySequenceEdit 样式"""
    return f"""
        QLineEdit, QKeySequenceEdit {{
            background: {BG_PRIMARY};
            border: 1px solid {BORDER_DEFAULT};
            border-radius: {RADIUS_MD}px;
            padding: 8px 12px;
            font-size: 13px;
            color: {TEXT_PRIMARY};
        }}
        QLineEdit:focus, QKeySequenceEdit:focus {{
            border-color: {ACCENT_PRIMARY};
        }}
        QLineEdit:disabled, QKeySequenceEdit:disabled {{
            background: {BG_SECONDARY};
            color: {TEXT_TERTIARY};
        }}
    """



def get_text_edit_style():

    """QTextEdit 样式"""
    return f"""
        QTextEdit {{
            background: {BG_PRIMARY};
            border: 1px solid {BORDER_DEFAULT};
            border-radius: {RADIUS_MD}px;
            padding: 8px;
            font-size: 13px;
            color: {TEXT_PRIMARY};
        }}
        QTextEdit:focus {{
            border-color: {ACCENT_PRIMARY};
        }}
    """


def get_btn_success_style():
    """成功/提交按钮样式"""
    return f"""
        QPushButton {{
            background: {COLOR_SUCCESS};
            color: white;
            border: none;
            border-radius: {RADIUS_MD}px;
            padding: 10px 20px;
            font-size: 13px;
            font-weight: 500;
        }}
        QPushButton:hover {{
            background: #16a34a;
        }}
        QPushButton:pressed {{
            background: #15803d;
        }}
        QPushButton:disabled {{
            background: #bbf7d0;
        }}
    """


def get_preview_frame_style():
    """预览区域样式"""
    return f"""
        QFrame {{
            background: {ACCENT_SUBTLE};
            border: 1px solid rgba(0, 102, 255, 0.1);
            border-radius: {RADIUS_MD}px;
        }}
        QLabel {{
            background: transparent;
        }}
    """

def get_dialog_style():
    """对话框通用样式 (QMessageBox, QInputDialog 等)"""
    return f"""
        QDialog, QMessageBox, QInputDialog {{

            background-color: {BG_PRIMARY};
        }}
        QLabel {{
            color: {TEXT_PRIMARY};
            font-size: 13px;
        }}
        QPushButton {{
            background: {BG_PRIMARY};
            color: {TEXT_SECONDARY};
            border: 1px solid {BORDER_DEFAULT};
            border-radius: {RADIUS_MD}px;
            padding: 6px 16px;
            min-width: 60px;
            font-size: 13px;
        }}
        QPushButton:hover {{
            background: {BG_HOVER};
        }}
        QPushButton:pressed {{
            background: {BG_ACTIVE};
        }}
        QPushButton:default {{
            background: {ACCENT_PRIMARY};
            color: white;
            border: none;
        }}
        QPushButton:default:hover {{
            background: {ACCENT_HOVER};
        }}
        QLineEdit {{
            background: {BG_PRIMARY};
            border: 1px solid {BORDER_DEFAULT};
            border-radius: {RADIUS_MD}px;
            padding: 6px 10px;
            color: {TEXT_PRIMARY};
            font-size: 13px;
        }}
        QLineEdit:focus {{
            border-color: {ACCENT_PRIMARY};
        }}
    """

