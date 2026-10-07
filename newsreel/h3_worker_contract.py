from __future__ import annotations

import base64
import re
import secrets
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import Settings
from .creative import (
    DEFAULT_DIRECTOR,
    DEFAULT_PALETTE,
    build_host_video_prompt,
    build_reporter_video_prompt,
    silent_tail_seconds,
)
from .h3_workflow import (
    H3_DURATION_SECONDS,
    H3_FPS,
    H3_FRAMES,
    H3_HEIGHT,
    H3_STEPS,
    H3_WIDTH,
    h3_contract_config,
    h3_frames_for_dialogue,
)
from .models import Scenario, Segment


@dataclass(slots=True)
class H3Job:
    id: str
    title: str
    image_path: Path
    dialogue: str
    prompt: str
    duration_seconds: float = H3_DURATION_SECONDS
    width: int = H3_WIDTH
    height: int = H3_HEIGHT
    fps: int = H3_FPS
    frames: int = H3_FRAMES
    steps: int = H3_STEPS
    seed: int = field(default_factory=lambda: secrets.randbelow(2**53))


class H3RendererError(RuntimeError):
    pass


@dataclass(slots=True)
class H3BatchResult:
    videos: dict[str, bytes]
    generation_seconds: float | None = None


def build_host_prompt(
    scenario: Scenario,
    segment: Segment,
    director: str = DEFAULT_DIRECTOR,
    palette: str = DEFAULT_PALETTE,
    duration_seconds: float | None = None,
) -> str:
    spoken_text = segment.host_dialogue.strip()
    if not spoken_text:
        raise ValueError(f"Le dialogue host {segment.id} est vide.")
    intensity = scenario.creative.get("intensity", "strong")
    creative = build_host_video_prompt(
        scenario.to_dict(),
        segment.to_dict(),
        director,
        palette,
        duration_seconds if duration_seconds is not None else h3_frames_for_dialogue(spoken_text) / H3_FPS,
        intensity,
    )
    return creative


def build_reporter_prompt(
    segment: Segment,
    director: str = DEFAULT_DIRECTOR,
    palette: str = DEFAULT_PALETTE,
    intensity: str = "strong",
    duration_seconds: float | None = None,
) -> str:
    spoken_text = segment.reporter_dialogue.strip()
    if not spoken_text:
        raise ValueError(f"Le dialogue du reporter {segment.id} est vide.")
    creative = build_reporter_video_prompt(
        segment.to_dict(),
        director,
        palette,
        duration_seconds if duration_seconds is not None else h3_frames_for_dialogue(spoken_text, visual_seconds=5, tail_seconds=silent_tail_seconds(segment.to_dict())) / H3_FPS,
        intensity,
    )
    return creative


def create_h3_jobs(
    scenario: Scenario,
    host_image: Path,
    reporter_images: list[Path],
    settings: Settings,
    director: str | None = None,
    palette: str | None = None,
) -> list[H3Job]:
    if len(scenario.segments) != len(reporter_images):
        raise ValueError("Une image Agnes est requise pour chaque reporter H3.")
    if not host_image.is_file():
        raise FileNotFoundError(f"Image host H3 introuvable: {host_image}")
    selected_director = director or scenario.creative.get("director") or DEFAULT_DIRECTOR
    selected_palette = palette or scenario.creative.get("palette") or DEFAULT_PALETTE

    jobs: list[H3Job] = []
    for index, (segment, reporter_image) in enumerate(
        zip(scenario.segments, reporter_images, strict=True)
    ):
        if not reporter_image.is_file():
            raise FileNotFoundError(f"Image H3 introuvable: {reporter_image}")
        host_frames = h3_frames_for_dialogue(segment.host_dialogue)
        reporter_frames = h3_frames_for_dialogue(segment.reporter_dialogue, visual_seconds=5, tail_seconds=silent_tail_seconds(segment.to_dict()))
        jobs.append(
            H3Job(
                id=f"host-{index}",
                title=segment.title,
                image_path=host_image,
                dialogue=segment.host_dialogue,
                prompt=build_host_prompt(
                    scenario, segment, selected_director, selected_palette, host_frames / H3_FPS
                ),
                duration_seconds=host_frames / H3_FPS,
                width=settings.h3_width,
                height=settings.h3_height,
                fps=settings.h3_fps,
                frames=host_frames,
                steps=settings.h3_steps,
            )
        )
        jobs.append(
            H3Job(
                id=f"reporter-{index}",
                title=segment.title,
                image_path=reporter_image,
                dialogue=segment.reporter_dialogue,
                prompt=build_reporter_prompt(
                    segment,
                    selected_director,
                    selected_palette,
                    scenario.creative.get("intensity", "strong"),
                    reporter_frames / H3_FPS,
                ),
                duration_seconds=reporter_frames / H3_FPS,
                width=settings.h3_width,
                height=settings.h3_height,
                fps=settings.h3_fps,
                frames=reporter_frames,
                steps=settings.h3_steps,
            )
        )
    return jobs


