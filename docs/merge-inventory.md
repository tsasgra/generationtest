# Đối chiếu hợp nhất hai nhánh

Mã nguồn, thư viện, thư mục mẫu và các chức năng của cả hai nhánh đã được đưa vào `main`. Theo yêu cầu gộp Start/Stop, chỉ giữ `start.bat` tự dừng, dọn và chạy mới; các chế độ riêng dùng CLI `pipeline.py`.
Các file trùng tên giữ chung một đường dẫn và hợp nhất chức năng. `.env` là ngoại lệ: khóa giữ cục bộ, Git dùng `.env.example`.

Nguồn ban đầu có **144 đường dẫn**. Bảng dưới ghi cách giữ hoặc gộp từng nhóm; `.env` chứa khóa được thay bằng mẫu trong Git.

| Nhánh | Commit nguồn | Số file |
| --- | --- | --- |
| `upload_img_to_gemini` | `0054f241743c012478a01457a5ad79829266d466` | 26 |
| `copy_info_on_polygon` | `7afd51eaa655a6ac2d1a44d03c54d532cffe03da` | 121 |

| File/nhóm file | Cách hợp nhất |
| --- | --- |
| `img/.gitkeep`, `img/img1`…`img/img10/.gitkeep` (11 file) | Giữ các thư mục ảnh từ nhánh Gemini. |
| `problem/problem1`…`problem/problem10` (100 file `.txt`) | Giữ nguyên các bộ mẫu trống từ nhánh Polygon; bộ chưa điền được bỏ qua khi chạy batch. |
| `.env` | Giữ cục bộ, không commit khóa. Thêm `.env.example` trống. |
| `.gitattributes` | Giữ mã nguồn; dùng phiên bản hợp nhất hiện tại. |
| `.gitignore` | Gộp các quy tắc dữ liệu/runtime của hai nhánh; giữ file test và mẫu cấu hình. |
| `README.md` | Hướng dẫn chung; giữ hướng dẫn chi tiết hai nhánh trong `docs/gemini.md` và `docs/polygon.md`. |
| `gemini_tool/__init__.py` | Giữ mã nguồn; dùng phiên bản hợp nhất hiện tại. |
| `gemini_tool/browser.py` | Giữ mã nguồn; dùng phiên bản hợp nhất hiện tại. |
| `gemini_tool/control.py` | Giữ mã nguồn; dùng phiên bản hợp nhất hiện tại. |
| `gemini_tool/images.py` | Giữ mã nguồn; dùng phiên bản hợp nhất hiện tại. |
| `gemini_tool/launch.py` | Giữ lệnh module cũ; dùng chung khởi động/reset với pipeline. |
| `gemini_tool/native.py` | Giữ mã nguồn; dùng phiên bản hợp nhất hiện tại. |
| `gemini_tool/parts.py` | Giữ mã nguồn; dùng phiên bản hợp nhất hiện tại. |
| `gemini_tool/state.py` | Giữ mã nguồn; dùng phiên bản hợp nhất hiện tại. |
| `gemini_tool/stop.py` | Giữ mã nguồn; dùng phiên bản hợp nhất hiện tại. |
| `gemini_upload.py` | Điểm vào cũ, gọi triển khai chung trong `gemini_tool/cli.py`. |
| `polygon_tool/__init__.py` | Giữ mã nguồn; dùng phiên bản hợp nhất hiện tại. |
| `polygon_tool/api.py` | Giữ mã nguồn; dùng phiên bản hợp nhất hiện tại. |
| `polygon_tool/batch.py` | Hợp nhất pipeline batch và BatchWorkflow tương thích checkpoint cũ. |
| `polygon_tool/credentials.py` | Giữ mã nguồn; dùng phiên bản hợp nhất hiện tại. |
| `polygon_tool/input.py` | Giữ parse một/nhiều bài, init_batch và thêm nhận diện bộ mẫu trống. |
| `polygon_tool/launch_windows.cmd` | Đã gộp vào `python pipeline.py polygon-legacy [auto|check|resume|stop]`. |
| `polygon_tool/problem_url.py` | Giữ mã nguồn; dùng phiên bản hợp nhất hiện tại. |
| `polygon_tool/samples.py` | Giữ mã nguồn; dùng phiên bản hợp nhất hiện tại. |
| `polygon_tool/stop.py` | Giữ mã nguồn; dùng phiên bản hợp nhất hiện tại. |
| `polygon_tool/workflow.py` | Giữ mã nguồn; dùng phiên bản hợp nhất hiện tại. |
| `polygon_upload.py` | Điểm vào cũ, gọi CLI một/nhiều bài trong `polygon_tool/cli.py`. |
| `requirements-browser.txt` | Giữ danh sách thư viện browser fallback. |
| `requirements-gemini.txt` | Dẫn tới requirements.txt để tránh lệch phiên bản. |
| `requirements.txt` | Hợp nhất thư viện cho luồng chung. |
| `start.bat` | Launcher Windows duy nhất: tự dừng lượt cũ, xóa checkpoint và chạy mới toàn bộ luồng; không có menu. |
| `start_check.bat` | Đã gộp vào `python pipeline.py polygon-legacy check`; kiểm tra ảnh dùng `python pipeline.py check`. |
| `start_gemini.bat` | Đã gộp vào `python pipeline.py gemini`. |
| `start_resume.bat` | Đã gộp vào `python pipeline.py resume`. |
| `stop.bat` | Dừng lượt cũ tự động khi mở `start.bat`; dừng riêng qua `python pipeline.py stop`, hoặc `python pipeline.py polygon-legacy stop` cho chế độ Polygon cũ. |
