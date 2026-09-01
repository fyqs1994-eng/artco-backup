"""
配置模块 - 存放全局配置和常量
"""

import os
import sys
import json
import shutil
import threading
import time

import requests

# --- 配置文件路径 ---
def get_app_dir():
    """获取应用数据目录（便携模式：exe 同目录）"""
    if getattr(sys, 'frozen', False):
        # PyInstaller 打包后 - 便携模式，使用 exe 所在目录
        app_dir = os.path.dirname(sys.executable)
    else:
        # 开发环境
        app_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 确保目录存在
    if not os.path.exists(app_dir):
        os.makedirs(app_dir)
    
    return app_dir

def get_bundle_dir():
    """获取打包资源目录"""
    if getattr(sys, 'frozen', False):
        # PyInstaller 打包后的临时解压目录
        return sys._MEIPASS
    else:
        return os.path.dirname(os.path.abspath(__file__))

def init_config_file(filename):
    """初始化配置文件（从打包资源复制到用户目录）"""
    app_dir = get_app_dir()
    user_file = os.path.join(app_dir, filename)
    
    # 如果用户目录没有配置文件，从打包资源复制
    if not os.path.exists(user_file):
        bundle_file = os.path.join(get_bundle_dir(), filename)
        if os.path.exists(bundle_file):
            shutil.copy(bundle_file, user_file)
    
    return user_file

CONFIG_DIR = get_app_dir()
HOTKEY_CONFIG_PATH = init_config_file("hotkeys.json")
AI_CONFIG_PATH = init_config_file("ai_config.json")
WORKSPACE_CONFIG_PATH = os.path.join(get_app_dir(), "workspace.json")

# --- AI 模型配置 ---
AI_MODELS = {
    "vision": [
        {"id": "gemini-2.0-flash", "name": "Gemini 2.0 Flash", "provider": "google"},
        {"id": "gemini-2.5-flash", "name": "Gemini 2.5 Flash", "provider": "google"},
        {"id": "gemini-1.5-pro", "name": "Gemini 1.5 Pro", "provider": "google"},
        {"id": "gpt-4o", "name": "GPT-4o", "provider": "openai"},
        {"id": "gpt-4o-mini", "name": "GPT-4o Mini", "provider": "openai"},
        {"id": "gpt-4-turbo", "name": "GPT-4 Turbo", "provider": "openai"},
        {"id": "claude-3-5-sonnet-20241022", "name": "Claude 3.5 Sonnet", "provider": "anthropic"},
    ],
    "image_gen": [
        {"id": "imagen-3.0-generate-001", "name": "Imagen 3.0", "provider": "google"},
        {"id": "imagen-3.0-generate-001-fast", "name": "Imagen 3.0 (快速)", "provider": "google"},
        {"id": "imagen-3.0-generate-001-ultra", "name": "Imagen 3.0 (超高清)", "provider": "google"},
    ]
}

# --- AI 服务商配置 ---
AI_PROVIDERS = {
    "google": {
        "name": "Google Gemini",
        "models": ["gemini-2.0-flash", "gemini-2.5-flash", "gemini-1.5-pro"],
        "key_url": "https://aistudio.google.com/app/apikey",
        "default_vision": "gemini-2.5-flash",
        "default_image_gen": "imagen-3.0-generate-001",
    },
    "openai": {
        "name": "OpenAI",
        "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"],
        "key_url": "https://platform.openai.com/api-keys",
        "default_vision": "gpt-4o-mini",
        "default_image_gen": "imagen-3.0-generate-001",  # OpenAI 图像生成使用 DALL-E，但暂不支持
    },
    "anthropic": {
        "name": "Anthropic Claude",
        "models": ["claude-3-5-sonnet-20241022"],
        "key_url": "https://console.anthropic.com/settings/keys",
        "default_vision": "claude-3-5-sonnet-20241022",
        "default_image_gen": "imagen-3.0-generate-001",  # Claude 不支持图像生成
    },
    "seedream": {
        "name": "Seedream",
        "models": ["seedream-3-0"],
        "key_url": "https://platform.seedream.io/",
        "default_vision": "seedream-3-0",
        "default_image_gen": "seedream-3-0",
    }
}

# --- 默认配置 ---
DEFAULT_AI_CONFIG = {
    "task_type": "vision",
    "vision_model": "gemini-2.5-flash",
    "image_gen_model": "imagen-3.0-generate-001",
    "enabled_providers": ["google", "openai", "anthropic", "seedream"],
    "current_provider": "google",
    "api_keys": {
        "google": "",
        "openai": "",
        "anthropic": "",
        "seedream": ""
    },
    "api_base_urls": {
        "google": "",
        "openai": "",
        "anthropic": "",
        "seedream": ""
    },
    "custom_providers": []
}

