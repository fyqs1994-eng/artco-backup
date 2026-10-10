"""
LightAI 客户端模块

LightAI（lightai_api_manager）是内部的 AI 能力网关，采用
「异步提交 + 轮询查询」模式，与 OpenAI 兼容协议不通用。

统一流程：
    1. POST /api/v1/{service}/call   提交任务 -> task_id
    2. GET  /api/v1/tasks/{task_id}  轮询     -> status=success 时取 data

认证：Authorization: Bearer <jwt_token>
文档：LightAI API Manager - API 调用文档
"""

import time

import requests

DEFAULT_BASE_URL = "https://lightaiapi.lightspeed.qq.com"
API_PREFIX = "/api/v1"

# _app 系列服务的计费身份头默认值（可由配置覆盖）
# 注意：X-User-Id 必须是已在 LightAI 中关联项目的真实邮箱，
# 未关联项目的邮箱会被拒绝（403 用户未关联任何项目）。
# 此处仅作占位示例，真实身份请在「设置 → LightAI → 计费身份」中填写；
# 未填写时调用会失败，属预期行为（不硬编码任何个人邮箱）。
DEFAULT_USER_ID = ""
DEFAULT_COMPANY = "tencent-formal"
DEFAULT_USER_TYPE = "internal"

# 任务状态
STATUS_PENDING = "pending"
STATUS_PROCESSING = "processing"
STATUS_SUCCESS = "success"
STATUS_FAILED = "failed"

# 默认轮询参数
DEFAULT_POLL_INTERVAL = 2.0
DEFAULT_TIMEOUT = 300.0


class LightAIError(Exception):
    """LightAI 调用错误"""


