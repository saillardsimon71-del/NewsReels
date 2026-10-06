from __future__ import annotations

from pathlib import Path

import pytest

from newsreel.run_store import RunStore


def test_runs_are_isolated_and_manifest_tracks_files(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "output")
    first_id, first = store.create("run-one")
    second_id, second = store.create("run-two")
    asset = first / "images" / "only-first.png"
    asset.write_bytes(b"one")
    store.register_file(first_id, asset)
    assert first != second
    assert store.read_manifest(first_id)["files"] == ["images/only-first.png"]
    assert store.read_manifest(second_id)["files"] == []
    with pytest.raises(FileExistsError):
        store.create("run-one")


def test_run_id_and_registered_paths_are_confined(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "output")
    with pytest.raises(ValueError):
        store.create("../escape")
    run_id, run_dir = store.create("safe")
    outside = tmp_path / "outside.txt"
    outside.write_text("no")
    with pytest.raises(ValueError):
        store.register_file(run_id, outside)
    with pytest.raises(FileNotFoundError):
        store.path("missing")


def test_list_runs_returns_recent_persisted_metadata(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "output")
    first_id, _ = store.create("run-first")
    store.update(first_id, status="failed", query="actualité France", requested_subject_count=3)
    second_id, second_dir = store.create("run-second")
    store.update(
        second_id,
        status="complete",
        query="technologie",
        requested_subject_count=5,
        final_file="newsreel_final.mp4",
        summary={"title": "JT Tech"},
    )

    malformed = store.output_root / "not-a-run"
    malformed.mkdir()
    (malformed / "run_manifest.json").write_text("{not json", encoding="utf-8")

    runs = store.list_runs(limit=10)
    ids = [run["run_id"] for run in runs]
    assert second_id in ids
    assert first_id in ids
    selected = next(run for run in runs if run["run_id"] == second_id)
    assert selected["status"] == "complete"
    assert selected["query"] == "technologie"
    assert selected["requested_subject_count"] == 5
    assert selected["final_file"] == "newsreel_final.mp4"
    assert selected["summary"]["title"] == "JT Tech"
