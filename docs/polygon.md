> Hướng dẫn chế độ Polygon riêng, dùng các lệnh `start.bat polygon-legacy ...` hoặc mục 7/8/R trong menu `start.bat`. Checkpoint `run_state.json` cũ vẫn được hỗ trợ. Xem [README chung](../README.md).

# Polygon Upload — 10 bài cùng lúc

Công cụ Python tải **tối đa 10 bài lần lượt trong một lần chạy** từ `problem/problem1` đến `problem/problem10`. Mỗi bài có **10 file `.txt` riêng biệt**. Với từng bài, công cụ tải nội dung bạn đã chuẩn bị lên Codeforces Polygon: tạo bài, lưu statement tiếng Việt, gán checker, tải generator và lời giải chính, lưu script test, đánh dấu sample, cấp quyền cho `codeforces`, commit và chờ package Standard hoàn thành. Nội dung đề và mã C++ không được AI viết lại. Kết quả cuối là link bài Polygon; bạn tự thêm bài vào Gym/Mashup.

## Bấm đúp để chạy trên Windows

Sau khi cập nhật hoặc tải repository về máy, điền đủ 10 file của **từng bài** trong `problem/problem1` đến `problem/problem10`, rồi bấm đúp một trong các file sau tại thư mục chính:

| File | Chức năng |
| --- | --- |
| **`start.bat polygon-legacy auto`** | Upload lần lượt tối đa 10 bài. Nếu có `run_state.json`, tiếp tục các bài chưa xong trong đợt đó; nếu chưa có, tạo đợt mới từ `problem/`. |
| `start.bat polygon-legacy resume` | Tiếp tục đợt upload trong `run_state.json`, bỏ qua các bài đã hoàn tất. Báo lỗi nếu chưa có checkpoint. |
| `start.bat polygon-legacy check` | Kiểm tra toàn bộ bài trong `problem/` bằng `--dry-run`, không gọi Polygon. |
| **`start.bat polygon-legacy stop`** | Dừng uploader và xóa checkpoint/kết quả cục bộ của lần chạy trước trong thư mục này, để `start.bat polygon-legacy auto` bắt đầu đợt mới. |

Các file start tự chuyển về thư mục repository và giữ cửa sổ mở để đọc kết quả/lỗi. Chúng tìm Python **3.10 trở lên** theo thứ tự: `.venv\Scripts\python.exe`, `py -3`, rồi `python`. Nếu máy đã có Python phù hợp, bạn không cần tạo virtual environment hoặc gõ lệnh để chạy phần API. Nếu chưa có, cửa sổ sẽ hướng dẫn cài Python.

Các chế độ này dùng chung file `start.bat`; không còn launcher Start/Stop phụ. Khi tiếp tục, script dùng thư mục đầu vào đã lưu trong checkpoint. Nếu muốn chuyển sang đợt mới, bấm **`start.bat polygon-legacy stop`**, sửa các bộ đầu vào trong `problem/problemN/`, rồi bấm **`start.bat polygon-legacy auto`**. Nếu tên định danh cũ đã tồn tại trên Polygon, điền tên mới trong `name problem.txt` của bài đó. Khi chưa bấm Stop, `start.bat polygon-legacy auto` vẫn tiếp tục đợt trong checkpoint và giữ kết quả các bài đã hoàn tất. Checkpoint một bài từ bản cũ vẫn tiếp tục được. Các tùy chọn nâng cao và trình duyệt lấy link vẫn dùng các lệnh bên dưới.

Để dừng và reset chế độ Polygon cũ, chọn R trong menu `start.bat` hoặc chạy `start.bat polygon-legacy stop`. Công cụ nhận diện các lệnh Python chạy `polygon_upload.py run`, `resume` hoặc `init` (qua file start hoặc gõ trực tiếp), kiểm tra lại PID/thời điểm tạo tiến trình rồi dừng cả cây tiến trình bằng `taskkill /T /F`, bao gồm trình duyệt do lần chạy đó mở. Các bản sao repository đang chạy uploader cũng thuộc phạm vi dừng. Những chương trình Python khác không bị dừng theo tên chung `python.exe`. Các cửa sổ start đã chạy xong và đang chờ nhấn phím có thể vẫn mở.

