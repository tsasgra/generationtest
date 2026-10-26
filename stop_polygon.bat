@echo off
setlocal DisableDelayedExpansion
call "%~dp0polygon_tool\launch_windows.cmd" stop %*
exit /b %errorlevel%
