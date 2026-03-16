"""
数据库模块 - 管理历史记录存储和自定义 Prompt
使用 SQLite 存储记录元数据，图片文件保存在本地文件夹
"""

import sqlite3
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional


def get_data_dir():
    """获取数据存储目录（便携模式：exe 同目录）"""
    if getattr(sys, 'frozen', False):
        # PyInstaller 打包后 - 便携模式，使用 exe 所在目录
        data_dir = Path(os.path.dirname(sys.executable))
    else:
        # 开发环境
        data_dir = Path(__file__).parent
    
    # 确保目录存在
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir

# 数据库和图片存储路径
DB_PATH = get_data_dir() / "history.db"
IMAGES_DIR = get_data_dir() / "history_images"

# 预设 Prompt 数据
DEFAULT_PROMPTS = [
    {
        "title": "智能分析",
        "content": "请详细分析这张图片的内容。",
        "is_default": True,
        "prompt_type": "text"
    },
    {
        "title": "代码审查",
        "content": "图片中是一段代码，请分析其逻辑，指出潜在 Bug 并给出优化建议。",
        "is_default": False,
        "prompt_type": "text"
    },
    {
        "title": "UI 建议",
        "content": "作为一名资深 UI 设计师，请评价这张界面的配色和布局，并给出改进意见。",
        "is_default": False,
        "prompt_type": "text"
    },
    {
        "title": "生成类似风格",
        "content": "请生成一张与参考图片风格相似的图像。",
        "is_default": False,
        "prompt_type": "image"
    },
]


def _get_connection() -> sqlite3.Connection:
    """获取数据库连接"""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row  # 支持字典式访问
    return conn


def init_database():
    """初始化数据库和图片文件夹"""
    # 创建图片存储文件夹
    IMAGES_DIR.mkdir(exist_ok=True)
    
    # 创建数据库表
    conn = _get_connection()
    cursor = conn.cursor()
    
    # records 表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS records (
            id TEXT PRIMARY KEY,
            timestamp TEXT NOT NULL,
            image_path TEXT NOT NULL,
            ai_text TEXT NOT NULL,
            tags TEXT DEFAULT ''
        )
    """)
    
    # 创建时间索引，加速按时间排序查询
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_timestamp ON records(timestamp DESC)
    """)
    
    # prompts 表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS prompts (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            is_default INTEGER DEFAULT 0,
            prompt_type TEXT DEFAULT 'text'
        )
    """)
    
    # 检查是否需要添加 prompt_type 列（兼容旧数据库）
    cursor.execute("PRAGMA table_info(prompts)")
    columns = [col[1] for col in cursor.fetchall()]
    if "prompt_type" not in columns:
        cursor.execute("ALTER TABLE prompts ADD COLUMN prompt_type TEXT DEFAULT 'text'")
    
    conn.commit()
    
    # 检查 prompts 表是否为空，如果为空则插入预设数据
    cursor.execute("SELECT COUNT(*) FROM prompts")
    count = cursor.fetchone()[0]
    
    if count == 0:
        for prompt in DEFAULT_PROMPTS:
            prompt_id = str(uuid.uuid4())
            cursor.execute("""
                INSERT INTO prompts (id, title, content, is_default, prompt_type)
                VALUES (?, ?, ?, ?, ?)
            """, (prompt_id, prompt["title"], prompt["content"], 1 if prompt["is_default"] else 0, prompt.get("prompt_type", "text")))
        conn.commit()
    
    conn.close()


def add_record(image_data: bytes, ai_text: str, tags: str = "", ext: str = ".png") -> str:
    """
    保存一条新记录
    
    Args:
        image_data: 图片的二进制数据
        ai_text: AI 分析的文字内容
        tags: 可选标签，逗号分隔
        ext: 文件扩展名，包含点号（如 .png, .jpg），默认为 .png
    
    Returns:
        记录的唯一 ID
    """
    # 生成唯一 ID 和时间戳
    record_id = str(uuid.uuid4())
    timestamp = datetime.now().isoformat()
    
    # 保存图片文件，使用指定扩展名
    # 确保扩展名以点号开头
    if not ext.startswith("."):
        ext = "." + ext
    image_filename = f"{record_id}{ext}"
    image_path = IMAGES_DIR / image_filename
    with open(image_path, "wb") as f:
        f.write(image_data)
    
    # 存储相对路径到数据库
    relative_path = f"history_images/{image_filename}"
    
    # 插入数据库记录
    conn = _get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO records (id, timestamp, image_path, ai_text, tags)
        VALUES (?, ?, ?, ?, ?)
    """, (record_id, timestamp, relative_path, ai_text, tags))
    
    conn.commit()
    conn.close()
    
    return record_id