Sau khi dừng tiến trình thành công, `start.bat polygon-legacy stop` xóa `run_state.json`, `run_state.json.tmp`, `run_state.json.lock`, `result.json`, `result.json.tmp`, `problem_url.txt` và `problem_url.txt.tmp` trong thư mục repository chứa file Stop. Việc xóa vẫn chạy khi uploader đã kết thúc hoặc checkpoint bị hỏng. Nếu không dừng được tiến trình hoặc checkpoint đang bị khóa, công cụ báo lỗi và chưa xóa checkpoint. Với đợt nhiều bài, Stop cũng xóa checkpoint con trong `run_state.problems/` và các file kết quả của từng bài trong `results/problemN/`. Công cụ khóa cả checkpoint tổng và checkpoint con trước khi xóa; không xóa file khác trong các thư mục này. Checkpoint đặt tên riêng bằng `--state`, kết quả ở thư mục khác và checkpoint của bản sao repository khác không nằm trong phạm vi xóa.

Stop giữ lại toàn bộ file đầu vào của các bài, `.env` và mã nguồn. Bài đã tải lên Polygon vẫn tồn tại; request hoặc package mà Polygon đã nhận có thể tiếp tục trên máy chủ. Nếu chỉ muốn tạm dừng để tiếp tục cùng bài, dùng **Ctrl+C** trong cửa sổ đang chạy, sau đó dùng `start.bat polygon-legacy resume`. File Stop cần Python 3.10 trở lên và Windows PowerShell có sẵn trên máy, chạy bằng cùng tài khoản/quyền với uploader.

## Cài đặt trên Windows / PowerShell

Cần Python **3.10 trở lên**. Chạy trong thư mục repository:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Phần API dùng thư viện chuẩn Python; `requirements.txt` hiện chứa thêm các thư viện cho luồng Gemini chung. Các lệnh dưới dùng trực tiếp Python trong virtual environment, không cần đổi Execution Policy hoặc kích hoạt môi trường.

Script tự đọc file `.env` nằm cạnh `polygon_upload.py`. Chép `.env.example` thành `.env` và điền khóa API; khóa thật không được đưa vào commit mới. Điền đủ 10 file trong mỗi thư mục `problem/problemN/` trước khi upload.

Nếu muốn dùng tài khoản Polygon khác, sửa hai biến `POLYGON_API_KEY` và `POLYGON_API_SECRET` trong `.env`. Script không in credentials hoặc ghi chúng vào checkpoint/kết quả; các giá trị trong `.env` được đọc nguyên văn, không chạy như lệnh shell.

Bạn cũng có thể nhập credentials qua biến môi trường PowerShell; biến môi trường có giá trị sẽ được ưu tiên hơn `.env`:

```powershell
$env:POLYGON_API_KEY = Read-Host "Polygon API key"
$secret = Read-Host "Polygon API secret" -AsSecureString
$env:POLYGON_API_SECRET = [System.Net.NetworkCredential]::new("", $secret).Password
Remove-Variable secret
```

Các biến chỉ có hiệu lực trong phiên PowerShell hiện tại và các tiến trình con. `init` và `--dry-run` không cần đọc `.env` hoặc credentials.

## Chuẩn bị 10 bài

Repository có sẵn 10 thư mục đầu vào trống, mỗi thư mục chứa đủ 10 file:

```text
problem/
├── problem1/   # 10 file .txt của bài 1
├── problem2/   # 10 file .txt của bài 2
├── ...
└── problem10/  # 10 file .txt của bài 10
```

Điền nội dung riêng cho từng bài; `name problem.txt` của các bài phải khác nhau. Có thể dùng bất kỳ thư mục nào từ `problem1` đến `problem10`. Thư mục trống và bộ 10 file mẫu hoàn toàn trống được bỏ qua; bộ điền dở sẽ báo lỗi. Tên `problem(1)` đến `problem(10)` cũng được hỗ trợ; không dùng đồng thời `problem1` và `problem(1)`. Không để bộ 10 file `.txt` trực tiếp ở thư mục cha khi chạy nhiều bài.

