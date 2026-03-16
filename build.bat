@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

cd /d "%~dp0"

echo ============================================
echo   Artco 构建工具
echo ============================================
echo.

if "%1"=="" (
    echo 用法:
    echo   build.bat full     - 构建正式版（含 AI API Key）
    echo   build.bat lite     - 构建脱敏版（不含 AI API Key）
    echo   build.bat all      - 构建两个版本
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
pyinstaller Artco.spec --noconfirm
if errorlevel 1 (
    echo.
    echo [失败] 正式版构建失败！
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
echo [1/3] 准备脱敏配置...

:: 创建临时目录
if not exist "_build_tmp" mkdir "_build_tmp"

:: 复制空 API Key 配置
copy /y "ai_config_empty.json" "_build_tmp\ai_config.json" >nul
echo       ai_config.json (API Key 已清空)

:: 备份原文件
copy /y "supabase_client.py" "_build_tmp\supabase_client.py.bak" >nul

:: 用 Python 脱敏 supabase_client.py
python -c "import re; f=open('supabase_client.py','r',encoding='utf-8'); c=f.read(); f.close(); c=re.sub(r'os\.getenv\(\"VITE_SUPABASE_URL\",\s*\"[^\"]*\"\)','os.getenv(\"VITE_SUPABASE_URL\", \"\")',c); c=re.sub(r'os\.getenv\(\"VITE_SUPABASE_ANON_KEY\",\s*\"[^\"]*\"\)','os.getenv(\"VITE_SUPABASE_ANON_KEY\", \"\")',c); f=open('supabase_client.py','w',encoding='utf-8'); f.write(c); f.close(); print('      supabase_client.py (Supabase 凭证已清空)')"

echo.
echo [2/3] 正在构建脱敏版 (Artco_Lite)...
echo.
pyinstaller Artco_Lite.spec --noconfirm
set BUILD_RESULT=%errorlevel%

:: 还原 supabase_client.py
echo.
echo [3/3] 还原源文件...
copy /y "_build_tmp\supabase_client.py.bak" "supabase_client.py" >nul
echo       supabase_client.py 已还原

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
