from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from newsreel.config import Settings
from newsreel.demo import run_offline_demo
from newsreel.media import MediaToolError, probe_media


def test_full_offline_fixture_to_final_mp4(tmp_path: Path) -> None:
    ffmpeg = shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")
    ffprobe = shutil.which("ffprobe") or shutil.which("ffprobe.exe")
    if not ffmpeg or not ffprobe:
        pytest.skip("ffmpeg et ffprobe ne sont pas installés dans cet environnement.")
    settings = Settings(
        project_root=tmp_path,
        output_dir=tmp_path / "output",
        ffmpeg_path=ffmpeg,
        ffprobe_path=ffprobe,
    )
    manifest = run_offline_demo(settings, run_id="offline-test")
    run_dir = settings.output_dir / "offline-test"
    final_path = run_dir / "newsreel_final.mp4"
    assert manifest["status"] == "complete"
    assert manifest["h3_clip_count"] == 3
    assert final_path.is_file() and final_path.stat().st_size > 10_000
    assert (run_dir / "scenario.json").is_file()
    assert (run_dir / "timeline.json").is_file()
    assert (run_dir / "run_manifest.json").is_file()
    assert len(list((run_dir / "h3").glob("*.mp4"))) == 3
    assert len(list((run_dir / "segments").glob("*.mp4"))) == 8
    assert len([item for item in manifest["files"] if item.startswith("segments/")]) == 8
    assert manifest["errors"] == []
    assert manifest["h3_generation_seconds"] is None  # Synthetic fixture, not a GPU measurement.
    info = probe_media(final_path, settings)
    assert info.video and info.audio
    assert (info.width, info.height) == (1080, 1920)
    assert info.fps == pytest.approx(24, abs=0.05)
    assert 45 <= info.duration <= 60
    assert manifest["stages"]["assembly"]["status"] == "succeeded"


def test_missing_tools_have_an_explicit_error(tmp_path: Path) -> None:
    settings = Settings(
        project_root=tmp_path, output_dir=tmp_path / "output", ffmpeg_path="missing-ffmpeg"
    )
    from newsreel.assembler import FFmpegAssembler

    with pytest.raises(MediaToolError, match="ffmpeg"):
        FFmpegAssembler(settings).assemble(tmp_path / "not-created.json", tmp_path)
