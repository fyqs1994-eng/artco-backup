# Python 桌面应用专用 Skill 文件
name: python-desktop-app-development
description: Python 桌面应用开发专用规范，适用于 Windows/macOS/Linux 桌面软件，包含 GUI 架构、线程模型、系统托盘、快捷键、剪贴板、拖拽、打包发布与测试规范。
version: 1.0
author: ChatGPT
recommended_runtime: Python 3.11+
recommended_gui: PySide6
---

# Python Desktop App Development Skill

## 目标

该 Skill 用于指导开发者或 AI 助手以工程化方式开发 Python 桌面应用，适用于以下类型项目：

- 本地工具类 GUI 软件
- 系统托盘应用
- 剪贴板增强工具
- 文件处理桌面应用
- 自动化操作桌面工具
- 带拖拽功能的本地应用
- 图像/文本管理小工具
- 后台驻留型桌面程序

核心目标：

1. 输出可运行的桌面应用
2. 界面逻辑与业务逻辑分离
3. 主线程不阻塞，交互流畅
4. 支持日志、配置、异常处理
5. 可打包为可执行程序
6. 具备基本可维护性与可扩展性

---

## 适用范围

本 Skill 主要适用于：

- GUI 框架：`PySide6` / `PyQt6`
- 平台：Windows / macOS / Linux
- 应用形态：
  - 常规窗口应用
  - 浮动面板
  - 托盘应用
  - 后台监听工具
  - 快捷键唤起工具
  - 剪贴板历史工具
  - 拖拽输入/输出工具

不适用于：

- 纯 Web 前端
- 超大型跨团队企业桌面系统
- 重度 3D 渲染桌面程序
- 强依赖 C++ 原生 Qt 模块的大型复杂软件

---

## 默认技术选型

### Python 版本
- 默认使用 **Python 3.11+**

### GUI 框架
优先顺序：

1. **PySide6**（推荐）
   - 许可证相对友好
   - Qt 能力完整
   - 适合大多数桌面应用
2. **PyQt6**
   - 生态成熟
   - 某些资料更多
3. **Tkinter**
   - 仅用于极轻量原型
   - 不适合复杂拖拽、托盘、现代 UI

### 其他常用库
根据需求选择：

- 全局快捷键/键鼠监听：
  - `pynput`
  - `keyboard`（仅部分平台更方便，但兼容性需验证）
- 剪贴板：
  - 优先使用 Qt 自带 `QClipboard`
- 图片处理：
  - `Pillow`
- 数据库存储：
  - `sqlite3`
  - `SQLAlchemy`（中等项目）
- 配置：
  - `.env` + `python-dotenv`
  - 或 JSON / TOML / YAML 配置文件
- 日志：
  - Python 标准库 `logging`
- 打包：
  - `PyInstaller`
  - 如需更高性能和更难逆向可评估 `Nuitka`

---

## 开发前必须确认的需求

开始编码前，必须明确以下内容：

### 1. 平台范围
- Windows only
- macOS only
- Linux only
- 跨平台

### 2. 应用形态
- 普通主窗口
- 悬浮窗
- 无边框窗口
- 系统托盘后台应用
- 开机自启应用
- 全局快捷键唤起应用

### 3. 数据类型
- 纯文本
- 图片
- 文件
- 富文本
- 剪贴板内容
- 本地数据库记录

### 4. 关键交互
- 拖拽上传
- 拖拽导出
- 多选
- 搜索
- 历史记录
- 右键菜单
- 快捷键
- 悬浮显示
- 自动隐藏

### 5. 系统能力
- 托盘
- 通知
- 剪贴板监听
- 全局键鼠监听
- 文件关联
- 开机启动
- 后台驻留

### 6. 交付形式
- 源码
- 单文件 exe
- 安装包
- macOS app
- 便携版

如果以上内容不完整，应先提问澄清，再进行实现。

---

## 桌面应用开发总原则

### 原则 1：UI 与业务逻辑分离
不要把以下逻辑全部写进窗口类：

- 数据处理
- 文件读写
- 数据库存储
- 网络请求
- 配置加载
- 监听器管理

