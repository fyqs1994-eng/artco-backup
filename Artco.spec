# -*- mode: python ; coding: utf-8 -*-
"""
Artco 正式版 PyInstaller spec 文件
生成单文件 exe（Artco.exe），便携模式
"""

import os
import sys

block_cipher = None

# 收集所有需要打包的数据文件
datas = [
    # 图标资源
    ('icon', 'icon'),
    # UI SVG 资源
    ('ui/resources', 'ui/resources'),
    # 默认配置文件模板（首次运行时复制到 exe 同目录）
    ('ai_config_empty.json', '.'),
    # 内嵌 ArtcoUpdater.exe（自动更新用）
    ('dist/ArtcoUpdater.exe', '.'),
]

# 确保所有 .py 模块都被收集
hiddenimports = [
    'PySide6.QtWidgets',
    'PySide6.QtCore',
    'PySide6.QtGui',
    'PySide6.QtSvg',
    'PySide6.QtSvgWidgets',
    'qtawesome',
    'qfluentwidgets',
    'qfluentwidgets.icons',
    # AI 依赖
    'google.genai',
    # WinRT OCR
    'winsdk',
    'winsdk.windows.media.ocr',
    'winsdk.windows.globalization',
    'winsdk.windows.graphics.imaging',
    'winsdk.windows.storage.streams',
    # 其他依赖
    'pynput',
    'pynput.keyboard',
    'pynput.mouse',
    'psd_tools',
    'dotenv',
    # 更新模块依赖
    'requests',
    # 项目内部模块
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
    # 版本和更新模块
    'version',
    'updater',
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
    name='Artco',
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

# viewer_main.py 作为独立入口也可以打包为 ArtcoViewer.exe
# 如需同时打包 viewer，取消下方注释：
# viewer = Analysis(
#     ['viewer_main.py'],
#     pathex=[os.path.abspath('.')],
#     binaries=[],
#     datas=datas,
#     hiddenimports=hiddenimports,
#     hookspath=['rthook_qt_api.py'],
#     hooksconfig={},
#     runtime_hooks=['rthook_qt_api.py'],
#     excludes=[],
#     cipher=block_cipher,
# )
# viewer_pyz = PYZ(viewer.pure, viewer.zipped_data, cipher=block_cipher)
# viewer_exe = EXE(
#     viewer_pyz,
#     viewer.scripts,
#     viewer.binaries,
#     viewer.zipfiles,
#     viewer.datas,
#     [],
#     name='ArtcoViewer',
#     ...
# )
