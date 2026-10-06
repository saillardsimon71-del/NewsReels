from __future__ import annotations

from pathlib import Path

from .config import Settings
from .models import Scenario, Scene, Timeline
from .run_store import RunStore

HOST_MIN_SECONDS = 3.5
HOST_AUDIO_MARGIN_SECONDS = 0.4
INTRO_SECONDS = 2.5
OUTRO_SECONDS = 2.0


def _relative(path: Path, run_dir: Path) -> str:
    return path.resolve().relative_to(run_dir.resolve()).as_posix()


def build_timeline(
    run_id: str,
    run_dir: Path,
    scenario: Scenario,
    host_plate: Path,
    host_audio: list[Path],
    reporter_videos: list[Path],
    host_audio_durations: list[float],
    reporter_durations: list[float],
    settings: Settings,
) -> Timeline:
    count = len(scenario.segments)
    if not all(
        len(values) == count
        for values in (host_audio, reporter_videos, host_audio_durations, reporter_durations)
    ):
        raise ValueError("Les assets et durées doivent correspondre au nombre de sujets.")

    scenes: list[Scene] = [
        Scene(
            id="intro",
            type="still",
            asset=_relative(host_plate, run_dir),
            duration=INTRO_SECONDS,
            motion="slow_push_in",
            title="NEWSREEL",
            kicker="L'actualité, en bref",
        )
    ]
    host_motions = ("slow_push_in", "slow_pan_left", "slow_pan_right")
    for index, segment in enumerate(scenario.segments):
        actual_audio = float(host_audio_durations[index])
        if actual_audio <= 0:
            raise ValueError(f"Audio host vide pour le sujet {index + 1}.")
        # Never trim speech to enforce the target runtime: the voice duration is the source of truth.
        host_duration = max(HOST_MIN_SECONDS, actual_audio + HOST_AUDIO_MARGIN_SECONDS)
        scenes.append(
            Scene(
                id=f"host-{index}",
                type="host_still",
                asset=_relative(host_plate, run_dir),
                audio=_relative(host_audio[index], run_dir),
                dialogue=segment.host_dialogue,
                duration=round(host_duration, 3),
                motion=host_motions[index % len(host_motions)],
                title=segment.title,
                kicker="EN DIRECT • NEWSREEL",
                source_url=segment.source_url,
            )
        )
        scenes.append(
            Scene(
                id=f"reporter-{index}",
                type="h3_video",
                asset=_relative(reporter_videos[index], run_dir),
                dialogue=segment.reporter_dialogue,
                duration=round(float(reporter_durations[index]), 3),
                title=segment.title,
                kicker="LE POINT SUR LA SITUATION",
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
            kicker="À bientôt pour un nouveau JT",
        )
    )
    timeline = Timeline(
        run_id=run_id,
        fps=settings.fps,
        width=settings.width,
        height=settings.height,
        scenes=scenes,
    )
    RunStore.atomic_write_json(run_dir / "timeline.json", timeline.to_dict())
    return timeline
