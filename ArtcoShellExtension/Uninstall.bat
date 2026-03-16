@echo off
:: Artco Shell Extension 卸载脚本
:: 需要以管理员身份运行

echo ========================================
echo   Artco Shell Extension 卸载程序
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

:: 检查 RegAsm 是否存在
if not exist "%REGASM%" (
    set "REGASM=%SystemRoot%\Microsoft.NET\Framework\v4.0.30319\RegAsm.exe"
)

echo [1/3] 正在注销 COM 组件...
if exist "%DLL_PATH%" (
    "%REGASM%" "%DLL_PATH%" /unregister
    echo [OK] COM 组件已注销
) else (
    echo [跳过] DLL 文件不存在
)

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
echo   卸载完成！
echo ========================================
echo.
pause
