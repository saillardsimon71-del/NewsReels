from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .config import Settings
from .media import MediaToolError, probe_media, require_media_tools, run_ffmpeg
from .models import Scene, Timeline


class AssemblyError(RuntimeError):
    pass


def _font_path(size: int, bold: bool) -> Any:
    from PIL import ImageFont

    candidates: list[Path] = []
    windir = Path(os.environ.get("WINDIR", r"C:\Windows"))
    if os.name == "nt":
        if bold:
            candidates.extend([windir / "Fonts" / "segoeuib.ttf", windir / "Fonts" / "arialbd.ttf"])
        else:
            candidates.extend([windir / "Fonts" / "segoeui.ttf", windir / "Fonts" / "arial.ttf"])
    for path in candidates:
        if path.is_file():
            try:
                return ImageFont.truetype(str(path), size=size)
            except OSError:
                pass
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _wrap_text(
    draw: Any, text: str, font: Any, max_width: int, max_lines: int = 2
) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        test = f"{current} {word}".strip()
        if current and draw.textbbox((0, 0), test, font=font)[2] > max_width:
            lines.append(current)
            current = word
        else:
            current = test
    if current:
        lines.append(current)
    return lines[:max_lines]


def _render_overlay(path: Path, scene: Scene, width: int, height: int) -> None:
    from PIL import Image, ImageDraw

    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    if not scene.title and not scene.kicker:
        overlay.save(path)
        return
    draw = ImageDraw.Draw(overlay)

    if scene.id in {"intro", "outro"}:
        title_font = _font_path(round(width * 0.09), bold=True)
        kicker_font = _font_path(round(width * 0.031), bold=True)
        title = scene.title.upper()
        kicker = scene.kicker.upper()
        title_box = draw.textbbox((0, 0), title, font=title_font)
        title_w = title_box[2] - title_box[0]
        y = round(height * 0.43)
        x = max(round(width * 0.06), (width - title_w) // 2)
        draw.rounded_rectangle(
            (
                round(width * 0.10),
                y - round(height * 0.035),
                round(width * 0.90),
                y + round(height * 0.14),
            ),
            radius=28,
            fill=(3, 10, 18, 178),
        )
        draw.text((x + 3, y + 4), title, font=title_font, fill=(0, 0, 0, 125))
        draw.text((x, y), title, font=title_font, fill=(255, 255, 255, 255))
        if kicker:
            kicker_box = draw.textbbox((0, 0), kicker, font=kicker_font)
            kicker_w = kicker_box[2] - kicker_box[0]
            draw.text(
                ((width - kicker_w) // 2, y + round(height * 0.09)),
                kicker,
                font=kicker_font,
                fill=(78, 222, 225, 255),
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        overlay.save(path)
        return

    margin = round(width * 0.055)
    panel_left = margin
    panel_right = width - margin
    panel_bottom = height - round(height * 0.045)
    panel_top = round(height * 0.79)
    draw.rounded_rectangle(
        (panel_left, panel_top, panel_right, panel_bottom),
        radius=22,
        fill=(6, 18, 34, 210),
    )
    accent_w = max(8, round(width * 0.010))
    draw.rounded_rectangle(
        (panel_left, panel_top, panel_left + accent_w * 2, panel_bottom),
        radius=5,
        fill=(39, 207, 215, 255),
    )
    text_left = panel_left + round(width * 0.040)
    max_width = panel_right - text_left - round(width * 0.035)
    kicker_font = _font_path(round(width * 0.022), bold=True)
    title_font = _font_path(round(width * 0.042), bold=True)
    y = panel_top + round(height * 0.022)
    kicker = scene.kicker.upper()
    if kicker:
        draw.text((text_left, y), kicker, font=kicker_font, fill=(78, 222, 225, 255))
        y += round(height * 0.048)
    for line in _wrap_text(draw, scene.title, title_font, max_width, max_lines=2):
        draw.text((text_left, y), line, font=title_font, fill=(255, 255, 255, 255))
        y += round(height * 0.055)
    path.parent.mkdir(parents=True, exist_ok=True)
    overlay.save(path)


def _escape_concat_path(path: Path) -> str:
    value = path.resolve().as_posix()
    return value.replace("'", "'\\''")


def _audio_filter(duration: float) -> str:
    return (
        "aresample=48000,loudnorm=I=-16:TP=-1.5:LRA=11,"
        f"apad=pad_dur={duration:.6f},atrim=duration={duration:.6f},asetpts=PTS-STARTPTS[a]"
    )


def _image_video_filter(scene: Scene, fps: int, frames: int) -> str:
    motion = scene.motion
    step = 0.00032
    max_zoom = 1.045
    if motion == "slow_pan_left":
        zoom = f"min(zoom+{step},{max_zoom})"
        x = f"(iw-iw/zoom)*min(on/{frames},1)"
    elif motion == "slow_pan_right":
        zoom = f"min(zoom+{step},{max_zoom})"
        x = f"(iw-iw/zoom)*(1-min(on/{frames},1))"
    elif motion == "slow_pull_out":
        zoom = f"max({max_zoom}-on*{step},1.0)"
        x = "iw/2-(iw/zoom/2)"
    else:
        zoom = f"min(zoom+{step},{max_zoom})"
        x = "iw/2-(iw/zoom/2)"
    return (
        "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
        f"zoompan=z='{zoom}':x='{x}':y='ih/2-(ih/zoom/2)':d=1:s=1080x1920:fps={fps},setsar=1"
    )


class FFmpegAssembler:
    def __init__(self, settings: Settings):
        self.settings = settings

    def assemble(self, timeline_path: Path, run_dir: Path) -> dict[str, Any]:
        require_media_tools(self.settings)
        timeline_path = Path(timeline_path).resolve()
        run_dir = Path(run_dir).resolve()
        try:
            timeline = Timeline.from_mapping(json.loads(timeline_path.read_text(encoding="utf-8")))
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise AssemblyError(f"Timeline absente ou invalide: {exc}") from exc
        if timeline.run_id != run_dir.name:
            raise AssemblyError("Le run_id de timeline ne correspond pas au dossier de run.")
        if (timeline.width, timeline.height, timeline.fps) != (
            self.settings.width,
            self.settings.height,
            self.settings.fps,
        ):
            raise AssemblyError(
                "La résolution ou le framerate de la timeline ne correspond pas à la config."
            )

        segment_dir = run_dir / "segments"
        segment_dir.mkdir(parents=True, exist_ok=True)
        rendered: list[Path] = []
        for index, scene in enumerate(timeline.scenes):
            rendered.append(self._render_scene(index, scene, timeline, run_dir, segment_dir))

        concat_file = segment_dir / "concat.ffconcat"
        concat_file.write_text(
            "ffconcat version 1.0\n"
            + "".join(f"file '{_escape_concat_path(path)}'\n" for path in rendered),
            encoding="utf-8",
        )
        final_path = run_dir / "newsreel_final.mp4"
        try:
            run_ffmpeg(
                [
                    "-f",
                    "concat",
                    "-safe",
                    "0",
                    "-i",
                    str(concat_file),
                    "-map",
                    "0:v:0",
                    "-map",
                    "0:a:0",
                    "-c",
                    "copy",
                    "-movflags",
                    "+faststart",
                    "-fflags",
                    "+genpts",
                    str(final_path),
                ],
                self.settings,
            )
        except MediaToolError as exc:
            raise AssemblyError(f"Concaténation finale impossible: {exc}") from exc
        info = probe_media(final_path, self.settings)
        if not info.video or not info.audio:
            raise AssemblyError("Le MP4 final doit contenir une vidéo et une piste audio.")
        if (info.width, info.height) != (timeline.width, timeline.height):
            raise AssemblyError(
                f"Résolution finale incorrecte: {info.width}x{info.height}, "
                f"attendu {timeline.width}x{timeline.height}."
            )
        if info.fps is None or abs(info.fps - timeline.fps) > 0.05:
            raise AssemblyError(f"Framerate final incorrect: {info.fps} fps.")
        expected_duration = sum(scene.duration for scene in timeline.scenes)
        if info.duration < expected_duration - 0.75:
            raise AssemblyError(
                f"MP4 final tronqué ({info.duration:.2f}s, attendu environ {expected_duration:.2f}s)."
            )
        return {
            "path": final_path,
            "duration_seconds": round(info.duration, 3),
            "expected_duration_seconds": round(expected_duration, 3),
            "width": info.width,
            "height": info.height,
            "fps": round(info.fps, 3) if info.fps is not None else None,
            "audio": info.audio,
            "scene_count": len(timeline.scenes),
            "h3_clip_count": sum(scene.type == "h3_video" for scene in timeline.scenes),
            "segment_files": [path.relative_to(run_dir).as_posix() for path in rendered],
        }

    def _render_scene(
        self,
        index: int,
        scene: Scene,
        timeline: Timeline,
        run_dir: Path,
        segment_dir: Path,
    ) -> Path:
        source = (run_dir / Path(scene.asset)).resolve()
        try:
            source.relative_to(run_dir)
        except ValueError as exc:
            raise AssemblyError(f"Asset hors du dossier de run: {scene.asset}") from exc
        if not source.is_file():
            raise AssemblyError(f"Asset de scène introuvable ({scene.id}): {source}")
        duration = float(scene.duration)
        frames = max(1, int(round(duration * timeline.fps)))
        overlay = segment_dir / f"overlay-{index:02d}.png"
        _render_overlay(overlay, scene, timeline.width, timeline.height)
        destination = segment_dir / f"{index:02d}-{scene.id}.mp4"

        cmd: list[str] = []
        if scene.type in {"still", "host_still"}:
            audio_path: Path | None = None
            if scene.audio:
                audio_path = (run_dir / Path(scene.audio)).resolve()
                try:
                    audio_path.relative_to(run_dir)
                except ValueError as exc:
                    raise AssemblyError(f"Audio hors du dossier de run: {scene.audio}") from exc
                if not audio_path.is_file():
                    raise AssemblyError(f"Audio host introuvable ({scene.id}): {audio_path}")
                audio_info = probe_media(audio_path, self.settings)
                if not audio_info.audio:
                    raise AssemblyError(
                        f"Le fichier host n'a pas de piste audio: {audio_path.name}"
                    )
            cmd.extend(["-loop", "1", "-framerate", str(timeline.fps), "-i", str(source)])
            cmd.extend(["-loop", "1", "-framerate", str(timeline.fps), "-i", str(overlay)])
            if audio_path:
                cmd.extend(["-i", str(audio_path)])
                audio_index = 2
            else:
                cmd.extend(
                    [
                        "-f",
                        "lavfi",
                        "-i",
                        "anullsrc=channel_layout=stereo:sample_rate=48000",
                    ]
                )
                audio_index = 2
            video_filter = _image_video_filter(scene, timeline.fps, frames)
            graph = (
                f"[0:v]{video_filter}[base];"
                "[1:v]format=rgba[ov];"
                "[base][ov]overlay=0:0:eof_action=repeat:format=auto,"
                f"fps={timeline.fps},format=yuv420p,setsar=1[v];"
                f"[{audio_index}:a]{_audio_filter(duration)}"
            )
        elif scene.type == "h3_video":
            media = probe_media(source, self.settings)
            if not media.video:
                raise AssemblyError(f"Le clip reporter n'a pas de flux vidéo: {source.name}")
            if not media.audio:
                raise AssemblyError(
                    f"Le clip H3 {scene.id} n'a pas d'audio natif; l'assemblage s'arrête plutôt que "
                    "de masquer l'absence de voix reporter."
                )
            if media.duration < duration - (1 / timeline.fps):
                raise AssemblyError(
                    f"Clip H3 trop court ({media.duration:.3f}s) pour la scène "
                    f"{scene.id} ({duration:.3f}s)."
                )
            cmd.extend(["-i", str(source)])
            cmd.extend(["-loop", "1", "-framerate", str(timeline.fps), "-i", str(overlay)])
            graph = (
                "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,"
                "crop=1080:1920,setsar=1[base];"
                "[1:v]format=rgba[ov];"
                "[base][ov]overlay=0:0:eof_action=repeat:format=auto,"
                f"fps={timeline.fps},format=yuv420p,setsar=1[v];"
                f"[0:a:0]{_audio_filter(duration)}"
            )
        else:
            raise AssemblyError(f"Type de scène non pris en charge: {scene.type}")

        cmd.extend(
            [
                "-filter_complex",
                graph,
                "-map",
                "[v]",
                "-map",
                "[a]",
                "-frames:v",
                str(frames),
                "-t",
                f"{duration:.6f}",
                "-r",
                str(timeline.fps),
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "20",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                "160k",
                "-ar",
                "48000",
                "-ac",
                "2",
                "-video_track_timescale",
                "24000",
                "-movflags",
                "+faststart",
                str(destination),
            ]
        )
        try:
            run_ffmpeg(cmd, self.settings)
        except MediaToolError as exc:
            raise AssemblyError(f"Rendu de la scène {scene.id} impossible: {exc}") from exc
        if not destination.is_file() or destination.stat().st_size == 0:
            raise AssemblyError(f"ffmpeg n'a pas produit le segment {scene.id}.")
        return destination