这些逻辑应拆分到 `services/`、`storage/`、`core/` 等模块。

### 原则 2：GUI 主线程不能阻塞
以下任务不得直接在 UI 主线程执行：

- 大文件读写
- 网络请求
- 批量图像处理
- 长时间监听初始化
- 数据导入导出
- 复杂扫描操作

应改为：

- `QThread`
- `QRunnable + QThreadPool`
- 或独立工作线程 + signal/slot 回传

### 原则 3：先做 MVP，再增强
优先做：

1. 最小可运行界面
2. 核心业务链路
3. 基础错误处理
4. 基础数据存储
5. 打包运行验证

然后再做：

- 动画
- 主题
- 高级快捷键
- 性能优化
- 更复杂状态管理

### 原则 4：优先兼容 Qt 原生能力
能用 Qt 自带能力解决的问题，优先不用额外三方库，例如：

- 剪贴板：`QClipboard`
- 拖拽：`QDrag`, `QMimeData`
- 定时器：`QTimer`
- 托盘：`QSystemTrayIcon`
- 设置存储：`QSettings`（轻量场景可选）

### 原则 5：平台相关逻辑必须隔离
与系统强相关的功能必须放在独立模块中，例如：

- Windows 开机启动
- macOS 权限请求
- 全局鼠标钩子
- 注册表
- 特定平台通知

建议统一放在：

- `platform/`
- 或 `services/platform/`

---

## 推荐架构

适合中小型桌面应用的推荐结构：

```text
project_name/
├─ README.md
├─ pyproject.toml
├─ .gitignore
├─ .env.example
├─ assets/
│  ├─ icons/
│  ├─ images/
│  └─ styles/
├─ src/
│  └─ app/
│     ├─ __init__.py
│     ├─ main.py
│     ├─ app.py
│     ├─ config.py
│     ├─ logger.py
│     ├─ constants.py
│     ├─ ui/
│     │  ├─ __init__.py
│     │  ├─ main_window.py
│     │  ├─ tray.py
│     │  ├─ dialogs/
│     │  ├─ widgets/
│     │  └─ styles.py
│     ├─ core/
│     │  ├─ __init__.py
│     │  ├─ models.py
│     │  ├─ events.py
│     │  └─ types.py
│     ├─ services/
│     │  ├─ __init__.py
│     │  ├─ clipboard_service.py
│     │  ├─ hotkey_service.py
│     │  ├─ history_service.py
│     │  ├─ dragdrop_service.py
│     │  └─ notification_service.py
│     ├─ storage/
│     │  ├─ __init__.py
│     │  ├─ database.py
│     │  ├─ repositories.py
│     │  └─ file_store.py
│     ├─ platform/
│     │  ├─ __init__.py
│     │  ├─ startup_windows.py
│     │  ├─ startup_macos.py
│     │  └─ startup_linux.py
│     ├─ workers/
│     │  ├─ __init__.py
│     │  └─ tasks.py
│     └─ utils/
│        ├─ __init__.py
│        ├─ paths.py
│        ├─ timeutils.py
│        └─ validators.py
├─ tests/
│  ├─ __init__.py
│  ├─ test_config.py
│  ├─ test_history_service.py
│  └─ test_storage.py
└─ scripts/
```

---

## 模块职责规范

### `main.py`
程序入口，仅负责：

- 初始化 QApplication
- 加载配置
- 初始化日志
- 创建主应用对象
- 启动事件循环

不要在这里写业务逻辑。

### `app.py`
应用装配层，负责：

- 创建主窗口
- 注册服务
- 初始化托盘
- 连接信号
- 管理应用生命周期

### `ui/`
仅负责：

- 界面布局
- 用户交互事件
- 展示状态
- 调用服务层接口
- 接收信号并更新 UI

不要在 UI 层直接做重型任务。

### `services/`
负责应用核心能力，例如：

- 剪贴板监听
- 快捷键注册
- 历史记录管理
- 文件导入导出
- 数据转换
- 拖拽生成 mime data

### `storage/`
负责：

