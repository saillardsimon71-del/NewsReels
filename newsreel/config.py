from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path


def _resolve_path(value: str | Path | None, base: Path) -> Path | None:
    if value is None or str(value).strip() == "":
        return None
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (base / path).resolve()


@dataclass(frozen=True, slots=True)
class Settings:
    """Runtime configuration. Secrets are deliberately not persisted here."""

    project_root: Path = field(default_factory=lambda: Path(__file__).resolve().parents[1])
    output_dir: Path | None = None
    ffmpeg_path: str | None = None
    ffprobe_path: str | None = None
    tts_voice: str = "fr-FR-DeniseNeural"
    agnes_base_url: str = "https://apihub.agnes-ai.com/v1"
    agnes_text_model: str = "agnes-2.5-flash"
    agnes_image_model: str = "agnes-image-2.1-flash"
    agnes_image_size: str = "768x1344"
    agnes_timeout_seconds: int = 180
    modal_app_name: str = "newsreel-fasth3"
    modal_function_name: str = "render_h3_batch"
    h3_workflow_path: Path | None = None
    width: int = 1080
    height: int = 1920
    fps: int = 24
    h3_width: int = 768
    h3_height: int = 1344
    h3_fps: int = 24
    h3_duration_seconds: float = 10.125
    h3_steps: int = 8
    max_news_items: int = 12

    def __post_init__(self) -> None:
        root = Path(self.project_root).expanduser().resolve()
        object.__setattr__(self, "project_root", root)
        if self.output_dir is None:
            object.__setattr__(self, "output_dir", root / "output")
        else:
            object.__setattr__(self, "output_dir", _resolve_path(self.output_dir, root))
        if self.h3_workflow_path is not None:
            object.__setattr__(self, "h3_workflow_path", _resolve_path(self.h3_workflow_path, root))
        if self.width < 1 or self.height < 1 or self.fps < 1:
            raise ValueError("La résolution et le framerate de sortie doivent être positifs.")
        if (self.h3_width, self.h3_height, self.h3_fps, self.h3_steps) != (
            768,
            1344,
            24,
            8,
        ) or self.h3_duration_seconds != 10.125:
            raise ValueError(
                "Le contrat validé FastH3 V2 est fixé à 768x1344, 24 fps, 243 frames / "
                "10,125 s et 8 étapes."
            )

    @classmethod
    def from_env(cls, project_root: Path | None = None) -> Settings:
        root = (project_root or Path(__file__).resolve().parents[1]).expanduser().resolve()
        output = os.getenv("NEWSREEL_OUTPUT_DIR")
        workflow = os.getenv("NEWSREEL_H3_API_WORKFLOW")
        return cls(
            project_root=root,
            output_dir=_resolve_path(output, root) if output else root / "output",
            ffmpeg_path=os.getenv("NEWSREEL_FFMPEG"),
            ffprobe_path=os.getenv("NEWSREEL_FFPROBE"),
            tts_voice=os.getenv("NEWSREEL_TTS_VOICE", "fr-FR-DeniseNeural"),
            agnes_base_url=os.getenv("AGNES_API_BASE_URL", "https://apihub.agnes-ai.com/v1").rstrip(
                "/"
            ),
            agnes_text_model=os.getenv("AGNES_TEXT_MODEL", "agnes-2.5-flash"),
            agnes_image_model=os.getenv("AGNES_IMAGE_MODEL", "agnes-image-2.1-flash"),
            agnes_image_size=os.getenv("AGNES_IMAGE_SIZE", "768x1344"),
            agnes_timeout_seconds=int(os.getenv("AGNES_TIMEOUT_SECONDS", "180")),
            modal_app_name=os.getenv("NEWSREEL_MODAL_APP", "newsreel-fasth3"),
            modal_function_name=os.getenv("NEWSREEL_MODAL_FUNCTION", "render_h3_batch"),
            h3_workflow_path=_resolve_path(workflow, root) if workflow else None,
        )

    def resolved_ffmpeg(self) -> str | None:
        configured = self.ffmpeg_path
        if configured:
            path = Path(configured).expanduser()
            if path.is_file():
                return str(path.resolve())
            found = shutil.which(configured)
            return found
        return shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")

    def resolved_ffprobe(self) -> str | None:
        configured = self.ffprobe_path
        if configured:
            path = Path(configured).expanduser()
            if path.is_file():
                return str(path.resolve())
            return shutil.which(configured)
        found = shutil.which("ffprobe") or shutil.which("ffprobe.exe")
        if found:
            return found
        ffmpeg = self.resolved_ffmpeg()
        if ffmpeg:
            sibling_name = "ffprobe.exe" if Path(ffmpeg).suffix.lower() == ".exe" else "ffprobe"
            sibling = Path(ffmpeg).with_name(sibling_name)
            if sibling.is_file():
                return str(sibling.resolve())
        return None
