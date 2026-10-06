"""
NewsReel Studio — bridge local LTX / Modal.

Démarrage :
    python newsreel_ltx_bridge.py
    → http://127.0.0.1:8765

Endpoints :
    GET  /health                       → vérifie réellement la résolution Modal
    POST /render-batch  { items: [...] } → batch complet
    GET  /output/*                     → fichiers statiques
"""

import os
import time
import uuid
import base64
import urllib.request
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

try:
    import modal
except Exception as e:
    modal = None
    _modal_import_error = str(e)
else:
    _modal_import_error = None


# ------------------------------------------------------------------------------
HOST       = "127.0.0.1"
PORT       = 8765
BASE_URL   = f"http://{HOST}:{PORT}"
OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

MODAL_APP  = "newsreel-ltx"
MODAL_FUNC = "render_batch"

# ------------------------------------------------------------------------------
app = FastAPI(title="NewsReel LTX Bridge")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/output", StaticFiles(directory=str(OUTPUT_DIR)), name="output")


# ------------------------------------------------------------------------------
class BatchItem(BaseModel):
    key: str
    image_url: str
    prompt: str
    duration: Optional[int] = 5
    fps: Optional[int] = 24
    seed: Optional[int] = None


class BatchRequest(BaseModel):
    items: List[BatchItem]
    run_id: Optional[str] = None


# ------------------------------------------------------------------------------
def _fetch_image_bytes(url_or_data: str) -> bytes:
    s = (url_or_data or "").strip()
    if s.startswith("data:"):
        try:
            _, b64 = s.split(",", 1)
            return base64.b64decode(b64)
        except Exception as e:
            raise RuntimeError(f"data URL invalide: {e}")
    if s.startswith("http://") or s.startswith("https://"):
        req = urllib.request.Request(s, headers={"User-Agent": "NewsReel/1.0"})
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.read()
    raise RuntimeError("image_url doit être http(s):// ou data:...")


def _modal_fn(check: bool = False):
    """
    Retourne le handle Function Modal.
    Si check=True, force une vraie résolution réseau du handle :
    - d'abord fn.info(refresh=True)
    - fallback fn.hydrate() si l'API info() ne supporte pas refresh.
    """
    if modal is None:
        raise RuntimeError(
            f"Le package modal n'est pas installé ({_modal_import_error}). "
            f"Fais : pip install modal && modal setup"
        )
    try:
        fn = modal.Function.from_name(MODAL_APP, MODAL_FUNC)
    except Exception as e:
        raise RuntimeError(
            f"Impossible de résoudre {MODAL_APP}.{MODAL_FUNC} : {e}. "
            f"Avez-vous exécuté `modal deploy newsreel_ltx_modal.py` ?"
        )

    if not check:
        return fn

    # ─── Forcer une vraie résolution réseau (from_name est lazy) ─────────────
    resolved = False
    last_err = None

    try:
        fn.info(refresh=True)
        resolved = True
    except TypeError:
        # info() existe mais sans paramètre refresh
        try:
            fn.info()
            resolved = True
        except Exception as e:
            last_err = e
    except Exception as e:
        last_err = e

    if not resolved:
        try:
            fn.hydrate()
            resolved = True
        except Exception as e:
            last_err = e

    if not resolved:
        raise RuntimeError(
            f"Handle Modal non résolu pour {MODAL_APP}.{MODAL_FUNC} : {last_err}"
        )
    return fn


# ------------------------------------------------------------------------------
@app.get("/health")
def health():
    info = {"ok": True, "bridge": "ltx", "modal_ready": False, "detail": None}
    try:
        _modal_fn(check=True)          # ← résolution réseau réelle
        info["modal_ready"] = True
    except Exception as e:
        info["detail"] = str(e)
    return info


@app.post("/render-batch")
def render_batch(req: BatchRequest):
    run_id = req.run_id or f"run_{int(time.time())}_{uuid.uuid4().hex[:8]}"
    run_dir = OUTPUT_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    # 1. Images côté bridge
    items_for_modal = []
    for it in req.items:
        try:
            img_bytes = _fetch_image_bytes(it.image_url)
            items_for_modal.append({
                "key": it.key,
                "image_b64": base64.b64encode(img_bytes).decode("ascii"),
                "prompt": it.prompt,
                "duration": it.duration or 5,
                "fps": it.fps or 24,
                "seed": it.seed if it.seed is not None
                        else int(time.time() * 1000) % (2**31),
            })
        except Exception as e:
            items_for_modal.append({
                "key": it.key,
                "error": f"bridge image fetch: {e}",
            })

    # 2. UN seul appel Modal (pas de check, handle déjà validé par /health)
    try:
        fn = _modal_fn(check=False)
        raw_results = fn.remote(items_for_modal, run_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Modal error: {e}")

    # 3. Sauvegarde locale + URLs
    out_results = []
    metrics = None

    for r in raw_results:
        if r.get("key") == "__metrics__":
            metrics = r
            continue

        key = r.get("key")
        if r.get("ok") and r.get("mp4_b64"):
            try:
                mp4 = base64.b64decode(r["mp4_b64"])
                path = run_dir / f"{key}.mp4"
                path.write_bytes(mp4)
                url = f"{BASE_URL}/output/{run_id}/{key}.mp4"
                out_results.append({
                    "key": key, "ok": True,
                    "url": url, "elapsed": r.get("elapsed"),
                })
            except Exception as e:
                out_results.append({
                    "key": key, "ok": False,
                    "error": f"bridge save error: {e}",
                })
        else:
            out_results.append({
                "key": key, "ok": False,
                "error": r.get("error", "unknown error"),
            })

    return {
        "ok": True,
        "run_id": run_id,
        "results": out_results,
        "metrics": metrics,
    }


# ------------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    print("─" * 60)
    print(f"NewsReel LTX bridge  →  http://{HOST}:{PORT}")
    print(f"Output               →  {OUTPUT_DIR}")
    print("─" * 60)
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")