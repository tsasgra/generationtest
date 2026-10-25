@echo off
setlocal DisableDelayedExpansion
call "%~dp0launch_pipeline.cmd" check %*
exit /b %errorlevel%