- SQLite 读写
- JSON 文件读写
- 缓存
- 缩略图落盘
- 历史记录持久化

### `workers/`
负责后台任务，例如：

- 生成缩略图
- 扫描目录
- 导入大量记录
- 导出数据
- 异步加载图片

### `platform/`
负责系统特定功能，例如：

- 开机自启
- 注册系统协议
- 平台权限处理
- 系统级特殊兼容代码

---

## 推荐 UI 架构规则

桌面应用建议使用“轻量分层”：

- **UI 层**：界面与用户交互
- **Service 层**：业务能力
- **Storage 层**：数据持久化
- **Worker 层**：后台任务
- **Platform 层**：系统相关能力

如果项目较复杂，可进一步引入：

- Presenter / ViewModel
- Event Bus
- Command 模式

但小型桌面工具不要过度设计。

---

## 窗口设计规范

### 普通主窗口
适用于：

- 文件处理工具
- 管理类桌面应用
- 设置面板

### 无边框窗口
适用于：

- 悬浮面板
- 快捷唤出工具
- 搜索框
- 剪贴板历史弹窗

注意事项：

- 需自行处理拖动窗口
- 需处理焦点丢失自动隐藏
- 需处理 ESC 关闭/隐藏
- 需考虑阴影与圆角兼容

### 托盘应用
适用于：

- 后台长期运行
- 快捷呼出工具
- 自动监听型工具

必须具备：

- 托盘菜单
- 退出按钮
- 打开主界面入口
- 错误提示策略

---

## Qt 线程与事件规则

### 必须遵守

1. 所有 UI 更新必须在主线程执行
2. Worker 线程不得直接操作界面控件
3. 后台结果通过 `Signal` 回传
4. 长任务必须可取消或至少可感知状态
5. 线程对象生命周期要明确，避免提前销毁

### 推荐方式

#### 方式 A：QThread + Worker QObject
适合：
- 中长任务
- 可复用后台服务

#### 方式 B：QRunnable + QThreadPool
适合：
- 轻量批处理
- 一次性任务

### 禁止行为

- 在按钮回调里直接执行耗时文件扫描
- 在 `showEvent` 中加载大量图片
- 在主线程做同步网络请求
- 子线程中直接修改 `QLabel`, `QListWidget`, `QPixmap` 等 UI 对象

---

## 剪贴板开发规范

如果应用涉及剪贴板，遵循以下规则：

1. 优先使用 `QApplication.clipboard()`
2. 监听 `dataChanged` 信号
3. 对重复内容去重
4. 区分以下类型：
   - 文本
   - 图片
   - HTML
   - URL
   - 文件列表
5. 大图片建议落盘存储缩略图，避免内存膨胀
6. 历史记录需设最大条数
7. 监听时要防止“自己写入剪贴板又被再次采集”的循环

建议保存结构：

- id
- type
- content_text
- file_path
- image_path
- created_at
- source_app（如可获取）

---

## 拖拽（Drag & Drop）规范

### 拖入
如果支持拖入，需处理：

- 文本拖入
- 图片拖入
- 文件拖入
- 多文件拖入

优先判断 `mimeData()` 类型。

### 拖出
如果支持拖拽内容到外部应用，必须正确设置：

- `QMimeData.setText()`
- `QMimeData.setImageData()`
- `QMimeData.setUrls()`

### 规范要求

1. 卡片组件应封装拖拽逻辑
2. 拖拽前应有最小移动距离判断
3. 图片拖拽建议使用原图或临时文件路径
4. 文件拖拽建议使用 `QUrl.fromLocalFile`
5. 拖拽失败时不要导致程序异常

---

## 全局快捷键与全局监听规范

如果项目需要系统级快捷键或鼠标监听：

1. Qt 自身不一定能满足全局监听，需要额外库
2. 优先封装成独立服务：
   - `hotkey_service.py`
   - `mouse_hook_service.py`
3. 全局监听逻辑不得直接写在窗口类中
4. 监听事件触发 UI 时，必须通过信号切回主线程
5. 需要明确平台兼容性
6. 需要处理权限问题
7. 必须提供关闭监听和退出清理逻辑

