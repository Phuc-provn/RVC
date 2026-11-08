# RVC System Evolution & Modification Log
# Nhật Ký Thay Đổi & Nâng Cấp Hệ Thống RVC

This document provides a detailed breakdown of all architecture changes, additions, modifications, and optimizations made to transform the legacy Gradio-based demo into a production-grade, standalone Fullstack (FastAPI + React/TypeScript) Real-Time Singing Voice Conversion system.

Tài liệu này ghi lại chi tiết toàn bộ các thay đổi kiến trúc, thêm mới, sửa đổi và tối ưu hóa để chuyển đổi bản demo Gradio cũ thành hệ thống Web thời gian thực độc lập chuẩn Fullstack (FastAPI + React/TypeScript) hoàn chỉnh.

---

## 🇻🇳 BẢN TIẾNG VIỆT (VIETNAMESE)

### 1. Tổng quan Kiến trúc: Trước và Sau khi Nâng cấp

| Đặc điểm | Hệ thống gốc (Original System) | Hệ thống hiện tại (Current Fullstack System) |
| :--- | :--- | :--- |
| **Giao diện (Frontend)** | Gradio Web UI nguyên khối (Monolith) chạy trực tiếp trong tiến trình Python. | Ứng dụng **React 19 + TypeScript + Vite + Tailwind CSS** độc lập, tốc độ phản hồi cao, có thể deploy riêng trên Vercel hoặc đóng gói tĩnh. |
| **Backend & API** | Không có REST API riêng, không có WebSocket endpoint độc lập; phụ thuộc hoàn toàn vào cơ chế streaming nội bộ của Gradio. | **FastAPI** hiệu năng cao, cung cấp đầy đủ chuẩn REST APIs (`/api/health`, `/api/voices`, `/api/status`) và **WebSocket endpoint nhị phân** chuyên biệt cho âm thanh. |
| **Xử lý âm thanh trình duyệt** | Dùng component `gr.Audio(streaming=True)` mặc định của trình duyệt, dễ bị trễ (latency cao) và không kiểm soát được luồng đệm (buffering). | Sử dụng trực tiếp **Web Audio API (`AudioContext`, `ScriptProcessorNode`, `AudioBufferSourceNode`)**, kiểm soát bộ đệm chống rè/giật, chuyển đổi PCM 16-bit trực tiếp ở client. |
| **Chống dội âm (Feedback Loop)** | Trình duyệt thường bị phát ngược tiếng nói vào loa/tai nghe khi mở mic. | Tích hợp nút `GainNode` ngắt âm (muted gain node) trên luồng thu âm, chỉ phát âm thanh AI sau khi đã biến đổi. |
| **Quản lý GPU & Đa nhiệm** | Xung đột nếu nhiều người mở web cùng lúc hoặc tiến trình GPU chặn (block) toàn bộ server. | Kết hợp `asyncio.Lock` và `threading.Lock` cùng cơ chế đẩy suy luận sang thread pool (`run_in_executor`), đảm bảo server không bao giờ bị đơ (hang). |
| **Môi trường & Bộ nhớ đĩa** | Cài đặt mặc định dễ gây tràn ổ đĩa C (đặc biệt khi dung lượng ổ C chỉ còn vài GB). | Toàn bộ môi trường Conda và các package được cấu hình nằm trọn vẹn tại **ổ E (`E:\LAB TW\Help\conda_envs\rvc`)**. |

---

### 2. Bảng Chi Tiết Thêm / Bớt / Sửa Đổi Các Thành Phần

| Thành phần / Tệp tin | Trạng thái | Chi tiết thay đổi & Mục đích |
| :--- | :---: | :--- |
| **`simple_web_vc.py`** | **GIỮ NGUYÊN (Preserved)** | **Không sửa đổi mã nguồn gốc**. Giữ nguyên pipeline suy luận cốt lõi (`RealtimeSession`, `RVC`, HuBERT, RMVPE) làm thư viện nền để backend gọi vào, bảo toàn độ chính xác của mô hình. |
| **`backend/main.py`** | **THÊM MỚI (Added)** | Xây dựng server FastAPI: quản lý phiên làm việc GPU, xử lý giao thức WebSocket (`/ws/voice-conversion`), lọc bỏ các audio chunk gửi sớm trước khi nạp model (chống race condition), phân phối static files của React. |
| **`frontend/`** | **THÊM MỚI (Added)** | Toàn bộ dự án Single Page Application (SPA):<br>• `src/hooks/useAudioStream.ts`: Quản lý thu âm mic, vẽ thanh đo âm lượng (VU meters), phát âm thanh mượt không khoảng lặng.<br>• `src/hooks/useWebSocket.ts`: Giao tiếp socket nhị phân, tự động nhận diện URL tunnel/Vercel/Localhost.<br>• `src/components/*`: Tách biệt các component giao diện trực quan, sang trọng. |
| **`environment.yml`** | **SỬA ĐỔI (Modified)** | Cập nhật cấu hình xung đột giữa `hydra-core` và `omegaconf`, hạ phiên bản pip nội bộ (`pip<24.1`) để tránh lỗi metadata, gán các thư viện audio tương thích với PyTorch CUDA 12.1. |
| **`fairseq` (Package)** | **SỬA ĐỔI (Fixed/Added)** | Khắc phục lỗi thiếu trình biên dịch C++ trên Windows bằng cách cài đặt bản phân phối tiền biên dịch (prebuilt wheel) `fairseq-0.12.2-cp310-cp310-win_amd64.whl`, bổ sung `av` (PyAV) và `tensorboardX`. |
| **`start_app.bat` & `start_app.ps1`** | **THÊM MỚI (Added)** | Script khởi động tiện lợi bằng 1 cú nhấp chuột: tự động trỏ đến đường dẫn Python trong Conda ổ E, kiểm tra build frontend và hỗ trợ cờ bật tunnel Cloudflare chia sẻ mạng ra ngoài. |
| **`test_voice_conversion.py`** | **THÊM MỚI (Added)** | Script tự động hóa kiểm thử End-to-End: giả lập client gửi 54 audio chunks từ file `Alto-1_1.wav` qua WebSocket và lưu file kết quả đã biến đổi để nghiệm thu chất lượng âm thanh. |

