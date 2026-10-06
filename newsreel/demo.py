from __future__ import annotations

from pathlib import Path
from typing import Any

from .assembler import FFmpegAssembler
from .config import Settings
from .creative import DEFAULT_DIRECTOR, DEFAULT_INTENSITY, DEFAULT_PALETTE
from .media import run_ffmpeg
from .models import NewsItem, Scenario
from .run_store import RunStore
from .timeline import build_timeline


def _fake_image(path: Path, label: str, color: tuple[int, int, int]) -> None:
    from PIL import Image, ImageDraw, ImageFont

    width, height = 768, 1344
    image = Image.new("RGB", (width, height), (8, 24, 43))
    draw = ImageDraw.Draw(image)
    for y in range(height):
        blend = y / height
        base = tuple(int(color[i] * (1 - blend) + (8, 19, 37)[i] * blend) for i in range(3))
        draw.line((0, y, width, y), fill=base)
    draw.ellipse((500, 130, 900, 530), fill=(20, 87, 108))
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", 42)
    except OSError:
        font = ImageFont.load_default()
    draw.text((56, 910), label, font=font, fill=(245, 250, 255))
    image.save(path, format="PNG")


def _fake_h3_video(path: Path, color: str, frequency: int, settings: Settings) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(
        [
            "-f",
            "lavfi",
            "-i",
            f"color=c={color}:s=384x672:r=24:d=10.125",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency={frequency}:sample_rate=48000:duration=10.125",
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-frames:v",
            "243",
            "-t",
            "10.125",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-tune",
            "stillimage",
            "-crf",
            "30",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "96k",
            "-ar",
            "48000",
            "-ac",
            "2",
            "-shortest",
            str(path),
        ],
        settings,
    )


