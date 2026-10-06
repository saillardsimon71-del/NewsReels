from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .comfy_workflow import validate_api_workflow
from .config import Settings
from .models import Segment


@dataclass(slots=True)
class H3Job:
    id: str
    title: str
    image_path: Path
    dialogue: str
    prompt: str
    duration_seconds: float = 10.125
    width: int = 768
    height: int = 1344
    fps: int = 24
    frames: int = 243
    steps: int = 8


class H3RendererError(RuntimeError):
    pass


@dataclass(slots=True)
class H3BatchResult:
    videos: dict[str, bytes]
    generation_seconds: float | None = None


def build_reporter_prompt(segment: Segment) -> str:
    action = segment.reporter_action.strip() or (
        "The reporter faces the camera and speaks calmly, with subtle natural facial expression "
        "and restrained, believable hand movement. Keep the shot a stable medium close-up."
    )
    spoken_text = segment.reporter_dialogue.strip()
    if not spoken_text:
        raise ValueError(f"Le dialogue du reporter {segment.id} est vide.")
    return "\n".join(
        (
            "Create one continuous, photorealistic French TV-news reporter shot based on the supplied first frame.",
            "Preserve exactly the reporter's identity, face, clothing, framing, lighting and location from the Agnes image.",
            "Keep facial features and anatomy stable throughout; hands must remain coherent and natural.",
            "Use restrained movement and a controlled, nearly locked camera; maintain temporal continuity.",
            "Do not duplicate people, morph faces, change the set, add graphics, or introduce unrelated action.",
            "No visible text, no logos, and no generated subtitles.",
            action,
            "The reporter has a clear, natural French voice (S1).",
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
                frames=243,
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
        "image_name": job.image_path.name,
        "image_base64": base64.b64encode(job.image_path.read_bytes()).decode("ascii"),
    }


def encode_batch(jobs: list[H3Job], workflow: dict[str, Any]) -> dict[str, Any]:
    if not 1 <= len(jobs) <= 6:
        raise H3RendererError(
            "NewsReel V1 accepte de un à six sujets par batch (trois par défaut)."
        )
    return {
        "contract_version": 1,
        "engine": "FastH3 8-Step V2 / MiniMax H3",
        "config": {
            "width": 768,
            "height": 1344,
            "fps": 24,
            "frames": 243,
            "duration_seconds": 10.125,
            "steps": 8,
            "native_audio": True,
            "video_sparse_attention": True,
            "modal_gpu": "L40S",
            "volume_name": "fasth3-models",
        },
        "workflow": workflow,
        "jobs": [encode_job(job) for job in jobs],
    }


class ModalH3Renderer:
    """One Modal call for the full three-reporter batch; never one call per clip."""

    def __init__(self, app_name: str, function_name: str, workflow_path: Path | None):
        self.app_name = app_name
        self.function_name = function_name
        self.workflow_path = workflow_path

    def render_batch(self, jobs: list[H3Job]) -> H3BatchResult:
        if self.workflow_path is None or not self.workflow_path.is_file():
            raise H3RendererError(
                "Workflow API FastH3 absent. Définissez NEWSREEL_H3_API_WORKFLOW vers l'export "
                "ComfyUI API de fasth3_push_test.py (le fichier reference/fasth3_push_test.py "
                "n'est pas présent dans ce checkout). Le worker refuse de substituer un workflow "
                "ou des poids non validés."
            )
        try:
            workflow = json.loads(self.workflow_path.read_text(encoding="utf-8"))
            validate_api_workflow(workflow)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise H3RendererError(
                f"Workflow FastH3 invalide, aucun appel Modal lancé: {exc}"
            ) from exc
        try:
            import modal
        except ImportError as exc:
            raise H3RendererError(
                "Le client Modal n'est pas installé. Lancez: pip install -r requirements-modal.txt"
            ) from exc
        payload = encode_batch(jobs, workflow)
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
