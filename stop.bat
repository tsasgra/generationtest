@echo off
setlocal DisableDelayedExpansion
call "%~dp0launch_pipeline.cmd" stop %*
exit /b %errorlevel%
