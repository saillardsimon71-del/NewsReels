"""Modal entrypoint: one L40S container and one in-code FastH3/ComfyUI graph per JT batch."""

from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any

from newsreel.h3_workflow import (
    H3_DURATION_SECONDS,
    H3_FPS,
    H3_FRAMES,
    H3_HEIGHT,
    H3_MODAL_CPU,
    H3_MODAL_GPU,
    H3_MODAL_MEMORY_MIB,
    H3_MODAL_TIMEOUT_SECONDS,
    H3_MODEL_FILES,
    H3_STEPS,
    H3_VOLUME_NAME,
    H3_WIDTH,
    build_h3_api_workflow,
    h3_contract_config,
)

COMFYUI_DIR = Path(os.getenv("NEWSREEL_COMFYUI_DIR", "/opt/ComfyUI"))
MODELS_ROOT = Path("/mnt/fasth3-models")
COMFY_API = "http://127.0.0.1:8188"
COMFYUI_REPOSITORY = "https://github.com/Comfy-Org/ComfyUI.git"


def validate_batch(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if payload.get("contract_version") != 1:
        raise ValueError("Version de contrat H3 non prise en charge.")
    if "workflow" in payload:
        raise ValueError(
            "Le graphe FastH3 est construit dans le code du worker; aucun JSON workflow externe n'est accepté."
        )
    config = payload.get("config")
    expected_config = h3_contract_config()
    if not isinstance(config, dict):
        raise ValueError("Configuration FastH3 absente du batch.")
    for key, value in expected_config.items():
        if config.get(key) != value:
            raise ValueError(f"Paramètre FastH3 requis invalide: {key}={config.get(key)!r}.")
    if set(config) != set(expected_config):
        raise ValueError("Le contrat FastH3 contient des paramètres inconnus.")

    run_id = payload.get("run_id")
    if not isinstance(run_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", run_id):
        raise ValueError("Identifiant de run invalide pour le batch FastH3.")
    jobs = payload.get("jobs")
    if not isinstance(jobs, list) or not 1 <= len(jobs) <= 6:
        raise ValueError("Le worker Modal accepte un batch de un à six reporters.")

    required_per_job = {
        "width": H3_WIDTH,
        "height": H3_HEIGHT,
        "fps": H3_FPS,
        "frames": H3_FRAMES,
        "duration_seconds": H3_DURATION_SECONDS,
        "steps": H3_STEPS,
    }
    seen_ids: set[str] = set()
    for index, job in enumerate(jobs):
        if not isinstance(job, dict):
            raise ValueError(f"Job reporter #{index + 1} invalide.")
        job_id = job.get("id")
        if not isinstance(job_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", job_id):
            raise ValueError(f"Identifiant invalide pour le job reporter #{index + 1}.")
        if job_id in seen_ids:
            raise ValueError(f"Identifiant de job reporter dupliqué: {job_id}.")
        seen_ids.add(job_id)
        if not isinstance(job.get("prompt"), str) or not job["prompt"].strip():
            raise ValueError(f"Prompt vide pour le job reporter {job_id}.")
        if not isinstance(job.get("image_base64"), str) or not job["image_base64"]:
            raise ValueError(f"Image base64 absente pour le job reporter {job_id}.")
        for key, expected in required_per_job.items():
            if job.get(key) != expected:
                raise ValueError(f"Paramètre FastH3 requis invalide pour {job_id}: {key}.")
        seed = job.get("seed")
        if not isinstance(seed, int) or not 0 <= seed < 2**53:
            raise ValueError(f"Seed invalide pour le job reporter {job_id}.")
    return jobs


def _http_json(url: str, body: dict[str, Any] | None = None, timeout: int = 60) -> dict[str, Any]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"} if data is not None else {},
        method="POST" if data is not None else "GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:3000]
        raise RuntimeError(f"ComfyUI HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError(f"ComfyUI injoignable: {exc}") from exc


def _upload_image(image_path: Path) -> str:
    boundary = uuid.uuid4().hex
    image_bytes = image_path.read_bytes()
    body = (
        (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="image"; filename="{image_path.name}"\r\n'
            "Content-Type: application/octet-stream\r\n\r\n"
        ).encode()
        + image_bytes
        + (
            f"\r\n--{boundary}\r\n"
            'Content-Disposition: form-data; name="overwrite"\r\n\r\ntrue\r\n'
            f"--{boundary}--\r\n"
        ).encode()
    )
    request = urllib.request.Request(
        f"{COMFY_API}/upload/image",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            result = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
        raise RuntimeError(f"Upload image vers ComfyUI échoué: {exc}") from exc
    name = str(result.get("name", ""))
    if not name:
        raise RuntimeError("ComfyUI n'a pas retourné le nom de l'image uploadée.")
    subfolder = str(result.get("subfolder", "")).strip("/")
    return f"{subfolder}/{name}" if subfolder else name


def _history_entry(history: dict[str, Any], prompt_id: str) -> dict[str, Any] | None:
    exact = history.get(prompt_id)
    if isinstance(exact, dict):
        return exact
    for entry in history.values():
        if isinstance(entry, dict) and str(entry.get("prompt_id", "")) == prompt_id:
            return entry
    # /history/{id} normally returns a one-entry map. Accept a different key in that
    # response instead of treating a key-name mismatch as a failed generation.
    entries = [entry for entry in history.values() if isinstance(entry, dict)]
    return entries[0] if len(entries) == 1 else None


def _history_video(prompt_id: str) -> tuple[bytes | None, str | None, bool]:
    try:
        history = _http_json(f"{COMFY_API}/history/{urllib.parse.quote(prompt_id)}")
    except (RuntimeError, ValueError):
        return None, None, False
    entry = _history_entry(history, prompt_id) if isinstance(history, dict) else None
    if not isinstance(entry, dict):
        return None, None, False

    status = entry.get("status", {})
    status_str = str(status.get("status_str", "")).casefold() if isinstance(status, dict) else ""
    if status_str == "error":
        messages = status.get("messages", [])
        raise RuntimeError(f"ComfyUI a échoué sur le prompt {prompt_id}: {messages!r}"[:4000])
    completed = bool(status.get("completed")) or status_str in {"success", "completed"}
    if not completed:
        return None, None, False

    outputs = entry.get("outputs", {})
    if not isinstance(outputs, dict):
        return None, None, True
    for output in outputs.values():
        if not isinstance(output, dict):
            continue
        for key in ("videos", "gifs", "files", "images"):
            items = output.get(key, [])
            for item in items if isinstance(items, list) else []:
                if not isinstance(item, dict):
                    continue
                filename = str(item.get("filename", ""))
                if Path(filename).suffix.lower() != ".mp4":
                    continue
                # Current SaveVideo exposes PreviewVideo data through `images` with
                # animated=true rather than the older videos/gifs/files fields.
                if key == "images" and item.get("animated") is not True:
                    continue
                query = urllib.parse.urlencode(
                    {
                        "filename": filename,
                        "subfolder": str(item.get("subfolder", "")),
                        "type": str(item.get("type", "output")),
                    }
                )
                try:
                    with urllib.request.urlopen(
                        f"{COMFY_API}/view?{query}", timeout=180
                    ) as response:
                        content = response.read()
                    if content:
                        return content, filename, True
                except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
                    # Try the worker's output-directory fallback below.
                    continue
    return None, None, True


def _find_output_video(filename_prefix: str) -> Path | None:
    relative_prefix = Path(filename_prefix.replace("\\", "/"))
    if relative_prefix.is_absolute() or ".." in relative_prefix.parts:
        raise ValueError("Préfixe de sortie ComfyUI invalide.")
    output_dir = COMFYUI_DIR / "output" / relative_prefix.parent
    if not output_dir.is_dir():
        return None
    candidates = [
        path
        for path in output_dir.iterdir()
        if path.is_file()
        and path.name.startswith(relative_prefix.name)
        and path.suffix.casefold() == ".mp4"
    ]
    return max(
        candidates, key=lambda path: (path.stat().st_mtime_ns, path.stat().st_size), default=None
    )


def _prompt_is_active(prompt_id: str) -> bool | None:
    try:
        queue = _http_json(f"{COMFY_API}/queue", timeout=5)
    except (RuntimeError, ValueError):
        return None
    for key in ("queue_running", "queue_pending"):
        items = queue.get(key, []) if isinstance(queue, dict) else []
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, (list, tuple)) and len(item) > 1 and str(item[1]) == prompt_id:
                return True
            if (
                isinstance(item, dict)
                and str(item.get("prompt_id", item.get("id", ""))) == prompt_id
            ):
                return True
    return False


def _wait_for_video(
    prompt_id: str, filename_prefix: str, timeout_seconds: int = 1200
) -> tuple[bytes, str]:
    deadline = time.monotonic() + timeout_seconds
    previous_file: tuple[Path, int, int] | None = None
    stable_file_polls = 0
    while time.monotonic() < deadline:
        content, filename, completed = _history_video(prompt_id)
        if content is not None and filename:
            return content, filename

        candidate = _find_output_video(filename_prefix)
        if completed and candidate is not None:
            data = candidate.read_bytes()
            if data:
                return data, candidate.name
        elif candidate is not None and _prompt_is_active(prompt_id) is False:
            stat = candidate.stat()
            current_file = (candidate, stat.st_size, stat.st_mtime_ns)
            stable_file_polls = stable_file_polls + 1 if current_file == previous_file else 1
            previous_file = current_file
            # With no matching history entry, a stable unique-prefix MP4 and an idle
            # Comfy queue are the fallback completion signal.
            if stable_file_polls >= 2:
                data = candidate.read_bytes()
                if data:
                    return data, candidate.name
        else:
            previous_file = None
            stable_file_polls = 0
        time.sleep(2)
    raise TimeoutError(
        f"ComfyUI n'a pas terminé le rendu {prompt_id} (préfixe {filename_prefix}) "
        f"en {timeout_seconds}s."
    )


def _mount_volume_models() -> None:
    if not MODELS_ROOT.is_dir():
        raise RuntimeError(
            f"Volume Modal {H3_VOLUME_NAME} vide ou non monté à {MODELS_ROOT}. "
            "Le worker ne télécharge ni ne remplace les modèles H3."
        )

    model_locations = (
        ("diffusion_models", H3_MODEL_FILES["unet"]),
        ("text_encoders", H3_MODEL_FILES["clip"]),
        ("vae", H3_MODEL_FILES["video_vae"]),
        ("vae", H3_MODEL_FILES["audio_vae"]),
    )
    sources = [
        (category, filename, MODELS_ROOT / category / filename)
        for category, filename in model_locations
    ]
    missing = [str(source) for _, _, source in sources if not source.is_file()]
    if missing:
        raise RuntimeError(
            "Poids FastH3 exacts absents du volume fasth3-models: " + ", ".join(missing)
        )

    target_root = COMFYUI_DIR / "models"
    for category, filename, source in sources:
        destination_dir = target_root / category
        destination_dir.mkdir(parents=True, exist_ok=True)
        destination = destination_dir / filename

        if destination.is_symlink():
            if destination.resolve(strict=False) == source.resolve(strict=True):
                continue
            raise RuntimeError(
                f"Lien de poids ComfyUI incorrect, refus de l'écraser: {destination}"
            )
        if destination.exists():
            raise RuntimeError(
                f"Fichier de poids ComfyUI déjà présent, refus de l'écraser: {destination}"
            )
        destination.symlink_to(source, target_is_directory=False)


def _start_comfyui() -> subprocess.Popen[bytes]:
    if not (COMFYUI_DIR / "main.py").is_file():
        raise RuntimeError(f"ComfyUI non installé dans l'image Modal: {COMFYUI_DIR}")
    _mount_volume_models()
    log_path = Path("/tmp/newsreel-comfyui.log")
    log_handle = log_path.open("wb")
    command = [
        sys.executable,
        "main.py",
        "--listen",
        "127.0.0.1",
        "--port",
        "8188",
        "--disable-auto-launch",
        "--disable-comfy-compiler",
    ]
    process = subprocess.Popen(
        command,
        cwd=COMFYUI_DIR,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    deadline = time.monotonic() + 360
    while time.monotonic() < deadline:
        if process.poll() is not None:
            tail = log_path.read_text(encoding="utf-8", errors="replace")[-6000:]
            raise RuntimeError(f"ComfyUI s'est arrêté pendant le démarrage:\n{tail}")
        try:
            _http_json(f"{COMFY_API}/system_stats", timeout=5)
            return process
        except Exception:
            time.sleep(2)
    process.terminate()
    tail = log_path.read_text(encoding="utf-8", errors="replace")[-6000:]
    raise TimeoutError(f"ComfyUI n'a pas démarré en 360s:\n{tail}")


def _run_batch(payload: dict[str, Any]) -> dict[str, Any]:
    jobs = validate_batch(payload)
    process = _start_comfyui()
    videos: dict[str, dict[str, str]] = {}
    generation_start = time.perf_counter()
    run_id = payload["run_id"]
    try:
        # Keep one ComfyUI process and the exact same model-loader node IDs for every reporter.
        for job in jobs:
            job_id = job["id"]
            try:
                image_bytes = base64.b64decode(job["image_base64"], validate=True)
            except ValueError as exc:
                raise ValueError(f"Image base64 invalide pour {job_id}.") from exc
            image_path = (
                COMFYUI_DIR / "input" / f"newsreel-{run_id}-{job_id}-{uuid.uuid4().hex}.png"
            )
            image_path.parent.mkdir(parents=True, exist_ok=True)
            image_path.write_bytes(image_bytes)
            try:
                uploaded_image = _upload_image(image_path)
                output_prefix = f"newsreel/{run_id}/{job_id}"
                workflow = build_h3_api_workflow(job, uploaded_image, output_prefix)
                queued = _http_json(f"{COMFY_API}/prompt", {"prompt": workflow}, timeout=60)
                prompt_id = str(queued.get("prompt_id", ""))
                if not prompt_id:
                    raise RuntimeError(f"ComfyUI n'a pas accepté le job {job_id}: {queued!r}")
                content, source_name = _wait_for_video(prompt_id, output_prefix)
                if Path(source_name).suffix.lower() != ".mp4":
                    raise RuntimeError(
                        f"Le workflow FastH3 doit produire un MP4, reçu: {source_name}."
                    )
                videos[job_id] = {
                    "filename": f"{job_id}.mp4",
                    "data_base64": base64.b64encode(content).decode("ascii"),
                }
            finally:
                image_path.unlink(missing_ok=True)
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
    return {
        "videos": videos,
        "h3_generation_seconds": round(time.perf_counter() - generation_start, 3),
        "container_count": 1,
        "comfyui_start_count": 1,
        "batch_clip_count": len(videos),
    }


try:
    import modal
except ImportError:  # Local/offline tests do not install Modal or contact the GPU service.
    modal = None  # type: ignore[assignment]

if modal is not None:
    app = modal.App("newsreel-fasth3")
    models_volume = modal.Volume.from_name(H3_VOLUME_NAME, create_if_missing=False)
    comfy_image = (
        modal.Image.debian_slim(python_version="3.11")
        .apt_install("git", "ffmpeg", "libgl1", "libglib2.0-0", "libsm6", "libxext6")
        .pip_install(
            "torch==2.8.0",
            index_url="https://download.pytorch.org/whl/cu128",
        )
        .run_commands(
            f"git clone --depth 1 {COMFYUI_REPOSITORY} /opt/ComfyUI",
            "pip install --no-cache-dir -r /opt/ComfyUI/requirements.txt",
        )
        .env({"NEWSREEL_COMFYUI_DIR": "/opt/ComfyUI"})
        .add_local_python_source("newsreel")
    )

    @app.function(
        image=comfy_image,
        gpu=H3_MODAL_GPU,
        cpu=H3_MODAL_CPU,
        memory=H3_MODAL_MEMORY_MIB,
        timeout=H3_MODAL_TIMEOUT_SECONDS,
        max_containers=1,
        single_use_containers=True,
        volumes={str(MODELS_ROOT): models_volume},
    )
    def render_h3_batch(payload: dict[str, Any]) -> dict[str, Any]:
        """Render all reporter clips sequentially in one disposable L40S/ComfyUI worker."""
        return _run_batch(payload)
else:
    app = None

    def render_h3_batch(payload: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError(
            "Modal n'est pas installé; installez requirements-modal.txt pour déployer le worker."
        )