# --- 默认 Prompt ---
DEFAULT_PROMPT = "请详细分析这张图片的内容。如果是代码，请提取代码；如果是UI，请描述布局；如果是文字，请OCR识别。"


# ==================== 模型分类器 ====================

# OpenRouter 模型元数据缓存文件路径
_OPENROUTER_CACHE_PATH = os.path.join(CONFIG_DIR, "openrouter_models_cache.json")

# 关键词分类规则（用于 OpenRouter 未收录的模型）
_IMAGE_GEN_KEYWORDS = [
    "dall-e", "imagen", "seedream", "flux", "sdxl", "stable-diffusion",
    "midjourney", "kolors", "hunyuan-image", "wan", "cogview", "dall",
    "sd-", "sdxl", "playground", "ideogram", "recraft", "leo", "imagen",
    "gpt-image", "gpt-5-image", "nano-banana", "flux-kontext",
    "gemini-image", "imagen-4", "tongyi-image", "wanx",
]
_VISION_KEYWORDS = [
    "gpt-4o", "gpt-4-vision", "gpt-4-turbo", "gemini", "claude",
    "qwen-vl", "qwen2-vl", "qwen3-vl", "qwen2.5-vl", "qwen-vision",
    "internvl", "llava", "vision", "-vl", "vl-", "multimodal",
    "glm-4v", "glm-4.6v", "glm-4.5v", "hunyuan-vision", "hunyuan-turbo-vision",
    "pixtral", "moondream", "cogvlm", "mini-cpm", "minicpm",
]


