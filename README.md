# Xử lý song song 10 bài trong img trên Gemini

Đặt ảnh bài 1 vào **`img/img1/`**, bài 2 vào **`img/img2/`**, ... bài 10 vào **`img/img10/`**,
rồi chạy **`start_gemini.bat`** một lần. Thư mục **`img/`** nằm cạnh script;
10 thư mục con `img1` đến `img10` được tạo lại nếu thiếu. Mỗi thư mục có thể chứa nhiều ảnh của cùng một bài, tối đa **10 ảnh**.
Script chạy **tối đa 10 bài song song**, bỏ qua thư mục trống hoặc không tìm
thấy ảnh hợp lệ (chỉ có file rỗng, file hỏng hoặc file không phải ảnh). Mỗi bài dùng
một chat mới, gửi toàn bộ ảnh hợp lệ trong thư mục kèm đúng một dòng prompt
`apply polygon-problem-setter skill`. Các bài dùng những tab riêng trong cùng
một trình duyệt và phiên đăng nhập Google. Mỗi tab tự chờ ảnh tải xong mới submit,
chờ Gemini hoàn tất **10 Part**, xác nhận chat đã lưu, ghi đủ 10 file vào
**`problem/problemN/`** rồi xử lý ảnh gốc của bài đó. Bài xong trước được lưu trước.
Start tự dừng/dọn phiên cũ trước khi chạy. Sau khi tất cả bài đã kết thúc, script
tự đóng trình duyệt và xóa trạng thái lần chạy; không cần mở Stop riêng.
Luồng chạy gồm tải ảnh, gửi đúng prompt và lưu 10 phần trả lời
cục bộ theo nhánh `copy_info_on_gemini`. Không đăng bài lên Polygon.
**Bản chạy trong repository yêu cầu đăng nhập Google trước khi tải ảnh.**
Chỉ script kiểm thử cục bộ trong `work/` được thử phiên khách; các script này
không được đưa lên GitHub và không tạo tùy chọn bỏ qua đăng nhập cho bản chạy.

Khi cập nhật từ bản cũ, chuyển ảnh còn lại ở các thư mục `img1` … `img10` cạnh script
vào các thư mục tương ứng bên trong `img/` trước khi chạy. Kết quả mới lưu theo tên
`problem1` … `problem10`; các bộ kết quả cũ được giữ nguyên.

## Windows: lần chạy đầu

1. Cài Python **3.10+** và Google Chrome hoặc Microsoft Edge bản cập nhật.
2. Đặt ảnh từng bài vào `img/img1` đến `img/img10` bên trong thư mục `img`, cạnh `gemini_upload.py`, rồi bấm đúp `start_gemini.bat`.
   File chạy tự tạo `.venv-gemini` và cài thư viện cần thiết.
3. Đăng nhập Google trong cửa sổ Chrome/Edge được mở. Script chờ đăng nhập trước khi kết nối tự động.
4. Khi ô chat sẵn sàng, script bấm **dấu + / Upload & tools → Upload files / Tải tệp lên**,
   chọn ảnh, chờ tải xong rồi mới submit. Script chờ Gemini hoàn tất đủ 10 Part,
   xác nhận chat đã lưu, ghi 10 file vào `problem/problemN` rồi mới xóa ảnh đã xác nhận.
5. Các bài chạy đồng thời. Một bài lỗi được báo riêng; các bài khác tiếp tục.
   Khi tất cả bài đã hoàn tất hoặc báo lỗi, script tự đóng trình duyệt và dọn checkpoint.
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

Lần sau chỉ cần thêm ảnh vào `img/img1` đến `img/img10` và chạy lại. Phiên đăng nhập được giữ trong
`.gemini-browser-native/chrome` hoặc `.gemini-browser-native/edge`, giống nhánh `copy_info_on_gemini`.
Không chỉnh sửa/di chuyển ảnh khi đang chạy. Trên Windows, mở Start lần nữa sẽ
dừng phiên cũ, dọn dữ liệu cũ rồi mới chạy phiên mới.

## Một file Start: tự dừng và dọn trước/sau mỗi lần chạy

Chỉ cần **`start_gemini.bat`**. Chức năng Stop đã được gộp vào bộ khởi động;
không còn file `stop.bat` riêng trong repository.

