from __future__ import annotations

import base64
from pathlib import Path

import pytest

from modal_h3 import validate_batch
from newsreel.comfy_workflow import patch_api_workflow
from newsreel.config import Settings
from newsreel.h3_worker_contract import (
    H3RendererError,
    ModalH3Renderer,
    build_reporter_prompt,
    create_h3_jobs,
    encode_batch,
)
from newsreel.models import Segment


def test_reporter_prompt_keeps_exact_dialogue_and_stability_constraints(tmp_path: Path) -> None:
    segment = Segment(
        id="subject-0",
        title="Le point du jour",
        host_dialogue="Une introduction.",
        reporter_dialogue="Texte exact du reporter, sans paraphrase.",
    )
    image = tmp_path / "reporter.png"
    image.write_bytes(b"fake image")
    prompt = build_reporter_prompt(segment)
    assert "<d>[French] Texte exact du reporter, sans paraphrase.</d>" in prompt
    assert "Keep facial features and anatomy stable" in prompt
    assert "no generated subtitles" in prompt
    jobs = create_h3_jobs([segment], [image], Settings(project_root=tmp_path))
    assert len(jobs) == 1
    assert (jobs[0].width, jobs[0].height, jobs[0].fps, jobs[0].frames, jobs[0].steps) == (
        768,
        1344,
        24,
        243,
        8,
    )


def test_batch_contract_uses_one_batch_and_exact_validated_settings(tmp_path: Path) -> None:
    segments = [
        Segment(f"subject-{i}", f"Sujet {i}", "Intro", f"Dialogue français {i}.") for i in range(3)
    ]
    images = []
    for i in range(3):
        image = tmp_path / f"{i}.png"
        image.write_bytes(f"fixture-{i}".encode())
        images.append(image)
    jobs = create_h3_jobs(segments, images, Settings(project_root=tmp_path))
    workflow = {"1": {"class_type": "LoadImage", "inputs": {"image": "x.png"}}}
    payload = encode_batch(jobs, workflow)
    assert len(payload["jobs"]) == 3
    assert payload["config"] == {
        "width": 768,
        "height": 1344,
        "fps": 24,
        "frames": 243,
        "duration_seconds": 10.125,
        "steps": 8,
        "native_audio": True,
        "video_sparse_attention": True,
        "modal_gpu": "L40S",
        "volume_name": "fasth3-models",
    }
    assert base64.b64decode(payload["jobs"][0]["image_base64"]) == b"fixture-0"
    assert "<d>[French] Dialogue français 0.</d>" in payload["jobs"][0]["prompt"]


def test_worker_patches_only_per_job_values_and_preserves_model_graph() -> None:
    api_workflow = {
        "1": {"class_type": "LoadImage", "inputs": {"image": "old.png"}},
        "4": {
            "class_type": "BlockSparseAttention",
            "inputs": {"selection": "vsa", "model": "FastH3 8-Step V2"},
        },
        "2": {
            "class_type": "MiniMaxH3ImageToVideo",
            "inputs": {
                "prompt": "old",
                "width": 1024,
                "height": 768,
                "length": 121,
                "steps": 8,
                "first_frame": ["1", 0],
                "vae_name": "validated-vae.safetensors",
            },
        },
        "3": {"class_type": "SaveVideo", "inputs": {"video": ["2", 0], "filename_prefix": "old"}},
    }
    job = {"prompt": "French dialogue prompt", "width": 768, "height": 1344}
    patched = patch_api_workflow(api_workflow, job, "upload.png", "newsreel/reporter-0")
    assert patched["1"]["inputs"]["image"] == "upload.png"
    assert patched["2"]["inputs"]["prompt"] == "French dialogue prompt"
    assert (patched["2"]["inputs"]["width"], patched["2"]["inputs"]["height"]) == (768, 1344)
    assert patched["2"]["inputs"]["length"] == 243
    assert patched["2"]["inputs"]["steps"] == 8
    assert patched["2"]["inputs"]["vae_name"] == "validated-vae.safetensors"
    assert patched["3"]["inputs"]["filename_prefix"] == "newsreel/reporter-0"
    assert api_workflow["2"]["inputs"]["width"] == 1024


def test_worker_rejects_workflow_that_drops_vsa() -> None:
    workflow = {
        "1": {"class_type": "LoadImage", "inputs": {"image": "old.png"}},
        "2": {
            "class_type": "MiniMaxH3ImageToVideo",
            "inputs": {"prompt": "old", "width": 768, "height": 1344, "length": 243},
        },
        "3": {"class_type": "SaveVideo", "inputs": {"filename_prefix": "old"}},
    }
    job = {"prompt": "French dialogue prompt"}
    with pytest.raises(ValueError, match="VSA"):
        patch_api_workflow(workflow, job, "upload.png", "newsreel/reporter-0")


def test_modal_batch_validator_rejects_wrong_resolution() -> None:
    payload = {
        "contract_version": 1,
        "config": {"width": 720},
        "workflow": {"1": {}},
        "jobs": [{}],
    }
    with pytest.raises(ValueError, match="width"):
        validate_batch(payload)


def test_missing_validated_workflow_fails_clearly(tmp_path: Path) -> None:
    job = object()
    renderer = ModalH3Renderer("test-app", "render_h3_batch", None)
    with pytest.raises(H3RendererError, match="fasth3_push_test.py"):
        renderer.render_batch([job])