Để tạo một đợt mới ở thư mục chưa tồn tại:

```powershell
.\.venv\Scripts\python.exe polygon_upload.py init --output my_batch --count 10
.\.venv\Scripts\python.exe polygon_upload.py run --input my_batch --dry-run
.\.venv\Scripts\python.exe polygon_upload.py run --input my_batch
```

`start.bat polygon-legacy auto` tự nhận diện cấu trúc nhiều bài và chạy lần lượt theo số thứ tự.
Bài hiện tại phải hoàn tất package và lấy được link rồi mới bắt đầu bài tiếp theo.
Một bài lỗi sẽ dừng đợt; Resume tiếp tục từ bài đang dở. `--jobs` chỉ nhận `1`, kể cả
khi checkpoint cũ từng lưu giá trị lớn hơn. `--request-interval` vẫn điều tiết các request.


Toàn bộ đầu vào được kiểm tra trước khi gọi API. Thiếu file, nội dung bắt buộc rỗng hoặc tên định danh trùng sẽ dừng cả đợt trước khi tạo bài. Sau khi bắt đầu upload, kết quả/checkpoint được tách như sau:

| Đường dẫn mặc định | Nội dung |
| --- | --- |
| `run_state.json` | Danh sách và cấu hình đợt upload |
| `run_state.problems/problemN.json` | Checkpoint riêng của bài N |
| `results/problemN/result.json`, `results/problemN/problem_url.txt` | Kết quả riêng của bài N |
| `result.json` | Tổng số bài, số hoàn tất/lỗi/chưa xong và kết quả từng bài |
| `problem_url.txt` | Một link mỗi dòng cho các bài thành công, theo thứ tự số bài |

Các file tổng hợp được cập nhật sau mỗi bài. `--url-only` chỉ in các link thành công ra stdout. Nếu có bất kỳ bài lỗi, chương trình trả exit code 1 và giữ kết quả các bài thành công. `--output-dir` đổi nơi lưu cả kết quả tổng lẫn thư mục `results/`; `--state batch_A.json` dùng checkpoint con trong `batch_A.problems/`.

Bấm `start.bat polygon-legacy resume` hoặc chạy `resume --state run_state.json` để tiếp tục các bài chưa xong. Bài hoàn tất được lấy kết quả từ checkpoint, không upload/build lại. Giữ nguyên danh sách thư mục và tên định danh của đợt khi resume. Dùng Ctrl+C để tạm dừng; các request đang gửi có thể cần chờ đến timeout để đóng, còn checkpoint được giữ lại.

Các cờ `--problem-id`, `--package-id`, `--update-input`, `--retry-failed-package` chỉ dùng với checkpoint riêng của một bài, ví dụ:

```powershell
.\.venv\Scripts\python.exe polygon_upload.py resume --state run_state.problems/problem3.json --problem-id 123456
.\.venv\Scripts\python.exe polygon_upload.py resume --state run_state.problems/problem3.json --update-input problem/problem3
.\.venv\Scripts\python.exe polygon_upload.py resume --state run_state.json
```

Khi sửa một bài trong đợt, cập nhật nội dung ngay tại thư mục gốc của bài đó rồi dùng `--update-input` trỏ tới chính thư mục ấy. Sau khi xử lý riêng xong, resume đợt để cập nhật kết quả tổng. Các tùy chọn giới hạn/thời gian/sample truyền cho cả đợt áp dụng cho mọi bài; cần khác biệt thì chạy riêng từng bài.

## Cấu trúc 10 file của mỗi bài

Luồng một bài vẫn được hỗ trợ: trỏ `--input` trực tiếp tới `problem/problem1` hoặc một thư mục chứa 10 file `.txt`. Nếu cần tạo một bộ mới:

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
5. Kiểm tra các cấu hình đang theo dõi và cảnh báo Polygon, commit, xác nhận revision sạch, yêu cầu package Standard với `full=false`, `verify=true`.
6. Poll đúng package ID của revision đó đến `READY`; trạng thái `FAILED` luôn là lỗi.
7. Lấy link chính thức, lưu `result.json` và `problem_url.txt`.