class ModelClassifier:
    """模型分类器：基于 OpenRouter API + 关键词匹配的混合策略"""

    _instance = None
    _modality_cache = None  # {model_name: {"input": [...], "output": [...]}}
    _cache_timestamp = 0
    _cache_lock = threading.Lock()
    _fetch_lock = threading.Lock()
    _is_fetching = False

    # 缓存有效期：24小时
    _CACHE_TTL = 86400

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load_cache()
        return cls._instance

    def _load_cache(self):
        """从本地文件加载缓存的模型元数据"""
        try:
            if os.path.exists(_OPENROUTER_CACHE_PATH):
                with open(_OPENROUTER_CACHE_PATH, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self._modality_cache = data.get("models", {})
                    self._cache_timestamp = data.get("timestamp", 0)
        except Exception:
            self._modality_cache = {}
            self._cache_timestamp = 0

    def _save_cache(self):
        """保存模型元数据到本地文件"""
        try:
            with open(_OPENROUTER_CACHE_PATH, 'w', encoding='utf-8') as f:
                json.dump({
                    "models": self._modality_cache,
                    "timestamp": self._cache_timestamp,
                }, f, ensure_ascii=False)
        except Exception:
            pass

    def fetch_openrouter_models(self):
        """从 OpenRouter API 拉取模型列表并构建分类字典（同步）"""
        with self._fetch_lock:
            if self._is_fetching:
                return False
            self._is_fetching = True
        try:
            resp = requests.get(
                "https://openrouter.ai/api/v1/models",
                timeout=15,
                headers={"User-Agent": "Artco/1.0"},
            )
            if resp.status_code != 200:
                return False

            data = resp.json().get("data", [])
            cache = {}
            for model in data:
                model_id = model.get("id", "")
                if not model_id:
                    continue
                arch = model.get("architecture", {})
                input_mods = arch.get("input_modalities", [])
                output_mods = arch.get("output_modalities", [])

                # 存储多个别名形式以便匹配
                cache[model_id] = {
                    "input": input_mods,
                    "output": output_mods,
                }
                # 去掉 provider 前缀后的名字也存一份（如 qwen/qwen3-vl → qwen3-vl）
                if "/" in model_id:
                    short_name = model_id.split("/", 1)[1]
                    if short_name not in cache:
                        cache[short_name] = {
                            "input": input_mods,
                            "output": output_mods,
                        }

            with self._cache_lock:
                self._modality_cache = cache
                self._cache_timestamp = time.time()
                self._save_cache()

            return True
        except Exception:
            return False
        finally:
            with self._fetch_lock:
                self._is_fetching = False

    def fetch_async(self):
        """异步拉取 OpenRouter 模型（不阻塞 UI）"""
        if self._is_fetching:
            return
        t = threading.Thread(target=self.fetch_openrouter_models, daemon=True)
        t.start()

    def _is_cache_fresh(self):
        """检查缓存是否在有效期内"""
        if not self._modality_cache:
            return False
        return (time.time() - self._cache_timestamp) < self._CACHE_TTL

    def _lookup_openrouter(self, model_name):
        """在 OpenRouter 缓存中查找模型能力"""
        if not self._modality_cache:
            return None
        # 直接匹配
        entry = self._modality_cache.get(model_name)
        if entry:
            return entry
        # 不区分大小写匹配
        lower = model_name.lower()
        for key, val in self._modality_cache.items():
            if key.lower() == lower:
                return val
        return None

    def _match_keywords(self, model_name):
        """关键词匹配兜底"""
        lower = model_name.lower()

        # 图像生成关键词
        for kw in _IMAGE_GEN_KEYWORDS:
            if kw in lower:
                return "image_gen"

        # 视觉分析关键词
        for kw in _VISION_KEYWORDS:
            if kw in lower:
                return "vision"

        # 默认归为视觉分析（大多数现代 LLM 都支持图片输入）
        return "vision"

    def classify(self, model_name):
        """分类单个模型，返回 'vision' / 'image_gen' / 'both'"""
        if not model_name:
            return "vision"

        # 第一层：OpenRouter 缓存查找
        entry = self._lookup_openrouter(model_name)
        if entry:
            input_mods = entry.get("input", [])
            output_mods = entry.get("output", [])
            has_vision = "image" in input_mods
            has_image_gen = "image" in output_mods
            if has_vision and has_image_gen:
                return "both"
            elif has_image_gen:
                return "image_gen"
            elif has_vision:
                return "vision"
            # OpenRouter 有记录但不含 image modality → 纯文本模型
            # 降级到关键词匹配看是否能归类
            return self._match_keywords(model_name)

        # 第二层：关键词匹配
        return self._match_keywords(model_name)

    def classify_batch(self, model_names):
        """批量分类模型列表，返回 {"vision": [...], "image_gen": [...]}"""
        vision = []
        image_gen = []

        for name in model_names:
            if not name:
                continue
            category = self.classify(name)
            if category == "vision":
                vision.append(name)
            elif category == "image_gen":
                image_gen.append(name)
            elif category == "both":
                vision.append(name)
                image_gen.append(name)

        return {"vision": vision, "image_gen": image_gen}

    def ensure_cache_ready(self):
        """确保缓存可用：如果缓存过期或为空，触发异步拉取"""
        if not self._is_cache_fresh():
            self.fetch_async()


# 全局分类器实例
model_classifier = ModelClassifier()


class AIConfigManager:
    """AI 配置管理器"""
    _instance = None
    _config = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load_config()
        return cls._instance
    
    def _load_config(self):
        """加载配置"""
        if os.path.exists(AI_CONFIG_PATH):
            try:
                with open(AI_CONFIG_PATH, 'r', encoding='utf-8') as f:
                    self._config = json.load(f)
                # 合并默认配置（处理新增字段）
                for key, value in DEFAULT_AI_CONFIG.items():
                    if key not in self._config:
                        self._config[key] = value
                    elif isinstance(value, dict):
                        for k, v in value.items():
                            if k not in self._config[key]:
                                self._config[key][k] = v
            except Exception:
                self._config = DEFAULT_AI_CONFIG.copy()
        else:
            self._config = DEFAULT_AI_CONFIG.copy()
    
    def _save_config(self):
        """保存配置"""
        try:
            with open(AI_CONFIG_PATH, 'w', encoding='utf-8') as f:
                json.dump(self._config, f, indent=2, ensure_ascii=False)
        except Exception:
            pass
    
    def get(self, key, default=None):
        """获取配置项"""
        return self._config.get(key, default)
    
    def set(self, key, value):
        """设置配置项"""
        self._config[key] = value
        self._save_config()
    
    def get_api_key(self, provider):
        """获取指定提供商的 API Key"""
        return self._config.get("api_keys", {}).get(provider, "")
    
    def set_api_key(self, provider, key):
        """设置指定提供商的 API Key"""
        if "api_keys" not in self._config:
            self._config["api_keys"] = {}
        self._config["api_keys"][provider] = key
        self._save_config()
    
    def get_api_base_url(self, provider):
        """获取指定提供商的 API Base URL"""
        return self._config.get("api_base_urls", {}).get(provider, "")
    
    def set_api_base_url(self, provider, url):
        """设置指定提供商的 API Base URL"""
        if "api_base_urls" not in self._config:
            self._config["api_base_urls"] = {}
        self._config["api_base_urls"][provider] = url
        self._save_config()
    
    def get_current_model(self):
        """获取当前选择的模型"""
        task_type = self._config.get("task_type", "vision")
        if task_type == "vision":
            model = self._config.get("vision_model")
            return model if model else "gemini-2.5-flash"
        else:
            return self.get_image_gen_model()

    def get_image_gen_model(self):
        """获取图像生成模型"""
        model = self._config.get("image_gen_model")
        return model if model else "imagen-3.0-generate-001"

    def get_image_gen_provider(self):
        """获取图像生成模型所属的 provider"""
        return self._config.get("image_gen_provider", "google")
    
    def get_current_provider(self):
        """获取当前模型的提供商"""
        model_id = self.get_current_model()
        task_type = self._config.get("task_type", "vision")
        models = AI_MODELS.get(task_type, [])
        for model in models:
            if model["id"] == model_id:
                return model["provider"]
        return "google"

    # ========== 服务商列表管理 ==========
    def get_enabled_providers(self):
        """获取已启用的服务商列表"""
        return self._config.get("enabled_providers", [])

    def set_enabled_providers(self, providers):
        """设置已启用的服务商列表"""
        self._config["enabled_providers"] = providers
        self._save_config()

    def get_current_provider_selected(self):
        """获取当前选中的服务商"""
        provider = self._config.get("current_provider")
        return provider if provider else "google"

    def set_current_provider_selected(self, provider):
        """设置当前选中的服务商"""
        self._config["current_provider"] = provider
        self._save_config()

    def add_provider(self, provider):
        """添加服务商"""
        providers = self.get_enabled_providers()
        if provider not in providers:
            providers.append(provider)
            self.set_enabled_providers(providers)

    def remove_provider(self, provider):
        """移除服务商"""
        providers = self.get_enabled_providers()
        if provider in providers:
            providers.remove(provider)
            self.set_enabled_providers(providers)
        # 如果删除的是当前选中的服务商，切换到第一个
        if self.get_current_provider_selected() == provider:
            remaining = self.get_enabled_providers()
            if remaining:
                self.set_current_provider_selected(remaining[0])
            else:
                self.set_current_provider_selected("")

    # ========== 自定义服务商管理 ==========
    def get_custom_providers(self):
        """获取自定义服务商列表"""
        return self._config.get("custom_providers", [])

    def add_custom_provider(self, provider_id, name, base_url, key_url="",
                            vision_models=None, image_gen_models=None):
        """添加自定义服务商"""
        customs = self.get_custom_providers()
        entry = {
            "id": provider_id,
            "name": name,
            "base_url": base_url,
            "key_url": key_url,
            "vision_models": vision_models or [],
            "image_gen_models": image_gen_models or [],
        }
        customs.append(entry)
        self._config["custom_providers"] = customs
        # 同时启用该服务商
        self.add_provider(provider_id)
        self._save_config()

    def update_custom_provider(self, provider_id, name=None, base_url=None, key_url=None,
                               vision_models=None, image_gen_models=None):
        """更新自定义服务商信息"""
        customs = self.get_custom_providers()
        for c in customs:
            if c["id"] == provider_id:
                if name is not None:
                    c["name"] = name
                if base_url is not None:
                    c["base_url"] = base_url
                if key_url is not None:
                    c["key_url"] = key_url
                if vision_models is not None:
                    c["vision_models"] = vision_models
                if image_gen_models is not None:
                    c["image_gen_models"] = image_gen_models
                break
        self._config["custom_providers"] = customs
        self._save_config()

    def remove_custom_provider(self, provider_id):
        """删除自定义服务商记录"""
        customs = self.get_custom_providers()
        customs = [c for c in customs if c["id"] != provider_id]
        self._config["custom_providers"] = customs
        # 清理 api_keys / api_base_urls 中残留
        self._config.get("api_keys", {}).pop(provider_id, None)
        self._config.get("api_base_urls", {}).pop(provider_id, None)
        self._save_config()

    def get_custom_provider_info(self, provider_id):
        """获取单个自定义服务商信息"""
        for c in self.get_custom_providers():
            if c["id"] == provider_id:
                return c
        return None

    def is_custom_provider(self, provider_id):
        """判断是否为自定义服务商"""
        return self.get_custom_provider_info(provider_id) is not None


# 全局配置管理器实例
ai_config = AIConfigManager()


# ==================== 工作区配置 ====================

# 资源类型选项
RESOURCE_TYPES = ["KV", "拍脸", "海报", "界面"]

# 图片进度选项
IMAGE_PROGRESS = ["粗草", "精草", "预完成", "已完成"]

# 默认工作区配置
DEFAULT_WORKSPACE_CONFIG = {
    "workspace_path": "",  # 工作区根目录
    "recent_topics": [],   # 最近使用的主题（最多保留20个）
    "last_topic": "",      # 上次使用的主题
    "last_resource_type": "KV",  # 上次使用的资源类型
    "last_progress": "粗草",     # 上次使用的进度
}


class WorkspaceConfigManager:
    """工作区配置管理器"""
    _instance = None
    _config = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load_config()
        return cls._instance
    
    def _load_config(self):
        """加载配置"""
        if os.path.exists(WORKSPACE_CONFIG_PATH):
            try:
                with open(WORKSPACE_CONFIG_PATH, 'r', encoding='utf-8') as f:
                    self._config = json.load(f)
                # 合并默认配置
                for key, value in DEFAULT_WORKSPACE_CONFIG.items():
                    if key not in self._config:
                        self._config[key] = value
                self._config.pop("vendor_company", None)
            except Exception:
                self._config = DEFAULT_WORKSPACE_CONFIG.copy()
        else:
            self._config = DEFAULT_WORKSPACE_CONFIG.copy()
    
    def _save_config(self):
        """保存配置"""
        try:
            with open(WORKSPACE_CONFIG_PATH, 'w', encoding='utf-8') as f:
                json.dump(self._config, f, indent=2, ensure_ascii=False)
        except Exception:
            pass
    
    def get_workspace_path(self) -> str:
        """获取工作区路径"""
        return self._config.get("workspace_path", "")
    
    def set_workspace_path(self, path: str):
        """设置工作区路径"""
        self._config["workspace_path"] = path
        self._save_config()
    
    def is_workspace_configured(self) -> bool:
        """检查工作区是否已配置"""
        path = self.get_workspace_path()
        return bool(path) and os.path.isdir(path)

    def get_recent_topics(self) -> list:
        """获取最近使用的主题列表"""
        return self._config.get("recent_topics", [])
    
    def add_recent_topic(self, topic: str):
        """添加最近使用的主题"""
        topics = self._config.get("recent_topics", [])
        # 移除已存在的（避免重复）
        if topic in topics:
            topics.remove(topic)
        # 添加到开头
        topics.insert(0, topic)
        # 保留最近20个
        self._config["recent_topics"] = topics[:20]
        self._config["last_topic"] = topic
        self._save_config()
    
    def get_last_settings(self) -> dict:
        """获取上次使用的设置"""
        return {
            "topic": self._config.get("last_topic", ""),
            "resource_type": self._config.get("last_resource_type", "KV"),
            "progress": self._config.get("last_progress", "粗草"),
        }
    
    def save_last_settings(self, topic: str, resource_type: str, progress: str):
        """保存上次使用的设置"""
        self._config["last_topic"] = topic
        self._config["last_resource_type"] = resource_type
        self._config["last_progress"] = progress
        self.add_recent_topic(topic)
    
    def get_existing_topics(self) -> list:
        """获取工作区中已存在的主题文件夹"""
        workspace = self.get_workspace_path()
        if not workspace or not os.path.isdir(workspace):
            return []
        
        topics = []
        try:
            for name in os.listdir(workspace):
                full_path = os.path.join(workspace, name)
                if os.path.isdir(full_path) and not name.startswith('.'):
                    topics.append(name)
        except Exception:
            pass
        return sorted(topics)


# 全局工作区配置管理器实例
workspace_config = WorkspaceConfigManager()


# ==================== Photoshop 路径配置 ====================

PS_CONFIG_PATH = os.path.join(get_app_dir(), "ps_config.json")

def _find_ps_from_registry() -> str:
    """从 Windows 注册表查找 Photoshop 路径"""
    if sys.platform != 'win32':
        return ""
    
    try:
        import winreg
        
        # 尝试多个注册表位置
        registry_paths = [
            # Adobe Photoshop 各版本
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Adobe\Photoshop"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Adobe\Photoshop"),
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Adobe\Photoshop"),
        ]
        
        for hkey, path in registry_paths:
            try:
                with winreg.OpenKey(hkey, path) as key:
                    # 枚举子键（版本号）
                    i = 0
                    while True:
                        try:
                            version_key = winreg.EnumKey(key, i)
                            with winreg.OpenKey(key, version_key) as ver_key:
                                try:
                                    app_path, _ = winreg.QueryValueEx(ver_key, "ApplicationPath")
                                    ps_exe = os.path.join(app_path, "Photoshop.exe")
                                    if os.path.exists(ps_exe):
                                        return ps_exe
                                except FileNotFoundError:
                                    pass
                            i += 1
                        except OSError:
                            break
            except FileNotFoundError:
                continue
        
        # 尝试从 App Paths 查找
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, 
                               r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\Photoshop.exe") as key:
                path, _ = winreg.QueryValueEx(key, "")
                if os.path.exists(path):
                    return path
        except FileNotFoundError:
            pass
            
    except Exception:
        pass
    
    return ""


