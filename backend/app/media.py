import json
import math
import subprocess
from fractions import Fraction
from pathlib import Path

from fastapi import HTTPException


def inspect_video(path: Path, extension: str, ffprobe: str) -> dict:
    """Inspect a local, self-contained media container with bounded probe work."""
    family = "mov" if extension in {".mov", ".mp4"} else "matroska"
    args = [
        ffprobe, "-v", "error", "-protocol_whitelist", "file",
        "-format_whitelist", "mov,matroska,webm", "-probesize", "5000000",
        "-analyzeduration", "5000000", "-max_streams", "64",
        "-show_entries",
        "format=format_name,duration:stream=codec_type,width,height,avg_frame_rate:"
        "stream_disposition=attached_pic",
        "-of", "json", str(path),
    ]
    try:
        probe = subprocess.run(args, stdin=subprocess.DEVNULL, capture_output=True, timeout=20, check=False)
    except OSError as exc:
        raise HTTPException(503, "Video inspection is unavailable. Check the FFprobe installation.") from exc
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(422, "Video inspection timed out.") from exc
    if probe.returncode:
        raise HTTPException(422, "The uploaded file could not be read as a supported video.")
    try:
        data = json.loads(probe.stdout)
        streams = data["streams"]
        container = data["format"]
        if family not in container["format_name"].split(","):
            raise ValueError("Unexpected container")
        video = next(s for s in streams if s["codec_type"] == "video" and not s.get("disposition", {}).get("attached_pic"))
        duration = float(container["duration"])
        width, height = int(video["width"]), int(video["height"])
        if min(width, height) < 1 or not math.isfinite(duration) or duration <= 0:
            raise ValueError("Invalid media dimensions or duration")
    except (KeyError, StopIteration, TypeError, ValueError) as exc:
        raise HTTPException(422, "A playable video stream with a known duration is required.") from exc
    try:
        frame_rate = float(Fraction(video["avg_frame_rate"]))
    except (KeyError, ValueError, ZeroDivisionError):
        frame_rate = None
    return {
        "duration_seconds": duration, "width": width, "height": height,
        "frame_rate": frame_rate, "audio_streams": sum(s["codec_type"] == "audio" for s in streams),
        "format": container["format_name"],
    }
