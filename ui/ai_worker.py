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

    def __init__(self, base64_image, prompt: str = None):
        super().__init__()
        self.base64_image = base64_image
        self.prompt = prompt or DEFAULT_PROMPT



    def run(self):
        try:
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
        else:
            self._run_openai_compatible_vision(provider_id, api_key, base_url, model_id)



    
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
            client_kwargs["base_url"] = base_url
        
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
        """图像生成模式 - 使用 Google Gemini 模型"""
        import os
        import tempfile
        from datetime import datetime
        from google import genai
        from google.genai import types
        from PIL import Image
        import io
        
        # 图像生成固定使用 Google provider
        api_key = ai_config.get_api_key("google")
        
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
        
        # 从配置读取图像生成模型
        image_gen_model = ai_config.get_image_gen_model()

        if not image_gen_model:
            self.error.emit("图像生成模型配置错误，请重新验证 API Key")
            return
        
        # 构建 Google SDK 要求的模型名格式 (添加 models/ 前缀)
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
