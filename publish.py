"""
Artco 发布脚本 —— 打包 → 创建 GitHub Release → 上传 exe → 同步 latest.json

用法（PowerShell）：
    python publish.py                 # 完整流程：升版本+打包+上传+同步清单
    python publish.py --check-only    # 只做上线前体检，不上传

设计要点：
1. **凭据绝不硬编码**。优先调用 `git credential fill` 复用本机已保存的
   GitHub 凭据（也就是 git push 用的那个），取不到再回退环境变量
   GITHUB_TOKEN，最后才交互式询问（输入不回显）。
2. **上传前先体检**。若 latest.json 已指向某版本而 Releases 上没有对应资产，
   会导致老客户端「看到更新却下载 404」，因此发布前后都会校验下载链接。
3. **sha256 与体积取自真实产物**，不手填，避免清单与实际文件不符。
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SPEC_NAME = "Artco.spec"
EXE_NAME = "Artco.exe"
DIST_EXE = ROOT / "dist" / EXE_NAME
LATEST_JSON = ROOT / "releases" / "latest.json"
VERSION_PY = ROOT / "version.py"

REPO = "fyqs1994-eng/artco-backup"
GITHUB_API = "https://api.github.com"
GITHUB_UPLOAD = "https://uploads.github.com"


class PublishError(Exception):
    """发布流程中的可预期错误（直接展示给用户，不打堆栈）"""


# ──────────────────────────────────────────────
#  凭据获取
# ──────────────────────────────────────────────

def get_github_token() -> str:
    """按优先级获取 GitHub token，全程不落盘、不打印

    顺序：git credential（复用 push 凭据）→ GITHUB_TOKEN 环境变量 → 交互输入
    """
    # 1) 复用本机 git 凭据
    try:
        proc = subprocess.run(
            ["git", "credential", "fill"],
            input="protocol=https\nhost=github.com\n\n",
            capture_output=True, text=True, cwd=str(ROOT), timeout=20,
        )
        for line in (proc.stdout or "").splitlines():
            if line.startswith("password="):
                token = line[len("password="):].strip()
                if token:
                    return token
    except Exception:
        pass

    # 2) 环境变量
    env_token = (os.environ.get("GITHUB_TOKEN") or "").strip()
    if env_token:
        return env_token

    # 3) 交互式输入（不回显）
    try:
        import getpass
        print("未找到已保存的 GitHub 凭据。")
        print(f"请到 https://github.com/settings/tokens 生成 token（勾 public_repo）。")
        token = getpass.getpass("GitHub Token（输入不回显）: ").strip()
    except Exception:
        token = input("GitHub Token: ").strip()

    if not token:
        raise PublishError("未提供 GitHub token，无法上传 Release。")
    return token


# ──────────────────────────────────────────────
#  版本与清单
# ──────────────────────────────────────────────

def read_version() -> str:
    """从 version.py 读取当前版本号（全局唯一版本源）"""
    text = VERSION_PY.read_text(encoding="utf-8")
    m = re.search(r'APP_VERSION\s*=\s*["\']([^"\']+)["\']', text)
    if not m:
        raise PublishError(f"无法从 {VERSION_PY} 解析 APP_VERSION")
    return m.group(1).strip()


def bump_version(version: str) -> str:
    """版本号末位 +1，返回新版本字符串"""
    parts = version.split(".")
    try:
        parts[-1] = str(int(parts[-1]) + 1)
    except ValueError:
        raise PublishError(f"版本号末位不是数字，无法自增：{version}")
    return ".".join(parts)


def write_version(new_version: str) -> None:
    """字符级精确替换 version.py 中的版本号"""
    text = VERSION_PY.read_text(encoding="utf-8")
    old = re.search(r'APP_VERSION\s*=\s*["\']([^"\']+)["\']', text)
    if not old:
        raise PublishError("version.py 中未找到 APP_VERSION 赋值")
    new_text = text[:old.start(1)] + new_version + text[old.end(1):]
    VERSION_PY.write_text(new_text, encoding="utf-8")


def sha256_of(path: Path) -> str:
    """计算文件 sha256（大写十六进制）"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def write_latest_json(version: str, sha256: str, changelog: str) -> dict:
    """写入发布清单，返回写入内容"""
    data = {
        "version": version,
        "url": f"https://github.com/{REPO}/releases/download/v{version}/{EXE_NAME}",
        "changelog": changelog,
        "sha256": sha256,
        "min_required": "1.0.0",
        "release_date": time.strftime("%Y-%m-%d"),
    }
    LATEST_JSON.parent.mkdir(parents=True, exist_ok=True)
    LATEST_JSON.write_text(
        json.dumps(data, ensure_ascii=False, indent=4) + "\n", encoding="utf-8"
    )
    return data


