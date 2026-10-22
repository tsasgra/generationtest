@echo off
setlocal DisableDelayedExpansion
chcp 65001 >nul
title Gemini Export
set "GEMINI_EXIT_CODE=1"
set "GEMINI_PYTHON_ARGS="
pushd "%~dp0"
if errorlevel 1 goto folder_error

if not exist "gemini_export.py" goto script_missing
if exist ".venv\Scripts\python.exe" goto try_venv
goto try_py

:try_venv
".venv\Scripts\python.exe" -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if errorlevel 1 goto try_py
set "GEMINI_PYTHON=%CD%\.venv\Scripts\python.exe"
goto prepare_browser

:try_py
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if errorlevel 1 goto try_python
set "GEMINI_PYTHON=py"
set "GEMINI_PYTHON_ARGS=-3"
goto prepare_browser

:try_python
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if errorlevel 1 goto python_missing
set "GEMINI_PYTHON=python"

:prepare_browser
"%GEMINI_PYTHON%" %GEMINI_PYTHON_ARGS% -c "import playwright.sync_api" >nul 2>&1
if not errorlevel 1 goto execute
echo Đang cài thư viện Playwright để đọc Gemini...
"%GEMINI_PYTHON%" %GEMINI_PYTHON_ARGS% -m pip install -r requirements.txt
if errorlevel 1 goto install_failed

:execute
echo Đang sao chép Part 1–10 từ Gemini vào thư mục problem...
echo Bộ 10 file trong problem sẽ được thay sau khi đọc và kiểm tra đủ nội dung.
"%GEMINI_PYTHON%" %GEMINI_PYTHON_ARGS% "gemini_export.py" --output problem --overwrite
set "GEMINI_EXIT_CODE=%errorlevel%"
echo(
if not "%GEMINI_EXIT_CODE%"=="0" goto export_failed
echo Đã xuất xong 10 file. Mở thư mục problem để xem kết quả.
goto done

:export_failed
echo Chưa xuất được 10 file. Xem lỗi phía trên; có thể dùng --from-file theo README.
goto done

:install_failed
echo Không cài được Playwright. Kiểm tra kết nối mạng rồi chạy lại.
goto done

:python_missing
echo Không tìm thấy Python 3.10 trở lên.
echo Cài Python từ https://www.python.org/downloads/windows/ rồi mở lại file này.
echo Khi cài, chọn Add python.exe to PATH nếu tùy chọn này xuất hiện.
goto done

:script_missing
echo Không tìm thấy gemini_export.py. Hãy giữ nguyên cấu trúc repository.
goto done

:folder_error
echo Không mở được thư mục chứa script.
goto pause_and_exit

:done
popd

:pause_and_exit
echo(
echo Nhấn phím bất kỳ để đóng cửa sổ.
pause >nul
exit /b %GEMINI_EXIT_CODE%
