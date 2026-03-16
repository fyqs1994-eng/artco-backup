"""
任务面板 - 显示分配给供应商的任务，支持提交资产
"""

import os
from datetime import datetime
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QComboBox, QMessageBox,
    QSizePolicy, QStackedWidget, QProgressBar
)
from PySide6.QtCore import Qt, Signal, QThread, QSize
from PySide6.QtGui import QColor

import qtawesome as qta

from config import workspace_config
# Supabase 功能已移除
def get_vendors(): return []
def get_vendor_tasks(vendor_id): return []
def get_task_asset(task_id): return None
def get_latest_version_status(task_id): return None
def submit_first_version(task_id, file_path, note): return {"success": False, "message": "Supabase功能已禁用"}
def submit_new_version(task_id, file_path, note): return {"success": False, "message": "Supabase功能已禁用"}
def get_task_comments(task_id): return []
from ui.theme import (
    BG_PRIMARY, BG_SECONDARY, BG_HOVER, BG_ACTIVE, BG_ELEVATED,
    BORDER_SUBTLE, BORDER_DEFAULT,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_TERTIARY, TEXT_MUTED,
    ACCENT_PRIMARY, ACCENT_HOVER, ACCENT_PRESSED, ACCENT_SUBTLE, ACCENT_BORDER,
    COLOR_SUCCESS, COLOR_WARNING, COLOR_ERROR, COLOR_INFO,
    COLOR_SUCCESS_SUBTLE, COLOR_WARNING_SUBTLE, COLOR_ERROR_SUBTLE,
    RADIUS_SM, RADIUS_MD, RADIUS_LG,
    SPACING_XS, SPACING_SM, SPACING_MD, SPACING_LG,
    get_scrollbar_style, get_combo_style, get_btn_primary_style
)


