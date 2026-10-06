from __future__ import annotations

import time
from pathlib import Path
from typing import Protocol

from .agnes import AgnesClient
from .assembler import FFmpegAssembler
from .config import Settings
from .creative import (
    DEFAULT_DIRECTOR,
    DEFAULT_INTENSITY,
    DEFAULT_PALETTE,
    build_host_image_prompt,
    build_reporter_image_prompt,
)
from .h3_worker_contract import H3BatchResult, H3Job, ModalH3Renderer, create_h3_jobs
from .media import probe_media
from .models import NewsItem, Scenario
from .news import GoogleNewsRSS
from .run_store import RunStore
from .timeline import build_timeline


class H3Renderer(Protocol):
    def render_batch(self, jobs: list[H3Job], run_id: str | None = None) -> H3BatchResult: ...


class NewsReelPipeline:
    """One production run, with independent run-scoped assets and manifest progress."""

    def __init__(
        self,
        settings: Settings,
        store: RunStore | None = None,
        news_provider: GoogleNewsRSS | None = None,
        h3_renderer: H3Renderer | None = None,
        assembler: FFmpegAssembler | None = None,
    ):
        self.settings = settings
        self.store = store or RunStore(settings.output_dir or settings.project_root / "output")
        self.news_provider = news_provider or GoogleNewsRSS()
        self.h3_renderer = h3_renderer or ModalH3Renderer(
            settings.modal_app_name, settings.modal_function_name
        )
        self.assembler = assembler or FFmpegAssembler(settings)

    def run_live(
        self,
        run_id: str,
        query: str,
        count: int,
        agnes_api_key: str,
        director: str = DEFAULT_DIRECTOR,
        palette: str = DEFAULT_PALETTE,
        intensity: str = DEFAULT_INTENSITY,
    ) -> dict[str, object]:
        run_dir = self.store.path(run_id)
        active_stage = "news"
        try:
            self.store.update(
                run_id,
                status="running",
                query=query,
                requested_subject_count=count,
                creative={
                    "director": director,
                    "palette": palette,
                    "intensity": intensity,
                },
            )
            self.store.stage(
                run_id, active_stage, "running", message="Récupération du flux Google News"
            )
            news = self.news_provider.fetch(
                query, limit=min(self.settings.max_news_items, max(count * 3, count))
            )
            news_path = run_dir / "news.json"
            RunStore.atomic_write_json(news_path, [item.to_dict() for item in news])
            self.store.register_file(run_id, news_path)
            self.store.stage(run_id, active_stage, "succeeded", article_count=len(news))

            active_stage = "scenario"
            self.store.stage(
                run_id,
                active_stage,
                "running",
                message="Écriture du scénario satirique et direction artistique Agnes",
            )
            agnes = AgnesClient(self.settings, agnes_api_key)
            scenario = agnes.write_scenario(
                news,
                count,
                director=director,
                palette=palette,
                intensity=intensity,
            )
            scenario.host_image_prompt = build_host_image_prompt(
                scenario.host_dict(), director, palette, intensity
            )
            for segment in scenario.segments:
                segment.reporter_image_prompt = build_reporter_image_prompt(
                    segment.to_dict(), director, palette, intensity
                )
            scenario_path = run_dir / "scenario.json"
            RunStore.atomic_write_json(scenario_path, scenario.to_dict())
            self.store.register_file(run_id, scenario_path)
            self.store.stage(
                run_id,
                active_stage,
                "succeeded",
                subject_count=len(scenario.segments),
                message="Scénario créatif structuré validé",
            )

            active_stage = "images"
            self.store.stage(
                run_id,
                active_stage,
                "running",
                message="Génération des keyframes créatives Agnes",
            )
            host_plate = agnes.generate_image(
                scenario.host_image_prompt, run_dir / "images" / "host-plate.png"
            )
            self.store.register_file(run_id, host_plate)
            reporter_images: list[Path] = []
            for index, segment in enumerate(scenario.segments):
                image_path = agnes.generate_image(
                    segment.reporter_image_prompt,
                    run_dir / "images" / f"reporter-{index}.png",
                )
                reporter_images.append(image_path)
                self.store.register_file(run_id, image_path)
            self.store.stage(
                run_id,
                active_stage,
                "succeeded",
                image_count=1 + len(reporter_images),
                host_audio_count=0,
                message="Keyframes host + reporters générées",
            )

            active_stage = "h3"
            jobs = create_h3_jobs(
                scenario,
                host_plate,
                reporter_images,
                self.settings,
                director=director,
                palette=palette,
            )
            self.store.stage(
                run_id,
                active_stage,
                "running",
                message=(
                    f"Rendu FastH3 batch de {len(jobs)} clips "
                    f"({len(scenario.segments)} host + {len(scenario.segments)} reporters)"
                ),
                clip_count=len(jobs),
            )
            local_start = time.perf_counter()
            batch_result = self.h3_renderer.render_batch(jobs, run_id=run_id)
            local_elapsed = time.perf_counter() - local_start

            h3_paths: dict[str, Path] = {}
            h3_durations: dict[str, float] = {}
            for job in jobs:
                video_bytes = batch_result.videos.get(job.id)
                if not video_bytes:
                    raise RuntimeError(f"Le batch FastH3 n'a pas renvoyé {job.id}.")
                video_path = run_dir / "h3" / f"{job.id}.mp4"
                video_path.write_bytes(video_bytes)
                self.store.register_file(run_id, video_path)
                info = probe_media(video_path, self.settings)
                if not info.video or not info.audio:
                    raise RuntimeError(
                        f"Clip H3 invalide ou sans audio natif: {video_path.name}. "
                        "Aucun fallback silencieux."
                    )
                h3_paths[job.id] = video_path
                h3_durations[job.id] = info.duration

            host_videos = [h3_paths[f"host-{index}"] for index in range(len(scenario.segments))]
            reporter_videos = [
                h3_paths[f"reporter-{index}"] for index in range(len(scenario.segments))
            ]
            host_durations = [
                h3_durations[f"host-{index}"] for index in range(len(scenario.segments))
            ]
            reporter_durations = [
                h3_durations[f"reporter-{index}"] for index in range(len(scenario.segments))
            ]
            h3_elapsed = batch_result.generation_seconds or local_elapsed
            self.store.stage(
                run_id,
                active_stage,
                "succeeded",
                clip_count=len(jobs),
                generation_seconds=round(h3_elapsed, 3),
                message="Batch full-H3 terminé; un seul appel Modal",
            )

            active_stage = "assembly"
            self.store.stage(
                run_id,
                active_stage,
                "running",
                message="Construction timeline et montage FFmpeg local",
            )
            timeline = build_timeline(
                run_id=run_id,
                run_dir=run_dir,
                scenario=scenario,
                host_plate=host_plate,
                host_videos=host_videos,
                reporter_videos=reporter_videos,
                host_durations=host_durations,
                reporter_durations=reporter_durations,
                settings=self.settings,
            )
            timeline_path = run_dir / "timeline.json"
            self.store.register_file(run_id, timeline_path)
            result = self.assembler.assemble(timeline_path, run_dir)
            final_path = Path(result["path"])
            self.store.register_file(run_id, final_path)
            for relative in result["segment_files"]:
                self.store.register_file(run_id, run_dir / relative)
            manifest = self.store.read_manifest(run_id)
            self.store.stage(
                run_id,
                active_stage,
                "succeeded",
                scene_count=len(timeline.scenes),
                final_duration_seconds=result["duration_seconds"],
                resolution=f"{result['width']}x{result['height']}",
                fps=result["fps"],
                audio=result["audio"],
            )
            self.store.stage(run_id, "ready", "succeeded", message="JT final prêt")
            self.store.update(
                run_id,
                status="complete",
                final_duration_seconds=result["duration_seconds"],
                h3_clip_count=len(jobs),
                h3_generation_seconds=round(h3_elapsed, 3),
                final_file="newsreel_final.mp4",
                summary={
                    "title": scenario.title,
                    "subject_count": len(scenario.segments),
                    "h3_clip_count": len(jobs),
                    "duration_seconds": result["duration_seconds"],
                    "resolution": f"{result['width']}x{result['height']}",
                    "fps": result["fps"],
                    "creative": scenario.creative,
                    "errors": len(manifest.get("errors", [])),
                },
            )
            return self.store.read_manifest(run_id)
        except Exception as exc:
            try:
                self.store.stage(run_id, active_stage, "failed", message=str(exc))
                self.store.add_error(run_id, str(exc), active_stage)
            except Exception:
                pass
            raise

    @staticmethod
    def save_scenario(run_dir: Path, scenario: Scenario) -> Path:
        path = Path(run_dir) / "scenario.json"
        RunStore.atomic_write_json(path, scenario.to_dict())
        return path

    @staticmethod
    def save_news(run_dir: Path, news: list[NewsItem]) -> Path:
        path = Path(run_dir) / "news.json"
        RunStore.atomic_write_json(path, [item.to_dict() for item in news])
        return path
