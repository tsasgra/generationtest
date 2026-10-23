# Tự tải ảnh trong img lên Gemini

Đặt ảnh vào **`img/`** rồi chạy **`start_gemini.bat`**. Script tự nhận dạng ảnh
theo nội dung file, mở chat mới, gửi ảnh và **xóa ảnh gốc đã xác nhận gửi thành công**.
Script giữ các tab Gemini mở để bạn xem kết quả; đóng tab hoặc nhấn Ctrl+C khi xong.

## Windows: lần chạy đầu

1. Cài Python **3.10+** và Google Chrome hoặc Microsoft Edge bản cập nhật.
2. Đặt ảnh vào `img`, cạnh `gemini_upload.py`, rồi bấm đúp `start_gemini.bat`.
   File chạy tự tạo `.venv-gemini` và cài thư viện cần thiết.
3. Đăng nhập Google trong cửa sổ Chrome/Edge được mở. Script chờ đăng nhập trước khi kết nối tự động.
4. Khi ô chat sẵn sàng, script tự gửi ảnh, kiểm tra chat đã lưu và xóa ảnh đã xác nhận.
5. Xem kết quả rồi đóng các tab Gemini do script mở hoặc nhấn Ctrl+C.

Lần sau chỉ cần thêm ảnh vào `img` và chạy lại. Phiên đăng nhập được giữ trong
`.gemini-browser-native/chrome` hoặc `.gemini-browser-native/edge`, giống nhánh `copy_info_on_gemini`.
Không chạy hai bản script cùng lúc hoặc chỉnh sửa/di chuyển ảnh khi đang chạy.

## Trình duyệt từ copy_info_on_gemini

