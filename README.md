# Tự tải ảnh trong img lên Gemini

Đặt ảnh vào **`img/`** rồi chạy **`start_gemini.bat`**. Script tự nhận dạng ảnh
theo nội dung file, mở chat mới, gửi ảnh và **xóa ảnh gốc đã xác nhận gửi thành công**.
Start tự dừng/dọn phiên cũ trước khi chạy. Sau khi gửi xong hoặc gặp lỗi, script
tự đóng trình duyệt và xóa trạng thái lần chạy; không cần mở Stop riêng.
Nhánh này chỉ có luồng tải ảnh từ file trong `img/` lên Gemini và submit;
không có thao tác copy thông tin hoặc đăng bài lên Polygon.
**Bản chạy trong repository yêu cầu đăng nhập Google trước khi tải ảnh.**
Chỉ script kiểm thử cục bộ trong `work/` được thử phiên khách; các script này
không được đưa lên GitHub và không tạo tùy chọn bỏ qua đăng nhập cho bản chạy.

## Windows: lần chạy đầu

1. Cài Python **3.10+** và Google Chrome hoặc Microsoft Edge bản cập nhật.
2. Đặt ảnh vào `img`, cạnh `gemini_upload.py`, rồi bấm đúp `start_gemini.bat`.
   File chạy tự tạo `.venv-gemini` và cài thư viện cần thiết.
3. Đăng nhập Google trong cửa sổ Chrome/Edge được mở. Script chờ đăng nhập trước khi kết nối tự động.
4. Khi ô chat sẵn sàng, script bấm **dấu + / Upload & tools → Upload files / Tải tệp lên**,
   chọn ảnh, chờ tải xong rồi mới submit, kiểm tra chat đã lưu và xóa ảnh đã xác nhận.
5. Script tự đóng trình duyệt và dọn checkpoint dù thành công hay lỗi.
   Xem lại kết quả trong lịch sử Gemini; thêm ảnh rồi chạy lại Start khi cần.

Giữ thư mục **`.venv-gemini`** chứa các package đã cài. Start kiểm tra thư viện
trước mỗi lần chạy; khi đã đủ và dùng được, màn hình báo **dùng lại và bỏ qua
cài đặt**. Khi thiếu thư viện, Start gọi pip để bổ sung; dòng `Requirement already
satisfied` nghĩa là package đó đã có sẵn. Bước reset trước/sau lượt chạy và chế
độ `--stop` đều giữ nguyên môi trường Python này.

Script chờ giao diện chat mới ổn định, hỗ trợ cả `/app` và đường dẫn theo tài khoản
như `/u/0/app`. Nếu Gemini khôi phục chat cũ, script bấm **New chat** rồi chờ chat
trống trước khi thêm ảnh. Nội dung lịch sử ẩn và ký tự trắng của trình soạn thảo
không bị tính nhầm thành một cuộc trò chuyện đang có nội dung.

Lần sau chỉ cần thêm ảnh vào `img` và chạy lại. Phiên đăng nhập được giữ trong
`.gemini-browser-native/chrome` hoặc `.gemini-browser-native/edge`, giống nhánh `copy_info_on_gemini`.
Không chỉnh sửa/di chuyển ảnh khi đang chạy. Trên Windows, mở Start lần nữa sẽ
dừng phiên cũ, dọn dữ liệu cũ rồi mới chạy phiên mới.

## Một file Start: tự dừng và dọn trước/sau mỗi lần chạy

Chỉ cần **`start_gemini.bat`**. Chức năng Stop đã được gộp vào bộ khởi động;
không còn file `stop.bat` riêng trong repository.

1. Trước khi chạy trên Windows, Start dừng phiên uploader/trình duyệt cũ và dọn
   dữ liệu còn sót, kể cả khi lần trước bị lỗi hoặc bị tắt cưỡng bức.
2. Chạy tải ảnh, chờ ảnh tải xong hoàn toàn, gửi đúng prompt rồi xác nhận chat đã lưu.
3. Khi gửi xong, lỗi, hết thời gian, hủy bằng Ctrl+C hoặc cài thư viện thất bại,
   bộ khởi động luôn chạy bước dọn trong `finally`. Luồng gửi bình thường không
   giữ tab mở chờ bạn đóng nữa.

Bước dọn xóa file kết nối/checkpoint, cổng debug, tab/phiên khôi phục, bản nháp,
dữ liệu trang web cục bộ, service worker, cache, lịch sử duyệt cục bộ và ảnh
chuyển đổi tạm. `.gemini-runtime` và tín hiệu Stop cũng được dọn. Các file khóa
hệ điều hành rỗng có thể còn lại, nhưng không lưu tiến độ và tự nhả khi tiến trình thoát.

**Giữ nguyên dữ liệu đăng nhập Google và ảnh gốc chưa được xác nhận gửi.**
File cookie, khóa mã hóa và dữ liệu tài khoản được giữ tại vị trí cũ; không thay
hoặc xóa toàn bộ profile. Ảnh đã gửi và xác nhận thành công vẫn được xóa theo luồng
cũ, trừ khi dùng `--keep-images`. Dọn checkpoint không khôi phục ảnh đã xóa và
không xóa chat/thu hồi ảnh trên máy chủ Gemini. Nếu lần trước đã bấm Gửi nhưng báo
chưa xác nhận được, kiểm tra lịch sử Gemini trước khi chạy lại để tránh gửi trùng.