def get_all_records() -> List[dict]:
    """
    按时间倒序获取所有记录
    
    Returns:
        记录列表，每条记录包含 id, timestamp, image_path, ai_text, tags
    """
    conn = _get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, timestamp, image_path, ai_text, tags
        FROM records
        ORDER BY timestamp DESC
    """)
    
    rows = cursor.fetchall()
    conn.close()
    
    # 转换为字典列表
    records = []
    for row in rows:
        records.append({
            "id": row["id"],
            "timestamp": row["timestamp"],
            "image_path": row["image_path"],
            "ai_text": row["ai_text"],
            "tags": row["tags"]
        })
    
    return records


def get_record_by_id(record_id: str) -> Optional[dict]:
    """
    根据 ID 获取单条记录
    
    Args:
        record_id: 记录 ID
    
    Returns:
        记录字典，不存在则返回 None
    """
    conn = _get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, timestamp, image_path, ai_text, tags
        FROM records
        WHERE id = ?
    """, (record_id,))
    
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return {
            "id": row["id"],
            "timestamp": row["timestamp"],
            "image_path": row["image_path"],
            "ai_text": row["ai_text"],
            "tags": row["tags"]
        }
    return None


def delete_record(record_id: str) -> bool:
    """
    删除记录并删除对应的本地图片文件
    
    Args:
        record_id: 记录 ID
    
    Returns:
        是否删除成功
    """
    conn = _get_connection()
    cursor = conn.cursor()
    
    # 先获取图片路径
    cursor.execute("SELECT image_path FROM records WHERE id = ?", (record_id,))
    row = cursor.fetchone()
    
    if not row:
        conn.close()
        return False
    
    image_path = row["image_path"]
    
    # 删除数据库记录
    cursor.execute("DELETE FROM records WHERE id = ?", (record_id,))
    conn.commit()
    conn.close()
    
    # 删除本地图片文件
    full_image_path = get_data_dir() / image_path
    if full_image_path.exists():
        try:
            full_image_path.unlink()
        except Exception:
            pass
    
    return True


def update_record_tags(record_id: str, tags: str) -> bool:
    """
    更新记录的标签
    
    Args:
        record_id: 记录 ID
        tags: 新的标签字符串
    
    Returns:
        是否更新成功
    """
    conn = _get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        UPDATE records SET tags = ? WHERE id = ?
    """, (tags, record_id))
    
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    
    return affected > 0


def get_image_full_path(relative_path: str) -> Path:
    """
    获取图片的完整路径
    
    Args:
        relative_path: 数据库中存储的相对路径 (如 "history_images/xxx.png")
    
    Returns:
        完整的文件路径
    """
    # 使用数据目录而不是脚本目录
    data_dir = get_data_dir()
    
    # relative_path 格式为 "history_images/xxx.png"
    # 需要提取文件名并拼接到正确的目录
    filename = Path(relative_path).name
    return IMAGES_DIR / filename


# ==================== Prompt 管理函数 ====================

def get_all_prompts() -> List[dict]:
    """
    获取所有提示词
    
    Returns:
        提示词列表，每条包含 id, title, content, is_default, prompt_type
    """
    conn = _get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, title, content, is_default, prompt_type
        FROM prompts
        ORDER BY is_default DESC, title ASC
    """)
    
    rows = cursor.fetchall()
    conn.close()
    
    prompts = []
    for row in rows:
        prompts.append({
            "id": row["id"],
            "title": row["title"],
            "content": row["content"],
            "is_default": bool(row["is_default"]),
            "prompt_type": row["prompt_type"] or "text"
        })
    
    return prompts


