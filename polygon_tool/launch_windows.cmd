@echo off
setlocal DisableDelayedExpansion
chcp 65001 >nul
title Polygon Upload
set "POLYGON_EXIT_CODE=1"
set "POLYGON_PYTHON_ARGS="
pushd "%~dp0.."
if errorlevel 1 goto folder_error

if not exist "polygon_upload.py" goto script_missing
if exist ".venv\Scripts\python.exe" goto try_venv
goto try_py

:try_venv
".venv\Scripts\python.exe" -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if errorlevel 1 goto try_py
set "POLYGON_PYTHON=%CD%\.venv\Scripts\python.exe"
goto choose_action

:try_py
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if errorlevel 1 goto try_python
set "POLYGON_PYTHON=py"
set "POLYGON_PYTHON_ARGS=-3"
goto choose_action

:try_python
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if errorlevel 1 goto python_missing
set "POLYGON_PYTHON=python"
goto choose_action

:choose_action
if /i "%~1"=="stop" goto stop_upload
if /i "%~1"=="check" goto check_input
if /i "%~1"=="resume" goto resume_upload
if /i not "%~1"=="auto" goto invalid_action
if exist "run_state.json" goto resume_upload
echo Đang tải bài mới từ thư mục problem lên Polygon...
set "POLYGON_UPLOAD_ARGS=run --input problem --state run_state.json"
goto execute

:resume_upload
if not exist "run_state.json" goto state_missing
echo Đang tiếp tục bài trong run_state.json...
set "POLYGON_UPLOAD_ARGS=resume --state run_state.json"
goto execute

:check_input
echo Đang kiểm tra đầu vào trong problem. Bước này không tải lên Polygon.
set "POLYGON_UPLOAD_ARGS=run --input problem --dry-run"

:execute
echo(
"%POLYGON_PYTHON%" %POLYGON_PYTHON_ARGS% "polygon_upload.py" %POLYGON_UPLOAD_ARGS%
set "POLYGON_EXIT_CODE=%errorlevel%"
goto show_result

:stop_upload
echo Đang dừng Polygon Upload và xóa checkpoint để bắt đầu bài mới...
"%POLYGON_PYTHON%" %POLYGON_PYTHON_ARGS% -m polygon_tool.stop
set "POLYGON_EXIT_CODE=%errorlevel%"

:show_result
echo(
if not "%POLYGON_EXIT_CODE%"=="0" goto execution_failed
echo Đã hoàn tất. Xem kết quả phía trên.
goto done

:execution_failed
if /i "%~1"=="stop" goto stop_failed
echo Chưa hoàn tất. Hãy xem thông báo lỗi phía trên.
echo Giữ nguyên run_state.json nếu đã có; bấm start_resume.bat để tiếp tục sau khi xử lý lỗi.
goto done

:stop_failed
echo Chưa hoàn tất việc dừng và xóa checkpoint. Hãy xem lỗi phía trên rồi bấm stop.bat lại.
goto done

:python_missing
echo Không tìm thấy Python 3.10 trở lên.
echo Cài Python từ https://www.python.org/downloads/windows/ rồi mở lại file start.
echo Khi cài, chọn Add python.exe to PATH nếu tùy chọn này xuất hiện.
goto done

:state_missing
echo Chưa có run_state.json để tiếp tục. Bấm start.bat để chạy bài mới.
goto done

:script_missing
echo Không tìm thấy polygon_upload.py. Hãy giữ nguyên cấu trúc thư mục repository.
goto done

:invalid_action
echo Hãy mở start.bat, start_resume.bat, start_check.bat hoặc stop.bat ở thư mục chính.
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
exit /b %POLYGON_EXIT_CODE%
