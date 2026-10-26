@echo off
setlocal DisableDelayedExpansion
if exist "%~dp0.pipeline-state\polygon\batch.json" (
    call "%~dp0start.bat" resume %*
) else (
    call "%~dp0polygon_tool\launch_windows.cmd" resume %*
)
exit /b %errorlevel%
