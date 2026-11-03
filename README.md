# Polygon Upload — 10 file .txt

Công cụ Python đọc **10 file `.txt` riêng biệt** trong một thư mục và tải nội dung bạn đã chuẩn bị lên Codeforces Polygon: tạo bài, lưu statement tiếng Việt, gán checker, tải generator và lời giải chính, lưu script test, đánh dấu sample, cấp quyền cho `codeforces`, Commit Changes rồi tạo package **Full**, bật **Verify** và chờ hoàn thành. Nội dung đề và mã C++ không được AI viết lại. Kết quả cuối là link bài Polygon; bạn tự thêm bài vào Gym/Mashup.

## Một file Start cho cả dừng, dọn và chạy

Chỉ cần **`start.bat`** ở thư mục chính. Mỗi lần mở Start là bắt đầu một bài mới theo thứ tự:

1. Dừng các tiến trình uploader cũ và tiến trình con của chúng.
2. Xóa checkpoint, kết quả và dữ liệu chạy cũ; **giữ nguyên toàn bộ thư mục `problem/`, `resource/` và nội dung đã có**.
3. Chỉ tạo bộ 10 file trống nếu thư mục `problem/` chưa tồn tại; không xóa hoặc ghi đè file đã có.
4. Tự chạy upload ngay từ các file đã chuẩn bị, không có màn hình chờ xác nhận hoặc nhấn Enter. Nếu đầu vào thiếu/sai, chương trình báo lỗi và dừng trước khi gọi Polygon; sửa file rồi chạy lại.

**Điền và lưu đủ 10 file trước khi mở Start.** Mỗi lần mở `start.bat`, nội dung đã điền vẫn được giữ nguyên; checkpoint và kết quả của phiên trước sẽ bị xóa. `note.txt` được để trống; chín file còn lại phải có nội dung. Nếu tên bài cũ đã tồn tại trên Polygon, dùng tên định danh mới trong `problem/name problem.txt`.

Khi mở `start.bat` bằng nhấp đúp, cửa sổ tự đóng sau khi toàn bộ quy trình thành công, gồm lấy link bài và lưu `result.json`, `problem_url.txt`. Trạng thái package `READY` chưa phải bước cuối. Nếu có lỗi, cửa sổ vẫn chờ nhấn phím để bạn đọc thông báo và lệnh resume. Nếu gọi Start từ terminal đã mở sẵn, lệnh kết thúc và trả về dấu nhắc của terminal đó.

Start dọn các dữ liệu của uploader trong repository, ngoại trừ toàn bộ thư mục `problem/` và `resource/`:

- Các file `run_state*.json` và file `.tmp`/`.lock` đi kèm, kể cả checkpoint hỏng; các checkpoint đặt tên riêng được nhận diện bằng cấu trúc JSON của uploader.
- Các thư mục checkpoint `*.problems/` còn sót từ bản upload nhiều bài.
- `result.json`, `problem_url.txt` và các bản `.tmp`, kể cả khi nằm trong thư mục kết quả con; toàn bộ `results/`.
- Phiên trình duyệt mặc định `.polygon-browser/`, cache `__pycache__/` và file `.log` ở thư mục chính.

`problem/`, `resource/`, `.env`, mã nguồn, tài liệu, Git, môi trường Python và thư mục phát triển `work/` được giữ lại. Công cụ chỉ dọn dữ liệu trong repository, không lần theo đường dẫn trong checkpoint ra ngoài thư mục này. Các thư mục liên kết được bỏ qua hoặc báo lỗi nếu là mục cần xóa. Checkpoint đang khóa hoặc tiến trình không dừng được sẽ làm Start dừng trước khi dọn dữ liệu chạy cũ và upload.

