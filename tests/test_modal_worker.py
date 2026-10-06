from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

import modal_h3
from newsreel.h3_workflow import H3_MODEL_FILES


class _FakeResponse:
    def __init__(self, content: bytes):
        self.content = content

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self) -> bytes:
        return self.content


def test_history_reads_savevideo_previewvideo_images_and_mismatched_history_key(
    monkeypatch,
) -> None:
    filename = "reporter-0_00001.mp4"
    subfolder = "newsreel/run-1/reporter-0"
    monkeypatch.setattr(
        modal_h3,
        "_http_json",
        lambda *_args, **_kwargs: {
            "different-history-key": {
                "status": {"status_str": "success", "completed": True},
                "outputs": {
                    "92": {
                        "images": [
                            {
                                "filename": filename,
                                "subfolder": subfolder,
                                "type": "output",
                                "animated": True,
                            }
                        ]
                    }
                },
            }
        },
    )
    requested_urls: list[str] = []

    def fake_urlopen(url, timeout=0):
        requested_urls.append(str(url))
        return _FakeResponse(b"savevideo-mp4")

    monkeypatch.setattr(modal_h3.urllib.request, "urlopen", fake_urlopen)

    content, identified_filename, completed = modal_h3._history_video("requested-prompt-id")

    assert completed is True
    assert content == b"savevideo-mp4"
    assert identified_filename == filename
    query = parse_qs(urlparse(requested_urls[0]).query)
    assert query == {"filename": [filename], "subfolder": [subfolder], "type": ["output"]}


def test_wait_for_video_falls_back_to_unique_prefix_in_comfy_output(
    tmp_path: Path, monkeypatch
) -> None:
    comfy_dir = tmp_path / "ComfyUI"
    prefix = "newsreel/run-1/reporter-0"
    output_dir = comfy_dir / "output" / "newsreel" / "run-1"
    output_dir.mkdir(parents=True)
    video_path = output_dir / "reporter-0_00001.mp4"
    video_path.write_bytes(b"filesystem-mp4")
    monkeypatch.setattr(modal_h3, "COMFYUI_DIR", comfy_dir)
    monkeypatch.setattr(modal_h3, "_history_video", lambda _prompt_id: (None, None, False))
    active_checks = iter((True, False, False))
    monkeypatch.setattr(modal_h3, "_prompt_is_active", lambda _prompt_id: next(active_checks))
    monkeypatch.setattr(modal_h3.time, "sleep", lambda _seconds: None)

    content, filename = modal_h3._wait_for_video("prompt-id", prefix, timeout_seconds=5)

    assert content == b"filesystem-mp4"
    assert filename == video_path.name


def _prepare_model_mount(tmp_path: Path, missing: str | None = None) -> tuple[Path, Path]:
    volume_root = tmp_path / "fasth3-models"
    comfy_dir = tmp_path / "ComfyUI"
    model_root = comfy_dir / "models"
    placeholders = {
        "diffusion_models": "put_diffusion_model_files_here",
        "text_encoders": "put_text_encoder_files_here",
        "vae": "put_vae_here",
    }
    for category, placeholder in placeholders.items():
        placeholder_path = model_root / category / placeholder
        placeholder_path.parent.mkdir(parents=True, exist_ok=True)
        placeholder_path.write_text("ComfyUI placeholder", encoding="utf-8")

    sources = (
        ("diffusion_models", H3_MODEL_FILES["unet"]),
        ("text_encoders", H3_MODEL_FILES["clip"]),
        ("vae", H3_MODEL_FILES["video_vae"]),
        ("vae", H3_MODEL_FILES["audio_vae"]),
    )
    for category, filename in sources:
        if filename == missing:
            continue
        source = volume_root / category / filename
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(b"fake model")
    return volume_root, comfy_dir


