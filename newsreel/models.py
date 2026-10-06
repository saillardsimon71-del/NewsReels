from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class NewsItem:
    title: str
    url: str = ""
    source: str = ""
    published: str = ""
    summary: str = ""

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> NewsItem:
        return cls(
            title=str(value.get("title", "")).strip(),
            url=str(value.get("url", value.get("link", ""))).strip(),
            source=str(value.get("source", "")).strip(),
            published=str(value.get("published", value.get("pubDate", ""))).strip(),
            summary=str(value.get("summary", value.get("description", ""))).strip(),
        )

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(slots=True)
class Segment:
    id: str
    title: str
    host_dialogue: str
    reporter_dialogue: str
    reporter_image_prompt: str = ""
    source_title: str = ""
    source_url: str = ""
    reporter_action: str = ""

    @classmethod
    def from_mapping(cls, value: dict[str, Any], index: int) -> Segment:
        host = value.get("host_dialogue", value.get("host_text", ""))
        reporter = value.get(
            "reporter_dialogue",
            value.get("reporter_text", value.get("dialogue", value.get("reporter_script", ""))),
        )
        title = value.get("title", value.get("headline", f"Sujet {index + 1}"))
        return cls(
            id=str(value.get("id", f"subject-{index}")),
            title=str(title).strip(),
            host_dialogue=str(host).strip(),
            reporter_dialogue=str(reporter).strip(),
            reporter_image_prompt=str(
                value.get("reporter_image_prompt", value.get("image_prompt", ""))
            ).strip(),
            source_title=str(value.get("source_title", "")).strip(),
            source_url=str(value.get("source_url", value.get("url", ""))).strip(),
            reporter_action=str(value.get("reporter_action", "")).strip(),
        )

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(slots=True)
class Scenario:
    title: str
    segments: list[Segment]
    host_image_prompt: str = (
        "Portrait vertical réaliste d'une présentatrice ou d'un présentateur français "
        "de journal télévisé, adulte, visage avenant, tenue professionnelle bleu nuit, "
        "studio d'information moderne bleu et cyan en arrière-plan, cadrage poitrine, "
        "lumière douce de studio, sans texte, sans logo, composition centrée."
    )
    intro_dialogue: str = ""
    outro_dialogue: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> Scenario:
        raw_segments = value.get("segments") or value.get("subjects")
        if not isinstance(raw_segments, list) or not raw_segments:
            raise ValueError("Le scénario Agnes doit contenir une liste 'segments' non vide.")
        segments = [Segment.from_mapping(item, i) for i, item in enumerate(raw_segments)]
        for index, segment in enumerate(segments, start=1):
            if not segment.host_dialogue:
                raise ValueError(f"Le sujet {index} ne contient pas segment.host_dialogue.")
            if not segment.reporter_dialogue:
                raise ValueError(f"Le sujet {index} ne contient pas de dialogue reporter.")
            if not segment.title:
                raise ValueError(f"Le sujet {index} ne contient pas de titre.")
        return cls(
            title=str(value.get("title", "Le JT NewsReel")).strip(),
            segments=segments,
            host_image_prompt=str(value.get("host_image_prompt", "")).strip()
            or cls.__dataclass_fields__["host_image_prompt"].default,
            intro_dialogue=str(value.get("intro_dialogue", "")).strip(),
            outro_dialogue=str(value.get("outro_dialogue", "")).strip(),
            raw=value,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "host_image_prompt": self.host_image_prompt,
            "intro_dialogue": self.intro_dialogue,
            "outro_dialogue": self.outro_dialogue,
            "segments": [segment.to_dict() for segment in self.segments],
        }


@dataclass(slots=True)
class Scene:
    id: str
    type: str
    asset: str
    duration: float
    motion: str = "none"
    dialogue: str = ""
    audio: str = ""
    title: str = ""
    kicker: str = ""
    source_url: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> Scene:
        scene = cls(
            id=str(value["id"]),
            type=str(value["type"]),
            asset=str(value["asset"]),
            duration=float(value["duration"]),
            motion=str(value.get("motion", "none")),
            dialogue=str(value.get("dialogue", "")),
            audio=str(value.get("audio", "")),
            title=str(value.get("title", "")),
            kicker=str(value.get("kicker", "")),
            source_url=str(value.get("source_url", "")),
        )
        if scene.type not in {"still", "host_still", "h3_video"}:
            raise ValueError(f"Type de scène inconnu: {scene.type}")
        if scene.duration <= 0:
            raise ValueError(f"Durée invalide pour la scène {scene.id}.")
        return scene


@dataclass(slots=True)
class Timeline:
    run_id: str
    fps: int
    width: int
    height: int
    scenes: list[Scene]
    version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "run_id": self.run_id,
            "fps": self.fps,
            "width": self.width,
            "height": self.height,
            "scenes": [scene.to_dict() for scene in self.scenes],
            "duration": round(sum(scene.duration for scene in self.scenes), 3),
        }

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> Timeline:
        scenes = [Scene.from_mapping(item) for item in value.get("scenes", [])]
        if not scenes:
            raise ValueError("La timeline ne contient aucune scène.")
        timeline = cls(
            run_id=str(value["run_id"]),
            fps=int(value.get("fps", 24)),
            width=int(value.get("width", 1080)),
            height=int(value.get("height", 1920)),
            scenes=scenes,
            version=int(value.get("version", 1)),
        )
        if timeline.fps != 24 or (timeline.width, timeline.height) != (1080, 1920):
            raise ValueError("La V1 attend une timeline 1080x1920 à 24 fps.")
        ids = [scene.id for scene in scenes]
        if len(ids) != len(set(ids)):
            raise ValueError("Les identifiants de scène doivent être uniques.")
        return timeline
