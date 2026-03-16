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
        """视觉分析模式 - 统一 OpenAI 兼容协议"""
        from openai import OpenAI
        
        provider = ai_config.get_current_provider()
        model_id = ai_config.get_current_model()
        
        if not provider:
            self.error.emit("请先在设置中添加 AI 服务商")
            return
        
        api_key = provider.get("api_key", "")
        base_url = provider.get("base_url", "")
        
        if not api_key:
            self.error.emit(f"请先在设置中配置 {provider.get('name', '')} 的 API Key")
            return
        
        # 构建 OpenAI 兼容客户端
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
        """图像生成模式 - 保留 Google 原生 SDK（OpenAI 协议不支持图生图）"""
        import os
        import tempfile
        from datetime import datetime
        from google import genai
        from google.genai import types
        
        # 图像生成固定使用 Google provider
        provider = ai_config.get_provider("google")
        api_key = provider.get("api_key", "") if provider else ""
        
        if not api_key:
            self.error.emit("图像生成需要配置 Google API Key")
            return
        
        client = genai.Client(api_key=api_key)
        
        contents = []
        
        if self.base64_image:
            image_data = base64.b64decode(self.base64_image)
            contents.append(types.Part.from_bytes(data=image_data, mime_type="image/png"))
        
        contents.append(self.prompt)
        
        # 从配置读取图像生成模型
        image_gen_model = ai_config.get_image_gen_model()
        
        response = client.models.generate_content(
            model=image_gen_model,
            contents=contents,
        )
        
        generated_image = None
        for part in response.parts:
            if part.inline_data:
                generated_image = part.as_image()
                break
        
        if not generated_image:
            self.error.emit("图像生成失败：模型未返回图片")
            return
        
        temp_dir = os.path.join(tempfile.gettempdir(), "artco_generated")
        os.makedirs(temp_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        image_path = os.path.join(temp_dir, f"generated_{timestamp}.png")
        
        generated_image.save(image_path)
        
        self.finished_image.emit(image_path)
