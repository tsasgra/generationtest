@echo off
setlocal DisableDelayedExpansion
chcp 65001 >nul
title Gemini to Polygon - 10 Problems
set "PIPELINE_EXIT_CODE=1"
set "PYTHONUTF8=1"
pushd "%~dp0"
if errorlevel 1 goto folder_error
if not exist ".venv-gemini\Scripts\python.exe" goto try_py
".venv-gemini\Scripts\python.exe" -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if errorlevel 1 goto try_py
".venv-gemini\Scripts\python.exe" -m pipeline_launch %*
set "PIPELINE_EXIT_CODE=%errorlevel%"
goto done

:try_py
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if errorlevel 1 goto try_python
py -3 -m pipeline_launch %*
set "PIPELINE_EXIT_CODE=%errorlevel%"
goto done

:try_python
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if errorlevel 1 goto python_missing
python -m pipeline_launch %*
set "PIPELINE_EXIT_CODE=%errorlevel%"
goto done

:python_missing
echo Cần Python 3.10 trở lên. Cài từ https://www.python.org/downloads/windows/
echo Khi cài, chọn Add python.exe to PATH rồi mở lại file này.
goto done

:folder_error
echo Không mở được thư mục chứa script.
goto finish

:done
popd

:finish
echo(
echo Nhấn phím bất kỳ để đóng cửa sổ.
pause >nul
exit /b %PIPELINE_EXIT_CODE%
