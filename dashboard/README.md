# InterLOG Mail Operations Dashboard

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
