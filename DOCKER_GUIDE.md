# Hướng Dẫn Deploy RVC Bằng Docker / Docker Compose

Tài liệu này dùng để gửi cho bạn / DevOps / Cloud Engineer để deploy hệ thống RVC (FastAPI Backend + React Frontend + GPU CUDA) lên máy chủ hoặc VPS GPU.

---

## 🚀 Cách chạy nhanh nhất (1 Dòng Lệnh)

Tại thư mục gốc dự án, chạy lệnh:

```bash
docker compose up --build -d
```

Sau khi chạy xong, ứng dụng sẽ phục vụ tại:
👉 **`http://<IP-của-server>:8000`** (hoặc `http://localhost:8000`)

---

## 📋 Yêu cầu trên Server

1. **Docker & Docker Compose** (Docker v20+ / Compose v2+).
2. **NVIDIA GPU** & **NVIDIA Container Toolkit** (để Docker có thể sử dụng GPU CUDA):
   - Kiểm tra GPU bằng lệnh: `nvidia-smi`
   - Cài đặt NVIDIA Container Toolkit (nếu server Ubuntu chưa có):
     ```bash
     sudo apt-get update
     sudo apt-get install -y nvidia-container-toolkit
     sudo systemctl restart docker
     ```

---

## 🛠️ Cấu trúc Docker đã tối ưu:

1. **Multi-stage Build**:
   - **Stage 1 (Node 20)**: Tự động cài đặt thư viện và build mã nguồn React/Vite Frontend sang file tĩnh tối ưu.
   - **Stage 2 (NVIDIA CUDA 12.1 + Ubuntu 22.04 + Python 3.10)**: Cài đặt PyTorch CUDA, trích xuất đặc trưng âm thanh, nạp FastAPI và WebSocket.
2. **Volume Mount**:
   - `weights/`, `logs/`, `assets/` (~10 GB) được mount ngoài máy chủ vào container, giúp quá trình `docker build` **cực kỳ nhanh** (không bị nhồi 10GB vào image layer) và dễ dàng cập nhật thêm ca sĩ mới mà không cần build lại image.
3. **Cổng Port**:
   - Cổng **`8000:8000`** phục vụ toàn bộ:
     - Giao diện Web SPA: `http://<IP>:8000`
     - WebSocket truyền âm thanh mic trực tiếp: `ws://<IP>:8000/ws/voice-conversion`
     - API kiểm tra tình trạng: `http://<IP>:8000/api/health`

---

## 🔍 Một số lệnh quản lý hữu ích:

* **Xem log thời gian thực:**
  ```bash
  docker compose logs -f
  ```
* **Dừng ứng dụng:**
  ```bash
  docker compose down
  ```
* **Khởi động lại:**
  ```bash
  docker compose restart
  ```

