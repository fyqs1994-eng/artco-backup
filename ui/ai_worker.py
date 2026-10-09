"""
AI 工作线程模块
负责执行 AI 视觉分析和图像生成任务
统一使用 OpenAI 兼容协议调用所有 provider
"""

import base64

from PySide6.QtCore import QThread, Signal

from config import DEFAULT_PROMPT, ai_config


class AIWorker(QThread):
    """AI 分析工作线程"""
    finished = Signal(str)  # 文本结果
    finished_image = Signal(str)  # 图像生成结果（图片路径）
    error = Signal(str)

    def __init__(self, base64_image=None, prompt: str = None, qimage=None):
        super().__init__()
        self.base64_image = base64_image
        self._qimage = qimage  # 若提供，则在子线程中完成 PNG→base64 编码
        self.prompt = prompt or DEFAULT_PROMPT



    def run(self):
        try:
            # 若传入了 QImage，在子线程中完成 PNG→base64 编码（避免主线程阻塞）
            if self._qimage is not None and not self.base64_image:
                from PySide6.QtCore import QBuffer, QIODevice
                from PySide6.QtGui import QPixmap
                buf = QBuffer()
                buf.open(QIODevice.OpenModeFlag.WriteOnly)
                QPixmap.fromImage(self._qimage).save(buf, "PNG")
                self.base64_image = base64.b64encode(buf.data().data()).decode()
                buf.close()

            task_type = ai_config.get("task_type", "vision")
            
            if task_type == "image_gen":
                self._run_image_generation()
            else:
                self._run_vision_analysis()
        except Exception as e:
            self.error.emit(f"请求失败: {str(e)}")
    
    def _run_vision_analysis(self):
        """视觉分析模式"""
        provider_id = ai_config.get_current_provider_selected()
        model_id = ai_config.get_current_model()

        if not provider_id:
            self.error.emit("请先在设置中添加 AI 服务商")
            return

        # 兜底：模型不属于当前服务商时，回退到该服务商的默认模型
        # （历史配置里存过带前缀的显示名，或切换服务商后遗留了上一个的模型）
        model_id = self._resolve_model_for_provider(provider_id, model_id, "vision")

        if not model_id:
            self.error.emit("模型配置错误，请重新验证 API Key")
            return

        api_key = ai_config.get_api_key(provider_id)
        base_url = ai_config.get_api_base_url(provider_id)

        if not api_key:
            self.error.emit(f"请先在设置中配置 {provider_id} 的 API Key")
            return

        # 根据服务商使用不同的 SDK
        if provider_id == "google":
            self._run_google_vision(api_key, model_id)
        elif provider_id == "lightai":
            self._run_lightai_vision(api_key, base_url, model_id)
        else:
            self._run_openai_compatible_vision(provider_id, api_key, base_url, model_id)

    def _resolve_model_for_provider(self, provider_id, model_id, kind):
        """校验模型是否属于当前服务商，不属于则回退到其默认模型

        kind: "vision" 或 "image_gen"

        注意：模型 ID 会跨服务商重名（gemini-3-flash-preview 同时属于
        Google 和 LightAI），所以这里必须用 get_models_for_provider 判断，
        不能查 AI_MODELS 里的 provider 字段——那只会命中第一条。
        """
        allowed = ai_config.get_models_for_provider(provider_id, kind)
        if not allowed:
            return model_id
        if model_id in allowed:
            return model_id

        fallback = allowed[0]
        key = "vision_model" if kind == "vision" else "image_gen_model"
        ai_config.set(key, fallback)
        return fallback

    def _run_lightai_vision(self, api_key, base_url, model_id):
        """LightAI 视觉理解（异步提交 + 轮询）"""
        from ui.lightai_client import LightAIClient, LightAIError

        if not self.base64_image:
            self.error.emit("视觉分析需要图片，请先截图")
            return

        try:
            client = LightAIClient.from_config(api_key, base_url or None)
            text = client.vision_analyze(model_id, self.prompt, self.base64_image)
            self.finished.emit(text)
        except LightAIError as e:
            self.error.emit(str(e))
        except Exception as e:
            self.error.emit(f"LightAI 请求失败: {str(e)}")



    
    def _run_google_vision(self, api_key, model_id):
        """Google 原生 SDK 视觉分析"""
        from google import genai
        from google.genai import types
        
        client = genai.Client(api_key=api_key)
        
        # 构建 Google SDK 要求的模型名格式 (添加 models/ 前缀)
        if not model_id:
            self.error.emit("模型 ID 为空，请重新验证 API Key")
            return
        
        if not model_id.startswith("models/"):
            model_id = f"models/{model_id}"
        
        # 构建内容
        image_data = base64.b64decode(self.base64_image)
        contents = [
            types.Part.from_bytes(data=image_data, mime_type="image/png"),
            self.prompt
        ]
        
        response = client.models.generate_content(
            model=model_id,
            contents=contents,
        )

        self.finished.emit(response.text)

    def _run_openai_compatible_vision(self, provider_id, api_key, base_url, model_id):
        """OpenAI 兼容协议（OpenAI、Anthropic 等）"""
        from openai import OpenAI
        
        client_kwargs = {"api_key": api_key}
        if base_url:
            # 规范化：去除用户可能误填的路径后缀
            url = base_url.rstrip("/")
            for suffix in ["/chat/completions", "/v1/chat/completions", "/llmproxy/chat/completions"]:
                if url.endswith(suffix):
                    url = url[:-len(suffix)]
                    break
            client_kwargs["base_url"] = url
        
        client = OpenAI(**client_kwargs)
        
        response = client.chat.completions.create(
            model=model_id,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": self.prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{self.base64_image}"
                            }
                        }
                    ]
                }
            ],
            max_tokens=4096
        )
        self.finished.emit(response.choices[0].message.content)

    def _run_image_generation(self):
        """图像生成模式 - 根据 provider 类型路由到对应 SDK"""
        provider_id = ai_config.get_image_gen_provider()
        model_id = ai_config.get_image_gen_model()

        if not provider_id:
            self.error.emit("请先在设置中配置图像生成服务商")
            return

        # 兜底：模型不属于当前服务商时，回退到该服务商的默认模型
        model_id = self._resolve_model_for_provider(provider_id, model_id, "image_gen")

        if not model_id:
            self.error.emit("图像生成模型配置错误，请重新验证 API Key")
            return

        api_key = ai_config.get_api_key(provider_id)
        if not api_key:
            self.error.emit(f"请先在设置中配置 {provider_id} 的 API Key")
            return

        # 根据 provider 类型路由
        if provider_id == "google":
            self._run_google_image_generation(api_key, model_id)
        elif provider_id == "lightai":
            base_url = ai_config.get_api_base_url(provider_id)
            self._run_lightai_image_generation(api_key, base_url, model_id)
        else:
            base_url = ai_config.get_api_base_url(provider_id)
            self._run_openai_compatible_image_generation(api_key, base_url, model_id)

    def _run_lightai_image_generation(self, api_key, base_url, model_id):
        """LightAI 生图 / 改图（异步提交 + 轮询）"""
        import os
        import io
        import tempfile
        from datetime import datetime

        from ui.lightai_client import LightAIClient, LightAIError, extract_image

        try:
            client = LightAIClient.from_config(api_key, base_url or None)
            result = client.generate_image(
                model_id, self.prompt, image_base64=self.base64_image
            )

            kind, payload = extract_image(result)

            temp_dir = os.path.join(tempfile.gettempdir(), "artco_generated")
            os.makedirs(temp_dir, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            image_path = os.path.join(temp_dir, f"generated_{timestamp}.png")

            if kind == "base64":
                from PIL import Image
                img = Image.open(io.BytesIO(base64.b64decode(payload)))
                img.save(image_path, "PNG")
            else:
                import requests
                from PIL import Image
                resp = requests.get(payload, timeout=60)
                resp.raise_for_status()
                img = Image.open(io.BytesIO(resp.content))
                img.save(image_path, "PNG")

            self.finished_image.emit(image_path)

        except LightAIError as e:
            self.error.emit(str(e))
        except Exception as e:
            self.error.emit(f"LightAI 生图失败: {str(e)}")

    def _run_google_image_generation(self, api_key, model_id):
        """使用 Google Gemini SDK 生成图像"""
        import os
        import tempfile
        import io
        from datetime import datetime
        from google import genai
        from google.genai import types
        from PIL import Image

        if not api_key:
            self.error.emit("图像生成需要配置 Google API Key")
            return

        client = genai.Client(api_key=api_key)

        # 构建请求内容
        contents = []

        # 如果有参考图片，先添加
        if self.base64_image:
            image_data = base64.b64decode(self.base64_image)
            contents.append(types.Part.from_bytes(data=image_data, mime_type="image/png"))

        # 添加提示词
        contents.append(self.prompt)

        # 构建 Google SDK 要求的模型名格式 (添加 models/ 前缀)
        image_gen_model = model_id
        if not image_gen_model.startswith("models/"):
            image_gen_model = f"models/{image_gen_model}"

        try:
            # 调用生成内容 API
            response = client.models.generate_content(
                model=image_gen_model,
                contents=contents,
            )

            # 检查响应状态
            if hasattr(response, 'candidates') and response.candidates:
                # 从候选结果中提取图片
                generated_image = None
                for candidate in response.candidates:
                    if hasattr(candidate, 'content') and hasattr(candidate.content, 'parts'):
                        for part in candidate.content.parts:
                            if hasattr(part, 'inline_data') and part.inline_data:
                                # 从 inline_data 中提取图片数据
                                image_data = part.inline_data.data
                                if image_data:
                                    # 使用 PIL 处理图片数据
                                    generated_image = Image.open(io.BytesIO(image_data))
                                    break
                        if generated_image:
                            break

                if not generated_image:
                    # 尝试旧的解析方式
                    for part in response.parts if hasattr(response, 'parts') else []:
                        if hasattr(part, 'inline_data') and part.inline_data:
                            image_data = part.inline_data.data
                            if image_data:
                                generated_image = Image.open(io.BytesIO(image_data))
                                break
            else:
                self.error.emit(f"图像生成失败：API返回空结果")
                return

            if not generated_image:
                self.error.emit("图像生成失败：模型未返回图片数据")
                return

            # 保存生成的图片
            temp_dir = os.path.join(tempfile.gettempdir(), "artco_generated")
            os.makedirs(temp_dir, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            image_path = os.path.join(temp_dir, f"generated_{timestamp}.png")

            generated_image.save(image_path, "PNG")

            self.finished_image.emit(image_path)

        except Exception as e:
            self.error.emit(f"图像生成失败: {str(e)}")
            return

    def _run_openai_compatible_image_generation(self, api_key, base_url, model_id):
        """使用 OpenAI 兼容协议生成图像（支持 DALL-E、Venus 等自定义服务商）"""
        import os
        import tempfile
        from datetime import datetime
        from openai import OpenAI

        client_kwargs = {"api_key": api_key}
        if base_url:
            url = base_url.rstrip("/")
            for suffix in ["/chat/completions", "/v1/chat/completions", "/llmproxy/chat/completions"]:
                if url.endswith(suffix):
                    url = url[:-len(suffix)]
                    break
            client_kwargs["base_url"] = url

        client = OpenAI(**client_kwargs)

        try:
            # 优先尝试 images API（DALL-E 风格接口）
            image_url = None
            b64_data = None

            try:
                if self.base64_image:
                    import io
                    from PIL import Image
                    img_data = base64.b64decode(self.base64_image)
                    img = Image.open(io.BytesIO(img_data))
                    buf = io.BytesIO()
                    img.save(buf, format="PNG")
                    buf.seek(0)
                    # 设置 name 属性让 SDK 识别 mimetype
                    buf.name = "image.png"

                    response = client.images.edit(
                        model=model_id,
                        image=buf,
                        prompt=self.prompt,
                        n=1,
                    )
                else:
                    response = client.images.generate(
                        model=model_id,
                        prompt=self.prompt,
                        n=1,
                    )

                if response.data and len(response.data) > 0:
                    b64_data = response.data[0].b64_json
                    if not b64_data and hasattr(response.data[0], 'url'):
                        image_url = response.data[0].url
            except Exception:
                # images API 不支持该模型或参数，fallback 到 chat completions
                b64_data = None
                image_url = None

            # fallback：通过 chat completions 获取图片（如 Venus 的 qwen 等模型）
            if not b64_data and not image_url:
                response = client.chat.completions.create(
                    model=model_id,
                    messages=[
                        {
                            "role": "user",
                            "content": self.prompt
                        }
                    ],
                    max_tokens=4096,
                )
                content = response.choices[0].message.content
                # 尝试从文本回复中提取 base64 图片或 URL
                import re
                # 尝试提取 markdown 图片链接
                url_match = re.search(r'!\[.*?\]\((https?://[^\s)]+)\)', content)
                if url_match:
                    image_url = url_match.group(1)
                else:
                    # 尝试提取裸 URL
                    url_match = re.search(r'(https?://[^\s"\'<>]+\.(?:png|jpg|jpeg|webp))', content, re.IGNORECASE)
                    if url_match:
                        image_url = url_match.group(1)

                if not image_url:
                    self.error.emit(f"图像生成失败：模型未返回图片数据。回复内容: {content[:200]}")
                    return

            # 下载或解码图片
            temp_dir = os.path.join(tempfile.gettempdir(), "artco_generated")
            os.makedirs(temp_dir, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            image_path = os.path.join(temp_dir, f"generated_{timestamp}.png")

            if b64_data:
                from PIL import Image
                import io
                img = Image.open(io.BytesIO(base64.b64decode(b64_data)))
                img.save(image_path, "PNG")
            elif image_url:
                import requests
                from PIL import Image
                import io
                resp = requests.get(image_url, timeout=30)
                resp.raise_for_status()
                img = Image.open(io.BytesIO(resp.content))
                img.save(image_path, "PNG")

            self.finished_image.emit(image_path)

        except Exception as e:
            self.error.emit(f"图像生成失败: {str(e)}")
            return
