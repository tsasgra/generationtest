# Ảnh → Gemini → Polygon

Chỉ dùng một file **`start.bat`** cho cả Start và Stop. Bấm đúp để mở menu:

- **1 — Start mới:** dừng lượt cũ, dọn checkpoint và dữ liệu chạy cũ, rồi chạy từ đầu.
- **2 — Stop:** dừng tác vụ hiện tại; menu vẫn mở.
- **3 — Resume:** chủ động tiếp tục lượt đang dở.
- Các mục còn lại dùng để kiểm tra dữ liệu hoặc chạy riêng Gemini/Polygon.

Trên Windows, tác vụ mở trong cửa sổ riêng, nên có thể chọn Stop ngay trong menu.
Chọn Start mới thực hiện liên tục:

```text
img/imgN/ → gửi ảnh lên Gemini → lấy đủ 10 phần → problem/problemN/
          → kiểm tra nội dung bài N → hoàn tất Polygon → chuyển sang bài N+1
```

Hỗ trợ **1–10 bài** mỗi lượt. Mỗi thư mục ảnh chứa 1–10 ảnh của cùng một bài.
Thư mục trống được bỏ qua; số bài luôn được giữ nguyên: chỉ có ảnh trong `img2`
và `img10` thì kết quả nằm trong `problem2` và `problem10`.
Các bài chạy **lần lượt theo số thứ tự**. Bài N phải nhận đủ 10 phần, tải lên Polygon
và có package READY cùng link hợp lệ rồi mới gửi ảnh bài kế tiếp lên Gemini.
Nếu một bài lỗi, luồng dừng tại bài đó; các bài phía sau chưa được gửi.

## Cách dùng

1. Clone hoặc tải toàn bộ nhánh `main`. Cài Python 3.10+ và Chrome hoặc Edge trên Windows.
2. Repository có sẵn `img/img1`…`img/img10` và 10 bộ file trống trong `problem/problem1`…`problem/problem10`.
   Có thể dùng `start.bat init` để tạo lại các thư mục bị thiếu.
3. Đặt ảnh vào các thư mục `img/imgN/`. Nếu đề có nhiều trang, đặt tên ảnh theo thứ tự,
   chẳng hạn `01.png`, `02.png`. Cũng chấp nhận `img/img(1)/`…`img/img(10)/`;
   không dùng đồng thời `img1` và `img(1)`.
4. Chép `.env.example` thành `.env` cạnh `pipeline.py` và điền khóa của bạn:

   ```dotenv
   POLYGON_API_KEY=your_api_key
   POLYGON_API_SECRET=your_api_secret
   ```

5. Bấm đúp **`start.bat`**, chọn **1 — Start mới**. Lần đầu, script tự tạo `.venv-gemini` và cài thư viện
   trong `requirements.txt`. Đăng nhập Google trực tiếp ở cửa sổ Chrome/Edge được mở;
   những lần sau dùng lại phiên đăng nhập.
6. Khi hoàn tất, mở **`report.txt`** để lấy link Polygon theo thứ tự bài.

Biến môi trường cũng được hỗ trợ thay cho `.env`. File `.env` được đọc như văn bản,
không thực thi lệnh. Khóa API, ảnh, profile trình duyệt và checkpoint/kết quả phụ được
bỏ qua bởi Git. Riêng 100 file `.txt` mẫu trong `problem/` được theo dõi để giữ đầy đủ
cấu trúc của nhánh Polygon; khi sinh đề vào các file này, Git sẽ hiển thị thay đổi cục bộ.

## Lệnh chạy

Các lệnh đều dùng chung `start.bat` hoặc `python pipeline.py`:

| Lệnh | Chức năng |
| --- | --- |
| `start.bat` | Mở menu Start/Stop dùng chung |
| `start.bat run` | Dừng lượt cũ, dọn trạng thái và chạy mới toàn bộ luồng |
| `start.bat init` | Tạo các thư mục đầu vào/đầu ra, không ghi đè file |
| `start.bat check` | Kiểm tra ảnh offline, giữ kết quả cũ |
| `start.bat resume` | Tiếp tục bài đang dở và các bài còn lại; không gửi lại bài đã nhận đủ nội dung |
| `start.bat stop` | Dừng tác vụ, giữ checkpoint và kết quả |
| `start.bat gemini` | Chỉ gửi ảnh lên Gemini và lưu nội dung vào `problem/` |
| `start.bat polygon` | Tải các bộ nội dung đã có trong `problem/` lên Polygon |
| `start.bat polygon-one resume --state .pipeline-state/polygon/02.json` | Khôi phục riêng bài 2 |

