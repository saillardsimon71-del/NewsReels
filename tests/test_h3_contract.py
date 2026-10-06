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
from newsreel.models import Segment


def _three_jobs(tmp_path: Path):
    segments = [
        Segment(
            f"subject-{i}",
            f"Sujet {i}",
            "Introduction plateau",
            f"Dialogue français exact {i}.",
            reporter_action=(
                "Le reporter se tourne légèrement vers le chantier." if i == 0 else ""
            ),
        )
        for i in range(3)
    ]
    images = []
    for i in range(3):
        image = tmp_path / f"reporter-{i}.png"
        image.write_bytes(f"fixture-image-{i}".encode())
        images.append(image)
    return create_h3_jobs(segments, images, Settings(project_root=tmp_path))


def test_reporter_prompt_keeps_exact_dialogue_action_and_stability_constraints(
    tmp_path: Path,
) -> None:
    segment = Segment(
        id="subject-0",
        title="Le point du jour",
        host_dialogue="Une introduction.",
        reporter_dialogue="Texte exact du reporter, sans paraphrase.",
        reporter_action="Le reporter se tourne légèrement vers le chantier.",
    )
    prompt = build_reporter_prompt(segment)
    assert "Preserve exactly the reporter's identity, face, hairstyle, clothing" in prompt
    assert "Keep anatomy and facial features stable" in prompt
    assert "controlled, nearly locked camera" in prompt
    assert "Do not morph or duplicate people or body parts" in prompt
    assert "visible text" in prompt and "subtitles" in prompt
    assert "Le reporter se tourne légèrement vers le chantier." in prompt
    assert prompt.endswith(
        "The reporter has a clear natural French voice (S1).\n"
        "<d>[French] Texte exact du reporter, sans paraphrase.</d>"
    )

    image = tmp_path / "reporter.png"
    image.write_bytes(b"fake image")
    jobs = create_h3_jobs([segment], [image], Settings(project_root=tmp_path))
    assert len(jobs) == 1
    assert (jobs[0].width, jobs[0].height, jobs[0].fps, jobs[0].frames, jobs[0].steps) == (
        768,
        1344,
        24,
        243,
        8,
    )


def test_api_graph_contains_exact_models_dimensions_sampling_vsa_and_native_audio(
    tmp_path: Path,
) -> None:
    assert COMFYUI_REPOSITORY == "https://github.com/Comfy-Org/ComfyUI.git"
    jobs = _three_jobs(tmp_path)
    job = jobs[0]
    graph = build_h3_api_workflow(
        dataclasses.asdict(job), "reporter-0.png", "newsreel/test-run/reporter-0"
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
        "filename_prefix": "newsreel/test-run/reporter-0",
        "format": "auto",
        "codec": "auto",
    }

    other_graph = build_h3_api_workflow(
        {
            "prompt": jobs[1].prompt,
            "seed": jobs[1].seed,
            "width": 768,
            "height": 1344,
            "fps": 24,
            "frames": 243,
            "duration_seconds": 10.125,
            "steps": 8,
        },
        "reporter-1.png",
        "newsreel/test-run/reporter-1",
    )
    # The same ComfyUI loader nodes and inputs are reused while each reporter is processed.
    for node_id in ("6", "13", "11", "24", "143", "128", "127"):
        assert graph[node_id] == other_graph[node_id]


def test_batch_contract_contains_three_reporters_but_no_external_workflow(tmp_path: Path) -> None:
    jobs = _three_jobs(tmp_path)
    payload = encode_batch(jobs, "run-123")
    assert len(payload["jobs"]) == 3
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
    assert base64.b64decode(payload["jobs"][0]["image_base64"]) == b"fixture-image-0"
    assert "<d>[French] Dialogue français exact 0.</d>" in payload["jobs"][0]["prompt"]


def test_modal_worker_validates_builtin_graph_contract_and_rejects_external_workflow(
    tmp_path: Path,
) -> None:
    payload = encode_batch(_three_jobs(tmp_path), "run-123")
    assert len(validate_batch(payload)) == 3

    wrong_resolution = {**payload, "config": {**payload["config"], "width": 720}}
    with pytest.raises(ValueError, match="width"):
        validate_batch(wrong_resolution)

    with_external_workflow = {**payload, "workflow": {"1": {}}}
    with pytest.raises(ValueError, match="JSON workflow externe"):
        validate_batch(with_external_workflow)


def test_modal_renderer_uses_one_remote_call_for_three_reporters(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    jobs = _three_jobs(tmp_path)
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
                "h3_generation_seconds": 30.5,
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
    assert remote_calls[0]["run_id"] == "run-123"
    assert len(remote_calls[0]["jobs"]) == 3
    assert "workflow" not in remote_calls[0]
    assert result.videos == {job.id: f"mp4-{job.id}".encode() for job in jobs}
    assert result.generation_seconds == 30.5


def test_agnes_model_defaults_and_settings_need_no_workflow_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("AGNES_TEXT_MODEL", raising=False)
    monkeypatch.delenv("AGNES_IMAGE_MODEL", raising=False)
    monkeypatch.delenv("AGNES_IMAGE_SIZE", raising=False)
    monkeypatch.delenv("AGNES_IMAGE_RATIO", raising=False)
    settings = Settings.from_env(project_root=tmp_path)
    assert settings.agnes_text_model == "agnes-2.5-flash"
    assert settings.agnes_image_model == "agnes-image-2.5-flash"
    assert settings.agnes_image_size == "1K"
    assert settings.agnes_image_ratio == "9:16"
    assert not hasattr(settings, "h3_workflow_path")
    assert not hasattr(ModalH3Renderer("app", "function"), "workflow_path")


def test_batch_rejects_invalid_count_and_run_id(tmp_path: Path) -> None:
    jobs = _three_jobs(tmp_path)
    with pytest.raises(H3RendererError, match="run"):
        encode_batch(jobs, "../unsafe")
    with pytest.raises(H3RendererError, match="un à six"):
        encode_batch([], "run-123")
