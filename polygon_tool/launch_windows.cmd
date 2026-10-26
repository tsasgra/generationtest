@echo off
setlocal DisableDelayedExpansion
call "%~dp0..\start.bat" polygon-legacy %*
exit /b %errorlevel%
