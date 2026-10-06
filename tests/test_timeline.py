from __future__ import annotations

import json
from pathlib import Path

from newsreel.config import Settings
from newsreel.models import Scenario
from newsreel.run_store import RunStore
from newsreel.timeline import build_timeline


def test_build_timeline_uses_full_h3_for_host_and_reporters(tmp_path: Path) -> None:
    settings = Settings(project_root=tmp_path, output_dir=tmp_path / "output")
    store = RunStore(settings.output_dir)
    run_id, run_dir = store.create("timeline-test")
    host_plate = run_dir / "images" / "host.png"
    host_plate.write_bytes(b"fixture")
    hosts = []
    reporters = []
    for index in range(3):
        host = run_dir / "h3" / f"host-{index}.mp4"
        reporter = run_dir / "h3" / f"reporter-{index}.mp4"
        host.write_bytes(b"fake video")
        reporter.write_bytes(b"fake video")
        hosts.append(host)
        reporters.append(reporter)

    scenario = Scenario.from_mapping(
        {
            "title": "JT de test",
            "host": {
                "name": "Host",
                "description": "retrofuturistic anchor",
                "plateau": "retrofuturistic studio",
            },
            "segments": [
                {
                    "title": f"Sujet {i + 1}",
                    "host_dialogue": f"Texte host exact {i + 1}.",
                    "reporter": {
                        "name": f"Reporter {i + 1}",
                        "dialogue": f"Texte reporter exact {i + 1}.",
                    },
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
        host_plate,
        hosts,
        reporters,
        [10.125] * 3,
        [10.125] * 3,
        settings,
    )
    serialized = json.loads((run_dir / "timeline.json").read_text(encoding="utf-8"))
    assert serialized["version"] == 2
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
    content_scenes = serialized["scenes"][1:-1]
    assert all(scene["type"] == "h3_video" for scene in content_scenes)
    assert all(not scene["audio"] for scene in content_scenes)
    assert sum(scene["type"] == "h3_video" for scene in serialized["scenes"]) == 6
    assert serialized["duration"] == timeline.to_dict()["duration"]
    assert 63 <= serialized["duration"] <= 65
