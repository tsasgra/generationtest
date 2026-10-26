# Đối chiếu hợp nhất hai nhánh

Các file mã nguồn, launcher, thư viện và thư mục mẫu của cả hai nhánh đều có trong `main`.
Các file trùng tên giữ chung một đường dẫn và hợp nhất chức năng. `.env` là ngoại lệ: khóa giữ cục bộ, Git dùng `.env.example`.

Tổng cộng: **144 đường dẫn nguồn; 143 đường dẫn được giữ trong Git và 1 file cấu hình bí mật được thay bằng mẫu.**

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
| `polygon_tool/launch_windows.cmd` | Giữ auto/check/resume/stop; dùng chung launcher Windows. |
| `polygon_tool/problem_url.py` | Giữ mã nguồn; dùng phiên bản hợp nhất hiện tại. |
| `polygon_tool/samples.py` | Giữ mã nguồn; dùng phiên bản hợp nhất hiện tại. |
| `polygon_tool/stop.py` | Giữ mã nguồn; dùng phiên bản hợp nhất hiện tại. |
| `polygon_tool/workflow.py` | Giữ mã nguồn; dùng phiên bản hợp nhất hiện tại. |
| `polygon_upload.py` | Điểm vào cũ, gọi CLI một/nhiều bài trong `polygon_tool/cli.py`. |
| `requirements-browser.txt` | Giữ danh sách thư viện browser fallback. |
| `requirements-gemini.txt` | Dẫn tới requirements.txt để tránh lệch phiên bản. |
| `requirements.txt` | Hợp nhất thư viện cho luồng chung. |
| `start.bat` | Mặc định chạy cả luồng; Start riêng của Polygon được giữ dưới tên `start_polygon.bat`. |
| `start_check.bat` | Giữ kiểm tra problem offline. Kiểm tra ảnh dùng `start.bat check`. |
| `start_gemini.bat` | Giữ mã nguồn; dùng phiên bản hợp nhất hiện tại. |
| `start_resume.bat` | Nhận checkpoint pipeline hoặc định dạng Polygon cũ. |
| `stop.bat` | Dừng luồng chung, giữ checkpoint; Stop/reset Polygon riêng được giữ ở `stop_polygon.bat`. |
