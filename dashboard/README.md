# InterLOG Mail Operations Dashboard

Phiên bản dashboard `0.2.0` dành cho IT quản lý toàn bộ vòng đời một yêu cầu backup PST: tiếp nhận yêu cầu, chọn đúng phạm vi, lên lịch export trên VM, xác nhận PST, theo dõi chuyển file và lưu lịch sử trong SQLite.

## Quy trình hiện tại

1. IT tạo job, nhập mailbox test, chọn `Mailbox chính`, `Online Archive` hoặc `Thư mục cụ thể`.
2. Với `Outlook Classic`, đến lịch dashboard chuyển job sang `Chờ IT export`.
3. IT export đúng phạm vi trên VM, đóng Outlook, mở chi tiết job và bấm `PST đã export xong`.
4. Công cụ PST Transfer chạy BITS ở máy đích; API `/api/jobs/{id}/receipt` nhận receipt để hiển thị byte, lỗi SMB, resume và `COMPLETE`.
5. Toàn bộ thao tác được lưu trong `dashboard/data/dashboard.db`.

Dashboard có tìm kiếm theo email/ticket, lọc trạng thái, chi tiết job, timeline, retry, hủy job và trạng thái heartbeat của VM worker.

Để đẩy receipt của PST Transfer lên một job dashboard (chạy một lần), dùng:

```powershell
.\dashboard\worker\publish-bits-receipt.ps1 -JobId 12 -ReceiptPath "D:\MAIL BACKUP\user.pst.bits-receipt.json"
```

Thêm `-Watch` nếu muốn theo dõi file receipt mỗi 10 giây trong lúc BITS đang chạy. Script chỉ đọc receipt và gửi trạng thái; không đọc nội dung PST.

> Mặc định luôn là `TEST MODE`. Purview connector bị khóa cứng, không truy cập mailbox thật và không nhận/lưu mật khẩu Microsoft 365.

MVP quản trị yêu cầu export và chuyển PST. Mặc định luôn chạy `TEST MODE`; worker chỉ mô phỏng trạng thái và không truy cập mailbox thật.

## Chạy development

```powershell
cd dashboard\backend
python -m venv .venv
.\.venv\Scripts\pip.exe install -r requirements.txt

cd ..\frontend
npm install
npm run build

cd ..\backend
.\.venv\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8080
```

Mở `http://127.0.0.1:8080`.

Trên Windows có thể bấm `START-DASHBOARD.cmd`. Lần đầu script sẽ tạo môi trường Python, cài dependency, build React rồi mở dashboard. Cửa sổ PowerShell đang chạy chính là backend; đóng cửa sổ để dừng dashboard.

## Nguyên tắc xác thực

- Không nhận và không lưu password Microsoft 365 của user.
- Production ưu tiên app-only bằng certificate, Microsoft Graph/Purview và Exchange RBAC.
- Nếu bắt buộc tương tác, dùng OAuth trong trình duyệt và cache token được bảo vệ bằng Windows DPAPI.
- Outlook Classic chỉ là fallback có người đăng nhập; không chạy Outlook COM trong Windows Service.

## Trạng thái hiện tại

- Có dashboard React, API FastAPI và lịch sử SQLite.
- Có tạo job theo mailbox, phạm vi, lịch chạy, engine và thư mục đích.
- Có worker mô phỏng tiến trình trong TEST MODE.
- Chưa cấp quyền Purview và chưa thực thi export thật.
- Chưa điều khiển BITS trên máy user từ dashboard.