def _find_ps_from_common_paths() -> str:
    """从常见安装路径查找 Photoshop"""
    common_paths = [
        # 2024-2019 版本
        r"C:\Program Files\Adobe\Adobe Photoshop 2025\Photoshop.exe",
        r"C:\Program Files\Adobe\Adobe Photoshop 2024\Photoshop.exe",
        r"C:\Program Files\Adobe\Adobe Photoshop 2023\Photoshop.exe",
        r"C:\Program Files\Adobe\Adobe Photoshop 2022\Photoshop.exe",
        r"C:\Program Files\Adobe\Adobe Photoshop 2021\Photoshop.exe",
        r"C:\Program Files\Adobe\Adobe Photoshop 2020\Photoshop.exe",
        r"C:\Program Files\Adobe\Adobe Photoshop 2019\Photoshop.exe",
        r"C:\Program Files\Adobe\Adobe Photoshop CC 2019\Photoshop.exe",
        r"C:\Program Files\Adobe\Adobe Photoshop CC 2018\Photoshop.exe",
        r"C:\Program Files\Adobe\Adobe Photoshop CC 2017\Photoshop.exe",
        # CS 版本
        r"C:\Program Files\Adobe\Adobe Photoshop CS6 (64 Bit)\Photoshop.exe",
        r"C:\Program Files (x86)\Adobe\Adobe Photoshop CS6\Photoshop.exe",
        r"C:\Program Files\Adobe\Adobe Photoshop CS6\Photoshop.exe",
        # D 盘
        r"D:\Program Files\Adobe\Adobe Photoshop 2024\Photoshop.exe",
        r"D:\Program Files\Adobe\Adobe Photoshop 2023\Photoshop.exe",
        r"D:\Adobe\Adobe Photoshop 2024\Photoshop.exe",
        r"D:\Adobe\Adobe Photoshop 2023\Photoshop.exe",
    ]
    
    for path in common_paths:
        if os.path.exists(path):
            return path
    
    return ""


