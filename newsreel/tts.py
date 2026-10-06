from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Protocol

from .config import Settings
from .media import probe_media


class TTSProvider(Protocol):
    def synthesize(self, text: str, destination: Path, voice: str) -> float: ...


class EdgeTTSProvider:
    """edge-tts adapter; replaceable by another implementation of TTSProvider."""

    def __init__(self, settings: Settings):
        self.settings = settings

    def synthesize(self, text: str, destination: Path, voice: str | None = None) -> float:
        text = text.strip()
        if not text:
            raise ValueError("Impossible de synthétiser un dialogue vide.")
        try:
            import edge_tts
        except ImportError as exc:
            raise RuntimeError(
                "Le provider TTS edge-tts n'est pas installé. Réinstallez requirements.txt."
            ) from exc
        destination.parent.mkdir(parents=True, exist_ok=True)
        chosen_voice = voice or self.settings.tts_voice

        async def save() -> None:
            communicate = edge_tts.Communicate(text, chosen_voice)
            await communicate.save(str(destination))

        try:
            asyncio.run(save())
        except RuntimeError as exc:
            # The production pipeline runs in a worker thread; this guard makes direct callers clear.
            raise RuntimeError(f"Échec edge-tts pour la voix {chosen_voice}: {exc}") from exc
        if not destination.is_file() or destination.stat().st_size == 0:
            raise RuntimeError(f"edge-tts n'a produit aucun audio pour la voix {chosen_voice}.")
        info = probe_media(destination, self.settings)
        if info.duration <= 0 or not info.audio:
            raise RuntimeError(f"Le TTS {chosen_voice} a produit un fichier audio invalide.")
        return info.duration
