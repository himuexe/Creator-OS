"""CPU-only offline speech recognition for the video analysis worker."""
from collections.abc import Callable
from dataclasses import asdict, dataclass
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Protocol
import wave


MAX_DURATION_SECONDS = 3600
SAMPLE_RATE = 16000
NO_SPEECH = "No speech was detected in this recording."
Progress = Callable[[float], None]


class TranscriptionError(RuntimeError):
    """Safe to display to the creator."""


@dataclass(frozen=True)
class SpeechSegment:
    start: float
    end: float
    text: str


@dataclass(frozen=True)
class Transcription:
    language: str
    provider: str
    model: str
    segments: list[SpeechSegment]


class TranscriptionProvider(Protocol):
    def recognize(self, audio: Path, duration: float, progress: Progress) -> Transcription: ...


def extract_audio(source: Path, audio: Path, duration: float) -> None:
    if shutil.disk_usage(audio.parent).free < math.ceil(duration * SAMPLE_RATE * 2) + 1048576:
        raise TranscriptionError("There is insufficient temporary disk space to extract this recording.")
    try:
        result = subprocess.run([
            os.environ.get("FFMPEG_BIN", "ffmpeg"), "-hide_banner", "-loglevel", "error", "-nostdin",
            "-protocol_whitelist", "file", "-format_whitelist", "mov,matroska,webm",
            "-threads", "1", "-i", str(source), "-map", "0:a:0", "-vn", "-sn", "-dn",
            # Preserve late audio starts and gaps on the original playback timeline.
            "-af", "aresample=16000:async=1:first_pts=0", "-ac", "1", "-ar", str(SAMPLE_RATE),
            "-c:a", "pcm_s16le", "-t", str(duration), "-f", "wav", "-n", str(audio),
        ], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
           timeout=min(600, 30 + duration / 2), check=False)
    except OSError as exc:
        raise TranscriptionError("FFmpeg is unavailable. Check FFMPEG_BIN on the worker.") from exc
    except subprocess.TimeoutExpired as exc:
        raise TranscriptionError("Audio extraction timed out.") from exc
    if result.returncode:
        raise TranscriptionError("The video could not be decoded to audio. Check that it has a readable audio stream.")
    try:
        with wave.open(str(audio), "rb") as stream:
            if (stream.getnchannels(), stream.getframerate(), stream.getsampwidth()) != (1, SAMPLE_RATE, 2):
                raise TranscriptionError("Audio extraction returned an unexpected format.")
            if stream.getnframes() < 1:
                raise TranscriptionError("The recording contains no audio samples.")
    except (wave.Error, EOFError, OSError) as exc:
        raise TranscriptionError("The extracted audio could not be read.") from exc


def _decode(audio: Path, model_dir: Path, duration: float) -> Transcription:
    try:
        import numpy as np
        from faster_whisper import WhisperModel
    except (ImportError, OSError) as exc:
        raise TranscriptionError("Install the CPU speech dependencies in the worker environment.") from exc
    model = WhisperModel(str(model_dir), device="cpu", compute_type="int8", cpu_threads=4,
                         num_workers=1, local_files_only=True)
    # FFmpeg already produced validated mono PCM. Pass samples directly to the model.
    with wave.open(str(audio), "rb") as stream:
        samples = np.frombuffer(stream.readframes(stream.getnframes()), dtype="<i2").astype(np.float32)
    samples *= 1 / 32768
    predicted, info = model.transcribe(
        samples, beam_size=3, vad_filter=True, vad_parameters={"min_silence_duration_ms": 600},
        word_timestamps=True, condition_on_previous_text=False, temperature=0.0,
    )
    if info.duration_after_vad <= 0:
        raise TranscriptionError(NO_SPEECH)
    spans: list[SpeechSegment] = []
    progress_file = audio.parent / "progress"
    previous_percent = -1
    for prediction in predicted:
        text = prediction.text.strip()
        start, end = prediction.start, prediction.end
        if not math.isfinite(start) or not math.isfinite(end) or end < start:
            raise TranscriptionError("The speech model returned an invalid timestamp.")
        start = max(spans[-1].end if spans else 0.0, start)
        end = min(end, duration)
        if end <= start or not text:
            continue
        spans.append(SpeechSegment(start, end, text))
        percent = int(100 * end / duration)
        if percent > previous_percent:
            progress_file.write_text(str(percent), encoding="ascii")
            previous_percent = percent
    if not spans:
        raise TranscriptionError(NO_SPEECH)
    return Transcription(info.language, "faster-whisper", model_dir.name, spans)


