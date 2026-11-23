import array
import math
import os
from pathlib import Path
import shutil
import subprocess
import wave

import pytest

from app.transcription import (
    FasterWhisperCPU, NO_SPEECH, SAMPLE_RATE, SpeechSegment, Transcription,
    TranscriptionError, transcribe,
)


@pytest.fixture
def encoder():
    path = shutil.which(os.environ.get("FFMPEG_BIN", "ffmpeg"))
    if not path:
        pytest.skip("Set FFMPEG_BIN to test audio extraction.")
    return path


@pytest.mark.parametrize("duration", [0, math.inf, math.nan, 3601])
def test_invalid_duration_is_rejected_before_decoding(duration, tmp_path):
    with pytest.raises(TranscriptionError, match="duration|60 minutes"):
        transcribe(tmp_path / "missing.mp4", duration, lambda _: None)


def test_missing_model_reports_configuration_issue(monkeypatch, tmp_path):
    monkeypatch.setenv("WHISPER_MODEL_PATH", str(tmp_path))
    with pytest.raises(TranscriptionError, match="WHISPER_MODEL_PATH"):
        FasterWhisperCPU().recognize(tmp_path / "audio.wav", 10, lambda _: None)


def test_extraction_preserves_audio_timeline_and_cleans_up(encoder, monkeypatch, tmp_path):
    movie = tmp_path / "late-audio.mp4"
    subprocess.run([
        encoder, "-loglevel", "error", "-nostdin", "-f", "lavfi", "-i", "color=s=64x64:r=8:d=2",
        "-itsoffset", "1", "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
        "-c:v", "mpeg4", "-c:a", "aac", str(movie),
    ], check=True, timeout=30)
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path))

    class CheckAudio:
        def recognize(self, audio, duration, progress):
            with wave.open(str(audio), "rb") as reader:
                assert (reader.getframerate(), reader.getnchannels(), reader.getsampwidth()) == (16000, 1, 2)
                samples = array.array("h", reader.readframes(reader.getnframes()))
            assert max(map(abs, samples[:SAMPLE_RATE // 2])) < 2
            assert max(map(abs, samples[SAMPLE_RATE:])) > 100
            return Transcription("en", "fixture", "tone", [SpeechSegment(1, 2, "Example")])

    updates = []
    result = transcribe(movie, 2, updates.append, provider=CheckAudio())
    assert updates == [0, 0.05, 1]
    assert result.segments[0].start == 1
    assert not list((tmp_path / "processing").iterdir())


def test_video_without_audio_returns_actionable_error(encoder, monkeypatch, tmp_path):
    movie = tmp_path / "no-audio.mp4"
    subprocess.run([
        encoder, "-loglevel", "error", "-nostdin", "-f", "lavfi", "-i", "color=s=64x64:d=1",
        "-c:v", "mpeg4", str(movie),
    ], check=True, timeout=30)
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path))
    with pytest.raises(TranscriptionError, match="audio stream"):
        transcribe(movie, 1, lambda _: None)
    assert not list((tmp_path / "processing").iterdir())


def test_silence_does_not_create_transcript(encoder, monkeypatch, tmp_path):
    pytest.importorskip("faster_whisper", reason="Run with the CPU worker and its local model.")
    if not (os.getenv("WHISPER_MODEL_PATH") and Path(os.environ["WHISPER_MODEL_PATH"]).is_dir()):
        pytest.skip("Set WHISPER_MODEL_PATH to run real voice activity detection.")
    movie = tmp_path / "silence.mp4"
    subprocess.run([
        encoder, "-loglevel", "error", "-nostdin", "-f", "lavfi", "-i", "color=s=64x64:d=3",
        "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono", "-t", "3", "-c:v", "mpeg4", "-c:a", "aac",
        str(movie),
    ], check=True, timeout=30)
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path))
    with pytest.raises(TranscriptionError, match=NO_SPEECH):
        transcribe(movie, 3, lambda _: None)
    assert not list((tmp_path / "processing").iterdir())
