"""
Artco - AI 截图工具
主入口文件
"""

import sys
import os
import base64
import threading

# 设置 Qt API 为 PySide6（必须在导入 qtawesome 之前）
os.environ['QT_API'] = 'pyside6'

import qtawesome as qta
from PySide6.QtWidgets import (
    QApplication, QWidget, QHBoxLayout, QPushButton, QGraphicsDropShadowEffect,
    QMenu, QSystemTrayIcon, QLabel
)

from PySide6.QtCore import (
    Qt, QSize, Signal, QTimer, QPropertyAnimation, QEasingCurve, Property, QPoint, QSharedMemory,
    QBuffer, QIODevice
)

from PySide6.QtGui import QColor, QFont, QGuiApplication, QIcon, QPixmap


from version import APP_VERSION, APP_NAME
from config import ai_config, get_bundle_dir, appearance_config
from ui.theme import MENU_STYLE

from database import init_database, add_record
from utils import hotkey_manager, convert_hotkey_format
import updater
from ui import (
    AIWorker, AIResultBubble, AIImageResultWindow, SettingsDialog, WorkbenchWindow,
    ClipboardHistoryManager, ClipboardFloatPanel
)
from screenshot import ScreenshotOverlay, ScreenSelector, PinWindow


def get_app_icon():
    icon_path = os.path.join(get_bundle_dir(), "icon", "artco.png")
    if os.path.exists(icon_path):
        return QIcon(icon_path)
    return qta.icon('mdi6.crop', color='#ffffff')