`stop.bat`, `start_check.bat`, `start_resume.bat` và launcher CMD trung gian đã được bỏ. Có thể nhấn **Ctrl+C** để dừng trong cửa sổ Start. Khi muốn tiếp tục bài đang dở và giữ input/checkpoint, dùng lệnh `resume` trong mục bên dưới; mở Start luôn tạo phiên mới. Bài và tác vụ đã gửi lên Polygon vẫn tồn tại trên server.

Start tìm Python **3.10 trở lên** theo thứ tự: `.venv\Scripts\python.exe`, `py -3`, rồi `python`. Cần Windows PowerShell có sẵn để dừng tiến trình. Công cụ nhận diện lệnh `polygon_upload.py start`, `run`, `resume`, `init`, kiểm tra PID/thời điểm tạo rồi dừng cả cây tiến trình bằng `taskkill /T /F`; uploader từ các bản sao repository khác cũng thuộc phạm vi dừng như trước. Các chương trình Python khác và tiến trình cha đang chạy Start mới được giữ nguyên.

## Cài đặt trên Windows / PowerShell

Cần Python **3.10 trở lên**. Chạy trong thư mục repository:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Phần API dùng thư viện chuẩn Python nên `requirements.txt` không có dependency bắt buộc. Các lệnh dưới dùng trực tiếp Python trong virtual environment, không cần đổi Execution Policy hoặc kích hoạt môi trường.

Script tự đọc file `.env` nằm cạnh `polygon_upload.py`. Repository private này đã kèm `.env` theo cấu hình của chủ repo; bản clone từ GitHub có sẵn cấu hình để chạy. Điền và lưu 10 file trong `problem/`, rồi mở `start.bat` để tự upload ngay.

Nếu muốn dùng tài khoản Polygon khác, sửa hai biến `POLYGON_API_KEY` và `POLYGON_API_SECRET` trong `.env`. Script không in credentials hoặc ghi chúng vào checkpoint/kết quả; các giá trị trong `.env` được đọc nguyên văn, không chạy như lệnh shell.

Bạn cũng có thể nhập credentials qua biến môi trường PowerShell; biến môi trường có giá trị sẽ được ưu tiên hơn `.env`:

```powershell
$env:POLYGON_API_KEY = Read-Host "Polygon API key"
$secret = Read-Host "Polygon API secret" -AsSecureString
$env:POLYGON_API_SECRET = [System.Net.NetworkCredential]::new("", $secret).Password
Remove-Variable secret
```

Các biến chỉ có hiệu lực trong phiên PowerShell hiện tại và các tiến trình con. `init` và `--dry-run` không cần đọc `.env` hoặc credentials.

## Chuẩn bị 10 file đầu vào

Repository có một bộ 10 file đầu vào trống trong thư mục `problem/`. Start giữ nguyên bộ file và nội dung đã có; chỉ tạo bộ trống khi cả thư mục `problem/` chưa tồn tại. Nếu dùng CLI trực tiếp, bạn có thể chuẩn bị đầu vào trước mà không chạy Start. Để tạo một bộ ở thư mục mới:

```powershell
.\.venv\Scripts\python.exe polygon_upload.py init --output my_problem
```

Lệnh tạo thư mục `my_problem` cùng 10 file `.txt` trống. `init` không ghi đè thư mục đã tồn tại. Mở từng file bằng trình soạn thảo hỗ trợ UTF-8 rồi dán nội dung tương ứng trực tiếp vào file; **không cần marker `<<<PART: ...>>>`**.

```text
my_problem/
├── name problem.txt
├── name.txt
├── lengend.txt
├── input.txt
├── output.txt
├── note.txt
├── checker.txt
├── gen.txt
├── script_sinh_test.txt
└── solution.txt
```

