# Upload ảnh từ img lên Gemini

Mỗi lần chạy, script đọc ảnh trong `img/`, mở chat mới tại `gemini.google.com`
và đính kèm ảnh. Mặc định giữ trình duyệt mở để bạn nhập nội dung và bấm **Gửi**.
Chat nháp có ảnh chưa gửi có thể chưa xuất hiện trong lịch sử Gemini.
Nếu muốn gửi tự động, truyền `--prompt "Nội dung của bạn"`.

## Windows: bấm đúp để chạy

1. Cài Python **3.10+** và Google Chrome.
2. Đặt ảnh của bạn vào thư mục **`img`** cạnh `gemini_upload.py`.
3. Bấm đúp **`start_gemini.bat`**. Lần đầu script tạo `.venv-gemini` và cài thư viện.
4. Đăng nhập Google trong cửa sổ mở ra, hoàn tất màn hình chào mừng Gemini nếu có.
5. Chờ thông báo đủ ảnh, sau đó nhập yêu cầu và gửi trong Gemini.
6. Đóng các tab Gemini do script mở hoặc nhấn Ctrl+C để kết thúc.

Phiên đăng nhập lưu trong `.gemini-browser`, dùng lại ở lần chạy tiếp theo.
Không mở đồng thời hai script với cùng profile. Không dùng profile Chrome chính
của bạn cho `--profile`. Script không cần Gemini API key.

## Chạy bằng dòng lệnh

```powershell
py -3 -m venv .venv-gemini
.\.venv-gemini\Scripts\python.exe -m pip install -r requirements-gemini.txt
.\.venv-gemini\Scripts\python.exe gemini_upload.py
```

Kiểm tra ảnh offline hoặc gửi thêm nội dung:

```powershell
.\.venv-gemini\Scripts\python.exe gemini_upload.py --dry-run
.\.venv-gemini\Scripts\python.exe gemini_upload.py --prompt "Hãy đọc nội dung trong các ảnh này."
```

macOS/Linux dùng `python3 -m venv .venv-gemini`, sau đó thay đường dẫn Python
trên bằng `.venv-gemini/bin/python`. Cần phiên máy tính có giao diện.
Nếu dùng Edge, thêm `--browser msedge`. Nếu dùng Chromium của Playwright,
chạy `python -m playwright install chromium` bằng đúng Python của môi trường
đã cài thư viện, rồi thêm `--browser chromium`.

## Định dạng ảnh và số lượng

- Không lọc theo đuôi file: script nhận dạng nội dung bằng bộ giải mã, kể cả tên
  không có đuôi hoặc có đuôi viết hoa. Hỗ trợ các định dạng Pillow đọc được như
  PNG, JPEG, WebP, GIF, BMP, TIFF, ICO, PSD; thêm HEIC/HEIF bằng pillow-heif,
  AVIF bằng Pillow, SVG bằng resvg và nhiều định dạng RAW bằng LibRaw/rawpy.
- Mọi ảnh được chuyển thành PNG tạm thời, xoay theo EXIF và bỏ metadata.
  Ảnh gốc không bị sửa/xóa. GIF động, ảnh nhiều khung và TIFF nhiều trang chỉ lấy
  **khung/trang đầu**, có thông báo khi chuyển. SVG cần chứa đủ tài nguyên bên trong.
- Không thể bảo đảm mọi định dạng ảnh tồn tại đều đọc được. File hỏng, định dạng
  bộ giải mã không hỗ trợ hoặc file không phải ảnh sẽ làm script dừng trước khi
  mở Gemini, kèm tên file cần xử lý. Xuất file đó sang PNG/JPEG rồi chạy lại.
- Mặc định mỗi PNG tối đa **20 MiB**, mỗi chat tối đa **10 ảnh**. Nhiều hơn 10 ảnh
  được chia thành nhiều chat mới. `--batch-size 1` tạo một chat cho từng ảnh;
  `--batch-size` nhận giá trị 1–10. Gemini vẫn có hạn mức theo tài khoản tại thời điểm chạy.
- Ảnh được sắp theo đường dẫn (không phân biệt hoa thường); đặt tên `001`, `002`, ...
  nếu cần thứ tự. Mặc định chỉ đọc trực tiếp `img`; thêm `--recursive` để đọc thư mục con.
  Bỏ qua file/thư mục ẩn, `Thumbs.db` và `desktop.ini`.

Các tùy chọn khác: `--input THU_MUC`, `--login-timeout 600`,
`--upload-timeout 300`, `--max-file-mb 20`, `--profile THU_MUC_PROFILE`.
Thư mục `img` mặc định luôn nằm cạnh script, kể cả khi chạy từ thư mục khác.

## Khi Google chặn đăng nhập từ trình duyệt tự động

Có thể mở **một Chrome riêng** bằng lệnh sau trong CMD ở thư mục repository,
rồi đăng nhập Gemini thủ công trong cửa sổ đó:

```bat
"%ProgramFiles%\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="%CD%\.gemini-browser-cdp"
```

Nếu Chrome cài ở vị trí khác, thay đường dẫn đến `chrome.exe` cho đúng.
Sau đó chạy:

```powershell
.\.venv-gemini\Scripts\python.exe gemini_upload.py --cdp-url http://127.0.0.1:9222
```

Script tạo tab mới trong Chrome này, không đóng tab cũ hoặc trình duyệt CDP.
Chỉ mở cổng CDP trên máy của bạn. Việc đăng nhập, CAPTCHA hoặc xác minh tài khoản
do bạn thực hiện; script không vượt qua các bước đó.

## Git và giới hạn kiểm thử

`img/` chỉ có `.gitkeep` để giữ thư mục trống trên GitHub. Ảnh thật, profile/cookie,
môi trường Python, file test/example và dữ liệu kiểm thử không được thêm vào commit.
Nếu dùng `--input` hoặc `--profile` trỏ đến thư mục tự đặt trong repo, hãy thêm đường
dẫn đó vào `.gitignore` hoặc đặt nó ngoài repo.

Script kiểm tra toàn bộ ảnh trước khi mở Gemini, đợi đủ phần đính kèm và hết chỉ báo
đang tải, rồi mới báo đã đính kèm hoặc gửi prompt. Khi lỗi, script giữ tab để kiểm tra;
không tự gửi lại. Đóng tab để nhận thông báo lỗi cuối và exit code khác 0.
Ảnh đã gửi ở các chat trước đó vẫn tồn tại nếu chat tiếp theo gặp lỗi.

11 bài kiểm thử xử lý ảnh và trình duyệt đã đạt với dữ liệu/trang mô phỏng offline
trên Linux/Chromium. File `.bat` chưa được chạy trên Windows thật.
**Chưa xác minh end-to-end với tài khoản Gemini thật trong môi trường phát triển:**
môi trường không cho phép truy cập Gemini. Giao diện, hạn mức và chính sách đăng nhập
của Google có thể thay đổi; nếu không nhận diện được nút/ảnh, script sẽ báo lỗi.
