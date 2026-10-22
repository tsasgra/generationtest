@echo off
setlocal DisableDelayedExpansion
call "%~dp0polygon_tool\launch_windows.cmd" gemini
exit /b %errorlevel%