class PhotoshopConfigManager:
    """Photoshop 路径配置管理器"""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._config = None  # 确保实例变量被初始化
            cls._instance._load_config()
        return cls._instance
    
    def _load_config(self):
        """加载配置"""
        if os.path.exists(PS_CONFIG_PATH):
            try:
                with open(PS_CONFIG_PATH, 'r', encoding='utf-8') as f:
                    self._config = json.load(f)
            except Exception:
                self._config = {"ps_path": ""}
        else:
            self._config = {"ps_path": ""}
    
    def _save_config(self):
        """保存配置"""
        try:
            with open(PS_CONFIG_PATH, 'w', encoding='utf-8') as f:
                json.dump(self._config, f, indent=2, ensure_ascii=False)
        except Exception:
            pass
    
    def get_ps_path(self) -> str:
        """获取 Photoshop 路径，自动检测或返回已保存的路径"""
        saved_path = self._config.get("ps_path", "")
        
        # 如果有保存的路径且有效，直接返回
        if saved_path and os.path.exists(saved_path):
            return saved_path
        
        # 尝试自动检测
        # 1. 从注册表查找
        ps_path = _find_ps_from_registry()
        if ps_path:
            self.set_ps_path(ps_path)
            return ps_path
        
        # 2. 从常见路径查找
        ps_path = _find_ps_from_common_paths()
        if ps_path:
            self.set_ps_path(ps_path)
            return ps_path
        
        return ""
    
    def set_ps_path(self, path: str):
        """设置 Photoshop 路径"""
        self._config["ps_path"] = path
        self._save_config()
    
    def is_configured(self) -> bool:
        """检查是否已配置有效的 PS 路径"""
        path = self.get_ps_path()
        return bool(path) and os.path.exists(path)

    # 裁剪缩小功能设置
    def get_crop_shrink_enabled(self) -> bool:
        """获取裁剪缩小功能是否启用"""
        return self._config.get("crop_shrink_enabled", False)

    def set_crop_shrink_enabled(self, enabled: bool):
        """设置裁剪缩小功能是否启用"""
        self._config["crop_shrink_enabled"] = enabled
        self._save_config()

    def get_thumbnail_size(self) -> int:
        """获取缩略图大小"""
        return self._config.get("thumbnail_size", 64)

    def set_thumbnail_size(self, size: int):
        """设置缩略图大小"""
        self._config["thumbnail_size"] = size
        self._save_config()


