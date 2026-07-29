# -*- mode: python ; coding: utf-8 -*-
"""
Artco 脱敏版 PyInstaller spec 文件
与正式版相同，但 ai_config.json 使用空 API Key 版本
build.bat 会自动将 ai_config_empty.json 复制为 ai_config.json 后调用此 spec
"""

import os
import sys

block_cipher = None

datas = [
    ('icon', 'icon'),
    ('ui/resources', 'ui/resources'),
    ('ai_config_empty.json', '.'),
]

hiddenimports = [
    'PySide6.QtWidgets',
    'PySide6.QtCore',
    'PySide6.QtGui',
    'PySide6.QtSvg',
    'PySide6.QtSvgWidgets',
    'qtawesome',
    'qfluentwidgets',
    'qfluentwidgets.icons',
    'google.genai',
    'winsdk',
    'winsdk.windows.media.ocr',
    'winsdk.windows.globalization',
    'winsdk.windows.graphics.imaging',
    'winsdk.windows.storage.streams',
    'pynput',
    'pynput.keyboard',
    'pynput.mouse',
    'psd_tools',
    'dotenv',
    'config',
    'database',
    'utils',
    'screenshot',
    'screenshot.marks',
    'screenshot.canvas',
    'screenshot.toolbar',
    'screenshot.editor',
    'screenshot.overlay',
    'screenshot.pin',
    'screenshot.ocr',
    'screenshot.cache',
    'screenshot.utils',
    'screenshot.window_detect',
    'ui',
    'ui.ai_worker',
    'ui.ai_result',
    'ui.archive',
    'ui.assign_panel',
    'ui.clipboard_float',
    'ui.feedback_dialog',
    'ui.image_viewer',
    'ui.prompt_manager',
    'ui.settings',
    'ui.sidebar',
    'ui.theme',
    'ui.workbench',
]

a = Analysis(
    ['main.py'],
    pathex=[os.path.abspath('.')],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['rthook_qt_api.py'],
    excludes=[],
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='Artco_Lite',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icon/artco.ico',
)
