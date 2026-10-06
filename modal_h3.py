"""Modal entrypoint: one L40S container and one ComfyUI server per three-clip batch.

The exact validated ComfyUI API workflow is supplied by the local bridge through
NEWSREEL_H3_API_WORKFLOW. It is intentionally not replaced by a guessed graph.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any

from newsreel.comfy_workflow import patch_api_workflow, validate_api_workflow

COMFYUI_DIR = Path(os.getenv("NEWSREEL_COMFYUI_DIR", "/opt/ComfyUI"))
MODELS_ROOT = Path("/mnt/fasth3-models")
COMFY_API = "http://127.0.0.1:8188"


def validate_batch(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if payload.get("contract_version") != 1:
        raise ValueError("Version de contrat H3 non prise en charge.")
    expected = {
        "width": 768,
        "height": 1344,
        "fps": 24,
        "frames": 243,
        "duration_seconds": 10.125,
        "steps": 8,
        "native_audio": True,
        "video_sparse_attention": True,
    }
    config = payload.get("config", {})
    for key, value in expected.items():
        if config.get(key) != value:
            raise ValueError(f"Paramètre FastH3 requis invalide: {key}={config.get(key)!r}.")
    jobs = payload.get("jobs")
    if not isinstance(jobs, list) or not 1 <= len(jobs) <= 6:
        raise ValueError("Le worker Modal accepte un batch de un à six reporters.")
    if not isinstance(payload.get("workflow"), dict):
        raise ValueError("Export JSON de workflow ComfyUI absent du batch.")
    validate_api_workflow(payload["workflow"])
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


def _history_video(prompt_id: str) -> tuple[bytes | None, str | None]:
    history = _http_json(f"{COMFY_API}/history/{urllib.parse.quote(prompt_id)}")
    entry = history.get(prompt_id) if isinstance(history, dict) else None
    if not isinstance(entry, dict):
        return None, None
    status = entry.get("status", {})
    if isinstance(status, dict) and status.get("status_str") == "error":
        messages = status.get("messages", [])
        raise RuntimeError(f"ComfyUI a échoué sur le prompt {prompt_id}: {messages!r}"[:4000])
    outputs = entry.get("outputs", {})
    if not isinstance(outputs, dict):
        return None, None
    for output in outputs.values():
        if not isinstance(output, dict):
            continue
        for key in ("videos", "gifs", "files"):
            for item in output.get(key, []) if isinstance(output.get(key, []), list) else []:
                if not isinstance(item, dict):
                    continue
                filename = str(item.get("filename", ""))
                if Path(filename).suffix.lower() not in {".mp4", ".mkv", ".webm"}:
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
                        return response.read(), filename
                except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
                    raise RuntimeError(f"Téléchargement du MP4 ComfyUI échoué: {exc}") from exc
    return None, None


def _wait_for_video(prompt_id: str, timeout_seconds: int = 1200) -> tuple[bytes, str]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        result, filename = _history_video(prompt_id)
        if result is not None and filename:
            if not result:
                raise RuntimeError(f"ComfyUI a retourné un fichier vidéo vide ({filename}).")
            return result, filename
        time.sleep(2)
    raise TimeoutError(f"ComfyUI n'a pas terminé le rendu {prompt_id} en {timeout_seconds}s.")


def _mount_volume_models() -> None:
    if not MODELS_ROOT.is_dir():
        raise RuntimeError(
            "Volume Modal fasth3-models vide ou non monté à /mnt/fasth3-models. "
            "Réutilisez le volume du smoke FastH3."
        )
    target_root = COMFYUI_DIR / "models"
    target_root.mkdir(parents=True, exist_ok=True)
    categories = (
        "diffusion_models",
        "text_encoders",
        "vae",
        "loras",
        "clip",
        "checkpoints",
    )
    linked = 0
    for category in categories:
        target = target_root / category
        if target.exists() and not target.is_symlink():
            has_weights = target.is_dir() and any(target.rglob("*.safetensors"))
            if has_weights:
                continue
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()
        if target.exists() or target.is_symlink():
            continue
        candidates = [p for p in MODELS_ROOT.rglob(category) if p.is_dir()]
        if (MODELS_ROOT / category).is_dir():
            source = MODELS_ROOT / category
        elif candidates:
            source = candidates[0]
        else:
            continue
        target.symlink_to(source, target_is_directory=True)
        linked += 1
    for category in ("diffusion_models", "text_encoders", "vae"):
        directory = target_root / category
        if not directory.is_dir() or not any(directory.rglob("*.safetensors")):
            raise RuntimeError(f"Poids FastH3/H3 manquants dans le volume: {category}.")
    if not linked and not any((target_root / name).is_symlink() for name in categories):
        raise RuntimeError("Impossible de relier les dossiers de modèles du volume fasth3-models.")


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
    try:
        for job in jobs:
            job_id = str(job.get("id", ""))
            if not job_id or not job.get("image_base64") or not job.get("prompt"):
                raise ValueError("Job reporter incomplet: id, image_base64 et prompt requis.")
            import base64

            try:
                image_bytes = base64.b64decode(job["image_base64"], validate=True)
            except ValueError as exc:
                raise ValueError(f"Image base64 invalide pour {job_id}.") from exc
            image_path = COMFYUI_DIR / "input" / f"newsreel-{uuid.uuid4().hex}.png"
            image_path.parent.mkdir(parents=True, exist_ok=True)
            image_path.write_bytes(image_bytes)
            try:
                uploaded_image = _upload_image(image_path)
                workflow = patch_api_workflow(
                    payload["workflow"],
                    job,
                    uploaded_image,
                    f"newsreel/{job_id}-{uuid.uuid4().hex[:8]}",
                )
                queued = _http_json(f"{COMFY_API}/prompt", {"prompt": workflow}, timeout=60)
                prompt_id = str(queued.get("prompt_id", ""))
                if not prompt_id:
                    raise RuntimeError(f"ComfyUI n'a pas accepté le job {job_id}: {queued!r}")
                content, source_name = _wait_for_video(prompt_id)
                if Path(source_name).suffix.lower() != ".mp4":
                    raise RuntimeError(
                        f"Le workflow FastH3 doit produire un MP4, reçu: {source_name}."
                    )
                videos[job_id] = {
                    "filename": f"{job_id}{Path(source_name).suffix.lower() or '.mp4'}",
                    "data_base64": base64.b64encode(content).decode("ascii"),
                }
            finally:
                try:
                    image_path.unlink(missing_ok=True)
                except OSError:
                    pass
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
    models_volume = modal.Volume.from_name("fasth3-models", create_if_missing=False)
    comfy_image = (
        modal.Image.debian_slim(python_version="3.11")
        .add_local_python_source("newsreel")
        .apt_install("git", "ffmpeg", "libgl1", "libglib2.0-0", "libsm6", "libxext6")
        .pip_install(
            "torch==2.8.0",
            index_url="https://download.pytorch.org/whl/cu128",
        )
        .run_commands(
            "git clone --depth 1 https://github.com/comfyanonymous/ComfyUI.git /opt/ComfyUI",
            "pip install --no-cache-dir -r /opt/ComfyUI/requirements.txt",
        )
        .env({"NEWSREEL_COMFYUI_DIR": "/opt/ComfyUI"})
    )

    @app.function(
        image=comfy_image,
        gpu="L40S",
        timeout=5400,
        concurrency_limit=1,
        volumes={str(MODELS_ROOT): models_volume},
    )
    def render_h3_batch(payload: dict[str, Any]) -> dict[str, Any]:
        """Render three reporter clips in one L40S container and one ComfyUI lifetime."""
        return _run_batch(payload)
else:
    app = None

    def render_h3_batch(payload: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError(
            "Modal n'est pas installé; installez requirements-modal.txt pour déployer le worker."
        )
