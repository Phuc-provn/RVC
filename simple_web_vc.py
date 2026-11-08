import os
import json
import math
import re
import sys
import threading
import time
import traceback
import queue
from queue import Queue
from pathlib import Path

import numpy as np
from dotenv import load_dotenv

now_dir = os.getcwd()
sys.path.append(now_dir)
load_dotenv()

os.environ.setdefault("weight_root", "weights")
os.environ.setdefault("index_root", "logs")

import gradio as gr


def _patch_gradio_hls_target_duration():
    """Work around a Gradio bug that makes streamed audio freeze for longer and longer.

    Gradio's MediaStream.add_segment does `max_duration = max(max_duration, d) + 1`
    for every segment, so the HLS #EXT-X-TARGETDURATION grows by 1 s per chunk.
    hls.js waits roughly that long before polling for new audio, causing stalls.
    Here the target duration is kept at the real (rounded-up) segment length.
    """
    try:
        import uuid
        from gradio import route_utils

        media_stream = getattr(route_utils, "MediaStream", None)
        if media_stream is None or getattr(media_stream, "_svc_patched", False):
            return

        async def add_segment(self, data):
            if not data:
                return
            self.segments.append({"id": str(uuid.uuid4()), **data})
            longest = max(getattr(self, "_svc_longest_segment", 0.0), float(data["duration"]))
            self._svc_longest_segment = longest
            self.max_duration = max(1, math.ceil(longest))

        media_stream.add_segment = add_segment
        media_stream._svc_patched = True
    except Exception:
        traceback.print_exc()


_patch_gradio_hls_target_duration()


def _patch_gradio_unique_stream_runs():
    """Work around a Gradio bug that makes the second Record play nothing.

    Gradio names each streamed output by `id(iterator)` (blocks.py, the only
    `id()` call there). When one take ends its iterator is freed, and the next
    take's iterator often gets the same memory address, so it reuses the old,
    finished stream URL: the browser keeps the stale player and new audio is
    appended to a stream that already ended. Here each iterator gets a unique,
    never-reused number instead.
    """
    try:
        import builtins
        import itertools
        from gradio import blocks as gradio_blocks

        if getattr(gradio_blocks, "_svc_unique_runs", False):
            return
        counter = itertools.count(1)

        def unique_run_id(obj):
            try:
                run_id = obj.__dict__.get("_svc_run_id")
                if run_id is None:
                    run_id = obj._svc_run_id = next(counter)
                return run_id
            except Exception:
                return builtins.id(obj)

        gradio_blocks.id = unique_run_id
        gradio_blocks._svc_unique_runs = True
    except Exception:
        traceback.print_exc()


_patch_gradio_unique_stream_runs()

import torch
import torch.nn.functional as F
import torchaudio.transforms as tat

from configs.config import Config
from infer.lib import rtrvc as rvc_for_realtime
from infer.modules.vc.modules import VC

# Keep old torch.load behavior compatible with older checkpoints.
try:
    import fairseq

    try:
        torch.serialization.add_safe_globals([fairseq.data.dictionary.Dictionary])
    except AttributeError:
        pass
except Exception:
    pass

_original_load = torch.load


def _force_unsafe_load(*args, **kwargs):
    if "weights_only" not in kwargs:
        kwargs["weights_only"] = False
    return _original_load(*args, **kwargs)


torch.load = _force_unsafe_load


def get_speaker_map(model_name):
    index_root = Path(os.getenv("index_root", "logs"))
    speakers_file = index_root / Path(model_name).stem / "speakers.json"
    if not speakers_file.exists():
        return {}

    try:
        with speakers_file.open(encoding="utf-8") as file:
            speaker_data = json.load(file)
    except (OSError, json.JSONDecodeError):
        return {}

    return {
        str(details.get("name", f"Speaker {speaker_id}")): int(speaker_id)
        for speaker_id, details in speaker_data.items()
        if str(speaker_id).isdigit() and isinstance(details, dict)
    }


def get_speaker_choices(model_name):
    if not model_name:
        return []
    speaker_map = get_speaker_map(model_name)
    if speaker_map:
        return list(speaker_map)

    index_root = Path(os.getenv("index_root", "logs")) / Path(model_name).stem
    speaker_ids = set()
    if index_root.exists():
        for index_path in index_root.rglob("*.index"):
            match = re.search(r"speaker[_-]?([0-9]+)", index_path.stem, flags=re.I)
            if match:
                speaker_ids.add(int(match.group(1)))
    return [f"Speaker {speaker_id}" for speaker_id in sorted(speaker_ids)]


