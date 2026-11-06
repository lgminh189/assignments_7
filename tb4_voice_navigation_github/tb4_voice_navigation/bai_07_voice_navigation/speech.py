"""Offline Vietnamese Vosk input, PCM16 mono WAV or ALSA microphone."""
import json
import array
import math
import os
from pathlib import Path
import select
import subprocess
import tempfile
import time
import wave


def navigation_grammar(regions):
    """Keep unknown targets in the vocabulary so D is never mapped to A/B/C."""
    names = {"khu vực dê", "khu vực d", "khu vực không tồn tại", "phòng dê"}
    canonical = []
    for region in regions:
        ident = str(region["id"]).lower()
        names.update([ident, region["name"].lower(), f"khu vực {ident}", f"phòng {ident}"])
        names.update(alias.lower() for alias in region.get("aliases", []))
        canonical.append(f"khu vực {ident}")
        spoken = {"a": "phòng học", "b": "phòng thí nghiệm", "c": "hành lang"}.get(ident)
        if spoken in names:
            canonical.append(spoken)
    phrases = {"dừng", "dừng lại", "hủy", "hủy lệnh", "[unk]"}
    for name in names:
        phrases.update([f"đi đến {name}", f"di chuyển đến {name}", f"đến {name}"])
    for start in canonical:
        for end in [*canonical, "khu vực dê"]:
            phrases.add(f"di chuyển từ {start} đến {end}")
            for via in canonical:
                phrases.add(f"đi từ {start} qua {via} rồi đến {end}")
    return sorted(phrases)


def audio_level(audio):
    samples = array.array("h", audio[:len(audio)//2*2])
    import sys
    if sys.byteorder != "little":
        samples.byteswap()
    if not samples:
        return -96., 0.
    rms = math.sqrt(sum(x*x for x in samples)/len(samples))
    return max(-96., 20*math.log10(max(rms, .5)/32768)), sum(abs(x) >= 32700 for x in samples)/len(samples)


class PcmHighPass:
    """Stateful rumble filter; preserve state across incoming PCM chunks."""
    def __init__(self, rate, cutoff=150.):
        import numpy as np
        from scipy.signal import butter
        if not math.isfinite(cutoff) or not 0 <= cutoff < rate/2:
            raise ValueError("highpass phải >= 0 và nhỏ hơn nửa sample rate")
        self.sos = butter(4, cutoff, btype="highpass", fs=rate, output="sos") if cutoff else None
        self.state = np.zeros((len(self.sos), 2)) if cutoff else None

    def process(self, pcm):
        if self.sos is None:
            return pcm
        import numpy as np
        from scipy.signal import sosfilt
        samples = np.frombuffer(pcm, dtype="<i2").astype(float)
        filtered, self.state = sosfilt(self.sos, samples, zi=self.state)
        return np.clip(np.rint(filtered), -32768, 32767).astype("<i2").tobytes()


class SpeechRecognizer:
    def __init__(self, model_path, grammar=None, highpass_hz=150.):
        if not Path(model_path).is_dir():
            raise ValueError(f"Thiếu model Vosk: {model_path}")
        from vosk import Model
        self.model = Model(str(model_path))
        self.highpass_hz = highpass_hz
        if grammar is not None and not (Path(model_path) / "graph/HCLr.fst").is_file():
            raise ValueError("Model không hỗ trợ grammar động; dùng --free-form hoặc model small-vn-0.4")
        # Drop the whole phrase if a word is unsupported. Letting Vosk drop only
        # the missing destination token would leave an incomplete command.
        self.grammar = (list(dict.fromkeys(phrase for phrase in grammar
                         if all(self.model.vosk_model_find_word(word) >= 0 for word in phrase.split())))
                        if grammar is not None else None)
        if self.grammar is not None and "[unk]" not in self.grammar:
            raise ValueError("Model thiếu [unk]; dùng --free-form để giữ khả năng từ chối câu ngoài từ vựng")

    def decoder(self, rate):
        from vosk import KaldiRecognizer
        decoder = (KaldiRecognizer(self.model, rate, json.dumps(self.grammar, ensure_ascii=False))
                   if self.grammar is not None else KaldiRecognizer(self.model, rate))
        decoder.SetWords(True)
        return decoder

    @staticmethod
    def result(payload):
        result = json.loads(payload)
        return (result.get("text", "").strip(),
                min((word.get("conf", 0) for word in result.get("result", [])), default=0.))

    def wav(self, filename):
        with wave.open(str(filename), "rb") as audio:
            if audio.getnchannels() != 1 or audio.getsampwidth() != 2 or audio.getcomptype() != "NONE":
                raise ValueError("WAV phải là PCM16 mono không nén")
            decoder = self.decoder(audio.getframerate())
            processor = PcmHighPass(audio.getframerate(), self.highpass_hz)
            chunks = []
            while data := audio.readframes(4096):
                data = processor.process(data)
                if decoder.AcceptWaveform(data):
                    chunks.append(self.result(decoder.Result()))
            chunks.append(self.result(decoder.FinalResult()))
            chunks = [(text, conf) for text, conf in chunks if text]
            return " ".join(text for text, _ in chunks), min((c for _, c in chunks), default=0.)

    def microphone(self, stop, on_result, device="default", on_audio=None, on_partial=None):
        decoder = self.decoder(16000)
        processor = PcmHighPass(16000, self.highpass_hz)
        # A file avoids blocking the child if ALSA produces many diagnostics.
        with tempfile.TemporaryFile() as errors:
            process = subprocess.Popen(["arecord", "-q", "-D", device, "-t", "raw",
                                        "-f", "S16_LE", "-r", "16000", "-c", "1"],
                                       stdout=subprocess.PIPE, stderr=errors)
            try:
                last_audio = time.monotonic()
                last_level = 0.
                previous_partial = ""
                remainder = b""
                while not stop.is_set():
                    if not select.select([process.stdout], [], [], .1)[0]:
                        if time.monotonic()-last_audio > 5:
                            raise RuntimeError("Micro không gửi dữ liệu trong 5 giây")
                        continue
                    audio = os.read(process.stdout.fileno(), 4096)
                    if not audio:
                        errors.seek(0)
                        raise RuntimeError(errors.read().decode(errors="replace") or "Micro đã đóng")
                    audio = remainder + audio
                    usable = len(audio)//2*2
                    remainder = audio[usable:]
                    if not usable:
                        continue
                    audio = processor.process(audio[:usable])
                    last_audio = time.monotonic()
                    if on_audio and last_audio-last_level >= 2:
                        on_audio(*audio_level(audio))
                        last_level = last_audio
                    if decoder.AcceptWaveform(audio) and not stop.is_set():
                        on_result(*self.result(decoder.Result()))
                        previous_partial = ""
                    elif on_partial:
                        partial = json.loads(decoder.PartialResult()).get("partial", "")
                        if partial and partial != previous_partial:
                            on_partial(partial)
                        previous_partial = partial
                # Do not submit a partial utterance when input is stopped.
            finally:
                if process.poll() is None:
                    process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                process.stdout.close()
