@echo off
setlocal DisableDelayedExpansion
call "%~dp0launch_pipeline.cmd" %*
exit /b %errorlevel%