### 推荐实践

- 使用 `pynput` 做键鼠监听
- 监听线程发信号给主窗口
- 主窗口根据鼠标位置弹出浮层

---

## 系统托盘规范

托盘应用必须具备以下能力：

1. 托盘图标
2. 打开主界面
3. 打开设置
4. 暂停/恢复监听（如适用）
5. 退出程序

### 规范要求

- 关闭主窗口时默认隐藏到托盘，而不是退出
- 退出动作必须明确调用清理逻辑
- 托盘图标丢失时应给出回退方案
- 托盘菜单命名清晰

---

## 配置管理规范

### 配置来源
建议按优先级读取：

1. 环境变量
2. 用户配置文件
3. 默认配置

### 推荐配置项

- APP_NAME
- APP_ENV
- LOG_LEVEL
- DATA_DIR
- DB_PATH
- MAX_HISTORY_ITEMS
- THUMBNAIL_DIR
- HOTKEY
- AUTO_START
- START_MINIMIZED
- THEME
- WINDOW_WIDTH
- WINDOW_HEIGHT

### 轻量桌面应用建议
优先选以下方案之一：

#### 方案 A：`dataclass + os.getenv`
适合小项目

#### 方案 B：JSON / TOML 配置
适合用户可编辑设置

#### 方案 C：`QSettings`
适合轻量偏 Qt 原生配置存储

---

## 数据持久化规范

### 小型桌面工具
优先推荐：

- 文本设置：JSON / TOML / QSettings
- 历史记录：SQLite
- 缩略图：本地文件目录

### 设计原则

1. 配置和业务数据分离
2. 大对象不直接塞数据库字段
3. 图片建议落盘，数据库保存路径
4. 删除历史记录时要同步清理文件
5. 程序启动应自动初始化数据目录

### 推荐目录

```text
data/
├─ app.db
├─ cache/
├─ thumbnails/
├─ temp/
└─ logs/
```

---

## 日志规范

### 日志要求

1. 程序启动必须初始化日志
2. 记录关键生命周期事件
3. 记录重要用户操作
4. 异常必须保留 traceback
5. 日志不要输出敏感信息

### 重点记录的内容

- 应用启动/退出
- 配置加载结果
- 托盘初始化
- 快捷键注册结果
- 剪贴板变化
- 数据库存储失败
- 线程任务异常
- 打包环境异常

### 日志级别建议

- DEBUG：调试细节
- INFO：生命周期与普通事件
- WARNING：可恢复问题
- ERROR：用户可感知错误
- EXCEPTION：带 traceback 的异常

---

## 错误处理规范

### 原则

1. 不静默吞异常
2. 对用户展示“可理解”的错误信息
3. 对开发者记录详细日志
4. UI 层捕获并提示
5. Service 层抛出业务可识别异常
6. Storage 层对 IO/数据库异常做包装

### 推荐策略

- 用户提示：简洁
- 日志记录：完整
- 错误分类：
  - 配置错误
  - 文件错误
  - 数据库错误
  - 平台权限错误
  - 快捷键注册错误
  - 剪贴板读取错误

---

## 资源文件规范

### 资源目录
统一放入：

- `assets/icons`
- `assets/images`
- `assets/styles`

### 规范要求

1. 图标命名清晰
2. 尽量提供多分辨率图标
3. 样式表单独管理
4. 路径读取应统一封装，避免相对路径混乱
5. 打包后资源路径要兼容

建议封装 `utils/paths.py` 统一获取资源目录。

---

## 样式与主题规范

### 原则

1. 样式集中管理
2. 不在每个控件里大量内联样式
3. 可用 QSS 统一定义
4. 深色/浅色主题需预留扩展能力

### 推荐方式

- 小项目：`styles.py` 中维护 QSS 字符串
- 中项目：独立 `.qss` 文件
- 动态主题：统一主题管理器

---

## 屏幕适配与 DPI 规范

桌面应用必须考虑：

