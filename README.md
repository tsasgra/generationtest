# Tự tải ảnh trong img lên Gemini

Đặt ảnh vào **`img/`** rồi chạy **`start_gemini.bat`**. Script tự nhận dạng ảnh
theo nội dung file, mở chat mới, gửi ảnh và **xóa ảnh gốc đã xác nhận gửi thành công**.
Các tab Gemini vẫn mở sau khi script kết thúc.

## Windows: lần chạy đầu

1. Cài Python **3.10+** và Google Chrome hoặc Microsoft Edge.
2. Đặt ảnh vào `img`, cạnh `gemini_upload.py`, rồi bấm đúp `start_gemini.bat`.
   File chạy tự tạo `.venv-gemini` và cài các thư viện cần thiết.
3. Script mở Chrome/Edge cài trên máy bằng một profile riêng, **chưa kết nối
   điều khiển và chưa bật cổng debug**. Đăng nhập Google và vào được Gemini.
4. Đóng toàn bộ cửa sổ của phiên Gemini vừa mở, quay lại cửa sổ script rồi nhấn **Enter**.
5. Script mở lại đúng phiên đã đăng nhập, kết nối qua cổng localhost, rồi tự gửi ảnh.

Lần sau chỉ cần thêm ảnh vào `img` và chạy lại. Phiên đăng nhập được giữ trong
`.gemini-browser-cdp`. Script tự tìm Chrome, nếu không có thì dùng Edge.
Không chạy hai bản script cùng lúc hoặc chỉnh sửa/di chuyển ảnh khi đang chạy.

Bản này bỏ cách Playwright tự mở trình duyệt để đăng nhập, vốn có thể bị Google
báo “This browser or app may not be secure”. Script không tắt bảo mật trình duyệt,
không giả lập dấu vân tay, không lấy cookie từ Chrome cá nhân và không vượt CAPTCHA.
Google vẫn quyết định có cho đăng nhập hay không; nếu tiếp tục bị chặn, cập nhật
Chrome/Edge hoặc chọn Edge bằng `--browser msedge`.

Để đăng nhập lại, đóng các cửa sổ phiên Gemini rồi chạy:

```bat
start_gemini.bat --login
```

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
start_gemini.bat --browser msedge
```

`--dry-run` nhận diện và kiểm tra ảnh offline, không mở trình duyệt hoặc xóa ảnh.
`--attach-only` chỉ đính kèm, không gửi và không xóa ảnh; bạn tự thao tác trong Gemini.
`--prompt` thay nội dung gửi kèm. `--recursive` đọc cả các thư mục con trong `img`.

Các tùy chọn khác: `--input THU_MUC`, `--batch-size 1` (1–10),
`--upload-timeout 300`, `--login-timeout 600`, `--max-file-mb 20`,
`--profile THU_MUC_RIENG`, `--browser-path DUONG_DAN_CHROME_HOAC_EDGE`.
`img` mặc định luôn nằm cạnh script, kể cả khi chạy từ thư mục khác.

Script hỗ trợ ảnh mà Pillow đọc được như PNG, JPEG, WebP, BMP, GIF, TIFF, ICO, PSD;
thêm HEIC/HEIF, AVIF, SVG và nhiều định dạng RAW qua các bộ giải mã đi kèm.
Ảnh có tên không có đuôi/đuôi viết hoa vẫn được nhận dạng. Không thể bảo đảm mọi
định dạng ảnh tồn tại đều hỗ trợ. SVG cần chứa đủ tài nguyên bên trong.
Ảnh được xoay theo EXIF, bỏ metadata, chuyển thành PNG tạm, tối đa 20 MiB/ảnh.
Gemini vẫn áp dụng hạn mức tài khoản thực tế. Tên file được sắp không phân biệt
hoa thường; đặt tên `001`, `002`, ... nếu cần thứ tự. Bỏ qua file ẩn và liên kết mềm.

## Dòng lệnh, macOS/Linux và phiên Chrome tự mở

```powershell
py -3 -m venv .venv-gemini
.\.venv-gemini\Scripts\python.exe -m pip install -r requirements-gemini.txt
.\.venv-gemini\Scripts\python.exe gemini_upload.py
```

macOS/Linux dùng `python3 -m venv .venv-gemini`, sau đó dùng
`.venv-gemini/bin/python` cho các lệnh cài đặt/chạy. Cần phiên máy tính có giao diện.
Không cần tải Chromium của Playwright. Không dùng profile Chrome cá nhân cho `--profile`.

Nếu đã tự mở một Chrome/Edge có cổng debug localhost và đã đăng nhập, có thể dùng
`--cdp-url http://127.0.0.1:9222`. Chỉ chấp nhận localhost; không dùng cùng `--login`.
Script không đóng trình duyệt hoặc các tab cũ. Đóng phiên Gemini khi dùng xong
để đóng luôn cổng debug; không mở cổng này ra mạng.

## Git và kiểm thử

GitHub chỉ chứa mã chạy, thư viện cần cài, file `.bat`, hướng dẫn và `img/.gitkeep`.
Ảnh, profile đăng nhập, môi trường Python, file test/example đều được loại khỏi Git.
Với `--input`/`--profile` tự đặt, dùng đường dẫn ngoài repo hoặc bổ sung vào `.gitignore`.

23 kiểm thử offline đã đạt, kiểm tra nhận dạng ảnh, gửi/tải lại chat bằng trang mô phỏng,
xóa đúng ảnh đã xác nhận, giữ ảnh lỗi/thay đổi và luồng mở trình duyệt đăng nhập trước.
**Chưa xác minh end-to-end trên Gemini thật hoặc chạy `.bat` trên Windows thật**:
môi trường phát triển không cho truy cập Gemini. Nếu giao diện Gemini thay đổi
khiến không xác nhận được ảnh, script báo lỗi và giữ nguyên các ảnh chưa xác nhận.