# 全局 Photoshop 配置管理器实例
ps_config = PhotoshopConfigManager()


# ==================== 企业微信 Webhook 配置 ====================

WECOM_CONFIG_PATH = os.path.join(get_app_dir(), "wecom_config.json")

DEFAULT_WECOM_CONFIG = {
    "webhooks": [],  # 格式: [{"name": "群名", "url": "webhook url"}, ...]
    "last_used": ""  # 上次使用的 webhook name
}


class WeComConfigManager:
    """企业微信配置管理器"""
    _instance = None
    _config = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load_config()
        return cls._instance
    
    def _load_config(self):
        """加载配置"""
        if os.path.exists(WECOM_CONFIG_PATH):
            try:
                with open(WECOM_CONFIG_PATH, 'r', encoding='utf-8') as f:
                    self._config = json.load(f)
                # 合并默认配置
                for key, value in DEFAULT_WECOM_CONFIG.items():
                    if key not in self._config:
                        self._config[key] = value
            except Exception:
                self._config = DEFAULT_WECOM_CONFIG.copy()
        else:
            self._config = DEFAULT_WECOM_CONFIG.copy()
    
    def _save_config(self):
        """保存配置"""
        try:
            with open(WECOM_CONFIG_PATH, 'w', encoding='utf-8') as f:
                json.dump(self._config, f, indent=2, ensure_ascii=False)
        except Exception:
            pass
    
    def get_webhooks(self) -> list:
        """获取所有 webhook 配置"""
        return self._config.get("webhooks", [])
    
    def add_webhook(self, name: str, url: str):
        """添加 webhook"""
        webhooks = self._config.get("webhooks", [])
        # 检查是否已存在
        for wh in webhooks:
            if wh["name"] == name:
                wh["url"] = url
                self._save_config()
                return
        webhooks.append({"name": name, "url": url})
        self._config["webhooks"] = webhooks
        self._save_config()
    
    def remove_webhook(self, name: str):
        """移除 webhook"""
        webhooks = self._config.get("webhooks", [])
        self._config["webhooks"] = [wh for wh in webhooks if wh["name"] != name]
        self._save_config()
    
    def get_webhook_url(self, name: str) -> str:
        """根据名称获取 webhook URL"""
        for wh in self._config.get("webhooks", []):
            if wh["name"] == name:
                return wh["url"]
        return ""
    
    def get_last_used(self) -> str:
        """获取上次使用的 webhook"""
        return self._config.get("last_used", "")
    
    def set_last_used(self, name: str):
        """设置上次使用的 webhook"""
        self._config["last_used"] = name
        self._save_config()