JSON kết quả gồm problem ID, tên định danh, tên hiển thị, ngôn ngữ, số test, sample indices, quyền `codeforces`, revision, package ID/trạng thái, link bài và giới hạn/tên file thực tế. Thông báo tiến độ nằm ở stderr. Để stdout chỉ có link sau khi thành công:

```powershell
.\.venv\Scripts\python.exe polygon_upload.py run --input my_problem --url-only
```

Nếu muốn tách checkpoint/kết quả của từng bài:

```powershell
.\.venv\Scripts\python.exe polygon_upload.py run --input my_problem --state run_state_my_problem.json --output-dir results\my_problem
```

## Sample và cấu hình

Sample tự động được nhận diện từ token hoặc giá trị tham số bằng đúng `sample` trong trường `scriptLine` của từng test Polygon đã triển khai, ví dụ `gen sample 1 > $` hoặc `gen --mode=sample --id=2 > $`. Các từ `nonsample`, `not_sample`, `sample.txt` không khớp. Công cụ dùng `index` của test thực tế, không dùng số dòng script; điều này áp dụng cả khi script có FreeMarker/vòng lặp.

Có thể ưu tiên danh sách chỉ số cụ thể:

```powershell
.\.venv\Scripts\python.exe polygon_upload.py run --input my_problem --sample-indices 1,3
```

Chỉ cờ `testUseInStatements` được cập nhật. Input và lệnh sinh test không được gửi lại khi đánh dấu sample. Test thường được đặt cờ false. Nếu không tìm được sample, công cụ dừng tại checkpoint, không tự lấy test đầu tiên.

| Tùy chọn | Giá trị / hành vi |
| --- | --- |
| `--time-limit` | Millisecond, 250–15000, chia hết cho 50 |
| `--memory-limit` | MB, 4–1024 |
| `--input-file`, `--output-file` | Tên file vào/ra, mỗi tên 1–64 ký tự; không được giống nhau |
| `--source-type` | Mặc định `cpp.g++17`, gửi cùng checker, generator và solution |
| `--request-timeout` | Mặc định 60 giây mỗi request |
| `--retries` | Mặc định 3 lần thử lại cho lỗi đọc tạm thời; request ghi không tự lặp trong cùng lần chạy |
| `--request-interval` | Mặc định 1 giây giữa các request, dùng chung cho cả đợt nhiều bài |
| `--jobs` | Chỉ nhận 1; mỗi lần xử lý một bài |
| `--poll-interval` | Mặc định 5 giây giữa các lần kiểm tra package |
| `--poll-timeout` | Mặc định 900 giây cho một lần chờ package |

Nếu không truyền time limit, memory limit hoặc tên file, CLI giữ mặc định thực tế của Polygon và in chúng khi chạy. Công cụ không tự thêm validator hoặc thay ràng buộc đề. Nếu thiếu validator, checker tests hoặc thành phần khác khiến Polygon chặn đóng gói, lỗi thực tế được giữ nguyên để bạn xử lý. Nếu mã dùng `testlib.h`, công cụ kiểm tra resource đã có; trường hợp Polygon cung cấp thư viện ngoài danh sách resource sẽ được xác nhận qua build có kiểm tra. Lỗi compiler/build không bị chuyển thành kết quả thành công.

## Tiếp tục khi bị gián đoạn

Giữ nguyên thư mục gồm 10 file đầu vào và checkpoint, rồi chạy:

```powershell
.\.venv\Scripts\python.exe polygon_upload.py resume --state run_state.json
```

Checkpoint có dấu vân tay đầu vào local, ghi nhận các request upload đã thành công và trạng thái server đang theo dõi. `run` từ chối dùng lại checkpoint đã tồn tại; `resume` tiếp tục trên đúng ID. Với `resume` thông thường, input phải giữ nguyên; dùng `--update-input` bên dưới nếu chủ động sửa nội dung. Công cụ vẫn kiểm tra revision, statement, lựa chọn checker, test/sample, quyền truy cập và các file ngoài bốn phần upload. Nội dung `checker.cpp`, `gen.cpp`, `solution.cpp` và script không được đối chiếu với server.

