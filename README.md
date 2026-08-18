# BÁO CÁO DỰ ÁN INTERLOG PST TRANSFER

**Tên dự án:** InterLOG PST Transfer

**Phiên bản:** 1.1

**Ngày báo cáo:** 18/08/2026

**Đơn vị sử dụng:** Bộ phận IT - InterLOG

**Phạm vi hiện tại:** Công cụ nội bộ hỗ trợ chuyển file PST dung lượng lớn từ máy ảo/máy backup về máy người dùng.

---

## 1. Bối cảnh

Khi người dùng cần lưu dữ liệu email, bộ phận IT thực hiện export bằng Outlook Classic trên một máy ảo. IT đăng nhập mailbox của người dùng, chọn đúng nguồn cần sao lưu, ví dụ **Online Archive**, sau đó export thành file Outlook Data File (`.pst`).

Các file PST thực tế có thể đạt khoảng 50 GB. Sau khi Outlook export xong, file PST nằm trên ổ đĩa của máy ảo. IT cần chuyển file này qua mạng nội bộ về máy người dùng để import vào Outlook và kiểm tra dữ liệu.

Quy trình cũ:

1. IT export Online Archive/mailbox/folder thành PST trên máy ảo.
2. Trên máy người dùng, IT truy cập thư mục chia sẻ của máy ảo qua đường dẫn UNC.
3. IT dùng File Explorer để copy toàn bộ PST về máy người dùng.
4. IT import hoặc mở PST bằng Outlook Classic.
5. Sau khi xác nhận dữ liệu đầy đủ, IT mới thực hiện các thay đổi quản trị cần thiết đối với Online Archive.

## 2. Vấn đề cần giải quyết

Vấn đề chính không nằm ở bước Outlook export PST. Trong quá trình thử nghiệm, Outlook có thể export một PST khoảng 50 GB tương đối ổn định và có cơ chế xử lý dữ liệu trùng khi chạy lại.

Điểm yếu lớn nhất nằm ở bước **copy PST từ máy ảo về máy người dùng**:

- File có dung lượng rất lớn nên thời gian chuyển lâu.
- Kết nối mạng nội bộ hoặc phiên truy cập máy ảo có thể bị gián đoạn.
- File Explorer không cung cấp quy trình resume đủ tin cậy cho trường hợp vận hành này.
- Nếu quá trình copy bị lỗi, IT thường phải copy lại từ đầu.
- Việc copy lại một file 50 GB gây mất nhiều thời gian và băng thông.
- IT phải giữ cửa sổ copy để theo dõi, gây bất tiện khi xử lý công việc khác.
- Khó xác định file đã chuyển hoàn chỉnh hay chưa nếu quá trình bị ngắt bất thường.

## 3. Mục tiêu dự án

Dự án được xây dựng với các mục tiêu sau:

- Giữ nguyên bước export PST quen thuộc bằng Outlook Classic.
- Cho phép IT chọn chính xác Online Archive, mailbox hoặc folder cần export.
- Chuyển PST từ máy ảo về máy người dùng bằng một cơ chế chạy nền.
- Tự tạm dừng khi mất mạng và tiếp tục khi kết nối phục hồi.
- Không phải copy lại toàn bộ file từ đầu sau lỗi mạng.
- Cho phép đóng giao diện mà job chuyển file vẫn tiếp tục.
- Theo dõi được trạng thái, số byte đã chuyển và lỗi của job.
- Kiểm tra kích thước file sau khi chuyển; tùy chọn kiểm tra SHA-256 khi cần.
- Đóng gói portable để IT giải nén và chạy trên máy người dùng, không cần cài Python hay Outlook add-in.
- Không chứa mật khẩu, Client Secret, dữ liệu email hoặc PST mẫu trong gói phát hành.

## 4. Giải pháp được lựa chọn

Công cụ sử dụng **Windows Background Intelligent Transfer Service (BITS)** để chuyển file PST.

BITS là thành phần có sẵn trong Windows, hỗ trợ:

- Chuyển file ở chế độ nền.
- Tạm dừng khi nguồn mạng tạm thời không truy cập được.
- Tiếp tục chuyển khi mạng hoạt động trở lại.
- Lưu trạng thái job độc lập với cửa sổ giao diện.
- Hạn chế ảnh hưởng đến công việc đang thực hiện trên máy người dùng bằng mức ưu tiên thấp.
- Theo dõi tổng dung lượng và dung lượng đã chuyển.

