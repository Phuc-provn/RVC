"""
FastAPI backend for Real-Time Singing Voice Conversion (RVC).

Run from the project root directory:
    cd E:\\LAB TW\\Help\\RVC_Project_20260421\\RVC_Project_20260421
    python backend/main.py
    # or: uvicorn backend.main:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import threading
import time
import traceback
from pathlib import Path

import numpy as np
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Project root setup – the backend MUST be run from the project root so that
# relative paths (weights/, logs/, etc.) resolve correctly.
# ---------------------------------------------------------------------------
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)
os.chdir(PROJECT_ROOT)
load_dotenv()

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger("rvc-backend")

# ---------------------------------------------------------------------------
# Import existing RVC code (this also initialises torch, Config, etc.)
# ---------------------------------------------------------------------------
RVC_IMPORT_ERROR: str | None = None
try:
    from simple_web_vc import (  # noqa: E402
        RealtimeSession,
        get_model_choices,
        get_speaker_choices,
        get_speaker_map,
        resolve_speaker_id,
        get_index_for_speaker,
        _to_float_mono,
        _to_int16,
        REALTIME_BLOCK_SECONDS,
        _shared_rvc_lock,
        _shared_rvc,
    )
    RVC_AVAILABLE = True
except Exception as exc:
    RVC_AVAILABLE = False
    RVC_IMPORT_ERROR = str(exc)
    REALTIME_BLOCK_SECONDS = 0.25
    RealtimeSession = None
    _shared_rvc_lock = threading.Lock()
    _shared_rvc = None
    logger.warning("Could not import simple_web_vc directly: %s. Reading model weights and metadata directly from files.", exc)

    def get_model_choices():
        weight_dir = Path(os.getenv("weight_root", "weights"))
        if not weight_dir.exists():
            return []
        return sorted(p.name for p in weight_dir.glob("*.pth"))

    def get_speaker_map(model_name):
        index_root = Path(os.getenv("index_root", "logs"))
        speakers_file = index_root / Path(model_name).stem / "speakers.json"
        if not speakers_file.exists():
            return {}
        try:
            with speakers_file.open(encoding="utf-8") as file:
                speaker_data = json.load(file)
            return {
                str(details.get("name", f"Speaker {speaker_id}")): int(speaker_id)
                for speaker_id, details in speaker_data.items()
                if str(speaker_id).isdigit() and isinstance(details, dict)
            }
        except Exception:
            return {}

    def get_speaker_choices(model_name):
        if not model_name:
            return []
        smap = get_speaker_map(model_name)
        return list(smap.keys())

    def resolve_speaker_id(speaker_name=None, model_name=None, index_path=None):
        if speaker_name is not None and model_name:
            return get_speaker_map(model_name).get(str(speaker_name), 0)
        return 0

from fastapi import FastAPI, WebSocket, WebSocketDisconnect  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402

# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------
app = FastAPI(
    title="RVC Singing Voice Conversion",
    description="Real-time singing voice conversion backend",
    version="1.0.0",
)

# CORS – allow all origins for development; restrict via CORS_ORIGINS env var.
_cors_origins = os.getenv("CORS_ORIGINS", "*")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if _cors_origins == "*" else [o.strip() for o in _cors_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Resolve the default model (the one with a speakers.json)
# ---------------------------------------------------------------------------
_model_choices = get_model_choices()
_default_model: str | None = next(
    (
        name
        for name in _model_choices
        if (Path(os.getenv("index_root", "logs")) / Path(name).stem / "speakers.json").exists()
    ),
    _model_choices[0] if _model_choices else None,
)

# ---------------------------------------------------------------------------
# Session management
#
# Only ONE inference session can run at a time (single GPU). We guard with an
# asyncio.Lock for the WebSocket coroutine and a threading.Lock for the
# blocking RealtimeSession itself.
# ---------------------------------------------------------------------------
_session_lock = asyncio.Lock()  # async gate: only one WS client at a time
_session_thread_lock = threading.Lock()  # guards blocking session operations

# Active session state (protected by _session_lock)
_active_session: RealtimeSession | None = None
_active_session_key: tuple[str, str] | None = None  # (model, speaker)
_active_client_id: str | None = None


def _get_or_create_session(model_name: str, speaker_name: str):
    """Return a RealtimeSession, reusing an existing one when model+speaker match."""
    global _active_session, _active_session_key

    if not RVC_AVAILABLE or RealtimeSession is None:
        raise RuntimeError(
            f"RVC inference environment is not fully loaded ({RVC_IMPORT_ERROR}). "
            "Please ensure the conda 'rvc' environment is activated: 'conda activate rvc'."
        )

    key = (model_name, speaker_name)
    with _session_thread_lock:
        if _active_session is not None and _active_session_key == key and _active_session.rvc is not None:
            _active_session.reset()
            return _active_session

        # Different model/speaker or no session – close the old one and create new.
        if _active_session is not None:
            try:
                _active_session.close()
            except Exception:
                traceback.print_exc()
            _active_session = None

        logger.info("Creating RealtimeSession: model=%s, speaker=%s", model_name, speaker_name)
        session = RealtimeSession(model_name, speaker_name, f0_method="rmvpe")
        _active_session = session
        _active_session_key = key
        return session


def _close_session() -> None:
    """Fully close (release GPU resources) the active session."""
    global _active_session, _active_session_key
    with _session_thread_lock:
        if _active_session is not None:
            try:
                _active_session.close()
            except Exception:
                traceback.print_exc()
            _active_session = None
            _active_session_key = None


def _reset_session() -> None:
    """Clear audio buffers but keep the model loaded."""
    with _session_thread_lock:
        if _active_session is not None:
            try:
                _active_session.reset()
            except Exception:
                traceback.print_exc()


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------
@app.get("/api/health")
async def health():
    import torch

    return {
        "status": "ok" if RVC_AVAILABLE else "degraded",
        "rvc_pipeline_ready": RVC_AVAILABLE,
        "rvc_import_error": RVC_IMPORT_ERROR,
        "device": str(torch.cuda.current_device()) if torch.cuda.is_available() else "cpu",
        "cuda_available": torch.cuda.is_available(),
        "gpu_name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        "models_available": len(_model_choices),
        "default_model": _default_model,
    }


@app.get("/api/voices")
async def voices():
    model = _default_model
    if not model:
        return {"default_model": None, "voices": []}

    speaker_map = get_speaker_map(model)
    voice_list = []
    if speaker_map:
        for name, sid in speaker_map.items():
            voice_list.append({
                "id": str(sid),
                "name": name,
                "speaker_name": name,
            })
    else:
        # Fallback: use get_speaker_choices which returns "Speaker 0", etc.
        for choice in get_speaker_choices(model):
            sid = resolve_speaker_id(speaker_name=choice, model_name=model)
            voice_list.append({
                "id": str(sid),
                "name": choice,
                "speaker_name": choice,
            })

    return {
        "default_model": model,
        "voices": voice_list,
    }


@app.get("/api/status")
async def status():
    return {
        "session_active": _active_session is not None and _active_session.rvc is not None,
        "active_client": _active_client_id,
        "active_model": _active_session_key[0] if _active_session_key else None,
        "active_speaker": _active_session_key[1] if _active_session_key else None,
        "models": _model_choices,
        "default_model": _default_model,
    }


# ---------------------------------------------------------------------------
# WebSocket endpoint: /ws/voice-conversion
# ---------------------------------------------------------------------------
@app.websocket("/ws/voice-conversion")
async def ws_voice_conversion(ws: WebSocket):
    await ws.accept()
    client_id = f"{ws.client.host}:{ws.client.port}" if ws.client else "unknown"
    logger.info("WebSocket connected: %s", client_id)

    global _active_client_id
    session: RealtimeSession | None = None
    owns_lock = False
    client_sample_rate: int = 48000
    loop = asyncio.get_running_loop()

    async def send_json_safe(data: dict) -> bool:
        """Send a JSON message; return False if the connection is gone."""
        try:
            await ws.send_json(data)
            return True
        except Exception:
            return False

    try:
        while True:
            message = await ws.receive()

            # --- Binary audio data ---
            if "bytes" in message and message["bytes"]:
                raw = message["bytes"]
                if session is None:
                    # Ignore early audio chunks before the session is ready
                    continue

                # Decode PCM int16 → numpy
                audio = np.frombuffer(raw, dtype=np.int16)
                if audio.size == 0:
                    continue

                try:
                    # process_chunk is a blocking GPU call; run in executor
                    out_sr, converted = await loop.run_in_executor(
                        None,
                        session.process_chunk,
                        (client_sample_rate, audio),
                    )
                    # Convert float32 [-1,1] → int16 bytes
                    out_bytes = (np.clip(converted, -1.0, 1.0) * 32767).astype(np.int16).tobytes()
                    await ws.send_bytes(out_bytes)
                except Exception as exc:
                    logger.error("process_chunk error: %s", exc)
                    traceback.print_exc()
                    await send_json_safe({"type": "error", "message": f"Conversion error: {exc}"})
                continue

            # --- Text (JSON) messages ---
            if "text" in message and message["text"]:
                try:
                    data = json.loads(message["text"])
                except json.JSONDecodeError:
                    await send_json_safe({"type": "error", "message": "Invalid JSON"})
                    continue

                msg_type = data.get("type", "")

                # ---- START ----
                if msg_type == "start":
                    voice_id = data.get("voice_id", "")
                    model = data.get("model", _default_model or "")
                    client_sample_rate = int(data.get("sample_rate", 48000))

                    if not model:
                        await send_json_safe({"type": "error", "message": "No model available."})
                        continue
                    if not voice_id:
                        await send_json_safe({"type": "error", "message": "No voice_id specified."})
                        continue

                    # Try to acquire the session lock (non-blocking check)
                    if _session_lock.locked() and not owns_lock:
                        await send_json_safe({
                            "type": "error",
                            "message": "Another client is currently using the GPU. Please wait and try again.",
                        })
                        continue

                    if not owns_lock:
                        try:
                            await asyncio.wait_for(_session_lock.acquire(), timeout=1.0)
                            owns_lock = True
                            _active_client_id = client_id
                        except asyncio.TimeoutError:
                            await send_json_safe({
                                "type": "error",
                                "message": "Could not acquire GPU lock. Another session is active.",
                            })
                            continue

                    # Create / reuse the session (blocking – run in executor)
                    try:
                        session = await loop.run_in_executor(
                            None,
                            _get_or_create_session,
                            model,
                            voice_id,
                        )
                        logger.info(
                            "Session ready: model=%s, speaker=%s, tgt_sr=%d, client_sr=%d",
                            model, voice_id, session.sample_rate, client_sample_rate,
                        )
                        await send_json_safe({
                            "type": "init",
                            "sample_rate": int(session.sample_rate),
                            "model": model,
                            "voice_id": voice_id,
                            "block_seconds": REALTIME_BLOCK_SECONDS,
                        })
                    except Exception as exc:
                        logger.error("Session creation failed: %s", exc)
                        traceback.print_exc()
                        await send_json_safe({"type": "error", "message": f"Failed to load voice model: {exc}"})
                        # Release lock on failure
                        if owns_lock:
                            _session_lock.release()
                            owns_lock = False
                            _active_client_id = None
                        session = None

                # ---- STOP ----
                elif msg_type == "stop":
                    logger.info("Client %s sent stop", client_id)
                    if session is not None:
                        await loop.run_in_executor(None, _reset_session)
                        session = None
                    await send_json_safe({"type": "stopped"})
                    # Release lock so another client can connect
                    if owns_lock:
                        _session_lock.release()
                        owns_lock = False
                        _active_client_id = None

                # ---- PING ----
                elif msg_type == "ping":
                    await send_json_safe({"type": "pong", "timestamp": time.time()})

                else:
                    await send_json_safe({"type": "error", "message": f"Unknown message type: {msg_type}"})

    except (WebSocketDisconnect, RuntimeError) as exc:
        if isinstance(exc, WebSocketDisconnect) or "disconnect" in str(exc).lower():
            logger.info("WebSocket disconnected: %s", client_id)
        else:
            logger.error("WebSocket error for %s: %s", client_id, exc)
            traceback.print_exc()
    except Exception as exc:
        logger.error("WebSocket error for %s: %s", client_id, exc)
        traceback.print_exc()
    finally:
        # Clean up on disconnect
        if session is not None:
            try:
                await loop.run_in_executor(None, _close_session)
            except Exception:
                traceback.print_exc()
            session = None
        if owns_lock:
            try:
                _session_lock.release()
            except RuntimeError:
                pass
            _active_client_id = None
        logger.info("WebSocket cleanup complete: %s", client_id)


# ---------------------------------------------------------------------------
# Static file serving (frontend build)
# ---------------------------------------------------------------------------
_frontend_dist = Path(PROJECT_ROOT) / "frontend" / "dist"
if _frontend_dist.is_dir():
    logger.info("Serving frontend from %s", _frontend_dist)

    @app.get("/")
    async def serve_frontend_index():
        index = _frontend_dist / "index.html"
        if index.exists():
            return FileResponse(str(index))
        return {"error": "Frontend index.html not found"}

    # Mount static assets AFTER the root route so /api and /ws still work.
    app.mount("/", StaticFiles(directory=str(_frontend_dist), html=True), name="frontend")
else:
    @app.get("/")
    async def root():
        return {
            "service": "RVC Voice Conversion Backend",
            "docs": "/docs",
            "health": "/api/health",
            "voices": "/api/voices",
            "websocket": "/ws/voice-conversion",
        }


# ---------------------------------------------------------------------------
# Startup / shutdown events
# ---------------------------------------------------------------------------
@app.on_event("startup")
async def on_startup():
    import torch

    logger.info("=" * 60)
    logger.info("RVC Voice Conversion Backend starting")
    logger.info("Project root: %s", PROJECT_ROOT)
    logger.info("Available models: %s", _model_choices)
    logger.info("Default model: %s", _default_model)
    if _default_model:
        speakers = get_speaker_choices(_default_model)
        logger.info("Speakers for %s: %s", _default_model, speakers)
    logger.info("CUDA available: %s", torch.cuda.is_available())
    if torch.cuda.is_available():
        logger.info("GPU: %s", torch.cuda.get_device_name(0))
        logger.info(
            "GPU memory: %.1f GB total",
            torch.cuda.get_device_properties(0).total_memory / 1e9,
        )
    logger.info("Block size: %.3f s", REALTIME_BLOCK_SECONDS)
    if _frontend_dist.is_dir():
        logger.info("Frontend: serving from %s", _frontend_dist)
    else:
        logger.info("Frontend: not found at %s (API-only mode)", _frontend_dist)
    logger.info("=" * 60)

    # Pre-warm default model in a background thread so first live conversion is instant
    if _default_model and RVC_AVAILABLE:
        speakers = get_speaker_choices(_default_model)
        if speakers:
            default_spk = speakers[0]
            def _prewarm_bg():
                try:
                    logger.info("Pre-warming model '%s' (%s) in background...", _default_model, default_spk)
                    _get_or_create_session(_default_model, default_spk)
                    logger.info("Pre-warm complete! Real-time conversion is ready.")
                except Exception as exc:
                    logger.warning("Pre-warm note: %s", exc)
            threading.Thread(target=_prewarm_bg, daemon=True).start()


@app.on_event("shutdown")
async def on_shutdown():
    logger.info("Shutting down – closing active session if any")
    _close_session()
    logger.info("Shutdown complete")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("BACKEND_PORT", "8000"))
    host = os.getenv("BACKEND_HOST", "0.0.0.0")
    logger.info("Starting uvicorn on %s:%d", host, port)
    uvicorn.run(
        "backend.main:app",
        host=host,
        port=port,
        reload=False,
        log_level="info",
        ws_ping_interval=30,
        ws_ping_timeout=60,
    )
