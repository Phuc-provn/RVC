# Real-Time Singing Voice Conversion (RVC) Web Application

A modern, standalone real-time Singing Voice Conversion web application featuring a dedicated **FastAPI backend** with WebSocket streaming and a responsive **React + TypeScript + Vite frontend**.

The application wraps the existing AI voice conversion pipeline (RVC with HuBERT feature extraction, RMVPE pitch estimation, and trained multi-singer neural synthesizer) without modifying or breaking the original model weights or inference logic.

---

## 1. Project Overview

- **Frontend**: Clean, modern AI dashboard built with React 19, TypeScript, and Tailwind CSS. Provides live audio capture via Web Audio API, real-time volume level indicators, target singer voice selection, and continuous gapless playback of converted audio.
- **Backend**: FastAPI with asynchronous WebSocket binary transport. Features single-session GPU locking, thread-pool execution for CPU/GPU-bound neural inference, and graceful resource lifecycle management.
- **AI Core**: Retrieval-based Voice Conversion (RVC) using HuBERT features, RMVPE pitch tracking, FAISS index similarity matching, and multi-speaker Synthesizer checkpoints (`6Singer_800epoch.pth`).

---

## 2. System Architecture

```
Browser Microphone (Web Audio API)
       │ (PCM int16, 48 kHz chunks)
       ▼
Frontend Audio Streaming Hook
       │ (WebSocket binary stream)
       ▼
FastAPI Backend (/ws/voice-conversion)
       │ (Thread-pool executor)
       ▼
Existing RVC Pipeline (RealtimeSession)
   ├── 1. HuBERT Feature Extraction (assets/hubert/hubert_base.pt)
   ├── 2. RMVPE Pitch Estimation (assets/rmvpe/rmvpe.pt)
   ├── 3. FAISS Feature Retrieval (logs/6Singer_800epoch/*.index)
   └── 4. Synthesizer Generator (weights/6Singer_800epoch.pth)
       │ (SOLA crossfade & PCM int16 conversion)
       ▼
FastAPI Backend (/ws/voice-conversion)
       │ (WebSocket binary stream)
       ▼
Frontend Audio Playback (AudioBufferSourceNode scheduling)
       │
       ▼
User Hears Converted Singer Voice in Real Time
```

---

## 3. Prerequisites & Environment

| Component | Requirement |
|---|---|
| **OS** | Windows 10/11 64-bit or Linux |
| **GPU** | NVIDIA GPU with CUDA support (e.g. RTX 3050/3060 or higher with >= 4GB VRAM) |
| **Python** | Python 3.10 (64-bit) |
| **Node.js** | Node.js 18.x or 20.x+ and npm |
| **CUDA / PyTorch** | PyTorch 2.5.1 with CUDA 12.1 (`torch==2.5.1+cu121`) |

---

## 4. Required Model Weights & Assets

Ensure the following assets exist in the project root:

```
├── assets/
│   ├── hubert/
│   │   └── hubert_base.pt          # HuBERT base model
│   └── rmvpe/
│       └── rmvpe.pt                # RMVPE pitch estimation model
├── weights/
│   ├── 6Singer.pth                 # Trained checkpoint
│   └── 6Singer_800epoch.pth        # Default 6-singer checkpoint
└── logs/
    └── 6Singer_800epoch/
        ├── speakers.json           # Speaker ID to name and pitch mapping
        └── added_IVF*.index        # FAISS indexes for each speaker (0 to 5)
```

Available Singers:
1. **陳嘉樺 (ELLA)** (Speaker ID 0)
2. **林俊傑** (Speaker ID 1)
3. **劉德華** (Speaker ID 2)
4. **周杰倫** (Speaker ID 3)
5. **王心凌** (Speaker ID 4)
6. **黃小琥** (Speaker ID 5)

---

## 5. Backend Installation & Setup

### Using Conda (Recommended):

```powershell
# 1. Create and activate the conda environment
conda env create -f environment.yml
conda activate rvc

# 2. Verify GPU detection
python -c "import torch; print('PyTorch:', torch.__version__, '| CUDA Available:', torch.cuda.is_available())"

# 3. Ensure backend extra dependencies are installed
pip install -r backend/requirements.txt
```

