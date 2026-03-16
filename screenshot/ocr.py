"""
截图模块 - WinRT OCR 文字识别
使用 Windows 10/11 内置 OCR 引擎，零依赖、零体积。
"""

import asyncio
import sys
from PySide6.QtGui import QPixmap, QImage


def _qpixmap_to_bytes(pixmap: QPixmap) -> bytes:
    """将 QPixmap 转为 PNG 字节流"""
    from PySide6.QtCore import QBuffer, QIODevice
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    pixmap.save(buf, "PNG")
    data = buf.data().data()
    buf.close()
    return bytes(data)


async def _ocr_async(image_bytes: bytes, lang: str = "zh-Hans") -> str:
    """异步调用 WinRT OCR"""
    from winsdk.windows.media.ocr import OcrEngine
    from winsdk.windows.globalization import Language
    from winsdk.windows.graphics.imaging import (
        BitmapDecoder, SoftwareBitmap
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


def recognize(pixmap: QPixmap, lang: str = "zh-Hans") -> str:
    """
    同步接口：对 QPixmap 执行 OCR，返回识别文本。
    在子线程中调用。
    """
    if sys.platform != "win32":
        return "[错误] OCR 功能仅支持 Windows 10/11"

    image_bytes = _qpixmap_to_bytes(pixmap)

    # 在新的事件循环中运行异步 OCR
    loop = asyncio.new_event_loop()
    try:
        text = loop.run_until_complete(_ocr_async(image_bytes, lang))
    finally:
        loop.close()

    return text