Giải pháp không thay đổi cách Outlook tạo PST. Công cụ chỉ đảm nhiệm bước sau khi Outlook đã export xong và đã đóng.

Luồng xử lý tổng quát:

```text
Exchange Online / Online Archive
               |
               v
     Outlook Classic trên VM
               |
               | Export
               v
        File PST trên máy ảo
               |
               | Windows BITS, chạy nền, có resume
               v
        File PST trên máy user
               |
               | Mở/import và kiểm tra
               v
             Outlook
```

## 5. Phạm vi của công cụ

### 5.1. Công cụ thực hiện

- Nhận đường dẫn PST nguồn trên máy ảo hoặc thư mục share.
- Nhận thư mục đích trên máy người dùng.
- Kiểm tra file nguồn có phải PST hay không.
- Kiểm tra PST còn bị Outlook khóa hay không.
- Tạo job BITS chạy nền với độ ưu tiên thấp.
- Tạo biên nhận JSON để lưu trạng thái job.
- Theo dõi và tự resume một số lỗi mạng tạm thời.
- Đối chiếu kích thước file nguồn và file đích.
- Tùy chọn đối chiếu SHA-256 sau khi chuyển.
- Ngăn việc bấm nút nhiều lần tạo job trùng cho cùng file và cùng thư mục đích.
- Hiển thị thông tin lỗi BITS để IT chẩn đoán.

### 5.2. Công cụ không thực hiện

- Không tự đăng nhập Outlook hoặc Microsoft 365.
- Không tự export Online Archive thành PST.
- Không gửi, sửa hoặc xóa email.
- Không tự import PST vào Outlook.
- Không tự tắt Online Archive trên Microsoft 365 Admin Center.
- Không xóa PST nguồn trên máy ảo.
- Không thay thế chính sách backup, retention hoặc compliance của Microsoft 365.

## 6. Kiến trúc và thành phần

Gói portable phiên bản 1.1 gồm:

```text
InterLOG-PST-Transfer/
|-- START-PST-TRANSFER.cmd
|-- PST-TRANSFER-GUI.ps1
|-- README.txt
`-- scripts/
    |-- start-pst-bits-transfer.ps1
    `-- monitor-pst-bits-transfers.ps1
```

Chức năng từng thành phần:

- `START-PST-TRANSFER.cmd`: điểm khởi chạy dành cho IT.
- `PST-TRANSFER-GUI.ps1`: giao diện nhập file nguồn, thư mục đích, khởi chạy và kiểm tra trạng thái.
- `start-pst-bits-transfer.ps1`: kiểm tra điều kiện đầu vào, chống job trùng và tạo job BITS.
- `monitor-pst-bits-transfers.ps1`: theo dõi, resume, hoàn tất job và cập nhật biên nhận.
- `README.txt`: hướng dẫn sử dụng nhanh.

## 7. Quy trình vận hành đề xuất

### Bước 1 - Chuẩn bị trên máy ảo

1. Mở Outlook Classic với mailbox cần xử lý.
2. Chọn **File > Open & Export > Import/Export**.
3. Chọn **Export to a file**.
4. Chọn **Outlook Data File (.pst)**.
5. Chọn đúng nguồn cần backup, ví dụ **Online Archive**.
6. Chọn **Include subfolders** nếu cần lấy toàn bộ cây thư mục.
7. Export PST vào ổ đĩa local của máy ảo.
8. Chờ Outlook export hoàn tất.
9. Đóng Outlook để giải phóng khóa trên file PST.
10. Chia sẻ thư mục chứa PST và cấp quyền đọc cho tài khoản thao tác trên máy người dùng.

### Bước 2 - Chuyển PST về máy người dùng

1. Chép file `InterLOG-PST-Transfer-v1.1.zip` sang máy người dùng.
2. Giải nén toàn bộ ZIP vào một thư mục local.
3. Chạy `START-PST-TRANSFER.cmd`.
4. Xác nhận Outlook trên máy ảo đã đóng và PST export đã hoàn tất.
5. Chọn PST nguồn qua đường dẫn UNC, ví dụ:

   ```text
   \\IP-MAY-AO\MailBackup\user_archive.pst
   ```

