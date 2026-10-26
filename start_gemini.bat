@echo off
setlocal DisableDelayedExpansion
call "%~dp0launch_pipeline.cmd" gemini %*
exit /b %errorlevel%
