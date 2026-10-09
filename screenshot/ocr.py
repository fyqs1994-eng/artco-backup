"""
截图模块 - 文字识别（OCR）

两种后端，共用 recognize() 入口：
1. WinRT  —— Windows 10/11 内置引擎，零依赖、零体积，默认可用。
2. RapidOCR —— 本地 PP-OCRv6 ONNX 模型，中文明显更强，需用户主动下载（约 30MB）。

设计原则：
- 引擎选择由 config 的 ocr_engine 决定，未安装 RapidOCR 时自动回退 WinRT，绝不报错。
- 识别结果按「视觉阅读顺序」重排：先按 y 聚类成行，行内按 x 排序。
  RapidOCR 原始输出按检测框顺序，直接拼接会是乱序的。
"""

import asyncio
import logging
import sys

from PySide6.QtGui import QPixmap, QImage

# 配置键：ocr_engine = "winrt" | "rapidocr"
_OCR_ENGINE_KEY = "ocr_engine"
_ENGINE_WINRT = "winrt"
_ENGINE_RAPIDOCR = "rapidocr"

# 行聚类容差：同一行文字的 y 中心差值在此范围内视为同一行
_ROW_TOLERANCE_RATIO = 0.6


def _qpixmap_to_bytes(pixmap: QPixmap) -> bytes:
    """将 QPixmap 转为 PNG 字节流"""
    from PySide6.QtCore import QBuffer, QIODevice
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    pixmap.save(buf, "PNG")
    data = buf.data().data()
    buf.close()
    return bytes(data)


def _qpixmap_to_ndarray(pixmap: QPixmap):
    """将 QPixmap 转为 RGB numpy 数组（供 RapidOCR 使用）"""
    img = pixmap.toImage().convertToFormat(QImage.Format.Format_RGB888)
    w, h = img.width(), img.height()
    ptr = img.constBits()
    import numpy as np
    # 每行字节数可能带 padding，需按实际 bytesPerLine 切片
    stride = img.bytesPerLine()
    raw = np.frombuffer(ptr, dtype=np.uint8)
    if stride != w * 3:
        arr = raw.reshape((h, stride))[:, : w * 3].reshape((h, w, 3))
    else:
        arr = raw.reshape((h, w, 3))
    # frombuffer 得到的是只读视图，OpenCV 无法处理，必须拷贝一份
    return np.ascontiguousarray(arr.copy())


