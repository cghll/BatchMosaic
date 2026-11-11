@echo off
setlocal
cd /d "%~dp0"

rem ---------------- 依赖检查：缺了就自动装 ----------------
python -c "import PySide6, PIL, numpy" >nul 2>nul
if not errorlevel 1 goto :deps_ok

echo [MaSai] 缺少依赖，正在自动安装，请稍候...
python -m pip install -r requirements.txt
if errorlevel 1 goto :install_failed
python -c "import PySide6, PIL, numpy" >nul 2>nul
if errorlevel 1 goto :install_failed
goto :deps_ok

:install_failed
echo.
echo [MaSai] 依赖安装失败。请手动执行：
echo     python -m pip install -r requirements.txt
echo.
echo 当前使用的 Python：
where python
echo.
pause
exit /b 1

:deps_ok
rem ---------------- 启动 ----------------
rem 正常双击：无控制台窗口；启动失败会弹窗并写入 masai_startup_error.log
rem 诊断模式：命令行执行 run.bat debug，保留控制台输出便于排错
if /i "%~1"=="debug" goto :debug

where pythonw >nul 2>nul
if errorlevel 1 goto :debug
start "" pythonw -m masai
goto :eof

:debug
python -m masai
if errorlevel 1 (
    echo.
    echo [MaSai] 程序异常退出，错误码 %errorlevel%
    pause
)
goto :eof