Phần mở trình duyệt được chuyển từ
[`gemini_export.bat` của nhánh `copy_info_on_gemini`](https://github.com/tsasgra/generationtest/blob/e5ee49144ef20f7d5b02e8aa31b69f8056a0125c/gemini_export.bat).
Chỉ cần chạy **`start_gemini.bat`**, không cần chọn Python hoặc trình duyệt bằng tham số.

1. Tìm **Google Chrome đã cài trên máy**, dùng Microsoft Edge nếu không tìm thấy Chrome.
2. Mở trực tiếp trình duyệt đó bằng `subprocess.Popen`, với profile riêng và cổng
   kết nối chỉ ở `127.0.0.1`.
3. Mở trang đăng nhập Google `accounts.google.com/ServiceLogin`, trỏ về Gemini.
   Bạn tự nhập tài khoản trong giao diện Google; script chờ tab mới quay về Gemini.
4. **Sau bước này** mới khởi động Playwright và kết nối qua CDP. Script tiếp tục chờ
   ô chat sẵn sàng, mở chat mới, tải và gửi ảnh.

Cách này dùng Chrome/Edge của máy, không tải hoặc mở Chromium đi kèm Playwright.
Không có bước giả mạo user-agent, tắt kiểm tra bảo mật hay đọc mật khẩu/cookie.
Nếu Google vẫn chuyển đến trang “Couldn't sign you in”, script báo ngay và giữ ảnh.
Chưa thể bảo đảm Google chấp nhận đăng nhập trên mọi máy/tài khoản.

Dùng `start_gemini.bat --browser-info` để xem tên, đường dẫn và profile trình duyệt
sẽ dùng; lệnh này không cần ảnh và không mở trình duyệt.
Các tùy chọn cũ `--polygon-python`, `--login`, `--browser`, `--browser-path`,
`--cdp-url` không còn dùng. Khi cập nhật từ bản trước, chạy lại BAT không kèm chúng.

Nếu chuyển nhánh trong **cùng thư mục** đã chạy bản `copy_info_on_gemini`, profile
`.gemini-browser-native` có thể được dùng lại. Nếu hai bản nằm ở hai thư mục khác
nhau, mỗi bản giữ phiên riêng. Không chạy đồng thời hai công cụ dùng cùng profile.
Script chỉ đóng cửa sổ của profile riêng sau khi bạn xem xong các tab kết quả;
cửa sổ Chrome/Edge cá nhân không thuộc profile này.

## Khi nào ảnh bị xóa?

Mỗi nhóm tối đa **10 ảnh** được gửi vào một chat mới, kèm nội dung mặc định
`Ảnh được tải lên từ thư mục img.`. Script đợi tin nhắn có đủ ảnh, **tải lại chat**,
và phải thấy lại tin nhắn cùng ảnh trong chat đã lưu rồi mới xóa file tương ứng.
Chỉ thấy ảnh trong ô soạn thảo chưa đủ điều kiện xóa.

- Chỉ xóa file thuộc nhóm đã gửi và có nội dung/thông tin file khớp bản đã tải.
  File mới thêm vào `img`, file thay đổi trong lúc chạy và `.gitkeep` được giữ lại.
- Lỗi đăng nhập, tải ảnh, gửi tin nhắn hoặc không xác nhận được sau khi tải lại:
  giữ ảnh chưa xác nhận và trả lỗi. Không tự gửi lại; kiểm tra chat trước khi chạy lại
  nếu lần trước đã bấm Gửi, để tránh gửi trùng.
- Nếu nhóm trước thành công nhưng nhóm sau lỗi, chỉ ảnh của nhóm trước đã bị xóa.
- File không phải ảnh, hỏng hoặc chưa hỗ trợ được bỏ qua và giữ nguyên; ảnh hợp lệ
  khác vẫn được xử lý. Nếu không có ảnh hợp lệ, không mở trình duyệt.
- GIF động/TIFF nhiều trang chỉ chuyển khung/trang đầu, nên **giữ bản gốc nhiều
  khung/trang** để không xóa phần chưa tải. Script báo rõ trường hợp này.
- Xóa trực tiếp khỏi ổ đĩa, không đưa vào thùng rác. Dùng `--keep-images` để giữ bản gốc.

## Tùy chọn thường dùng

```bat
start_gemini.bat --dry-run
start_gemini.bat --prompt "Hãy đọc nội dung trong các ảnh này."
start_gemini.bat --keep-images
start_gemini.bat --attach-only
```

`--dry-run` nhận diện và kiểm tra ảnh offline, không mở trình duyệt hoặc xóa ảnh.
`--attach-only` chỉ đính kèm, không gửi và không xóa ảnh; bạn tự thao tác trong Gemini.
`--prompt` thay nội dung gửi kèm. `--recursive` đọc cả các thư mục con trong `img`.

Các tùy chọn khác: `--input THU_MUC`, `--batch-size 1` (1–10),
`--upload-timeout 300`, `--login-timeout 600`, `--max-file-mb 20`,
`--profile THU_MUC_RIENG`.
`img` mặc định luôn nằm cạnh script, kể cả khi chạy từ thư mục khác.

Script hỗ trợ ảnh mà Pillow đọc được như PNG, JPEG, WebP, BMP, GIF, TIFF, ICO, PSD;
thêm HEIC/HEIF, AVIF, SVG và nhiều định dạng RAW qua các bộ giải mã đi kèm.
Ảnh có tên không có đuôi/đuôi viết hoa vẫn được nhận dạng. Không thể bảo đảm mọi
định dạng ảnh tồn tại đều hỗ trợ. SVG cần chứa đủ tài nguyên bên trong.
Ảnh được xoay theo EXIF, bỏ metadata, chuyển thành PNG tạm, tối đa 20 MiB/ảnh.
Gemini vẫn áp dụng hạn mức tài khoản thực tế. Tên file được sắp không phân biệt
hoa thường; đặt tên `001`, `002`, ... nếu cần thứ tự. Bỏ qua file ẩn và liên kết mềm.

## Dòng lệnh và macOS/Linux

```powershell
py -3 -m venv .venv-gemini
.\.venv-gemini\Scripts\python.exe -m pip install -r requirements-gemini.txt
.\.venv-gemini\Scripts\python.exe gemini_upload.py
```

macOS/Linux dùng `python3 -m venv .venv-gemini`, sau đó dùng
`.venv-gemini/bin/python` cho các lệnh cài đặt/chạy. Cần phiên máy tính có giao diện.
Cài Google Chrome hoặc Microsoft Edge; script tìm ứng dụng ở vị trí chuẩn hoặc PATH.
Không dùng profile Chrome cá nhân cho `--profile`. Đóng phiên khác dùng cùng profile
trước khi chạy. Không cần xóa profile cũ của bản trước để dùng bản này.

## Git và kiểm thử

GitHub chỉ chứa mã chạy, thư viện cần cài, file `.bat`, hướng dẫn và `img/.gitkeep`.
Ảnh, profile đăng nhập, môi trường Python, file test/example đều được loại khỏi Git.
Với `--input`/`--profile` tự đặt, dùng đường dẫn ngoài repo hoặc bổ sung vào `.gitignore`.

Các kiểm thử offline kiểm tra trình tự mở Chrome/Edge → đăng nhập → kết nối CDP,
nhận diện trang Google từ chối đăng nhập, gửi/tải lại chat bằng trang mô phỏng,
xóa đúng ảnh đã xác nhận và giữ ảnh lỗi/thay đổi. File kiểm thử không được đưa lên GitHub.
**Chưa xác minh end-to-end trên Gemini thật hoặc chạy `.bat` trên Windows thật**:
môi trường phát triển không cho truy cập Gemini. Nếu giao diện Gemini thay đổi
khiến không xác nhận được ảnh, script báo lỗi và giữ nguyên các ảnh chưa xác nhận.