def get_prompt_by_id(prompt_id: str) -> Optional[dict]:
    """
    根据 ID 获取单条提示词
    
    Args:
        prompt_id: 提示词 ID
    
    Returns:
        提示词字典，不存在则返回 None
    """
    conn = _get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, title, content, is_default, prompt_type
        FROM prompts
        WHERE id = ?
    """, (prompt_id,))
    
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return {
            "id": row["id"],
            "title": row["title"],
            "content": row["content"],
            "is_default": bool(row["is_default"]),
            "prompt_type": row["prompt_type"] or "text"
        }
    return None


def get_default_prompt() -> Optional[dict]:
    """
    获取默认提示词
    
    Returns:
        默认提示词字典，不存在则返回 None
    """
    conn = _get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, title, content, is_default, prompt_type
        FROM prompts
        WHERE is_default = 1
        LIMIT 1
    """)
    
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return {
            "id": row["id"],
            "title": row["title"],
            "content": row["content"],
            "is_default": bool(row["is_default"]),
            "prompt_type": row["prompt_type"] or "text"
        }
    return None


def add_prompt(title: str, content: str, is_default: bool = False, prompt_type: str = "text") -> str:
    """
    新增提示词
    
    Args:
        title: 提示词标题
        content: 提示词内容
        is_default: 是否设为默认
        prompt_type: 提示词类型 ("text" 或 "image")
    
    Returns:
        新增提示词的 ID
    """
    conn = _get_connection()
    cursor = conn.cursor()
    
    # 如果设为默认，先取消其他默认
    if is_default:
        cursor.execute("UPDATE prompts SET is_default = 0")
    
    prompt_id = str(uuid.uuid4())
    cursor.execute("""
        INSERT INTO prompts (id, title, content, is_default, prompt_type)
        VALUES (?, ?, ?, ?, ?)
    """, (prompt_id, title, content, 1 if is_default else 0, prompt_type))
    
    conn.commit()
    conn.close()
    
    return prompt_id


def update_prompt(prompt_id: str, title: str = None, content: str = None, is_default: bool = None, prompt_type: str = None) -> bool:
    """
    更新提示词
    
    Args:
        prompt_id: 提示词 ID
        title: 新标题（可选）
        content: 新内容（可选）
        is_default: 是否设为默认（可选）
        prompt_type: 提示词类型（可选）
    
    Returns:
        是否更新成功
    """
    conn = _get_connection()
    cursor = conn.cursor()
    
    # 构建更新语句
    updates = []
    params = []
    
    if title is not None:
        updates.append("title = ?")
        params.append(title)
    
    if content is not None:
        updates.append("content = ?")
        params.append(content)
    
    if is_default is not None:
        # 如果设为默认，先取消其他默认
        if is_default:
            cursor.execute("UPDATE prompts SET is_default = 0")
        updates.append("is_default = ?")
        params.append(1 if is_default else 0)
    
    if prompt_type is not None:
        updates.append("prompt_type = ?")
        params.append(prompt_type)
    
    if not updates:
        conn.close()
        return False
    
    params.append(prompt_id)
    cursor.execute(f"""
        UPDATE prompts SET {', '.join(updates)} WHERE id = ?
    """, params)
    
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    
    return affected > 0


def delete_prompt(prompt_id: str) -> bool:
    """
    删除提示词
    
    Args:
        prompt_id: 提示词 ID
    
    Returns:
        是否删除成功
    """
    conn = _get_connection()
    cursor = conn.cursor()
    
    cursor.execute("DELETE FROM prompts WHERE id = ?", (prompt_id,))
    
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    
    return affected > 0


def set_default_prompt(prompt_id: str) -> bool:
    """
    设置某个提示词为默认
    
    Args:
        prompt_id: 提示词 ID
    
    Returns:
        是否设置成功
    """
    conn = _get_connection()
    cursor = conn.cursor()
    
    # 先取消所有默认
    cursor.execute("UPDATE prompts SET is_default = 0")
    
    # 设置新默认
    cursor.execute("UPDATE prompts SET is_default = 1 WHERE id = ?", (prompt_id,))
    
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    
    return affected > 0