Nếu đang dở một trong bốn request upload này, `resume` gửi lại vào **đúng tên file/testset** rồi ghi nhận khi API trả thành công. Bước đã có ghi nhận thành công được bỏ qua khi đầu vào local không đổi. Checkpoint của bản cũ tự chuyển sang cơ chế này; các quy tắc khôi phục tạo bài, commit và build package vẫn được giữ riêng.

Các tình huống cần xử lý:

- **Kẹt tại `checker.cpp`, `gen.cpp`, `solution` hoặc `script` do lỗi đọc lại của bản cũ:** cập nhật repository, giữ nguyên bộ đầu vào và `run_state.json`, rồi bấm `start.bat polygon-legacy resume`. Công cụ gửi lại bước đang dở và tiếp tục trên cùng bài, không còn lỗi so sánh byte/nội dung cho bốn phần này.
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

Tài liệu API không cam kết trường `url` trong đối tượng Problem/Package. Công cụ trước hết đọc `problem.xml` từ đúng package Standard và chỉ dùng URL nếu thực sự có trong metadata phù hợp. Không tự ghép URL từ owner/name, không trả link editor, API hoặc ZIP để thay link bài.

Nếu package không cung cấp link, dùng nhánh đọc giao diện bằng Playwright:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-browser.txt
.\.venv\Scripts\python.exe -m playwright install chromium
.\.venv\Scripts\python.exe polygon_upload.py resume --state run_state.json --browser
```

Trình duyệt mở để bạn đăng nhập thủ công lần đầu và mở đúng bài theo problem ID. Công cụ đọc link/input thực tế từ DOM, kiểm tra bài đang mở rồi lấy link Polygon. Phiên riêng được lưu trong `.polygon-browser`; có thể đổi bằng `--browser-profile`. `--browser-timeout` mặc định 300 giây. Nếu không thể xác minh link, CLI dừng và giữ checkpoint dù package đã `READY`; không tạo link giả hoặc báo đã import Gym.

## Kiểm thử và giới hạn đã xác minh

Bộ kiểm thử offline/mock được giữ riêng trong workspace phát triển, không đưa lên GitHub. Repository chứa mã chạy, cấu hình `.env` và 10 bộ đầu vào trống trong `problem/problem1` đến `problem/problem10`. File thử nghiệm, dữ liệu test, checkpoint và kết quả chạy không được đưa lên GitHub.

Các nhóm kiểm thử bao phủ parser UTF-8/BOM, note rỗng, tiếng Việt/LaTeX, file thiếu/thừa, alias trùng, sample theo index sau triển khai, tránh nhận nhầm `nonsample`, chữ ký/HTTP/API errors, checkpoint/resume, tạo bài/build bị mất phản hồi, xung đột, package `FAILED`, cùng trích xuất URL từ dữ liệu mẫu. Phần nhiều bài được kiểm tra offline/mock về thứ tự 1–10, đầu vào trùng/sai, chạy tuần tự, dừng trước bài kế tiếp khi có lỗi, giới hạn nhịp gọi API, tách checkpoint/kết quả, lỗi một bài, tiếp tục các bài chưa xong, tương thích một bài và reset checkpoint.


**Phần nhiều bài được kiểm thử offline/mock, chưa chạy end-to-end trên tài khoản Polygon thật.** Bộ khởi chạy Windows được kiểm tra cấu trúc lệnh, chưa chạy trên Windows trong môi trường phát triển này. Compiler phía server, tải file thật, render statement, phiên đăng nhập browser và package thực tế cần được xác nhận bằng lần chạy của bạn. Không có problem ID, package hoặc link thành công thật được tạo sẵn trong repository.

API được đối chiếu với [tài liệu Polygon API chính thức](https://codeforces.github.io/polygon-misc/API), gồm `notes`, tag `MA`, `testUseInStatements`, `problem.setAccess`, commit và package. [Trang apiHelp](https://polygon.codeforces.com/apiHelp) là điểm tra cứu bổ sung trên Polygon.
