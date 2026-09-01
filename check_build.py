"""
打包产物校验脚本 — 体积异常时报错退出，防止 exe 无声膨胀。

用法: python check_build.py <exe路径>
阈值依据历史正常构建: Artco.exe 约 105 MB。
"""

import os
import sys

# 体积阈值（MB）: 正常约 105，低于下限说明模块缺失，高于上限说明打进了无关大包
MIN_MB = 90.0
MAX_MB = 130.0


def main():
    if len(sys.argv) < 2:
        print('[错误] 用法: python check_build.py <exe路径>')
        return 1

    exe_path = sys.argv[1]
    if not os.path.isfile(exe_path):
        print('[错误] 产物不存在: %s' % exe_path)
        return 1

    size_mb = os.path.getsize(exe_path) / 1024.0 / 1024.0
    print('      %s = %.1f MB' % (os.path.basename(exe_path), size_mb))

    if size_mb < MIN_MB:
        print('[失败] 体积 %.1f MB 低于下限 %.1f MB，可能有模块未打进去！' % (size_mb, MIN_MB))
        return 1

    if size_mb > MAX_MB:
        print('[失败] 体积 %.1f MB 超过上限 %.1f MB，可能打进了无关大包！' % (size_mb, MAX_MB))
        print('       请检查 Artco.spec 的 excludes 是否生效。')
        return 1

    print('      体积校验通过（正常区间 %.0f-%.0f MB）' % (MIN_MB, MAX_MB))
    return 0


if __name__ == '__main__':
    sys.exit(main())
