from __future__ import annotations

import base64
import re
import secrets
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import Settings
from .h3_workflow import (
    H3_DURATION_SECONDS,
    H3_FPS,
    H3_FRAMES,
    H3_HEIGHT,
    H3_STEPS,
    H3_WIDTH,
    h3_contract_config,
)
from .models import Segment


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


def build_reporter_prompt(segment: Segment) -> str:
    spoken_text = segment.reporter_dialogue.strip()
    if not spoken_text:
        raise ValueError(f"Le dialogue du reporter {segment.id} est vide.")

    context_action = " ".join(segment.reporter_action.split())
    if context_action:
        action_instruction = (
            "Subtle contextual action from Agnes: "
            f"{context_action} Perform it once, gently, and only if it remains natural "
            "for the supplied frame."
        )
    else:
        action_instruction = (
            "No additional action is needed: the reporter may make one small, natural "
            "facial expression or restrained hand gesture while speaking."
        )

    return "\n".join(
        (
            "Create one continuous, photorealistic French TV-news reporter shot from the supplied first frame, lasting 10.125 seconds.",
            "Preserve exactly the reporter's identity, face, hairstyle, clothing, framing, lighting, and location from the Agnes image.",
            "Keep anatomy and facial features stable from frame to frame; hands and fingers must remain coherent and natural.",
            "Use measured, believable body movement and a controlled, nearly locked camera; preserve temporal continuity.",
            "Do not morph or duplicate people or body parts, change the set, add cuts, or introduce unrelated action.",
            "Do not add visible text, lower thirds, logos, graphics, or subtitles.",
            action_instruction,
            "The reporter has a clear natural French voice (S1).",
            f"<d>[French] {spoken_text}</d>",
        )
    )


def create_h3_jobs(segments: list[Segment], images: list[Path], settings: Settings) -> list[H3Job]:
    if len(segments) != len(images):
        raise ValueError("Une image Agnes est requise pour chaque reporter H3.")
    jobs = []
    for index, (segment, image) in enumerate(zip(segments, images, strict=True)):
        if not image.is_file():
            raise FileNotFoundError(f"Image H3 introuvable: {image}")
        jobs.append(
            H3Job(
                id=f"reporter-{index}",
                title=segment.title,
                image_path=image,
                dialogue=segment.reporter_dialogue,
                prompt=build_reporter_prompt(segment),
                duration_seconds=settings.h3_duration_seconds,
                width=settings.h3_width,
                height=settings.h3_height,
                fps=settings.h3_fps,
                frames=H3_FRAMES,
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
    if not 1 <= len(jobs) <= 6:
        raise H3RendererError(
            "NewsReel V1 accepte de un à six sujets par batch (trois par défaut)."
        )
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", run_id):
        raise H3RendererError("Identifiant de run invalide pour le batch FastH3.")
    return {
        "contract_version": 1,
        "run_id": run_id,
        "engine": "FastH3 8-Step V2 / MiniMax H3",
        "config": h3_contract_config(),
        "jobs": [encode_job(job) for job in jobs],
    }


class ModalH3Renderer:
    """One Modal call for the full reporter batch; never one call per clip."""

    def __init__(self, app_name: str, function_name: str):
        self.app_name = app_name
        self.function_name = function_name

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
