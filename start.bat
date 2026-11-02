@echo off
setlocal DisableDelayedExpansion
chcp 65001 >nul
title Polygon Upload
set "POLYGON_EXIT_CODE=1"
set "POLYGON_PYTHON_ARGS="
pushd "%~dp0"
if errorlevel 1 goto folder_error

if not exist "polygon_upload.py" goto script_missing
if exist ".venv\Scripts\python.exe" goto try_venv
goto try_py

:try_venv
".venv\Scripts\python.exe" -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if errorlevel 1 goto try_py
set "POLYGON_PYTHON=%CD%\.venv\Scripts\python.exe"
goto start_upload

:try_py
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if errorlevel 1 goto try_python
set "POLYGON_PYTHON=py"
set "POLYGON_PYTHON_ARGS=-3"
goto start_upload

:try_python
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if errorlevel 1 goto python_missing
set "POLYGON_PYTHON=python"
goto start_upload

:start_upload
echo Đang dừng phiên cũ và dọn dữ liệu để chuẩn bị bài mới...
"%POLYGON_PYTHON%" %POLYGON_PYTHON_ARGS% "%CD%\polygon_upload.py" start
set "POLYGON_EXIT_CODE=%errorlevel%"
echo(
if not "%POLYGON_EXIT_CODE%"=="0" goto execution_failed
echo Đã hoàn tất. Kết quả đã lưu trong result.json và problem_url.txt.
goto done

:execution_failed
echo Chưa hoàn tất. Hãy xem thông báo lỗi phía trên.
echo Mở lại start.bat sẽ xóa checkpoint và kết quả cũ, giữ nguyên nội dung trong problem.
echo Nếu muốn tiếp tục bài đang dở, dùng lệnh resume được in khi upload lỗi.
goto done

:python_missing
echo Không tìm thấy Python 3.10 trở lên.
echo Cài Python từ https://www.python.org/downloads/windows/ rồi mở lại start.bat.
echo Khi cài, chọn Add python.exe to PATH nếu tùy chọn này xuất hiện.
goto done

:script_missing
echo Không tìm thấy polygon_upload.py. Hãy giữ nguyên cấu trúc thư mục repository.
goto done

:folder_error
echo Không mở được thư mục chứa script.
goto pause_and_exit

:done
popd
if "%POLYGON_EXIT_CODE%"=="0" exit /b 0

:pause_and_exit
echo(
echo Nhấn phím bất kỳ để đóng cửa sổ.
pause >nul
exit /b %POLYGON_EXIT_CODE%