| File | Nội dung / vị trí trên Polygon |
| --- | --- |
| `name problem.txt` | Tên định danh khi tạo bài, ví dụ `a-plus-b` |
| `name.txt` | Tên hiển thị của statement tiếng Việt, ví dụ `Tổng hai số` |
| `lengend.txt` | Legend |
| `input.txt` | Input format |
| `output.txt` | Output format |
| `note.txt` | Notes của statement; có thể để trống |
| `checker.txt` | Mã C++ được tải thành `checker.cpp` và chọn làm checker |
| `gen.txt` | Mã C++ được tải thành `gen.cpp` trong Source Files |
| `script_sinh_test.txt` | Script của testset `tests` |
| `solution.txt` | Mã C++ được tải thành `solution.cpp` trong Solution files, tag `MA` |

Tên file `name problem.txt` có một dấu cách giữa `name` và `problem`. `lengend.txt` giữ cách viết trong yêu cầu; có thể dùng `legend.txt` thay thế, nhưng không dùng cả hai. Thư mục phải có đủ 10 file tương ứng, không có file `.txt` lạ. Thiếu file, trùng phần qua alias hoặc file bắt buộc rỗng đều bị từ chối trước khi gọi API. `note.txt` rỗng hoặc chỉ chứa khoảng trắng được gửi thành chuỗi rỗng; chín file còn lại phải có nội dung.

`name problem.txt` và `name.txt` độc lập. Tên hiển thị được dùng tiếng Việt nhưng phải nằm trên một dòng. Tên định danh được kiểm tra sơ bộ bằng `[a-z0-9-]+` (chữ thường, chữ số và dấu gạch ngang), không tự chuyển đổi; Polygon tiếp tục kiểm tra tên khi tạo bài. Tài liệu API công khai chưa liệt kê đầy đủ mọi giới hạn tên phía server.

Mỗi file được đọc dưới dạng UTF-8 có hoặc không có BOM. Với hai file tên, một dấu xuống dòng cuối file được bỏ để hỗ trợ cách lưu thông thường của trình soạn thảo. Nội dung các file còn lại giữ nguyên tiếng Việt, LaTeX, backslash, `$`, `~`, thụt dòng, dấu cách và xuống dòng, kể cả các dòng trắng đầu/cuối. Request gửi nội dung đã đọc. Statement vẫn được đọc lại và đối chiếu, chấp nhận khác biệt CRLF/LF.

Theo cấu hình hiện tại, **checker, generator, solution và script không được đọc lại để so sánh nội dung hoặc compiler**. Khi API trả thành công, công cụ ghi nhận bước tải đã hoàn tất trong checkpoint. Bốn nội dung này cũng không được dùng để đối chiếu snapshot ở bước commit hoặc resume. Script Polygon/FreeMarker chỉ được gửi lên Polygon, không được thực thi như shell trên máy bạn. Việc chọn checker, gán tag `MA`, lấy danh sách test để đánh dấu sample và build package vẫn được thực hiện.

## Statement Resource Files

Đặt tài nguyên trực tiếp trong thư mục `resource/` cạnh `problem/` và `start.bat`:

```text
project/
├── start.bat
├── problem/
│   └── ...10 file .txt giữ nguyên...
└── resource/
    ├── .gitkeep
    ├── d.png
    └── illustration.jpg
```

Script upload các file này vào **Statement → Statement Resource Files** bằng `problem.saveStatementResource`, dùng chung cho các phần statement. Tên và byte của file được giữ nguyên. Các loại file được chấp nhận phụ thuộc Polygon; lỗi server được báo cùng tên resource. Đây là tài nguyên đính kèm statement; file ví dụ trong thư mục này không tự trở thành test Example.

Bạn tự thêm tham chiếu tại vị trí muốn hiển thị trong `lengend.txt`, `input.txt`, `output.txt` hoặc `note.txt`. Ví dụ với ảnh `resource/d.png`:

```latex
\includegraphics{d.png}
```

Script không tự sửa nội dung bốn file trên. Không có resource hoặc thư mục trống thì bỏ qua bước upload. `.gitkeep` không được upload; tài nguyên bạn thêm được Git bỏ qua. Start giữ nguyên toàn bộ `resource/`, chỉ tạo thư mục nếu chưa có. Thư mục con, liên kết và các tên trùng nhau khi không phân biệt hoa/thường bị từ chối trước khi gọi API; hãy đặt các file trực tiếp trong thư mục.