Muốn dừng ngay mà không bắt đầu lượt mới, dùng chính file Start:

```bat
start_gemini.bat --stop
start_gemini.bat --stop --profile "D:\GeminiProfile"
```

Hoặc nhấn Ctrl+C trong cửa sổ đang chạy. Chế độ `--attach-only` vẫn chờ bạn thao tác
thủ công; khi đóng tab hoặc Ctrl+C, bước dọn cũng chạy. `--browser-info` và `--help`
chỉ xem thông tin, không gọi Stop hay xóa công việc đang chạy.

Trên Windows, bước dừng dùng PowerShell có sẵn và `taskkill /T /F`, nhận diện đúng
uploader/profile của công cụ. Nó bảo vệ tiến trình Start hiện tại cùng các tiến
trình `py.exe` cha để không tự tắt khi dọn. Nếu thiếu quyền dừng hoặc không dọn được
file, script báo lỗi, không báo hoàn tất giả. Trình duyệt Chrome/Edge cá nhân ngoài
profile riêng không bị đóng theo tên chung. Khi cập nhật, lấy cả thư mục `gemini_tool`
và file `start_gemini.bat`.

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
   ô chat và nút tài khoản Google để xác nhận đã đăng nhập, mở chat mới, tải và gửi ảnh.
   Chỉ thấy ô chat của phiên khách hoặc quay về URL Gemini chưa đủ để bắt đầu tải ảnh.

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
Kết thúc lượt gửi, script tự đóng cửa sổ của profile riêng và dọn trạng thái;
cửa sổ Chrome/Edge cá nhân không thuộc profile này.

## Khi nào ảnh bị xóa?

Mỗi nhóm tối đa **10 ảnh** được gửi vào một chat mới, kèm nội dung mặc định
`apply polygon setter skill`, chỉ đúng một dòng này, không thêm nội dung khác.
Trước khi bấm Gửi/submit, script phải thấy đủ
ảnh xem trước đã tải được, không còn tiến trình/trạng thái đang tải hoặc xử lý và
nút Gửi đang bật. Cả trạng thái tải trong ô soạn thảo lẫn thanh tiến trình/thông báo
tải bên ngoài đều phải kết thúc. Các điều kiện phải ổn định ít nhất **hai giây**. Script kiểm tra lại
sau khi điền nội dung gửi kèm; chỉ thấy tên file chưa đủ để submit. Nếu hết
`--upload-timeout`, script báo lỗi và giữ ảnh, không cố bấm Gửi.

Sau khi submit, script đợi tin nhắn có đủ ảnh, **tải lại chat**,
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
start_gemini.bat --prompt "apply polygon setter skill"
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

Kiểm thử bằng Chromium trên trang mô phỏng bao gồm menu thêm ảnh hiện tại,
tải chậm, ảnh xem trước hỏng, nút Gửi bị khóa, lỗi/hạn mức, submit rồi tải lại chat,
chế độ chỉ đính kèm và việc giữ/xóa đúng ảnh gốc. File kiểm thử và ảnh mẫu chỉ
được giữ trong `work/`, không đưa lên GitHub.

Kiểm thử Stop mô phỏng việc dừng đúng cây tiến trình/profile, PID bị tái sử dụng,
lỗi quyền truy cập, dọn trạng thái hỏng và giữ ảnh cùng dữ liệu đăng nhập.
Đã chạy tiến trình uploader riêng với Chromium thật và trang Gemini mô phỏng:
Hủy trong lúc chờ tải ảnh hoặc ở chế độ chỉ đính kèm đều đóng trình duyệt, xóa ảnh tạm,
giữ ảnh gốc và trả mã dừng 130 mà không cần cưỡng bức tiến trình thử nghiệm.
Đã kiểm tra thêm bằng Chromium mở qua CDP với profile lưu trên ổ đĩa: đóng trình
duyệt giữa lúc tải → lỗi hết thời gian tải → ba lần tải/submit liên tiếp, chạy qua
bộ khởi động và tự dọn trước/sau, không gọi Stop thủ công. Cookie đăng nhập giả lập
vẫn còn; ảnh chưa xác nhận được giữ, ảnh tạm/tab/bản nháp được dọn ngay sau mỗi lượt.
Đã kiểm tra thêm lỗi cài thư viện, Ctrl+C, mã thoát khác 0 và việc Start thay thế
phiên cũ đang giữ khóa, đồng thời bảo vệ chính nó cùng các tiến trình cha. Đây là trang Gemini mô phỏng, không dùng tài khoản
Google thật. Phần dừng tiến trình Windows chưa được chạy trực tiếp trên Windows thật.

Script test cục bộ đã truy cập Gemini thật ở phiên khách: ảnh vào vùng xem trước
qua ô chọn ảnh riêng nhưng dừng ở 50% sau 180 giây; chưa xác nhận submit thành công.
Kết quả test khách không thay đổi yêu cầu đăng nhập của mã được đẩy lên nhánh này.
**Chưa xác minh gửi ảnh end-to-end trên tài khoản Gemini thật hoặc chạy `.bat`
trên Windows thật**: môi trường phát triển chưa có phiên Google đăng nhập.
Nếu giao diện thay đổi khiến không xác nhận được ảnh, script báo lỗi và giữ ảnh.
