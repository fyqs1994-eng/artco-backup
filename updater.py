"""
Artco 自动更新模块
负责：检查新版本 → 下载 → SHA256 校验 → 启动外部 Updater → 退出主程序
"""

import os
import sys
import json
import hashlib
import tempfile
import subprocess
import shutil

from version import APP_VERSION, APP_NAME

# ── 远程版本清单 URL ──────────────────────────────────────
# 使用 GitHub raw 文件，发版时更新 releases/latest.json
UPDATE_MANIFEST_URL = (
    "https://raw.githubusercontent.com/fyqs1994-eng/Artco-backup/main/releases/latest.json"
)

# ── 更新检查间隔（秒）──
# 静默检查间隔：6 小时，避免频繁请求
CHECK_INTERVAL_SECONDS = 6 * 60 * 60

# ── 跳过版本记录文件 ──
def _get_skip_file():
    """获取跳过版本记录文件路径"""
    try:
        from config import get_app_dir
        return os.path.join(get_app_dir(), ".update_skip")
    except Exception:
        return os.path.join(os.path.dirname(sys.executable if getattr(sys, 'frozen', False) else __file__), ".update_skip")


def _compare_versions(v1: str, v2: str) -> int:
    """比较两个语义化版本号
    返回: 1 if v1>v2, -1 if v1<v2, 0 if equal
    """
    try:
        parts1 = [int(x) for x in v1.split(".")]
        parts2 = [int(x) for x in v2.split(".")]
    except ValueError:
        return 0
    # 补齐长度
    max_len = max(len(parts1), len(parts2))
    parts1 += [0] * (max_len - len(parts1))
    parts2 += [0] * (max_len - len(parts2))
    for a, b in zip(parts1, parts2):
        if a > b:
            return 1
        if a < b:
            return -1
    return 0


def _get_last_check_time() -> float:
    """获取上次检查时间"""
    try:
        from config import get_app_dir
        ts_file = os.path.join(get_app_dir(), ".update_lastcheck")
        if os.path.exists(ts_file):
            with open(ts_file, "r") as f:
                return float(f.read().strip())
    except Exception:
        pass
    return 0.0


def _save_check_time():
    """保存当前检查时间"""
    try:
        import time
        from config import get_app_dir
        ts_file = os.path.join(get_app_dir(), ".update_lastcheck")
        with open(ts_file, "w") as f:
            f.write(str(time.time()))
    except Exception:
        pass


def _get_skipped_version() -> str:
    """获取用户跳过的版本号"""
    skip_file = _get_skip_file()
    if os.path.exists(skip_file):
        try:
            with open(skip_file, "r") as f:
                return f.read().strip()
        except Exception:
            pass
    return ""


def skip_version(version: str):
    """记录用户跳过的版本"""
    skip_file = _get_skip_file()
    try:
        with open(skip_file, "w") as f:
            f.write(version)
    except Exception:
        pass


def should_check_silently() -> bool:
    """判断是否应该进行静默检查（距上次检查超过间隔时间）"""
    import time
    last = _get_last_check_time()
    if last == 0:
        return True
    return (time.time() - last) > CHECK_INTERVAL_SECONDS


def check_for_update(timeout: int = 10) -> tuple:
    """检查是否有新版本
    返回: (has_update: bool, update_info: dict | None)
    update_info 包含: version, url, changelog, sha256, min_required, release_date
    """
    try:
        import requests
        resp = requests.get(UPDATE_MANIFEST_URL, timeout=(5, timeout))
        if resp.status_code != 200:
            return False, None
        info = resp.json()

        remote_version = info.get("version", "0.0.0")
        if _compare_versions(remote_version, APP_VERSION) <= 0:
            # 远程版本不高于当前版本
            return False, None

        # 检查是否被用户跳过
        skipped = _get_skipped_version()
        if skipped == remote_version:
            return False, None

        # 检查最低兼容版本
        min_required = info.get("min_required", "0.0.0")
        if _compare_versions(APP_VERSION, min_required) < 0:
            # 当前版本太低，不允许直接更新（需要重新下载完整安装）
            return False, None

        return True, info
    except Exception:
        return False, None


def _compute_sha256(file_path: str) -> str:
    """计算文件的 SHA256 哈希"""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def download_update(update_info: dict, progress_callback=None) -> str:
    """下载新版本到临时目录
    progress_callback: 可选回调，参数为 0.0~1.0 的进度比例
    返回: 下载的文件路径
    异常: 下载失败或校验失败时抛出
    """
    import requests

    url = update_info.get("url")
    if not url:
        raise ValueError("更新信息中缺少下载 URL")

    temp_dir = tempfile.mkdtemp(prefix="artco_update_")
    target_path = os.path.join(temp_dir, "Artco_new.exe")

    resp = requests.get(url, stream=True, timeout=60)
    if resp.status_code != 200:
        raise RuntimeError(f"下载失败，HTTP {resp.status_code}")

    total = int(resp.headers.get("content-length", 0))
    downloaded = 0

    with open(target_path, "wb") as f:
        for chunk in resp.iter_content(8192):
            f.write(chunk)
            downloaded += len(chunk)
            if progress_callback and total > 0:
                progress_callback(downloaded / total)

    # SHA256 校验
    expected_sha = update_info.get("sha256", "")
    if expected_sha:
        actual_sha = _compute_sha256(target_path)
        if actual_sha.lower() != expected_sha.lower():
            os.remove(target_path)
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise ValueError("文件校验失败：SHA256 不匹配")

    return target_path


def _get_updater_exe_path() -> str:
    """获取 ArtcoUpdater.exe 路径
    打包后从 _MEIPASS 释放到临时目录；
    开发环境直接使用同目录的 ArtcoUpdater.exe
    """
    if getattr(sys, 'frozen', False):
        # PyInstaller 打包后：从 _MEIPASS 提取 Updater 到临时目录
        bundle_dir = sys._MEIPASS
        bundled_updater = os.path.join(bundle_dir, "ArtcoUpdater.exe")
        if os.path.exists(bundled_updater):
            # 复制到临时目录（因为 _MEIPASS 会在退出时清理）
            temp_updater = os.path.join(tempfile.gettempdir(), "ArtcoUpdater.exe")
            try:
                shutil.copy2(bundled_updater, temp_updater)
                return temp_updater
            except Exception:
                return bundled_updater
    else:
        # 开发环境
        dev_updater = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ArtcoUpdater.exe")
        if os.path.exists(dev_updater):
            return dev_updater

    raise FileNotFoundError("ArtcoUpdater.exe 未找到，请确保已正确打包")


def apply_update(new_exe_path: str):
    """启动外部 Updater 进行替换，然后退出主程序
    此函数调用后主程序应立即退出
    """
    updater_path = _get_updater_exe_path()
    current_exe = sys.executable  # PyInstaller 打包后是 exe 路径

    # 启动 Updater，传入参数
    subprocess.Popen([
        updater_path,
        "--new-exe", new_exe_path,
        "--target", current_exe,
        "--relaunch", current_exe,
    ], creationflags=subprocess.CREATE_NO_WINDOW)

    # 主程序退出
    sys.exit(0)


def do_full_update(update_info: dict, progress_callback=None):
    """完整更新流程：下载 + 校验 + 启动 Updater + 退出
    供 UI 调用，调用后程序会退出
    """
    new_path = download_update(update_info, progress_callback)
    apply_update(new_path)
