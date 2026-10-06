from __future__ import annotations

import base64
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from .config import Settings
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
        request = urllib.request.Request(
            f"{self.base_url}/{endpoint.lstrip('/')}",
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "NewsReel/1.0",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(
                request, timeout=timeout or self.settings.agnes_timeout_seconds
            ) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:1200]
            raise AgnesError(f"Agnes a répondu HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise AgnesError(f"Appel Agnes impossible: {exc}") from exc
        if not isinstance(data, dict):
            raise AgnesError("Réponse Agnes JSON inattendue.")
        return data

    def write_scenario(self, news: list[NewsItem], count: int) -> Scenario:
        compact_news = [
            {
                "title": item.title,
                "source": item.source,
                "published": item.published,
                "summary": item.summary,
                "url": item.url,
            }
            for item in news[: max(count, count * 3)]
        ]
        prompt = (
            "Tu es le rédacteur en chef d'un journal télévisé français, factuel et concis. "
            "Écris un scénario de JT vertical pour un présentateur plateau et un reporter par sujet. "
            f"Sélectionne exactement {count} sujets dans les articles fournis. N'invente aucun fait; "
            "n'ajoute des détails que s'ils sont présents dans les sources. "
            "Pour chaque sujet, fournis un host_dialogue de 10 à 18 mots pour l'introduction plateau, "
            "et un reporter_dialogue de 20 à 28 mots, prononçable en français en 8 à 10 secondes. "
            "Le texte reporter sera prononcé exactement par la voix native H3. "
            "Fournis aussi un reporter_image_prompt en anglais, photoréaliste, sobre, sans texte, "
            "pour un reporter sur le terrain cohérent avec l'article. "
            "Retourne uniquement un objet JSON, sans markdown, selon ce schéma: "
            '{"title":"...","host_image_prompt":"...","segments":[{"id":"subject-0",'
            '"title":"...","source_title":"...","source_url":"...",'
            '"host_dialogue":"...","reporter_dialogue":"...",'
            '"reporter_image_prompt":"...","reporter_action":"..."}]}\n\n'
            f"Articles RSS:\n{json.dumps(compact_news, ensure_ascii=False, indent=2)}"
        )
        response = self._request(
            "chat/completions",
            {
                "model": self.settings.agnes_text_model,
                "temperature": 0.4,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": "Réponds uniquement avec du JSON valide."},
                    {"role": "user", "content": prompt},
                ],
            },
        )
        try:
            content = response["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise AgnesError("Réponse texte Agnes sans choices[0].message.content.") from exc
        if isinstance(content, list):
            content = "".join(
                str(part.get("text", "")) if isinstance(part, dict) else str(part)
                for part in content
            )
        text = str(content).strip()
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE)
        try:
            value = json.loads(text)
            scenario = Scenario.from_mapping(value)
        except (json.JSONDecodeError, ValueError, TypeError) as exc:
            raise AgnesError(
                f"Le scénario Agnes n'est pas conforme au schéma NewsReel: {exc}"
            ) from exc
        if len(scenario.segments) != count:
            raise AgnesError(
                f"Agnes a produit {len(scenario.segments)} sujets au lieu de {count}; "
                "le pipeline s'arrête pour ne pas générer un JT incomplet."
            )
        # Keep source URLs aligned with the RSS items if the model omitted them.
        for segment in scenario.segments:
            if not segment.source_url:
                match = next((item for item in news if item.title == segment.source_title), None)
                if match:
                    segment.source_url = match.url
        return scenario

    def generate_image(self, prompt: str, destination: Path, size: str | None = None) -> Path:
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        response = self._request(
            "images/generations",
            {
                "model": self.settings.agnes_image_model,
                "prompt": prompt,
                "size": size or self.settings.agnes_image_size,
                "n": 1,
                "response_format": "url",
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
            request = urllib.request.Request(url, headers={"User-Agent": "NewsReel/1.0"})
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
