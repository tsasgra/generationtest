# Tự tải ảnh trong img lên Gemini

Đặt ảnh vào **`img/`** rồi chạy **`start_gemini.bat`**. Script tự nhận dạng ảnh
theo nội dung file, mở chat mới và gửi ảnh. **Không bắt buộc đăng nhập hoặc đổi model.**
Chat khách giữ nguyên ảnh gốc; chỉ chat đã lưu và xác nhận lại sau khi tải lại mới
được xóa ảnh gốc nếu bạn không dùng `--keep-images`.
Script giữ các tab Gemini mở để bạn xem kết quả; đóng tab hoặc nhấn Ctrl+C khi xong.
Nhánh này chỉ có luồng tải ảnh từ file trong `img/` lên Gemini và submit;
không có thao tác copy thông tin hoặc đăng bài lên Polygon.

## Windows: lần chạy đầu

1. Cài Python **3.10+** và Google Chrome hoặc Microsoft Edge bản cập nhật.
2. Đặt ảnh vào `img`, cạnh `gemini_upload.py`, rồi bấm đúp `start_gemini.bat`.
   File chạy tự tạo `.venv-gemini` và cài thư viện cần thiết.
3. Script mở thẳng Gemini, chờ ô chat và dùng phiên khách ngay; không mở trang đăng nhập Google.
4. Khi ô chat sẵn sàng, script bấm **dấu + / Upload & tools → Upload files / Tải tệp lên**,
   chọn ảnh, chờ tải xong rồi mới submit. Với giao diện khách có menu tài liệu/công cụ
   bị khóa, script dùng ô chọn ảnh riêng đang bật của trang và bỏ qua lời mời đăng nhập.
   Script xác nhận tin nhắn kèm ảnh và phản hồi Gemini.
5. Xem kết quả rồi đóng các tab Gemini do script mở hoặc nhấn Ctrl+C.

Lần sau chỉ cần thêm ảnh vào `img` và chạy lại. Profile riêng nằm trong
`.gemini-browser-native/chrome` hoặc `.gemini-browser-native/edge`. Nếu profile này
đã đăng nhập từ trước, script dùng phiên sẵn có; không tự đăng nhập, đăng xuất hoặc đổi model.
Không chạy hai bản script cùng lúc hoặc chỉnh sửa/di chuyển ảnh khi đang chạy.

## Mở thẳng Gemini

Chỉ cần chạy **`start_gemini.bat`**, không cần nhập tài khoản hoặc chọn model.
Script tìm Google Chrome đã cài, dùng Microsoft Edge nếu không tìm thấy Chrome,
mở `https://gemini.google.com/app?hl=en` bằng profile riêng rồi kết nối Playwright
qua cổng cục bộ `127.0.0.1`. Ô chat khách sẵn sàng là đủ để bắt đầu tải ảnh.
Không tải Chromium đi kèm Playwright, đọc mật khẩu/cookie hoặc gọi API Gemini riêng.

Dùng `start_gemini.bat --browser-info` để xem trình duyệt và profile sẽ dùng;
lệnh này không cần ảnh và không mở trình duyệt. Đóng phiên khác dùng cùng profile
trước khi chạy. Các tùy chọn cũ `--polygon-python`, `--login`, `--browser`,
`--browser-path`, `--cdp-url` không được dùng.

Script giữ các tab kết quả để bạn xem, sau đó chỉ đóng cửa sổ thuộc profile riêng.
Với chat khách, không tải lại hoặc đóng tab trước khi xem xong vì cuộc trò chuyện
có thể không được lưu. Nếu dịch vụ giữ ảnh ở trạng thái đang tải hoặc từ chối ảnh,
script báo lỗi và giữ ảnh gốc; không tự chuyển sang đăng nhập hay bấm submit sớm.

## Khi nào ảnh bị xóa?

Mỗi nhóm tối đa **10 ảnh** được gửi vào một chat mới, kèm nội dung mặc định
`Ảnh được tải lên từ thư mục img.`. Trước khi bấm Gửi/submit, script phải thấy đủ
ảnh xem trước đã tải được, không còn tiến trình/trạng thái đang tải hoặc xử lý và
nút Gửi đang bật. Các điều kiện phải ổn định ít nhất một giây. Script kiểm tra lại
sau khi điền nội dung gửi kèm; chỉ thấy tên file chưa đủ để submit. Nếu hết
`--upload-timeout`, script báo lỗi và giữ ảnh, không cố bấm Gửi.

Sau khi submit ở **phiên khách**, script đợi tin nhắn có đủ ảnh và phản hồi từ
Gemini, **không tải lại chat và không xóa ảnh gốc**. Không cần chat có URL đã lưu.

Nếu dùng phiên đã đăng nhập từ trước và chat có URL đã lưu, script **tải lại chat**,
phải thấy lại tin nhắn cùng ảnh rồi mới xóa file tương ứng. Chỉ thấy ảnh trong ô
soạn thảo chưa đủ điều kiện xóa.

- Chỉ xóa file thuộc nhóm đã gửi và có nội dung/thông tin file khớp bản đã tải.
  File mới thêm vào `img`, file thay đổi trong lúc chạy và `.gitkeep` được giữ lại.
- Lỗi tải ảnh, gửi tin nhắn hoặc không xác nhận được phản hồi/chat đã lưu:
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
`--upload-timeout 300`, `--browser-timeout 60`, `--max-file-mb 20`,
`--profile THU_MUC_RIENG`.
`img` mặc định luôn nằm cạnh script, kể cả khi chạy từ thư mục khác.
`--login-timeout` vẫn được nhận như tên cũ của `--browser-timeout`, chỉ là thời gian
chờ ô chat sẵn sàng; không có bước bắt buộc đăng nhập.

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
Ảnh, profile trình duyệt, môi trường Python, file test/example đều được loại khỏi Git.
Với `--input`/`--profile` tự đặt, dùng đường dẫn ngoài repo hoặc bổ sung vào `.gitignore`.

Kiểm thử bằng Chromium trên trang mô phỏng bao gồm mở thẳng Gemini mà không
đăng nhập, menu khách kèm ô chọn ảnh đang bật, tải chậm, ảnh hỏng, nút Gửi bị khóa,
lỗi/hạn mức, submit và xác nhận phản hồi khách mà không tải lại/xóa ảnh gốc.
Luồng chat đã lưu, chỉ đính kèm và việc giữ/xóa đúng ảnh gốc cũng được kiểm tra.
File kiểm thử, log và ảnh mẫu chỉ giữ trong `work/`, không đưa lên GitHub.

Đã thử ô chọn ảnh riêng trên Gemini thật ở phiên khách, không đăng nhập hoặc đổi
model. Ảnh vào được vùng xem trước nhưng lần thử trong môi trường cloud vẫn chờ
ở trạng thái đang tải; chưa xác nhận được submit thành công trên Gemini thật.
Chưa chạy `.bat` trên Windows thật. Script không coi việc có ảnh xem trước là đã
gửi thành công và giữ nguyên ảnh khi chưa xác nhận.