# 全局企业微信配置管理器实例
wecom_config = WeComConfigManager()


# ════════════════════════════════════════════════════════════
# 外观配置 (浮窗背景渐变/图片自定义)
# ════════════════════════════════════════════════════════════

APPEARANCE_CONFIG_PATH = os.path.join(get_app_dir(), "appearance.json")

# 默认渐变方案：纯白
DEFAULT_GRADIENT = {
    "type": "gradient",          # "gradient" 或 "image"
    "direction": "diagonal",     # "diagonal" | "horizontal" | "vertical"
    "stops": [
        {"pos": 0.0,  "color": [255, 255, 255, 1.0]},
        {"pos": 1.0,  "color": [250, 250, 252, 1.0]},
    ],
    "border_radius": 12,
    "border": "1px solid rgba(255, 255, 255, 0.6)",
}

# 预设方案库
PRESET_SCHEMES = {
    "aurora": {
        "name": "极光蓝黄紫粉",
        "direction": "diagonal",
        "stops": [
            {"pos": 0.0,  "color": [120, 190, 255, 1.0]},
            {"pos": 0.33, "color": [255, 240, 170, 1.0]},
            {"pos": 0.66, "color": [190, 160, 245, 1.0]},
            {"pos": 1.0,  "color": [255, 180, 210, 1.0]},
        ],
    },
    "mint_sunset": {
        "name": "薄荷日落",
        "direction": "diagonal",
        "stops": [
            {"pos": 0.0,  "color": [200, 248, 225, 1.0]},
            {"pos": 0.35, "color": [205, 228, 253, 1.0]},
            {"pos": 0.7,  "color": [225, 195, 240, 1.0]},
            {"pos": 1.0,  "color": [242, 175, 200, 1.0]},
        ],
    },
    "ocean_breeze": {
        "name": "海风",
        "direction": "diagonal",
        "stops": [
            {"pos": 0.0,  "color": [170, 220, 240, 1.0]},
            {"pos": 0.5,  "color": [210, 240, 230, 1.0]},
            {"pos": 1.0,  "color": [240, 225, 200, 1.0]},
        ],
    },
    "warm_gray": {
        "name": "暖灰",
        "direction": "diagonal",
        "stops": [
            {"pos": 0.0,  "color": [245, 243, 240, 1.0]},
            {"pos": 1.0,  "color": [235, 230, 225, 1.0]},
        ],
    },
    "pure_white": {
        "name": "纯白",
        "direction": "diagonal",
        "stops": [
            {"pos": 0.0,  "color": [255, 255, 255, 1.0]},
            {"pos": 1.0,  "color": [250, 250, 252, 1.0]},
        ],
    },
}


