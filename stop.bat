@echo off
setlocal DisableDelayedExpansion
call "%~dp0start.bat" stop %*
exit /b %errorlevel%