class CapsuleWidget(QWidget):

    """胶囊浮窗 - 主界面"""
    hotkey_triggered = Signal()
    clipboard_float_requested = Signal()  # 请求显示剪贴板悬浮面板
    update_check_result = Signal(bool, object)  # 检查更新结果
    update_check_timeout = Signal()  # 检查更新超时
    
    def _build_bg_css(self, border_radius: int = None, border: str = None, border_color: str = None) -> str:
        """从 appearance_config 动态生成 #container 背景样式"""
        if border_radius is None:
            border_radius = appearance_config.get_border_radius()
        if border is None:
            border = appearance_config.get_border_css()
        if border_color:
            border = f"1px solid {border_color}"

        bg = appearance_config.get_background_css(border_radius=border_radius)
        return f"""
            #container {{
                {bg}
                border-radius: {border_radius}px;
                border: {border};
            }}"""

    def __init__(self):
        super().__init__()
        self._breathing_value = 0.0
        self._is_processing = False
        self._force_hidden = False  # 强制隐藏模式
        self.ai_worker = None
        self.ai_bubble = None
        self.ai_result_text = ""  # 保存 AI 结果文本，供编辑器归档使用
        
        # 多轮对话历史
        self._conversation_history = []  # OpenAI messages 格式
        self._conversation_image = None  # 首次截图的 base64 数据（追问时不重传）
        self._original_task_type = "vision"  # 记录原始任务类型（vision / image_gen）
        
        # 三点加载动画状态
        self._loading_dot_index = 0
        self._loading_timer = QTimer(self)
        self._loading_timer.timeout.connect(self._update_loading_dots)
        
        self.hotkey_triggered.connect(self.start_screenshot)
        self.clipboard_float_requested.connect(self._show_clipboard_float)
        self.update_check_result.connect(self._on_tray_update_result)
        self.update_check_timeout.connect(self._on_tray_update_timeout)
        
        self.init_ui()
        self._saved_pos = None
        QApplication.instance()._capsule_widget = self
        
        self._setup_breathing_animation()
        self._setup_pop_animation()
        self._setup_global_hotkey()
        self._setup_clipboard_float_hotkey()  # 注册剪贴板悬浮面板快捷键
        self._setup_tray_icon()
        
        # 启动剪贴板监听，确保截图复制的内容能被归档界面记录
        ClipboardHistoryManager.instance().start_monitoring()
    
    def _setup_breathing_animation(self):
        self.breathing_animation = QPropertyAnimation(self, b"breathing_value")
        self.breathing_animation.setDuration(3000)
        self.breathing_animation.setStartValue(0.0)
        self.breathing_animation.setEndValue(1.0)
        self.breathing_animation.setEasingCurve(QEasingCurve.Type.Linear)
        self.breathing_animation.setLoopCount(-1)
    
    def _setup_pop_animation(self):
        self._fade_anim = QPropertyAnimation(self, b"windowOpacity")
        self._fade_anim.setDuration(220)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        
        self._pop_pos_anim = QPropertyAnimation(self, b"pos")
        self._pop_pos_anim.setDuration(320)
        self._pop_pos_anim.setEasingCurve(QEasingCurve.Type.OutBack)

    
    def get_breathing_value(self):
        return self._breathing_value

    
    def set_breathing_value(self, value):
        self._breathing_value = value
        self._update_breathing_style()
    
    breathing_value = Property(float, get_breathing_value, set_breathing_value)
    
    def _update_loading_dots(self):
        """更新弹跳球加载动画 - 三个球依次上下弹跳"""
        # 用不同大小的点模拟弹跳高度：●在下(落地)，·在上(弹起)
        bounce_frames = [
            '●  ·  ·',  # 球1落地，球2、3弹起
            '·  ●  ·',  # 球2落地
            '·  ·  ●',  # 球3落地
            '·  ·  ●',  # 停顿
            '·  ●  ·',  # 返回
            '●  ·  ·',  # 返回
        ]
        self.btn_screenshot.setText(bounce_frames[self._loading_dot_index])
        self.btn_screenshot.setIcon(QIcon())  # 清除图标，只显示文字
        self._loading_dot_index = (self._loading_dot_index + 1) % 6
    
    def _update_breathing_style(self):
        if not self._is_processing:
            return
        
        # 彩虹色循环：使用 HSV 色相旋转，降低饱和度营造柔和感
        import colorsys
        hue = self._breathing_value  # 0.0 ~ 1.0 对应色相 0° ~ 360°
        r, g, b = colorsys.hsv_to_rgb(hue, 0.35, 0.92)
        r, g, b = int(r * 255), int(g * 255), int(b * 255)
        
        # 计算渐变终点颜色（色相偏移）
        hue2 = (hue + 0.08) % 1.0
        r2, g2, b2 = colorsys.hsv_to_rgb(hue2, 0.35, 0.92)
        r2, g2, b2 = int(r2 * 255), int(g2 * 255), int(b2 * 255)
        
        bg_css = self._build_bg_css()
        # 转换为大括号格式（f-string 兼容）
        bg_css_f = bg_css.replace("{", "{{").replace("}", "}}")
        
        self.container.setStyleSheet(f"""
            {bg_css_f}
            QPushButton#btn_screenshot {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba({r}, {g}, {b}, 0.9),
                    stop:1 rgba({r2}, {g2}, {b2}, 0.9));
                border: 1px solid rgba(255, 255, 255, 0.35);
                border-radius: 8px;
                color: rgba(255, 255, 255, 0.95);
            }}

            QPushButton#btn_archive {{
                background-color: transparent;
                border: none;
                border-radius: 8px;
            }}
            QPushButton#btn_archive:hover {{ background-color: rgba(0, 0, 0, 0.08); }}
            QPushButton#btn_archive:pressed {{ background-color: rgba(0, 0, 0, 0.12); }}
        """)

    
    def reveal(self, animated: bool = True):
        if not animated:
            self._pop_pos_anim.stop()
            self._fade_anim.stop()
            self.setWindowOpacity(1.0)
            super().show()
            self.raise_()
            return
        if self.isVisible():
            self.raise_()
            return
        self._pop_pos_anim.stop()
        self._fade_anim.stop()
        target_pos = self.pos()
        start_pos = QPoint(target_pos.x(), target_pos.y() + 18)
        self.move(start_pos)
        self.setWindowOpacity(0.0)
        super().show()
        self.raise_()
        self._pop_pos_anim.setStartValue(start_pos)
        self._pop_pos_anim.setEndValue(target_pos)
        self._pop_pos_anim.start()
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.start()

    
    def start_ai_processing(self, base64_data: str, prompt: str = None, prompt_type: str = "text"):
        self._is_processing = True

        self._current_image_data = base64.b64decode(base64_data)
        
        # 初始化对话历史（新对话）
        self._conversation_history = []
        self._conversation_image = base64_data
        self._original_task_type = ai_config.get("task_type", "vision")
        
        # 构建首条消息（带图片）
        from config import DEFAULT_PROMPT
        first_prompt = prompt or DEFAULT_PROMPT
        first_message = {
            "role": "user",
            "content": [
                {"type": "text", "text": first_prompt},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{base64_data}"
                    }
                }
            ]
        }
        self._conversation_history.append(first_message)
        
        # 启动弹跳点加载动画
        self._loading_dot_index = 0
        self._update_loading_dots()
        self._loading_timer.start(200)  # 每200ms切换，弹跳更生动
        
        self.btn_screenshot.setIconSize(QSize(18, 18))
        self.btn_screenshot.setEnabled(False)
        
        self.breathing_animation.start()
        
        # AI 处理时临时显示胶囊（不改变强制隐藏状态）
        self.reveal(animated=True)
        
        # 延迟一下再允许点击终止（避免动画期间误触）
        QTimer.singleShot(600, self._enable_abort_button)
        
        # 根据 prompt_type 设置任务类型

        if prompt_type == "image":
            ai_config.set("task_type", "image_gen")
        else:
            ai_config.set("task_type", "vision")
        
        self.ai_worker = AIWorker(base64_data, prompt)
        self.ai_worker.finished.connect(self._on_ai_finished)
        self.ai_worker.finished_image.connect(self._on_ai_image_finished)
        self.ai_worker.error.connect(self._on_ai_error)
        self.ai_worker.start()
    
    def _on_ai_finished(self, result: str):
        self._stop_processing()
        self.ai_result_text = result  # 保存结果供编辑器归档使用
        
        # 记录 AI 回复到对话历史
        self._conversation_history.append({
            "role": "assistant",
            "content": result
        })
        
        self._show_result_bubble(result)
    
    def _on_ai_image_finished(self, image_path: str):
        """处理 AI 图像生成结果"""
        self._stop_processing()
        
        # 为图片生成结果初始化对话历史（将生成的图片作为后续追问的上下文）
        import base64 as b64_mod
        pixmap = QPixmap(image_path)
        if not pixmap.isNull():
            buffer = QBuffer()
            buffer.open(QIODevice.OpenModeFlag.WriteOnly)
            pixmap.save(buffer, "PNG")
            img_base64 = b64_mod.b64encode(buffer.data().data()).decode()
            buffer.close()
            self._conversation_image = img_base64
            # 构建对话历史：一条系统提示 + 图片上下文
            self._conversation_history = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "这是 AI 生成的一张图片，请根据我的后续问题进行回答。"},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{img_base64}"
                            }
                        }
                    ]
                },
                {
                    "role": "assistant",
                    "content": "好的，我已收到这张图片。请问你有什么问题？"
                }
            ]
        
        self._show_image_bubble(image_path)
    
    def _show_image_bubble(self, image_path: str):
        """在气泡中显示图像生成结果"""
        if self.ai_bubble:
            self.ai_bubble.close()
        
        self.ai_bubble = AIResultBubble()
        self.ai_bubble.closed.connect(self._on_bubble_closed)
        self.ai_bubble.pin_image_requested.connect(self._pin_generated_image)
        self.ai_bubble.followup_requested.connect(self._on_followup_requested)
        
        capsule_pos = self.pos()
        bubble_x = capsule_pos.x()
        bubble_y = capsule_pos.y() + self.height() + 10
        
        screen = QGuiApplication.primaryScreen().geometry()
        if bubble_y + self.ai_bubble.height() > screen.height():
            bubble_y = capsule_pos.y() - self.ai_bubble.height() - 10
        if bubble_x + self.ai_bubble.width() > screen.width():
            bubble_x = screen.width() - self.ai_bubble.width() - 10
        
        self.ai_bubble.move(bubble_x, bubble_y)
        self.ai_bubble.show_image(image_path)
    
    def _pin_generated_image(self, pixmap):
        """将生成的图片贴到屏幕"""
        from screenshot.editor import EditorWindow
        
        pin_window = PinWindow(pixmap)
        
        # 居中显示
        screen = QGuiApplication.primaryScreen().geometry()
        pin_window.move(
            (screen.width() - pin_window.width()) // 2,
            (screen.height() - pin_window.height()) // 2
        )
        
        # 添加到全局列表防止被回收
        app = QApplication.instance()
        if not hasattr(app, '_pin_windows'):
            app._pin_windows = []
        app._pin_windows.append(pin_window)
        
        def on_pin_closed():
            if pin_window in app._pin_windows:
                app._pin_windows.remove(pin_window)
        pin_window.destroyed.connect(on_pin_closed)
        
        # 连接编辑请求信号
        def on_edit_requested(edit_pixmap):
            editor = EditorWindow(edit_pixmap)
            editor.show()
            if not hasattr(app, '_editor_windows'):
                app._editor_windows = []
            app._editor_windows.append(editor)
            def on_editor_closed():
                if editor in app._editor_windows:
                    app._editor_windows.remove(editor)
            editor.destroyed.connect(on_editor_closed)
        pin_window.edit_requested.connect(on_edit_requested)
        
        pin_window.show()
    
    def _on_ai_error(self, error_msg: str):
        self._stop_processing()
        self._show_result_bubble(f"❌ 错误: {error_msg}", is_error=True)
    
    def _stop_processing(self):
        self._is_processing = False
        self.breathing_animation.stop()
        self._loading_timer.stop()  # 停止三点动画
        self.btn_screenshot.setIcon(qta.icon('mdi6.crop', color='#666666'))
        self.btn_screenshot.setIconSize(QSize(18, 18))
        self.btn_screenshot.setText("")  # 紧凑模式仅图标
        self.btn_screenshot.setEnabled(True)
        
        # 断开所有 clicked 连接，重新绑定截图功能
        try:
            self.btn_screenshot.clicked.disconnect()
        except (RuntimeError, RuntimeWarning):
            pass
        self.btn_screenshot.clicked.connect(self.start_screenshot)
        self.btn_screenshot.setToolTip("截图 (快捷键)")
        
        self.container.setStyleSheet(self._build_bg_css() + """
            QPushButton#btn_screenshot {
                background-color: transparent;
                border: none;
                border-radius: 16px;
                color: #555555;
            }
QPushButton#btn_screenshot:hover { background-color: rgba(0, 0, 0, 0.08); }
QPushButton#btn_screenshot:pressed { background-color: rgba(0, 0, 0, 0.12); }
            QPushButton#btn_archive {
                background-color: transparent;
                border: none;
                border-radius: 16px;
            }
            QPushButton#btn_archive:hover { background-color: rgba(0, 0, 0, 0.08); }
            QPushButton#btn_archive:pressed { background-color: rgba(0, 0, 0, 0.12); }
        """)
    
    def _enable_abort_button(self):
        """AI 工作中，将截图按钮变为终止按钮"""
        if not self._is_processing:
            return
        self.btn_screenshot.setEnabled(True)
        self.btn_screenshot.setToolTip("点击终止 AI 处理")
        # 临时断开所有连接，绑定终止功能
        try:
            self.btn_screenshot.clicked.disconnect()
        except (RuntimeError, RuntimeWarning):
            pass
        self.btn_screenshot.clicked.connect(self._abort_ai_processing)
    
    def _abort_ai_processing(self):
        """一键终止 AI 处理"""
        # 终止主 worker
        if self.ai_worker and self.ai_worker.isRunning():
            self.ai_worker.abort()
            self.ai_worker.finished.disconnect()
            self.ai_worker.error.disconnect()
            try:
                self.ai_worker.finished_image.disconnect()
            except RuntimeError:
                pass
        # 终止追问 worker
        if hasattr(self, '_followup_worker') and self._followup_worker and self._followup_worker.isRunning():
            self._followup_worker.abort()
            self._followup_worker.finished.disconnect()
            self._followup_worker.error.disconnect()
            try:
                self._followup_worker.finished_image.disconnect()
            except RuntimeError:
                pass
        
        self._stop_processing()
        
        # 如果有打开的气泡且正在加载，恢复其输入状态
        if self.ai_bubble:
            self.ai_bubble.on_abort()
    
    def hideEvent(self, event):
        self._pop_pos_anim.stop()
        self._fade_anim.stop()
        self.setWindowOpacity(1.0)
        super().hideEvent(event)

    
    def _show_result_bubble(self, text: str, is_error: bool = False):

        if self.ai_bubble:
            self.ai_bubble.close()
        
        self.ai_bubble = AIResultBubble()
        self.ai_bubble.closed.connect(self._on_bubble_closed)
        self.ai_bubble.followup_requested.connect(self._on_followup_requested)
        
        if not is_error and hasattr(self, '_current_image_data') and self._current_image_data:
            self.ai_bubble.set_image_data(self._current_image_data)
        
        capsule_pos = self.pos()
        bubble_x = capsule_pos.x()
        bubble_y = capsule_pos.y() + self.height() + 10
        
        screen = QGuiApplication.primaryScreen().geometry()
        if bubble_y + self.ai_bubble.height() > screen.height():
            bubble_y = capsule_pos.y() - self.ai_bubble.height() - 10
        if bubble_x + self.ai_bubble.width() > screen.width():
            bubble_x = screen.width() - self.ai_bubble.width() - 10
        
        self.ai_bubble.move(bubble_x, bubble_y)
        
        if is_error:
            self.ai_bubble.show_error(text)
        else:
            self.ai_bubble.show_result(text)
    
    def _on_bubble_closed(self):
        self.ai_bubble = None
        # 对话结束，清空历史
        self._conversation_history = []
        self._conversation_image = None
    
    def _on_followup_requested(self, text: str):
        """处理追问请求 - 根据当前使用的模型类型选择不同路径"""

        # 根据当前配置的模型来判断任务类型（而不是依赖 task_type 配置）
        vision_model = ai_config.get("vision_model")
        image_gen_model = ai_config.get("image_gen_model")

        # 判断当前使用的模型类型
        current_model = ai_config.get_current_model()
        is_using_image_gen_model = (current_model == image_gen_model)

        if is_using_image_gen_model:
            # ── 图片生成追问：用新 prompt + 原图重新生成 ──
            ai_config.set("task_type", "image_gen")

            self._followup_worker = AIWorker(
                self._conversation_image,
                prompt=text
            )
            self._followup_worker.finished_image.connect(self._on_followup_image_finished)
            self._followup_worker.finished.connect(self._on_followup_finished)
            self._followup_worker.error.connect(self._on_followup_error)
            self._followup_worker.start()
        else:
            # ── 视觉分析追问：用新 prompt + 原图重新分析 ──
            ai_config.set("task_type", "vision")

            self._followup_worker = AIWorker(
                self._conversation_image,
                prompt=text
            )
            self._followup_worker.finished.connect(self._on_followup_finished)
            self._followup_worker.error.connect(self._on_followup_error)
            self._followup_worker.start()
    
    def _on_followup_finished(self, result: str):
        """追问回复完成（文本）"""
        # 记录 AI 回复到对话历史
        self._conversation_history.append({
            "role": "assistant",
            "content": result
        })
        
        self.ai_result_text = result
        
        # 通知气泡显示回复
        if self.ai_bubble:
            self.ai_bubble.append_ai_reply(result)
    
    def _on_followup_image_finished(self, image_path: str):
        """追问图片生成完成 — 在聊天气泡中显示新图片"""
        # 更新 conversation_image 为新生成的图片（后续追问基于新图）
        import base64 as b64_mod
        pixmap = QPixmap(image_path)
        if not pixmap.isNull():
            buffer = QBuffer()
            buffer.open(QIODevice.OpenModeFlag.WriteOnly)
            pixmap.save(buffer, "PNG")
            self._conversation_image = b64_mod.b64encode(buffer.data().data()).decode()
            buffer.close()
        
        if self.ai_bubble:
            self.ai_bubble.append_ai_image(image_path)
    
    def _on_followup_error(self, error_msg: str):
        """追问出错"""
        # 移除失败的用户消息
        if self._conversation_history and self._conversation_history[-1]["role"] == "user":
            self._conversation_history.pop()
        
        if self.ai_bubble:
            self.ai_bubble.show_followup_error(error_msg)

    def _setup_global_hotkey(self):
        """设置全局热键（使用底层钩子，阻止按键传递给其他应用）"""
        self._hotkey_hook = None
        self._hotkey_keys = set()
        self._pressed_keys = set()
        self._register_hotkey()
    
    def _register_hotkey(self):
        try:
            import ctypes
            from ctypes import wintypes
            import threading
            
            # 停止旧的钩子
            if hasattr(self, '_hotkey_hook') and self._hotkey_hook:
                self._unhook_hotkey()
            
            hotkey_str = hotkey_manager.get('screenshot')
            if not hotkey_str:
                return
            
            # 解析热键字符串为虚拟键码集合
            self._hotkey_keys = self._parse_hotkey_to_vk(hotkey_str)
            if not self._hotkey_keys:
                return
            
            self._pressed_keys = set()
            
            # Windows 底层键盘钩子
            user32 = ctypes.windll.user32
            
            WH_KEYBOARD_LL = 13
            WM_KEYDOWN = 0x0100
            WM_KEYUP = 0x0101
            WM_SYSKEYDOWN = 0x0104
            WM_SYSKEYUP = 0x0105
            
            class KBDLLHOOKSTRUCT(ctypes.Structure):
                _fields_ = [
                    ("vkCode", wintypes.DWORD),
                    ("scanCode", wintypes.DWORD),
                    ("flags", wintypes.DWORD),
                    ("time", wintypes.DWORD),
                    ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))
                ]
            
            # SetWindowsHookExW expects stdcall callback (WinFunctionType), not cdecl.
            HOOKPROC = ctypes.WINFUNCTYPE(
                ctypes.c_long,
                ctypes.c_int,
                wintypes.WPARAM,
                ctypes.POINTER(KBDLLHOOKSTRUCT),
            )

            user32.SetWindowsHookExW.argtypes = [
                ctypes.c_int,
                HOOKPROC,
                wintypes.HINSTANCE,
                wintypes.DWORD,
            ]
            user32.SetWindowsHookExW.restype = wintypes.HHOOK
            user32.CallNextHookEx.argtypes = [
                wintypes.HHOOK,
                ctypes.c_int,
                wintypes.WPARAM,
                wintypes.LPARAM,
            ]
            user32.CallNextHookEx.restype = wintypes.LPARAM
            
            def keyboard_hook_proc(nCode, wParam, lParam):
                if nCode >= 0:
                    vk = lParam.contents.vkCode
                    
                    if wParam in (WM_KEYDOWN, WM_SYSKEYDOWN):
                        self._pressed_keys.add(vk)
                        
                        # 检查是否所有热键都被按下
                        if self._hotkey_keys and self._hotkey_keys.issubset(self._pressed_keys):
                            # 触发截图（通过信号，避免跨线程问题）
                            self.hotkey_triggered.emit()
                            # 返回 1 阻止按键传递给其他应用
                            return 1
                    
                    elif wParam in (WM_KEYUP, WM_SYSKEYUP):
                        self._pressed_keys.discard(vk)
                
                lparam_val = ctypes.cast(lParam, ctypes.c_void_p).value or 0
                return user32.CallNextHookEx(None, nCode, wParam, wintypes.LPARAM(lparam_val))
            
            # 保持回调函数引用，防止被垃圾回收
            self._hook_proc = HOOKPROC(keyboard_hook_proc)
            
            def run_hook():
                self._hotkey_hook = user32.SetWindowsHookExW(
                    WH_KEYBOARD_LL,
                    self._hook_proc,
                    None,
                    0
                )
                
                if self._hotkey_hook:
                    msg = wintypes.MSG()
                    while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
                        user32.TranslateMessage(ctypes.byref(msg))
                        user32.DispatchMessageW(ctypes.byref(msg))
            
            # 在后台线程运行消息循环
            self._hook_thread = threading.Thread(target=run_hook, daemon=True)
            self._hook_thread.start()
            
        except Exception:
            # 回退到 pynput 方式
            self._setup_fallback_hotkey()
    
    def _parse_hotkey_to_vk(self, hotkey_str: str) -> set:
        """解析热键字符串为虚拟键码集合"""
        # 虚拟键码映射
        vk_map = {
            'ctrl': 0x11,  # VK_CONTROL
            'alt': 0x12,   # VK_MENU
            'shift': 0x10, # VK_SHIFT
            'win': 0x5B,   # VK_LWIN
            'f1': 0x70, 'f2': 0x71, 'f3': 0x72, 'f4': 0x73,
            'f5': 0x74, 'f6': 0x75, 'f7': 0x76, 'f8': 0x77,
            'f9': 0x78, 'f10': 0x79, 'f11': 0x7A, 'f12': 0x7B,
            'a': 0x41, 'b': 0x42, 'c': 0x43, 'd': 0x44, 'e': 0x45,
            'f': 0x46, 'g': 0x47, 'h': 0x48, 'i': 0x49, 'j': 0x4A,
            'k': 0x4B, 'l': 0x4C, 'm': 0x4D, 'n': 0x4E, 'o': 0x4F,
            'p': 0x50, 'q': 0x51, 'r': 0x52, 's': 0x53, 't': 0x54,
            'u': 0x55, 'v': 0x56, 'w': 0x57, 'x': 0x58, 'y': 0x59, 'z': 0x5A,
            '0': 0x30, '1': 0x31, '2': 0x32, '3': 0x33, '4': 0x34,
            '5': 0x35, '6': 0x36, '7': 0x37, '8': 0x38, '9': 0x39,
            'space': 0x20, 'enter': 0x0D, 'tab': 0x09, 'esc': 0x1B,
            'backspace': 0x08, 'delete': 0x2E, 'insert': 0x2D,
            'home': 0x24, 'end': 0x23, 'pageup': 0x21, 'pagedown': 0x22,
            'up': 0x26, 'down': 0x28, 'left': 0x25, 'right': 0x27,
            'printscreen': 0x2C, 'prtsc': 0x2C,
        }
        
        keys = set()
        parts = hotkey_str.lower().replace(' ', '').split('+')
        
        for part in parts:
            if part in vk_map:
                keys.add(vk_map[part])
            elif len(part) == 1 and part.isalnum():
                keys.add(ord(part.upper()))
        
        return keys
    
    def _unhook_hotkey(self):
        """卸载键盘钩子"""
        if hasattr(self, '_hotkey_hook') and self._hotkey_hook:
            try:
                import ctypes
                ctypes.windll.user32.UnhookWindowsHookEx(self._hotkey_hook)
            except:
                pass
            self._hotkey_hook = None

    def _unhook_clipboard_mouse_hook(self):
        """卸载剪贴板浮窗鼠标钩子"""
        try:
            import ctypes
            from ctypes import wintypes
            if hasattr(self, '_clipboard_mouse_hook') and self._clipboard_mouse_hook:
                ctypes.windll.user32.UnhookWindowsHookEx(self._clipboard_mouse_hook)
                self._clipboard_mouse_hook = None
            if hasattr(self, '_clipboard_mouse_thread_id') and self._clipboard_mouse_thread_id:
                WM_QUIT = 0x0012
                ctypes.windll.user32.PostThreadMessageW(
                    wintypes.DWORD(self._clipboard_mouse_thread_id), WM_QUIT, 0, 0
                )
                self._clipboard_mouse_thread_id = 0
        except Exception:
            pass
    
    def _setup_fallback_hotkey(self):
        """回退到 pynput 方式（不阻止按键传递）"""
        try:
            from pynput import keyboard
            
            hotkey_str = hotkey_manager.get('screenshot')
            if not hotkey_str:
                return
            
            hotkey_pynput = convert_hotkey_format(hotkey_str)
            if not hotkey_pynput:
                return
            
            def on_activate():
                self.hotkey_triggered.emit()
            
            self.hotkey_listener = keyboard.GlobalHotKeys({
                hotkey_pynput: on_activate
            })
            self.hotkey_listener.start()
        except Exception:
            pass
    
    def _setup_clipboard_float_hotkey(self):
        """注册剪贴板悬浮面板快捷键（鼠标侧键）"""
        # 停止旧的监听器
        try:
            if hasattr(self, '_mouse_listener') and self._mouse_listener:
                self._mouse_listener.stop()
                self._mouse_listener = None
        except Exception:
            pass

        # 停止旧的底层鼠标钩子
        self._unhook_clipboard_mouse_hook()
        
        try:
            if hasattr(self, '_clipboard_float_listener') and self._clipboard_float_listener:
                self._clipboard_float_listener.stop()
                self._clipboard_float_listener = None
        except Exception:
            pass
        
        try:
            hotkey_str = hotkey_manager.get('clipboard_float')
            
            if not hotkey_str:
                return
            
            # 非鼠标侧键：走键盘监听
            hk_lower = hotkey_str.lower()
            if hk_lower not in ('mousex1', 'mousex2'):
                # 不是鼠标按钮，尝试使用键盘热键
                from pynput import keyboard
                hotkey_pynput = convert_hotkey_format(hotkey_str)
                if hotkey_pynput:
                    def on_activate():
                        self.clipboard_float_requested.emit()
                    
                    self._clipboard_float_listener = keyboard.GlobalHotKeys({
                        hotkey_pynput: on_activate
                    })
                    self._clipboard_float_listener.start()
                return

            # 鼠标侧键：使用底层钩子拦截并吞掉，避免触发浏览器后退/前进
            import ctypes
            from ctypes import wintypes
            import threading

            user32 = ctypes.windll.user32
            WH_MOUSE_LL = 14
            WM_XBUTTONDOWN = 0x020B
            WM_XBUTTONUP = 0x020C
            XBUTTON1 = 0x0001
            XBUTTON2 = 0x0002
            target_xbutton = XBUTTON1 if hk_lower == 'mousex1' else XBUTTON2

            class MSLLHOOKSTRUCT(ctypes.Structure):
                _fields_ = [
                    ("pt_x", ctypes.c_long),
                    ("pt_y", ctypes.c_long),
                    ("mouseData", wintypes.DWORD),
                    ("flags", wintypes.DWORD),
                    ("time", wintypes.DWORD),
                    ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))
                ]

            MOUSEHOOKPROC = ctypes.WINFUNCTYPE(
                ctypes.c_long,
                ctypes.c_int,
                wintypes.WPARAM,
                ctypes.POINTER(MSLLHOOKSTRUCT),
            )

            user32.SetWindowsHookExW.argtypes = [
                ctypes.c_int,
                MOUSEHOOKPROC,
                wintypes.HINSTANCE,
                wintypes.DWORD,
            ]
            user32.SetWindowsHookExW.restype = wintypes.HHOOK
            user32.CallNextHookEx.argtypes = [
                wintypes.HHOOK,
                ctypes.c_int,
                wintypes.WPARAM,
                wintypes.LPARAM,
            ]
            user32.CallNextHookEx.restype = wintypes.LPARAM

            def mouse_hook_proc(nCode, wParam, lParam):
                if nCode >= 0 and wParam in (WM_XBUTTONDOWN, WM_XBUTTONUP):
                    md = int(lParam.contents.mouseData)
                    xbtn = (md >> 16) & 0xFFFF
                    if xbtn == target_xbutton:
                        if wParam == WM_XBUTTONDOWN:
                            self.clipboard_float_requested.emit()
                        # 吞掉侧键默认行为（浏览器前进/后退）
                        return 1
                lparam_val = ctypes.cast(lParam, ctypes.c_void_p).value or 0
                return user32.CallNextHookEx(None, nCode, wParam, wintypes.LPARAM(lparam_val))

            self._clipboard_mouse_proc = MOUSEHOOKPROC(mouse_hook_proc)

            def run_mouse_hook():
                self._clipboard_mouse_thread_id = ctypes.windll.kernel32.GetCurrentThreadId()
                self._clipboard_mouse_hook = user32.SetWindowsHookExW(
                    WH_MOUSE_LL,
                    self._clipboard_mouse_proc,
                    None,
                    0
                )
                if self._clipboard_mouse_hook:
                    msg = wintypes.MSG()
                    while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
                        user32.TranslateMessage(ctypes.byref(msg))
                        user32.DispatchMessageW(ctypes.byref(msg))

            self._clipboard_mouse_thread = threading.Thread(target=run_mouse_hook, daemon=True)
            self._clipboard_mouse_thread.start()
        except Exception:
            pass
    
    def _on_hotkey_changed(self):
        self._register_hotkey()
        self._setup_clipboard_float_hotkey()

    def init_ui(self):
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAcceptDrops(True)  # 接受外部拖入文件/图片

        self.container = QWidget(self)
        self.container.setObjectName("container")
        self.container.setAcceptDrops(True)  # container 也接受拖放，防止事件被子控件吞掉
        self.container.setFixedSize(116, 40)  # 圆角矩形浮窗，减小宽度
        
        layout = QHBoxLayout(self.container)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # 截图按钮（仅图标，悬停显示文字提示）
        self.btn_screenshot = QPushButton()
        self.btn_screenshot.setIcon(qta.icon('mdi6.crop', color='#666666'))
        self.btn_screenshot.setIconSize(QSize(18, 18))
        self.btn_screenshot.setObjectName("btn_screenshot")
        self.btn_screenshot.setFixedSize(42, 32)
        self.btn_screenshot.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_screenshot.setToolTip("截图 (快捷键)")
        self.btn_screenshot.clicked.connect(self.start_screenshot)
        layout.addWidget(self.btn_screenshot)
        
        # 拖动手柄（中间）
        self.drag_handle = QLabel()
        self.drag_handle.setObjectName("drag_handle")
        self.drag_handle.setFixedSize(20, 32)
        self.drag_handle.setCursor(Qt.CursorShape.SizeAllCursor)
        self.drag_handle.setToolTip("拖动移动")
        self.drag_handle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # 使用 qtawesome 图标作为拖动手柄
        drag_icon = qta.icon('mdi6.drag-vertical', color='#888888')
        self.drag_handle.setPixmap(drag_icon.pixmap(QSize(20, 20)))
        layout.addWidget(self.drag_handle)

        # 归档按钮
        self.btn_archive = QPushButton()
        self.btn_archive.setIcon(qta.icon('mdi6.archive', color='#666666'))
        self.btn_archive.setIconSize(QSize(16, 16))
        self.btn_archive.setObjectName("btn_archive")
        self.btn_archive.setFixedSize(42, 32)
        self.btn_archive.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_archive.setToolTip("归档记录")
        self.btn_archive.clicked.connect(self._open_archive)
        layout.addWidget(self.btn_archive)
        
        # 只为拖动手柄安装事件过滤器
        self.drag_handle.installEventFilter(self)
        
        # 让子控件也接受拖放，并安装事件过滤器转发给父窗口
        for child in (self.btn_screenshot, self.btn_archive, self.drag_handle, self.container):
            child.setAcceptDrops(True)
            child.installEventFilter(self)

        self._normal_style = self._build_bg_css() + """
            #drag_handle {
                background-color: transparent;
            }
            QPushButton#btn_screenshot {
                background-color: transparent;
                border: none;
                border-radius: 8px;
                color: #555555;
            }
QPushButton#btn_screenshot:hover { background-color: rgba(0, 0, 0, 0.08); }
QPushButton#btn_screenshot:pressed { background-color: rgba(0, 0, 0, 0.12); }
            QPushButton#btn_archive {
                background-color: transparent;
                border: none;
                border-radius: 8px;
            }
            QPushButton#btn_archive:hover { background-color: rgba(0, 0, 0, 0.08); }
            QPushButton#btn_archive:pressed { background-color: rgba(0, 0, 0, 0.12); }
        """
        
        self._dragging_style = self._build_bg_css(border="1px solid rgba(100, 150, 255, 0.6)") + """
            #drag_handle {
                background-color: transparent;
            }
            QPushButton#btn_screenshot {
                background-color: transparent;
                border: none;
                border-radius: 8px;
                color: #555555;
            }
            QPushButton#btn_archive {
                background-color: transparent;
                border: none;
                border-radius: 8px;
            }
        """
        
        self.container.setStyleSheet(self._normal_style)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(15)
        shadow.setColor(QColor(0, 0, 0, 40))
        shadow.setOffset(0, 3)
        self.container.setGraphicsEffect(shadow)

        self.setFixedSize(136, 60)  # 外框尺寸（包含阴影空间）
        self.container.move(10, 10)

        screen = QGuiApplication.primaryScreen().geometry()
        self.move(screen.width() - self.width() - 30, screen.height() // 2 - self.height() // 2)

    def start_screenshot(self):
        # 检查是否已有截图窗口正在运行
        if hasattr(self, 'overlay') and self.overlay is not None:
            try:
                if self.overlay.isVisible():
                    return  # 截图窗口已存在，不重复创建
            except RuntimeError:
                # 窗口已被销毁
                self.overlay = None
        
        # 关闭所有活跃的弹出窗口（ComboBox下拉层、菜单等），
        # 避免弹出层抢占事件循环导致截图流程卡住
        active_popup = QApplication.activePopupWidget()
        while active_popup is not None:
            active_popup.close()
            active_popup = QApplication.activePopupWidget()
        
        self._saved_pos = self.pos()
        self.hide()
        
        # 处理事件，确保窗口完全隐藏后再截图
        QApplication.processEvents()
        
        screens = QGuiApplication.screens()
        if len(screens) > 1:
            self.screen_selector = ScreenSelector(self)
            self.screen_selector.screen_selected.connect(self._on_screen_selected)
        else:
            # 单屏直接启动截图，processEvents 已确保窗口隐藏
            QTimer.singleShot(0, lambda: self._start_screenshot_on_screen(None))
    
    def _on_screen_selected(self, data):
        if data is None or (isinstance(data, tuple) and data[0] is None):
            self._restore_position()
            return
        
        if isinstance(data, tuple):
            if len(data) >= 3:
                screen, start_pos, prefetched = data[0], data[1], data[2]
            else:
                screen, start_pos = data[0], data[1]
                prefetched = None
        else:
            screen, start_pos, prefetched = data, None, None
            
        # 立即启动截图，屏幕选择器已关闭（默认参数绑定，避免闭包滞后）
        QTimer.singleShot(
            0,
            lambda s=screen, sp=start_pos, pf=prefetched: self._start_screenshot_on_screen(s, sp, pf),
        )
    
    def _start_screenshot_on_screen(self, screen, start_pos=None, prefetched_pixmap=None):
        # 再次检查是否已有截图窗口
        if hasattr(self, 'overlay') and self.overlay is not None:
            try:
                if self.overlay.isVisible():
                    return
            except RuntimeError:
                self.overlay = None
        
        try:
            self.overlay = ScreenshotOverlay(screen, start_pos, prefetched_pixmap)
            self.overlay.destroyed.connect(self._on_overlay_closed)
        except Exception as e:
            print(f"启动截图失败: {e}")
            self.overlay = None
            self._restore_position()
    
    def _on_overlay_closed(self):
        app = QApplication.instance()
        if hasattr(app, '_editor_windows') and app._editor_windows:
            self.overlay = None
            return
        
        # 检查是否需要自动分析剪贴板
        if hasattr(self, '_pending_clipboard_analyze') and self._pending_clipboard_analyze:
            self._pending_clipboard_analyze = False
            # 延迟一点确保剪贴板已更新
            QTimer.singleShot(200, self._ai_analyze_clipboard)
            return
        
        self._restore_position()
    
    def _restore_position(self):
        self.overlay = None
        if self._saved_pos is not None:
            self.move(self._saved_pos)
        # 只有非强制隐藏模式才自动显示
        if not self._force_hidden:
            self.reveal(animated=True)
    
    def _open_archive(self):

        self.archive_window = WorkbenchWindow()
        self.archive_window.show()

    def _open_settings(self):
        # 如果已有设置窗口，激活它
        if hasattr(self, '_settings_dialog') and self._settings_dialog is not None:
            try:
                if self._settings_dialog.isVisible():
                    self._settings_dialog.raise_()
                    self._settings_dialog.activateWindow()
                    return
            except RuntimeError:
                self._settings_dialog = None
        
        self._settings_dialog = SettingsDialog(self)
        self._settings_dialog.hotkey_changed.connect(self._on_hotkey_changed)
        self._settings_dialog._appearance_preview_callback = self._refresh_appearance
        self._settings_dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self._settings_dialog.destroyed.connect(lambda: setattr(self, '_settings_dialog', None))
        self._settings_dialog.show()
    
    def _refresh_appearance(self):
        """从 appearance_config 刷新浮窗样式"""
        self._normal_style = self._build_bg_css() + """
            #drag_handle { background-color: transparent; }
            QPushButton#btn_screenshot {
                background-color: transparent; border: none; border-radius: 8px; color: #555555;
            }
            QPushButton#btn_screenshot:hover { background-color: rgba(0, 0, 0, 0.08); }
            QPushButton#btn_screenshot:pressed { background-color: rgba(0, 0, 0, 0.12); }
            QPushButton#btn_archive {
                background-color: transparent; border: none; border-radius: 8px;
            }
            QPushButton#btn_archive:hover { background-color: rgba(0, 0, 0, 0.08); }
            QPushButton#btn_archive:pressed { background-color: rgba(0, 0, 0, 0.12); }
        """
        self._dragging_style = self._build_bg_css(border="1px solid rgba(100, 150, 255, 0.6)") + """
            #drag_handle { background-color: transparent; }
            QPushButton#btn_screenshot {
                background-color: transparent; border: none; border-radius: 8px; color: #555555;
            }
            QPushButton#btn_archive {
                background-color: transparent; border: none; border-radius: 8px;
            }
        """
        if not self._is_processing:
            self.container.setStyleSheet(self._normal_style)
    
    def _open_prompt_settings(self):
        # 统一入口：在设置面板内管理 Prompt
        if hasattr(self, '_settings_dialog') and self._settings_dialog is not None:
            try:
                if self._settings_dialog.isVisible():
                    self._settings_dialog.show_tab('prompt')
                    self._settings_dialog.raise_()
                    self._settings_dialog.activateWindow()
                    return
            except RuntimeError:
                self._settings_dialog = None

        self._settings_dialog = SettingsDialog(self)
        self._settings_dialog.hotkey_changed.connect(self._on_hotkey_changed)
        self._settings_dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self._settings_dialog.destroyed.connect(lambda: setattr(self, '_settings_dialog', None))
        self._settings_dialog.show_tab('prompt')
        self._settings_dialog.show()
    
    def _setup_tray_icon(self):
        """设置系统托盘图标"""
        # 创建托盘图标
        self.tray_icon = QSystemTrayIcon(self)
        
        app_icon = get_app_icon()
        self.tray_icon.setIcon(app_icon)

        self.tray_icon.setToolTip("Artco - AI 截图工具")
        
        # 创建托盘菜单
        self.tray_menu = QMenu()
        self.tray_menu.setStyleSheet(MENU_STYLE)
        
        self.show_action = self.tray_menu.addAction(qta.icon('mdi6.eye-outline', color='#555'), "  显示胶囊")
        self.show_action.triggered.connect(self._toggle_capsule_visibility)
        
        screenshot_action = self.tray_menu.addAction(qta.icon('mdi6.crop', color='#555'), "  截图")
        screenshot_action.triggered.connect(self.start_screenshot)
        
        self.tray_menu.addSeparator()
        
        # AI 功能子菜单
        ai_menu = self.tray_menu.addMenu(qta.icon('mdi6.auto-fix', color='#555'), "  AI 分析")
        ai_menu.setStyleSheet(self.tray_menu.styleSheet())
        
        ai_clipboard_action = ai_menu.addAction(qta.icon('mdi6.clipboard-text-outline', color='#555'), "  分析剪贴板图片")
        ai_clipboard_action.triggered.connect(self._ai_analyze_clipboard)
        
        ai_screenshot_action = ai_menu.addAction(qta.icon('mdi6.crop', color='#555'), "  截图并分析")
        ai_screenshot_action.triggered.connect(self._ai_screenshot_analyze)
        
        self.tray_menu.addSeparator()
        
        archive_action = self.tray_menu.addAction(qta.icon('mdi6.archive', color='#555'), "  归档记录")
        archive_action.triggered.connect(self._open_archive)
        
        settings_action = self.tray_menu.addAction(qta.icon('mdi6.cog-outline', color='#555'), "  设置")
        settings_action.triggered.connect(self._open_settings)
        
        self.tray_menu.addSeparator()
        
        update_action = self.tray_menu.addAction(qta.icon('mdi6.cloud-download-outline', color='#555'), "  检查更新")
        update_action.triggered.connect(self._check_update_manual)
        
        self.tray_menu.addSeparator()
        
        quit_action = self.tray_menu.addAction(qta.icon('mdi6.power', color='#e53935'), "  退出")
        quit_action.triggered.connect(QApplication.quit)
        
        self.tray_icon.setContextMenu(self.tray_menu)
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.show()
        
        # 启动后延迟 8 秒静默检查更新
        QTimer.singleShot(8000, self._check_update_silent)
    
    def _toggle_capsule_visibility(self):
        """切换胶囊显示/强制隐藏状态"""
        if self._force_hidden:
            # 取消强制隐藏，显示胶囊
            self._force_hidden = False
            self.show_action.setText("  隐藏胶囊")
            self.show_action.setIcon(qta.icon('mdi6.eye-off-outline', color='#555'))
            self.reveal(animated=True)
            self.activateWindow()

        else:
            # 强制隐藏
            self._force_hidden = True
            self.show_action.setText("  显示胶囊")
            self.show_action.setIcon(qta.icon('mdi6.eye-outline', color='#555'))
            self.hide()
    
    def _show_clipboard_float(self):
        """显示剪贴板悬浮面板"""
        # 懒加载悬浮面板
        if not hasattr(self, '_clipboard_float_panel') or not self._clipboard_float_panel:
            self._clipboard_float_panel = ClipboardFloatPanel()
        
        self._clipboard_float_panel.show_at_cursor()
    
    def _ai_analyze_clipboard(self):
        """分析剪贴板中的图片"""
        clipboard = QGuiApplication.clipboard()
        pixmap = clipboard.pixmap()
        
        if pixmap.isNull():
            # 尝试从图片数据获取
            mime_data = clipboard.mimeData()
            if mime_data.hasImage():
                image = mime_data.imageData()
                if image:
                    pixmap = QPixmap.fromImage(image)
        
        if pixmap.isNull():
            self.tray_icon.showMessage(
                "Artco",
                "剪贴板中没有图片",
                QSystemTrayIcon.MessageIcon.Warning,
                2000
            )
            return
        
        # 转换为 base64
        from PySide6.QtCore import QBuffer, QIODevice
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        pixmap.save(buffer, "PNG")
        base64_data = base64.b64encode(buffer.data().data()).decode()
        buffer.close()
        
        # 显示胶囊并开始处理
        self._force_hidden = False
        self.show_action.setText("  隐藏胶囊")
        self.show_action.setIcon(qta.icon('mdi6.eye-off-outline', color='#555'))
        self.start_ai_processing(base64_data)
    
    def _ai_screenshot_analyze(self):
        """截图并直接进行 AI 分析 - 截图后自动分析剪贴板"""
        # 先截图，完成后会自动复制到剪贴板
        # 然后延迟调用分析剪贴板
        self._pending_clipboard_analyze = True
        self.start_screenshot()
    
    def _show_window(self):
        """显示主窗口"""
        self._force_hidden = False
        self.show_action.setText("  隐藏胶囊")
        self.show_action.setIcon(qta.icon('mdi6.eye-off-outline', color='#555'))
        self.reveal(animated=True)
        self.activateWindow()

    # ══════════════════════════════════════════════════════
    #  自动更新
    # ══════════════════════════════════════════════════════

    def _check_update_silent(self):
        """启动后静默检查更新（非侵入式托盘通知）"""
        if not updater.should_check_silently():
            return
        threading.Thread(target=self._do_silent_check, daemon=True).start()

    def _do_silent_check(self):
        """后台线程：静默检查"""
        has_update, info = updater.check_for_update()
        updater._save_check_time()
        if has_update:
            version = info.get("version", "?")
            changelog = info.get("changelog", "")
            # 通过信号在主线程显示托盘通知
            QTimer.singleShot(0, lambda: self._show_update_notification(version, changelog, info))

    def _show_update_notification(self, version: str, changelog: str, info: dict):
        """在系统托盘显示更新通知（非侵入式）"""
        title = f"Artco {version} 可用"
        msg = changelog[:200] if changelog else "点击检查更新"
        self.tray_icon.showMessage(
            title, msg,
            QSystemTrayIcon.MessageIcon.Information,
            5000
        )

    def _check_update_manual(self):
        """手动检查更新（从托盘菜单或设置页触发）"""
        # 显示检查中提示
        self.tray_icon.showMessage(
            "Artco", "正在检查更新…",
            QSystemTrayIcon.MessageIcon.NoIcon, 2000
        )
        # 兜底定时器：15 秒后强制提示超时
        self._tray_update_timer = QTimer(self)
        self._tray_update_timer.setSingleShot(True)
        self._tray_update_timer.timeout.connect(self.update_check_timeout.emit)
        self._tray_update_timer.start(15000)

        threading.Thread(target=self._do_manual_check, daemon=True).start()

    def _do_manual_check(self):
        """后台线程：手动检查"""
        has_update, info = updater.check_for_update()
        updater._save_check_time()
        self.update_check_result.emit(has_update, info)

    def _on_tray_update_result(self, has_update: bool, info):
        """托盘检查更新结果回调（主线程）"""
        if hasattr(self, '_tray_update_timer') and self._tray_update_timer:
            self._tray_update_timer.stop()
            self._tray_update_timer = None
        if has_update:
            version = info.get("version", "?")
            changelog = info.get("changelog", "")
            self._show_update_dialog(version, changelog, info)
        else:
            self.tray_icon.showMessage(
                "Artco", "已是最新版本 ✓",
                QSystemTrayIcon.MessageIcon.Information, 2000
            )

    def _on_tray_update_timeout(self):
        """托盘检查更新超时回调（主线程）"""
        if hasattr(self, '_tray_update_timer') and self._tray_update_timer:
            self._tray_update_timer = None
        self.tray_icon.showMessage(
            "Artco", "检查更新超时，请稍后重试",
            QSystemTrayIcon.MessageIcon.Warning, 3000
        )

    def _show_update_dialog(self, version: str, changelog: str, info: dict):
        """显示更新对话框，让用户选择立即更新/稍后/跳过"""
        from PySide6.QtWidgets import QMessageBox, QProgressDialog
        from PySide6.QtCore import QThread, Signal

        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setWindowTitle(f"发现新版本 v{version}")
        msg.setText(f"<h3>Artco v{version} 已发布</h3>")
        changes = changelog if changelog else "暂无更新说明"
        msg.setInformativeText(f"<b>更新内容：</b><br>{changes}<br><br>当前版本：v{APP_VERSION}")
        btn_update = msg.addButton("立即更新", QMessageBox.ButtonRole.AcceptRole)
        btn_later = msg.addButton("稍后提醒", QMessageBox.ButtonRole.RejectRole)
        btn_skip = msg.addButton("跳过此版本", QMessageBox.ButtonRole.DestructiveRole)
        msg.setDefaultButton(btn_update)
        msg.exec()

        if msg.clickedButton() == btn_update:
            self._start_download_update(info)
        elif msg.clickedButton() == btn_skip:
            updater.skip_version(info.get("version", ""))

    def _start_download_update(self, info: dict):
        """开始下载更新，显示进度条"""
        from PySide6.QtWidgets import QProgressDialog

        self._update_progress = QProgressDialog("正在下载更新…", "取消", 0, 100, self)
        self._update_progress.setWindowTitle("Artco 更新")
        self._update_progress.setMinimumWidth(400)
        self._update_progress.setWindowModality(Qt.WindowModality.ApplicationModal)
        self._update_progress.setAutoClose(False)
        self._update_progress.canceled.connect(self._cancel_update_download)
        self._update_info = info
        self._update_cancelled = False
        self._update_progress.show()

        threading.Thread(target=self._download_thread, daemon=True).start()

    def _download_thread(self):
        """后台下载线程"""
        try:
            new_path = updater.download_update(
                self._update_info,
                progress_callback=self._on_download_progress
            )
            if self._update_cancelled:
                return
            QTimer.singleShot(0, lambda: self._on_download_complete(new_path))
        except Exception as e:
            QTimer.singleShot(0, lambda: self._on_download_error(str(e)))

    def _on_download_progress(self, ratio: float):
        """下载进度回调（在下载线程中调用，需通过 QTimer 切回主线程）"""
        if ratio < 0:
            # 不确定模式：content-length 缺失，显示已下载 MB
            downloaded_mb = -ratio / (1024 * 1024)
            QTimer.singleShot(0, lambda: self._update_progress.setLabelText(f"正在下载… 已下载 {downloaded_mb:.1f} MB"))
        else:
            percent = int(ratio * 100)
            QTimer.singleShot(0, lambda: self._update_progress.setValue(percent))

    def _on_download_complete(self, new_path: str):
        """下载完成，启动 Updater 替换"""
        self._update_progress.setValue(100)
        self._update_progress.setLabelText("下载完成，正在应用更新…")
        QMessageBox.information(self, "更新", "下载完成，程序将重启以完成更新。")
        updater.apply_update(new_path)

    def _on_download_error(self, error_msg: str):
        """下载失败"""
        if hasattr(self, '_update_progress'):
            self._update_progress.close()
        QMessageBox.warning(self, "更新失败", f"下载更新失败：\n{error_msg}")

    def _cancel_update_download(self):
        """用户取消下载"""
        self._update_cancelled = True

    
    def _on_tray_activated(self, reason):
        """托盘图标被点击"""
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            # 单击托盘图标，切换窗口显示状态
            self._toggle_capsule_visibility()
        elif reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            # 双击托盘图标，开始截图
            self.start_screenshot()
    
    # ---- 拖放图片到胶囊 → 自动归档 ----

    _IMAGE_EXTS = ('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp', '.tiff', '.tif')

    def _is_image_url(self, url):
        path = url.toLocalFile().lower()
        return path.endswith(self._IMAGE_EXTS)

    def dragEnterEvent(self, event):
        md = event.mimeData()
        accepted = False
        if md.hasUrls():
            for url in md.urls():
                if self._is_image_url(url):
                    accepted = True
                    break
        if not accepted and md.hasImage():
            accepted = True
        if accepted:
            event.acceptProposedAction()
            self._set_drop_highlight(True)
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        """必须接受 DragMove 否则 Windows 上 drop 不会触发"""
        event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self._set_drop_highlight(False)

    def dropEvent(self, event):
        self._set_drop_highlight(False)
        md = event.mimeData()
        imported = 0

        # 优先处理文件 URL
        if md.hasUrls():
            for url in md.urls():
                path = url.toLocalFile()
                if not path:
                    continue
                ext = os.path.splitext(path)[1].lower()
                if ext not in self._IMAGE_EXTS:
                    continue
                try:
                    with open(path, 'rb') as f:
                        raw = f.read()
                    add_record(raw, "", ext=ext)
                    imported += 1
                except Exception as e:
                    print(f"归档失败: {path} - {e}")

        # 如果没有文件，尝试 mimeData 中的图片（如从浏览器拖图）
        if imported == 0 and md.hasImage():
            pixmap = QPixmap.fromImage(md.imageData())
            if not pixmap.isNull():
                img_bytes = self._pixmap_to_jpeg_bytes(pixmap)
                if img_bytes:
                    add_record(img_bytes, "", ext=".jpg")
                    imported += 1

        if imported > 0:
            event.acceptProposedAction()
            self._show_drop_feedback(imported)
        else:
            event.ignore()

    @staticmethod
    def _pixmap_to_jpeg_bytes(pixmap: QPixmap) -> bytes | None:
        """将 QPixmap 转为 JPEG bytes（仅用于浏览器拖图等无文件源的场景）"""
        from PySide6.QtCore import QBuffer, QIODevice
        buf = QBuffer()
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        pixmap.save(buf, "JPEG", 85)
        return buf.data().data()

    def _set_drop_highlight(self, active: bool):
        """拖入时高亮胶囊边框"""
        if active:
            self.container.setStyleSheet("""
                #container {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                        stop:0 rgba(230, 243, 255, 0.98),
                        stop:1 rgba(200, 225, 255, 0.95));
                    border-radius: 20px;
                    border: 2px solid #007aff;
                }
            """)
        else:
            self.container.setStyleSheet(self._normal_style)

    def _show_drop_feedback(self, count: int):
        """归档成功后短暂闪烁反馈"""
        self.container.setStyleSheet("""
            #container {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(220, 245, 220, 0.98),
                    stop:1 rgba(200, 240, 210, 0.95));
                border-radius: 20px;
                border: 2px solid #34c759;
            }
        """)
        QTimer.singleShot(600, lambda: self.container.setStyleSheet(self._normal_style))

    def eventFilter(self, obj, event):
        """事件过滤器 - 拖放转发 + 拖动手柄的鼠标事件处理"""
        from PySide6.QtCore import QEvent
        
        # 将子控件的 drag 事件转发给 CapsuleWidget 自身处理
        if obj is not self and event.type() in (
            QEvent.Type.DragEnter, QEvent.Type.DragMove,
            QEvent.Type.DragLeave, QEvent.Type.Drop
        ):
            if event.type() == QEvent.Type.DragEnter:
                self.dragEnterEvent(event)
                return event.isAccepted()
            elif event.type() == QEvent.Type.DragLeave:
                self.dragLeaveEvent(event)
                return True
            elif event.type() == QEvent.Type.Drop:
                self.dropEvent(event)
                return event.isAccepted()
            elif event.type() == QEvent.Type.DragMove:
                self.dragMoveEvent(event)
                return True
        
        # 只处理拖动手柄的鼠标事件
        if obj != self.drag_handle:
            return super().eventFilter(obj, event)
        
        if event.type() == QEvent.Type.MouseButtonDblClick and event.button() == Qt.MouseButton.LeftButton:
            # 双击打开归档界面
            self._open_archive()
            return True
        
        if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            # 记录拖动起始状态
            self._drag_offset = self.mapFromGlobal(event.globalPosition().toPoint())
            self._drag_start_pos = event.globalPosition().toPoint()
            self._is_dragging = False
            return True
        
        elif event.type() == QEvent.Type.MouseMove and hasattr(self, '_drag_offset') and self._drag_offset is not None:
            # 检测是否开始拖动（移动超过 3 像素）
            if not self._is_dragging:
                delta = event.globalPosition().toPoint() - self._drag_start_pos
                if abs(delta.x()) > 3 or abs(delta.y()) > 3:
                    self._is_dragging = True
                    # 进入拖动模式，应用拖动样式
                    self.container.setStyleSheet(self._dragging_style)
                    self.setWindowOpacity(0.85)
            
            if self._is_dragging:
                new_pos = event.globalPosition().toPoint() - self._drag_offset
                self.move(new_pos)
            return True
        
        elif event.type() == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
            # 恢复正常样式
            if getattr(self, '_is_dragging', False):
                self.container.setStyleSheet(self._normal_style)
                self.setWindowOpacity(1.0)
            
            self._drag_offset = None
            self._is_dragging = False
            return True
        
        return super().eventFilter(obj, event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            menu = QMenu(self)
            menu.setStyleSheet(MENU_STYLE)
            prompt_action = menu.addAction(qta.icon('mdi6.text-box-edit-outline', color='#555'), "Prompt 管理")
            settings_action = menu.addAction(qta.icon('mdi6.cog-outline', color='#555'), "设置")
            menu.addSeparator()
            quit_action = menu.addAction(qta.icon('mdi6.power', color='#e53935'), "退出程序")
            action = menu.exec(event.globalPosition().toPoint())
            if action == prompt_action:
                self._open_prompt_settings()
            elif action == settings_action:
                self._open_settings()
            elif action == quit_action:
                QApplication.quit()


if __name__ == "__main__":
    init_database()
    
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)

    font = QFont("Microsoft YaHei UI", 9)
    font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    app.setFont(font)
    
    # 单实例检测
    shared_memory = QSharedMemory("ArtcoSingleInstanceLock")
    if not shared_memory.create(1):
        # 已有实例在运行
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.warning(None, "Artco", "程序已在运行中，请查看系统托盘。")
        sys.exit(0)
    
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(get_app_icon())
    window = CapsuleWidget()

    window.reveal(animated=False)
    sys.exit(app.exec())