1. 高 DPI 缩放
2. 不同分辨率窗口显示
3. 多显示器坐标兼容
4. 弹窗位置不越界
5. 跟随鼠标出现时处理边缘溢出

### 特别注意
悬浮窗或鼠标附近弹窗时：

- 不要直接 `move(x, y)` 就结束
- 要检查是否超出屏幕边界
- 必要时向左/向上偏移

---

## 交互设计建议

### 必备体验细节

1. 支持 ESC 关闭/隐藏浮窗
2. 支持回车执行主操作
3. 支持搜索框自动聚焦
4. 点击窗口外部自动隐藏
5. 耗时任务显示状态
6. 禁止重复提交
7. 关键动作有反馈

### 如果是后台驻留工具
建议支持：

- 首次启动引导
- 托盘右键菜单
- 快捷键说明
- 设置页
- 日志导出
- 版本信息

---

## 测试规范

桌面应用测试不要求完全 UI 自动化，但至少应覆盖：

### 必测内容

1. 配置加载
2. 数据存储读写
3. 核心业务逻辑
4. 历史记录去重逻辑
5. 数据迁移逻辑
6. 关键服务初始化逻辑

### 推荐内容

- 剪贴板处理函数测试
- 文本/图片类型识别测试
- SQLite repository 测试
- 配置路径生成测试

### 不建议
- 过早投入大量复杂 UI 自动化测试

### 如需 UI 测试
可评估：

- `pytest-qt`

---

## 性能规范

### 必须关注

1. 大图不要全部原图驻留内存
2. 列表不要无限增长
3. 大量卡片应懒加载或限制数量
4. 缩略图异步生成
5. 文件缓存定期清理
6. 搜索过滤要避免主线程卡顿

### 推荐策略

- 历史记录上限默认 50~200
- 图片显示缩略图
- 原图路径落盘
- 加载卡片分页或按需渲染

---

## 安全与权限规范

### 原则

1. 不信任外部输入
2. 文件路径要校验
3. 拖入文件要判断存在性和类型
4. 不记录敏感剪贴板内容到日志
5. 全局监听需提醒用户用途
6. 平台权限要求必须在 README 中说明

### 特别提醒
如果应用包含以下能力，应明确告知用户：

- 键盘监听
- 鼠标监听
- 剪贴板持续监听
- 开机自启
- 后台常驻

---

## 打包与发布规范

### Windows
优先：

- `PyInstaller`

示例：

```bash
pyinstaller -F -w --name MyDesktopApp src/app/main.py
```

如果有资源文件，需要补充：

```bash
pyinstaller -F -w --add-data "assets;assets" src/app/main.py
```

### macOS
可用：

- `PyInstaller`
- 或后续使用 `briefcase` / 原生打包流程

### 打包要求

1. 验证资源文件路径
2. 验证图标是否正确
3. 验证托盘是否工作
4. 验证多平台路径兼容
5. 验证首次启动数据目录创建
6. 验证日志目录是否可写

### 发布建议

- 提供便携版与安装版说明
- 提供已知问题列表
- 提供权限/兼容性说明

---

## README 规范

桌面应用 README 至少应包含：

1. 项目简介
2. 功能特性
3. 技术栈
4. 运行环境
5. 开发启动方式
6. 打包方式
7. 配置项说明
8. 常见问题
9. 平台兼容说明
10. 权限说明
11. 截图或录屏说明（建议）

如果是后台工具，额外补充：

- 如何呼出主界面
- 托盘图标说明
- 快捷键说明
- 如何退出程序
- 是否会监听剪贴板/键鼠

---

## AI 助手执行规则

当 AI 助手基于该 Skill 开发桌面应用时，必须遵守以下流程：

### 1. 先输出方案，不直接堆代码
必须先给出：

- 需求理解
- 技术栈选择
- 模块划分
- 文件结构
- 风险点
- MVP 开发顺序

### 2. 优先实现最小可运行版本
第一版必须满足：

- 能启动
- 有主窗口或托盘
- 核心能力贯通
- 至少有基础配置和日志

### 3. 输出代码时必须标明文件路径
例如：

- `src/app/main.py`
- `src/app/ui/main_window.py`
- `src/app/services/clipboard_service.py`