class LoadingWorker(QThread):
    """后台加载线程"""
    finished = Signal(dict)
    error = Signal(str)
    
    def __init__(self, func, *args, **kwargs):
        super().__init__()
        self.func = func
        self.args = args
        self.kwargs = kwargs
    
    def run(self):
        try:
            result = self.func(*self.args, **self.kwargs)
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class SubmitWorker(QThread):
    """提交任务线程"""
    finished = Signal(dict)
    error = Signal(str)
    progress = Signal(str)
    
    def __init__(self, task, file_path, is_first_version=True, asset_id=None, version_count=0):
        super().__init__()
        self.task = task
        self.file_path = file_path
        self.is_first_version = is_first_version
        self.asset_id = asset_id
        self.version_count = version_count
    
    def run(self):
        try:
            self.progress.emit("正在上传文件...")
            
            if self.is_first_version:
                result = submit_first_version(self.task, self.file_path)
            else:
                result = submit_new_version(self.task, self.asset_id, self.version_count, self.file_path)
            
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class TaskCard(QFrame):
    """任务卡片"""
    submit_clicked = Signal(dict)  # 发射任务数据
    
    def __init__(self, task: dict, parent=None):
        super().__init__(parent)
        self.task = task
        self._version_info = None
        self._comments = []
        self._hover = False
        self.init_ui()
        self._load_version_info()
    
    def init_ui(self):
        self.setObjectName("taskCard")
        self._update_card_style()
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACING_MD, SPACING_MD, SPACING_MD, SPACING_MD)
        layout.setSpacing(SPACING_SM)
        
        # 标题行
        title_layout = QHBoxLayout()
        title_layout.setSpacing(SPACING_SM)
        
        # 资产类型图标
        type_icon = self._get_type_icon(self.task.get("asset_type", ""))
        icon_label = QLabel()
        icon_label.setPixmap(type_icon.pixmap(QSize(18, 18)))
        title_layout.addWidget(icon_label)
        
        # 标题
        title = QLabel(self.task.get("title", "未命名任务"))
        title.setStyleSheet(f"font-size: 13px; font-weight: 600; color: {TEXT_PRIMARY};")
        title_layout.addWidget(title)
        title_layout.addStretch()
        
        # 状态标签
        self.status_label = QLabel()
        self._update_status_label()
        title_layout.addWidget(self.status_label)
        
        layout.addLayout(title_layout)
        
        # 项目信息
        project_name = "未分配项目"
        if self.task.get("projects"):
            project_name = self.task["projects"].get("title", project_name)
        
        info_layout = QHBoxLayout()
        info_layout.setSpacing(SPACING_MD)
        
        project_label = QLabel(f"📁 {project_name}")
        project_label.setStyleSheet(f"color: {TEXT_TERTIARY}; font-size: 11px;")
        info_layout.addWidget(project_label)
        
        type_label = QLabel(f"🏷️ {self.task.get('asset_type', '未知类型')}")
        type_label.setStyleSheet(f"color: {TEXT_TERTIARY}; font-size: 11px;")
        info_layout.addWidget(type_label)
        
        # 截止日期
        deadline = self.task.get("deadline")
        if deadline:
            try:
                dt = datetime.fromisoformat(deadline.replace("Z", "+00:00"))
                deadline_str = dt.strftime("%m/%d")
                deadline_label = QLabel(f"⏰ {deadline_str}")
                deadline_label.setStyleSheet(f"color: {TEXT_TERTIARY}; font-size: 11px;")
                info_layout.addWidget(deadline_label)
            except:
                pass
        
        info_layout.addStretch()
        layout.addLayout(info_layout)
        
        # 描述（如果有）
        desc = self.task.get("description")
        if desc:
            desc_label = QLabel(desc[:80] + ("..." if len(desc) > 80 else ""))
            desc_label.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px;")
            desc_label.setWordWrap(True)
            layout.addWidget(desc_label)
        
        # 反馈区域（如果被拒绝）
        self.feedback_container = QWidget()
        self.feedback_layout = QVBoxLayout(self.feedback_container)
        self.feedback_layout.setContentsMargins(0, 0, 0, 0)
        self.feedback_container.hide()
        layout.addWidget(self.feedback_container)
        
        # 操作按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self.submit_btn = QPushButton("提交当前图片")
        self.submit_btn.setIcon(qta.icon('mdi6.upload', color='#fff'))
        self.submit_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {ACCENT_PRIMARY};
                color: white;
                border: none;
                border-radius: {RADIUS_MD}px;
                padding: 6px 12px;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: {ACCENT_HOVER};
            }}
            QPushButton:pressed {{
                background-color: {ACCENT_PRESSED};
            }}
            QPushButton:disabled {{
                background-color: {BORDER_DEFAULT};
                color: {TEXT_MUTED};
            }}
        """)
        self.submit_btn.clicked.connect(self._on_submit_clicked)
        self.submit_btn.setEnabled(False)  # 默认禁用，需要有当前图片才启用
        self.submit_btn.setToolTip("请先在图片浏览器中选择一张图片")
        btn_layout.addWidget(self.submit_btn)
        
        layout.addLayout(btn_layout)
    
    def set_has_current_image(self, has_image: bool):
        """设置是否有当前可提交的图片"""
        # 先检查版本状态
        if self._version_info:
            status = self._version_info.get("status", "pending")
            if status == "pending":
                # 审核中，不允许提交
                return
            elif status == "approved":
                # 已通过，不允许提交
                return
        
        # 有可提交的图片时才启用按钮
        self.submit_btn.setEnabled(has_image)
        if has_image:
            self.submit_btn.setToolTip("")
        else:
            self.submit_btn.setToolTip("请先在图片浏览器中选择一张图片")
    
    def _update_card_style(self):
        """更新卡片样式"""
        if self._hover:
            bg = BG_HOVER
            border = BORDER_DEFAULT
        else:
            bg = BG_PRIMARY
            border = BORDER_SUBTLE
        
        self.setStyleSheet(f"""
            #taskCard {{
                background-color: {bg};
                border: 1px solid {border};
                border-radius: {RADIUS_MD}px;
            }}
        """)
    
    def enterEvent(self, event):
        self._hover = True
        self._update_card_style()
    
    def leaveEvent(self, event):
        self._hover = False
        self._update_card_style()
    
    def _get_type_icon(self, asset_type: str):
        """根据资产类型返回图标"""
        icon_map = {
            "KV": ("mdi6.image-area", COLOR_ERROR),
            "Character": ("mdi6.account", "#722ed1"),
            "Environment": ("mdi6.terrain", COLOR_SUCCESS),
            "UI": ("mdi6.view-dashboard", COLOR_INFO),
            "Icon": ("mdi6.star", COLOR_WARNING),
        }
        icon_name, color = icon_map.get(asset_type, ("mdi6.file-image", TEXT_TERTIARY))
        return qta.icon(icon_name, color=color)
    
    def _update_status_label(self):
        """更新状态标签"""
        status = self.task.get("status", "open")
        
        # 状态配置: (文字, 文字颜色, 背景色)
        status_config = {
            "open": ("待提交", COLOR_WARNING, COLOR_WARNING_SUBTLE),
            "in_progress": ("审核中", COLOR_INFO, ACCENT_SUBTLE),
            "completed": ("已完成", COLOR_SUCCESS, COLOR_SUCCESS_SUBTLE),
            "cancelled": ("已取消", TEXT_TERTIARY, BG_SECONDARY),
        }
        
        # 如果有版本信息，检查是否被拒绝
        if self._version_info and self._version_info.get("status") == "rejected":
            text, fg, bg = "需修改", COLOR_ERROR, COLOR_ERROR_SUBTLE
        else:
            text, fg, bg = status_config.get(status, ("未知", TEXT_TERTIARY, BG_SECONDARY))
        
        self.status_label.setText(f" {text} ")
        self.status_label.setStyleSheet(f"""
            background-color: {bg};
            color: {fg};
            border-radius: {RADIUS_SM}px;
            padding: 2px 6px;
            font-size: 11px;
            font-weight: 500;
        """)
    
    def _load_version_info(self):
        """加载版本信息"""
        task_id = self.task.get("id")
        if not task_id:
            return
        
        self._worker = LoadingWorker(get_latest_version_status, task_id)
        self._worker.finished.connect(self._on_version_loaded)
        self._worker.start()
    
    def _on_version_loaded(self, result):
        """版本信息加载完成"""
        if result.get("success") and result.get("data"):
            self._version_info = result["data"]
            self._update_status_label()
            self._update_submit_button()
            
            # 如果被拒绝，加载评论
            if self._version_info.get("status") == "rejected":
                self._load_comments()
    
    def _update_submit_button(self):
        """根据版本状态更新提交按钮"""
        if not self._version_info:
            # 还没提交过
            self.submit_btn.setText("提交当前图片")
            # 按钮启用由 set_has_current_image 控制
            return
        
        status = self._version_info.get("status", "pending")
        version = self._version_info.get("version_number", "v1")
        
        if status == "pending":
            self.submit_btn.setText("等待审核中...")
            self.submit_btn.setEnabled(False)
        elif status == "rejected":
            next_version = f"v{int(version[1:]) + 1}"
            self.submit_btn.setText(f"上传修改版 {next_version}")
            # 按钮启用由 set_has_current_image 控制
        elif status == "approved":
            self.submit_btn.setText("已通过")
            self.submit_btn.setEnabled(False)
    
    def _load_comments(self):
        """加载评论"""
        task_id = self.task.get("id")
        if not task_id:
            return
        
        self._comments_worker = LoadingWorker(get_task_comments, task_id)
        self._comments_worker.finished.connect(self._on_comments_loaded)
        self._comments_worker.start()
    
    def _on_comments_loaded(self, result):
        """评论加载完成"""
        if result.get("success") and result.get("data"):
            self._comments = result["data"]
            self._show_feedback()
    
    def _show_feedback(self):
        """显示反馈信息"""
        # 清空旧内容
        while self.feedback_layout.count():
            item = self.feedback_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        if not self._comments:
            return
        
        # 显示最新评论
        latest = self._comments[0]
        content = latest.get("content", "")
        
        feedback_frame = QFrame()
        feedback_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {COLOR_ERROR_SUBTLE};
                border: 1px solid {COLOR_ERROR}20;
                border-radius: {RADIUS_MD}px;
            }}
        """)
        
        fl = QVBoxLayout(feedback_frame)
        fl.setContentsMargins(SPACING_SM, SPACING_SM, SPACING_SM, SPACING_SM)
        fl.setSpacing(SPACING_XS)
        
        header = QLabel("💬 审核反馈")
        header.setStyleSheet(f"color: {COLOR_ERROR}; font-size: 11px; font-weight: 600;")
        fl.addWidget(header)
        
        content_label = QLabel(content)
        content_label.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 12px;")
        content_label.setWordWrap(True)
        fl.addWidget(content_label)
        
        self.feedback_layout.addWidget(feedback_frame)
        self.feedback_container.show()
    
    def _on_submit_clicked(self):
        """点击提交按钮"""
        self.submit_clicked.emit({
            "task": self.task,
            "version_info": self._version_info
        })


