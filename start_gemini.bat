@echo off
setlocal DisableDelayedExpansion
chcp 65001 >nul
title Gemini Image Upload
set "GEMINI_EXIT_CODE=1"
set "PYTHONUTF8=1"
pushd "%~dp0"
if errorlevel 1 goto folder_error
if exist ".venv-gemini\Scripts\python.exe" goto dependencies

py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if errorlevel 1 goto try_python
py -3 -m venv .venv-gemini
if errorlevel 1 goto failed
goto dependencies

:try_python
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if errorlevel 1 goto python_missing
python -m venv .venv-gemini
if errorlevel 1 goto failed

:dependencies
".venv-gemini\Scripts\python.exe" -c "import playwright.sync_api, PIL, pillow_heif, resvg_py, rawpy" >nul 2>&1
if not errorlevel 1 goto run
echo Đang cài thư viện cho Gemini...
".venv-gemini\Scripts\python.exe" -m pip install -r requirements-gemini.txt
if errorlevel 1 goto failed

:run
".venv-gemini\Scripts\python.exe" -u gemini_upload.py %*
set "GEMINI_EXIT_CODE=%errorlevel%"
goto done

:python_missing
echo Cần Python 3.10 trở lên. Cài từ https://www.python.org/downloads/windows/
echo Khi cài, chọn Add python.exe to PATH rồi mở lại file này.
goto done

:failed
echo Chưa chạy được. Xem lỗi cài đặt phía trên rồi thử lại.
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
exit /b %GEMINI_EXIT_CODE%