### Direct Python 3.10 / venv:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
pip install -r backend/requirements.txt
```

---

## 6. Frontend Installation & Setup

```powershell
cd frontend
npm install
npm run build
cd ..
```

*Note*: Building the frontend generates production files in `frontend/dist`. The FastAPI backend automatically serves these static files from `/` in production mode.

---

## 7. Environment Variables (.env)

Copy `.env.example` to `.env`:

```ini
# Backend host and port
BACKEND_HOST=0.0.0.0
BACKEND_PORT=8000

# RVC Model asset folders
weight_root=weights
index_root=logs

# Device
DEVICE=cuda:0

# Security / CORS
CORS_ORIGINS=*

# Frontend development port
FRONTEND_PORT=5173
```

---

## 8. How to Run Locally

### Option A: Unified Full-Stack Service (Recommended)

Once the frontend is built (`frontend/dist`), simply run the FastAPI backend:

```powershell
conda activate rvc
python backend/main.py
```

Then open your browser at **http://localhost:8000**.
The React frontend, REST API, and WebSocket streaming are all served from the single port!

### Option B: Separate Frontend Development Server

If modifying frontend code with hot module reloading (HMR):

**Terminal 1 (Backend):**
```powershell
conda activate rvc
python backend/main.py
```

**Terminal 2 (Frontend Dev Server):**
```powershell
cd frontend
npm run dev
```

Open **http://localhost:5173** (Vite proxies `/api` and `/ws` to `localhost:8000`).

---

## 9. How to Run the Original Gradio Application

The legacy Gradio application remains fully intact and can be run at any time:

```powershell
conda activate rvc
python simple_web_vc.py
```

Access the Gradio demo at **http://localhost:7865**.

---

## 10. How to Test Real-Time Microphone Streaming

1. Plug in **headphones** (essential to avoid audio feedback into your microphone).
2. Open the web interface at `http://localhost:8000` (or your public URL).
3. Under **Voice Settings**, select your desired singer (e.g., `周杰倫` or `陳嘉樺(ELLA)`).
4. Click **Start Conversion**.
5. Grant browser microphone permission when prompted.
6. The status will update to **"Live conversion active"**.
7. Sing or speak into the microphone. You should observe:
   - Green input volume meter reacting to your voice.
   - Violet output volume meter indicating converted voice generation.
   - Real-time converted singing voice playing in your headphones.
8. Click **Stop** to conclude the session.

---

## 11. Deployment & Public Partner URL (HTTPS / WSS)

Modern browsers strictly require **HTTPS** (or `localhost`) to access the microphone API (`navigator.mediaDevices.getUserMedia`). Secure WebSockets (`wss://`) are also required over HTTPS.

### Deploying via Cloudflare Tunnel (Quickest & Free):

A standalone `cloudflared.exe` is included in the project directory.

1. Start the FastAPI backend:
   ```powershell
   python backend/main.py
   ```

2. In a second terminal, launch the secure tunnel:
   ```powershell
   .\cloudflared.exe tunnel --url http://localhost:8000
   ```

3. `cloudflared` will generate a public URL like:
   ```
   https://<random-id>.trycloudflare.com
   ```

4. Share this URL with your project partner. It automatically terminates HTTPS and WSS, allowing remote microphone access and real-time streaming without port-forwarding or SSL configuration.

---

## 12. Troubleshooting & FAQ

- **Microphone permission denied / not working on remote devices**:
  Browsers block microphone access over insecure `http://<ip>:8000`. You must use `localhost` or an HTTPS URL (such as Cloudflare Tunnel).
- **"Another client is currently using the GPU"**:
  RVC real-time inference uses a single session lock to prevent GPU memory collisions. Click Stop on any other active tab before starting a new session.
- **Latency or audio gaps**:
  Use headphones. In the console or status box, observe if lag warnings appear. Lowering background GPU utilization helps inference keep up with live audio.

---

## 13. Known Technical Limitations

1. **GPU Concurrency**: The current RVC inference pipeline utilizes ~1-2GB of VRAM and holds internal recurrent streaming buffers. Concurrent sessions from different clients are locked to 1 active session at a time to protect GPU stability.
2. **Buffer Latency**: Algorithmic latency is approximately 0.25s block size + RMVPE / Synthesizer inference time (~0.3-0.5s total roundtrip latency).