Upload resource diễn ra sau khi lưu statement và trước Commit Changes. Script đọc lại byte để xác nhận, lưu dấu kiểm tra trong checkpoint và đối chiếu lại trước khi hoàn tất. File cùng tên được cập nhật khi dữ liệu server còn khớp checkpoint; thay đổi bên ngoài gây xung đột sẽ được báo. Resume xác minh request mất phản hồi và bỏ qua resource đã đúng, không tạo bài hay build package trùng.

Với CLI, mặc định dùng thư mục `resource/` cạnh thư mục `--input`. Có thể chọn thư mục khác khi tạo phiên:

```powershell
python polygon_upload.py run --input my_problem --resource-dir my_resources
```

Resume dùng đường dẫn resource đã lưu. Nếu thêm, sửa hoặc bỏ file local, dùng `resume --state run_state.json --update-input problem` để chủ động cập nhật trên cùng bài, kể cả khi 10 file văn bản không đổi. Bỏ file local không xóa tài nguyên đã có trên Polygon. Checkpoint từ bản cũ chưa có resource vẫn resume như trước; dùng `--update-input` để bổ sung tài nguyên từ `resource/` cạnh thư mục input. Các nội dung upload trong bộ nhớ là dữ liệu đã đọc lúc bắt đầu; hãy lưu xong tất cả file trước khi chạy.

## Kiểm tra trước khi tạo bài

```powershell
.\.venv\Scripts\python.exe polygon_upload.py run --input my_problem --dry-run
```

`--dry-run` chạy hoàn toàn offline, không cần credentials, không gọi API và không tạo checkpoint hay sửa bài. Nó kiểm tra cấu trúc đầu vào và tùy chọn, rồi in kế hoạch. Biên dịch C++, triển khai FreeMarker, chỉ số sample và tính hợp lệ cuối cùng trên Polygon chỉ được xác nhận khi chạy thật.

## Chạy và nhận kết quả

```powershell
.\.venv\Scripts\python.exe polygon_upload.py run --input my_problem
```

Một lần chạy thành công thực hiện:

1. Tạo bài mới, ghi problem ID vào `run_state.json` ngay khi nhận được.
2. Lưu và đọc lại statement `vietnamese`; tải `checker.cpp`, gọi `problem.setChecker` để chọn file này làm checker (tương đương nút **Set checker**), rồi đọc `problem.checker` xác nhận lựa chọn. Khi thành công, CLI in `Đã xác nhận checker đang dùng trên Polygon: checker.cpp.`, sau đó mới tải `gen.cpp` và lưu `solution.cpp` với tag `MA`. Không đọc lại nội dung ba file này.
3. Lưu script test, lấy danh sách test thực tế từ Polygon, cập nhật cờ Example và kiểm tra lại.
4. Thêm READ cho đúng login `codeforces` nếu chưa có quyền đọc. Quyền READ/WRITE/OWNER đã có được giữ; quyền của tài khoản khác không bị sửa.
5. Sau khi upload đủ nội dung 10 file, các statement resource và xác nhận mọi sample đã bật Example, thực hiện **Commit Changes**. Chỉ khi Polygon xác nhận commit thành công, revision đã tăng và working copy sạch, công cụ mới gọi **Create package → Full**, với **Verify bật** (`full=true`, `verify=true`).
6. Poll đúng package ID của revision đó đến `READY`; nếu package Full `FAILED` thì báo lỗi, không tự build lại hoặc báo thành công.
7. Lấy link chính thức, lưu `result.json` và `problem_url.txt`.

