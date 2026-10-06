from __future__ import annotations

import json
import re
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$")


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def validate_run_id(run_id: str) -> str:
    if not _RUN_ID_RE.fullmatch(run_id):
        raise ValueError("run_id invalide.")
    return run_id


class RunStore:
    """Filesystem-backed run isolation and manifest updates."""

    def __init__(self, output_root: Path):
        self.output_root = Path(output_root).expanduser().resolve()
        self.output_root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def create(self, run_id: str | None = None) -> tuple[str, Path]:
        with self._lock:
            if run_id is None:
                stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
                run_id = f"{stamp}-{uuid.uuid4().hex[:8]}"
            run_id = validate_run_id(run_id)
            run_dir = (self.output_root / run_id).resolve()
            if run_dir.parent != self.output_root:
                raise ValueError("Le run_id sort du dossier output.")
            run_dir.mkdir(parents=True, exist_ok=False)
            for folder in ("images", "audio", "h3", "segments"):
                (run_dir / folder).mkdir()
            manifest: dict[str, Any] = {
                "run_id": run_id,
                "status": "queued",
                "created_at": utc_now(),
                "updated_at": utc_now(),
                "stages": {
                    key: {"status": "pending", "started_at": None, "finished_at": None}
                    for key in ("news", "scenario", "images", "h3", "assembly", "ready")
                },
                "files": [],
                "final_duration_seconds": None,
                "h3_clip_count": 0,
                "h3_generation_seconds": None,
                "errors": [],
            }
            self._write_manifest(run_dir, manifest)
            return run_id, run_dir

    def path(self, run_id: str) -> Path:
        run_id = validate_run_id(run_id)
        run_dir = (self.output_root / run_id).resolve()
        if run_dir.parent != self.output_root or not run_dir.is_dir():
            raise FileNotFoundError(f"Run introuvable: {run_id}")
        return run_dir

    def read_manifest(self, run_id: str) -> dict[str, Any]:
        path = self.path(run_id) / "run_manifest.json"
        if not path.is_file():
            raise FileNotFoundError(f"Manifest introuvable pour {run_id}")
        return json.loads(path.read_text(encoding="utf-8"))

    def update(self, run_id: str, **changes: Any) -> dict[str, Any]:
        with self._lock:
            run_dir = self.path(run_id)
            manifest = self.read_manifest(run_id)
            manifest.update(changes)
            manifest["updated_at"] = utc_now()
            self._write_manifest(run_dir, manifest)
            return manifest

    def stage(self, run_id: str, name: str, status: str, **details: Any) -> dict[str, Any]:
        allowed = {"pending", "running", "succeeded", "failed", "skipped"}
        if status not in allowed:
            raise ValueError(f"Statut d'étape invalide: {status}")
        with self._lock:
            run_dir = self.path(run_id)
            manifest = self.read_manifest(run_id)
            stages = manifest.setdefault("stages", {})
            entry = stages.setdefault(name, {})
            entry["status"] = status
            if status == "running":
                entry["started_at"] = utc_now()
            if status in {"succeeded", "failed", "skipped"}:
                entry["finished_at"] = utc_now()
            entry.update(details)
            manifest["status"] = "running" if status == "running" else manifest.get("status")
            manifest["updated_at"] = utc_now()
            self._write_manifest(run_dir, manifest)
            return manifest

    def add_error(self, run_id: str, message: str, stage: str | None = None) -> None:
        with self._lock:
            run_dir = self.path(run_id)
            manifest = self.read_manifest(run_id)
            errors = manifest.setdefault("errors", [])
            errors.append({"at": utc_now(), "stage": stage, "message": message})
            manifest["status"] = "failed"
            manifest["updated_at"] = utc_now()
            self._write_manifest(run_dir, manifest)

    def register_file(self, run_id: str, path: Path) -> str:
        run_dir = self.path(run_id)
        resolved = Path(path).resolve()
        try:
            relative = resolved.relative_to(run_dir)
        except ValueError as exc:
            raise ValueError("Un fichier enregistré doit appartenir à son dossier de run.") from exc
        rel = relative.as_posix()
        with self._lock:
            manifest = self.read_manifest(run_id)
            files = manifest.setdefault("files", [])
            if rel not in files:
                files.append(rel)
            manifest["updated_at"] = utc_now()
            self._write_manifest(run_dir, manifest)
        return rel

    @staticmethod
    def atomic_write_json(path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)

    def _write_manifest(self, run_dir: Path, manifest: dict[str, Any]) -> None:
        self.atomic_write_json(run_dir / "run_manifest.json", manifest)
