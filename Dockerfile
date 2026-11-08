# ===========================================================================
# Stage 1: Build Frontend UI (React + TypeScript + Vite)
# ===========================================================================
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend

COPY frontend/package*.json ./
RUN npm install

COPY frontend/ ./
RUN npm run build

# ===========================================================================
# Stage 2: Runtime with NVIDIA CUDA & PyTorch
# ===========================================================================
FROM nvidia/cuda:12.1.1-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    BACKEND_HOST=0.0.0.0 \
    BACKEND_PORT=8000

WORKDIR /app

# 1. Install system tools, Python 3.10 and audio dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.10 \
    python3.10-dev \
    python3-pip \
    ffmpeg \
    build-essential \
    curl \
    git \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.10 1 && \
    update-alternatives --install /usr/bin/python python /usr/bin/python3.10 1

# 2. Upgrade pip and pin pip < 24.1 for legacy fairseq/omegaconf compatibility
RUN python3 -m pip install --no-cache-dir "pip<24.1" setuptools wheel cython

# 3. Install PyTorch with CUDA 12.1
RUN python3 -m pip install --no-cache-dir \
    torch==2.5.1+cu121 \
    torchvision==0.20.1+cu121 \
    torchaudio==2.5.1+cu121 \
    --index-url https://download.pytorch.org/whl/cu121

# 4. Copy requirements and install dependencies
COPY requirements.txt .
RUN python3 -m pip install --no-cache-dir omegaconf==2.0.6 hydra-core==1.0.7 && \
    python3 -m pip install --no-cache-dir -r requirements.txt

# 5. Copy project source code
COPY . .

# 6. Copy freshly built static frontend from Stage 1 into frontend/dist
COPY --from=frontend-builder /app/frontend/dist /app/frontend/dist

# Expose FastAPI backend port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD curl -f http://localhost:8000/api/health || exit 1

# Launch FastAPI backend serving API, WebSocket and Frontend UI
CMD ["python3", "backend/main.py"]