JSON kết quả gồm problem ID, tên định danh, tên hiển thị, ngôn ngữ, số test, sample indices, quyền `codeforces`, revision, package ID/trạng thái, `package_full: true`, `package_verify: true`, link bài và giới hạn/tên file thực tế. Thông báo tiến độ nằm ở stderr. Để stdout chỉ có link sau khi thành công:

```powershell
.\.venv\Scripts\python.exe polygon_upload.py run --input my_problem --url-only
```

Nếu muốn tách checkpoint/kết quả của từng bài:

```powershell
.\.venv\Scripts\python.exe polygon_upload.py run --input my_problem --state run_state_my_problem.json --output-dir results\my_problem
```

## Sample và cấu hình

Sample tự động được nhận diện từ token hoặc giá trị tham số bằng đúng `sample` trong trường `scriptLine` của từng test Polygon đã triển khai, ví dụ `gen sample 1 > $` hoặc `gen --mode=sample --id=2 > $`. Các từ `nonsample`, `not_sample`, `sample.txt` không khớp. Công cụ dùng `index` của test thực tế, không dùng số dòng script; điều này áp dụng cả khi script có FreeMarker/vòng lặp.

Có thể **bổ sung** các chỉ số làm Example bằng `--sample-indices`. Danh sách này được hợp với toàn bộ sample tự nhận diện, không thay thế chúng:

```powershell
.\.venv\Scripts\python.exe polygon_upload.py run --input my_problem --sample-indices 1,3
```

Tất cả test `gen sample ...` đều được bật `testUseInStatements=true`, kể cả khi chỉ truyền một phần danh sách vào `--sample-indices`. Các test thủ công đã bật Example cũng được giữ. Test thường không nằm trong danh sách bổ sung được đặt cờ false. Chỉ cờ Example được cập nhật; input và lệnh sinh test không được gửi lại.

CLI đọc danh sách test một lần để chỉ cập nhật các cờ Example chưa đúng; test đã đúng không bị gọi API lặp riêng từng dòng. Request sample đang dở trong checkpoint vẫn được xác minh khi resume. Tiến độ hiển thị tổng số test, số cần cập nhật và test đang xử lý. Sau khi đánh dấu, CLI đọc lại toàn bộ danh sách test và in ví dụ: `Đã xác nhận Example cho tất cả 3 test sample: 1, 3, 7.` Công cụ kiểm tra lại trước commit, trước build/poll package và trước khi ghi kết quả thành công, kể cả khi resume. Nếu còn sample thiếu cờ Example, mất test hoặc phản hồi không xác nhận cờ boolean, công cụ báo lỗi và không báo thành công. Checkpoint cũ đã commit nhưng còn thiếu Example cũng bị chặn trước build; không tự coi package cũ là đã sửa.

Trên trang Tests của Polygon, **`Y` ở cột Example** nghĩa là test đã được chọn làm ví dụ. Ô checkbox ở mép phải chỉ dùng để chọn dòng cho thao tác hàng loạt. Nếu không nhận diện được sample, công cụ dừng tại checkpoint, không tự lấy test đầu tiên.

| Tùy chọn | Giá trị / hành vi |
| --- | --- |
| `--time-limit` | Millisecond, 250–15000, chia hết cho 50 |
| `--memory-limit` | MB, 4–1024 |
| `--input-file`, `--output-file` | Tên file vào/ra, mỗi tên 1–64 ký tự; không được giống nhau |
| `--source-type` | Mặc định `cpp.g++17`, gửi cùng checker, generator và solution |
| `--request-timeout` | Mặc định 60 giây mỗi request |
| `--retries` | Mặc định 3 lần thử lại cho lỗi đọc tạm thời; request ghi không tự lặp trong cùng lần chạy |
| `--request-interval` | Mặc định 1 giây giữa các request |
| `--poll-interval` | Mặc định 5 giây giữa các lần kiểm tra package |
| `--poll-timeout` | Mặc định 900 giây cho một lần chờ package |

