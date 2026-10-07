from dataclasses import asdict, replace

import pytest
from test_h3_contract import _scenario, _six_jobs

import newsreel.h3_workflow as workflow
from modal_h3 import validate_batch
from newsreel.config import Settings
from newsreel.creative import apply_creative_postprocessing
from newsreel.h3_worker_contract import create_h3_jobs, encode_batch


def test_short_dialogue_does_not_get_ten_seconds(tmp_path):
    jobs = _six_jobs(tmp_path)
    assert jobs[0].frames == 124
    assert jobs[0].duration_seconds == 124 / 24


@pytest.mark.parametrize("seconds,frames", [(5, 124), (6, 158), (8, 192), (10, 243), (15, 362)])
def test_duration_snaps_up_to_h3_grid(seconds, frames):
    assert workflow.h3_frames_for_duration(seconds) == frames


@pytest.mark.parametrize("seconds", [0, -1, float("nan"), float("inf"), 16])
def test_duration_rejects_invalid_or_untrained_range(seconds):
    with pytest.raises(ValueError):
        workflow.h3_frames_for_duration(seconds)


def test_speech_and_visual_action_both_set_duration():
    assert workflow.h3_frames_for_dialogue("Bonsoir à tous, voici les nouvelles du jour.") == 124
    assert workflow.h3_frames_for_dialogue(" ".join(["mot"] * 20)) == 226
    assert workflow.h3_frames_for_dialogue("Bonjour.", visual_seconds=8) == 192


def test_batch_accepts_different_clip_lengths_and_graph_uses_each(tmp_path):
    jobs = _six_jobs(tmp_path)
    jobs[0] = replace(jobs[0], frames=124, duration_seconds=124 / 24)
    jobs[1] = replace(jobs[1], frames=209, duration_seconds=209 / 24)
    payload = encode_batch(jobs, "mixed-durations")
    assert "frames" not in payload["config"]
    assert "duration_seconds" not in payload["config"]
    validated = validate_batch(payload)
    assert [job["frames"] for job in validated[:2]] == [124, 209]
    for job in jobs[:2]:
        graph = workflow.build_h3_api_workflow(asdict(job), "input.png", job.id)
        assert graph["104"]["inputs"]["length"] == job.frames
        assert graph["15"]["inputs"]["noise_seed"] == job.seed


@pytest.mark.parametrize("frames,duration", [(125, 125 / 24), (107, 107 / 24), (379, 379 / 24), (124, 10.125), (124.0, 124 / 24)])
def test_worker_and_graph_reject_invalid_length_or_timeline(tmp_path, frames, duration):
    payload = encode_batch(_six_jobs(tmp_path), "bad-length")
    payload["jobs"][0].update(frames=frames, duration_seconds=duration)
    with pytest.raises(ValueError):
        validate_batch(payload)
    with pytest.raises(ValueError):
        workflow.build_h3_api_workflow(payload["jobs"][0], "image.png", "bad-length")


def test_postprocessing_preserves_spoken_words():
    host = " ".join(["information"] * 23) + "."
    reporter = "Très drôle."
    value = apply_creative_postprocessing({"host": {}, "segments": [{"host_dialogue": host, "reporter": {"dialogue": reporter}}]}, 1, "wes_anderson", "electric_coral_cyan")
    assert value["segments"][0]["host_dialogue"] == host
    assert value["segments"][0]["reporter"]["dialogue"] == reporter


def test_production_prompt_has_one_spoken_line_in_official_fields(tmp_path):
    for job in _six_jobs(tmp_path):
        assert job.prompt.startswith("For the target video, at 0.00 seconds")
        assert "\n\nintegrated_multimodal_description: [Shot 1]" in job.prompt
        assert "\noverall_soundscape:" in job.prompt
        assert job.prompt.endswith("non_diegetic_music: N/A")
        assert job.prompt.count(job.dialogue) == 1
        assert job.prompt.count("<d>") == job.prompt.count("</d>") == 1
        assert "(S1) says: <d>[French] " in job.prompt
        assert "medium" in job.prompt
        assert "\\n" not in job.prompt
        assert f"{job.duration_seconds:g} seconds" in job.prompt


def test_different_dialogue_lengths_propagate_through_prompt_job_and_graph(tmp_path):
    images = _six_jobs(tmp_path)
    scenario = _scenario()
    scenario.segments[0].host_dialogue = " ".join(["information"] * 20) + "."
    scenario.segments[0].reporter_dialogue = "Très drôle."
    jobs = create_h3_jobs(scenario, images[0].image_path, [job.image_path for job in images[1::2]], Settings(project_root=tmp_path))
    assert [job.frames for job in jobs[:2]] == [226, 124]
    for job in jobs:
        assert f"{job.frames / 24:g} seconds" in job.prompt
        assert job.duration_seconds == job.frames / 24
        assert workflow.build_h3_api_workflow(asdict(job), "image.png", job.id)["104"]["inputs"]["length"] == job.frames


@pytest.mark.parametrize("seed", [0, 424242424242, 2**64 - 1])
def test_native_seed_range_is_preserved(tmp_path, seed):
    jobs = _six_jobs(tmp_path)
    jobs[0] = replace(jobs[0], seed=seed)
    payload = encode_batch(jobs, "native-seed")
    validate_batch(payload)
    assert workflow.build_h3_api_workflow(payload["jobs"][0], "image.png", "seed")["15"]["inputs"]["noise_seed"] == seed


@pytest.mark.parametrize("seed", [-1, 2**64, 42.5, True])
def test_invalid_seed_is_rejected_by_worker_and_graph(tmp_path, seed):
    payload = encode_batch(_six_jobs(tmp_path), "invalid-seed")
    payload["jobs"][0]["seed"] = seed
    with pytest.raises(ValueError):
        validate_batch(payload)
    with pytest.raises(ValueError):
        workflow.build_h3_api_workflow(payload["jobs"][0], "image.png", "seed")
