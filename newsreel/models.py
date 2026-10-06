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
    summary: str = ""
    host_action: str = ""
    people: list[dict[str, Any]] = field(default_factory=list)
    location: str = ""
    scene_action: str = ""
    camera_plan: str = ""
    reporter_name: str = "Reporter"
    reporter_description: str = ""
    reporter_image_prompt: str = ""
    source_title: str = ""
    source_url: str = ""
    reporter_action: str = ""
    emotion: str = ""
    stanislavski: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, value: dict[str, Any], index: int) -> Segment:
        reporter_value = value.get("reporter")
        reporter = reporter_value if isinstance(reporter_value, dict) else {}
        host = value.get("host_dialogue", value.get("host_text", ""))
        reporter_dialogue = reporter.get(
            "dialogue",
            value.get(
                "reporter_dialogue",
                value.get("reporter_text", value.get("dialogue", value.get("reporter_script", ""))),
            ),
        )
        title = value.get("title", value.get("headline", f"Sujet {index + 1}"))
        return cls(
            id=str(value.get("id", f"subject-{index}")),
            title=str(title).strip(),
            host_dialogue=str(host).strip(),
            reporter_dialogue=str(reporter_dialogue).strip(),
            summary=str(value.get("summary", "")).strip(),
            host_action=str(value.get("host_action", "")).strip(),
            people=[item for item in value.get("people", []) if isinstance(item, dict)],
            location=str(value.get("location", "")).strip(),
            scene_action=str(value.get("scene_action", value.get("reporter_action", ""))).strip(),
            camera_plan=str(value.get("camera_plan", "")).strip(),
            reporter_name=str(reporter.get("name", value.get("reporter_name", "Reporter"))).strip(),
            reporter_description=str(
                reporter.get("description", value.get("reporter_description", ""))
            ).strip(),
            reporter_image_prompt=str(
                value.get("reporter_image_prompt", value.get("image_prompt", ""))
            ).strip(),
            source_title=str(value.get("source_title", value.get("headline", title))).strip(),
            source_url=str(value.get("source_url", value.get("url", ""))).strip(),
            reporter_action=str(value.get("reporter_action", "")).strip(),
            emotion=str(value.get("emotion", "")).strip(),
            stanislavski=value.get("stanislavski", {})
            if isinstance(value.get("stanislavski"), dict)
            else {},
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "headline": self.title,
            "summary": self.summary,
            "host_dialogue": self.host_dialogue,
            "host_action": self.host_action,
            "people": self.people,
            "location": self.location,
            "scene_action": self.scene_action,
            "camera_plan": self.camera_plan,
            "reporter": {
                "name": self.reporter_name,
                "description": self.reporter_description,
                "dialogue": self.reporter_dialogue,
            },
            "reporter_dialogue": self.reporter_dialogue,
            "reporter_image_prompt": self.reporter_image_prompt,
            "reporter_action": self.reporter_action,
            "source_title": self.source_title,
            "source_url": self.source_url,
            "emotion": self.emotion,
            "stanislavski": self.stanislavski,
        }


@dataclass(slots=True)
class Scenario:
    title: str
    segments: list[Segment]
    host_name: str = "Chroniqueur"
    host_description: str = ""
    host_plateau: str = ""
    host_action: str = ""
    host_stanislavski: dict[str, Any] = field(default_factory=dict)
    host_image_prompt: str = ""
    intro_dialogue: str = ""
    outro_dialogue: str = ""
    creative: dict[str, str] = field(default_factory=dict)
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
        host_value = value.get("host")
        host = host_value if isinstance(host_value, dict) else {}
        creative_value = value.get("creative")
        creative = (
            {str(key): str(item) for key, item in creative_value.items()}
            if isinstance(creative_value, dict)
            else {}
        )
        return cls(
            title=str(value.get("title", value.get("jt_title", "Le JT NewsReel"))).strip(),
            segments=segments,
            host_name=str(host.get("name", "Chroniqueur")).strip(),
            host_description=str(host.get("description", "")).strip(),
            host_plateau=str(host.get("plateau", "")).strip(),
            host_action=str(host.get("host_action", "")).strip(),
            host_stanislavski=host.get("stanislavski", {})
            if isinstance(host.get("stanislavski"), dict)
            else {},
            host_image_prompt=str(value.get("host_image_prompt", "")).strip(),
            intro_dialogue=str(value.get("intro_dialogue", "")).strip(),
            outro_dialogue=str(value.get("outro_dialogue", "")).strip(),
            creative=creative,
            raw=value,
        )

    def host_dict(self) -> dict[str, Any]:
        return {
            "name": self.host_name,
            "description": self.host_description,
            "plateau": self.host_plateau,
            "host_action": self.host_action,
            "stanislavski": self.host_stanislavski,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "jt_title": self.title,
            "host": self.host_dict(),
            "host_image_prompt": self.host_image_prompt,
            "intro_dialogue": self.intro_dialogue,
            "outro_dialogue": self.outro_dialogue,
            "creative": self.creative,
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
    version: int = 2

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
            version=int(value.get("version", 2)),
        )
        if timeline.fps != 24 or (timeline.width, timeline.height) != (1080, 1920):
            raise ValueError("NewsReel attend une timeline 1080x1920 à 24 fps.")
        ids = [scene.id for scene in scenes]
        if len(ids) != len(set(ids)):
            raise ValueError("Les identifiants de scène doivent être uniques.")
        return timeline