def resolve_speaker_id(speaker_name=None, model_name=None, index_path=None):
    if speaker_name is not None:
        speaker_text = str(speaker_name).strip()
        if speaker_text.isdigit():
            return int(speaker_text)
        speaker_id = get_speaker_map(model_name).get(speaker_text) if model_name else None
        if speaker_id is not None:
            return speaker_id
        match = re.search(r"Speaker\s+([0-9]+)", speaker_text, flags=re.I)
        if match:
            return int(match.group(1))

    if index_path:
        match = re.search(r"speaker[_-]?([0-9]+)", str(index_path), flags=re.I)
        if match:
            return int(match.group(1))
    return 0


def get_model_choices():
    weight_dir = Path(os.getenv("weight_root", "weights"))
    if not weight_dir.exists():
        return []
    names = sorted(p.name for p in weight_dir.glob("*.pth"))
    return names if names else []


def get_index_choices():
    index_dir = Path(os.getenv("index_root", "logs"))
    if not index_dir.exists():
        return []
    paths = sorted(str(p) for p in index_dir.rglob("*.index"))
    return paths


def get_index_for_speaker(model_name, speaker_name):
    speaker_id = resolve_speaker_id(speaker_name=speaker_name, model_name=model_name)
    index_root = Path(os.getenv("index_root", "logs"))
    model_index_dir = index_root / Path(model_name).stem
    if not model_index_dir.exists():
        return ""

    for index_path in sorted(model_index_dir.rglob("*.index")):
        match = re.search(r"speaker[_-]?([0-9]+)", index_path.stem, flags=re.I)
        if match and int(match.group(1)) == speaker_id:
            return str(index_path)
    return ""


def _normalize_file_path(value):
    if value is None:
        return None
    if isinstance(value, dict):
        if "path" in value and value["path"]:
            return value["path"]
        if "name" in value and value["name"]:
            return value["name"]
        return None
    if isinstance(value, (list, tuple)) and value:
        return _normalize_file_path(value[0])
    return str(value)


_file_vc_lock = threading.Lock()
_file_vc_cache = {"model": None, "vc": None}


def _get_file_vc(model_name):
    """Load the file-conversion model once and reuse it until a different model is chosen."""
    if _file_vc_cache["model"] != model_name or _file_vc_cache["vc"] is None:
        vc = VC(Config())
        vc.get_vc(model_name, 0.33, 0.33)
        _file_vc_cache.update(model=model_name, vc=vc)
    return _file_vc_cache["vc"]


def convert_file(file_obj, speaker_name, model_name):
    if not file_obj:
        return "Please upload an audio file or record audio before converting.", None

    audio_path = _normalize_file_path(file_obj)
    if not audio_path or not os.path.exists(audio_path):
        return "The selected audio could not be found. Please upload or record it again.", None

    model_name = model_name or (get_model_choices()[0] if get_model_choices() else "")
    if not model_name:
        return "No voice model was found. Add a .pth model to the weights folder.", None

    speaker_id = resolve_speaker_id(speaker_name=speaker_name, model_name=model_name)
    index_path = get_index_for_speaker(model_name, speaker_name)

    try:
        with _file_vc_lock:
            vc = _get_file_vc(model_name)
            info, out_audio = vc.vc_single(
                sid=speaker_id,
                input_audio_path=audio_path,
                f0_up_key=0,
                f0_file=None,
                f0_method="rmvpe",
                file_index=index_path or "",
                file_index2="",
                index_rate=0.75,
                filter_radius=3,
                resample_sr=0,
                rms_mix_rate=0.25,
                protect=0.33,
            )
            tgt_sr = int(vc.tgt_sr)

        if out_audio is None:
            return f"{info}\nConversion finished but returned no audio.", None
        if isinstance(out_audio, np.ndarray):
            out_audio = (tgt_sr, out_audio)
        elif isinstance(out_audio, (tuple, list)) and len(out_audio) == 2:
            sample_rate, waveform = out_audio
            waveform = np.asarray(waveform)
            if waveform.size == 0:
                return f"{info}\nConversion finished but returned an empty audio track.", None
            out_audio = (int(sample_rate), waveform)
        else:
            return (
                f"{info}\nConversion returned an unsupported audio format: "
                f"{type(out_audio).__name__}.",
                None,
            )

        if index_path:
            info = f"Using index: {index_path}\n{info}"
        else:
            info = f"No matching voice index found for {speaker_name}; converted without an index.\n{info}"
        return info, out_audio
    except Exception as error:
        traceback.print_exc()
        return f"Audio conversion failed: {error}", None


def convert_selected_audio(source_mode, file_audio, microphone_audio, speaker_name, model_name):
    audio_source = file_audio if source_mode == "Upload a file" else microphone_audio
    return convert_file(audio_source, speaker_name, model_name)


REALTIME_BLOCK_SECONDS = 0.25
# If the server falls this far behind the microphone, drop input so the queue
# catches up instead of letting latency grow without bound.
REALTIME_MAX_LAG_SECONDS = 1.0
# Converted audio is sent to the browser in segments of this length. Each
# segment is re-encoded by Gradio, so very small segments add overhead.
REALTIME_OUTPUT_SEGMENT_SECONDS = 0.5
# End the output stream if the microphone sends nothing for this long.
REALTIME_OUTPUT_IDLE_TIMEOUT = 5.0