# ──────────────────────────────────────────────
#  构建
# ──────────────────────────────────────────────

def build_exe() -> None:
    """调用 PyInstaller 打包"""
    print(f"[build] 开始打包 {SPEC_NAME} ...")
    proc = subprocess.run(
        [sys.executable, "-m", "PyInstaller", SPEC_NAME, "--noconfirm", "--clean"],
        cwd=str(ROOT),
    )
    if proc.returncode != 0:
        raise PublishError("PyInstaller 打包失败，请查看上方输出。")
    if not DIST_EXE.exists():
        raise PublishError(f"打包未产出 {DIST_EXE}")
    size_mb = DIST_EXE.stat().st_size / 1024 / 1024
    print(f"[build] 产物就绪：{DIST_EXE}（{size_mb:.1f} MB）")


# ──────────────────────────────────────────────
#  GitHub API
# ──────────────────────────────────────────────

def _api(method: str, url: str, token: str, json_body=None, raw=None,
         headers_extra=None, timeout=60):
    """统一的 GitHub API 请求"""
    import urllib.request
    import urllib.error

    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "Artco-Publisher",
    }
    if headers_extra:
        headers.update(headers_extra)

    data = None
    if json_body is not None:
        data = json.dumps(json_body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    elif raw is not None:
        data = raw

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return resp.status, (json.loads(body) if body.strip() else {})
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        try:
            return e.code, json.loads(body)
        except Exception:
            return e.code, {"message": body[:300]}


def ensure_release(tag: str, token: str, name: str = None, body: str = ""):
    """确保 Release 存在：优先复用已有的，否则创建"""
    status, data = _api("GET", f"{GITHUB_API}/repos/{REPO}/releases/tags/{tag}", token)
    if status == 200:
        print(f"[release] 复用已存在的 Release：{tag}")
        return data

    payload = {
        "tag_name": tag,
        "name": name or f"Artco {tag}",
        "body": body or f"Artco {tag}",
        "draft": False,
        "prerelease": False,
    }
    status, data = _api("POST", f"{GITHUB_API}/repos/{REPO}/releases", token,
                        json_body=payload)
    if status not in (200, 201):
        raise PublishError(f"创建 Release 失败（HTTP {status}）：{data.get('message')}")
    print(f"[release] 已创建 Release：{tag}")
    return data


def upload_asset(release: dict, file_path: Path, token: str) -> None:
    """上传资产；若同名资产已存在则先删除（避免 422 校验失败）"""
    asset_name = file_path.name
    for asset in release.get("assets", []):
        if asset.get("name") == asset_name:
            print(f"[upload] 发现同名资产，先删除旧文件：{asset_name}")
            _api("DELETE",
                 f"{GITHUB_API}/repos/{REPO}/releases/assets/{asset['id']}", token)

    upload_url = release["upload_url"].split("{")[0]
    url = f"{upload_url}?name={asset_name}"
    raw = file_path.read_bytes()
    print(f"[upload] 上传 {asset_name}（{len(raw)/1024/1024:.1f} MB），请稍候 ...")

    status, data = _api(
        "POST", url, token, raw=raw,
        headers_extra={"Content-Type": "application/octet-stream"},
        timeout=1800,
    )
    if status not in (200, 201):
        raise PublishError(f"上传资产失败（HTTP {status}）：{data.get('message')}")
    print(f"[upload] 上传完成：{asset_name}")


def check_download_url(url: str) -> bool:
    """验证客户端真实的下载链接可访问（HEAD 跟随重定向）"""
    import urllib.request
    import urllib.error

    req = urllib.request.Request(url, method="HEAD",
                                 headers={"User-Agent": "Artco-Publisher"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status == 200
    except urllib.error.HTTPError as e:
        return e.code == 200
    except Exception:
        return False


# ──────────────────────────────────────────────
#  主流程
# ──────────────────────────────────────────────

def cmd_check(args):
    """上线前体检：确认清单版本与 Releases 资产是否匹配"""
    token = get_github_token()
    if not LATEST_JSON.exists():
        raise PublishError(f"未找到 {LATEST_JSON}")
    latest = json.loads(LATEST_JSON.read_text(encoding="utf-8"))
    version = latest.get("version")
    url = latest.get("url")
    print(f"[check] 清单版本：{version}")
    print(f"[check] 下载链接：{url}")

    ok = check_download_url(url)
    if ok:
        print("[check] ✅ 下载链接可访问（HTTP 200）")
    else:
        print("[check] ❌ 下载链接不可访问 —— 老客户端更新会失败！")
        print("[check]    请运行 python publish.py 上传对应资产。")

    status, _ = _api("GET", f"{GITHUB_API}/repos/{REPO}/releases/tags/v{version}", token)
    print(f"[check] Release v{version}：{'存在' if status == 200 else '不存在'}")
    return 0 if ok else 1


def cmd_publish(args):
    # 1) 版本
    current = read_version()
    if args.no_bump:
        version = current
        print(f"[version] 指定不升版，沿用 {version}")
    else:
        version = bump_version(current)
        write_version(version)
        print(f"[version] {current} → {version}")

    # 2) 打包
    if not args.skip_build:
        build_exe()
    if not DIST_EXE.exists():
        raise PublishError(f"未找到产物 {DIST_EXE}，请先打包或去掉 --skip-build")

    # 3) 凭据
    token = get_github_token()

    # 4) 上传
    tag = f"v{version}"
    changelog = args.changelog or f"Artco {version}"
    release = ensure_release(tag, token, name=f"Artco {version}", body=changelog)
    upload_asset(release, DIST_EXE, token)

    # 5) 同步清单（sha256 取自真实产物）
    sha = sha256_of(DIST_EXE)
    data = write_latest_json(version, sha, changelog)
    print(f"[latest] 已同步 {LATEST_JSON.name} → version={version}")
    print(f"[latest] sha256={sha}")

    # 6) 发布后校验：下载链接必须可访问，否则老客户端会 404
    print("[verify] 校验下载链接 ...")
    for _ in range(6):
        if check_download_url(data["url"]):
            print(f"[verify] ✅ {data['url']} 可访问")
            break
        time.sleep(5)
    else:
        raise PublishError(
            "下载链接仍不可访问，请稍后手动运行 python publish.py --check-only 复查。"
        )

    print()
    print("=" * 56)
    print(f" 发布完成：Artco {version}")
    print(f" 产物：{DIST_EXE}（{DIST_EXE.stat().st_size/1024/1024:.1f} MB）")
    print(f" 清单：{LATEST_JSON}")
    print(" 提示：清单已更新，记得 git commit 后再 push。")
    print("=" * 56)
    return 0


def main():
    parser = argparse.ArgumentParser(description="Artco 一键发布到 GitHub Releases")
    parser.add_argument("--check-only", action="store_true",
                        help="只体检：校验清单版本与下载链接，不上传")
    parser.add_argument("--no-bump", action="store_true",
                        help="不自动升版本号（沿用 version.py 当前值）")
    parser.add_argument("--skip-build", action="store_true",
                        help="跳过打包，直接上传现有 dist/Artco.exe")
    parser.add_argument("--changelog", type=str, default=None,
                        help="更新说明，同时写入 Release 正文与 latest.json")
    args = parser.parse_args()

    try:
        return cmd_check(args) if args.check_only else cmd_publish(args)
    except PublishError as e:
        print(f"\n[错误] {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
