import multiprocessing
import os
import sys
import traceback
import json

from scipy import signal
import librosa
import numpy as np
from scipy.io import wavfile

now_dir = os.getcwd()
sys.path.append(now_dir)
print(sys.argv)

inp_root = sys.argv[1]
sr = int(sys.argv[2])
n_p = int(sys.argv[3])
exp_dir = sys.argv[4]
noparallel = sys.argv[5] == "True"
per = float(sys.argv[6])

from infer.lib.audio import load_audio
from infer.lib.slicer2 import Slicer

mutex = multiprocessing.Lock()
f = open("%s/preprocess.log" % exp_dir, "a+")


def println(strr: str):
    mutex.acquire()
    try:
        print(strr)
        f.write("%s\n" % strr)
        f.flush()
    finally:
        mutex.release()


def is_audio_file(name: str) -> bool:
    name_l = name.lower()
    return name_l.endswith((".wav", ".flac", ".mp3", ".m4a", ".ogg", ".aac"))


class PreProcess:
    def __init__(self, sr, exp_dir, per=3.0):
        self.slicer = Slicer(
            sr=sr,
            threshold=-42,
            min_length=1500,
            min_interval=400,
            hop_size=15,
            max_sil_kept=500,
        )
        self.sr = sr
        self.bh, self.ah = signal.butter(N=5, Wn=48, btype="high", fs=self.sr)
        self.per = per
        self.overlap = 0.3
        self.tail = self.per + self.overlap
        self.max = 0.9
        self.alpha = 0.75
        self.exp_dir = exp_dir
        self.gt_wavs_dir = "%s/0_gt_wavs" % exp_dir
        self.wavs16k_dir = "%s/1_16k_wavs" % exp_dir
        os.makedirs(self.exp_dir, exist_ok=True)
        os.makedirs(self.gt_wavs_dir, exist_ok=True)
        os.makedirs(self.wavs16k_dir, exist_ok=True)

    def norm_write(self, tmp_audio, idx0, idx1):
        tmp_max = np.abs(tmp_audio).max()
        if tmp_max > 2.5:
            println("%s-%s-%s-filtered" % (idx0, idx1, tmp_max))
            return
        tmp_audio = (tmp_audio / tmp_max * (self.max * self.alpha)) + (
            1 - self.alpha
        ) * tmp_audio
        wavfile.write(
            "%s/%s_%s.wav" % (self.gt_wavs_dir, idx0, idx1),
            self.sr,
            tmp_audio.astype(np.float32),
        )
        tmp_audio = librosa.resample(tmp_audio, orig_sr=self.sr, target_sr=16000)
        wavfile.write(
            "%s/%s_%s.wav" % (self.wavs16k_dir, idx0, idx1),
            16000,
            tmp_audio.astype(np.float32),
        )

    def pipeline(self, path, idx0):
        try:
            audio = load_audio(path, self.sr)
            # zero phased digital filter cause pre-ringing noise...
            # audio = signal.filtfilt(self.bh, self.ah, audio)
            audio = signal.lfilter(self.bh, self.ah, audio)

            idx1 = 0
            for audio_seg in self.slicer.slice(audio):
                i = 0
                while 1:
                    start = int(self.sr * (self.per - self.overlap) * i)
                    i += 1
                    if len(audio_seg[start:]) > self.tail * self.sr:
                        tmp_audio = audio_seg[start : start + int(self.per * self.sr)]
                        self.norm_write(tmp_audio, idx0, idx1)
                        idx1 += 1
                    else:
                        tmp_audio = audio_seg[start:]
                        idx1 += 1
                        break
                self.norm_write(tmp_audio, idx0, idx1)
            println("%s->Suc." % path)
        except Exception:
            println("%s->%s" % (path, traceback.format_exc()))

    def pipeline_mp(self, infos):
        for path, idx0 in infos:
            self.pipeline(path, idx0)

    def run_infos(self, infos, n_p):
        """
        Run preprocessing on a prepared list of (wav_path, idx0).
        idx0 will be used as the filename prefix to avoid collisions.
        """
        if len(infos) == 0:
            println("No audio files found. Please check your dataset folder.")
            return

        if noparallel:
            for i in range(n_p):
                self.pipeline_mp(infos[i::n_p])
        else:
            ps = []
            for i in range(n_p):
                p = multiprocessing.Process(target=self.pipeline_mp, args=(infos[i::n_p],))
                ps.append(p)
                p.start()
            for p in ps:
                p.join()

    def pipeline_mp_inp_dir(self, inp_root, n_p):
        """
        Single-speaker (flat folder) mode: treat files under inp_root as one speaker.
        """
        try:
            infos = []
            for idx, name in enumerate(sorted(list(os.listdir(inp_root)))):
                if name.startswith("."):
                    continue
                full = os.path.join(inp_root, name)
                if os.path.isfile(full) and is_audio_file(name):
                    infos.append((full, str(idx)))
            self.run_infos(infos, n_p)
        except Exception:
            println("Fail. %s" % traceback.format_exc())


def build_infos_and_speaker_map(inp_root: str, exp_dir: str):
    """
    Multi-speaker:
    input_root/
      SpeakerA/*.wav
      SpeakerB/*.wav
    Output:
      infos: list[(wav_path, idx0_prefix)]
      speaker_map: dict[speaker_name] -> sid
    """
    entries = [e for e in os.listdir(inp_root) if not e.startswith(".")]
    speaker_dirs = sorted([d for d in entries if os.path.isdir(os.path.join(inp_root, d))])
    speaker_map = {name: idx for idx, name in enumerate(speaker_dirs)}

    # Save mapping for later use (training / inference UI can read it)
    os.makedirs(exp_dir, exist_ok=True)
    with open(os.path.join(exp_dir, "speakers.json"), "w", encoding="utf-8") as wf:
        json.dump(speaker_map, wf, ensure_ascii=False, indent=2)
    println(f"Saved speaker map -> {os.path.join(exp_dir, 'speakers.json')}")

    infos = []
    for spk_name, spk_id in speaker_map.items():
        spk_path = os.path.join(inp_root, spk_name)
        files = [fn for fn in sorted(os.listdir(spk_path)) if (not fn.startswith(".")) and is_audio_file(fn)]
        for file_idx, fn in enumerate(files):
            wav_path = os.path.join(spk_path, fn)
            # idx0 prefix: "{sid}_{fileidx}"  -> segments become "{sid}_{fileidx}_{segidx}.wav"
            idx0 = f"{spk_id}_{file_idx}"
            infos.append((wav_path, idx0))

    return infos, speaker_map


def preprocess_trainset(inp_root, sr, n_p, exp_dir, per):
    pp = PreProcess(sr, exp_dir, per)
    println("start preprocess")
    println(sys.argv)

    # Detect multi-speaker: if inp_root contains at least one subfolder
    try:
        entries = [e for e in os.listdir(inp_root) if not e.startswith(".")]
        has_subdir = any(os.path.isdir(os.path.join(inp_root, e)) for e in entries)

        if has_subdir:
            infos, spk_map = build_infos_and_speaker_map(inp_root, exp_dir)
            println(f"Detected multi-speaker dataset: {len(spk_map)} speakers")
            pp.run_infos(infos, n_p)
        else:
            pp.pipeline_mp_inp_dir(inp_root, n_p)
    except Exception:
        println("Fail. %s" % traceback.format_exc())

    println("end preprocess")


if __name__ == "__main__":
    preprocess_trainset(inp_root, sr, n_p, exp_dir, per)