# The HuBERT / synthesizer / RMVPE models are reused across sessions so that
# "Prepare voice model" does not reload everything from disk every time.
_shared_rvc = None
_shared_rvc_lock = threading.Lock()


def _to_float_mono(audio):
    """Gradio microphone audio arrives as int16 (samples, channels); the model needs float32 in [-1, 1]."""
    audio = np.asarray(audio)
    if np.issubdtype(audio.dtype, np.integer):
        audio = audio.astype(np.float32) / (float(np.iinfo(audio.dtype).max) + 1.0)
    else:
        audio = audio.astype(np.float32)
    if audio.ndim == 2:
        audio = audio.mean(axis=-1) if audio.shape[-1] <= 2 else audio.mean(axis=0)
    return audio.reshape(-1)


def _to_int16(audio):
    """Return int16 so Gradio does not peak-normalize each chunk (and divide by zero on silence)."""
    audio = np.nan_to_num(np.asarray(audio, dtype=np.float32), nan=0.0, posinf=0.0, neginf=0.0)
    return (np.clip(audio, -1.0, 1.0) * 32767.0).astype(np.int16)


class _StreamResampler:
    """Resamples a continuous stream chunk by chunk without clicks at chunk edges."""

    def __init__(self, in_rate, out_rate):
        self.in_rate = int(in_rate)
        self.out_rate = int(out_rate)
        try:
            import soxr

            self._stream = soxr.ResampleStream(
                self.in_rate, self.out_rate, 1, dtype="float32", quality="HQ"
            )
        except Exception:
            self._stream = None
            divisor = math.gcd(self.in_rate, self.out_rate)
            self._up = self.out_rate // divisor
            self._down = self.in_rate // divisor

    def __call__(self, audio):
        if audio.size == 0:
            return audio
        if self._stream is not None:
            return self._stream.resample_chunk(audio).astype(np.float32)
        from scipy.signal import resample_poly

        return resample_poly(audio, self._up, self._down).astype(np.float32)


