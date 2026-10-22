# Gemini Export — 10 file .txt

Công cụ sao chép câu trả lời gồm **Part 1–10** trên Gemini thành 10 file `.txt` UTF-8 trong thư mục `problem/`. Script lấy nội dung bên trong từng khối code và lưu vào máy.

## Bấm đúp để chạy trên Windows

Cần Python **3.10 trở lên** và Chrome, Edge hoặc Chromium.

1. Bấm đúp **`start_copy_gemini.bat`**.
2. Dán link cuộc trò chuyện, ví dụ `https://gemini.google.com/app/bc39f110ac308517`, rồi nhấn Enter.
3. Trong cửa sổ trình duyệt vừa mở, đăng nhập đúng tài khoản Google nếu cần. Chờ câu trả lời đủ **Part 1–10** hoàn tất và cuộn tới cuối.
4. Quay lại cửa sổ script, nhấn Enter để xuất file.
5. Mở thư mục `problem/` để lấy đủ 10 file.

File bấm đúp tìm Python theo thứ tự `.venv\Scripts\python.exe`, `py -3`, rồi `python`, và cài Playwright nếu chưa có. Bộ file cũ trong `problem/` chỉ được thay sau khi đọc và kiểm tra đủ các phần. Cửa sổ được giữ mở để đọc kết quả hoặc lỗi. Muốn dừng giữa chừng, nhấn **Ctrl+C** trong cửa sổ script.

## Tên file đầu ra

| Phần trong Gemini | File được tạo |
| --- | --- |
| Part 1: Polygon Problem Name | `name problem.txt` |
| Part 2: Statement Name | `name.txt` |
| Part 3: Statement | `lengend.txt` |
| Part 4: Input Format & Constraints | `input.txt` |
| Part 5: Output Format | `output.txt` |
| Part 6: Note (Explanation) | `note.txt` |
| Part 7: Checker | `checker.txt` |
| Part 8: Test Generator | `gen.txt` |
| Part 9: Polygon FreeMarker Script | `script_sinh_test.txt` |
| Part 10: Optimal C++ Solution | `solution.txt` |

`lengend.txt` và `name problem.txt` giữ đúng cách viết trong ảnh mẫu. Mỗi phần cần đúng một khối code, kể cả khối trống cho Part 6. Chỉ nội dung trong khối được lưu; tiêu đề, nhãn Plaintext/C++, nút Copy/Download và dấu code fence được bỏ qua. Script giữ tiếng Việt, LaTeX, `$`, backslash, thụt dòng và dấu cách. Tên bài được sao chép nguyên văn, không áp dụng quy tắc tên của dịch vụ upload.

Nếu thiếu hoặc trùng phần, có nhiều khối code hay khối bắt buộc rỗng, script báo lỗi trước khi thay bộ file cũ. `note.txt` được để trống. Chế độ trình duyệt chọn câu trả lời cuối cùng có tiêu đề Part; câu trả lời mới chưa đủ phần sẽ gây lỗi thay vì dùng câu trả lời cũ hơn.

## Chạy bằng PowerShell

Chạy trong thư mục repository:

```powershell
py -3 -m pip install -r requirements.txt
py -3 gemini_export.py --url "https://gemini.google.com/app/bc39f110ac308517" --output problem --overwrite
```

Không truyền `--url` thì script hỏi link. `--output` mặc định là `problem`; thư mục đã tồn tại cần `--overwrite`. Thư mục được thay chỉ được chứa các tên file chuẩn trong bảng. Có thể xuất một bộ riêng bằng `--output my_problem`.

Mặc định script thử Chrome, Edge rồi Chromium. Dùng `--channel chrome`, `--channel msedge` hoặc `--channel chromium` để chọn cụ thể. Nếu cần cài Chromium:

```powershell
py -3 -m playwright install chromium
```

Chế độ trình duyệt cần phiên máy tính có giao diện. Phiên Google lưu riêng trong `.gemini-browser/`, được bỏ qua bởi Git; `--browser-profile` chọn thư mục phiên khác. Nếu Google chặn đăng nhập hoặc giao diện Gemini thay đổi, dùng cách sao chép Markdown bên dưới.

## Xuất từ câu trả lời đã copy

Trong trình duyệt thường, dùng nút **Copy response** của toàn bộ một câu trả lời đã hoàn tất. Tạo thư mục `work` nếu chưa có, dán vào `work/gemini_response.md` và lưu UTF-8. Giữ tiêu đề `Part 1:` đến `Part 10:` và các code fence (ba dấu backtick hoặc dấu `~`), bao gồm khối trống của Part 6. Chạy:

```powershell
py -3 gemini_export.py --from-file work/gemini_response.md --output problem --overwrite
```

Chế độ `--from-file` chỉ dùng thư viện chuẩn Python, không cần cài Playwright hoặc đăng nhập.

## Kiểm thử

```powershell
py -3 -m unittest -v test_gemini_export
```

Các kiểm thử kiểm tra việc giữ nguyên nội dung, tạo đúng 10 file, từ chối câu trả lời không đầy đủ và khôi phục bộ file cũ nếu thay thư mục thất bại. Kiểm thử DOM dùng Playwright với HTML mô phỏng câu trả lời. Chưa kiểm thử đăng nhập hoặc đọc end-to-end trên tài khoản Gemini thật; link cuộc trò chuyện cần quyền của tài khoản Google đang đăng nhập.