### 4. 不得把全部代码塞进一个文件
除非用户明确要求单文件原型。

### 5. 修 bug 时遵循最小改动原则
步骤应为：

1. 复现问题
2. 分析原因
3. 指出影响模块
4. 修改最少必要代码
5. 给出验证步骤

### 6. 功能开发顺序建议
桌面应用功能建议按如下顺序开发：

1. 程序入口
2. 主窗口/浮窗
3. 配置与日志
4. 基础业务服务
5. 数据持久化
6. 托盘/快捷键/监听
7. 拖拽和高级交互
8. 打包与发布

---

## 桌面应用专用默认交付清单

一个合格的 Python 桌面应用，默认应交付以下内容：

### 基础部分
- 项目目录结构
- `pyproject.toml`
- 可运行入口
- 配置模块
- 日志模块
- README

### 界面部分
- 主窗口
- 基础控件拆分
- 样式管理
- 图标资源

### 业务部分
- 至少一个 service
- 存储模块
- 基础异常处理

### 工程部分
- 至少 2~3 个基础测试
- 打包命令
- 运行说明

### 若为后台工具，还应交付
- 托盘菜单
- 退出逻辑
- 隐藏/显示逻辑
- 快捷键或监听模块
- 开机自启说明（如支持）

---

## 推荐基础模板

### `src/app/main.py`

```python
import sys
from PySide6.QtWidgets import QApplication
from app.app import DesktopApplication

def main() -> int:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    desktop_app = DesktopApplication(app)
    desktop_app.start()

    return app.exec()

if __name__ == "__main__":
    raise SystemExit(main())
```

### `src/app/app.py`

```python
from PySide6.QtWidgets import QApplication
from app.logger import setup_logger
from app.ui.main_window import MainWindow

class DesktopApplication:
    def __init__(self, qt_app: QApplication) -> None:
        self.qt_app = qt_app
        self.logger = setup_logger()
        self.main_window = MainWindow()

    def start(self) -> None:
        self.logger.info("Desktop application starting")
        self.main_window.show()
```

### `src/app/logger.py`

```python
import logging
from pathlib import Path

def setup_logger(level: str = "INFO") -> logging.Logger:
    log_dir = Path("data/logs")
    log_dir.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=[
            logging.FileHandler(log_dir / "app.log", encoding="utf-8"),
            logging.StreamHandler()
        ],
    )
    return logging.getLogger("app")
```

### `src/app/ui/main_window.py`

```python
from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QLabel

class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Python Desktop App")
        self.resize(900, 600)

        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.addWidget(QLabel("Hello Desktop App"))
        self.setCentralWidget(central)
```

---

## 后台任务模板示例

### `src/app/workers/tasks.py`

```python
from PySide6.QtCore import QObject, Signal, Slot

class ExampleWorker(QObject):
    finished = Signal()
    error = Signal(str)
    result_ready = Signal(object)

    @Slot()
    def run(self) -> None:
        try:
            result = {"status": "ok"}
            self.result_ready.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            self.finished.emit()
```

---

## 完成定义（Definition of Done）

一个 Python 桌面应用在满足以下条件时，视为完成：

1. 应用可正常启动
2. 主界面或托盘功能可用
3. 核心功能链路完整
4. 配置和日志已接入
5. UI 不因长任务明显卡死
6. 有基础异常处理
7. 有最小测试
8. 有 README 与运行说明
9. 能完成至少一次本地打包验证
10. 他人拿到项目后可按说明运行

---

## 推荐附加 Skill

在本 Skill 基础上，可再叠加更细分的 Skill：

- `python-clipboard-tool.skill.md`
- `python-tray-app.skill.md`
- `python-pyside6-ui.skill.md`
- `python-desktop-packaging.skill.md`
- `python-global-hotkey.skill.md`

---

## 结束原则

开发 Python 桌面应用时，优先遵循以下四条原则：

1. **先可运行，再做精致**
2. **先分层，再堆功能**
3. **主线程不阻塞**
4. **能打包交付才算完成**
```