6. Chọn thư mục lưu local trên máy người dùng.
7. Có thể bật kiểm tra SHA-256 nếu cần mức xác minh cao hơn.
8. Bấm **BẮT ĐẦU CHẠY NGẦM / TỰ RESUME**.
9. Có thể đóng giao diện sau khi job được nhận.
10. Mở lại công cụ và chọn **Kiểm tra job nền** để theo dõi.
11. Chỉ chuyển sang bước tiếp theo khi trạng thái là `COMPLETE`.

### Bước 3 - Xác minh và bàn giao

1. Kiểm tra kích thước PST đích.
2. Mở hoặc import PST bằng Outlook Classic trên máy người dùng.
3. Kiểm tra các folder quan trọng, thư gần nhất và thư cũ.
4. Kiểm tra ngẫu nhiên email có attachment.
5. Ghi nhận kết quả bàn giao.
6. Chỉ xóa PST trên máy ảo hoặc tắt Online Archive sau khi đã xác nhận dữ liệu theo quy trình nội bộ.

## 8. Cơ chế an toàn và khôi phục

### 8.1. Mất mạng

Khi share trên máy ảo tạm thời không truy cập được, BITS đưa job vào trạng thái lỗi tạm thời. Monitor sẽ yêu cầu job tiếp tục khi kết nối phục hồi. Các byte đã chuyển không bị chủ động xóa và người dùng không cần copy lại từ đầu.

### 8.2. Đóng giao diện

Giao diện chỉ dùng để tạo và kiểm tra job. Sau khi BITS đã nhận job, việc đóng giao diện không hủy quá trình chuyển.

### 8.3. Đăng xuất hoặc khởi động lại

Công cụ đăng ký monitor cho phiên đăng nhập của người dùng. Sau khi người dùng đăng nhập lại, monitor tiếp tục theo dõi các job BITS còn tồn tại.

### 8.4. PST đang bị khóa

Nếu Outlook trên máy ảo chưa đóng hoặc vẫn đang export, công cụ từ chối tạo job và yêu cầu IT hoàn tất export trước. Điều này tránh chuyển một PST còn đang thay đổi.

### 8.5. Nguồn thay đổi sau khi tạo job

Công cụ ghi nhận kích thước và thời gian sửa cuối của PST nguồn. Trước khi xác nhận hoàn tất, monitor kiểm tra lại các thông tin này. Nếu nguồn thay đổi, job bị dừng để tránh bàn giao file không nhất quán.

### 8.6. Job trùng

Phiên bản 1.1 nhận biết job đang tồn tại cho cùng PST và cùng thư mục đích. Nếu IT bấm lại nút Start, công cụ trả về trạng thái job đang chạy thay vì tạo thêm job hoặc báo nhầm rằng Outlook đang khóa file.

### 8.7. Xác minh dữ liệu

Mặc định công cụ đối chiếu kích thước file. Khi bật SHA-256, công cụ tính mã băm của cả nguồn và đích. Việc kiểm tra SHA-256 đáng tin cậy hơn nhưng sẽ tốn thêm thời gian đọc hai file, đặc biệt với PST 50 GB.

## 9. Các trạng thái chính

| Trạng thái | Ý nghĩa |
|---|---|
| `QUEUED` | Job đang chờ BITS xử lý. |
| `TRANSFERRING_BACKGROUND` | Job đã được tạo và chạy nền. |
| `TRANSFERRING` | Dữ liệu đang được chuyển. |
| `TRANSIENTERROR` | Lỗi tạm thời, thường do mạng hoặc share; có thể resume. |
| `SUSPENDED` | Job đang tạm dừng. |
| `TRANSFERRED` | BITS đã nhận đủ dữ liệu, đang chờ bước hoàn tất/xác minh. |
| `VERIFYING_SHA256` | Đang đối chiếu SHA-256. |
| `COMPLETE` | File đã chuyển và kiểm tra hoàn tất. |
| `SOURCE_CHANGED_STOPPED` | File nguồn thay đổi trong lúc xử lý; cần kiểm tra lại. |
| `SIZE_MISMATCH` | Kích thước nguồn và đích không khớp. |
| `HASH_MISMATCH` | SHA-256 nguồn và đích không khớp. |
| `ERROR` | BITS gặp lỗi cần IT xử lý. |