def test_mount_volume_models_links_only_exact_weight_files_and_keeps_placeholders(
    tmp_path: Path, monkeypatch
) -> None:
    volume_root, comfy_dir = _prepare_model_mount(tmp_path)
    monkeypatch.setattr(modal_h3, "MODELS_ROOT", volume_root)
    monkeypatch.setattr(modal_h3, "COMFYUI_DIR", comfy_dir)

    modal_h3._mount_volume_models()

    sources = (
        ("diffusion_models", H3_MODEL_FILES["unet"]),
        ("text_encoders", H3_MODEL_FILES["clip"]),
        ("vae", H3_MODEL_FILES["video_vae"]),
        ("vae", H3_MODEL_FILES["audio_vae"]),
    )
    for category, filename in sources:
        destination_dir = comfy_dir / "models" / category
        destination = destination_dir / filename
        source = volume_root / category / filename
        assert destination.is_symlink()
        assert destination.resolve() == source.resolve()
        assert destination_dir.is_dir()
        assert not destination_dir.is_symlink()

    assert (comfy_dir / "models" / "diffusion_models" / "put_diffusion_model_files_here").read_text(
        encoding="utf-8"
    ) == "ComfyUI placeholder"
    assert (comfy_dir / "models" / "text_encoders" / "put_text_encoder_files_here").read_text(
        encoding="utf-8"
    ) == "ComfyUI placeholder"
    assert (comfy_dir / "models" / "vae" / "put_vae_here").read_text(encoding="utf-8") == (
        "ComfyUI placeholder"
    )
    assert not (comfy_dir / "models" / "loras").exists()
    assert not (comfy_dir / "models" / "clip").exists()
    assert not (comfy_dir / "models" / "checkpoints").exists()

    # A repeat invocation accepts the already-correct file symlinks.
    modal_h3._mount_volume_models()


def test_mount_volume_models_fails_before_linking_when_an_exact_source_is_missing(
    tmp_path: Path, monkeypatch
) -> None:
    missing = H3_MODEL_FILES["audio_vae"]
    volume_root, comfy_dir = _prepare_model_mount(tmp_path, missing=missing)
    monkeypatch.setattr(modal_h3, "MODELS_ROOT", volume_root)
    monkeypatch.setattr(modal_h3, "COMFYUI_DIR", comfy_dir)

    with pytest.raises(RuntimeError, match=missing):
        modal_h3._mount_volume_models()

    assert not any(
        (comfy_dir / "models" / category / filename).is_symlink()
        for category, filename in (
            ("diffusion_models", H3_MODEL_FILES["unet"]),
            ("text_encoders", H3_MODEL_FILES["clip"]),
            ("vae", H3_MODEL_FILES["video_vae"]),
            ("vae", H3_MODEL_FILES["audio_vae"]),
        )
    )


@pytest.mark.parametrize("conflict_type", ["file", "symlink"])
def test_mount_volume_models_refuses_to_overwrite_an_incorrect_destination(
    tmp_path: Path, monkeypatch, conflict_type: str
) -> None:
    volume_root, comfy_dir = _prepare_model_mount(tmp_path)
    monkeypatch.setattr(modal_h3, "MODELS_ROOT", volume_root)
    monkeypatch.setattr(modal_h3, "COMFYUI_DIR", comfy_dir)
    destination = comfy_dir / "models" / "vae" / H3_MODEL_FILES["video_vae"]
    if conflict_type == "file":
        destination.write_text("do not overwrite", encoding="utf-8")
    else:
        wrong_target = tmp_path / "wrong-model.safetensors"
        wrong_target.write_bytes(b"wrong model")
        destination.symlink_to(wrong_target)

    with pytest.raises(RuntimeError, match="refus"):
        modal_h3._mount_volume_models()

    if conflict_type == "file":
        assert destination.read_text(encoding="utf-8") == "do not overwrite"
    else:
        assert destination.is_symlink()
        assert destination.resolve() == wrong_target.resolve()
