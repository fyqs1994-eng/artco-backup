# -*- mode: python ; coding: utf-8 -*-
"""
ArtcoUpdater 打包配置
生成单文件 ArtcoUpdater.exe，仅使用标准库，体积约 5-6 MB
"""

import os

block_cipher = None

a = Analysis(
    ['updater_main.py'],
    pathex=[os.path.abspath('.')],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'PySide6', 'qtawesome', 'qfluentwidgets', 'google',
        'pynput', 'psd_tools', 'winsdk',
    ],
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
    name='ArtcoUpdater',
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
)
