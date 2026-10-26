@echo off
setlocal DisableDelayedExpansion
call "%~dp0start.bat" gemini %*
exit /b %errorlevel%
