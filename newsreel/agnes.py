from __future__ import annotations

import base64
import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .config import Settings
from .creative import (
    DEFAULT_INTENSITY,
    apply_creative_postprocessing,
    build_scenario_prompt,
)
from .models import NewsItem, Scenario


class AgnesError(RuntimeError):
    pass


class AgnesClient:
    """OpenAI-compatible Agnes text/image API adapter; the API key is never written to disk."""

    def __init__(self, settings: Settings, api_key: str):
        key = api_key.strip()
        if not key:
            raise AgnesError("Clé Agnes manquante (champ UI ou variable AGNES_API_KEY).")
        self.settings = settings
        self.api_key = key
        self.base_url = settings.agnes_base_url.rstrip("/")

    def _request(
        self, endpoint: str, payload: dict[str, Any], timeout: int | None = None
    ) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        target = f"{self.base_url}/{endpoint.lstrip('/')}"
        attempts = 3
        last_error: Exception | None = None
        for attempt in range(attempts):
            request = urllib.request.Request(
                target,
                data=body,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "User-Agent": "NewsReel/2.0",
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(
                    request, timeout=timeout or self.settings.agnes_timeout_seconds
                ) as response:
                    data = json.loads(response.read().decode("utf-8"))
                if not isinstance(data, dict):
                    raise AgnesError("Réponse Agnes JSON inattendue.")
                return data
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")[:1200]
                last_error = AgnesError(f"Agnes a répondu HTTP {exc.code}: {detail}")
                if exc.code not in {408, 429, 500, 502, 503, 504} or attempt == attempts - 1:
                    raise last_error from exc
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                last_error = AgnesError(f"Appel Agnes impossible: {exc}")
                if attempt == attempts - 1:
                    raise last_error from exc
            time.sleep(0.75 * (2**attempt))
        raise AgnesError(f"Appel Agnes impossible: {last_error}")

    def write_scenario(
        self,
        news: list[NewsItem],
        count: int,
        director: str,
        palette: str,
        intensity: str = DEFAULT_INTENSITY,
    ) -> Scenario:
        if not 1 <= count <= 7:
            raise AgnesError("Le nombre de sujets doit être compris entre 1 et 7.")
        prompt = build_scenario_prompt(news, count, director, palette, intensity)
        available = {item.title: item for item in news if item.title}
        last_error: Exception | None = None

        for attempt in range(2):
            correction = ""
            if last_error is not None:
                correction = (
                    "\n\nCORRECTION REQUIRED AFTER INVALID OUTPUT:\n"
                    f"{last_error}\n"
                    f"Return a completely valid replacement with EXACTLY {count} distinct segments, "
                    "each using one exact supplied HEADLINE and no invented factual claim."
                )
            response = self._request(
                "chat/completions",
                {
                    "model": self.settings.agnes_text_model,
                    "temperature": 0.65 if attempt == 0 else 0.35,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": "Réponds uniquement avec du JSON valide."},
                        {"role": "user", "content": prompt + correction},
                    ],
                },
            )
            try:
                content = response["choices"][0]["message"]["content"]
                if isinstance(content, list):
                    content = "".join(
                        str(part.get("text", "")) if isinstance(part, dict) else str(part)
                        for part in content
                    )
                text = str(content).strip()
                text = re.sub(r"^\`\`\`(?:json)?\s*|\s*\`\`\`$", "", text, flags=re.IGNORECASE)
                raw_value = json.loads(text)
                if not isinstance(raw_value, dict):
                    raise ValueError("la racine JSON doit être un objet")
                value = apply_creative_postprocessing(
                    raw_value,
                    count,
                    director=director,
                    palette=palette,
                    intensity=intensity,
                )
                scenario = Scenario.from_mapping(value)
                seen_titles: set[str] = set()
                for segment in scenario.segments:
                    match = available.get(segment.title) or available.get(segment.source_title)
                    if match is None:
                        raise ValueError(
                            f"headline non fourni par Google News: {segment.title!r}"
                        )
                    if match.title in seen_titles:
                        raise ValueError(f"headline dupliqué dans le JT: {match.title!r}")
                    seen_titles.add(match.title)
                    segment.title = match.title
                    segment.source_title = match.title
                    segment.source_url = match.url
                    if not segment.summary:
                        segment.summary = match.summary
                return scenario
            except (KeyError, IndexError, TypeError, json.JSONDecodeError, ValueError) as exc:
                last_error = exc

        raise AgnesError(
            "Le scénario Agnes reste invalide après une correction automatique: "
            f"{last_error}"
        )

    def generate_image(self, prompt: str, destination: Path, size: str | None = None) -> Path:
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        response = self._request(
            "images/generations",
            {
                "model": self.settings.agnes_image_model,
                "prompt": prompt,
                "size": size or self.settings.agnes_image_size,
                "ratio": self.settings.agnes_image_ratio,
                "n": 1,
            },
            timeout=max(self.settings.agnes_timeout_seconds, 300),
        )
        try:
            item = response["data"][0]
        except (KeyError, IndexError, TypeError) as exc:
            raise AgnesError("Réponse image Agnes sans data[0].") from exc
        encoded = item.get("b64_json")
        if encoded:
            try:
                content = base64.b64decode(encoded, validate=True)
            except ValueError as exc:
                raise AgnesError("L'image base64 reçue d'Agnes est invalide.") from exc
        else:
            url = item.get("url")
            if not url:
                raise AgnesError("Réponse image Agnes sans URL ni b64_json.")
            request = urllib.request.Request(url, headers={"User-Agent": "NewsReel/2.0"})
            try:
                with urllib.request.urlopen(request, timeout=180) as image_response:
                    content = image_response.read()
            except (urllib.error.URLError, TimeoutError) as exc:
                raise AgnesError(f"Téléchargement de l'image Agnes échoué: {exc}") from exc
        if not content:
            raise AgnesError("Agnes a renvoyé une image vide.")
        try:
            from io import BytesIO

            from PIL import Image

            with Image.open(BytesIO(content)) as image:
                image.convert("RGB").save(destination, format="PNG", optimize=True)
        except Exception as exc:
            raise AgnesError(f"Le fichier image Agnes est illisible: {exc}") from exc
        return destination