1. Trước khi chạy trên Windows, Start dừng phiên uploader/trình duyệt cũ và dọn
   dữ liệu còn sót, kể cả khi lần trước bị lỗi hoặc bị tắt cưỡng bức.
2. Với từng bài, tải toàn bộ ảnh, chờ ảnh tải xong hoàn toàn, gửi đúng prompt,
   chờ đủ 10 Part và lưu bộ file `problem/problemN` sau khi xác nhận chat đã lưu.
3. Khi tất cả bài kết thúc, hủy bằng Ctrl+C hoặc cài thư viện thất bại,
   bộ khởi động luôn chạy bước dọn trong `finally`. Luồng gửi bình thường không
   giữ tab mở chờ bạn đóng nữa.

Bước dọn xóa file kết nối/checkpoint, cổng debug, tab/phiên khôi phục, bản nháp,
dữ liệu trang web cục bộ, service worker, cache, lịch sử duyệt cục bộ và ảnh
chuyển đổi tạm. `.gemini-runtime` và tín hiệu Stop cũng được dọn. Các file khóa
hệ điều hành rỗng có thể còn lại, nhưng không lưu tiến độ và tự nhả khi tiến trình thoát.

**Giữ nguyên thư viện, dữ liệu đăng nhập Google, bộ `problem` đã lưu và ảnh gốc chưa hoàn tất.**
File cookie, khóa mã hóa và dữ liệu tài khoản được giữ tại vị trí cũ; không thay
hoặc xóa toàn bộ profile. Ảnh chỉ được xóa sau khi xác nhận chat và lưu đủ
10 Part, trừ khi dùng `--keep-images`. Dọn checkpoint không khôi phục ảnh đã xóa và
không xóa chat/thu hồi ảnh trên máy chủ Gemini. Nếu lần trước đã bấm Gửi nhưng báo
chưa xác nhận được, kiểm tra lịch sử Gemini trước khi chạy lại để tránh gửi trùng.

Muốn dừng ngay mà không bắt đầu lượt mới, dùng chính file Start:

```bat
start_gemini.bat --stop
start_gemini.bat --stop --profile "D:\GeminiProfile"
```

Hoặc nhấn Ctrl+C trong cửa sổ đang chạy. Stop/Ctrl+C hủy các bài đang chạy;
script chờ các tác vụ dừng trước khi đóng trình duyệt và dọn ảnh tạm.
Chế độ `--attach-only` vẫn chờ bạn thao tác thủ công và đóng từng tab; khi tất cả
tab đóng hoặc Ctrl+C, bước dọn cũng chạy. `--browser-info` và `--help`
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
Sau khi lưu đủ 10 Part cho tất cả bài có ảnh, script tự đóng cửa sổ profile riêng và dọn trạng thái;
cửa sổ Chrome/Edge cá nhân không thuộc profile này.

## Khi nào ảnh bị xóa?

Mỗi thư mục `img/img1` đến `img/img10` là **một bài**, tối đa **10 ảnh**, được gửi vào một chat mới, kèm nội dung mặc định
`apply polygon-problem-setter skill`, chỉ đúng một dòng này, không thêm nội dung khác.
Không trộn ảnh giữa hai thư mục hoặc tự tách một bài thành nhiều chat. Nếu một
thư mục có hơn 10 ảnh hợp lệ, script báo lỗi trước khi mở trình duyệt, giữ nguyên ảnh.
Trước khi bấm Gửi/submit, script phải thấy đủ
ảnh xem trước đã tải được, không còn tiến trình/trạng thái đang tải hoặc xử lý và
nút Gửi đang bật. Cả trạng thái tải trong ô soạn thảo lẫn thanh tiến trình/thông báo
tải bên ngoài đều phải kết thúc. Các điều kiện phải ổn định ít nhất **hai giây**. Script kiểm tra lại
sau khi điền nội dung gửi kèm; chỉ thấy tên file chưa đủ để submit. Nếu hết
`--upload-timeout`, script báo lỗi và giữ ảnh, không cố bấm Gửi.

Các thao tác bấm dấu +, chọn Upload files, đưa ảnh vào và điền/gửi prompt được
ngắt bằng khoảng nghỉ **0,8 giây**. Sau khi nhập prompt, script kiểm tra lại nội dung
ô chat còn đúng trước khi bấm Gửi; nếu ô chat bị xóa thì báo lỗi và giữ ảnh.

