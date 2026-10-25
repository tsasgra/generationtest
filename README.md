# 10 bài: ảnh → Gemini → Polygon

`start.bat` chạy trọn luồng cho **10 bài**: gửi ảnh lên 10 tab Gemini song song, lấy đủ 10 phần của từng bài, rồi tải 10 bài lên Polygon song song. Khi hoàn tất, `report.txt` chứa link chính thức theo thứ tự `problem1` đến `problem10`.

## Chuẩn bị

Cài Python 3.10 trở lên và Chrome hoặc Edge trên Windows. Lần đầu chạy Start, công cụ tạo `.venv-gemini` và cài các thư viện còn thiếu. Đăng nhập Google trực tiếp trong cửa sổ trình duyệt được mở; các lần sau dùng lại profile riêng `.gemini-browser-native`.

Đặt ảnh theo đúng cặp thư mục:

| Ảnh đầu vào | Nội dung nhận từ Gemini | Kết quả Polygon |
| --- | --- | --- |
| `img/img1/` | `problem/problem1/` | Bài 1 trong `report.txt` |
| `img/img2/` | `problem/problem2/` | Bài 2 trong `report.txt` |
| … | … | … |
| `img/img10/` | `problem/problem10/` | Bài 10 trong `report.txt` |

Mỗi thư mục ảnh chứa từ 1 đến 10 ảnh của **cùng một bài**. Cả 10 thư mục phải có ảnh hợp lệ. Nếu một bài có nhiều trang, lưu mỗi trang thành một ảnh riêng và đặt tên theo thứ tự. Sau khi xác nhận ảnh đã gửi và đã lưu đủ 10 phần, công cụ chuyển ảnh gốc của bài đó từ `img/imgN/` sang `problem/problemN/img/`. Ảnh chưa gửi thành công vẫn ở thư mục nguồn. Chạy `python pipeline.py init` để tạo các thư mục trống nếu chưa có.

Cấu hình hai biến `POLYGON_API_KEY` và `POLYGON_API_SECRET` trong file `.env` cạnh script, hoặc trong biến môi trường. `.env`, ảnh, nội dung đề, checkpoint và kết quả chỉ lưu trên máy, không được đưa lên Git. Giá trị trong `.env` được đọc như văn bản, không thực thi như lệnh shell.

## Các nút chạy

| File | Hành vi |
| --- | --- |
| **`start.bat`** | Xóa trạng thái lần trước và toàn bộ file `.txt` trực tiếp trong `problem/problem1`…`problem/problem10`, rồi bắt đầu lượt mới từ ảnh. |
| `start_check.bat` | Kiểm tra đủ 10 bộ ảnh, không xóa nội dung cũ và không gọi Gemini/Polygon. |
| `start_resume.bat` | Tiếp tục giai đoạn Polygon đã có checkpoint; không gửi lại ảnh và không xóa đầu vào. |
| `stop.bat` | Dừng các tiến trình thuộc luồng chạy. |

Start dọn checkpoint mặc định, dữ liệu tạm, kết quả Polygon và `report.txt` cũ. Ảnh trong cả thư mục nguồn lẫn `problem/problemN/img/`, `.env`, thư viện đã cài và phiên đăng nhập Google được giữ lại. Start không xóa bài hoặc cuộc trò chuyện đã tạo trên máy chủ. Sau khi reset, đây là lượt tạo mới: nếu tên định danh đã tồn tại trên Polygon, cần dùng tên mới hoặc dùng Resume để tiếp tục lượt cũ trước khi bấm Start. Muốn gửi lại ảnh đã chuyển, chép chúng từ `problem/problemN/img/` về `img/imgN/` trước khi Start; công cụ không tự gửi lại ảnh cũ trong kho lưu.

Mỗi bài phải trả về đủ một bộ 10 phần, gồm `name problem.txt`, `name.txt`, `lengend.txt`, `input.txt`, `output.txt`, `note.txt`, `checker.txt`, `gen.txt`, `script_sinh_test.txt`, `solution.txt`. `note.txt` được phép rỗng. Tên định danh chỉ gồm chữ thường ASCII, chữ số và dấu `-`; cả 10 bài phải có tên khác nhau.