Nếu không truyền time limit, memory limit hoặc tên file, CLI giữ mặc định thực tế của Polygon và in chúng khi chạy. Công cụ không tự thêm validator hoặc thay ràng buộc đề. Nếu thiếu validator, checker tests hoặc thành phần khác khiến Polygon chặn đóng gói, lỗi thực tế được giữ nguyên để bạn xử lý. Nếu mã dùng `testlib.h`, công cụ kiểm tra resource đã có; trường hợp Polygon cung cấp thư viện ngoài danh sách resource sẽ được xác nhận qua build có kiểm tra. Lỗi compiler/build không bị chuyển thành kết quả thành công.

## Tiếp tục khi bị gián đoạn

**Không mở lại `start.bat` nếu muốn resume**, vì Start sẽ xóa checkpoint (input vẫn được giữ). Giữ nguyên thư mục gồm 10 file đầu vào và checkpoint, rồi chạy:

```powershell
.\.venv\Scripts\python.exe polygon_upload.py resume --state run_state.json
```

Checkpoint có dấu vân tay đầu vào local, ghi nhận các request upload đã thành công và trạng thái server đang theo dõi. `run` từ chối dùng lại checkpoint đã tồn tại; `resume` tiếp tục trên đúng ID. Với `resume` thông thường, input phải giữ nguyên; dùng `--update-input` bên dưới nếu chủ động sửa nội dung. Công cụ vẫn kiểm tra revision, statement, lựa chọn checker, test/sample, quyền truy cập và các file ngoài bốn phần upload. Nội dung `checker.cpp`, `gen.cpp`, `solution.cpp` và script không được đối chiếu với server.

Nếu đang dở một trong bốn request upload này, `resume` gửi lại vào **đúng tên file/testset** rồi ghi nhận khi API trả thành công. Bước đã có ghi nhận thành công được bỏ qua khi đầu vào local không đổi. Checkpoint của bản cũ tự chuyển sang cơ chế này; các quy tắc khôi phục tạo bài, commit và build package vẫn được giữ riêng.

Checkpoint lưu lựa chọn Full/Verify trước khi gửi yêu cầu build. Nếu mất phản hồi, `resume` xác minh và theo dõi đúng package đã yêu cầu, không gửi build trùng. Với checkpoint bản cũ đã yêu cầu Standard, công cụ xác minh/chờ đúng package cũ kết thúc rồi tạo **một package Full mới trên cùng revision đã commit**, lưu package cũ trong lịch sử. Package Standard cũ không được báo là kết quả Full; các lỗi/xung đột đang có vẫn cần xử lý trước.

Khi Full build hoàn tất, API có thể trả nhiều bản ghi cùng package ID cho các bản ZIP `standard`, `windows` và `linux`. Công cụ theo dõi bản ghi `standard` của đúng ID/revision đã lưu, không coi các bản ZIP cùng ID là package bị mất. Nếu bản cũ báo `Không tìm thấy package ID đã ghi` dù trang Packages đã hiển thị `READY`, cập nhật mã rồi chạy lệnh `resume` ở trên với checkpoint cũ; không cần tạo lại bài hoặc build lại package.

Các tình huống cần xử lý:

