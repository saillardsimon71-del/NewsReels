from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

from modal_h3 import validate_batch
from newsreel.agnes import AgnesClient
from newsreel.config import Settings
from newsreel.creative import apply_creative_postprocessing, build_scenario_prompt
from newsreel.h3_worker_contract import ModalH3Renderer, create_h3_jobs, encode_batch
from newsreel.media import MediaInfo
from newsreel.models import NewsItem, Scenario
from newsreel.pipeline import NewsReelPipeline
from newsreel.run_store import RunStore


def _segment(index: int) -> dict:
    return {
        "headline": f"Sujet {index}",
        "host_dialogue": f"Information factuelle numéro {index} annoncée depuis le plateau.",
        "host_action": "a chrome dial rotates behind the host",
        "people": [
            {
                "name": "Witness",
                "role": "witness",
                "description": "retro-futuristic witness",
            }
        ],
        "location": "hallucinatory retrofuturist plaza",
        "scene_action": "a harmless giant machine slowly blocks the reporter",
        "camera_plan": "establishing shot, reaction close-up, final wide",
        "reporter": {
            "name": f"Reporter {index}",
            "description": "retro-futuristic field reporter",
            "dialogue": f"Même la machine réclame son badge numéro {index} aujourd'hui.",
        },
    }


def test_prompt_contains_grounding_context_and_real_intensity() -> None:
    prompt = build_scenario_prompt(
        [
            NewsItem(
                title="Titre exact",
                source="Agence Test",
                published="Tue, 06 Oct 2026 10:00:00 GMT",
                summary="Contexte factuel supplémentaire.",
            )
        ],
        1,
        "wes_anderson",
        "electric_coral_cyan",
        "subtle",
    )
    assert "HEADLINE: Titre exact" in prompt
    assert "SOURCE: Agence Test" in prompt
    assert "PUBLISHED: Tue, 06 Oct 2026 10:00:00 GMT" in prompt
    assert "CONTEXT: Contexte factuel supplémentaire." in prompt
    assert "CREATIVE INTENSITY — SUBTILE — CONTEMPLATIF" in prompt


def test_wrong_subject_count_is_rejected_instead_of_cloned() -> None:
    value = {
        "jt_title": "JT test",
        "host": {
            "name": "Host",
            "description": "retro-futuristic anchor",
            "plateau": "retro-futuristic studio",
        },
        "segments": [_segment(0)],
    }
    with pytest.raises(ValueError, match="exactement 3 sujets"):
        apply_creative_postprocessing(
            value,
            3,
            director="wes_anderson",
            palette="electric_coral_cyan",
        )


def test_worker_accepts_seven_subject_full_h3_batch(tmp_path: Path) -> None:
    scenario = Scenario.from_mapping(
        {
            "title": "JT 7 sujets",
            "host": {
                "name": "Host",
                "description": "retro-futuristic anchor",
                "plateau": "retro-futuristic studio",
            },
            "creative": {
                "director": "wes_anderson",
                "palette": "electric_coral_cyan",
                "intensity": "moderate",
            },
            "segments": [_segment(index) for index in range(7)],
        }
    )
    host = tmp_path / "host.png"
    host.write_bytes(b"host")
    reporters: list[Path] = []
    for index in range(7):
        path = tmp_path / f"reporter-{index}.png"
        path.write_bytes(f"reporter-{index}".encode())
        reporters.append(path)

    jobs = create_h3_jobs(scenario, host, reporters, Settings(project_root=tmp_path))
    assert len(jobs) == 14
    payload = encode_batch(jobs, "run-seven")
    assert len(validate_batch(payload)) == 14


def test_modal_preflight_resolves_deployed_function_without_gpu(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple] = []

    class FakeRemote:
        def info(self, refresh=False):
            calls.append(("info", refresh))
            return {"ok": True}

    class FakeFunction:
        @staticmethod
        def from_name(app_name, function_name):
            calls.append(("from_name", app_name, function_name))
            return FakeRemote()

    monkeypatch.setitem(sys.modules, "modal", types.SimpleNamespace(Function=FakeFunction))
    ModalH3Renderer("newsreel-fasth3", "render_h3_batch").check_available()
    assert calls == [
        ("from_name", "newsreel-fasth3", "render_h3_batch"),
        ("info", True),
    ]


