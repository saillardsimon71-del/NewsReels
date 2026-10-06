from __future__ import annotations

import asyncio
from pathlib import Path

import httpx

from bridge import create_app
from newsreel.config import Settings


def test_local_endpoints_and_explicit_missing_credentials(tmp_path: Path) -> None:
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
                assert (await client.get("/")).status_code == 200
                config = (await client.get("/config")).json()
                assert config["width"] == 1080
                assert config["height"] == 1920
                assert (await client.get("/run/absent")).status_code == 404
                missing_key = await client.post(
                    "/runs", json={"query": "actualité France", "count": 3}
                )
                assert missing_key.status_code == 400
                assert "Agnes" in missing_key.json()["detail"]
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
                    for marker in ("avant tout appel Agnes/Modal", "FFmpeg", "Workflow API FastH3")
                )

    asyncio.run(exercise())