class AppearanceConfigManager:
    """外观配置管理器 — 浮窗背景渐变 / 图片自定义"""
    _instance = None
    _config = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load_config()
        return cls._instance

    def _load_config(self):
        if os.path.exists(APPEARANCE_CONFIG_PATH):
            try:
                with open(APPEARANCE_CONFIG_PATH, 'r', encoding='utf-8') as f:
                    self._config = json.load(f)
                # 合并默认字段
                for key, value in DEFAULT_GRADIENT.items():
                    if key not in self._config:
                        self._config[key] = value
            except Exception:
                self._config = DEFAULT_GRADIENT.copy()
        else:
            self._config = DEFAULT_GRADIENT.copy()

    def _save_config(self):
        try:
            with open(APPEARANCE_CONFIG_PATH, 'w', encoding='utf-8') as f:
                json.dump(self._config, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def get_config(self) -> dict:
        return self._config

    def set_config(self, config: dict):
        self._config = config
        self._save_config()

    def get(self, key, default=None):
        return self._config.get(key, default)

    def set(self, key, value):
        self._config[key] = value
        self._save_config()

    def apply_preset(self, preset_id: str):
        """应用预设方案"""
        preset = PRESET_SCHEMES.get(preset_id)
        if preset:
            self._config["type"] = "gradient"
            self._config["direction"] = preset["direction"]
            self._config["stops"] = [s for s in preset["stops"]]
            self._save_config()

    def set_image(self, image_path: str):
        """设置为图片背景"""
        self._config["type"] = "image"
        self._config["image_path"] = image_path
        self._save_config()

    def set_gradient(self, direction: str, stops: list):
        """设置自定义渐变"""
        self._config["type"] = "gradient"
        self._config["direction"] = direction
        self._config["stops"] = stops
        self._save_config()

    def get_background_css(self, border_radius: int = 12, border: str = None) -> str:
        """生成 #container 背景的 QSS 片段"""
        if self._config.get("type") == "image" and self._config.get("image_path"):
            path = self._config["image_path"].replace("\\", "/")
            return f"background-image: url('{path}'); background-position: center; background-repeat: no-repeat; background-origin: content;"

        direction = self._config.get("direction", "diagonal")
        if direction == "horizontal":
            x1, y1, x2, y2 = 0, 0, 1, 0
        elif direction == "vertical":
            x1, y1, x2, y2 = 0, 0, 0, 1
        else:
            x1, y1, x2, y2 = 0, 0, 1, 1

        stops = self._config.get("stops", [])
        if not stops:
            stops = DEFAULT_GRADIENT["stops"]

        stop_strs = []
        for s in stops:
            pos = s.get("pos", 0)
            c = s.get("color", [255, 255, 255, 1.0])
            r, g, b = int(c[0]), int(c[1]), int(c[2])
            a = c[3] if len(c) > 3 else 1.0
            stop_strs.append(f"stop:{pos} rgba({r}, {g}, {b}, {a})")

        stops_css = ",\n                    ".join(stop_strs)
        return f"background: qlineargradient(x1:{x1}, y1:{y1}, x2:{x2}, y2:{y2},\n                    {stops_css});"

    def get_border_css(self) -> str:
        return self._config.get("border", DEFAULT_GRADIENT["border"])

    def get_border_radius(self) -> int:
        return self._config.get("border_radius", 12)


# 全局外观配置管理器实例
appearance_config = AppearanceConfigManager()