class VendorSelector(QWidget):
    """供应商选择器"""
    vendor_selected = Signal(str, str)  # vendor_id, vendor_name
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.vendors = []
        self.init_ui()
        self._load_vendors()
    
    def init_ui(self):
        self.setStyleSheet(f"background: {BG_SECONDARY};")
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACING_LG, SPACING_LG, SPACING_LG, SPACING_LG)
        layout.setSpacing(SPACING_MD)
        
        # 图标
        icon_label = QLabel()
        icon_label.setPixmap(qta.icon('mdi6.account-group', color=ACCENT_PRIMARY).pixmap(48, 48))
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon_label)
        
        # 标题
        title = QLabel("选择供应商身份")
        title.setStyleSheet(f"font-size: 14px; font-weight: 600; color: {TEXT_PRIMARY};")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        
        # 说明
        desc = QLabel("请选择您所属的供应商\n以查看分配给您的任务")
        desc.setStyleSheet(f"color: {TEXT_TERTIARY}; font-size: 12px;")
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(desc)
        
        layout.addSpacing(SPACING_SM)
        
        # 下拉框
        self.combo = QComboBox()
        self.combo.setMinimumHeight(36)
        self.combo.setStyleSheet(get_combo_style())
        self.combo.addItem("正在加载供应商列表...")
        self.combo.setEnabled(False)
        layout.addWidget(self.combo)
        
        layout.addSpacing(SPACING_XS)
        
        # 确认按钮
        self.confirm_btn = QPushButton("确认选择")
        self.confirm_btn.setMinimumHeight(36)
        self.confirm_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {ACCENT_PRIMARY};
                color: white;
                border: none;
                border-radius: {RADIUS_MD}px;
                font-size: 13px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background-color: {ACCENT_HOVER};
            }}
            QPushButton:pressed {{
                background-color: {ACCENT_PRESSED};
            }}
            QPushButton:disabled {{
                background-color: {BORDER_DEFAULT};
                color: {TEXT_MUTED};
            }}
        """)
        self.confirm_btn.setEnabled(False)
        self.confirm_btn.clicked.connect(self._on_confirm)
        layout.addWidget(self.confirm_btn)
        
        layout.addStretch()
    
    def _load_vendors(self):
        """加载供应商列表"""
        self._worker = LoadingWorker(get_vendors)
        self._worker.finished.connect(self._on_vendors_loaded)
        self._worker.error.connect(self._on_load_error)
        self._worker.start()
    
    def _on_vendors_loaded(self, result):
        """供应商列表加载完成"""
        self.combo.clear()
        
        if not result.get("success"):
            self.combo.addItem(f"加载失败: {result.get('message', '未知错误')}")
            return
        
        self.vendors = result.get("data", [])
        
        if not self.vendors:
            self.combo.addItem("暂无供应商")
            return
        
        for vendor in self.vendors:
            self.combo.addItem(vendor.get("name", "未命名"), vendor.get("id"))
        
        self.combo.setEnabled(True)
        self.confirm_btn.setEnabled(True)
    
    def _on_load_error(self, error):
        """加载出错"""
        self.combo.clear()
        self.combo.addItem(f"加载失败: {error}")
    
    def _on_confirm(self):
        """确认选择"""
        idx = self.combo.currentIndex()
        if idx < 0 or idx >= len(self.vendors):
            return
        
        vendor = self.vendors[idx]
        self.vendor_selected.emit(vendor.get("id", ""), vendor.get("name", ""))


class TaskListWidget(QWidget):
    """任务列表组件"""
    
    def __init__(self, vendor_id: str, parent=None):
        super().__init__(parent)
        self.vendor_id = vendor_id
        self.tasks = []
        self._workers = []
        self._current_image_path: Optional[str] = None  # 当前浏览的图片路径
        self.init_ui()
        self.refresh_tasks()
    
    def set_current_image_path(self, path: Optional[str]):
        """设置当前浏览的图片路径"""
        self._current_image_path = path
        self._update_submit_buttons()
    
    def _update_submit_buttons(self):
        """更新所有任务卡片的提交按钮状态"""
        has_image = bool(self._current_image_path and os.path.exists(self._current_image_path))
        for i in range(self.scroll_layout.count() - 1):  # 最后一个是 stretch
            item = self.scroll_layout.itemAt(i)
            if item and item.widget():
                widget = item.widget()
                if isinstance(widget, TaskCard):
                    widget.set_has_current_image(has_image)
    
    def init_ui(self):
        self.setStyleSheet(f"background: {BG_SECONDARY};")
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # 加载指示器
        self.loading_widget = QWidget()
        loading_layout = QVBoxLayout(self.loading_widget)
        loading_layout.setContentsMargins(SPACING_LG, 48, SPACING_LG, 48)
        loading_label = QLabel("正在加载任务...")
        loading_label.setStyleSheet(f"color: {TEXT_TERTIARY}; font-size: 13px;")
        loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        loading_layout.addWidget(loading_label)
        layout.addWidget(self.loading_widget)
        
        # 滚动区域
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet(f"""
            QScrollArea {{
                background-color: transparent;
                border: none;
            }}
            {get_scrollbar_style()}
        """)
        
        self.scroll_content = QWidget()
        self.scroll_content.setStyleSheet("background: transparent;")
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setContentsMargins(SPACING_SM, SPACING_SM, SPACING_SM, SPACING_SM)
        self.scroll_layout.setSpacing(SPACING_SM)
        self.scroll_layout.addStretch()
        
        self.scroll.setWidget(self.scroll_content)
        layout.addWidget(self.scroll)
        
        # 空状态
        self.empty_widget = QWidget()
        empty_layout = QVBoxLayout(self.empty_widget)
        empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.setContentsMargins(SPACING_LG, 60, SPACING_LG, 60)
        empty_layout.setSpacing(SPACING_SM)
        
        empty_icon = QLabel()
        empty_icon.setPixmap(qta.icon('mdi6.clipboard-text-outline', color=TEXT_MUTED).pixmap(40, 40))
        empty_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(empty_icon)
        
        empty_label = QLabel("暂无分配的任务")
        empty_label.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 13px; font-weight: 500;")
        empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(empty_label)
        
        empty_hint = QLabel("您的任务将会显示在这里")
        empty_hint.setStyleSheet(f"color: {TEXT_TERTIARY}; font-size: 12px;")
        empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(empty_hint)
        
        self.empty_widget.hide()
        layout.addWidget(self.empty_widget)
    
    def refresh_tasks(self):
        """刷新任务列表"""
        self.loading_widget.show()
        self.empty_widget.hide()
        
        # 清空现有任务卡片
        while self.scroll_layout.count() > 1:  # 保留 stretch
            item = self.scroll_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        self._worker = LoadingWorker(get_vendor_tasks, self.vendor_id)
        self._worker.finished.connect(self._on_tasks_loaded)
        self._worker.error.connect(self._on_load_error)
        self._workers.append(self._worker)
        self._worker.start()
    
    def _on_tasks_loaded(self, result):
        """任务加载完成"""
        self.loading_widget.hide()
        
        if not result.get("success"):
            QMessageBox.warning(self, "加载失败", result.get("message", "未知错误"))
            return
        
        self.tasks = result.get("data", [])
        
        if not self.tasks:
            self.empty_widget.show()
            return
        
        # 添加任务卡片
        for task in self.tasks:
            card = TaskCard(task)
            card.submit_clicked.connect(self._on_submit_task)
            self.scroll_layout.insertWidget(self.scroll_layout.count() - 1, card)
        
        # 加载完成后更新按钮状态
        self._update_submit_buttons()
    
    def _on_load_error(self, error):
        """加载出错"""
        self.loading_widget.hide()
        QMessageBox.warning(self, "加载失败", error)
    
    def _on_submit_task(self, data):
        """处理任务提交"""
        task = data.get("task")
        version_info = data.get("version_info")
        
        # 使用当前浏览的图片路径
        file_path = self._current_image_path
        
        if not file_path or not os.path.exists(file_path):
            QMessageBox.warning(self, "提交失败", "请先在图片浏览器中选择一张图片")
            return
        
        # 获取文件名用于确认
        from pathlib import Path
        file_name = Path(file_path).name
        
        # 检查文件大小
        file_size = os.path.getsize(file_path)
        if file_size > 50 * 1024 * 1024:  # 50MB
            QMessageBox.warning(self, "文件过大", "文件大小超过 50MB 限制，请压缩后再试")
            return
        
        # 格式化文件大小显示
        if file_size > 1024 * 1024:
            size_str = f"{file_size / (1024*1024):.1f} MB"
        elif file_size > 1024:
            size_str = f"{file_size / 1024:.0f} KB"
        else:
            size_str = f"{file_size} B"
        
        # 确认提交对话框
        task_title = task.get("title", "未命名任务")
        reply = QMessageBox.question(
            self, "确认提交",
            f"确定要将以下文件提交到任务吗？\n\n"
            f"📋 任务: {task_title}\n"
            f"📁 文件: {file_name}\n"
            f"📦 大小: {size_str}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )
        
        if reply != QMessageBox.StandardButton.Yes:
            return
        
        # 确定是首版还是修改版
        is_first_version = version_info is None
        asset_id = version_info.get("asset_id") if version_info else None
        version_count = 0
        
        if version_info:
            version_num = version_info.get("version_number", "v1")
            try:
                version_count = int(version_num[1:])
            except:
                version_count = 1
        
        # 开始提交
        self._submit_worker = SubmitWorker(
            task=task,
            file_path=file_path,
            is_first_version=is_first_version,
            asset_id=asset_id,
            version_count=version_count
        )
        self._submit_worker.finished.connect(self._on_submit_finished)
        self._submit_worker.error.connect(self._on_submit_error)
        self._workers.append(self._submit_worker)
        
        # 显示进度提示
        QMessageBox.information(self, "提交中", "正在上传文件，请稍候...")
        self._submit_worker.start()
    
    def _on_submit_finished(self, result):
        """提交完成"""
        if result.get("success"):
            QMessageBox.information(self, "提交成功", result.get("message", "提交成功"))
            self.refresh_tasks()  # 刷新列表
        else:
            QMessageBox.warning(self, "提交失败", result.get("message", "未知错误"))
    
    def _on_submit_error(self, error):
        """提交出错"""
        QMessageBox.warning(self, "提交失败", error)


class TaskPanel(QWidget):
    """任务面板主窗口"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("任务中心")
        self.setMinimumSize(500, 600)
        self.resize(550, 700)
        self.setStyleSheet(f"background-color: {BG_SECONDARY};")
        
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # 使用 StackedWidget 切换页面
        self.stack = QStackedWidget()
        layout.addWidget(self.stack)
        
        # 页面1: 供应商选择
        self.vendor_selector = VendorSelector()
        self.vendor_selector.vendor_selected.connect(self._on_vendor_selected)
        self.stack.addWidget(self.vendor_selector)
        
        # 页面2: 任务列表（稍后创建）
        self.task_list = None
        
        # 检查是否已配置供应商
        if workspace_config.is_vendor_configured():
            self._show_task_list(
                workspace_config.get_vendor_id(),
                workspace_config.get_vendor_name()
            )
    
    def _on_vendor_selected(self, vendor_id: str, vendor_name: str):
        """供应商选择完成"""
        # 保存到配置
        workspace_config.set_vendor(vendor_id, vendor_name)
        
        # 显示任务列表
        self._show_task_list(vendor_id, vendor_name)
    
    def _show_task_list(self, vendor_id: str, vendor_name: str):
        """显示任务列表"""
        # 创建带标题栏的容器
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)
        
        # 顶部身份栏
        identity_bar = QWidget()
        identity_bar.setStyleSheet(f"background-color: {BG_PRIMARY}; border-bottom: 1px solid {BORDER_DEFAULT};")
        identity_layout = QHBoxLayout(identity_bar)
        identity_layout.setContentsMargins(SPACING_LG, SPACING_SM, SPACING_LG, SPACING_SM)
        
        identity_label = QLabel(f"👤 当前身份: {vendor_name}")
        identity_label.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px;")
        identity_layout.addWidget(identity_label)
        
        identity_layout.addStretch()
        
        # 切换身份按钮
        switch_btn = QPushButton("切换身份")
        switch_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {ACCENT_PRIMARY};
                border: none;
                font-size: 12px;
            }}
            QPushButton:hover {{
                color: {ACCENT_HOVER};
            }}
        """)
        switch_btn.clicked.connect(self._switch_vendor)
        identity_layout.addWidget(switch_btn)
        
        container_layout.addWidget(identity_bar)
        
        # 任务列表
        self.task_list = TaskListWidget(vendor_id)
        container_layout.addWidget(self.task_list)
        
        # 添加到 stack
        self.stack.addWidget(container)
        self.stack.setCurrentWidget(container)
    
    def _switch_vendor(self):
        """切换供应商身份"""
        # 清除配置
        workspace_config.set_vendor("", "")
        
        # 切换到选择页面
        self.stack.setCurrentWidget(self.vendor_selector)
        
        # 刷新供应商列表
        self.vendor_selector._load_vendors()


# 测试入口
if __name__ == "__main__":
    import sys
    from PySide6.QtWidgets import QApplication
    
    app = QApplication(sys.argv)
    window = TaskPanel()
    window.show()
    sys.exit(app.exec())