class RealtimeSession:
    def __init__(self, model_name, speaker_name, f0_method="rmvpe"):
        global _shared_rvc
        self.lock = threading.Lock()
        self.f0_method = f0_method
        self.speaker_name = speaker_name
        self.has_streamed = False
        self.failed = False
        self.config = Config()
        self.config.use_jit = False
        self.speaker_id = resolve_speaker_id(speaker_name, model_name)
        self.index_path = get_index_for_speaker(model_name, speaker_name)
        index_rate = 0.75 if self.index_path else 0.0
        with _shared_rvc_lock:
            self.rvc = rvc_for_realtime.RVC(
                0,
                0.0,
                str(Path(os.getenv("weight_root", "weights")) / model_name),
                self.index_path,
                index_rate,
                1,
                Queue(),
                Queue(),
                self.config,
                _shared_rvc,
            )
            if not hasattr(self.rvc, "tgt_sr"):
                raise RuntimeError("Real-time voice model initialization failed; check the server log.")
            _shared_rvc = self.rvc
        self.rvc.spk_id = self.speaker_id

        self.sample_rate = self.rvc.tgt_sr
        self.zc = self.sample_rate // 100
        self.block_frame = int(round(REALTIME_BLOCK_SECONDS * self.sample_rate / self.zc)) * self.zc
        self.block_frame_16k = 160 * self.block_frame // self.zc
        self.crossfade_frame = int(round(0.05 * self.sample_rate / self.zc)) * self.zc
        self.sola_buffer_frame = min(self.crossfade_frame, 4 * self.zc)
        self.sola_search_frame = self.zc
        self.extra_frame = int(round(2.5 * self.sample_rate / self.zc)) * self.zc

        fade = torch.linspace(
            0.0, 1.0, steps=self.sola_buffer_frame, device=self.config.device, dtype=torch.float32
        )
        self.fade_in_window = torch.sin(0.5 * np.pi * fade) ** 2
        self.fade_out_window = 1 - self.fade_in_window
        self.resampler = tat.Resample(
            orig_freq=self.sample_rate, new_freq=16000, dtype=torch.float32
        ).to(self.config.device)

        self._reset_state()
        # Warm up (loads RMVPE etc.) so the first live chunk is not slow.
        self.process_block(np.zeros(self.block_frame, dtype=np.float32))
        self._reset_state()

    def _reset_state(self):
        buffer_size = (
            self.extra_frame
            + self.crossfade_frame
            + self.sola_search_frame
            + self.block_frame
        )
        device = self.config.device
        self.input_wav = torch.zeros(buffer_size, device=device, dtype=torch.float32)
        self.input_wav_res = torch.zeros(160 * buffer_size // self.zc, device=device, dtype=torch.float32)
        self.sola_buffer = torch.zeros(self.sola_buffer_frame, device=device, dtype=torch.float32)
        self.input_pending = np.empty(0, dtype=np.float32)
        self.output_pending = np.empty(0, dtype=np.float32)
        self.input_resampler = None
        # Lag tracking (see process_chunk).
        self.stream_anchor = None
        self.audio_received = 0.0
        self.last_call_end = None
        self.dropped_seconds = 0.0
        self.notice = None
        # Fresh pitch history for the new take.
        if self.rvc is not None:
            self.rvc.cache_pitch.zero_()
            self.rvc.cache_pitchf.zero_()
            self.rvc._log2_p_source_ema = None
            self.rvc._auto_key_ema = 0.0

    def reset(self):
        """Clear audio buffers between recordings but keep the model loaded."""
        with self.lock:
            if self.rvc is not None:
                self._reset_state()
            self.has_streamed = False
            self.failed = False

    def _is_backlogged(self, now, chunk_seconds):
        """Return True when this chunk is so late that it should be dropped."""
        # When the server keeps up, chunks arrive ~stream_every apart, leaving a
        # gap after the previous call. Back-to-back calls mean a queue backlog.
        idle_gap = None if self.last_call_end is None else now - self.last_call_end
        if self.stream_anchor is None or (idle_gap is not None and idle_gap > 0.3 * REALTIME_BLOCK_SECONDS):
            self.stream_anchor = now - self.audio_received
        self.audio_received += chunk_seconds
        lag = (now - self.stream_anchor) - self.audio_received
        return lag > REALTIME_MAX_LAG_SECONDS

    def process_chunk(self, audio_chunk):
        input_rate, audio = audio_chunk
        input_rate = int(input_rate)
        audio = _to_float_mono(audio)
        output_length = int(round(audio.size * self.sample_rate / input_rate)) if input_rate else 0

        with self.lock:
            if self.rvc is None:
                raise RuntimeError("The real-time session was stopped. Click Prepare voice model again.")
            now = time.monotonic()
            try:
                if audio.size and self._is_backlogged(now, audio.size / input_rate):
                    # Skip this chunk so the queue drains and latency recovers.
                    self.dropped_seconds += audio.size / input_rate
                    self.input_pending = np.empty(0, dtype=np.float32)
                    self.input_resampler = None
                    self.notice = (
                        f"The server is falling behind; skipped {self.dropped_seconds:.1f} s of audio. "
                        "Try the PM pitch method or a faster GPU."
                    )
                    return self.sample_rate, np.zeros(output_length, dtype=np.float32)

                if input_rate != self.sample_rate and audio.size:
                    if self.input_resampler is None or self.input_resampler.in_rate != input_rate:
                        self.input_resampler = _StreamResampler(input_rate, self.sample_rate)
                    audio = self.input_resampler(audio)

                self.input_pending = np.concatenate((self.input_pending, audio))
                processed = []
                while self.input_pending.size >= self.block_frame:
                    block = self.input_pending[: self.block_frame]
                    self.input_pending = self.input_pending[self.block_frame :]
                    processed.append(self.process_block(block))
                if processed:
                    self.output_pending = np.concatenate((self.output_pending, *processed))

                output = self.output_pending[:output_length]
                self.output_pending = self.output_pending[output_length:]
                if output.size < output_length:
                    output = np.pad(output, (0, output_length - output.size))
                return self.sample_rate, output
            finally:
                self.last_call_end = time.monotonic()

    def process_block(self, audio):
        self.input_wav[:-self.block_frame] = self.input_wav[self.block_frame :].clone()
        self.input_wav[-self.block_frame :] = torch.from_numpy(audio).to(self.config.device)
        self.input_wav_res[:-self.block_frame_16k] = self.input_wav_res[
            self.block_frame_16k :
        ].clone()
        self.input_wav_res[-160 * (self.block_frame // self.zc + 1) :] = self.resampler(
            self.input_wav[-self.block_frame - 2 * self.zc :]
        )[160:]

        skip_head = self.extra_frame // self.zc
        return_length = (
            self.block_frame + self.sola_buffer_frame + self.sola_search_frame
        ) // self.zc
        infer_wav = self.rvc.infer(
            self.input_wav_res,
            self.block_frame_16k,
            skip_head,
            return_length,
            self.f0_method,
        )

        conv_input = infer_wav[None, None, : self.sola_buffer_frame + self.sola_search_frame]
        cor_nom = F.conv1d(conv_input, self.sola_buffer[None, None, :])
        cor_den = torch.sqrt(
            F.conv1d(
                conv_input**2,
                torch.ones(1, 1, self.sola_buffer_frame, device=self.config.device),
            )
            + 1e-8
        )
        sola_offset = torch.argmax(cor_nom[0, 0] / cor_den[0, 0])
        infer_wav = infer_wav[sola_offset:]
        infer_wav[: self.sola_buffer_frame] *= self.fade_in_window
        infer_wav[: self.sola_buffer_frame] += self.sola_buffer * self.fade_out_window
        self.sola_buffer[:] = infer_wav[
            self.block_frame : self.block_frame + self.sola_buffer_frame
        ]
        return infer_wav[: self.block_frame].detach().cpu().numpy().astype(np.float32)

    def close(self):
        with self.lock:
            # Models stay cached in _shared_rvc for the next Prepare.
            self.rvc = None
            self.input_wav = None
            self.input_wav_res = None
            self.sola_buffer = None
        if torch.cuda.is_available():
            torch.cuda.empty_cache()


REALTIME_F0_METHOD = "rmvpe"


class LiveOutput:
    """Per-browser real-time state: the loaded voice session and the audio queue.

    Record starts `live_output_stream`, which loads the model and then streams
    converted audio to the player. Gradio only streams audio to a
    `streaming=True` output from a generator, so the microphone handler puts
    converted chunks in `queue` and the generator yields them.
    """

    def __init__(self):
        self.queue = queue.Queue()
        self.take = 0
        self.take_started = 0.0
        self.active = False
        self.ready = False
        self.error = None
        self.session = None
        self.session_key = None
        self.lock = threading.Lock()

    @staticmethod
    def _drain(q):
        while True:
            try:
                q.get_nowait()
            except queue.Empty:
                return

    def start_take(self):
        """Begin a new recording take; returns None for a duplicate Record event.

        When recording again, the browser can fire start_recording twice at
        once. The first call keeps the take; a second call within a moment of
        it is treated as a duplicate.
        """
        now = time.monotonic()
        if self.active and now - self.take_started < 1.5:
            return None
        self.take_started = now
        self.take += 1
        self.active = True
        self.ready = False
        self.error = None
        self._drain(self.queue)
        return self.take

    def ensure_session(self, model_name, speaker_name):
        """Load the voice model for this model/voice, reusing it when unchanged."""
        key = (model_name, speaker_name)
        with self.lock:
            if self.session is not None and self.session_key == key and self.session.rvc is not None:
                self.session.reset()
                return self.session
            if self.session is not None:
                self.session.close()
                self.session = None
            self.session = RealtimeSession(model_name, speaker_name, REALTIME_F0_METHOD)
            self.session_key = key
            return self.session

    def silence(self):
        """0.1 s of silence at the model's rate (long enough for Gradio's AAC encoder)."""
        rate = int(self.session.sample_rate) if self.session is not None else 48000
        return rate, np.zeros(rate // 10, dtype=np.int16)

    def stop(self):
        self.active = False
        self.ready = False
        if self.session is not None:
            self.session.reset()

    def close(self):
        self.active = False
        self.ready = False
        with self.lock:
            if self.session is not None:
                self.session.close()
                self.session = None


_live_outputs = {}
_live_outputs_lock = threading.Lock()


def _get_live_output(request):
    key = getattr(request, "session_hash", None) or "default"
    with _live_outputs_lock:
        live = _live_outputs.get(key)
        if live is None:
            live = _live_outputs[key] = LiveOutput()
        return live


def _drop_live_output(request: gr.Request):
    key = getattr(request, "session_hash", None) or "default"
    with _live_outputs_lock:
        live = _live_outputs.pop(key, None)
    if live is not None:
        live.close()


def live_output_stream(model_name, speaker_name, request: gr.Request):
    """Started by Record: load the voice model, then stream converted audio to the player.

    Yields audio only, and its first message is real converted audio at the
    model's rate, which is what makes the browser attach the player to this
    take's stream. Gradio fails when a stream ends without any audio, so early
    exits send 0.1 s of silence.
    """
    live = _get_live_output(request)
    take = live.start_take()

    if take is None:
        # Duplicate Record event: stay silent until the real take ends, so its
        # stream is the one the player attaches to, then end quietly.
        while live.active:
            time.sleep(0.2)
        yield live.silence()
        return

    if not model_name or not speaker_name:
        live.error = "Choose a target singer voice, then click Record again."
        live.active = False
        yield live.silence()
        return

    try:
        session = live.ensure_session(model_name, speaker_name)
    except Exception as error:
        traceback.print_exc()
        live.error = f"Could not load the voice model: {error}"
        live.active = False
        yield live.silence()
        return
    if live.take != take or not live.active:
        yield live.silence()  # stopped while the model was loading
        return
    live.ready = True

    pending, pending_rate = [], None
    pending_samples = 0
    idle_since = time.monotonic()

    def flush():
        nonlocal pending, pending_samples
        chunk = np.concatenate(pending)
        pending, pending_samples = [], 0
        return pending_rate, _to_int16(chunk)

    while live.active and live.take == take:
        try:
            rate, chunk = live.queue.get(timeout=0.2)
        except queue.Empty:
            if time.monotonic() - idle_since > REALTIME_OUTPUT_IDLE_TIMEOUT:
                break  # microphone stopped sending without a stop event
            continue
        idle_since = time.monotonic()
        if pending and rate != pending_rate:
            yield flush()
        pending_rate = rate
        pending.append(chunk)
        pending_samples += chunk.size
        if pending_samples >= REALTIME_OUTPUT_SEGMENT_SECONDS * rate:
            yield flush()
    if pending:
        yield flush()


def begin_realtime_take(speaker_name):
    """Runs instantly on Record: clear the player (so it remounts and attaches to the
    new take's stream) and show that the voice model is loading."""
    if not speaker_name:
        return None, "Choose a target singer voice, then click Record again."
    return None, f"Loading the voice model for {speaker_name}…"


def feed_realtime_chunk(audio_chunk, request: gr.Request):
    """Microphone stream handler: convert one chunk, queue it for the player, report status."""
    if audio_chunk is None:
        return gr.update()
    live = _get_live_output(request)
    if live.error is not None:
        return live.error
    session = live.session
    if not live.ready or session is None:
        return gr.update()  # model still loading; skip audio until it is ready
    if session.failed:
        return gr.update()
    try:
        sample_rate, converted = session.process_chunk(audio_chunk)
        live.queue.put((int(sample_rate), converted))
        if session.notice:
            notice, session.notice = session.notice, None
            return notice
        if not session.has_streamed:
            session.has_streamed = True
            index_note = "" if session.index_path else " (no matching index; converting without one)"
            return f"Live conversion is active for {session.speaker_name}{index_note}. Click Stop to finish."
        return gr.update()
    except Exception as error:
        traceback.print_exc()
        session.failed = True
        return f"Real-time conversion failed: {error}"


def stop_recording_realtime(request: gr.Request):
    """Stop: end the take but keep the model loaded so the next Record starts fast."""
    _get_live_output(request).stop()
    return "Stopped. Click Record to convert again."


model_choices = get_model_choices()
default_model = next(
    (
        model_name
        for model_name in model_choices
        if (Path(os.getenv("index_root", "logs")) / Path(model_name).stem / "speakers.json").exists()
    ),
    model_choices[0] if model_choices else None,
)
speaker_choices = get_speaker_choices(default_model) if default_model else []

APP_CSS = """
:root {
    --dlmsl-ink: #16263a;
    --dlmsl-muted: #64748b;
    --dlmsl-line: #dce5ee;
    --dlmsl-accent: #087f8c;
    --dlmsl-accent-hover: #066a75;
}

.gradio-container {
    width: 100% !important;
    max-width: 1320px !important;
    margin: 0 auto !important;
    background: #f3f6fa;
    color: var(--dlmsl-ink);
}

#dlmsl-app {
    width: 100%;
    max-width: 1320px;
    box-sizing: border-box;
    padding: 32px 28px 48px;
}

#page-header {
    padding: 30px 34px;
    margin-bottom: 22px;
    border: 1px solid var(--dlmsl-line);
    border-top: 4px solid var(--dlmsl-accent);
    border-radius: 16px;
    background: linear-gradient(115deg, #ffffff 0%, #f7fbfc 100%);
    box-shadow: 0 12px 30px rgba(22, 38, 58, 0.06);
}

#page-title h1 {
    margin: 0;
    color: var(--dlmsl-ink);
    font-family: "Segoe UI", Inter, sans-serif;
    font-size: clamp(27px, 3vw, 36px);
    font-weight: 750;
    letter-spacing: -0.7px;
}

#page-subtitle p {
    margin: 7px 0 0;
    color: var(--dlmsl-muted);
    font-size: 15px;
}

#mode-choice {
    padding: 14px 18px;
    margin-bottom: 20px;
    border: 1px solid var(--dlmsl-line);
    border-radius: 12px;
    background: #fff;
    box-shadow: 0 4px 14px rgba(22, 38, 58, 0.035);
}

#workspace {
    gap: 22px;
    align-items: stretch;
}

#audio-panel,
#controls-panel {
    padding: 26px;
    border: 1px solid var(--dlmsl-line);
    border-radius: 16px;
    background: #ffffff;
    box-shadow: 0 8px 24px rgba(22, 38, 58, 0.045);
}

#upload-instructions,
#realtime-instructions {
    margin: 0 0 16px;
    padding: 13px 16px;
    border: 1px solid #d7e8eb;
    border-radius: 10px;
    background: #f4fafb;
    color: #334155;
    font-size: 14px;
    line-height: 1.6;
}

#upload-instructions p,
#realtime-instructions p {
    margin: 0 0 5px;
}

#upload-instructions ol,
#realtime-instructions ol {
    margin: 5px 0 0;
    padding-left: 22px;
}

#upload-instructions li,
#realtime-instructions li {
    margin: 3px 0;
}

#audio-heading h2,
#controls-heading h2 {
    margin: 0 0 16px;
    color: var(--dlmsl-ink);
    font-family: "Segoe UI", Inter, sans-serif;
    font-size: 20px;
    font-weight: 700;
    letter-spacing: 0;
}

#dlmsl-app label {
    color: #334155;
    font-weight: 600;
}

#source-audio > div,
#output-audio > div {
    border-color: var(--dlmsl-line) !important;
    background: #f8fafc !important;
}

#convert-button button {
    min-height: 48px;
    border: 0;
    border-radius: 10px;
    background: var(--dlmsl-accent);
    color: #ffffff;
    font-size: 15px;
    font-weight: 700;
    box-shadow: 0 5px 14px rgba(8, 127, 140, 0.18);
    transition: filter 140ms ease, transform 140ms ease;
}

#convert-button button:hover {
    background: var(--dlmsl-accent-hover);
    transform: translateY(-1px);
}

#status-box textarea {
    color: #334155;
    background: #f8fafc;
}

#dlmsl-app button {
    border-radius: 9px;
    transition: background-color 140ms ease, transform 140ms ease;
}

#dlmsl-app button:not(#convert-button button):hover {
    background: #edf3f8;
    transform: translateY(-1px);
}

#dlmsl-app button:focus-visible {
    outline: 3px solid rgba(8, 127, 140, 0.35);
    outline-offset: 2px;
}

@media (max-width: 760px) {
    #dlmsl-app {
        padding: 16px 12px 28px;
    }

    #page-header {
        padding: 22px 20px;
    }

    #audio-panel,
    #controls-panel {
        padding: 19px;
    }
}
"""

# The page focuses on real-time conversion. The file-based Audio Conversion
# workflow is kept in the code but hidden; set SVC_SHOW_AUDIO_CONVERSION=1 to
# show it again (with a selector to switch between the two workflows).
SHOW_AUDIO_CONVERSION = os.getenv("SVC_SHOW_AUDIO_CONVERSION", "0").strip().lower() in ("1", "true", "yes")

with gr.Blocks(title="Singing Voice Conversion", elem_id="dlmsl-app") as demo:
    with gr.Column(elem_id="page-header"):
        gr.Markdown("# Singing Voice Conversion", elem_id="page-title")
        gr.Markdown(
            "Convert a recording or transform your voice live with your voice models."
            if SHOW_AUDIO_CONVERSION
            else "Transform your singing voice live with your voice models.",
            elem_id="page-subtitle",
        )

    mode_selector = gr.Radio(
        label="Choose a workflow",
        choices=["Audio Conversion", "Real-Time Voice Conversion"],
        value="Audio Conversion" if SHOW_AUDIO_CONVERSION else "Real-Time Voice Conversion",
        visible=SHOW_AUDIO_CONVERSION,
        elem_id="mode-choice",
    )
    with gr.Row(equal_height=False, elem_id="workspace"):
        with gr.Column(scale=6, elem_id="audio-panel"):
            with gr.Column(visible=SHOW_AUDIO_CONVERSION, elem_id="upload-workflow") as upload_workflow:
                gr.Markdown("## Audio Conversion", elem_id="audio-heading")
                gr.Markdown(
                    "**Quick steps**\n\n"
                    "1. Choose **Upload a file** or **Record with microphone**.\n"
                    "2. For a microphone recording, click **Record**, allow browser access if prompted, then stop when finished.\n"
                    "3. Choose a target singer voice, then click **Convert audio**. The converted result appears in the panel on the right.",
                    elem_id="upload-instructions",
                )
                audio_source_selector = gr.Radio(
                    label="Audio source",
                    choices=["Upload a file", "Record with microphone"],
                    value="Upload a file",
                    elem_id="audio-source-mode",
                )
                with gr.Group(elem_id="file-source") as file_source_group:
                    audio_input = gr.Audio(
                        label="Choose audio file",
                        sources=["upload"],
                        type="filepath",
                        elem_id="source-audio-file",
                    )
                with gr.Group(visible=False, elem_id="microphone-source") as microphone_source_group:
                    microphone_audio_input = gr.Audio(
                        label="Record audio",
                        sources=["microphone"],
                        type="filepath",
                        elem_id="source-audio-microphone",
                    )
            with gr.Column(visible=not SHOW_AUDIO_CONVERSION, elem_id="realtime-workflow") as realtime_workflow:
                gr.Markdown("## Real-Time Voice Conversion", elem_id="realtime-heading")
                gr.Markdown(
                    "**Quick steps**\n\n"
                    "1. Choose a target singer voice.\n"
                    "2. Click **Record** under **Microphone input** and allow browser access if prompted. "
                    "The voice model loads automatically (a few seconds the first time), then your converted voice plays under **Live output**.\n"
                    "3. Click **Stop** to finish. You can record again as often as you like.",
                    # "**Use headphones** — playing the output through speakers feeds it back into the microphone. "
                    # "Browser streaming adds roughly 1–3 seconds of delay; for live performance use the desktop app (gui_demo.py).",
                    elem_id="realtime-instructions",
                )
                realtime_input = gr.Audio(
                    label="Microphone input",
                    sources=["microphone"],
                    type="numpy",
                    streaming=True,
                    elem_id="realtime-microphone",
                )
                realtime_output = gr.Audio(
                    label="Live output",
                    streaming=True,
                    autoplay=True,
                    elem_id="realtime-output",
                )

        with gr.Column(scale=5, elem_id="controls-panel"):
            gr.Markdown("## Voice settings", elem_id="controls-heading")
            # Hidden: the default model (the one with a singer list) is always used.
            model_dropdown = gr.Dropdown(
                label="Voice model",
                choices=model_choices,
                value=default_model,
                interactive=True,
                visible=False,
                elem_id="model-select",
            )
            speaker_input = gr.Dropdown(
                label="Target singer voice",
                choices=speaker_choices,
                value=speaker_choices[0] if speaker_choices else None,
                interactive=True,
                elem_id="speaker-select",
            )
            with gr.Group(visible=SHOW_AUDIO_CONVERSION, elem_id="upload-controls") as upload_controls:
                convert_button = gr.Button("Convert audio", variant="primary", elem_id="convert-button")
                status_box = gr.Textbox(label="Conversion status", value="Ready to convert.", elem_id="status-box")
                output_audio = gr.Audio(label="Converted audio", elem_id="output-audio")
            with gr.Column(visible=not SHOW_AUDIO_CONVERSION, elem_id="realtime-controls") as realtime_controls:
                realtime_status = gr.Textbox(
                    label="Live conversion status",
                    value="Choose a target singer voice, then click Record to start converting.",
                    elem_id="realtime-status",
                )

    def update_speaker_choices(model_name):
        choices = get_speaker_choices(model_name)
        return gr.update(choices=choices, value=choices[0] if choices else None)

    def update_mode(mode):
        is_upload = mode == "Audio Conversion"
        return (
            gr.update(visible=is_upload),
            gr.update(visible=not is_upload),
            gr.update(visible=is_upload),
            gr.update(visible=not is_upload),
        )

    mode_selector.change(
        fn=update_mode,
        inputs=[mode_selector],
        outputs=[upload_workflow, realtime_workflow, upload_controls, realtime_controls],
    )

    def update_audio_source(source_mode):
        upload_file = source_mode == "Upload a file"
        return gr.update(visible=upload_file), gr.update(visible=not upload_file)

    audio_source_selector.change(
        fn=update_audio_source,
        inputs=[audio_source_selector],
        outputs=[file_source_group, microphone_source_group],
    )

    model_dropdown.change(
        fn=update_speaker_choices,
        inputs=[model_dropdown],
        outputs=[speaker_input],
    )

    # Record: load (or reuse) the voice model, then stream converted audio to the
    # Live output player for the whole take. Runs alongside the microphone
    # stream, so it must not share that event's concurrency slot.
    # The browser player attaches to a stream only once per mount, so clear the
    # Live output first: it remounts and attaches to this take's new stream.
    realtime_input.start_recording(
        fn=begin_realtime_take,
        inputs=[speaker_input],
        outputs=[realtime_output, realtime_status],
        queue=False,
        show_progress="hidden",
    )
    realtime_input.start_recording(
        fn=live_output_stream,
        inputs=[model_dropdown, speaker_input],
        outputs=[realtime_output],
        concurrency_limit=None,
        show_progress="hidden",
    )

    # Each microphone chunk is converted and queued for the output stream.
    realtime_stream_event = realtime_input.stream(
        fn=feed_realtime_chunk,
        inputs=[realtime_input],
        outputs=[realtime_status],
        stream_every=REALTIME_BLOCK_SECONDS,
        concurrency_limit=1,
        concurrency_id="realtime-svc",
        show_progress="hidden",
    )

    # Stop: end the take; the model stays loaded so the next Record starts fast.
    realtime_input.stop_recording(
        fn=stop_recording_realtime,
        inputs=None,
        outputs=[realtime_status],
        cancels=[realtime_stream_event],
    )

    # Free the model when the browser tab closes.
    demo.unload(_drop_live_output)

    convert_button.click(
        fn=convert_selected_audio,
        inputs=[audio_source_selector, audio_input, microphone_audio_input, speaker_input, model_dropdown],
        outputs=[status_box, output_audio],
    )


if __name__ == "__main__":
    # A public share link routes audio through Gradio's tunnel, which adds latency.
    # Set SVC_SHARE=0 to serve on the local network only.
    share = os.getenv("SVC_SHARE", "1").strip().lower() not in ("0", "false", "no")
    port = int(os.getenv("SVC_PORT", "7865"))
    demo.launch(server_name="0.0.0.0", server_port=port, share=share, css=APP_CSS)