def run_offline_demo(
    settings: Settings,
    run_id: str | None = None,
    store: RunStore | None = None,
) -> dict[str, Any]:
    """Build a full-H3-shaped fixture locally without network or GPU calls."""
    store = store or RunStore(settings.output_dir or settings.project_root / "output")
    if run_id is not None and (store.output_root / run_id / "run_manifest.json").is_file():
        run_dir = store.path(run_id)
    else:
        run_id, run_dir = store.create(run_id)
    store.update(run_id, status="running", mode="offline-demo", query="fixtures synthétiques")
    try:
        colors = [(30, 97, 112), (93, 70, 117), (129, 76, 53)]
        headlines = [
            "Énergie : les prix se stabilisent",
            "Climat : un nouvel accord européen",
            "Technologie : l'IA à l'école",
        ]
        host_plate = run_dir / "images" / "host-plate.png"
        _fake_image(host_plate, "PLATEAU NEWSREEL · MODE DÉMO", (16, 92, 120))

        reporter_images: list[Path] = []
        host_videos: list[Path] = []
        reporter_videos: list[Path] = []
        segments = []
        news = []
        for index, (headline, color) in enumerate(zip(headlines, colors, strict=True)):
            news.append(
                NewsItem(
                    title=headline,
                    url=f"https://example.invalid/demo/{index}",
                    source="Fixture hors-ligne",
                    published="fixture",
                    summary="Article factice généré localement pour vérifier le montage.",
                )
            )
            segments.append(
                {
                    "id": f"subject-{index}",
                    "headline": headline,
                    "summary": "Résumé factuel de fixture.",
                    "source_title": headline,
                    "source_url": news[-1].url,
                    "host_dialogue": f"{headline}. La rédaction fait le point.",
                    "host_action": "a chrome console starts blinking behind the host",
                    "people": [
                        {
                            "name": "Figurant",
                            "description": "retro-futuristic funny costume",
                            "role": "witness",
                        }
                    ],
                    "location": "hallucinatory retrofuturist test set",
                    "scene_action": "a harmless oversized prop slowly rolls through the frame",
                    "camera_plan": "establishing shot, reaction close-up, final wide",
                    "reporter": {
                        "name": f"Reporter {index + 1}",
                        "description": "retro-futuristic field reporter",
                        "dialogue": "Même le décor a décidé de commenter la situation à sa manière.",
                    },
                }
            )
            reporter_image = run_dir / "images" / f"reporter-{index}.png"
            _fake_image(reporter_image, f"REPORTER {index + 1} · FIXTURE", color)
            reporter_images.append(reporter_image)

            host_video = run_dir / "h3" / f"host-{index}.mp4"
            reporter_video = run_dir / "h3" / f"reporter-{index}.mp4"
            _fake_h3_video(host_video, "0x105c78", 210 + index * 25, settings)
            _fake_h3_video(
                reporter_video,
                f"0x{color[0]:02x}{color[1]:02x}{color[2]:02x}",
                320 + index * 70,
                settings,
            )
            host_videos.append(host_video)
            reporter_videos.append(reporter_video)

        scenario = Scenario.from_mapping(
            {
                "title": "JT NewsReel — démonstration hors-ligne",
                "host": {
                    "name": "Chroniqueur",
                    "description": "retrofuturistic anchor fixture",
                    "plateau": "hallucinatory retrofuturistic TV set",
                    "host_action": "a chrome console malfunctions",
                },
                "creative": {
                    "director": DEFAULT_DIRECTOR,
                    "palette": DEFAULT_PALETTE,
                    "intensity": DEFAULT_INTENSITY,
                },
                "segments": segments,
            }
        )
        news_path = run_dir / "news.json"
        RunStore.atomic_write_json(news_path, [item.to_dict() for item in news])
        store.register_file(run_id, news_path)
        store.stage(run_id, "news", "succeeded", article_count=len(news), mode="offline-fixture")
        scenario_path = run_dir / "scenario.json"
        RunStore.atomic_write_json(scenario_path, scenario.to_dict())
        store.register_file(run_id, scenario_path)
        store.stage(
            run_id, "scenario", "succeeded", subject_count=len(segments), mode="offline-fixture"
        )
        for path in [host_plate, *reporter_images]:
            store.register_file(run_id, path)
        store.stage(
            run_id,
            "images",
            "succeeded",
            image_count=4,
            host_audio_count=0,
            mode="synthetic-fixtures",
        )
        for path in [*host_videos, *reporter_videos]:
            store.register_file(run_id, path)
        store.stage(
            run_id,
            "h3",
            "succeeded",
            clip_count=6,
            generation_seconds=None,
            mode="synthetic-video-fixtures-no-gpu",
        )
        timeline = build_timeline(
            run_id,
            run_dir,
            scenario,
            host_plate,
            host_videos,
            reporter_videos,
            [10.125] * 3,
            [10.125] * 3,
            settings,
        )
        timeline_path = run_dir / "timeline.json"
        store.register_file(run_id, timeline_path)
        store.stage(run_id, "assembly", "running", message="Encodage FFmpeg local hors-ligne")
        result = FFmpegAssembler(settings).assemble(timeline_path, run_dir)
        final_path = Path(result["path"])
        store.register_file(run_id, final_path)
        for relative in result["segment_files"]:
            store.register_file(run_id, run_dir / relative)
        store.stage(
            run_id,
            "assembly",
            "succeeded",
            scene_count=len(timeline.scenes),
            final_duration_seconds=result["duration_seconds"],
            resolution=f"{result['width']}x{result['height']}",
            fps=result["fps"],
            audio=result["audio"],
        )
        store.stage(run_id, "ready", "succeeded", message="JT de démonstration prêt")
        store.update(
            run_id,
            status="complete",
            final_duration_seconds=result["duration_seconds"],
            h3_clip_count=6,
            h3_generation_seconds=None,
            final_file="newsreel_final.mp4",
            summary={
                "title": scenario.title,
                "subject_count": 3,
                "h3_clip_count": 6,
                "duration_seconds": result["duration_seconds"],
                "resolution": f"{result['width']}x{result['height']}",
                "fps": result["fps"],
                "note": "Fixtures synthétiques: aucune requête Agnes ou Modal, aucun GPU.",
            },
        )
        return store.read_manifest(run_id)
    except Exception as exc:
        store.add_error(run_id, str(exc), "offline-demo")
        raise


def main() -> int:
    settings = Settings.from_env()
    try:
        manifest = run_offline_demo(settings)
    except Exception as exc:
        print(f"Échec de la démo hors-ligne: {exc}")
        return 1
    print(f"Run terminé: {manifest['run_id']}")
    print(f"MP4: {settings.output_dir / manifest['run_id'] / 'newsreel_final.mp4'}")
    print(f"Durée: {manifest['final_duration_seconds']} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