- **Màn hình dừng lâu tại `Đang lưu: sample:1` nhưng chưa báo lỗi:** bản cũ gọi API cả cho từng test thường đã đúng, nên 100 test có thể mất hơn 5 phút ở bước Example. Bản hiện tại bỏ các lần gọi thừa và hiển thị tiến độ. Nếu cần dừng để cập nhật mã, dùng Ctrl+C, giữ input/checkpoint, rồi chạy `python polygon_upload.py resume --state run_state.json`; không mở Start vì Start xóa checkpoint. Nếu vẫn chờ lâu hoặc có lỗi API, giữ thông báo lỗi để xác định request gặp vấn đề.
- **Kẹt tại `checker.cpp`, `gen.cpp`, `solution` hoặc `script` do lỗi đọc lại của bản cũ:** cập nhật repository, giữ nguyên bộ đầu vào và `run_state.json`, rồi chạy `python polygon_upload.py resume --state run_state.json`. Công cụ gửi lại bước đang dở và tiếp tục trên cùng bài, không còn lỗi so sánh byte/nội dung cho bốn phần này.
- **Files đã có `checker.cpp` nhưng Checker vẫn là `None`:** tải file và chọn checker là hai bước riêng. Bản hiện tại chọn checker sau khi API xác nhận tải file thành công. Chạy `resume` với checkpoint cũ để hoàn tất bước còn thiếu. Nếu bạn đã chọn đúng `checker.cpp` trên web, công cụ xác nhận lựa chọn đó. Với checkpoint cũ đang chờ kết quả tải `gen.cpp`, công cụ xử lý request đang chờ trước rồi mới chọn checker.
- **Không nhận diện được sample:** kiểm tra chỉ số trong Tests rồi chạy `resume --state run_state.json --sample-indices 1,3`. Với resume thông thường, chỉ đổi danh sách sample trước commit.
- **Hết thời gian poll:** chạy `resume` để chờ tiếp cùng package; có thể tăng `--poll-timeout 1800`.
- **Mất phản hồi tạo bài:** CLI đọc lại server nhưng không tự gắn một bài chỉ vì trùng tên. Sau khi bạn xác nhận đúng bài vừa tạo trên Polygon, chạy `resume --state run_state.json --problem-id 123456`. ID phải thuộc danh sách mới sau thời điểm bắt đầu, đúng tên và bạn là owner. Nếu server chưa trả đủ bằng chứng, công cụ giữ checkpoint và dừng thay vì tạo thêm bài.
- **Mất phản hồi build:** CLI đối chiếu các package mới của revision đã commit. Nếu có nhiều ứng viên, kiểm tra Packages rồi dùng `resume --state run_state.json --package-id 123456`. Không build lại trong khi chưa xác định kết quả request cũ.
- **Package `FAILED`:** xem lỗi thật từ Polygon. `resume` thông thường vẫn theo dõi package đã thất bại. Nếu cần sửa nội dung hoặc chủ động thử lại một lỗi build tạm thời, dùng một trong hai lệnh bên dưới. Thay đổi trên web ở các phần còn được theo dõi vẫn được phát hiện là xung đột.

### Chủ động sửa nội dung hoặc thử lại package thất bại

Để sửa đề, checker, generator, script hoặc solution trên **cùng problem ID**, chuẩn bị thư mục đủ 10 file với nội dung đã sửa, giữ nguyên nội dung `name problem.txt`, rồi chạy:

```powershell
.\.venv\Scripts\python.exe polygon_upload.py resume --state run_state.json --update-input corrected_problem
```

`--update-input` yêu cầu input thực sự thay đổi, problem ID/snapshot đã xác định và không còn request đang chờ xác minh kết quả. Trước khi chấp nhận thư mục đầu vào mới, công cụ kiểm tra revision cùng các phần server còn được theo dõi. Bốn nội dung upload đã nêu không được đọc lại; phần có đầu vào local thay đổi sẽ được tải lên đúng tên file/testset, sau đó commit revision mới và tạo package mới. Có thể kèm `--sample-indices` nếu nội dung mới đổi quy ước sample. Lịch sử revision/package cũ được giữ trong checkpoint.

Nếu nội dung không cần đổi và package thất bại do nguyên nhân tạm thời, có thể chủ động yêu cầu một lần build mới:

```powershell
.\.venv\Scripts\python.exe polygon_upload.py resume --state run_state.json --retry-failed-package
```