## 10. Kết quả kiểm thử

Các nội dung đã được kiểm tra trong môi trường thử nghiệm:

- Giao diện khởi chạy được trên Windows.
- Chọn PST nguồn và thư mục đích được.
- BITS nhận job và chạy nền.
- Đóng giao diện không làm mất job.
- Theo dõi được số byte đã chuyển và tổng dung lượng.
- Một case chuyển PST thực tế khoảng 47,52 GB đã hoàn tất thành công.
- PST đích được tạo tại thư mục local đã chọn.
- Job thử nghiệm sau khi sửa báo đúng trạng thái `COMPLETE`.
- Khi file đích hoàn chỉnh đã tồn tại, công cụ không copy lại và trả về `COMPLETE_EXISTING`.
- Phiên bản 1.1 khắc phục tình trạng bấm Start lại tạo job trùng hoặc báo sai PST đang bị khóa.
- Các script PowerShell đã qua kiểm tra cú pháp.
- Gói ZIP phát hành không chứa PST, EML, JSON test, `.env`, Client Secret hoặc địa chỉ mailbox thử nghiệm.

## 11. Lợi ích so với copy bằng File Explorer

| Tiêu chí | File Explorer | InterLOG PST Transfer |
|---|---|---|
| Chạy nền | Hạn chế | Có |
| Mạng gián đoạn | Có nguy cơ phải copy lại | BITS tự tạm dừng và resume |
| Đóng giao diện | Dừng/mất cửa sổ theo dõi | Job vẫn chạy |
| Theo dõi byte đã chuyển | Cơ bản | Có biên nhận và trạng thái BITS |
| Chống job trùng | Không có quy trình riêng | Có |
| Kiểm tra nguồn thay đổi | Không | Có |
| Kiểm tra kích thước | Thủ công | Tự động |
| SHA-256 | Không tích hợp | Tùy chọn |
| Triển khai | Có sẵn | Portable, không cần cài đặt |

## 12. Yêu cầu triển khai

- Windows 10, Windows 11 hoặc Windows Server có dịch vụ BITS.
- PowerShell 5.1 trở lên.
- Tài khoản Windows trên máy người dùng truy cập được share của máy ảo.
- Máy ảo và máy người dùng có kết nối mạng nội bộ.
- PST phải được export hoàn tất và Outlook trên máy ảo phải đóng.
- Ổ đĩa đích phải còn đủ dung lượng, nên có khoảng trống lớn hơn kích thước PST.
- Không đổi tên, di chuyển hoặc xóa thư mục công cụ trong khi job chưa `COMPLETE`.

## 13. Giới hạn và rủi ro còn lại

- Nếu quyền truy cập share bị thu hồi, job không thể tiếp tục cho đến khi quyền được khôi phục.
- Nếu PST nguồn bị xóa hoặc đổi tên trước khi hoàn tất, job sẽ lỗi.
- Nếu PST nguồn thay đổi trong lúc chuyển, cần tạo lại bản export ổn định.
- BITS không sửa được PST bị lỗi do Outlook export không hoàn chỉnh.
- Kiểm tra SHA-256 trên file 50 GB có thể mất nhiều thời gian và tạo thêm tải đọc đĩa/mạng.
- Nếu máy người dùng tắt hoàn toàn, job không chạy; job tiếp tục sau khi máy bật và người dùng đăng nhập.
- Công cụ hiện phục vụ thao tác IT theo từng case, chưa có dashboard quản lý tập trung nhiều máy.
- PST vẫn có các giới hạn vận hành của Outlook; cần kiểm tra khả năng mở/import trước khi xóa dữ liệu nguồn.

## 14. Khuyến nghị vận hành

- Dùng tên file rõ ràng, ví dụ `user_online_archive_2026.pst`.
- Export vào ổ local của máy ảo trước, không export trực tiếp qua mạng.
- Luôn đóng Outlook trên máy ảo trước khi khởi chạy công cụ.
- Không dùng File Explorer copy song song cùng một PST.
- Không xóa PST nguồn cho đến khi trạng thái `COMPLETE` và Outlook mở được PST đích.
- Với case quan trọng, bật SHA-256 hoặc kiểm tra hash bằng quy trình riêng.
- Giữ log/receipt cùng PST đích trong thời gian bàn giao.
- Kiểm tra dung lượng ổ đĩa trước khi chuyển.
- Chỉ IT được thực hiện bước tắt Online Archive hoặc xóa dữ liệu nguồn.

