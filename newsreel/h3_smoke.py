from __future__ import annotations

import argparse
import hashlib
import json
import time
import uuid
from dataclasses import asdict
from pathlib import Path

from .config import Settings
from .h3_worker_contract import H3Job, ModalH3Renderer
from .h3_workflow import H3_FPS, h3_contract_config, h3_frames_for_dialogue
from .media import probe_media

DIALOGUE = "Bonsoir à tous, voici les nouvelles du jour."
PROMPT = """For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.

integrated_multimodal_description: [Shot 1] Preserve the reporter, clothing, colors, lighting and environment from <Picture 1>. The camera remains in a stable medium close-up from beginning to end. The reporter's head and shoulders fill the frame and the face remains large, sharp and clearly visible throughout the shot. The reporter looks directly into the camera. The reporter has a clear, natural French broadcast voice with calm pacing and precise articulation (S1) and says: <d>[French] Bonsoir à tous, voici les nouvelles du jour.</d> After finishing the sentence, the reporter remains calmly facing the camera.

overall_soundscape: Quiet natural room ambience with subtle environmental sound.

non_diegetic_music: N/A"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Un clip diagnostic FastH3 sans Agnes.")
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--seed", type=int, default=424242424242)
    args = parser.parse_args()
    if not args.image.is_file():
        parser.error(f"Image introuvable: {args.image}")
    settings = Settings.from_env()
    run_id = f"h3-diagnostic-{uuid.uuid4().hex}"
    root = args.output_dir or settings.output_dir
    run_dir = root / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    frames = h3_frames_for_dialogue(DIALOGUE)
    job = H3Job(
        id="diagnostic-french",
        title="Diagnostic français",
        image_path=args.image.resolve(),
        dialogue=DIALOGUE,
        prompt=PROMPT,
        seed=args.seed,
        frames=frames,
        duration_seconds=frames / H3_FPS,
    )
    metadata = {
        "run_id": run_id,
        "status": "running",
        "image_sha256": hashlib.sha256(args.image.read_bytes()).hexdigest(),
        "job": {**asdict(job), "image_path": str(job.image_path)},
        "contract": h3_contract_config(),
    }
    report = run_dir / "smoke.json"
    report.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Un rendu: {frames} frames, {job.duration_seconds:.6f} s, seed {job.seed}", flush=True)
    started = time.perf_counter()
    renderer = ModalH3Renderer(settings.modal_app_name, settings.modal_function_name)
    try:
        result = renderer.render_batch([job], run_id=run_id)
        clip = run_dir / "diagnostic-french.mp4"
        clip.write_bytes(result.videos[job.id])
        info = probe_media(clip, settings)
        if not info.video or not info.audio:
            raise RuntimeError("Le clip diagnostic ne contient pas vidéo et audio natif.")
        metadata.update(
            status="rendered",
            clip=str(clip.resolve()),
            generation_seconds=result.generation_seconds,
            wall_seconds=round(time.perf_counter() - started, 3),
            actual_duration_seconds=info.duration,
            width=info.width,
            height=info.height,
            fps=info.fps,
        )
    except Exception as exc:
        metadata.update(status="failed", error=str(exc), wall_seconds=round(time.perf_counter() - started, 3))
        raise
    finally:
        report.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Clip: {clip.resolve()}", flush=True)
    print(f"Mesures: {report.resolve()}", flush=True)


if __name__ == "__main__":
    main()
