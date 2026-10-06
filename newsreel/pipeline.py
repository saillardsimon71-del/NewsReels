from __future__ import annotations

import time
from pathlib import Path
from typing import Protocol

from .agnes import AgnesClient
from .assembler import FFmpegAssembler
from .config import Settings
from .h3_worker_contract import H3BatchResult, H3Job, ModalH3Renderer, create_h3_jobs
from .models import NewsItem, Scenario
from .news import GoogleNewsRSS
from .run_store import RunStore
from .timeline import build_timeline
from .tts import EdgeTTSProvider, TTSProvider


class H3Renderer(Protocol):
    def render_batch(self, jobs: list[H3Job], run_id: str | None = None) -> H3BatchResult: ...


class NewsReelPipeline:
    """One production run, with independent run-scoped assets and manifest progress."""

    def __init__(
        self,
        settings: Settings,
        store: RunStore | None = None,
        news_provider: GoogleNewsRSS | None = None,
        tts_provider: TTSProvider | None = None,
        h3_renderer: H3Renderer | None = None,
        assembler: FFmpegAssembler | None = None,
    ):
        self.settings = settings
        self.store = store or RunStore(settings.output_dir or settings.project_root / "output")
        self.news_provider = news_provider or GoogleNewsRSS()
        self.tts_provider = tts_provider or EdgeTTSProvider(settings)
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
    ) -> dict[str, object]:
        run_dir = self.store.path(run_id)
        active_stage = "news"
        try:
            self.store.update(run_id, status="running", query=query, requested_subject_count=count)
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
            self.store.stage(run_id, active_stage, "running", message="Écriture du scénario Agnes")
            agnes = AgnesClient(self.settings, agnes_api_key)
            scenario = agnes.write_scenario(news, count)
            scenario_path = run_dir / "scenario.json"
            RunStore.atomic_write_json(scenario_path, scenario.to_dict())
            self.store.register_file(run_id, scenario_path)
            self.store.stage(
                run_id,
                active_stage,
                "succeeded",
                subject_count=len(scenario.segments),
                message="Scénario structuré validé",
            )

            active_stage = "images"
            self.store.stage(run_id, active_stage, "running", message="Génération des images Agnes")
            host_plate = agnes.generate_image(
                scenario.host_image_prompt, run_dir / "images" / "host-plate.png"
            )
            self.store.register_file(run_id, host_plate)
            reporter_images: list[Path] = []
            for index, segment in enumerate(scenario.segments):
                prompt = segment.reporter_image_prompt or (
                    "Photorealistic vertical French television field-reporter news image, "
                    f"editorial setting related to this verified story: {segment.title}. "
                    "One calm reporter looking into the camera, documentary lighting, "
                    "realistic face and hands, no text, no captions, no logos."
                )
                image_path = agnes.generate_image(
                    prompt, run_dir / "images" / f"reporter-{index}.png"
                )
                reporter_images.append(image_path)
                self.store.register_file(run_id, image_path)
            audio_paths: list[Path] = []
            audio_durations: list[float] = []
            for index, segment in enumerate(scenario.segments):
                audio_path = run_dir / "audio" / f"host-{index}.mp3"
                # segment.host_dialogue is passed unchanged to TTS by design.
                duration = self.tts_provider.synthesize(
                    segment.host_dialogue, audio_path, self.settings.tts_voice
                )
                if duration <= 0:
                    raise RuntimeError(f"Le TTS n'a produit aucune durée audio pour host-{index}.")
                audio_paths.append(audio_path)
                audio_durations.append(duration)
                self.store.register_file(run_id, audio_path)
            self.store.stage(
                run_id,
                active_stage,
                "succeeded",
                image_count=1 + len(reporter_images),
                host_audio_count=len(audio_paths),
            )

            active_stage = "h3"
            self.store.stage(
                run_id,
                active_stage,
                "running",
                message=f"Rendu FastH3 batch de {len(scenario.segments)} reporter(s) sur un seul worker Modal",
                clip_count=len(scenario.segments),
            )
            jobs = create_h3_jobs(scenario.segments, reporter_images, self.settings)
            local_start = time.perf_counter()
            batch_result = self.h3_renderer.render_batch(jobs, run_id=run_id)  # One call per run.
            local_elapsed = time.perf_counter() - local_start
            h3_paths: list[Path] = []
            for index, job in enumerate(jobs):
                video_bytes = batch_result.videos.get(job.id)
                if not video_bytes:
                    raise RuntimeError(f"Le batch FastH3 n'a pas renvoyé {job.id}.")
                video_path = run_dir / "h3" / f"reporter-{index}.mp4"
                video_path.write_bytes(video_bytes)
                h3_paths.append(video_path)
                self.store.register_file(run_id, video_path)
            from .media import probe_media

            reporter_durations: list[float] = []
            for path in h3_paths:
                info = probe_media(path, self.settings)
                if not info.video or not info.audio:
                    raise RuntimeError(
                        f"Clip H3 invalide ou sans audio natif: {path.name}. Aucun fallback silencieux."
                    )
                reporter_durations.append(info.duration)
            h3_elapsed = batch_result.generation_seconds or local_elapsed
            self.store.stage(
                run_id,
                active_stage,
                "succeeded",
                clip_count=len(h3_paths),
                generation_seconds=round(h3_elapsed, 3),
                message="Batch FastH3 terminé; un seul appel Modal",
            )

            active_stage = "assembly"
            self.store.stage(
                run_id, active_stage, "running", message="Construction timeline et montage local"
            )
            timeline = build_timeline(
                run_id=run_id,
                run_dir=run_dir,
                scenario=scenario,
                host_plate=host_plate,
                host_audio=audio_paths,
                reporter_videos=h3_paths,
                host_audio_durations=audio_durations,
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
                h3_clip_count=len(h3_paths),
                h3_generation_seconds=round(h3_elapsed, 3),
                final_file="newsreel_final.mp4",
                summary={
                    "title": scenario.title,
                    "subject_count": len(scenario.segments),
                    "h3_clip_count": len(h3_paths),
                    "duration_seconds": result["duration_seconds"],
                    "resolution": f"{result['width']}x{result['height']}",
                    "fps": result["fps"],
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