`--retry-failed-package` chỉ hoạt động khi API xác nhận **đúng package ID trước đó đã `FAILED` ở cùng revision**, dữ liệu đang theo dõi khớp checkpoint và không có request chưa rõ kết quả. Nó giữ revision, tạo package mới có chủ đích; không dùng cho package `PENDING`, `RUNNING`, `READY` hoặc request build bị mất phản hồi. Hai cờ `--update-input` và `--retry-failed-package` loại trừ nhau.

Checkpoint được ghi nguyên tử và có khóa tiến trình để tránh hai lần chạy cùng ghi một state. Khi lỗi, CLI trả exit code khác 0, ghi bước lỗi và lệnh tiếp tục vào stderr. Chưa có cơ chế khóa chỉnh sửa đồng thời trên server; tránh sửa cùng bài trên web trong lúc công cụ chạy.

## Link Polygon và trình duyệt tùy chọn

Tài liệu API không cam kết trường `url` trong đối tượng Problem/Package. Package **Full** gồm các bản ZIP `standard`, `linux` và `windows`. Công cụ đọc `problem.xml` từ bản ZIP `standard` của đúng package đã build Full và chỉ dùng URL nếu thực sự có trong metadata phù hợp. Tham số tải ZIP `type=standard` không thay đổi lựa chọn build `full=true`; API tải ZIP không có `type=full`. Không tự ghép URL từ owner/name, không trả link editor, API hoặc ZIP để thay link bài.

Nếu package không cung cấp link, dùng nhánh đọc giao diện bằng Playwright:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-browser.txt
.\.venv\Scripts\python.exe -m playwright install chromium
.\.venv\Scripts\python.exe polygon_upload.py resume --state run_state.json --browser
```

Trình duyệt mở để bạn đăng nhập thủ công lần đầu và mở đúng bài theo problem ID. Công cụ đọc link/input thực tế từ DOM, kiểm tra bài đang mở rồi lấy link Polygon. Phiên riêng được lưu trong `.polygon-browser`; có thể đổi bằng `--browser-profile`. `--browser-timeout` mặc định 300 giây. Nếu không thể xác minh link, CLI dừng và giữ checkpoint dù package đã `READY`; không tạo link giả hoặc báo đã import Gym.

## Kiểm thử và giới hạn đã xác minh

Bộ kiểm thử offline/mock được giữ riêng trong workspace phát triển, không đưa lên GitHub. Repository chứa mã chạy, cấu hình và một bộ 10 file đầu vào trong `problem/`.

Các nhóm kiểm thử bao phủ parser UTF-8/BOM, note rỗng, tiếng Việt/LaTeX, file thiếu/thừa, alias trùng, sample theo index sau triển khai, tránh nhận nhầm `nonsample`, chữ ký/HTTP/API errors, checkpoint/resume, tạo bài/build bị mất phản hồi, xung đột, package `FAILED`, cùng trích xuất URL từ dữ liệu mẫu. Luồng Start mới được kiểm thử offline/mock về dừng tiến trình, bảo vệ tiến trình hiện tại và tiến trình cha, xóa dữ liệu chạy cũ, giữ nguyên byte của đầu vào, chỉ tạo 10 file trống khi thiếu thư mục, bảo vệ `.env`/mã nguồn, checkpoint đang khóa, tự upload không chờ nhập phím và báo lỗi đầu vào trước khi gọi API.


**Chưa chạy Start trên Windows hoặc kiểm thử end-to-end với tài khoản Polygon thật trong môi trường phát triển này.** Khả năng compiler phía server, tải file thật, render statement, phiên đăng nhập browser và package thực tế cần được xác nhận bằng lần chạy của bạn. Không có problem ID, package hoặc link thành công thật được tạo sẵn trong repository.

API được đối chiếu với [tài liệu Polygon API chính thức](https://codeforces.github.io/polygon-misc/API), gồm `notes`, tag `MA`, `testUseInStatements`, `problem.setAccess`, commit và package. [Trang apiHelp](https://polygon.codeforces.com/apiHelp) là điểm tra cứu bổ sung trên Polygon.
