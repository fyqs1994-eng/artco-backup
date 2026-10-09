"""
企业微信待办 MCP 客户端

对接企微官方 MCP 端点（JSON-RPC over HTTP）：
    https://qyapi.weixin.qq.com/mcp/v2/bot/todo?apikey=<KEY>

支持的工具：todo_create / todo_list / todo_get / todo_update / todo_finish / todo_delete

**安全说明**：apikey 不硬编码在本文件。优先从 ai_config.json 读取
（`wecom_todo.apikey`），该文件已被 .gitignore 忽略，不会进仓库。
"""

import json
import urllib.request
import urllib.error
from typing import List, Dict, Tuple

from config import ai_config

# MCP 端点（不含 apikey，apikey 运行时拼接）
WECOM_MCP_ENDPOINT = "https://qyapi.weixin.qq.com/mcp/v2/bot/todo"

# 单次批量上限（企微限制 20）
_MAX_BATCH = 20

_MISSING_KEY_MSG = "未配置企业微信待办 apikey，请到 设置 → 企业微信待办 填写"


class WeComTodoError(Exception):
    """企微待办接口错误"""


class WeComTodoClient:
    """企业微信待办 MCP 客户端"""

    def __init__(self, apikey: str = None, timeout: int = 30):
        # apikey 优先取参数，其次取配置，绝不硬编码
        self._apikey = (apikey or "").strip() or (
            (ai_config.get("wecom_todo") or {}).get("apikey") or "").strip()
        self._timeout = timeout
        if not self._apikey:
            raise WeComTodoError(_MISSING_KEY_MSG)

    # ──────────────────────────────
    #  底层调用
    # ──────────────────────────────

    def _endpoint(self) -> str:
        return f"{WECOM_MCP_ENDPOINT}?apikey={self._apikey}"

    def _call(self, method: str, params: dict = None) -> dict:
        """发起一次 JSON-RPC 调用，返回 result 字段

        注意：必须带 Accept: application/json，否则企微返回 406。
        """
        body = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params or {},
        }).encode("utf-8")

        req = urllib.request.Request(
            self._endpoint(),
            data=body,
            headers={
                "Content-Type": "application/json",
                # 企微强制要求，缺失会返回 406 Not Acceptable
                "Accept": "application/json, text/event-stream",
                "User-Agent": "Artco/1.0",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")
            raise WeComTodoError(f"HTTP {e.code}: {detail[:200]}")
        except urllib.error.URLError as e:
            raise WeComTodoError(f"网络错误：{e.reason}")
        except Exception as e:
            raise WeComTodoError(f"请求失败：{e}")

        try:
            data = json.loads(raw)
        except Exception:
            raise WeComTodoError(f"响应不是合法 JSON：{raw[:200]}")

        if "error" in data:
            err = data["error"]
            raise WeComTodoError(f"{err.get('message', '未知错误')} (code={err.get('code')})")

        return data.get("result") or {}

    def _call_tool(self, tool_name: str, arguments: dict) -> str:
        """调用 MCP 工具，返回文本内容"""
        result = self._call("tools/call", {
            "name": tool_name,
            "arguments": arguments,
        })
        content = result.get("content") or []
        texts = [c.get("text", "") for c in content if isinstance(c, dict)]
        return "\n".join(t for t in texts if t)

    # ──────────────────────────────
    #  业务方法
    # ──────────────────────────────

    def create_todos(self, title_prefix: str, items: List[Dict]) -> Tuple[Dict[str, str], str]:
        """批量创建待办

        Args:
            title_prefix: 标题前缀（一般用屏贴标题）
            items: [{"id":..., "text":...}, ...] 本地待办条目

        Returns:
            (本地id -> 企微todo_id 映射, 错误信息)。成功时错误信息为空串。
        """
        if not items:
            return {}, ""

        # 超过 20 条分批
        mapping: Dict[str, str] = {}
        for i in range(0, len(items), _MAX_BATCH):
            batch = items[i:i + _MAX_BATCH]
            payload_items = [{
                "title": f"{title_prefix} - {it['text']}"[:100],
                "description": it.get("text", ""),
            } for it in batch]

            try:
                text = self._call_tool("todo_create", {"items": payload_items})
            except WeComTodoError as e:
                return mapping, str(e)

            ids = self._extract_ids(text)
            for local_item, remote_id in zip(batch, ids):
                if remote_id:
                    mapping[local_item["id"]] = remote_id

        if not mapping:
            return {}, "创建成功但未返回待办 ID"
        return mapping, ""

    @staticmethod
    def _extract_ids(text: str) -> List[str]:
        """从返回文本中解析 todo_id 列表

        返回格式可能是 JSON，也可能是自然语言描述，两种都尝试兼容。
        """
        ids: List[str] = []

        # 1) 整段是 JSON
        try:
            data = json.loads(text)
            def walk(node):
                if isinstance(node, dict):
                    for k, v in node.items():
                        if k in ("todo_id", "todoId", "id") and isinstance(v, str):
                            ids.append(v)
                        else:
                            walk(v)
                elif isinstance(node, list):
                    for v in node:
                        walk(v)
            walk(data)
            if ids:
                return ids
        except Exception:
            pass

        # 2) 文本中嵌 JSON
        import re
        for m in re.finditer(r'"todo_id"\s*:\s*"([^"]+)"', text):
            ids.append(m.group(1))
        if not ids:
            for m in re.finditer(r'"todoId"\s*:\s*"([^"]+)"', text):
                ids.append(m.group(1))
        return ids

    def list_todos(self, limit: int = 20) -> List[Dict]:
        """读取待办列表"""
        try:
            text = self._call_tool("todo_list", {"limit": min(limit, _MAX_BATCH)})
        except WeComTodoError:
            return []
        try:
            data = json.loads(text)
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                return data.get("items") or data.get("todos") or []
        except Exception:
            pass
        return []

    def finish_todo(self, todo_id: str) -> bool:
        """完成一条待办"""
        try:
            self._call_tool("todo_finish", {"items": [{"todo_id": todo_id}]})
            return True
        except WeComTodoError:
            return False

    def delete_todo(self, todo_id: str) -> bool:
        """删除一条待办"""
        try:
            self._call_tool("todo_delete", {"items": [{"todo_id": todo_id}]})
            return True
        except WeComTodoError:
            return False

    def is_configured(self) -> bool:
        """是否已配置 apikey"""
        return bool(self._apikey)


def is_wecom_todo_configured() -> bool:
    """判断是否已配置企微待办 apikey（不抛异常，供 UI 判断）"""
    try:
        return WeComTodoClient().is_configured()
    except WeComTodoError:
        return False
