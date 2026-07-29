"""
ArtcoUpdater — 独立更新替换程序
由主程序在下载完成后启动，负责：
1. 等待主程序退出
2. 备份旧 exe
3. 覆盖写入新 exe
4. 启动新版本
5. 清理临时文件 + 自删除

打包为 ArtcoUpdater.exe，内嵌在主程序中运行时释放到临时目录。
仅需 Python 标准库，体积约 5-6 MB。
"""

import sys
import os
import time
import shutil
import subprocess
import argparse


def main():
    parser = argparse.ArgumentParser(description="Artco Auto Updater")
    parser.add_argument("--new-exe", required=True, help="下载的新 exe 路径")
    parser.add_argument("--target", required=True, help="要替换的旧 exe 路径")
    parser.add_argument("--relaunch", required=True, help="替换完成后要启动的 exe 路径")
    args = parser.parse_args()

    target_dir = os.path.dirname(args.target)
    bak_path = args.target + ".bak"

    # ── 1. 等待主程序退出（最多等 30 秒）──
    # 尝试 rename 旧 exe，如果成功说明文件已释放（主程序已退出）
    renamed = False
    for _ in range(30):
        try:
            os.rename(args.target, bak_path)
            renamed = True
            break
        except PermissionError:
            time.sleep(1)
        except FileNotFoundError:
            # 旧文件不存在，可能是首次安装，直接跳过备份
            renamed = True
            bak_path = None
            break

    if not renamed:
        print("[Updater] 主程序未能退出，更新中止")
        # 写入失败标记文件，主程序下次启动时可检测
        fail_flag = os.path.join(target_dir, ".artco_update_failed")
        try:
            with open(fail_flag, "w") as f:
                f.write("timeout")
        except Exception:
            pass
        sys.exit(1)

    # ── 2. 覆盖写入新 exe ──
    try:
        shutil.copy2(args.new_exe, args.target)
    except Exception as e:
        print(f"[Updater] 覆盖失败: {e}")
        # 恢复备份
        if bak_path and os.path.exists(bak_path):
            try:
                shutil.copy2(bak_path, args.target)
            except Exception:
                pass
        sys.exit(1)

    # ── 3. 启动新版本 ──
    try:
        subprocess.Popen([args.relaunch])
    except Exception as e:
        print(f"[Updater] 启动新版本失败: {e}")

    # ── 4. 清理临时文件 ──
    try:
        if bak_path and os.path.exists(bak_path):
            os.remove(bak_path)
        # 清理下载目录
        new_exe_dir = os.path.dirname(args.new_exe)
        if new_exe_dir and os.path.isdir(new_exe_dir) and "artco_update" in new_exe_dir:
            shutil.rmtree(new_exe_dir, ignore_errors=True)
    except Exception:
        pass

    # ── 5. 自删除 ──
    # Updater 自身在临时目录，直接删除
    try:
        self_path = sys.executable
        if os.path.exists(self_path):
            # 使用 bat 脚本延迟自删除（确保进程已退出）
            bat_path = os.path.join(os.path.dirname(self_path), "_self_delete.bat")
            with open(bat_path, "w") as f:
                f.write(f'@echo off\nping 127.0.0.1 -n 2 >nul\ndel "{self_path}"\ndel "{bat_path}"\n')
            subprocess.Popen(["cmd", "/c", bat_path], creationflags=subprocess.CREATE_NO_WINDOW)
    except Exception:
        pass


if __name__ == "__main__":
    main()
