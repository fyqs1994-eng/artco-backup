"""
配置模块 - 存放全局配置和常量
"""

import os
import sys
import json
import shutil

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
        {"id": "gemini-2.5-flash", "name": "Gemini 2.5 Flash", "provider": "google"},
        {"id": "gemini-2.0-flash", "name": "Gemini 2.0 Flash", "provider": "google"},
    ]
}

# --- 默认配置 ---
DEFAULT_AI_CONFIG = {
    "task_type": "vision",
    "vision_model": "gemini-2.5-flash",
    "image_gen_model": "gemini-2.5-flash",
    "api_keys": {
        "google": "",
        "openai": "",
        "anthropic": ""
    },
    "api_base_urls": {
        "google": "",
        "openai": "",
        "anthropic": ""
    }
}

# --- 默认 Prompt ---
DEFAULT_PROMPT = "请详细分析这张图片的内容。如果是代码，请提取代码；如果是UI，请描述布局；如果是文字，请OCR识别。"


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
            return self._config.get("vision_model", "gemini-2.5-flash")
        else:
            return self._config.get("image_gen_model", "dall-e-3")
    
    def get_current_provider(self):
        """获取当前模型的提供商"""
        model_id = self.get_current_model()
        task_type = self._config.get("task_type", "vision")
        models = AI_MODELS.get(task_type, [])
        for model in models:
            if model["id"] == model_id:
                return model["provider"]
        return "google"


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
    "vendor_company": "",  # 供应商公司名称（用于提交/协作分流）
    "vendor_id": "",       # 供应商 UUID（关联 Supabase vendors 表）
    "vendor_name": "",     # 供应商名称（缓存，避免重复查询）
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

    def get_vendor_company(self) -> str:
        """获取供应商公司名称（用于提交/协作分流）"""
        return (self._config.get("vendor_company") or "").strip()

    def set_vendor_company(self, name: str):
        """设置供应商公司名称"""
        self._config["vendor_company"] = (name or "").strip()
        self._save_config()
    
    def get_vendor_id(self) -> str:
        """获取供应商 UUID"""
        return self._config.get("vendor_id", "")
    
    def set_vendor_id(self, vendor_id: str):
        """设置供应商 UUID"""
        self._config["vendor_id"] = vendor_id or ""
        self._save_config()
    
    def get_vendor_name(self) -> str:
        """获取供应商名称"""
        return self._config.get("vendor_name", "")
    
    def set_vendor_name(self, vendor_name: str):
        """设置供应商名称"""
        self._config["vendor_name"] = vendor_name or ""
        self._save_config()
    
    def set_vendor(self, vendor_id: str, vendor_name: str):
        """设置供应商身份（同时设置 ID 和名称）"""
        self._config["vendor_id"] = vendor_id or ""
        self._config["vendor_name"] = vendor_name or ""
        self._save_config()
    
    def is_vendor_configured(self) -> bool:
        """检查是否已配置供应商身份"""
        return bool(self.get_vendor_id())
    
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
    _config = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
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
