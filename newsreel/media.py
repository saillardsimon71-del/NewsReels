from __future__ import annotations

import json
import subprocess
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import Settings


class MediaToolError(RuntimeError):
    pass


@dataclass(slots=True)
class MediaInfo:
    path: Path
    duration: float
    width: int | None
    height: int | None
    fps: float | None
    video: bool
    audio: bool
    streams: list[dict[str, Any]]


def require_media_tools(settings: Settings) -> tuple[str, str]:
    ffmpeg = settings.resolved_ffmpeg()
    ffprobe = settings.resolved_ffprobe()
    if not ffmpeg or not ffprobe:
        missing = "ffmpeg" if not ffmpeg else "ffprobe"
        raise MediaToolError(
            f"{missing} introuvable. Installez FFmpeg et ajoutez ffmpeg.exe/ffprobe.exe au PATH, "
            "ou définissez NEWSREEL_FFMPEG et NEWSREEL_FFPROBE."
        )
    return ffmpeg, ffprobe


def _fraction(value: str | None) -> float | None:
    if not value or value == "0/0":
        return None
    try:
        left, right = value.split("/", 1)
        denominator = float(right)
        return float(left) / denominator if denominator else None
    except (ValueError, ZeroDivisionError):
        try:
            return float(value)
        except ValueError:
            return None


def probe_media(path: Path, settings: Settings) -> MediaInfo:
    path = Path(path).resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    ffprobe = settings.resolved_ffprobe()
    if ffprobe:
        command = [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=codec_type,width,height,r_frame_rate,avg_frame_rate",
            "-of",
            "json",
            str(path),
        ]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise MediaToolError(f"ffprobe a échoué pour {path.name}: {result.stderr[-2000:]}")
        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise MediaToolError(f"Réponse ffprobe invalide pour {path.name}.") from exc
        streams = data.get("streams", [])
        video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
        audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)
        fmt_duration = data.get("format", {}).get("duration")
        duration = float(fmt_duration) if fmt_duration not in (None, "N/A") else 0.0
        fps = None
        if video_stream:
            fps = _fraction(video_stream.get("avg_frame_rate")) or _fraction(
                video_stream.get("r_frame_rate")
            )
        return MediaInfo(
            path=path,
            duration=duration,
            width=int(video_stream["width"])
            if video_stream and video_stream.get("width")
            else None,
            height=int(video_stream["height"])
            if video_stream and video_stream.get("height")
            else None,
            fps=fps,
            video=video_stream is not None,
            audio=audio_stream is not None,
            streams=streams,
        )
    if path.suffix.lower() in {".wav", ".wave"}:
        try:
            with wave.open(str(path), "rb") as audio_file:
                duration = audio_file.getnframes() / audio_file.getframerate()
            return MediaInfo(path, duration, None, None, None, False, True, [])
        except (wave.Error, ZeroDivisionError) as exc:
            raise MediaToolError(f"WAV illisible: {path.name}") from exc
    raise MediaToolError(
        "ffprobe est requis pour inspecter ce média. Vérifiez l'installation de FFmpeg."
    )


def run_ffmpeg(command: list[str], settings: Settings) -> subprocess.CompletedProcess[str]:
    ffmpeg = settings.resolved_ffmpeg()
    if not ffmpeg:
        raise MediaToolError("ffmpeg introuvable. Installez FFmpeg et ajoutez ffmpeg.exe au PATH.")
    result = subprocess.run(
        [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", *command],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "erreur ffmpeg inconnue").strip()
        raise MediaToolError(f"ffmpeg a échoué (code {result.returncode}): {detail[-5000:]}")
    return result