def _sort_by_reading_order(items):
    """按视觉阅读顺序重排：y 聚类成行，行内按 x 升序。

    Args:
        items: [(box, text, score), ...]，box 为 4 点坐标

    Returns:
        重排后的 [(box, text, score), ...]
    """
    if not items:
        return items

    # 计算每个框的 y 中心与高度，用于聚类
    entries = []
    for box, text, score in items:
        ys = [float(p[1]) for p in box]
        xs = [float(p[0]) for p in box]
        y_center = (min(ys) + max(ys)) / 2.0
        height = max(ys) - min(ys)
        x_left = min(xs)
        entries.append((y_center, height, x_left, text, score))

    # 容差取中位数行高的一部分，避免个别超高框把整页并成一行
    heights = sorted(e[1] for e in entries)
    median_h = heights[len(heights) // 2] or 1.0
    tol = max(median_h * _ROW_TOLERANCE_RATIO, 1.0)

    # 按 y 中心排序后顺序聚类成行
    entries.sort(key=lambda e: e[0])
    rows = []
    cur_row = [entries[0]]
    cur_y = entries[0][0]
    for e in entries[1:]:
        if abs(e[0] - cur_y) <= tol:
            cur_row.append(e)
            cur_y = sum(x[0] for x in cur_row) / len(cur_row)
        else:
            rows.append(cur_row)
            cur_row = [e]
            cur_y = e[0]
    rows.append(cur_row)

    # 行内按 x 升序
    ordered = []
    for row in rows:
        row.sort(key=lambda e: e[2])
        ordered.extend(row)

    return [(None, e[3], e[4]) for e in ordered]


_rapidocr_engine = None
_rapidocr_load_failed = False


def _get_rapidocr_engine():
    """获取 RapidOCR 引擎单例。

    构造一次约 0.25-0.4s（加载 det/cls/rec 三个 ONNX 模型），
    每次识别都重建会白白翻倍耗时，故缓存复用。
    """
    global _rapidocr_engine, _rapidocr_load_failed

    if _rapidocr_load_failed:
        return None
    if _rapidocr_engine is not None:
        return _rapidocr_engine

    try:
        from rapidocr import RapidOCR
    except ImportError:
        _rapidocr_load_failed = True
        return None

    try:
        # 模型加载会打大量 INFO，压掉以免淹没真实错误日志
        logging.getLogger("RapidOCR").setLevel(logging.WARNING)
        _rapidocr_engine = RapidOCR()
    except Exception:
        _rapidocr_load_failed = True
        return None

    return _rapidocr_engine


def _recognize_rapidocr(pixmap: QPixmap) -> str:
    """用 RapidOCR 识别，返回按阅读顺序拼接的文本。

    返回 None 表示引擎不可用（未安装或加载失败），调用方应回退。
    """
    engine = _get_rapidocr_engine()
    if engine is None:
        return None

    try:
        result = engine(_qpixmap_to_ndarray(pixmap))
    except Exception as e:
        return f"[错误] RapidOCR 识别失败：{e}"

    if result is None:
        return ""

    boxes = getattr(result, "boxes", None)
    txts = getattr(result, "txts", None)
    scores = getattr(result, "scores", None)

    if txts is None or len(txts) == 0:
        return ""

    items = []
    for i, text in enumerate(txts):
        box = boxes[i] if boxes is not None and i < len(boxes) else None
        score = scores[i] if scores is not None and i < len(scores) else 0.0
        # 无坐标时无法排序，退化为 y=-1 保持原序
        if box is None:
            box = [(0, 0), (0, 0), (0, 0), (0, 0)]
        items.append((box, text, score))

    ordered = _sort_by_reading_order(items)
    return "\n".join(t for _, t, _ in ordered)


async def _ocr_async(image_bytes: bytes, lang: str = "zh-Hans") -> str:
    """异步调用 WinRT OCR"""
    from winsdk.windows.media.ocr import OcrEngine
    from winsdk.windows.globalization import Language
    from winsdk.windows.graphics.imaging import (
        BitmapDecoder
    )
    from winsdk.windows.storage.streams import (
        InMemoryRandomAccessStream, DataWriter
    )

    # 将图片数据写入内存流
    stream = InMemoryRandomAccessStream()
    writer = DataWriter(stream)
    writer.write_bytes(image_bytes)
    await writer.store_async()
    await writer.flush_async()
    stream.seek(0)

    # 解码为 SoftwareBitmap
    decoder = await BitmapDecoder.create_async(stream)
    bitmap = await decoder.get_software_bitmap_async()

    # 创建 OCR 引擎并识别
    language = Language(lang)
    if not OcrEngine.is_language_supported(language):
        # 回退到英语
        language = Language("en")
        if not OcrEngine.is_language_supported(language):
            # 使用用户配置语言
            engine = OcrEngine.try_create_from_user_profile_languages()
            if engine is None:
                return "[错误] 系统未安装任何 OCR 语言包"
        else:
            engine = OcrEngine.try_create_from_language(language)
    else:
        engine = OcrEngine.try_create_from_language(language)

    result = await engine.recognize_async(bitmap)
    return result.text if result else ""


def _recognize_winrt(pixmap: QPixmap, lang: str) -> str:
    """用 WinRT 引擎识别"""
    if sys.platform != "win32":
        return "[错误] OCR 功能仅支持 Windows 10/11"

    image_bytes = _qpixmap_to_bytes(pixmap)
    loop = asyncio.new_event_loop()
    try:
        text = loop.run_until_complete(_ocr_async(image_bytes, lang))
    finally:
        loop.close()
    return text


def _ai_config():
    try:
        import config as _cfg
        return _cfg.ai_config
    except Exception:
        return None


def get_engine() -> str:
    """读取当前配置的 OCR 后端"""
    cfg = _ai_config()
    if cfg is None:
        return _ENGINE_WINRT
    try:
        return cfg.get(_OCR_ENGINE_KEY, _ENGINE_WINRT) or _ENGINE_WINRT
    except Exception:
        return _ENGINE_WINRT


def set_engine(engine: str):
    """写入 OCR 后端选择"""
    cfg = _ai_config()
    if cfg is None:
        return
    try:
        cfg.set(_OCR_ENGINE_KEY, engine)
    except Exception:
        pass


def is_rapidocr_available() -> bool:
    """RapidOCR 是否已安装可用"""
    try:
        import rapidocr  # noqa: F401
        return True
    except ImportError:
        return False


def recognize(pixmap: QPixmap, lang: str = "zh-Hans") -> str:
    """
    同步接口：对 QPixmap 执行 OCR，返回识别文本。
    在子线程中调用。

    后端由配置决定；RapidOCR 不可用或未安装时自动回退 WinRT。
    """
    if get_engine() == _ENGINE_RAPIDOCR:
        text = _recognize_rapidocr(pixmap)
        # 返回 None 表示模块未安装，回退；错误串直接返回
        if text is not None:
            return text

    return _recognize_winrt(pixmap, lang)
