# -*- mode: python ; coding: utf-8 -*-
"""
Artco 正式版 PyInstaller spec 文件
生成单文件 exe（Artco.exe），便携模式
"""

import os
import sys

block_cipher = None

SPEC_DIR = os.path.abspath(SPECPATH)


def collect_package_modules(pkg_name):
    """自动收集包内所有非私有 .py 模块，避免新增文件时漏配 hiddenimports。"""
    mods = [pkg_name]
    pkg_dir = os.path.join(SPEC_DIR, pkg_name)
    for filename in sorted(os.listdir(pkg_dir)):
        if filename.endswith('.py') and not filename.startswith('_'):
            mods.append('{}.{}'.format(pkg_name, filename[:-3]))
    return mods

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
    # 项目内部模块（自动扫描 ui/ 与 screenshot/ 目录，新增文件无需改这里）
    'config',
    'database',
    'utils',
    'version',
    'updater',
] + collect_package_modules('screenshot') + collect_package_modules('ui')

a = Analysis(
    ['main.py'],
    pathex=[os.path.abspath('.')],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['rthook_qt_api.py'],
    excludes=[
        # 以下大包项目代码未使用，但环境中已安装，必须排除以防 exe 膨胀
        'torch',           # ~750MB，AI 训练框架，项目未使用
        'torchvision',     # ~50MB，torch 配套，项目未使用
        'scipy',           # ~120MB，科学计算，项目未使用
        'scikit_image',    # ~100MB，图像处理，项目未使用
        'skimage',         # scikit-image 的模块名
        'cv2',             # ~60MB，opencv，项目未使用
        'opencv',          # opencv 的包名
        'matplotlib',      # ~150MB，绘图库，项目未使用
        'pandas',          # ~150MB，数据处理，项目未使用
        'IPython',         # ~50MB，交互式 shell
        'jupyter',         # ~50MB，notebook
        'notebook',        # jupyter notebook
        'pytest',          # 测试框架
        'sphinx',          # 文档生成
        'tkinter',         # Tk GUI，项目用 Qt
        'PyQt5',           # 项目用 PySide6
        'PyQt6',           # 项目用 PySide6
        'PyQt6.QtWidgets', # 防止误打包
        'PyQt6.QtCore',    # 防止误打包
        'PyQt6.QtGui',     # 防止误打包
        # Qt 重量级模块：项目纯 QWidget/QPainter 实现，以下均未使用，体积合计约 29MB
        'PySide6.QtQml',              # Qt6Qml.dll 5.01MB
        'PySide6.QtQuick',            # Qt6Quick.dll 5.99MB
        'PySide6.QtQmlModels',        # Qt6QmlModels.dll 0.71MB
        'PySide6.QtOpenGL',           # QtOpenGL.pyd 8.46MB
        'PySide6.QtOpenGLWidgets',
        'PySide6.QtPdf',              # Qt6Pdf.dll 5.09MB
        'PySide6.QtPdfWidgets',
        'PySide6.QtDataVisualization',# Qt6DataVisualization.dll 1.15MB
    ],
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# 剔除未使用的 Qt 重量级 DLL：项目纯 QWidget/QPainter 实现，不需要 QML/Quick/PDF/OpenGL。
# 注意：excludes 只能挡住 Python 模块，挡不住 PySide6 hook 收集的 C++ DLL，故此处在打包前过滤。
_EXCLUDE_BIN_SUFFIXES = (
    'opengl32sw.dll',           # 19.68MB Mesa 软件 OpenGL 兜底
    'Qt6Qml.dll',               # 5.01MB
    'Qt6QmlMeta.dll',           # 0.14MB
    'Qt6QmlModels.dll',         # 0.71MB
    'Qt6QmlWorkerScript.dll',   # 0.07MB
    'Qt6Quick.dll',             # 5.99MB
    'Qt6Pdf.dll',               # 5.09MB
    'Qt6OpenGL.dll',            # 1.88MB
)
_suffixes = tuple(s.lower() for s in _EXCLUDE_BIN_SUFFIXES)
_dropped = [e[0] for e in a.binaries if e[0].lower().endswith(_suffixes)]
a.binaries = [e for e in a.binaries if not e[0].lower().endswith(_suffixes)]
print('[Artco.spec] 剔除未使用 Qt DLL: {}'.format(_dropped))

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
