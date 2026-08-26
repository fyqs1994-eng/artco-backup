"""
截图模块 - 编辑器窗口
"""

import base64

import qtawesome as qta
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QPushButton, 
    QGraphicsDropShadowEffect, QScrollArea, QFileDialog, QMessageBox
)
from PySide6.QtCore import Qt, QSize, QPoint, QBuffer, QIODevice, QTimer, QRect
from PySide6.QtGui import QColor, QPainter, QPixmap, QGuiApplication, QKeyEvent, QCursor, QFont, QFontMetrics, QPen

from database import add_record
from ui import PromptSelectMenu, SettingsDialog
from .marks import FONT_NAME
from .canvas import EditorCanvas
from .marks import NumberDot
from .toolbar import EditorToolbar, NumberAnnotationPanel


class EditorWindow(QMainWindow):
    """独立编辑窗口"""
    def __init__(self, pixmap: QPixmap):
        super().__init__()
        self.pixmap = pixmap
        self._auto_fitted = False
        self._copied = False  # 标记是否有过复制操作
        self._marks_count_at_copy = 0  # 复制时的标记数量，用于检测复制后是否有新增
        self._annotation_panel_visible = False
        self._annotation_expand_delta = 0
        self._annotation_expanded_by_us = False
        self._skip_next_sync = False
        self.init_ui()

    
    def init_ui(self):
        self.setWindowTitle("Artco 编辑器")
        self.setMinimumSize(800, 600)
        
        # 使用逻辑尺寸计算窗口大小
        dpr = self.pixmap.devicePixelRatio()
        img_w = int(self.pixmap.width() / dpr)
        img_h = int(self.pixmap.height() / dpr)
        screen = QGuiApplication.primaryScreen().geometry()
        win_w = min(img_w + 160, screen.width() - 100)
        win_h = min(img_h + 100, screen.height() - 100)
        self.resize(win_w, win_h)
        
        central = QWidget()
        central.setStyleSheet("background-color: #f0f0f0;")
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)
        
        self.toolbar = EditorToolbar()
        self.toolbar.tool_changed.connect(self._on_tool_changed)
        self.toolbar.save_clicked.connect(self._save_image)
        self.toolbar.copy_clicked.connect(self._copy_image)
        self.toolbar.ai_clicked.connect(self._ai_analyze)
        self.toolbar.archive_clicked.connect(self._archive_record)
        self.toolbar.undo_clicked.connect(self._on_undo)
        self.toolbar.assign_clicked.connect(self._assign_feedback)
        self.toolbar.color_changed.connect(self._on_color_changed)
        
        # 工具栏阴影
        toolbar_shadow = QGraphicsDropShadowEffect(self.toolbar)
        toolbar_shadow.setBlurRadius(20)
        toolbar_shadow.setColor(QColor(0, 0, 0, 30))
        toolbar_shadow.setOffset(0, 2)
        self.toolbar.setGraphicsEffect(toolbar_shadow)
        main_layout.addWidget(self.toolbar)
        
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(False)
        scroll_area.setAlignment(Qt.AlignmentFlag.AlignCenter)
        scroll_area.setStyleSheet("""
            QScrollArea {
                background-color: #e0e0e0;
                border: none;
                border-radius: 12px;
            }
            QScrollBar:vertical, QScrollBar:horizontal {
                background: transparent;
                width: 8px;
                height: 8px;
                margin: 2px;
            }
            QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
                background: rgba(0, 0, 0, 0.2);
                border-radius: 4px;
                min-height: 30px;
                min-width: 30px;
            }
            QScrollBar::handle:hover {
                background: rgba(0, 0, 0, 0.35);
            }
            QScrollBar::add-line, QScrollBar::sub-line {
                height: 0px;
                width: 0px;
            }
            QScrollBar::add-page, QScrollBar::sub-page {
                background: transparent;
            }
        """)
        self.scroll_area = scroll_area
        
        self.canvas = EditorCanvas(self.pixmap)
        self.canvas.pan_requested.connect(self._on_pan)
        scroll_area.setWidget(self.canvas)
        main_layout.addWidget(scroll_area)
        
        # 序号注释侧栏（自动弹出）
        self.annotation_panel = NumberAnnotationPanel()
        panel_shadow = QGraphicsDropShadowEffect(self.annotation_panel)
        panel_shadow.setBlurRadius(20)
        panel_shadow.setColor(QColor(0, 0, 0, 30))
        panel_shadow.setOffset(0, 2)
        self.annotation_panel.setGraphicsEffect(panel_shadow)
        main_layout.addWidget(self.annotation_panel)
        
        self.setCentralWidget(central)
        
        # 连接序号点变化信号
        self.canvas.number_dots_changed.connect(self._sync_annotation_panel)
        # 连接序号点重编号信号，同步侧栏注释内容映射
        self.canvas.number_dots_renumbered.connect(self._on_renumber)
        # 连接序号点点击信号，聚焦到侧栏输入框
        self.canvas.number_dot_clicked.connect(self.annotation_panel.focus_annotation)

        
        # Prompt 选择菜单
        self.prompt_menu = PromptSelectMenu(self)
        self.prompt_menu.prompt_selected.connect(self._do_ai_analyze)
        self.prompt_menu.edit_requested.connect(self._open_prompt_editor)
        
        self.move(
            (screen.width() - self.width()) // 2,
            (screen.height() - self.height()) // 2
        )

        # 初次打开自动适配大图（不打扰用户后续手动缩放）
        QTimer.singleShot(0, self._auto_fit_canvas)

    
    def _sync_annotation_panel(self):
        """同步序号注释面板"""
        if getattr(self, '_skip_next_sync', False):
            self._skip_next_sync = False
            return
        number_dots = [m for m in self.canvas.marks if isinstance(m, NumberDot)]
        self.annotation_panel.sync_with_marks(number_dots)
        panel_visible = self.annotation_panel.isVisible()
        if panel_visible != self._annotation_panel_visible:
            self._on_annotation_panel_visibility_changed(panel_visible)
            self._annotation_panel_visible = panel_visible

    def _on_renumber(self, mapping: dict, deleted: int):
        """处理重编号：先执行侧栏 renumber，再跳过紧随的 sync_with_marks。
        
        renumber 已经全量重建了侧栏（含编号+内容），若紧随的 number_dots_changed
        → _sync_annotation_panel → sync_with_marks 再次用新编号增删，会把刚建好的
        条目删掉再补空，导致内容错乱。用标志位让下一次 _sync_annotation_panel 跳过。
        """
        self._skip_next_sync = True
        self.annotation_panel.renumber(mapping, deleted)

    def _on_annotation_panel_visibility_changed(self, visible: bool):
        """注释侧栏显隐时，窗口向外扩展/收回，避免挤压图片可视区域。"""
        panel_w = self.annotation_panel.width()
        spacing = 0
        central = self.centralWidget()
        if central and central.layout():
            spacing = central.layout().spacing()
        delta = panel_w + max(0, spacing)
        if delta <= 0:
            return

        geo = self.geometry()
        screen = QGuiApplication.screenAt(geo.center())
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        avail = screen.availableGeometry()

        if visible:
            # 仅在我们有空间扩展时外扩；优先向右扩，越界则整体左移以保持完整可见
            target_w = min(geo.width() + delta, avail.width())
            applied_delta = target_w - geo.width()
            if applied_delta <= 0:
                self._annotation_expanded_by_us = False
                self._annotation_expand_delta = 0
                return
            new_x = geo.x()
            overflow = (new_x + target_w) - avail.right()
            if overflow > 0:
                new_x = max(avail.left(), new_x - overflow)
            self.setGeometry(new_x, geo.y(), target_w, geo.height())
            self._annotation_expanded_by_us = True
            self._annotation_expand_delta = applied_delta
        else:
            # 只回收我们之前自动扩出来的宽度，避免覆盖用户手动调整
            if not self._annotation_expanded_by_us or self._annotation_expand_delta <= 0:
                return
            target_w = max(self.minimumWidth(), geo.width() - self._annotation_expand_delta)
            self.setGeometry(geo.x(), geo.y(), target_w, geo.height())
            self._annotation_expanded_by_us = False
            self._annotation_expand_delta = 0
    
    def _on_tool_changed(self, tool_id: int):
        self.canvas.set_tool(tool_id)
    
    def _on_undo(self):
        self.canvas.undo()
    
    def _on_color_changed(self, color):
        """更新画布标记颜色"""
        self.canvas.set_mark_color(color)
    
    def _on_pan(self, delta_x: int, delta_y: int):
        """处理画布平移"""
        h_bar = self.scroll_area.horizontalScrollBar()
        v_bar = self.scroll_area.verticalScrollBar()
        h_bar.setValue(h_bar.value() - delta_x)
        v_bar.setValue(v_bar.value() - delta_y)

    def _auto_fit_canvas(self):
        """首次打开时自动适配大图到可视区域"""
        if self._auto_fitted:
            return
        if not self.scroll_area or not self.canvas:
            return

        viewport = self.scroll_area.viewport().size()
        base = self.canvas.base_size
        if base.width() <= 0 or base.height() <= 0:
            return

        # 预留更多边距，避免紧贴边缘
        margin = 32
        avail_w = max(1, viewport.width() - margin * 2)
        avail_h = max(1, viewport.height() - margin * 2)

        scale = min(avail_w / base.width(), avail_h / base.height(), 1.0)
        scale *= 0.9  # 再小一点，留出更舒适的呼吸空间

        # 只在需要缩小的大图时自动适配
        if scale < 0.98:
            self.canvas.set_scale(scale)

            # 同步收缩窗口，避免大图缩小后窗口仍然很大
            toolbar_w = max(self.toolbar.width(), self.toolbar.sizeHint().width())
            canvas_w = int(base.width() * self.canvas._scale)
            canvas_h = int(base.height() * self.canvas._scale)

            # 计算期望窗口大小（包含边距与滚动区边框）
            target_w = canvas_w + toolbar_w + 64
            target_h = canvas_h + 120

            screen = QGuiApplication.primaryScreen().geometry()
            target_w = min(target_w, screen.width() - 80)
            target_h = min(target_h, screen.height() - 80)

            if target_w < self.width() or target_h < self.height():
                self.resize(target_w, target_h)

        self._auto_fitted = True


    
    def _render_final_image(self) -> QPixmap:
        """渲染最终图片（含标记）"""
        # 确保临时文本被提交（即使用户没按 Enter）
        self.canvas._finish_text_editing()
        
        # 使用物理像素尺寸创建结果图
        pixmap_size = self.canvas.original_pixmap.size()
        result = QPixmap(pixmap_size)
        result.setDevicePixelRatio(1.0)  # 确保输出图片 DPR 为 1
        
        painter = QPainter(result)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # 绘制原图到整个结果区域（忽略原图的 DPR）
        painter.drawPixmap(result.rect(), self.canvas.original_pixmap, self.canvas.original_pixmap.rect())
        
        # 标记是在逻辑坐标系绘制的，需要缩放到物理坐标
        dpr = self.canvas._device_pixel_ratio
        painter.scale(dpr, dpr)
        for mark in self.canvas.marks:
            mark.draw(painter)
        painter.end()
        return result
    
    def _render_final_image_with_annotations(self) -> QPixmap:
        """渲染最终图片 + 序号注释栏（文字与附加图片）"""
        base_image = self._render_final_image()
        
        annotations = self.annotation_panel.get_annotations()
        images = self.annotation_panel.get_annotation_images()
        
        if not self.annotation_panel.has_annotations():
            return base_image
        
        all_numbers = sorted(set(annotations.keys()) | set(images.keys()))
        if not all_numbers:
            return base_image
        
        panel_width = 260
        padding = 16
        title_height = 40
        circle_size = 22
        text_left_margin = 8
        # 仅作用于导出图：条目卡片内边距与间距（不动编辑器侧栏 UI）
        card_h_pad = 12
        card_w_pad = 12
        card_gap = 14
        card_radius = 8
        img_below_text_gap = 10
        
        inner_list_w = panel_width - padding * 2
        text_width = inner_list_w - 2 * card_w_pad - circle_size - text_left_margin
        
        item_font = QFont(FONT_NAME, 12)
        item_fm = QFontMetrics(item_font)
        
        item_text_heights: dict[int, int] = {}
        item_total_heights: dict[int, int] = {}
        item_scaled_images: dict[int, QPixmap] = {}
        
        for number in all_numbers:
            raw = (annotations.get(number) or "").strip()
            wrap_text = raw if raw else " "
            rect = item_fm.boundingRect(
                0, 0, text_width, 10000,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap,
                wrap_text
            )
            text_block_h = max(circle_size, rect.height())
            item_text_heights[number] = text_block_h
            
            pm = images.get(number)
            img_extra = 0
            if pm is not None and not pm.isNull():
                scaled = pm.scaled(
                    text_width, 200,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                item_scaled_images[number] = scaled
                img_extra = img_below_text_gap + scaled.height()
            else:
                item_scaled_images[number] = QPixmap()
            
            item_total_heights[number] = text_block_h + img_extra
        
        card_outer_heights = [item_total_heights[n] + 2 * card_h_pad for n in all_numbers]
        total_items_height = sum(card_outer_heights) + card_gap * max(0, len(all_numbers) - 1)
        panel_content_height = title_height + padding + total_items_height + padding
        panel_height = max(base_image.height(), panel_content_height)
        
        total_width = base_image.width() + panel_width
        result = QPixmap(total_width, panel_height)
        result.fill(QColor(255, 255, 255))
        
        painter = QPainter(result)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        
        painter.drawPixmap(0, 0, base_image)
        
        panel_x = base_image.width()
        painter.fillRect(panel_x, 0, panel_width, panel_height, QColor(248, 249, 250))
        
        title_font = QFont(FONT_NAME, 13)
        title_font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(title_font)
        painter.setPen(QColor(51, 51, 51))
        painter.drawText(panel_x + padding, padding, panel_width - padding * 2, 20,
                        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "序号注释")
        
        separator_y = padding + 24
        painter.setPen(QColor(224, 224, 224))
        painter.drawLine(panel_x + padding, separator_y, panel_x + panel_width - padding, separator_y)
        
        y_offset = title_height + padding
        card_border_light = QColor(235, 238, 243)
        card_fill = QColor(255, 255, 255)
        
        for number in all_numbers:
            text_block_h = item_text_heights[number]
            card_h = item_total_heights[number] + 2 * card_h_pad
            raw = (annotations.get(number) or "").strip()
            draw_text = raw if raw else " "
            
            card_x = panel_x + padding
            card_w = inner_list_w
            card_rect = QRect(card_x, y_offset, card_w, card_h)
            
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(0, 0, 0, 10))
            painter.drawRoundedRect(card_rect.adjusted(0, 1, 0, 1), card_radius, card_radius)
            
            painter.setBrush(card_fill)
            painter.setPen(QPen(card_border_light, 1))
            painter.drawRoundedRect(card_rect, card_radius, card_radius)
            
            circle_x = card_x + card_w_pad
            circle_y = y_offset + card_h_pad
            painter.setBrush(QColor(255, 50, 50))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(circle_x, circle_y, circle_size, circle_size)
            
            painter.setPen(QColor(255, 255, 255))
            number_font = QFont(FONT_NAME, 10)
            number_font.setWeight(QFont.Weight.Bold)
            painter.setFont(number_font)
            painter.drawText(circle_x, circle_y, circle_size, circle_size,
                           Qt.AlignmentFlag.AlignCenter, str(number))
            
            painter.setPen(QColor(51, 51, 51))
            painter.setFont(item_font)
            text_x = circle_x + circle_size + text_left_margin
            text_rect = QRect(text_x, circle_y, text_width, text_block_h)
            painter.drawText(text_rect,
                           Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap,
                           draw_text)
            
            scaled = item_scaled_images.get(number)
            if scaled is not None and not scaled.isNull():
                painter.drawPixmap(text_x, circle_y + text_block_h + img_below_text_gap, scaled)
            
            y_offset += card_h
            if number != all_numbers[-1]:
                y_offset += card_gap
        
        painter.end()
        return result
    
    def _save_image(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self, "保存图片", "annotated_image.png", "Images (*.png *.jpg)"
        )
        if file_path:
            final_pixmap = self._render_final_image_with_annotations()
            final_pixmap.save(file_path)
    
    def _copy_image(self):
        final_pixmap = self._render_final_image_with_annotations()
        QGuiApplication.clipboard().setPixmap(final_pixmap)
        self._copied = True  # 标记已复制
        self._marks_count_at_copy = len(self.canvas.marks)  # 记录复制时的标记数
        self.setWindowTitle("Artco 编辑器 - 已复制到剪贴板！")
        # 使用 weakref 避免窗口已删除后回调报错
        self._title_timer = QTimer()
        self._title_timer.setSingleShot(True)
        self._title_timer.timeout.connect(self._restore_title)
        self._title_timer.start(2000)
    
    def _restore_title(self):
        """恢复窗口标题（定时器回调）"""
        if self.isVisible():
            self.setWindowTitle("Artco 编辑器")
    
    def _ai_analyze(self):
        btn = self.toolbar.findChild(QPushButton, "action_btn")
        if btn:
            pos = btn.mapToGlobal(QPoint(btn.width(), 0))
        else:
            pos = QCursor.pos()
        self.prompt_menu.exec(pos)
    
    def _open_prompt_editor(self):
        self.prompt_settings_window = SettingsDialog(self)
        self.prompt_settings_window.show_tab('prompt')
        self.prompt_settings_window.show()
    
    def _do_ai_analyze(self, prompt: str = None, prompt_type: str = "text"):
        """执行 AI 分析 - 通过胶囊显示结果"""
        final_pixmap = self._render_final_image()
        
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        final_pixmap.save(buffer, "PNG")
        base64_data = base64.b64encode(buffer.data().data()).decode()
        buffer.close()
        
        # 调用胶囊进行 AI 处理
        app = QApplication.instance()
        if hasattr(app, '_capsule_widget') and app._capsule_widget:
            capsule = app._capsule_widget
            capsule.reveal(animated=True)
            capsule.start_ai_processing(base64_data, prompt, prompt_type)

    
    def _archive_record(self):
        final_pixmap = self._render_final_image()
        
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        final_pixmap.save(buffer, "JPEG", 85)  # 使用 JPEG 加速
        image_data = buffer.data().data()
        buffer.close()
        
        # 从胶囊获取 AI 结果文本
        ai_text = ""
        app = QApplication.instance()
        if hasattr(app, '_capsule_widget') and app._capsule_widget:
            capsule = app._capsule_widget
            if hasattr(capsule, 'ai_result_text'):
                ai_text = capsule.ai_result_text or ""
        
        try:
            add_record(image_data, ai_text)
            
            # 立即更新按钮样式给用户反馈
            self.toolbar.btn_archive.setIcon(qta.icon('mdi6.check', color='#4caf50'))
            self.toolbar.btn_archive.setStyleSheet("""
                QPushButton#btn_archive {
                    background-color: rgba(46, 125, 50, 0.3);
                }
            """)
            self.setWindowTitle("Artco 编辑器 - ✓ 已归档")
            
            # 缩短等待时间
            QTimer.singleShot(400, self._close_after_archive)
            
        except Exception as e:
            QMessageBox.warning(self, "归档失败", f"保存记录时出错：{e}")
    
    def _assign_feedback(self):
        """打开分配反馈对话框"""
        final_pixmap = self._render_final_image()
        
        from ui.feedback_dialog import FeedbackDialog
        dialog = FeedbackDialog(final_pixmap, self)
        dialog.feedback_sent.connect(self._on_feedback_sent)
        dialog.exec()
    
    def _on_feedback_sent(self, target_type: str, target_id: str, note: str):
        """反馈发送完成"""
        if target_type == "clipboard":
            self.setWindowTitle("Artco 编辑器 - ✓ 已复制到剪贴板")
            QTimer.singleShot(1500, lambda: self.setWindowTitle("Artco 编辑器"))
    
    def _close_after_archive(self):
        self.canvas.marks.clear()
        self.close()
    
    def closeEvent(self, event):
        # 判断是否需要弹出确认对话框
        need_confirm = False
        if self.canvas.marks:
            if getattr(self, '_copied', False):
                # 已复制：只有标记数量增加时才需要确认
                current_count = len(self.canvas.marks)
                copied_count = getattr(self, '_marks_count_at_copy', 0)
                if current_count > copied_count:
                    need_confirm = True
            else:
                # 未复制：有标记就需要确认
                need_confirm = True
        
        if need_confirm:
            reply = QMessageBox.question(
                self, "确认退出",
                "您的标注尚未保存，确定要退出吗？",
                QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Ok,
                QMessageBox.StandardButton.Cancel
            )
            if reply == QMessageBox.StandardButton.Cancel:
                event.ignore()
                return
        # 停止标题恢复定时器
        if hasattr(self, '_title_timer') and self._title_timer.isActive():
            self._title_timer.stop()
        if hasattr(self.toolbar, '_color_bubble') and self.toolbar._color_bubble:
            self.toolbar._color_bubble.hide()
            self.toolbar._color_bubble.deleteLater()
            self.toolbar._color_bubble = None
        event.accept()
    
    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Escape:
            event.ignore()
            return
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.canvas.delete_selected()
            return
        # Ctrl+Z 撤销
        if event.key() == Qt.Key.Key_Z and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.canvas.undo()
            return
        super().keyPressEvent(event)