---

## 🇬🇧 BẢN TIẾNG ANH (ENGLISH)

### 1. Architectural Overview: Before vs. After Modernization

| Aspect | Legacy System (Original) | Modernized System (Current) |
| :--- | :--- | :--- |
| **Frontend UI** | Monolithic Gradio Web UI tightly coupled and rendered inside the Python process. | High-performance, decoupled **React 19 + TypeScript + Vite + Tailwind CSS** application, deployable to Vercel or served statically by FastAPI. |
| **Backend & API** | No discrete REST API; relies exclusively on Gradio's internal engine without independent WebSocket abstraction. | Enterprise-grade **FastAPI** service providing REST APIs (`/api/health`, `/api/voices`, `/api/status`) and a dedicated **binary WebSocket** streaming endpoint. |
| **Audio Processing** | Default browser `gr.Audio(streaming=True)` components with high latency and lack of client-side buffer scheduling. | Native **Web Audio API (`AudioContext`, `ScriptProcessorNode`, `AudioBufferSourceNode`)** enabling sub-second latency, PCM int16 streaming, and continuous playback. |
| **Feedback Loop / Echo** | Microphones frequently looped un-converted input audio straight to speakers/headphones. | Integrated a muted intermediate `GainNode` on the recording pipeline, guaranteeing that only the AI-transformed audio reaches playback. |
| **GPU Concurrency & Stability**| Concurrent requests could block the Python GIL or cause GPU out-of-memory crashes. | Dual-lock concurrency design (`asyncio.Lock` + `threading.Lock`) offloading GPU compute via `run_in_executor`, ensuring non-blocking event loops. |
| **Environment & Disk Storage** | Standard environment installation prone to filling system Drive C to capacity. | Isolated Conda environment and package cache relocated entirely to **Drive E (`E:\LAB TW\Help\conda_envs\rvc`)**. |

---

### 2. Component Modification, Addition & Removal Breakdown

| Component / File | Status | Technical Details & Purpose |
| :--- | :---: | :--- |
| **`simple_web_vc.py`** | **PRESERVED** | **Left completely untouched**. Retained the original core inference logic (`RealtimeSession`, `RVC`, HuBERT, RMVPE) as an underlying module, maintaining full fidelity with the original model behavior. |
| **`backend/main.py`** | **ADDED** | Implemented FastAPI server handling GPU session lifecycle, binary WebSocket audio protocol (`/ws/voice-conversion`), race-condition suppression for premature chunks, and static asset distribution. |
| **`frontend/`** | **ADDED** | Modern SPA client containing:<br>• `src/hooks/useAudioStream.ts`: Microphone sampling, live VU metering, and gapless buffer scheduling.<br>• `src/hooks/useWebSocket.ts`: High-speed binary WebSocket communication supporting remote backend URLs.<br>• `src/components/*`: Decoupled UI components (`VoiceSelector`, `MicrophoneInput`, `AudioOutput`, `StatusDisplay`). |
| **`environment.yml`** | **MODIFIED** | Corrected dependency conflicts between `hydra-core` and `omegaconf`, pinned `pip<24.1` for legacy package compatibility, and aligned audio libraries with PyTorch CUDA 12.1. |
| **`fairseq` (Package)** | **FIXED / ADDED** | Resolved Windows C++ Build Tools compilation failures by deploying a precompiled binary wheel (`fairseq-0.12.2-cp310-cp310-win_amd64.whl`), alongside `av` (PyAV) and `tensorboardX`. |
| **`start_app.bat` & `start_app.ps1`** | **ADDED** | One-click production launchers explicitly targeting the Drive E Conda Python executable, automating frontend builds and optional Cloudflare Tunnel sharing. |
| **`test_voice_conversion.py`** | **ADDED** | Automated End-to-End testing script that simulates live audio streaming using `Alto-1_1.wav`, validates WebSocket chunk responses, and exports converted audio for audio quality verification. |

---
*Created for RVC Project Deployment & Documentation.*