Các chế độ từ hai nhánh vẫn được giữ trong launcher chung:

| Lệnh | Hành vi |
| --- | --- |
| `start.bat gemini`, `python -m gemini_tool.launch` | Chạy riêng Gemini qua bộ khởi động chung |
| `python gemini_upload.py` | CLI Gemini, giữ các tùy chọn `--input`, `--dry-run`, `--attach-only`, `--keep-images` |
| `python polygon_upload.py` | CLI Polygon một bài/nhiều bài, hỗ trợ `init --count`, `--jobs`, `--url-only` và checkpoint cũ |
| `start.bat polygon-legacy auto` | Chế độ Polygon cũ: tự chạy mới hoặc tiếp tục `run_state.json` |
| `start.bat polygon-legacy check` | Kiểm tra nội dung `problem/` offline; `start.bat check` kiểm tra ảnh |
| `start.bat resume` | Tiếp tục checkpoint pipeline nếu có; nếu không, tiếp tục `run_state.json` |
| `start.bat polygon-legacy stop`, `python -m polygon_tool.stop` | Dừng uploader riêng và xóa checkpoint/kết quả của chế độ Polygon cũ |

Các file Start/Stop phụ và `polygon_tool/launch_windows.cmd` đã được gộp vào `start.bat`.
Stop trong menu giữ checkpoint để Resume; chọn Start mới sẽ dọn chúng. Chế độ Polygon riêng lưu
checkpoint con trong `run_state.problems/`, kết quả trong `results/`, `result.json` và
`problem_url.txt`. Cả hai định dạng checkpoint đều được giữ, không tự chuyển đổi lẫn nhau.
Các bộ 10 file mẫu hoàn toàn trống được bỏ qua; bộ chỉ điền một phần sẽ báo lỗi.

Ví dụ tăng thời gian chờ:

```powershell
start.bat --response-timeout 1200 --poll-timeout 1800
```

Mọi chế độ, kể cả Gemini/Polygon chạy riêng và Resume checkpoint cũ, đều xử lý một
bài tại một thời điểm. `--workers`, `--polygon-workers` và `--jobs` được giữ để tương
thích lệnh cũ nhưng chỉ nhận giá trị `1`. Request Polygon vẫn có khoảng nghỉ theo
`--request-interval`.

```powershell
python pipeline.py --help
python pipeline.py run --help
python pipeline.py polygon run --dry-run
python pipeline.py polygon-one --help
```

Các tùy chọn `--time-limit` (ms), `--memory-limit` (MB), `--source-type`,
`--request-interval` và `--prompt` vẫn được hỗ trợ. Tùy chọn giới hạn không truyền
giữ mặc định Polygon. `polygon-one` giữ các chức năng khôi phục `--problem-id`,
`--package-id`, `--update-input` và `--retry-failed-package`.

## Kết quả và chạy tiếp

Mỗi bài có đúng 10 file: `name problem.txt`, `name.txt`, `lengend.txt`, `input.txt`,
`output.txt`, `note.txt`, `checker.txt`, `gen.txt`, `script_sinh_test.txt`, `solution.txt`.
`note.txt` được phép rỗng. Tên định danh chỉ gồm chữ thường ASCII, chữ số và dấu `-`;
các bài phải có tên khác nhau. Đầu vào Polygon cũng chấp nhận `legend.txt` thay
cho `lengend.txt`, và thư mục `problem(N)` thay cho `problemN`.

Sau khi xác nhận Gemini đã lưu ảnh và xuất đủ nội dung, ảnh gốc được chuyển vào
`problem/problemN/img/`. Bản PNG đã chuyển đổi nằm trong `img/uploaded/` khi cần.
Ảnh chưa hoàn tất vẫn ở đầu vào. Nếu đề tham chiếu ảnh, `report.txt` ghi
`problemN, nameproblem, thiếu ảnh`; bổ sung các ảnh đó vào **Statement Resource Files**
của Polygon với tên khớp statement.

