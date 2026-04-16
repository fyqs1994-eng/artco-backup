"""
分配面板 - 将图片快速分配到工作区
"""

import os
import shutil
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QButtonGroup, QFileDialog, QMessageBox, QGroupBox, QFrame
)

from PySide6.QtCore import Qt, Signal

from PySide6.QtGui import QFont



from config import workspace_config, RESOURCE_TYPES, IMAGE_PROGRESS
from ui.theme import (
    get_group_box_style, get_preview_frame_style,
    ACCENT_PRIMARY, TEXT_PRIMARY, TEXT_SECONDARY,
    SPACING_SM, SPACING_MD, SPACING_LG, SPACING_XL,
    FONT_FAMILY_MONO
)







class AssignPanel(QDialog):

    """分配面板对话框"""
    assigned = Signal(str)  # 分配完成后发出信号，参数为新文件路径
    
    def __init__(self, source_path: str, parent=None):
        super().__init__(parent)
        self._source_path = Path(source_path)
        self._init_ui()
        self._load_settings()
    
    def _init_ui(self):
        os.environ.setdefault("QT_API", "pyside6")
        from qfluentwidgets import PushButton, PrimaryPushButton, ComboBox, EditableComboBox, RadioButton


        self.setWindowTitle("分配到工作区")

        self.setMinimumWidth(460)  # 稍微调宽一点，更有呼吸感
        self.setModal(True)
        
        # 主布局

        layout = QVBoxLayout(self)
        layout.setSpacing(SPACING_LG)
        layout.setContentsMargins(SPACING_XL, SPACING_XL, SPACING_XL, SPACING_XL)
        

        # === 工作区路径 ===
        workspace_group = QGroupBox("工作区")
        workspace_group.setStyleSheet(get_group_box_style())
        workspace_layout = QHBoxLayout(workspace_group)
        workspace_layout.setContentsMargins(SPACING_LG, SPACING_LG, SPACING_LG, SPACING_LG)

        
        self.label_workspace = QLabel()
        self.label_workspace.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px;")
        workspace_layout.addWidget(self.label_workspace, 1)
        
        btn_change = PushButton("更改")
        btn_change.setFixedHeight(32)

        btn_change.setFixedWidth(60)
        btn_change.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_change.clicked.connect(self._select_workspace)
        workspace_layout.addWidget(btn_change)
        
        layout.addWidget(workspace_group)
        
        # === 主题 & 类型 (并排) ===
        row1_layout = QHBoxLayout()
        row1_layout.setSpacing(SPACING_LG)
        
        # 主题名称
        topic_group = QGroupBox("主题名称")
        topic_group.setStyleSheet(get_group_box_style())
        topic_layout = QVBoxLayout(topic_group)
        topic_layout.setContentsMargins(SPACING_LG, SPACING_LG, SPACING_LG, SPACING_LG)

        
        self.combo_topic = EditableComboBox()


        self.combo_topic.setPlaceholderText("选择或输入主题...")

        

        self.combo_topic.currentTextChanged.connect(self._update_preview)
        topic_layout.addWidget(self.combo_topic)
        row1_layout.addWidget(topic_group, 2)
        
        # 版本号
        version_group = QGroupBox("版本")
        version_group.setStyleSheet(get_group_box_style())
        version_layout = QVBoxLayout(version_group)
        version_layout.setContentsMargins(SPACING_LG, SPACING_LG, SPACING_LG, SPACING_LG)

        
        self.combo_version = EditableComboBox()
        self.combo_version.addItems(["v1", "v2", "v3", "v4", "v5"])


        self.combo_version.currentTextChanged.connect(self._update_preview)
        version_layout.addWidget(self.combo_version)
        row1_layout.addWidget(version_group, 1)
        
        layout.addLayout(row1_layout)
        
        # === 资源类型 ===
        type_group = QGroupBox("资源类型")
        type_group.setStyleSheet(get_group_box_style())
        type_layout = QHBoxLayout(type_group)
        type_layout.setContentsMargins(SPACING_LG, SPACING_LG, SPACING_LG, SPACING_LG)
        type_layout.setSpacing(SPACING_MD)

        
        self.type_group = QButtonGroup(self)
        for i, rtype in enumerate(RESOURCE_TYPES):
            btn = RadioButton(rtype)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)

            self.type_group.addButton(btn, i)
            type_layout.addWidget(btn)
            if i == 0:
                btn.setChecked(True)
        
        type_layout.addStretch()
        self.type_group.buttonClicked.connect(self._update_preview)
        layout.addWidget(type_group)
        
        # === 图片进度 ===
        progress_group = QGroupBox("制作进度")
        progress_group.setStyleSheet(get_group_box_style())
        progress_layout = QHBoxLayout(progress_group)
        progress_layout.setContentsMargins(SPACING_LG, SPACING_LG, SPACING_LG, SPACING_LG)
        progress_layout.setSpacing(SPACING_MD)

        
        self.progress_group = QButtonGroup(self)
        for i, progress in enumerate(IMAGE_PROGRESS):
            btn = RadioButton(progress)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)

            self.progress_group.addButton(btn, i)
            progress_layout.addWidget(btn)
            if i == 0:
                btn.setChecked(True)
        
        progress_layout.addStretch()
        self.progress_group.buttonClicked.connect(self._update_preview)
        layout.addWidget(progress_group)
        
        # === 预览 (使用标准化预览容器) ===
        preview_frame = QFrame()
        preview_frame.setStyleSheet(get_preview_frame_style())
        preview_layout = QVBoxLayout(preview_frame)
        preview_layout.setContentsMargins(SPACING_LG, SPACING_LG, SPACING_LG, SPACING_LG)
        preview_layout.setSpacing(SPACING_SM)

        
        preview_header = QHBoxLayout()
        preview_title = QLabel("📄 目标文件路径")
        preview_title.setStyleSheet(f"color: {ACCENT_PRIMARY}; font-weight: 600; font-size: 12px;")
        preview_header.addWidget(preview_title)
        preview_header.addStretch()
        preview_layout.addLayout(preview_header)
        
        self.label_preview = QLabel()
        self.label_preview.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 13px; font-family: {FONT_FAMILY_MONO};")
        self.label_preview.setWordWrap(True)
        preview_layout.addWidget(self.label_preview)
        
        layout.addWidget(preview_frame)
        
        # === 底部操作按钮 ===
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(SPACING_MD)

        
        btn_cancel = PushButton("取消")

        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)
        
        btn_layout.addStretch()
        
        self.btn_assign = PrimaryPushButton("确认分配")

        self.btn_assign.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_assign.clicked.connect(self._do_assign)
        btn_layout.addWidget(self.btn_assign)
        
        layout.addLayout(btn_layout)

    
    def _load_settings(self):
        """加载上次设置"""
        # 工作区路径
        workspace = workspace_config.get_workspace_path()
        if workspace:
            self.label_workspace.setText(workspace)
        else:
            self.label_workspace.setText("未设置")
        
        # 主题列表
        topics = workspace_config.get_existing_topics()
        recent = workspace_config.get_recent_topics()
        
        # 合并：最近使用的在前，其他按字母排序
        all_topics = []
        for t in recent:
            if t not in all_topics:
                all_topics.append(t)
        for t in topics:
            if t not in all_topics:
                all_topics.append(t)
        
        self.combo_topic.clear()
        self.combo_topic.addItems(all_topics)

        
        # 恢复上次设置
        last = workspace_config.get_last_settings()
        
        if last["topic"]:
            idx = self.combo_topic.findText(last["topic"])
            if idx >= 0:
                self.combo_topic.setCurrentIndex(idx)
            else:
                self.combo_topic.setEditText(last["topic"])
        
        # 资源类型
        try:
            type_idx = RESOURCE_TYPES.index(last["resource_type"])
            self.type_group.button(type_idx).setChecked(True)
        except ValueError:
            pass
        
        # 进度
        try:
            progress_idx = IMAGE_PROGRESS.index(last["progress"])
            self.progress_group.button(progress_idx).setChecked(True)
        except ValueError:
            pass
        
        # 自动检测版本号
        self._auto_detect_version()
        self._update_preview()
    
    def _select_workspace(self):
        """选择工作区目录"""
        current = workspace_config.get_workspace_path()
        path = QFileDialog.getExistingDirectory(
            self, "选择工作区目录", current or ""
        )
        if path:
            workspace_config.set_workspace_path(path)
            self.label_workspace.setText(path)
            # 重新加载主题列表
            topics = workspace_config.get_existing_topics()
            self.combo_topic.clear()
            self.combo_topic.addItems(topics)

            self._update_preview()
    
    def _get_current_settings(self) -> dict:
        """获取当前选择的设置"""
        topic = self.combo_topic.currentText().strip()
        
        type_btn = self.type_group.checkedButton()
        resource_type = type_btn.text() if type_btn else RESOURCE_TYPES[0]
        
        progress_btn = self.progress_group.checkedButton()
        progress = progress_btn.text() if progress_btn else IMAGE_PROGRESS[0]
        
        version = self.combo_version.currentText().strip()
        if not version.startswith("v"):
            version = f"v{version}"
        
        return {
            "topic": topic,
            "resource_type": resource_type,
            "progress": progress,
            "version": version,
        }
    
    def _generate_filename(self, settings: dict) -> str:
        """生成文件名"""
        ext = self._source_path.suffix
        return f"{settings['topic']}_{settings['resource_type']}_{settings['progress']}_{settings['version']}{ext}"
    
    def _generate_target_path(self, settings: dict) -> Path:
        """生成目标路径"""
        workspace = workspace_config.get_workspace_path()
        filename = self._generate_filename(settings)
        return Path(workspace) / settings["topic"] / settings["resource_type"] / filename
    
    def _auto_detect_version(self):
        """自动检测版本号"""
        settings = self._get_current_settings()
        workspace = workspace_config.get_workspace_path()
        
        if not workspace or not settings["topic"]:
            return
        
        # 查找同名文件的最大版本号
        target_dir = Path(workspace) / settings["topic"] / settings["resource_type"]
        if not target_dir.exists():
            self.combo_version.setCurrentText("v1")
            return
        
        prefix = f"{settings['topic']}_{settings['resource_type']}_{settings['progress']}_v"
        max_version = 0
        
        for f in target_dir.iterdir():
            if f.is_file() and f.stem.startswith(prefix.rstrip("v")):
                # 提取版本号
                name = f.stem
                try:
                    v_idx = name.rfind("_v")
                    if v_idx > 0:
                        v_str = name[v_idx + 2:]
                        v_num = int(v_str)
                        max_version = max(max_version, v_num)
                except ValueError:
                    pass
        
        self.combo_version.setCurrentText(f"v{max_version + 1}")
    
    def _update_preview(self):
        """更新预览"""
        settings = self._get_current_settings()
        
        if not settings["topic"]:
            self.label_preview.setText("请输入主题名称")
            self.btn_assign.setEnabled(False)
            return
        
        workspace = workspace_config.get_workspace_path()
        if not workspace:
            self.label_preview.setText("请先设置工作区目录")
            self.btn_assign.setEnabled(False)
            return
        
        target = self._generate_target_path(settings)
        self.label_preview.setText(str(target))
        self.btn_assign.setEnabled(True)
        
        # 自动检测版本
        self._auto_detect_version()
    
    def _do_assign(self):
        """执行分配"""
        settings = self._get_current_settings()
        workspace = workspace_config.get_workspace_path()
        
        # 验证
        if not workspace:
            QMessageBox.warning(self, "错误", "请先设置工作区目录")
            return
        
        if not settings["topic"]:
            QMessageBox.warning(self, "错误", "请输入主题名称")
            return
        
        if not self._source_path.exists():
            QMessageBox.warning(self, "错误", "源文件不存在")
            return
        
        # 生成目标路径
        target = self._generate_target_path(settings)
        
        # 检查目标是否已存在
        if target.exists():
            reply = QMessageBox.question(
                self, "文件已存在",
                f"目标文件已存在：\n{target.name}\n\n是否覆盖？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        
        # 创建目录
        target.parent.mkdir(parents=True, exist_ok=True)
        
        # 复制文件
        try:
            shutil.copy2(str(self._source_path), str(target))
        except Exception as e:
            QMessageBox.critical(self, "错误", f"复制文件失败：\n{e}")
            return
        
        # 保存设置
        workspace_config.save_last_settings(
            settings["topic"],
            settings["resource_type"],
            settings["progress"]
        )
        
        # 发送信号并关闭
        self.assigned.emit(str(target))
        self.accept()
        
        QMessageBox.information(
            self.parent(), "分配成功",
            f"文件已分配到：\n{target}"
        )
