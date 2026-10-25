@echo off
setlocal DisableDelayedExpansion
call "%~dp0launch_pipeline.cmd" run %*
exit /b %errorlevel%
