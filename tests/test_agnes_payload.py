from __future__ import annotations

import base64
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image

from newsreel.agnes import AgnesClient
from newsreel.config import Settings


def test_agnes_image_request_uses_validated_payload_without_network(
    tmp_path: Path, monkeypatch
) -> None:
    image_buffer = BytesIO()
    Image.new("RGB", (4, 6), color=(20, 80, 140)).save(image_buffer, format="PNG")
    image_base64 = base64.b64encode(image_buffer.getvalue()).decode("ascii")
    settings = Settings(project_root=tmp_path)
    client = AgnesClient(settings, "offline-test-key")
    captured: list[tuple[str, dict[str, Any]]] = []

    def fake_request(endpoint: str, payload: dict[str, Any], timeout: int | None = None):
        captured.append((endpoint, payload))
        return {"data": [{"b64_json": image_base64}]}

    monkeypatch.setattr(client, "_request", fake_request)
    client.generate_image("A restrained French field reporter.", tmp_path / "reporter.png")

    assert captured == [
        (
            "images/generations",
            {
                "model": "agnes-image-2.5-flash",
                "prompt": "A restrained French field reporter.",
                "size": "1K",
                "ratio": "9:16",
                "n": 1,
            },
        )
    ]
