import base64
import json
import shutil
from io import BytesIO

import pytest
from PIL import Image
from test_staging import _value

from newsreel.agnes import AgnesClient
from newsreel.config import Settings
from newsreel.h3_worker_contract import H3BatchResult
from newsreel.media import probe_media, run_ffmpeg
from newsreel.models import NewsItem
from newsreel.pipeline import NewsReelPipeline
from newsreel.run_store import RunStore


def test_live_pipeline_carries_agnes_staging_to_native_audio_and_final_mp4(tmp_path, monkeypatch):
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("FFmpeg/ffprobe requis pour le test de pipeline complet.")
    settings = Settings(project_root=tmp_path)
    store = RunStore(settings.output_dir)
    run_id, run_dir = store.create("live-fixture")
    value = _value(tail=2)
    value["segments"][0]["reporter"]["dialogue"] = " ".join(["mot"] * 12)
    buffer = BytesIO()
    Image.new("RGB", (96, 168), (20, 80, 140)).save(buffer, format="PNG")

    def request(_client, endpoint, payload, timeout=None):
        if endpoint == "chat/completions":
            return {"choices": [{"message": {"content": json.dumps(value)}}]}
        return {"data": [{"b64_json": base64.b64encode(buffer.getvalue()).decode()}]}

    monkeypatch.setattr(AgnesClient, "_request", request)

    class News:
        def fetch(self, query, limit):
            return [NewsItem(title="Titre exact", url="https://example.test/news")]

    class Renderer:
        def render_batch(self, jobs, run_id=None):
            assert [job.frames for job in jobs] == [124, 192]
            videos = {}
            for job in jobs:
                path = tmp_path / f"fixture-{job.id}.mp4"
                run_ffmpeg([
                    "-f", "lavfi", "-i", f"color=c=navy:s=192x336:r=24:d={job.duration_seconds}",
                    "-f", "lavfi", "-i", f"sine=frequency=440:sample_rate=48000:duration={job.duration_seconds}",
                    "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-t", str(job.duration_seconds), str(path),
                ], settings)
                videos[job.id] = path.read_bytes()
            return H3BatchResult(videos=videos, generation_seconds=1)

    result = NewsReelPipeline(settings, store, News(), Renderer()).run_live(
        run_id, "test", 1, "private-fixture-key",
    )
    assert result["status"] == "complete"
    assert result["errors"] == []
    final = probe_media(run_dir / "newsreel_final.mp4", settings)
    assert (final.width, final.height, final.fps, final.audio) == (1080, 1920, 24, True)
    assert final.duration == pytest.approx(16.1667, abs=0.12)
    saved = json.loads((run_dir / "scenario.json").read_text(encoding="utf-8"))
    assert saved["segments"][0]["camera_plan"] == value["segments"][0]["camera_plan"]
    records = json.loads((run_dir / "h3_jobs.json").read_text(encoding="utf-8"))
    assert [record["frames"] for record in records] == [124, 192]
    assert records[1]["prompt"].count(value["segments"][0]["reporter"]["dialogue"]) == 1
    assert value["segments"][0]["camera_plan"]["reporter"] in records[1]["prompt"]
    assert all(isinstance(record["seed"], int) and record["image_sha256"] for record in records)
    assert "private-fixture-key" not in (run_dir / "run_manifest.json").read_text(encoding="utf-8")


def test_agnes_corrects_duration_overflow_without_truncating_dialogue(tmp_path, monkeypatch):
    client = AgnesClient(Settings(project_root=tmp_path), "fixture-key")
    bad = _value(tail=3)
    bad["segments"][0]["reporter"]["dialogue"] = " ".join(["mot"] * 30)
    good = _value(tail=2)
    responses = iter([bad, good])

    def request(endpoint, payload, timeout=None):
        return {"choices": [{"message": {"content": json.dumps(next(responses))}}]}

    monkeypatch.setattr(client, "_request", request)
    scenario = client.write_scenario([NewsItem(title="Titre exact")], 1, "wes_anderson", "electric_coral_cyan")
    assert scenario.segments[0].reporter_dialogue == good["segments"][0]["reporter"]["dialogue"]
    assert scenario.segments[0].camera_plan == good["segments"][0]["camera_plan"]


def test_typographic_apostrophe_is_restored_to_exact_source_headline(tmp_path, monkeypatch):
    client = AgnesClient(Settings(project_root=tmp_path), "fixture-key")
    value = _value()
    value["segments"][0]["headline"] = "Budget pour l'environnement"
    monkeypatch.setattr(client, "_request", lambda *args, **kwargs: {"choices": [{"message": {"content": json.dumps(value)}}]})
    exact = "Budget pour l\u2019environnement"
    scenario = client.write_scenario([NewsItem(title=exact)], 1, "wes_anderson", "electric_coral_cyan")
    assert scenario.segments[0].title == scenario.segments[0].source_title == exact


def test_agnes_correction_receives_the_draft_it_must_repair(tmp_path, monkeypatch):
    client = AgnesClient(Settings(project_root=tmp_path), "fixture-key")
    bad = _value()
    bad["segments"][0]["scene_action"] = " ".join(["motion"] * 80)
    good = _value()
    responses = iter([bad, good])
    calls = []

    def request(endpoint, payload, timeout=None):
        calls.append(payload)
        return {"choices": [{"message": {"content": json.dumps(next(responses))}}]}

    monkeypatch.setattr(client, "_request", request)
    scenario = client.write_scenario([NewsItem(title="Titre exact")], 1, "wes_anderson", "electric_coral_cyan")
    assert calls[1]["messages"][-2] == {"role": "assistant", "content": json.dumps(bad)}
    assert "CORRECTION REQUIRED" in calls[1]["messages"][-1]["content"]
    assert scenario.segments[0].scene_action == good["segments"][0]["scene_action"]
