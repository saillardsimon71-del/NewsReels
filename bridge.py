from __future__ import annotations

import importlib.util
import json
import os
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field

from newsreel.assembler import FFmpegAssembler
from newsreel.comfy_workflow import validate_api_workflow
from newsreel.config import Settings
from newsreel.demo import run_offline_demo
from newsreel.h3_worker_contract import ModalH3Renderer, create_h3_jobs
from newsreel.models import Scenario
from newsreel.pipeline import NewsReelPipeline
from newsreel.run_store import RunStore

load_dotenv()


class StartRunRequest(BaseModel):
    query: str = Field(min_length=2, max_length=250)
    count: int = Field(default=3, ge=1, le=6)
    agnes_api_key: str | None = Field(default=None, repr=False)
    agnes_base_url: str | None = None
    agnes_text_model: str | None = None
    agnes_image_model: str | None = None
    agnes_image_size: str | None = None
    tts_voice: str | None = None


class RunActionRequest(BaseModel):
    run_id: str = Field(min_length=1, max_length=80)


def create_app(settings: Settings | None = None) -> FastAPI:
    runtime_settings = settings or Settings.from_env()
    output_root = runtime_settings.output_dir or runtime_settings.project_root / "output"
    store = RunStore(output_root)
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="newsreel-run")

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        try:
            yield
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    app = FastAPI(title="NewsReel local bridge", version="1.0.0", lifespan=lifespan)
    app.state.settings = runtime_settings
    app.state.store = store
    app.state.executor = executor

    @app.get("/", response_class=HTMLResponse)
    def index() -> FileResponse:
        html = runtime_settings.project_root / "web" / "index.html"
        if not html.is_file():
            raise HTTPException(status_code=500, detail="Interface web/index.html absente.")
        return FileResponse(html, media_type="text/html; charset=utf-8")

    @app.get("/health")
    def health() -> dict[str, Any]:
        ffmpeg = runtime_settings.resolved_ffmpeg()
        ffprobe = runtime_settings.resolved_ffprobe()
        return {
            "status": "ok",
            "service": "newsreel-local-bridge",
            "ffmpeg_available": bool(ffmpeg),
            "ffprobe_available": bool(ffprobe),
            "agnes_key_configured": bool(os.getenv("AGNES_API_KEY")),
            "h3_workflow_configured": bool(
                runtime_settings.h3_workflow_path and runtime_settings.h3_workflow_path.is_file()
            ),
            "modal_client_installed": importlib.util.find_spec("modal") is not None,
            "tts_provider_installed": importlib.util.find_spec("edge_tts") is not None,
            "output_dir": str(output_root),
        }

    @app.get("/config")
    def get_config() -> dict[str, Any]:
        return {
            "agnes_base_url": runtime_settings.agnes_base_url,
            "agnes_text_model": runtime_settings.agnes_text_model,
            "agnes_image_model": runtime_settings.agnes_image_model,
            "agnes_image_size": runtime_settings.agnes_image_size,
            "tts_voice": runtime_settings.tts_voice,
            "output_dir": str(output_root),
            "width": runtime_settings.width,
            "height": runtime_settings.height,
            "fps": runtime_settings.fps,
            "default_subject_count": 3,
        }

    @app.post("/runs", status_code=202)
    def start_run(body: StartRunRequest) -> dict[str, Any]:
        api_key = (body.agnes_api_key or os.getenv("AGNES_API_KEY", "")).strip()
        if not api_key:
            raise HTTPException(
                status_code=400,
                detail="Clé Agnes manquante. Saisissez-la dans le panneau Agnes ou définissez AGNES_API_KEY.",
            )
        if not runtime_settings.resolved_ffmpeg() or not runtime_settings.resolved_ffprobe():
            raise HTTPException(
                status_code=409,
                detail="FFmpeg et ffprobe doivent être installés avant tout appel Agnes/Modal.",
            )
        if not (runtime_settings.h3_workflow_path and runtime_settings.h3_workflow_path.is_file()):
            raise HTTPException(
                status_code=409,
                detail=(
                    "Workflow API FastH3 validé absent. Définissez NEWSREEL_H3_API_WORKFLOW; "
                    "aucune génération Agnes/Modal ne sera lancée sans ce fichier."
                ),
            )
        try:
            workflow = json.loads(runtime_settings.h3_workflow_path.read_text(encoding="utf-8"))
            validate_api_workflow(workflow)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise HTTPException(
                status_code=409,
                detail=f"Workflow FastH3 invalide; aucun appel Agnes/Modal lancé: {exc}",
            ) from exc
        if importlib.util.find_spec("modal") is None:
            raise HTTPException(
                status_code=409,
                detail="Client Modal absent. Installez requirements-modal.txt avant tout appel Agnes.",
            )
        if importlib.util.find_spec("edge_tts") is None:
            raise HTTPException(
                status_code=409,
                detail="Provider TTS absent. Installez requirements.txt avant tout appel Agnes.",
            )
        per_run_settings = replace(
            runtime_settings,
            agnes_base_url=(body.agnes_base_url or runtime_settings.agnes_base_url).rstrip("/"),
            agnes_text_model=body.agnes_text_model or runtime_settings.agnes_text_model,
            agnes_image_model=body.agnes_image_model or runtime_settings.agnes_image_model,
            agnes_image_size=body.agnes_image_size or runtime_settings.agnes_image_size,
            tts_voice=body.tts_voice or runtime_settings.tts_voice,
        )
        run_id, run_dir = store.create()
        # The secret is only captured in the worker closure and never enters the manifest.
        executor.submit(_run_live, per_run_settings, store, run_id, body.query, body.count, api_key)
        return {
            "run_id": run_id,
            "status": "queued",
            "output_path": str(run_dir),
            "message": "Run NewsReel démarré.",
        }

    @app.post("/demo", status_code=202)
    def start_demo() -> dict[str, Any]:
        run_id, run_dir = store.create()
        executor.submit(_run_demo, runtime_settings, store, run_id)
        return {
            "run_id": run_id,
            "status": "queued",
            "output_path": str(run_dir),
            "message": "Démo synthétique hors-ligne démarrée; aucune requête Agnes/Modal.",
        }

    @app.post("/render-h3-batch", status_code=202)
    def render_h3_batch(body: RunActionRequest) -> dict[str, Any]:
        try:
            run_dir = store.path(body.run_id)
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        scenario_path = run_dir / "scenario.json"
        if not scenario_path.is_file():
            raise HTTPException(status_code=409, detail="scenario.json absent pour ce run.")
        try:
            scenario = Scenario.from_mapping(json.loads(scenario_path.read_text(encoding="utf-8")))
        except (ValueError, OSError) as exc:
            raise HTTPException(status_code=422, detail=f"Scénario invalide: {exc}") from exc
        images = [
            run_dir / "images" / f"reporter-{index}.png" for index in range(len(scenario.segments))
        ]
        missing = [str(path) for path in images if not path.is_file()]
        if missing:
            raise HTTPException(status_code=409, detail=f"Images reporter manquantes: {missing}")
        executor.submit(_render_h3_run, runtime_settings, store, body.run_id, scenario, images)
        return {
            "run_id": body.run_id,
            "status": "queued",
            "message": "Batch H3 soumis une seule fois.",
        }

    @app.post("/assemble", status_code=202)
    def assemble_run(body: RunActionRequest) -> dict[str, Any]:
        try:
            run_dir = store.path(body.run_id)
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        timeline_path = run_dir / "timeline.json"
        if not timeline_path.is_file():
            raise HTTPException(status_code=409, detail="timeline.json absent pour ce run.")
        executor.submit(_assemble_run, runtime_settings, store, body.run_id)
        return {"run_id": body.run_id, "status": "queued", "message": "Montage local démarré."}

    @app.get("/run/{run_id}")
    @app.get("/runs/{run_id}")
    def get_run(run_id: str) -> dict[str, Any]:
        try:
            manifest = store.read_manifest(run_id)
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        run_dir = store.path(run_id)
        timeline_path = run_dir / "timeline.json"
        if timeline_path.is_file():
            manifest["timeline"] = json.loads(timeline_path.read_text(encoding="utf-8"))
        if manifest.get("final_file"):
            manifest["final_url"] = f"/output/{run_id}/newsreel_final.mp4"
        return manifest

    @app.get("/output/{run_id}/{asset_path:path}")
    def output_file(run_id: str, asset_path: str, download: bool = False) -> FileResponse:
        try:
            run_dir = store.path(run_id)
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=404, detail="Run introuvable.") from exc
        requested = (run_dir / Path(asset_path)).resolve()
        try:
            requested.relative_to(run_dir)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="Chemin invalide.") from exc
        if not requested.is_file():
            raise HTTPException(status_code=404, detail="Fichier introuvable.")
        if download:
            return FileResponse(requested, filename=requested.name)
        import mimetypes

        media_type = mimetypes.guess_type(requested.name)[0] or "application/octet-stream"
        return FileResponse(requested, media_type=media_type)

    return app


