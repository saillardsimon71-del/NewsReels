from __future__ import annotations

from pathlib import Path

from .config import Settings
from .models import Scenario, Scene, Timeline
from .run_store import RunStore

INTRO_SECONDS = 1.5
OUTRO_SECONDS = 1.5


def _relative(path: Path, run_dir: Path) -> str:
    return path.resolve().relative_to(run_dir.resolve()).as_posix()


def build_timeline(
    run_id: str,
    run_dir: Path,
    scenario: Scenario,
    host_plate: Path,
    host_videos: list[Path],
    reporter_videos: list[Path],
    host_durations: list[float],
    reporter_durations: list[float],
    settings: Settings,
) -> Timeline:
    count = len(scenario.segments)
    if not all(
        len(values) == count
        for values in (host_videos, reporter_videos, host_durations, reporter_durations)
    ):
        raise ValueError("Les assets et durées H3 doivent correspondre au nombre de sujets.")

    scenes: list[Scene] = [
        Scene(
            id="intro",
            type="still",
            asset=_relative(host_plate, run_dir),
            duration=INTRO_SECONDS,
            motion="slow_push_in",
            title="NEWSREEL",
            kicker="LE JT SATIRIQUE",
        )
    ]
    for index, segment in enumerate(scenario.segments):
        host_duration = float(host_durations[index])
        reporter_duration = float(reporter_durations[index])
        if host_duration <= 0 or reporter_duration <= 0:
            raise ValueError(f"Durée H3 invalide pour le sujet {index + 1}.")
        scenes.append(
            Scene(
                id=f"host-{index}",
                type="h3_video",
                asset=_relative(host_videos[index], run_dir),
                dialogue=segment.host_dialogue,
                duration=round(host_duration, 3),
                title=segment.title,
                kicker="NEWSREEL • PLATEAU",
                source_url=segment.source_url,
            )
        )
        scenes.append(
            Scene(
                id=f"reporter-{index}",
                type="h3_video",
                asset=_relative(reporter_videos[index], run_dir),
                dialogue=segment.reporter_dialogue,
                duration=round(reporter_duration, 3),
                title=segment.title,
                kicker="NEWSREEL • SUR LE TERRAIN",
                source_url=segment.source_url,
            )
        )
    scenes.append(
        Scene(
            id="outro",
            type="still",
            asset=_relative(host_plate, run_dir),
            duration=OUTRO_SECONDS,
            motion="slow_pull_out",
            title="NEWSREEL",
            kicker="À BIENTÔT",
        )
    )
    timeline = Timeline(
        run_id=run_id,
        fps=settings.fps,
        width=settings.width,
        height=settings.height,
        scenes=scenes,
        version=2,
    )
    RunStore.atomic_write_json(run_dir / "timeline.json", timeline.to_dict())
    return timeline
