from __future__ import annotations

import asyncio
from pathlib import Path

import httpx

from bridge import create_app
from newsreel.config import Settings


def test_local_endpoints_and_explicit_missing_credentials(tmp_path: Path, monkeypatch) -> None:
    import importlib.util

    real_find_spec = importlib.util.find_spec
    monkeypatch.setattr(
        "bridge.importlib.util.find_spec",
        lambda name: None if name == "modal" else real_find_spec(name),
    )
    repo_root = Path(__file__).resolve().parents[1]
    settings = Settings(project_root=repo_root, output_dir=tmp_path / "output")
    app = create_app(settings)

    async def exercise() -> None:
        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                health = await client.get("/health")
                assert health.status_code == 200
                assert health.json()["service"] == "newsreel-local-bridge"
                assert health.json()["version"] == "2"
                assert health.json()["h3_graph_built_in"] is True
                assert (await client.get("/")).status_code == 200

                config = (await client.get("/config")).json()
                assert config["width"] == 1080
                assert config["height"] == 1920
                assert config["agnes_text_model"] == "agnes-2.5-flash"
                assert config["agnes_image_model"] == "agnes-image-2.5-flash"
                assert config["agnes_image_size"] == "1K"
                assert config["agnes_image_ratio"] == "9:16"
                assert config["full_h3"] is True
                assert config["h3_clips_per_subject"] == 2
                assert len(config["creative"]["directors"]) == 25
                assert len(config["creative"]["palettes"]) == 16

                recent = await client.get("/runs")
                assert recent.status_code == 200
                assert recent.json() == {"runs": []}

                assert (await client.get("/run/absent")).status_code == 404
                missing_key = await client.post(
                    "/runs", json={"query": "actualité France", "count": 3}
                )
                assert missing_key.status_code == 400
                assert "Agnes" in missing_key.json()["detail"]

                invalid_style = await client.post(
                    "/runs",
                    json={
                        "query": "actualité France",
                        "count": 3,
                        "agnes_api_key": "not-a-real-key",
                        "director": "unknown",
                    },
                )
                assert invalid_style.status_code == 422

                blocked_before_agnes = await client.post(
                    "/runs",
                    json={
                        "query": "actualité France",
                        "count": 3,
                        "agnes_api_key": "not-a-real-key",
                    },
                )
                assert blocked_before_agnes.status_code == 409
                assert any(
                    marker in blocked_before_agnes.json()["detail"]
                    for marker in ("FFmpeg", "Modal")
                )

    asyncio.run(exercise())