Sau khi submit, script giữ chat mở để Gemini trả lời, **không tải lại khi đang sinh**.
Chỉ khi Gemini ngừng sinh, đủ Part 1–10 và nội dung ổn định ít nhất **hai giây**,
script mới tải lại chat để xác nhận ảnh đã lưu và ghi trọn bộ 10 file.
Ảnh gốc chỉ bị xóa sau cả hai bước xác nhận và ghi file thành công.

- Chỉ xóa file thuộc nhóm đã gửi và có nội dung/thông tin file khớp bản đã tải.
  File mới thêm vào các thư mục ảnh, file thay đổi trong lúc chạy và `.gitkeep` được giữ lại.
- Lỗi đăng nhập, tải/gửi ảnh, thiếu/trùng Part, ghi file lỗi hoặc không xác nhận được sau khi tải lại:
  giữ ảnh chưa xác nhận và trả lỗi. Không tự gửi lại; kiểm tra chat trước khi chạy lại
  nếu lần trước đã bấm Gửi, để tránh gửi trùng.
- Khi chạy song song, một bài lỗi không hủy các bài khác. Script chờ tất cả kết thúc
  rồi tổng hợp lỗi và trả mã lỗi nếu có bài thất bại. Kết quả thành công được giữ,
  ảnh bài lỗi và các bài chưa hoàn tất được giữ. Chạy lại sẽ bỏ qua thư mục đã
  hết ảnh. `--keep-images` giữ cả ảnh thành công, nên chạy lại sẽ gửi lại những bài đó.
- File không phải ảnh, hỏng hoặc chưa hỗ trợ được bỏ qua và giữ nguyên; ảnh hợp lệ
  khác vẫn được xử lý. Thư mục trống hoặc không có ảnh hợp lệ được bỏ qua để chạy
  thư mục kế tiếp, không tạo chat và không thay kết quả cũ của thư mục đã bỏ qua.
  Ví dụ `img/img2` không có ảnh thì tiếp tục `img/img3`, lưu vào `problem/problem3`.
  Nếu cả 10 thư mục không có ảnh hợp lệ, script kết thúc bình thường, không mở trình duyệt.
- GIF động/TIFF nhiều trang chỉ chuyển khung/trang đầu, nên **giữ bản gốc nhiều
  khung/trang** để không xóa phần chưa tải. Script báo rõ trường hợp này.
- Xóa trực tiếp khỏi ổ đĩa, không đưa vào thùng rác. Dùng `--keep-images` để giữ bản gốc.

## Bộ 10 file trong problem