def _run_live(
    settings: Settings,
    store: RunStore,
    run_id: str,
    query: str,
    count: int,
    api_key: str,
) -> None:
    try:
        NewsReelPipeline(settings, store=store).run_live(run_id, query, count, api_key)
    except Exception:
        # The pipeline records the redacted error message and failed stage in run_manifest.json.
        return


def _run_demo(settings: Settings, store: RunStore, run_id: str) -> None:
    try:
        run_offline_demo(settings, run_id=run_id, store=store)
    except Exception:
        return


def _render_h3_run(
    settings: Settings,
    store: RunStore,
    run_id: str,
    scenario: Scenario,
    images: list[Path],
) -> None:
    run_dir = store.path(run_id)
    store.stage(run_id, "h3", "running", clip_count=len(images))
    try:
        jobs = create_h3_jobs(scenario.segments, images, settings)
        result = ModalH3Renderer(
            settings.modal_app_name, settings.modal_function_name, settings.h3_workflow_path
        ).render_batch(jobs)
        for index, job in enumerate(jobs):
            path = run_dir / "h3" / f"reporter-{index}.mp4"
            path.write_bytes(result.videos[job.id])
            store.register_file(run_id, path)
        store.stage(
            run_id,
            "h3",
            "succeeded",
            clip_count=len(jobs),
            generation_seconds=result.generation_seconds,
        )
    except Exception as exc:
        store.stage(run_id, "h3", "failed", message=str(exc))
        store.add_error(run_id, str(exc), "h3")


def _assemble_run(settings: Settings, store: RunStore, run_id: str) -> None:
    run_dir = store.path(run_id)
    store.stage(run_id, "assembly", "running")
    try:
        result = FFmpegAssembler(settings).assemble(run_dir / "timeline.json", run_dir)
        path = Path(result["path"])
        store.register_file(run_id, path)
        for relative in result["segment_files"]:
            store.register_file(run_id, run_dir / relative)
        store.stage(
            run_id,
            "assembly",
            "succeeded",
            final_duration_seconds=result["duration_seconds"],
            resolution=f"{result['width']}x{result['height']}",
            fps=result["fps"],
            audio=result["audio"],
        )
        store.update(
            run_id,
            status="complete",
            final_file=path.name,
            final_duration_seconds=result["duration_seconds"],
        )
    except Exception as exc:
        store.stage(run_id, "assembly", "failed", message=str(exc))
        store.add_error(run_id, str(exc), "assembly")


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("bridge:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")), reload=False)