Nếu Gemini lỗi hoặc thiếu phần, luồng dừng trước khi tạo bài trên Polygon. Sau khi đủ cả 10 bộ hợp lệ, các tác vụ Polygon chạy song song với checkpoint riêng cho mỗi bài. Khi một bài lỗi, công cụ ghi rõ tình trạng trong báo cáo và giữ kết quả của những bài đã thành công; không báo đủ 10 link khi chưa hoàn tất.

Nếu `input`, `output`, `note`, `name` hoặc `legend`/`lengend` có tham chiếu ảnh, ví dụ `\includegraphics{hinh.png}`, công cụ vẫn tải nội dung lên như bình thường và thêm dòng **`problemN thiếu ảnh`** ở cuối `report.txt` cho từng bài liên quan. Cảnh báo được giữ cả khi một bài chưa tạo package thành công và khi Resume. Công cụ không tự tải ảnh vào **Statement Resource Files** của Polygon; bạn dùng ảnh trong `problem/problemN/img/` để bổ sung thủ công, với tên file khớp đường dẫn trong statement.

Nếu tên PNG gửi cho Gemini khác tên ảnh gốc, bản PNG đó được giữ thêm trong `problem/problemN/img/uploaded/`. Khi statement tham chiếu tên dạng `0001_...png`, dùng bản trong `uploaded/`. Ảnh lưu từ lượt cũ không bị ghi đè; nếu trùng tên nhưng khác nội dung, bản mới được thêm hậu tố và đường dẫn được in ra khi chạy.

## Chạy bằng dòng lệnh

```powershell
python -m pip install -r requirements.txt
python pipeline.py init
python pipeline.py check
python pipeline.py run
```

Giảm số tác vụ đồng thời hoặc tăng thời gian chờ khi cần:

```powershell
python pipeline.py run --workers 5 --polygon-workers 5 --response-timeout 1200 --poll-timeout 1800
```

`--workers` điều khiển Gemini, `--polygon-workers` điều khiển Polygon, mặc định đều là 10. Các công việc Polygon chạy đồng thời nhưng điều tiết request dùng chung để tránh dồn tải lên một tài khoản. Có thể truyền `--time-limit` (ms), `--memory-limit` (MB), `--source-type`, `--request-interval` và `--prompt`. Tùy chọn không truyền giữ mặc định Polygon.

Chỉ tải 10 bộ nội dung đã có lên Polygon hoặc tiếp tục lượt tải:

```powershell
python polygon_batch.py run --input problem --state-dir .pipeline-state/polygon --output-dir polygon_results --report report.txt
python polygon_batch.py resume --input problem --state-dir .pipeline-state/polygon --output-dir polygon_results --report report.txt
```

Các checkpoint được lưu riêng trong `.pipeline-state/polygon/`; kết quả từng bài ở `polygon_results/`. Khi Polygon báo request tạo bài hoặc build mất phản hồi, kiểm tra trạng thái thật trên Polygon trước khi khôi phục theo thông báo của công cụ; không bấm Start để thử tạo lại cùng tên.

`gemini_upload.py` và `polygon_upload.py` vẫn hỗ trợ chạy từng giai đoạn. `python polygon_upload.py --help` hiển thị tùy chọn khôi phục một bài (`--problem-id`, `--package-id`, `--update-input`, `--retry-failed-package`). Luồng ảnh riêng có thể bỏ qua thư mục trống; luồng chung `pipeline.py` yêu cầu đủ 10 bài.

## Phạm vi kiểm tra

Các kiểm tra cục bộ bao phủ điều phối 10 bài, dữ liệu thiếu/sai, thứ tự các giai đoạn, reset, checkpoint và báo cáo. Ảnh thật, phiên đăng nhập Google, giao diện Gemini hiện tại và khả năng build package của Polygon cần được kiểm tra trong lần chạy trên máy có dữ liệu/tài khoản. Repository chỉ chứa mã chạy, cấu hình thư viện và hướng dẫn; không chứa file test/example, ảnh, nội dung đề hay báo cáo mẫu.
