"""
End-to-End Voice Conversion Testing Script.

This script tests the inference pipeline by:
1. Connecting to the FastAPI WebSocket endpoint.
2. Sending a 'start' request for a target singer.
3. Reading an audio file (e.g. from Sampels/), streaming it in real-time chunks (0.25s).
4. Receiving converted audio chunks from the server.
5. Saving the converted audio to a file for listening verification.
"""

import asyncio
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf
import websockets

BACKEND_WS_URL = os.getenv("BACKEND_WS_URL", "ws://127.0.0.1:8000/ws/voice-conversion")
SAMPLE_FILE = Path(__file__).parent / "Sampels" / "Alto-1_1.wav"
OUTPUT_FILE = Path(__file__).parent / "tmp" / "test_converted_output.wav"


async def run_test():
    print("=" * 60)
    print(" Singing Voice Conversion - Automated E2E Test")
    print("=" * 60)

    if not SAMPLE_FILE.exists():
        print(f"Error: Sample audio file not found at {SAMPLE_FILE}")
        return

    # 1. Read input sample audio
    data, sr = sf.read(str(SAMPLE_FILE), dtype="float32")
    if data.ndim > 1:
        data = data.mean(axis=1)  # Mono
    int16_data = (np.clip(data, -1.0, 1.0) * 32767).astype(np.int16)
    duration = len(int16_data) / sr
    print(f"[1/5] Loaded sample audio: {SAMPLE_FILE.name} ({duration:.2f} s, {sr} Hz)")

    # 2. Connect to WebSocket
    print(f"[2/5] Connecting to WebSocket: {BACKEND_WS_URL}")
    try:
        async with websockets.connect(BACKEND_WS_URL) as ws:
            print("[3/5] Connected. Sending START command for '陳嘉樺(ELLA)'...")
            await ws.send(
                json.dumps(
                    {
                        "type": "start",
                        "voice_id": "陳嘉樺(ELLA)",
                        "model": "6Singer_800epoch.pth",
                        "sample_rate": sr,
                    }
                )
            )

            # Wait for init response
            init_resp_text = await ws.recv()
            init_data = json.loads(init_resp_text)
            print(f"      Server response: {init_data}")

            if init_data.get("type") == "error":
                print(f"      [!] Server returned error: {init_data.get('message')}")
                return

            tgt_sr = init_data.get("sample_rate", 40000)
            print(f"      Inference target sample rate: {tgt_sr} Hz")

            # 3. Stream chunks of 0.25 seconds
            chunk_size = int(sr * 0.25)
            total_chunks = (len(int16_data) + chunk_size - 1) // chunk_size
            received_audio = []

            print(f"[4/5] Streaming {total_chunks} audio chunks in real-time...")

            async def receive_loop():
                while True:
                    try:
                        msg = await ws.recv()
                        if isinstance(msg, bytes):
                            chunk_arr = np.frombuffer(msg, dtype=np.int16)
                            received_audio.append(chunk_arr)
                        elif isinstance(msg, str):
                            data = json.loads(msg)
                            if data.get("type") == "stopped":
                                break
                    except Exception:
                        break

            recv_task = asyncio.create_task(receive_loop())

            for i in range(0, len(int16_data), chunk_size):
                chunk = int16_data[i : i + chunk_size]
                if len(chunk) < chunk_size:
                    chunk = np.pad(chunk, (0, chunk_size - len(chunk)))
                await ws.send(chunk.tobytes())
                await asyncio.sleep(0.20)  # Simulate real-time streaming pace

            # 4. Stop conversion
            print("[5/5] Finished sending audio. Sending STOP command...")
            await ws.send(json.dumps({"type": "stop"}))
            await asyncio.wait_for(recv_task, timeout=5.0)

            # Save converted audio
            if received_audio:
                OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
                full_audio = np.concatenate(received_audio).astype(np.float32) / 32768.0
                sf.write(str(OUTPUT_FILE), full_audio, tgt_sr)
                print(f"[✓] Converted audio successfully saved to: {OUTPUT_FILE}")
                print(f"    Total duration: {len(full_audio)/tgt_sr:.2f} s")
            else:
                print("[!] No converted audio chunks received.")

    except Exception as e:
        print(f"[!] Connection or testing failed: {e}")


if __name__ == "__main__":
    asyncio.run(run_test())

