from __future__ import annotations

import base64
import dataclasses
import sys
import types
from pathlib import Path

import pytest

from modal_h3 import COMFYUI_REPOSITORY, build_h3_api_workflow, validate_batch
from newsreel.config import Settings
from newsreel.h3_worker_contract import (
    H3RendererError,
    ModalH3Renderer,
    build_host_prompt,
    build_reporter_prompt,
    create_h3_jobs,
    encode_batch,
)
from newsreel.h3_workflow import (
    H3_ATTENTION_BACKEND,
    H3_MODEL_FILES,
    H3_SIGMA_SHIFT,
    H3_VSA_SETTINGS,
    h3_contract_config,
)
from newsreel.models import Scenario


def _scenario() -> Scenario:
    return Scenario.from_mapping(
        {
            "title": "JT créatif",
            "host": {
                "name": "Alice",
                "description": "retrofuturistic anchor with chrome glasses",
                "plateau": "hallucinatory retrofuturistic TV set",
                "host_action": "a giant chrome dial spins",
                "stanislavski": {
                    "objective": "deliver the news",
                    "obstacle": "the absurd studio",
                },
            },
            "creative": {
                "director": "wes_anderson",
                "palette": "electric_coral_cyan",
                "intensity": "strong",
            },
            "segments": [
                {
                    "id": f"subject-{i}",
                    "headline": f"Sujet {i}",
                    "host_dialogue": f"Information factuelle exacte numéro {i} annoncée sur le plateau.",
                    "host_action": "a giant chrome dial spins behind the host",
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
                        "name": f"Reporter {i}",
                        "description": "retro-futuristic field reporter",
                        "dialogue": f"Même la machine réclame son temps de parole numéro {i} aujourd'hui.",
                    },
                }
                for i in range(3)
            ],
        }
    )


def _six_jobs(tmp_path: Path):
    scenario = _scenario()
    host = tmp_path / "host.png"
    host.write_bytes(b"fixture-host")
    images = []
    for i in range(3):
        image = tmp_path / f"reporter-{i}.png"
        image.write_bytes(f"fixture-image-{i}".encode())
        images.append(image)
    return create_h3_jobs(scenario, host, images, Settings(project_root=tmp_path))


def test_full_h3_prompts_keep_creativity_dialogue_and_stability(tmp_path: Path) -> None:
    scenario = _scenario()
    host_prompt = build_host_prompt(scenario, scenario.segments[0])
    reporter_prompt = build_reporter_prompt(scenario.segments[0])
    for prompt in (host_prompt, reporter_prompt):
        assert "Preserve the same face, hairstyle, costume, set design" in prompt
        assert "Keep anatomy, faces, hands and fingers coherent" in prompt
        assert "Avoid morphing, duplication, identity drift" in prompt
        assert "<d>[French] " in prompt
    assert "VISUAL GAG" in host_prompt
    assert "RETROFUTURIST STUDIO" in host_prompt
    assert "COMPLETE COMEDIC FIELD-REPORT SKETCH" in reporter_prompt
    assert "FULL VISUAL GAG" in reporter_prompt

    jobs = _six_jobs(tmp_path)
    assert [job.id for job in jobs] == [
        "host-0",
        "reporter-0",
        "host-1",
        "reporter-1",
        "host-2",
        "reporter-2",
    ]
    assert all(
        (job.width, job.height, job.fps, job.frames, job.steps) == (768, 1344, 24, 243, 8)
        for job in jobs
    )