## 15. Hướng phát triển đề xuất

Các cải tiến có thể thực hiện sau khi phiên bản 1.1 vận hành ổn định:

1. Hiển thị phần trăm và tốc độ chuyển trực tiếp trên giao diện.
2. Hiển thị danh sách tất cả job thay vì từng job riêng lẻ.
3. Nút Pause, Resume và Retry dành cho IT.
4. Xuất báo cáo hoàn tất theo từng user/case.
5. Ghi Windows Event Log hoặc log text tập trung.
6. Cảnh báo thiếu dung lượng trước khi tạo job.
7. Tự động kiểm tra quyền truy cập share và đưa ra hướng dẫn lỗi dễ hiểu hơn.
8. Ký số PowerShell script hoặc đóng gói bằng bộ cài nội bộ nếu triển khai diện rộng.

## 16. Kết luận

InterLOG PST Transfer giải quyết đúng điểm nghẽn của quy trình hiện tại: chuyển một file PST rất lớn từ máy ảo về máy người dùng trong điều kiện mạng có thể không ổn định.

Giải pháp giữ nguyên cách IT lựa chọn và export đúng Online Archive/mailbox/folder bằng Outlook, đồng thời thay bước copy File Explorer bằng Windows BITS có khả năng chạy nền và resume. Điều này giảm nguy cơ phải chuyển lại toàn bộ file 50 GB, giảm thời gian thao tác thủ công và cung cấp trạng thái rõ ràng để IT xác minh trước khi bàn giao.

Phiên bản 1.1 đã đủ điều kiện để tiếp tục sử dụng trong môi trường thử nghiệm/pilot. Trước khi áp dụng rộng rãi, nên thực hiện thêm nhiều case với dung lượng, chất lượng mạng và quyền share khác nhau, đồng thời chuẩn hóa checklist bàn giao và quy trình xóa dữ liệu nguồn.

---

## Phụ lục A - Thông tin gói phát hành

**Tên file:** `InterLOG-PST-Transfer-v1.1.zip`

**SHA-256:** `B65976703E5279949DAF1C99CD434B087B1E2931264E249E14F86A3E27553B99`

## Phụ lục B - Checklist nhanh cho IT

- [ ] Chọn đúng mailbox/Online Archive/folder cần export.
- [ ] Bật Include subfolders nếu yêu cầu lấy toàn bộ cây thư mục.
- [ ] Export PST vào ổ local của máy ảo.
- [ ] Chờ export xong và đóng Outlook.
- [ ] Xác nhận máy user truy cập được đường dẫn share.
- [ ] Xác nhận ổ đích đủ dung lượng.
- [ ] Chạy `START-PST-TRANSFER.cmd`.
- [ ] Chọn đúng PST nguồn và thư mục đích.
- [ ] Chờ trạng thái `COMPLETE`.
- [ ] Mở/import PST bằng Outlook Classic.
- [ ] Kiểm tra folder, email mới/cũ và attachment.
- [ ] Chỉ xử lý/xóa nguồn sau khi xác minh và bàn giao.

## Phụ lục C - Mail Operations Dashboard (MVP)

Repository có thêm MVP tại thư mục `dashboard/`:

- React dashboard dành cho IT.
- FastAPI backend và SQLite lưu job/event/history.
- Tạo yêu cầu theo mailbox, Mailbox chính, Online Archive hoặc folder cụ thể.
- Chọn lịch chạy, export engine và thư mục PST đích.
- Timeline trạng thái từ lúc lên lịch đến export, transfer, verify và hoàn tất.
- Mặc định bắt buộc `TEST MODE`; chưa truy cập mailbox thật.

Thiết kế không nhận hoặc lưu password Microsoft 365 của người dùng. Hướng production ưu tiên Microsoft Purview eDiscovery/app-only/RBAC; OAuth tương tác là fallback. Outlook Classic automation không được chạy trong Windows Service.