class LightAIClient:
    """LightAI 网关客户端（异步任务协议）"""

    cancel_check = None  # 可选：返回 True 时轮询立即退出

    def __init__(self, api_key: str, base_url: str = None,
                 user_id: str = None, company: str = "tencent-formal",
                 user_type: str = "internal"):
        self.api_key = (api_key or "").strip()
        # 容错：用户可能把 "Bearer xxx" 整段粘贴进来
        if self.api_key.lower().startswith("bearer "):
            self.api_key = self.api_key[7:].strip()
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self.user_id = (user_id or DEFAULT_USER_ID).strip()
        self.company = company or "tencent-formal"
        self.user_type = user_type or "internal"
        self._session = requests.Session()

    # ──────────────────────────────────────────────
    #  基础请求
    # ──────────────────────────────────────────────

    @classmethod
    def from_config(cls, api_key: str, base_url: str = None):
        """按 Artco 配置构造客户端（计费身份取自 ai_config）

        user_id 未配置时回退到内置默认值，保证老配置升级后仍可调用。
        """
        from config import ai_config

        billing = ai_config.get_lightai_billing()
        return cls(
            api_key,
            base_url=base_url,
            user_id=billing.get("user_id") or DEFAULT_USER_ID,
            company=billing.get("company") or DEFAULT_COMPANY,
            user_type=billing.get("user_type") or DEFAULT_USER_TYPE,
        )

    def _billing_headers(self):
        """_app 系列服务的必填计费头，缺失会返回 400"""
        return {
            "X-User-Id": self.user_id,
            "X-Company": self.company,
            "X-User-Type": self.user_type,
        }

    def _require_user_id(self):
        """计费身份未配置时提前给出明确提示

        网关对缺失 X-User-Id 只返回 HTTP 400，不说明原因，
        用户难以定位。这里提前拦截并给出可操作的中文提示。
        """
        if not (self.user_id or "").strip():
            raise LightAIError(
                "未配置 LightAI 计费身份：请到「设置 → LightAI」填写 "
                "计费身份邮箱（X-User-Id），需为已在 LightAI 平台关联项目的"
                "真实企业邮箱。"
            )

    def _json_headers(self):
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        headers.update(self._billing_headers())
        return headers

    def _auth_headers(self):
        headers = {"Authorization": f"Bearer {self.api_key}"}
        headers.update(self._billing_headers())
        return headers

    @staticmethod
    def service_for_model(model_id: str) -> str:
        """按模型名推断服务名，决定提交路径 /api/v1/{service}/call

        注意：带 _app 后缀的服务与不带后缀的是两套权限，不可混用。
        本 Key 仅具备 gemini_app / jimeng_app / gpt_app 权限。
        """
        m = (model_id or "").lower()
        if m.startswith("gpt"):
            return "gpt_app"
        if m.startswith("doubao") or "jimeng" in m:
            return "jimeng_app"
        return "gemini_app"

    @staticmethod
    def is_image_model(model_id: str) -> bool:
        """模型名含 image 即视为生图模型（与网关的推断规则一致）"""
        return "image" in (model_id or "").lower()

    def submit(self, service: str, payload: dict, files=None, form_data: dict = None):
        """提交任务，返回 task_id"""
        self._require_user_id()
        url = f"{self.base_url}{API_PREFIX}/{service}/call"

        if files:
            # 改图等场景：multipart/form-data（不手动设 Content-Type，交给 requests）
            resp = self._session.post(
                url, headers=self._auth_headers(),
                data=form_data or {}, files=files, timeout=60,
            )
        else:
            resp = self._session.post(
                url, headers=self._json_headers(), json=payload, timeout=60,
            )

        if resp.status_code in (401, 403):
            raise LightAIError(
                f"API Key 无效或无权访问服务 {service}（HTTP {resp.status_code}）"
            )
        if resp.status_code >= 400:
            raise LightAIError(
                f"提交任务失败（HTTP {resp.status_code}）：{_safe_text(resp)}"
            )

        data = resp.json()
        task_id = data.get("task_id")
        if not task_id:
            raise LightAIError(f"提交任务未返回 task_id：{str(data)[:200]}")
        return task_id

    def get_task(self, task_id: str) -> dict:
        """查询任务状态"""
        url = f"{self.base_url}{API_PREFIX}/tasks/{task_id}"
        resp = self._session.get(url, headers=self._json_headers(), timeout=30)
        if resp.status_code in (401, 403):
            raise LightAIError(f"API Key 无效（HTTP {resp.status_code}）")
        if resp.status_code >= 400:
            raise LightAIError(
                f"查询任务失败（HTTP {resp.status_code}）：{_safe_text(resp)}"
            )
        return resp.json()

    def wait_for_task(self, task_id: str, timeout: float = DEFAULT_TIMEOUT,
                      interval: float = DEFAULT_POLL_INTERVAL) -> dict:
        """轮询任务直至终态，返回完整任务结果"""
        deadline = time.time() + timeout
        while True:
            if self.cancel_check and self.cancel_check():
                raise LightAIError("任务已终止")
            data = self.get_task(task_id)
            status = data.get("status")

            if status == STATUS_SUCCESS:
                return data
            if status == STATUS_FAILED:
                raise LightAIError(
                    f"任务执行失败：{_extract_error(data)}"
                )

            if time.time() >= deadline:
                raise LightAIError(
                    f"任务超时（>{int(timeout)}s），最后状态：{status}"
                )
            time.sleep(interval)

    # ──────────────────────────────────────────────
    #  高层能力
    # ──────────────────────────────────────────────

    def gemini_call(self, model: str, contents: list, generation_config: dict = None,
                    system_instruction: dict = None, timeout: float = DEFAULT_TIMEOUT):
        """调用 Gemini 系列模型（视觉理解 / 对话 / 生图）"""
        payload = {"model": model, "contents": contents}
        if generation_config:
            payload["generationConfig"] = generation_config
        if system_instruction:
            payload["systemInstruction"] = system_instruction

        service = self.service_for_model(model)
        task_id = self.submit(service, payload)
        return self.wait_for_task(task_id, timeout=timeout)

    def vision_analyze(self, model: str, prompt: str, image_base64: str,
                       timeout: float = DEFAULT_TIMEOUT) -> str:
        """视觉理解：截图 base64 走 Gemini inlineData 直接传入，无需先上传 COS"""
        contents = [{
            "role": "user",
            "parts": [
                {"text": prompt},
                {
                    "inlineData": {
                        "mimeType": "image/png",
                        "data": image_base64,
                    }
                },
            ],
        }]
        result = self.gemini_call(model, contents, timeout=timeout)
        return extract_text(result)

    def generate_image(self, model: str, prompt: str, image_base64: str = None,
                       size: str = None, quality: str = None, n: int = 1,
                       timeout: float = DEFAULT_TIMEOUT):
        """生图 / 改图，返回任务结果 dict（由调用方解析图片）"""
        service = self.service_for_model(model)

        if service == "gpt_app":
            # gpt_app 按模型名分流：已登记的模型（gpt-image-2）走 prompt 字段。
            # 传 responses 的 input 格式会被网关以 400「缺少必填参数: prompt」拒绝。
            payload = {"model": model, "prompt": prompt}
            if image_base64:
                payload["image"] = image_base64
            if size:
                payload["size"] = size
            if quality:
                payload["quality"] = quality
            task_id = self.submit("gpt_app", payload)
            return self.wait_for_task(task_id, timeout=timeout)

        # Gemini / Jimeng 生图
        parts = [{"text": prompt}]
        if image_base64:
            parts.append({
                "inlineData": {"mimeType": "image/png", "data": image_base64}
            })

        contents = [{"role": "user", "parts": parts}]
        generation_config = {"responseModalities": ["IMAGE"]}
        # 即梦按官方参数透传，不用 Gemini 的 responseModalities
        if service == "jimeng_app":
            payload = {"model": model, "prompt": prompt}
            if size:
                payload["size"] = size
            task_id = self.submit("jimeng_app", payload)
            return self.wait_for_task(task_id, timeout=timeout)

        # 上游偶发 "incomplete chunked read"，自动重试一次
        last_err = None
        for _ in range(2):
            try:
                return self.gemini_call(
                    model, contents,
                    generation_config=generation_config,
                    timeout=timeout,
                )
            except LightAIError as e:
                last_err = e
                if "chunked read" not in str(e):
                    raise
                time.sleep(1)
        raise last_err

    def cos_upload(self, file_bytes: bytes, filename: str = "image.png",
                   content_type: str = "image/png") -> str:
        """上传文件到 COS，返回可直接访问的 cos_url"""
        url = f"{self.base_url}{API_PREFIX}/cos/upload"
        files = {"file": (filename, file_bytes, content_type)}
        resp = self._session.post(
            url, headers=self._auth_headers(), files=files, timeout=120,
        )
        if resp.status_code in (401, 403):
            raise LightAIError(f"API Key 无效（HTTP {resp.status_code}）")
        if resp.status_code >= 400:
            raise LightAIError(f"上传失败（HTTP {resp.status_code}）：{_safe_text(resp)}")
        data = resp.json()
        cos_url = data.get("cos_url")
        if not cos_url:
            raise LightAIError(f"上传未返回 cos_url：{str(data)[:200]}")
        return cos_url