def test_reassemble_recovers_without_existing_timeline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = Settings(project_root=tmp_path, output_dir=tmp_path / "output")
    store = RunStore(settings.output_dir)
    run_id, run_dir = store.create("recovery-test")

    scenario = Scenario.from_mapping(
        {
            "title": "JT récupération",
            "host": {
                "name": "Host",
                "description": "retro-futuristic anchor",
                "plateau": "retro-futuristic studio",
            },
            "creative": {
                "director": "wes_anderson",
                "palette": "electric_coral_cyan",
                "intensity": "strong",
            },
            "segments": [_segment(0)],
        }
    )
    RunStore.atomic_write_json(run_dir / "scenario.json", scenario.to_dict())
    (run_dir / "images" / "host-plate.png").write_bytes(b"fake-image")
    for role in ("host", "reporter"):
        (run_dir / "h3" / f"{role}-0.mp4").write_bytes(b"fake-mp4")

    monkeypatch.setattr(
        "newsreel.pipeline.probe_media",
        lambda path, _settings: MediaInfo(
            path=Path(path),
            duration=10.125,
            width=768,
            height=1344,
            fps=24.0,
            video=True,
            audio=True,
            streams=[],
        ),
    )

    class FakeAssembler:
        def assemble(self, timeline_path: Path, run_dir: Path):
            assert timeline_path.is_file()
            final_path = run_dir / "newsreel_final.mp4"
            final_path.write_bytes(b"final")
            segment = run_dir / "segments" / "00-intro.mp4"
            segment.write_bytes(b"segment")
            return {
                "path": final_path,
                "duration_seconds": 23.25,
                "width": 1080,
                "height": 1920,
                "fps": 24.0,
                "audio": True,
                "segment_files": ["segments/00-intro.mp4"],
            }

    pipeline = NewsReelPipeline(settings, store=store, assembler=FakeAssembler())
    result = pipeline.reassemble(run_id)

    assert result["status"] == "complete"
    assert (run_dir / "timeline.json").is_file()
    assert result["final_file"] == "newsreel_final.mp4"
    assert result["h3_clip_count"] == 2


def test_agnes_retries_once_when_headline_is_not_from_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = Settings(project_root=tmp_path)
    client = AgnesClient(settings, "offline-key")
    responses = iter(
        [
            {
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"jt_title":"JT","host":{},'
                                '"segments":[{"headline":"Titre inventé",'
                                '"host_dialogue":"Une information factuelle est annoncée depuis le plateau ce matin.",'
                                '"reporter":{"dialogue":"Même le décor semble demander une pause syndicale aujourd’hui."}}]}'
                            )
                        }
                    }
                ]
            },
            {
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"jt_title":"JT","host":{},'
                                '"segments":[{"headline":"Titre exact",'
                                '"host_dialogue":"Une information factuelle est annoncée depuis le plateau ce matin.",'
                                '"reporter":{"dialogue":"Même le décor semble demander une pause syndicale aujourd’hui."}}]}'
                            )
                        }
                    }
                ]
            },
        ]
    )
    calls: list[dict] = []

    def fake_request(_endpoint, payload, timeout=None):
        calls.append(payload)
        return next(responses)

    monkeypatch.setattr(client, "_request", fake_request)
    scenario = client.write_scenario(
        [
            NewsItem(
                title="Titre exact",
                url="https://example.test/source",
                source="Agence Test",
                published="Tue, 06 Oct 2026 10:00:00 GMT",
                summary="Contexte factuel.",
            )
        ],
        1,
        director="wes_anderson",
        palette="electric_coral_cyan",
        intensity="strong",
    )

    assert len(calls) == 2
    assert "CORRECTION REQUIRED AFTER INVALID OUTPUT" in calls[1]["messages"][1]["content"]
    assert scenario.segments[0].title == "Titre exact"
    assert scenario.segments[0].source_url == "https://example.test/source"
