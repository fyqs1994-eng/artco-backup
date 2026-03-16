@echo off
:: Artco Shell Extension 安装脚本
:: 需要以管理员身份运行

echo ========================================
echo   Artco Shell Extension 安装程序
echo ========================================
echo.

:: 检查管理员权限
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [错误] 请以管理员身份运行此脚本！
    echo 右键点击此文件，选择"以管理员身份运行"
    pause
    exit /b 1
)

:: 设置路径
set "DLL_PATH=%~dp0bin\Release\ArtcoShellExtension.dll"
set "REGASM=%SystemRoot%\Microsoft.NET\Framework64\v4.0.30319\RegAsm.exe"

:: 检查 DLL 是否存在
if not exist "%DLL_PATH%" (
    echo [错误] 找不到 DLL 文件: %DLL_PATH%
    echo 请先编译项目（Release 模式）
    pause
    exit /b 1
)

:: 检查 RegAsm 是否存在
if not exist "%REGASM%" (
    set "REGASM=%SystemRoot%\Microsoft.NET\Framework\v4.0.30319\RegAsm.exe"
)

if not exist "%REGASM%" (
    echo [错误] 找不到 RegAsm.exe，请确保已安装 .NET Framework 4.8
    pause
    exit /b 1
)

echo [1/3] 正在注册 COM 组件...
"%REGASM%" "%DLL_PATH%" /codebase
if %errorLevel% neq 0 (
    echo [错误] COM 注册失败
    pause
    exit /b 1
)
echo [OK] COM 组件注册成功

echo.
echo [2/3] 正在刷新资源管理器...
taskkill /f /im explorer.exe >nul 2>&1
timeout /t 2 /nobreak >nul
start explorer.exe

echo.
echo [3/3] 正在清除缩略图缓存...
del /f /s /q "%LocalAppData%\Microsoft\Windows\Explorer\thumbcache_*.db" >nul 2>&1

echo.
echo ========================================
echo   安装完成！
echo ========================================
echo.
echo 如果缩略图没有立即更新，请：
echo 1. 重启资源管理器
echo 2. 或者注销后重新登录
echo.
pause