# ──────────────────────────────────────────────
#  结果解析工具
# ──────────────────────────────────────────────

def _safe_text(resp, limit: int = 300) -> str:
    """安全提取响应正文（避免 HTML 刷屏）"""
    try:
        body = resp.text or ""
    except Exception:
        return ""
    return body[:limit]


def _extract_error(task_data: dict) -> str:
    """从任务结果中提取错误信息"""
    for key in ("error", "message", "detail"):
        val = task_data.get(key)
        if isinstance(val, str) and val.strip():
            return val[:300]
        if isinstance(val, dict):
            msg = val.get("message") or val.get("msg")
            if msg:
                return str(msg)[:300]
    data = task_data.get("data")
    if isinstance(data, dict):
        for key in ("error", "message"):
            val = data.get(key)
            if isinstance(val, str) and val.strip():
                return val[:300]
    return str(task_data)[:300]


def iter_parts(task_data: dict):
    """遍历任务结果中的所有 parts（兼容 Gemini / GPT 两种返回）"""
    data = task_data.get("data") or {}

    # 形态一：data.candidates[].content.parts[]
    candidates = data.get("candidates")
    if isinstance(candidates, list):
        for cand in candidates:
            if not isinstance(cand, dict):
                continue
            content = cand.get("content") or {}
            for part in content.get("parts") or []:
                if isinstance(part, dict):
                    yield part

    # 形态二：data.data[]（即梦风格的图片数组）
    items = data.get("data")
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict) and item.get("url"):
                yield {"url": item["url"]}

    # 形态三：data 本身就是 parts 容器
    for part in data.get("parts") or []:
        if isinstance(part, dict):
            yield part


def extract_text(task_data: dict) -> str:
    """从任务结果中提取文本内容"""
    chunks = []
    for part in iter_parts(task_data):
        text = part.get("text")
        if text:
            chunks.append(text)
    result = "\n".join(chunks).strip()
    if result:
        return result
    raise LightAIError(f"模型未返回文本内容：{str(task_data)[:300]}")


def extract_image(task_data: dict):
    """从任务结果中提取图片，返回 (kind, payload)

    kind 取值：
        "url"    -> payload 为图片 URL（网关已把 base64 转成 COS 链接）
        "base64" -> payload 为 base64 字符串（需自行解码）
    """
    import re

    for part in iter_parts(task_data):
        # 1) 直接的 URL 字段
        for key in ("url", "image_url", "cos_url"):
            val = part.get(key)
            if isinstance(val, str) and val.startswith(("http://", "https://")):
                return "url", val

        # 2) inlineData / inline_data（网关通常会替换为 COS URL）
        inline = part.get("inlineData") or part.get("inline_data")
        if isinstance(inline, dict):
            val = inline.get("url") or inline.get("cos_url")
            if isinstance(val, str) and val.startswith(("http://", "https://")):
                return "url", val
            b64 = inline.get("data")
            if b64:
                # 网关做 COS 后处理时，会把 data 字段的值替换成 COS URL，
                # 但字段名仍是 data，因此必须先判断是否已是 http 链接。
                if isinstance(b64, str) and b64.startswith(("http://", "https://")):
                    return "url", b64
                return "base64", b64

        # 3) 文本里可能直接给出图片链接
        text = part.get("text")
        if isinstance(text, str):
            match = re.search(r"https?://[^\s\"'<>()]+\.(?:png|jpe?g|webp)", text, re.I)
            if match:
                return "url", match.group(0)

    raise LightAIError(f"模型未返回图片数据：{str(task_data)[:300]}")