def encode_job(job: H3Job) -> dict[str, Any]:
    return {
        "id": job.id,
        "title": job.title,
        "dialogue": job.dialogue,
        "prompt": job.prompt,
        "duration_seconds": job.duration_seconds,
        "width": job.width,
        "height": job.height,
        "fps": job.fps,
        "frames": job.frames,
        "steps": job.steps,
        "seed": job.seed,
        "image_name": job.image_path.name,
        "image_base64": base64.b64encode(job.image_path.read_bytes()).decode("ascii"),
    }


def encode_batch(jobs: list[H3Job], run_id: str) -> dict[str, Any]:
    if not 1 <= len(jobs) <= 14:
        raise H3RendererError("NewsReel accepte de un à quatorze clips par batch FastH3.")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", run_id):
        raise H3RendererError("Identifiant de run invalide pour le batch FastH3.")
    return {
        "contract_version": 2,
        "run_id": run_id,
        "engine": "FastH3 8-Step V2 / MiniMax H3",
        "config": h3_contract_config(),
        "jobs": [encode_job(job) for job in jobs],
    }


class ModalH3Renderer:
    """One Modal call for all host + reporter clips in a JT."""

    def __init__(self, app_name: str, function_name: str):
        self.app_name = app_name
        self.function_name = function_name

    def check_available(self) -> None:
        """Resolve the deployed Modal function without allocating a GPU container."""
        try:
            import modal
        except ImportError as exc:
            raise H3RendererError(
                "Le client Modal n'est pas installé. Lancez: pip install -r requirements-modal.txt"
            ) from exc
        try:
            remote = modal.Function.from_name(self.app_name, self.function_name)
            try:
                remote.info(refresh=True)
            except TypeError:
                try:
                    remote.info()
                except Exception:
                    remote.hydrate()
            except AttributeError:
                remote.hydrate()
        except Exception as exc:
            raise H3RendererError(
                f"Déploiement Modal introuvable ou inaccessible: "
                f"{self.app_name}.{self.function_name}: {exc}"
            ) from exc

    def render_batch(self, jobs: list[H3Job], run_id: str | None = None) -> H3BatchResult:
        payload = encode_batch(jobs, run_id or uuid.uuid4().hex)
        try:
            import modal
        except ImportError as exc:
            raise H3RendererError(
                "Le client Modal n'est pas installé. Lancez: pip install -r requirements-modal.txt"
            ) from exc
        try:
            remote = modal.Function.from_name(self.app_name, self.function_name)
            result = remote.remote(payload)
        except Exception as exc:
            raise H3RendererError(f"Échec de l'appel Modal batch FastH3: {exc}") from exc
        if not isinstance(result, dict) or not isinstance(result.get("videos"), dict):
            raise H3RendererError("Réponse Modal invalide: fichiers MP4 batch absents.")
        files: dict[str, bytes] = {}
        for job in jobs:
            item = result["videos"].get(job.id)
            if not isinstance(item, dict) or not isinstance(item.get("data_base64"), str):
                raise H3RendererError(f"Le batch Modal n'a pas retourné {job.id}.")
            try:
                files[job.id] = base64.b64decode(item["data_base64"], validate=True)
            except ValueError as exc:
                raise H3RendererError(f"MP4 base64 invalide pour {job.id}.") from exc
            if not files[job.id]:
                raise H3RendererError(f"MP4 vide retourné par Modal pour {job.id}.")
        return H3BatchResult(
            videos=files,
            generation_seconds=(
                float(result["h3_generation_seconds"])
                if isinstance(result.get("h3_generation_seconds"), (int, float))
                else None
            ),
        )
