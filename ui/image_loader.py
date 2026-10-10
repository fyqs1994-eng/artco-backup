"""
归档图片后台加载

- 缩略图：首次从原图按显示尺寸解码，存到 history_images/thumbs/ 作磁盘缓存，之后直接读小图
- 详情图 / 原图：按需在工作线程解码，界面线程只负责把结果贴上去

线程约定：工作线程里只碰 QImage / QImageReader（Qt 保证线程安全），
QPixmap 只在界面线程由回调方创建。
"""

import os
from concurrent.futures import ThreadPoolExecutor

import shiboken6
from PySide6.QtCore import QObject, Signal, QSize, Qt
from PySide6.QtGui import QImage, QImageReader

# 缩略图缓存尺寸：卡片 160×130 的 2 倍，200% 缩放下也不发虚
THUMB_BOX = QSize(320, 260)


def thumb_cache_path(src: str) -> str:
    """原图 history_images/xxx.jpg 对应的缓存 history_images/thumbs/xxx.png"""
    folder = os.path.join(os.path.dirname(src), "thumbs")
    stem = os.path.splitext(os.path.basename(src))[0]
    return os.path.join(folder, stem + ".png")


def _read_scaled(src: str, box: QSize) -> QImage:
    """在解码阶段就缩放到 box 内（保持宽高比，不放大），避免整张大图进内存"""
    reader = QImageReader(src)
    reader.setAutoTransform(True)
    size = reader.size()
    if size.isValid() and (size.width() > box.width() or size.height() > box.height()):
        reader.setScaledSize(size.scaled(box, Qt.AspectRatioMode.KeepAspectRatio))
    return reader.read()


def _load_thumb(src: str) -> QImage:
    cache = thumb_cache_path(src)
    try:
        if os.path.getmtime(cache) >= os.path.getmtime(src):
            img = QImage(cache)
            if not img.isNull():
                return img
    except OSError:
        pass
    img = _read_scaled(src, THUMB_BOX)
    if not img.isNull():
        try:
            os.makedirs(os.path.dirname(cache), exist_ok=True)
            tmp = cache + ".tmp"
            if img.save(tmp, "PNG"):
                os.replace(tmp, cache)
        except OSError:
            pass
    return img


def load_full_image(src: str) -> QImage:
    """读原图。超出 Qt 解码内存上限（默认 256MB，约 6700 万像素）的超大图整图解不出来，
    此时按上限等比缩小后再读，保证复制 / 作参考图不会静默失败。"""
    reader = QImageReader(src)
    reader.setAutoTransform(True)
    size = reader.size()
    limit_px = QImageReader.allocationLimit() * 1024 * 1024 // 4  # 按 32 位像素估算
    if limit_px > 0 and size.isValid() and size.width() * size.height() > limit_px:
        # 按 1/2、1/4… 缩：JPEG 解码器只有在这些比例下才真正少分配内存
        scale = 0.5
        while size.width() * size.height() * scale * scale > limit_px * 0.9:
            scale /= 2
        reader.setScaledSize(QSize(max(1, int(size.width() * scale)),
                                   max(1, int(size.height() * scale))))
    return reader.read()


class _ImageLoader(QObject):
    _done = Signal(str, QImage)

    def __init__(self):
        super().__init__()
        # 缩略图批量生成用 2 个线程；点开详情 / 复制原图单独一个线程，不被缩略图队列堵住
        self._thumb_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="artco-thumb")
        self._demand_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="artco-image")
        self._waiters = {}  # key -> [(owner, callback)]
        self._done.connect(self._dispatch)

    def _submit(self, pool, key, owner, callback, fn, *args):
        waiters = self._waiters.setdefault(key, [])
        waiters.append((owner, callback))
        if len(waiters) > 1:
            return  # 同一张图已在解码，结果出来一起分发

        def job():
            try:
                img = fn(*args)
            except Exception:
                img = None
            self._done.emit(key, img if img is not None else QImage())

        pool.submit(job)

    def _dispatch(self, key, img):
        for owner, callback in self._waiters.pop(key, []):
            # 卡片 / 弹窗可能在解码期间已被销毁，跳过即可
            if owner is None or shiboken6.isValid(owner):
                try:
                    callback(img)
                except RuntimeError:
                    pass

    def request_thumb(self, src, owner, callback):
        self._submit(self._thumb_pool, "thumb:" + src, owner, callback, _load_thumb, src)

    def request_scaled(self, src, box: QSize, owner, callback):
        key = f"scaled:{box.width()}x{box.height()}:{src}"
        self._submit(self._demand_pool, key, owner, callback, _read_scaled, src, QSize(box))

    def request_full(self, src, owner, callback):
        self._submit(self._demand_pool, "full:" + src, owner, callback, load_full_image, src)


_instance = None


def loader() -> _ImageLoader:
    """全局单例，必须在 QApplication 创建后、界面线程里首次调用"""
    global _instance
    if _instance is None:
        _instance = _ImageLoader()
    return _instance


def fit_pixmap(img: QImage, box: QSize, dpr: float):
    """把解码结果按屏幕 DPR 平滑缩放到 box（逻辑像素）内，返回设置好 DPR 的 QPixmap"""
    from PySide6.QtGui import QPixmap
    target = QSize(round(box.width() * dpr), round(box.height() * dpr))
    scaled = img.scaled(target, Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation)
    pm = QPixmap.fromImage(scaled)
    pm.setDevicePixelRatio(dpr)
    return pm
