# -*- mode: python ; coding: utf-8 -*-

import os

block_cipher = None

a = Analysis(
    ['viewer_main.py'],
    pathex=[os.path.abspath('.')],
    binaries=[],
    datas=[
        ('ui/resources', 'ui/resources'),
        ('icon', 'icon'),
    ],
    hiddenimports=[
        'PySide6.QtWidgets',
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtSvg',
        'qtawesome',
        'qfluentwidgets',
        'psd_tools',
        'PIL',
        'config',
        'database',
        'utils',
        'ui.image_viewer',
        'ui.theme',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['rthook_qt_api.py'],
    excludes=[],
    noarchive=False,
    optimize=0,
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
    name='ArtcoViewer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icon/artco.ico',
)
