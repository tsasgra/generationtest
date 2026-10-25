@echo off
setlocal DisableDelayedExpansion
call "%~dp0launch_pipeline.cmd" resume %*
exit /b %errorlevel%