**Start luôn là lượt chạy mới**. Trên Windows, script tự dừng tiến trình và trình duyệt
của lượt cũ, kể cả lượt đang chạy hoặc bị gián đoạn khi cài thư viện. Sau khi kiểm tra
cấu hình API và ảnh thành công, script xóa checkpoint, báo cáo, kết quả cũ và toàn bộ
`problem/`, kể cả ảnh đã lưu, rồi tạo lại thư mục nhận bài. Tab khôi phục, kết nối và
dữ liệu tạm được dọn. Ảnh trong `img/`, `.env`, thư viện và đăng nhập được giữ lại.
Muốn gửi lại ảnh đã chuyển, chép chúng về `img/imgN/` trước khi Start.
Đầu vào hoặc cấu hình không hợp lệ sẽ không xóa bộ kết quả cũ.
Reset áp dụng cho dữ liệu cục bộ; chat Gemini và bài Polygon đã tạo vẫn tồn tại trên máy chủ.

Nếu Gemini lỗi hoặc thiếu phần, script dừng trước bước Polygon của bài đó. Các bài
đã hoàn thành và ảnh của các bài chưa xử lý được giữ lại. Dùng `start.bat resume`
để tiếp tục; nếu đã có đủ 10 file của bài đang dở, script dùng lại chúng.

Nếu Polygon lỗi, xem `report.txt` và dùng **`start.bat resume`**. Checkpoint riêng ở
`.pipeline-state/polygon/`; kết quả ở `polygon_results/problemN/`. Resume giữ ID bài
và package, kiểm tra nội dung/đường dẫn với checkpoint, và từ chối tạo lại bài khi
checkpoint của bài đã bắt đầu bị mất. Danh sách đầy đủ các bài được lưu trước bước
Gemini đầu tiên; `report.txt` luôn hiển thị cả các bài chưa đến lượt. Resume hoàn tất
bài hiện tại trên Polygon rồi mới xử lý ảnh bài tiếp theo. Với checkpoint từ bản
cũ chỉ có giai đoạn Polygon, Resume tiếp tục các bài đó lần lượt như trước.
Khi request tạo bài/build bị mất phản hồi,
khôi phục riêng bài theo hướng dẫn lỗi rồi chạy Resume cho cả lô.

## Cấu trúc và kiểm thử

`pipeline.py` là điểm vào chung, gồm khởi động môi trường và điều phối các giai đoạn.
`pipeline_reset.py` quản lý reset và khóa phiên chạy. `gemini_tool/` chứa trình duyệt,
ảnh và bộ đọc phản hồi; `polygon_tool/` chứa API, bộ đọc 10 phần và quy trình tải bài.
Các file trùng tên được hợp nhất trong cùng module; chỉ còn một launcher Windows
`start.bat`. `polygon_tool/batch.py` giữ cả bộ xử lý pipeline và bộ đọc checkpoint của CLI
Polygon riêng. `requirements-gemini.txt` dùng lại `requirements.txt`, còn
`requirements-browser.txt` dành cho browser fallback của Polygon.

Hướng dẫn chi tiết từ hai nhánh được giữ tại [Gemini](docs/gemini.md) và
[Polygon](docs/polygon.md). [Bảng đối chiếu](docs/merge-inventory.md) ghi nguồn và cách
hợp nhất từng nhóm file. File `.env` chứa khóa được giữ cục bộ; Git chỉ nhận `.env.example`.

```powershell
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

Kiểm thử offline dùng ảnh và phản hồi giả lập để kiểm tra thứ tự các giai đoạn,
thứ tự hoàn tất từng bài qua cả hai dịch vụ, đúng thư mục bài, dữ liệu lỗi, reset,
lưu ảnh, checkpoint, resume và báo cáo.
Gemini và quy trình gọi Polygon được giả lập; đăng nhập Google, giao diện Gemini,
launcher Windows và build package thật cần kiểm tra trên máy có tài khoản/dữ liệu.
