@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

cd /d "%~dp0"

:: PyInstaller 的 qtpy hook 会默认选 PyQt5，与本项目的 PySide6 冲突
set "QT_API=pyside6"

echo ============================================
echo   Artco 构建工具
echo ============================================
echo.

if "%1"=="" (
echo 用法:
echo   build.bat full     - 构建主程序（dist\Artco.exe）
echo   build.bat lite     - 构建精简版（dist\Artco_Lite.exe）
echo   build.bat all      - 构建两个版本
echo.
echo 说明: 两种模式均只内嵌 ai_config_empty.json（空 Key 模板），
echo       不含任何真实 API Key，真实配置在 exe 同目录的 ai_config.json。
    echo.
    goto :eof
)

if /i "%1"=="full" goto :build_full
if /i "%1"=="lite" goto :build_lite
if /i "%1"=="all" goto :build_all

echo [错误] 未知参数: %1
echo 可用参数: full / lite / all
goto :eof

:: ============================================
:: 构建正式版
:: ============================================
:build_full
echo 正在构建正式版 (Artco)...
echo.

echo [0/2] 构建更新替换程序 (ArtcoUpdater)...
pyinstaller ArtcoUpdater.spec --noconfirm
if errorlevel 1 (
    echo.
    echo [警告] ArtcoUpdater 构建失败，继续构建主程序（自动更新功能将不可用）
) else (
    echo       ArtcoUpdater.exe 已生成
)
echo.

echo [1/2] 构建正式版主程序...
pyinstaller Artco.spec --noconfirm
if errorlevel 1 (
    echo.
    echo [失败] 正式版构建失败！
    exit /b 1
)

echo.
echo [校验] 检查体积是否异常...
python "%~dp0check_build.py" "dist\Artco.exe"
if errorlevel 1 (
    echo.
    exit /b 1
)
echo.
echo [完成] 正式版已输出到 dist\Artco.exe
echo.
exit /b 0

:: ============================================
:: 构建脱敏版
:: ============================================
:build_lite
echo [1/2] 准备脱敏配置...

:: 创建临时目录
if not exist "_build_tmp" mkdir "_build_tmp"

:: 复制空 API Key 配置
copy /y "ai_config_empty.json" "_build_tmp\ai_config.json" >nul
echo       ai_config.json (API Key 已清空)

echo.
echo [2/2] 正在构建脱敏版 (Artco_Lite)...
echo.
pyinstaller Artco_Lite.spec --noconfirm
set BUILD_RESULT=%errorlevel%

:: 清理临时目录
rd /s /q "_build_tmp" 2>nul

if %BUILD_RESULT% neq 0 (
    echo.
    echo [失败] 脱敏版构建失败！
    exit /b 1
)

echo.
echo [完成] 脱敏版已输出到 dist\Artco_Lite.exe
echo.
exit /b 0

:: ============================================
:: 构建两个版本
:: ============================================
:build_all
echo.
echo ========== 构建正式版 ==========
call :build_full
if errorlevel 1 (
    echo [警告] 正式版构建失败，继续构建脱敏版...
)
echo.
echo ========== 构建脱敏版 ==========
call :build_lite
if errorlevel 1 (
    echo [警告] 脱敏版构建失败！
)
echo.
echo ============================================
echo   构建完成！
echo   dist\Artco.exe      - 正式版
echo   dist\Artco_Lite.exe - 脱敏版
echo ============================================
goto :eof
