from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs, urlparse

import modal_h3


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