class FasterWhisperCPU:
    """Run native inference in a child so cancellation and the deadline can stop it."""

    def recognize(self, audio: Path, duration: float, progress: Progress) -> Transcription:
        default = Path(__file__).resolve().parents[2] / ".local" / "models" / "faster-whisper-base"
        model_dir = Path(os.environ.get("WHISPER_MODEL_PATH", default)).resolve()
        if not all((model_dir / filename).is_file() for filename in ("config.json", "model.bin", "tokenizer.json")):
            raise TranscriptionError("The local speech model is missing. Check WHISPER_MODEL_PATH on the worker.")
        deadline = time.monotonic() + max(180, duration * 3)
        result_path = audio.parent / "recognition.json"
        progress_path = audio.parent / "progress"
        env = {**os.environ, "HF_HUB_OFFLINE": "1"}
        with subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), str(audio), str(model_dir), str(duration)],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            env=env,
        ) as process:
            latest = 0
            try:
                while process.poll() is None:
                    if time.monotonic() >= deadline:
                        raise TranscriptionError("CPU transcription exceeded its time limit.")
                    percentage = progress_path.read_text(encoding="ascii") if progress_path.exists() else ""
                    if percentage.isdecimal():
                        latest = max(latest, int(percentage))
                    progress(0.05 + 0.94 * latest / 100)
                    try:
                        process.wait(timeout=1)
                    except subprocess.TimeoutExpired:
                        pass
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()
        if not result_path.is_file():
            raise TranscriptionError("The CPU speech worker exited before completing recognition.")
        payload = json.loads(result_path.read_text(encoding="utf-8"))
        if process.returncode:
            raise TranscriptionError(payload["error"])
        return Transcription(payload["language"], payload["provider"], payload["model"],
                             [SpeechSegment(**span) for span in payload["segments"]])


def transcribe(source_path: Path, duration: float, progress: Progress, *,
               provider: TranscriptionProvider | None = None) -> Transcription:
    if not math.isfinite(duration) or duration <= 0:
        raise TranscriptionError("A known positive source duration is required for transcription.")
    if duration > MAX_DURATION_SECONDS:
        raise TranscriptionError("CPU transcription currently supports recordings up to 60 minutes.")
    scratch = None
    if os.environ.get("STORAGE_ROOT"):
        scratch = Path(os.environ["STORAGE_ROOT"]) / "processing"
        scratch.mkdir(exist_ok=True, parents=True)
    with tempfile.TemporaryDirectory(prefix="creatoros-speech-", dir=scratch) as directory:
        audio = Path(directory).resolve() / "audio.wav"
        progress(0.0)
        extract_audio(source_path.resolve(), audio, duration)
        progress(0.05)
        result = (provider or FasterWhisperCPU()).recognize(audio, duration, progress)
        progress(1.0)
        return result


if __name__ == "__main__":
    audio_file, model_path, seconds = sys.argv[1:]
    audio_file = Path(audio_file)
    output = audio_file.parent / "recognition.json"
    try:
        transcript = _decode(audio_file, Path(model_path), float(seconds))
        output.write_text(json.dumps(asdict(transcript), ensure_ascii=False), encoding="utf-8")
    except Exception as exc:
        message = str(exc) if isinstance(exc, TranscriptionError) else "CPU recognition failed. Check the speech model and worker installation."
        output.write_text(json.dumps({"error": message}), encoding="utf-8")
        raise SystemExit(1)
