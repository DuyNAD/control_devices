# control_devices

Phần mềm giúp người dùng điều khiển laptop và điện thoại bằng một tay, không cần chạm vào thiết bị. Mỗi thiết bị dùng camera của chính nó để nhận diện bàn tay. Cách dùng trên laptop nằm trong [docs/huong-dan-laptop.md](docs/huong-dan-laptop.md), còn quy tắc cử chỉ nằm trong [docs/gesture-rules.md](docs/gesture-rules.md).

Hiện dự án có logic cử chỉ cho laptop và app Windows với đủ 9 thao tác laptop trên màn hình chính.

## Cài đặt

Cần Python 3.12.

```bash
py -3.12 -m venv .venv
```

```bash
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Chạy app Windows

App này điều khiển chuột thật. Xòe tay, giữ yên 1 giây để bật. Nhấn Ctrl+Alt+Q ở bất kỳ đâu để dừng. Lần chạy đầu sẽ hỏi trước khi tải model nhận diện tay.

```bash
.venv\Scripts\python.exe windows_app.py
```

## Đóng gói cho máy khác

Tạo `dist\control_devices_windows.zip`, gồm app và hướng dẫn sử dụng `HUONG_DAN_LAPTOP.txt` nằm cạnh file exe. Người nhận chỉ cần giải nén rồi chạy `control_devices.exe`, không cần cài Python.

```bash
.venv\Scripts\python.exe -m pip install -r requirements-build.txt
```

```bash
powershell -ExecutionPolicy Bypass -File packaging\build.ps1
```

## Kiểm tra logic

```bash
.venv\Scripts\python.exe -m pytest tests
```

## Các file

| File | Vai trò |
|---|---|
| `gesture_core.py` | Logic cử chỉ dùng chung, không phụ thuộc camera hay hệ điều hành |
| `hand_tracking.py` | Đọc bàn tay bằng MediaPipe |
| `preview.py` | Cửa sổ camera dùng chung, vẽ khung xương và trạng thái |
| `windows_app.py` | App Windows, điều khiển chuột thật, click bằng giữ yên |
| `tests/` | Kiểm tra logic bằng dữ liệu bàn tay giả lập |
