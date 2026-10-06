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