Tên và nội dung file giữ đúng định dạng của
[`copy_info_on_gemini`](https://github.com/tsasgra/generationtest/blob/e5ee49144ef20f7d5b02e8aa31b69f8056a0125c/gemini_export.bat).
Mỗi Part phải có đúng một khối code; Part 6 (note) được phép để trống. Nội dung
được lưu UTF-8, giữ nguyên thụt dòng, LaTeX và mã nguồn.

| Part | File |
| --- | --- |
| 1 | `name problem.txt` |
| 2 | `name.txt` |
| 3 | `lengend.txt` |
| 4 | `input.txt` |
| 5 | `output.txt` |
| 6 | `note.txt` |
| 7 | `checker.txt` |
| 8 | `gen.txt` |
| 9 | `script_sinh_test.txt` |
| 10 | `solution.txt` |

Mỗi bài luôn lưu đủ 10 Part trong thư mục `problem`. Kết quả giữ đúng số thư mục đầu vào: `img/img1` → `problem/problem1/`, ...,
`img/img10` → `problem/problem10/`. Mỗi thư mục kết quả chứa đủ 10 file trên. Thư mục ảnh
trống không tạo hoặc xóa kết quả cũ; chỉ có ảnh trong `img/img2` và `img/img10` thì chỉ xử lý
hai bài đó song song, lưu vào `problem/problem2` và `problem/problem10`, dù bài nào xong trước.
Bộ cũ chỉ được thay khi đã chuẩn bị đủ 10 file mới;
không ghi dở dang hoặc xóa file lạ trong thư mục đầu ra.

Để dùng một thư mục riêng theo cách cũ, chạy `start_gemini.bat --input THU_MUC_ANH_RIENG`.
Chế độ `--input` chia nhóm theo `--batch-size`: một chat lưu trực tiếp trong
`problem/`, nhiều chat lưu riêng trong `problem/chat_0001/`, `problem/chat_0002/`, ...
Khi đã có các thư mục `chat_000N`, những lần sau vẫn dùng cách bố trí đó.
Nếu `problem/` đã chứa các kết quả `problemN`, hãy dùng hàng đợi mặc định để tiếp tục
lưu theo bài; chế độ cũ sẽ báo lỗi nếu phải thay thư mục có kết quả lạ.

Mặc định chờ Gemini tối đa **600 giây mỗi chat**. Có thể tăng thời gian:

```bat
start_gemini.bat --response-timeout 1800
```

Riêng bài hết thời gian được báo lỗi và giữ ảnh gốc cùng bộ `problem` cũ.
Các bài khác vẫn tiếp tục; bước dọn dữ liệu chạy tạm diễn ra sau khi tất cả đã kết thúc.
Các bộ `problem` hoàn thành được giữ qua Start/Stop và được loại khỏi Git.

Mặc định chạy đồng thời tối đa **10 bài**. Có thể giảm số bài chạy cùng lúc:

```bat
start_gemini.bat --workers 2
start_gemini.bat --workers 1
```

`--workers` nhận giá trị 1–10. Giá trị 1 chạy lần lượt và dừng ở bài lỗi như trước.
Gemini vẫn áp dụng hạn mức tải ảnh và sinh phản hồi của tài khoản đang đăng nhập.
Mỗi tác vụ có kết nối điều khiển riêng và chỉ thao tác trên tab của nó; trình duyệt
chỉ được đóng khi tất cả tác vụ đã kết thúc.

## Tùy chọn thường dùng

```bat
start_gemini.bat --dry-run
start_gemini.bat --prompt "apply polygon-problem-setter skill"
start_gemini.bat --keep-images
start_gemini.bat --attach-only
```

`--dry-run` nhận diện và kiểm tra ảnh offline, không mở trình duyệt hoặc xóa ảnh.
`--attach-only` chỉ đính kèm, không gửi và không xóa ảnh; bạn tự thao tác trong Gemini,
đóng từng tab khi xong. Số tab mở cùng lúc theo `--workers`.
`--prompt` thay nội dung gửi kèm. `--recursive` đọc cả các thư mục con trong từng thư mục ảnh.

Các tùy chọn khác: `--workers 2` (1–10), `--input THU_MUC` (thay hàng đợi mặc định), `--batch-size 1` (1–10, chỉ với `--input`),
`--upload-timeout 300`, `--response-timeout 1800`, `--login-timeout 600`, `--max-file-mb 20`,
`--profile THU_MUC_RIENG`.
Thư mục `img` mặc định luôn nằm cạnh script; `img1` đến `img10` nằm bên trong `img`,
kể cả khi chạy từ thư mục khác.

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

GitHub chỉ chứa mã chạy, thư viện cần cài, file `.bat`, hướng dẫn và các file `.gitkeep` trong thư mục ảnh.
Ảnh, `problem`, profile đăng nhập, môi trường Python, file test/example đều được loại khỏi Git.
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
Đã kiểm thử thêm phản hồi đang sinh, Part 10 đến muộn, mã phần cuối còn thay đổi,
thiếu/trùng Part, phản hồi cũ/ẩn, ghi file lỗi và hủy trong lúc chờ. Kiểm tra luồng
hoàn chỉnh xác nhận không reload, ghi file, xóa ảnh hoặc đóng phiên trước khi đủ
10 phần; bộ `problem` hoàn thành vẫn được giữ sau khi dọn trạng thái.
Kiểm thử gồm chạy đủ `img/img1` đến `img/img10` với nhiều ảnh mỗi bài; ở chế độ
song song, cả 10 bài phải submit trước khi bài đầu tiên được phép hoàn tất phản hồi.
Đã kiểm tra bỏ qua thư mục không có ảnh, giữ đúng số thư mục kết quả dù hoàn tất
khác thứ tự, giới hạn số tác vụ, một bài lỗi trong khi bài khác thành công,
Stop/Ctrl+C hủy nhiều tác vụ, cùng việc giữ đăng nhập, thư viện và kết quả đã hoàn tất.
Nếu giao diện thay đổi khiến không xác nhận được ảnh hoặc 10 Part, script báo lỗi và giữ ảnh.
