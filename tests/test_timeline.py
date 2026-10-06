from __future__ import annotations

import json
from pathlib import Path

import pytest

from newsreel.config import Settings
from newsreel.models import Scenario
from newsreel.run_store import RunStore
from newsreel.timeline import build_timeline


def test_build_timeline_is_explicit_serializable_and_targets_v1(tmp_path: Path) -> None:
    settings = Settings(project_root=tmp_path, output_dir=tmp_path / "output")
    store = RunStore(settings.output_dir)
    run_id, run_dir = store.create("timeline-test")
    image = run_dir / "images" / "host.png"
    image.write_bytes(b"fixture")
    hosts = []
    videos = []
    for index in range(3):
        host = run_dir / "audio" / f"host-{index}.wav"
        video = run_dir / "h3" / f"reporter-{index}.mp4"
        host.write_bytes(b"fake audio")
        video.write_bytes(b"fake video")
        hosts.append(host)
        videos.append(video)
    scenario = Scenario.from_mapping(
        {
            "title": "JT de test",
            "segments": [
                {
                    "title": f"Sujet {i + 1}",
                    "host_dialogue": f"Texte host exact {i + 1}.",
                    "reporter_dialogue": f"Texte reporter exact {i + 1}.",
                    "source_url": f"https://example.test/{i}",
                }
                for i in range(3)
            ],
        }
    )
    timeline = build_timeline(
        run_id,
        run_dir,
        scenario,
        image,
        hosts,
        videos,
        [4.2, 4.5, 5.0],
        [10.125, 10.125, 10.125],
        settings,
    )
    serialized = json.loads((run_dir / "timeline.json").read_text(encoding="utf-8"))
    assert serialized["run_id"] == run_id
    assert (serialized["width"], serialized["height"], serialized["fps"]) == (1080, 1920, 24)
    assert [scene["id"] for scene in serialized["scenes"]] == [
        "intro",
        "host-0",
        "reporter-0",
        "host-1",
        "reporter-1",
        "host-2",
        "reporter-2",
        "outro",
    ]
    host_scene = next(scene for scene in serialized["scenes"] if scene["id"] == "host-0")
    assert host_scene["dialogue"] == "Texte host exact 1."
    assert host_scene["duration"] == pytest.approx(4.2 + 0.4, abs=0.001)
    reporter_scene = next(scene for scene in serialized["scenes"] if scene["id"] == "reporter-0")
    assert reporter_scene["type"] == "h3_video"
    assert reporter_scene["duration"] == 10.125
    assert serialized["duration"] == timeline.to_dict()["duration"]
    assert 45 <= serialized["duration"] <= 60
