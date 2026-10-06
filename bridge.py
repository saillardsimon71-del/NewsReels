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

from newsreel.config import Settings
from newsreel.creative import (
    DEFAULT_DIRECTOR,
    DEFAULT_INTENSITY,
    DEFAULT_PALETTE,
    DIRECTORS,
    INTENSITY_LEVELS,
    PALETTES,
    creative_catalog,
)
from newsreel.demo import run_offline_demo
from newsreel.h3_worker_contract import ModalH3Renderer
from newsreel.h3_workflow import h3_contract_config
from newsreel.pipeline import NewsReelPipeline
from newsreel.run_store import RunStore

load_dotenv()


class StartRunRequest(BaseModel):
    query: str = Field(min_length=2, max_length=250)
    count: int = Field(default=3, ge=1, le=7)
    director: str = DEFAULT_DIRECTOR
    palette: str = DEFAULT_PALETTE
    intensity: str = DEFAULT_INTENSITY
    agnes_api_key: str | None = Field(default=None, repr=False)
    agnes_base_url: str | None = None
    agnes_text_model: str | None = None
    agnes_image_model: str | None = None
    agnes_image_size: str | None = None
    agnes_image_ratio: str | None = None


class RunActionRequest(BaseModel):
    run_id: str = Field(min_length=1, max_length=80)


def _validate_creative(body: StartRunRequest) -> None:
    if body.director not in DIRECTORS:
        raise HTTPException(status_code=422, detail=f"Réalisateur inconnu: {body.director}")
    if body.palette not in PALETTES:
        raise HTTPException(status_code=422, detail=f"Palette inconnue: {body.palette}")
    if body.intensity not in INTENSITY_LEVELS:
        raise HTTPException(status_code=422, detail=f"Intensité inconnue: {body.intensity}")


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

    app = FastAPI(title="NewsReel local bridge", version="2.0.0", lifespan=lifespan)
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
            "version": "2",
            "ffmpeg_available": bool(ffmpeg),
            "ffprobe_available": bool(ffprobe),
            "agnes_key_configured": bool(os.getenv("AGNES_API_KEY")),
            "h3_graph_built_in": True,
            "modal_client_installed": importlib.util.find_spec("modal") is not None,
            "output_dir": str(output_root),
        }

    @app.get("/config")
    def get_config() -> dict[str, Any]:
        return {
            "agnes_base_url": runtime_settings.agnes_base_url,
            "agnes_text_model": runtime_settings.agnes_text_model,
            "agnes_image_model": runtime_settings.agnes_image_model,
            "agnes_image_size": runtime_settings.agnes_image_size,
            "agnes_image_ratio": runtime_settings.agnes_image_ratio,
            "output_dir": str(output_root),
            "width": runtime_settings.width,
            "height": runtime_settings.height,
            "fps": runtime_settings.fps,
            "default_subject_count": 3,
            "creative": creative_catalog(),
            "full_h3": True,
            "h3_clips_per_subject": 2,
            "h3": h3_contract_config(),
        }

    @app.get("/runs")
    def list_runs(limit: int = 20) -> dict[str, Any]:
        return {"runs": store.list_runs(limit)}

    @app.post("/runs", status_code=202)
    def start_run(body: StartRunRequest) -> dict[str, Any]:
        _validate_creative(body)
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
        if importlib.util.find_spec("modal") is None:
            raise HTTPException(
                status_code=409,
                detail="Client Modal absent. Installez requirements-modal.txt avant tout appel Agnes.",
            )
        try:
            ModalH3Renderer(
                runtime_settings.modal_app_name,
                runtime_settings.modal_function_name,
            ).check_available()
        except Exception as exc:
            raise HTTPException(
                status_code=409,
                detail=f"Worker Modal indisponible avant génération Agnes: {exc}",
            ) from exc
        per_run_settings = replace(
            runtime_settings,
            agnes_base_url=(body.agnes_base_url or runtime_settings.agnes_base_url).rstrip("/"),
            agnes_text_model=body.agnes_text_model or runtime_settings.agnes_text_model,
            agnes_image_model=body.agnes_image_model or runtime_settings.agnes_image_model,
            agnes_image_size=body.agnes_image_size or runtime_settings.agnes_image_size,
            agnes_image_ratio=body.agnes_image_ratio or runtime_settings.agnes_image_ratio,
        )
        run_id, run_dir = store.create()
        executor.submit(
            _run_live,
            per_run_settings,
            store,
            run_id,
            body.query,
            body.count,
            api_key,
            body.director,
            body.palette,
            body.intensity,
        )
        return {
            "run_id": run_id,
            "status": "queued",
            "output_path": str(run_dir),
            "message": "Run NewsReel V2 démarré.",
        }

    @app.post("/demo", status_code=202)
    def start_demo() -> dict[str, Any]:
        run_id, run_dir = store.create()
        executor.submit(_run_demo, runtime_settings, store, run_id)
        return {
            "run_id": run_id,
            "status": "queued",
            "output_path": str(run_dir),
            "message": "Démo synthétique full-H3 hors-ligne démarrée; aucune requête Agnes/Modal.",
        }

    @app.post("/resume", status_code=202)
    def resume_run(body: RunActionRequest) -> dict[str, Any]:
        try:
            store.path(body.run_id)
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        executor.submit(_resume_run, runtime_settings, store, body.run_id)
        return {
            "run_id": body.run_id,
            "status": "queued",
            "message": "Reprise automatique du run soumise.",
        }

    @app.post("/render-h3-batch", status_code=202)
    def render_h3_batch(body: RunActionRequest) -> dict[str, Any]:
        try:
            store.path(body.run_id)
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        executor.submit(_rerender_h3_run, runtime_settings, store, body.run_id)
        return {
            "run_id": body.run_id,
            "status": "queued",
            "message": "Relance full-H3 puis remontage final soumis.",
        }

    @app.post("/assemble", status_code=202)
    def assemble_run(body: RunActionRequest) -> dict[str, Any]:
        try:
            store.path(body.run_id)
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        executor.submit(_reassemble_run, runtime_settings, store, body.run_id)
        return {
            "run_id": body.run_id,
            "status": "queued",
            "message": "Timeline reconstruite depuis les clips H3 puis montage local démarré.",
        }

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
    director: str,
    palette: str,
    intensity: str,
) -> None:
    try:
        NewsReelPipeline(settings, store=store).run_live(
            run_id,
            query,
            count,
            api_key,
            director=director,
            palette=palette,
            intensity=intensity,
        )
    except Exception:
        return


def _run_demo(settings: Settings, store: RunStore, run_id: str) -> None:
    try:
        run_offline_demo(settings, run_id=run_id, store=store)
    except Exception:
        return


def _resume_run(
    settings: Settings,
    store: RunStore,
    run_id: str,
) -> None:
    try:
        NewsReelPipeline(settings, store=store).resume(run_id)
    except Exception as exc:
        try:
            store.add_error(run_id, str(exc), "resume")
        except Exception:
            pass


def _rerender_h3_run(
    settings: Settings,
    store: RunStore,
    run_id: str,
) -> None:
    try:
        NewsReelPipeline(settings, store=store).rerender_h3(run_id)
    except Exception:
        return


def _reassemble_run(
    settings: Settings,
    store: RunStore,
    run_id: str,
) -> None:
    try:
        NewsReelPipeline(settings, store=store).reassemble(run_id)
    except Exception:
        return


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "bridge:app",
        host=os.getenv("NEWSREEL_HOST", "127.0.0.1"),
        port=int(os.getenv("NEWSREEL_PORT", os.getenv("PORT", "8000"))),
        reload=False,
    )