def test_api_graph_contains_exact_models_dimensions_sampling_vsa_and_native_audio(
    tmp_path: Path,
) -> None:
    assert COMFYUI_REPOSITORY == "https://github.com/Comfy-Org/ComfyUI.git"
    jobs = _six_jobs(tmp_path)
    job = jobs[0]
    graph = build_h3_api_workflow(
        dataclasses.asdict(job), "host.png", "newsreel/test-run/host-0"
    )

    assert graph["6"]["inputs"]["unet_name"] == (
        "fastvideo_fasth3_8step_v2_pruned_int8_convrot.safetensors"
    )
    assert graph["13"]["inputs"] == {
        "clip_name": "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
        "type": "minimax",
        "device": "default",
    }
    assert graph["11"]["inputs"]["vae_name"] == "minimax_h3_video_vae_int8_convrot.safetensors"
    assert graph["24"]["inputs"]["vae_name"] == "minimax_h3_audio_vae_fp32.safetensors"
    assert H3_MODEL_FILES == {
        "unet": "fastvideo_fasth3_8step_v2_pruned_int8_convrot.safetensors",
        "clip": "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
        "video_vae": "minimax_h3_video_vae_int8_convrot.safetensors",
        "audio_vae": "minimax_h3_audio_vae_fp32.safetensors",
    }

    h3_inputs = graph["104"]["inputs"]
    assert (h3_inputs["width"], h3_inputs["height"], h3_inputs["length"]) == (768, 1344, 243)
    assert h3_inputs["first_frame"] == ["1", 0]
    assert graph["91"]["inputs"]["fps"] == 24
    assert graph["9"]["inputs"]["scheduler"] == "simple"
    assert graph["9"]["inputs"]["steps"] == 8
    assert graph["9"]["inputs"]["denoise"] == 1
    assert graph["17"]["inputs"]["sampler_name"] == "res_multistep"
    assert graph["128"]["inputs"]["attention"] == H3_ATTENTION_BACKEND
    assert graph["127"]["inputs"] == {"model": ["128", 0], **H3_VSA_SETTINGS}
    assert graph["143"]["inputs"] == {"model": ["6", 0], **H3_SIGMA_SHIFT}
    assert graph["23"]["class_type"] == "VAEDecodeAudio"
    assert graph["91"]["inputs"]["audio"] == ["23", 0]
    assert graph["15"]["inputs"] == {"noise_seed": job.seed}
    assert graph["92"]["class_type"] == "SaveVideo"
    assert graph["92"]["inputs"] == {
        "video": ["91", 0],
        "filename_prefix": "newsreel/test-run/host-0",
        "format": "auto",
        "codec": "auto",
    }


def test_batch_contract_contains_six_clips_but_no_external_workflow(tmp_path: Path) -> None:
    jobs = _six_jobs(tmp_path)
    payload = encode_batch(jobs, "run-123")
    assert len(payload["jobs"]) == 6
    assert "workflow" not in payload
    assert payload["run_id"] == "run-123"
    assert payload["config"] == h3_contract_config()
    assert payload["config"]["frames"] == 243
    assert payload["config"]["fps"] == 24
    assert payload["config"]["steps"] == 8
    assert payload["config"]["native_audio"] is True
    assert payload["config"]["modal_gpu"] == "L40S"
    assert payload["config"]["modal_cpu"] == 8
    assert payload["config"]["modal_memory_mib"] == 98304
    assert payload["config"]["modal_timeout_seconds"] >= 3600
    assert payload["config"]["modal_max_containers"] == 1
    assert payload["config"]["single_use_containers"] is True
    assert payload["config"]["vsa"]["selection"] == "vsa"
    assert base64.b64decode(payload["jobs"][0]["image_base64"]) == b"fixture-host"
    assert payload["jobs"][0]["id"] == "host-0"
    assert payload["jobs"][1]["id"] == "reporter-0"


def test_modal_worker_validates_builtin_graph_contract_and_rejects_external_workflow(
    tmp_path: Path,
) -> None:
    payload = encode_batch(_six_jobs(tmp_path), "run-123")
    assert len(validate_batch(payload)) == 6

    wrong_resolution = {**payload, "config": {**payload["config"], "width": 720}}
    with pytest.raises(ValueError, match="width"):
        validate_batch(wrong_resolution)

    with_external_workflow = {**payload, "workflow": {"1": {}}}
    with pytest.raises(ValueError, match="JSON workflow externe"):
        validate_batch(with_external_workflow)


def test_modal_renderer_uses_one_remote_call_for_six_clips(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    jobs = _six_jobs(tmp_path)
    remote_calls: list[dict] = []
    function_lookups: list[tuple[str, str]] = []

    class FakeRemote:
        def remote(self, payload):
            remote_calls.append(payload)
            return {
                "videos": {
                    job.id: {"data_base64": base64.b64encode(f"mp4-{job.id}".encode()).decode()}
                    for job in jobs
                },
                "h3_generation_seconds": 61.0,
            }

    class FakeFunction:
        @staticmethod
        def from_name(app_name, function_name):
            function_lookups.append((app_name, function_name))
            return FakeRemote()

    monkeypatch.setitem(sys.modules, "modal", types.SimpleNamespace(Function=FakeFunction))
    renderer = ModalH3Renderer("test-app", "render_h3_batch")
    result = renderer.render_batch(jobs, run_id="run-123")

    assert function_lookups == [("test-app", "render_h3_batch")]
    assert len(remote_calls) == 1
    assert len(remote_calls[0]["jobs"]) == 6
    assert result.videos == {job.id: f"mp4-{job.id}".encode() for job in jobs}
    assert result.generation_seconds == 61.0


def test_batch_rejects_invalid_count_and_run_id(tmp_path: Path) -> None:
    jobs = _six_jobs(tmp_path)
    with pytest.raises(H3RendererError, match="run"):
        encode_batch(jobs, "../unsafe")
    with pytest.raises(H3RendererError, match="quatorze"):
        encode_batch([], "run-123")
