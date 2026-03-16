"""
Artco Viewer - 独立图片浏览器入口
可作为 Windows 默认图片查看器

设计目标：
- `main.py` 负责“常驻后台 + 快捷键截图”（无需专门入口）
- `viewer_main.py` 负责“系统级默认看图”（双击图片直接打开）

额外能力：
- 提供 `--register` 用于把 ArtcoViewer 注册到 Windows “打开方式”列表
  （注意：Windows 10/11 通常不允许程序静默强行设置默认应用，只能注册后让用户在系统设置里选择。）
"""

import sys
import os
from pathlib import Path
from typing import Optional, List

# 设置 Qt API 为 PySide6（必须在导入 qtawesome / qfluentwidgets 之前）
os.environ.setdefault('QT_API', 'pyside6')

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import Qt


def _open_default_apps_settings():
    """打开 Windows 默认应用设置页。"""
    try:
        # Windows 10/11
        os.startfile("ms-settings:defaultapps")
    except Exception:
        try:
            os.startfile("ms-settings:")
        except Exception:
            pass


def _notify_association_changed():
    """通知系统文件关联已变化，让资源管理器刷新缓存。"""
    try:
        import ctypes

        SHCNE_ASSOCCHANGED = 0x08000000
        SHCNF_IDLIST = 0x0000
        ctypes.windll.shell32.SHChangeNotify(SHCNE_ASSOCCHANGED, SHCNF_IDLIST, None, None)
    except Exception:
        pass


def _register_openwith(exe_path: Path, exts: List[str]) -> Optional[str]:
    """注册到 Windows“打开方式”列表。

    返回：错误信息（None 表示成功）。
    """
    if sys.platform != 'win32':
        return "仅支持 Windows 系统注册文件关联"

    try:
        import winreg

        exe_path = exe_path.resolve()
        exe_name = exe_path.name
        prog_id = "ArtcoViewer.Image"

        def set_value(root, sub_key: str, name: str, value, reg_type=winreg.REG_SZ):
            with winreg.CreateKeyEx(root, sub_key, 0, winreg.KEY_SET_VALUE) as k:
                winreg.SetValueEx(k, name, 0, reg_type, value)

        # 1) ProgID（供 OpenWithProgids 使用）
        set_value(winreg.HKEY_CURRENT_USER, rf"Software\Classes\{prog_id}", "", "Artco Viewer Image")
        set_value(
            winreg.HKEY_CURRENT_USER,
            rf"Software\Classes\{prog_id}\shell\open\command",
            "",
            f'"{exe_path}" "%1"'
        )
        set_value(
            winreg.HKEY_CURRENT_USER,
            rf"Software\Classes\{prog_id}\DefaultIcon",
            "",
            f'"{exe_path}",0'
        )

        # 2) Applications\xxx.exe（让“打开方式”里能看到）
        set_value(
            winreg.HKEY_CURRENT_USER,
            rf"Software\Classes\Applications\{exe_name}\shell\open\command",
            "",
            f'"{exe_path}" "%1"'
        )
        set_value(
            winreg.HKEY_CURRENT_USER,
            rf"Software\Classes\Applications\{exe_name}",
            "FriendlyAppName",
            "Artco Viewer"
        )

        # 3) 扩展名 -> OpenWithProgids / OpenWithList
        for ext in exts:
            ext = (ext or "").strip().lower()
            if not ext:
                continue
            if not ext.startswith('.'):
                ext = '.' + ext

            # 3.1 OpenWithProgids
            with winreg.CreateKeyEx(
                winreg.HKEY_CURRENT_USER,
                rf"Software\Classes\{ext}\OpenWithProgids",
                0,
                winreg.KEY_SET_VALUE
            ) as k:
                # REG_NONE：存在即可
                winreg.SetValueEx(k, prog_id, 0, winreg.REG_NONE, b"")

            # 3.2 OpenWithList
            with winreg.CreateKeyEx(
                winreg.HKEY_CURRENT_USER,
                rf"Software\Classes\{ext}\OpenWithList\{exe_name}",
                0,
                winreg.KEY_SET_VALUE
            ) as _:
                pass

        _notify_association_changed()
        return None

    except Exception as e:
        return str(e)


def main():
    """Viewer 主入口。

    用法：
    - `ArtcoViewer.exe <image_path>`：打开图片
    - `ArtcoViewer.exe`：空启动
    - `ArtcoViewer.exe --register`：注册到“打开方式”列表（之后用户可在系统设置里设为默认）
    """
    import argparse

    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("image", nargs="?", help="image path")
    parser.add_argument("--register", action="store_true", help="register open-with handler")
    parser.add_argument("--open-settings", action="store_true", help="open default apps settings")
    args, _ = parser.parse_known_args()

    # 高DPI支持
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("Artco Viewer")

    if args.register:
        if not getattr(sys, 'frozen', False):
            QMessageBox.information(
                None,
                "文件关联",
                "开发环境不建议注册文件关联。\n\n请先用 PyInstaller 打包生成 ArtcoViewer.exe 后，再运行：\nArtcoViewer.exe --register"
            )
            if args.open_settings:
                _open_default_apps_settings()
            return 0

        exe_path = Path(sys.executable)
        default_exts = [".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tif", ".tiff", ".ico"]
        err = _register_openwith(exe_path, default_exts)
        if err:
            QMessageBox.warning(None, "文件关联注册失败", f"注册失败：\n{err}")
            return 1

        QMessageBox.information(
            None,
            "文件关联已注册",
            "已把 Artco Viewer 注册到 Windows 的“打开方式”列表。\n\n"
            "接下来如需设置为默认看图：\n"
            "1）打开【设置】→【应用】→【默认应用】\n"
            "2）按文件类型（.png/.jpg 等）选择 Artco Viewer\n\n"
            "提示：Windows 10/11 通常不允许程序静默强行设置默认应用，只能由用户在系统设置里确认。"
        )
        if args.open_settings:
            _open_default_apps_settings()
        return 0

    from ui.image_viewer import ImageViewer
    from database import init_database
    
    # 确保数据库已初始化（sidebar 中的部分功能可能需要）
    init_database()

    image_path = args.image
    viewer = ImageViewer(image_path)
    viewer.closed.connect(app.quit)
    viewer.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())

