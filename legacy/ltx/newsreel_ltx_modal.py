"""
Modal worker — LTX-2.5 I2V batch renderer for NewsReel Studio.

Déploiement :
    modal deploy newsreel_ltx_modal.py

Puis le bridge local appelle :
    modal.Function.from_name("newsreel-ltx", "render_batch").remote(items, run_id)

UN appel Modal = UN JT complet = plusieurs clips dans le même conteneur.
Le conteneur est détruit immédiatement après (single_use_containers=True).
"""

import modal
import os
import json
import time
import uuid
import base64
import subprocess
from pathlib import Path


# ==============================================================================
# CONFIG
# ==============================================================================

APP_NAME = "newsreel-ltx"

VOLUME_NAME = "ltx25-comfy-models"

COMFY_DIR = "/opt/ComfyUI"
COMFY_URL = "http://127.0.0.1:8188"

VOLUME_MOUNT = "/mnt/ltx-models"

WORKFLOW_REMOTE = "/opt/workflow.json"

# Valeur officielle actuelle du node built-in ResolutionSelector ComfyUI.
TARGET_ASPECT = "9:16 (Portrait Widescreen)"

TARGET_MP = 0.4
TARGET_MULT = 32
TARGET_FPS = 24

VIDEO_EXTS = (
    ".mp4",
    ".webm",
    ".mkv",
    ".mov",
)


app = modal.App(APP_NAME)


# ==============================================================================
# IMAGE MODAL / COMFYUI
# ==============================================================================

_image = (
    modal.Image
    .debian_slim(
        python_version="3.11"
    )
    .apt_install(
        "git",
        "ffmpeg",
        "libgl1",
        "libglib2.0-0",
        "libsm6",
        "libxext6",
        "libxrender1",
        "wget",
        "curl",
    )
    .run_commands(
        f"git clone https://github.com/Comfy-Org/ComfyUI.git {COMFY_DIR}",
        f"cd {COMFY_DIR} && pip install -r requirements.txt",
    )
    .pip_install(
        "requests",
        "safetensors",
        "einops",
        "sentencepiece",
        "ftfy",
        "pydantic",
        "pillow",
        "numpy",
    )
    .add_local_file(
        "video_ltx2_5_i2v.json",
        remote_path=WORKFLOW_REMOTE,
    )
)


_volume = modal.Volume.from_name(
    VOLUME_NAME,
    create_if_missing=False,
)


# ==============================================================================
# MODELS
# ==============================================================================

_MODEL_MAP = {
    "diffusion_models":
        f"{COMFY_DIR}/models/diffusion_models",

    "text_encoders":
        f"{COMFY_DIR}/models/text_encoders",

    "vae":
        f"{COMFY_DIR}/models/vae",

    "latent_upscale_models":
        f"{COMFY_DIR}/models/latent_upscale_models",
}


def _setup_symlinks():

    for vol_sub, comfy_dir in _MODEL_MAP.items():

        src_dir = os.path.join(
            VOLUME_MOUNT,
            vol_sub,
        )

        os.makedirs(
            comfy_dir,
            exist_ok=True,
        )

        if not os.path.isdir(src_dir):
            continue

        for fname in os.listdir(src_dir):

            src = os.path.join(
                src_dir,
                fname,
            )

            dst = os.path.join(
                comfy_dir,
                fname,
            )

            if os.path.exists(dst):
                continue

            try:
                os.symlink(
                    src,
                    dst,
                )

            except FileExistsError:
                pass

    os.makedirs(
        os.path.join(
            COMFY_DIR,
            "input",
        ),
        exist_ok=True,
    )

    os.makedirs(
        os.path.join(
            COMFY_DIR,
            "output",
        ),
        exist_ok=True,
    )


# ==============================================================================
# COMFYUI PROCESS
# ==============================================================================

def _start_comfyui():

    env = os.environ.copy()

    env["PYTHONUNBUFFERED"] = "1"

    proc = subprocess.Popen(
        [
            "python",
            "main.py",

            "--listen",
            "127.0.0.1",

            "--port",
            "8188",

            "--reserve-vram",
            "1",

            "--disable-auto-launch",
        ],
        cwd=COMFY_DIR,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    return proc


def _wait_comfy(
    proc,
    timeout=300,
):

    import requests

    t0 = time.time()

    while (
        time.time() - t0
        < timeout
    ):

        if proc.poll() is not None:

            raise RuntimeError(
                "ComfyUI s'est arrêté pendant le démarrage"
            )

        try:

            r = requests.get(
                f"{COMFY_URL}/system_stats",
                timeout=2,
            )

            if r.status_code == 200:
                return

        except requests.RequestException:
            pass

        time.sleep(1)

    raise TimeoutError(
        f"ComfyUI n'a pas démarré en {timeout}s"
    )


# ==============================================================================
# RESOLUTION SELECTOR
# ==============================================================================

def _collect_strings(
    value,
    output,
):
    """
    Parcourt récursivement une structure JSON quelconque.

    Anciennes versions ComfyUI :
        [["1:1 ...", "9:16 ..."], {...}]

    Versions récentes :
        ["COMBO", {"options": [...]}]

    On supporte les deux.
    """

    if isinstance(
        value,
        str,
    ):

        output.append(
            value
        )

        return

    if isinstance(
        value,
        (list, tuple),
    ):

        for item in value:

            _collect_strings(
                item,
                output,
            )

        return

    if isinstance(
        value,
        dict,
    ):

        for item in value.values():

            _collect_strings(
                item,
                output,
            )


def _get_aspect_ratio_value():
    """
    Essaie de découvrir la valeur réellement exposée
    par ResolutionSelector.

    Si le schema /object_info ne fournit pas les options
    de manière exploitable, on utilise la valeur officielle
    actuelle de ComfyUI :

        9:16 (Portrait Widescreen)
    """

    import requests

    try:

        r = requests.get(
            f"{COMFY_URL}/object_info/ResolutionSelector",
            timeout=15,
        )

        r.raise_for_status()

        info = r.json()

        node_info = (
            info.get(
                "ResolutionSelector"
            )
            or {}
        )

        inputs = (
            node_info.get(
                "input"
            )
            or {}
        )

        required = (
            inputs.get(
                "required"
            )
            or {}
        )

        ar_spec = required.get(
            "aspect_ratio"
        )

        strings = []

        _collect_strings(
            ar_spec,
            strings,
        )

        # Nettoyage des marqueurs de type ComfyUI.
        candidates = []

        for value in strings:

            if not isinstance(
                value,
                str,
            ):
                continue

            if value in {
                "COMBO",
                "STRING",
                "FLOAT",
                "INT",
            }:
                continue

            if value not in candidates:

                candidates.append(
                    value
                )

        print(
            "[MODAL] ResolutionSelector "
            f"object_info candidates: {candidates}"
        )

        # Valeur exacte officielle actuelle.
        if TARGET_ASPECT in candidates:

            return TARGET_ASPECT

        # Compatibilité si le texte change légèrement
        # mais conserve 9:16.
        for candidate in candidates:

            if candidate.startswith(
                "9:16"
            ):

                return candidate

        # Certaines versions ne retournent que "COMBO"
        # sans exposer les options dans object_info.
        print(
            "[MODAL] ResolutionSelector options "
            "non exposées par object_info. "
            f"Fallback officiel : {TARGET_ASPECT!r}"
        )

        return TARGET_ASPECT

    except Exception as e:

        print(
            "[MODAL] WARN ResolutionSelector "
            f"object_info indisponible : {e}"
        )

        print(
            "[MODAL] Utilisation du fallback officiel : "
            f"{TARGET_ASPECT!r}"
        )

        return TARGET_ASPECT


# ==============================================================================
# WORKFLOW
# ==============================================================================

def _load_workflow():

    with open(
        WORKFLOW_REMOTE,
        "r",
        encoding="utf-8",
    ) as f:

        return json.load(f)


def _find_node(
    wf,
    *,
    class_type=None,
    title=None,
):

    for nid, node in wf.items():

        if not isinstance(
            node,
            dict,
        ):
            continue

        if (
            class_type is not None
            and
            node.get(
                "class_type"
            )
            != class_type
        ):
            continue

        if title is not None:

            node_title = (
                node.get(
                    "_meta"
                )
                or {}
            ).get(
                "title",
                "",
            )

            if node_title != title:
                continue

        return (
            nid,
            node,
        )

    return (
        None,
        None,
    )


def _apply_item_to_workflow(
    wf,
    item,
    image_filename,
    aspect_ratio_value,
    run_id,
):

    # --------------------------------------------------------------------------
    # LoadImage
    # --------------------------------------------------------------------------

    _, load_img = _find_node(
        wf,
        class_type="LoadImage",
    )

    if load_img is None:

        raise RuntimeError(
            "Node LoadImage introuvable"
        )

    load_img[
        "inputs"
    ][
        "image"
    ] = image_filename


    # --------------------------------------------------------------------------
    # ResolutionSelector
    # --------------------------------------------------------------------------

    _, resolution = _find_node(
        wf,
        class_type="ResolutionSelector",
    )

    if resolution is None:

        raise RuntimeError(
            "Node ResolutionSelector introuvable"
        )

    resolution[
        "inputs"
    ][
        "aspect_ratio"
    ] = aspect_ratio_value

    resolution[
        "inputs"
    ][
        "megapixels"
    ] = TARGET_MP

    resolution[
        "inputs"
    ][
        "multiple"
    ] = TARGET_MULT


    # --------------------------------------------------------------------------
    # Prompt EXACT
    # --------------------------------------------------------------------------

    _, prompt_node = _find_node(
        wf,
        class_type="PrimitiveStringMultiline",
        title="Prompt",
    )

    if prompt_node is None:

        raise RuntimeError(
            "Node PrimitiveStringMultiline "
            "'Prompt' introuvable"
        )

    prompt_node[
        "inputs"
    ][
        "value"
    ] = item["prompt"]


    # --------------------------------------------------------------------------
    # Duration
    # --------------------------------------------------------------------------

    _, duration_node = _find_node(
        wf,
        class_type="PrimitiveInt",
        title="Duration",
    )

    if duration_node is None:

        raise RuntimeError(
            "Node Duration introuvable"
        )

    duration_node[
        "inputs"
    ][
        "value"
    ] = int(
        item.get(
            "duration",
            5,
        )
    )


    # --------------------------------------------------------------------------
    # FPS
    # --------------------------------------------------------------------------

    _, fps_node = _find_node(
        wf,
        class_type="PrimitiveInt",
        title="Frame Rate",
    )

    if fps_node is None:

        raise RuntimeError(
            "Node Frame Rate introuvable"
        )

    fps_node[
        "inputs"
    ][
        "value"
    ] = TARGET_FPS


    # --------------------------------------------------------------------------
    # Prompt Enhance OFF
    # --------------------------------------------------------------------------

    _, enhance_node = _find_node(
        wf,
        class_type="PrimitiveBoolean",
        title="Boolean (Enable Prompt Enhance)",
    )

    if enhance_node is not None:

        enhance_node[
            "inputs"
        ][
            "value"
        ] = False


    # --------------------------------------------------------------------------
    # RandomNoise
    # --------------------------------------------------------------------------

    seed = int(
        item.get(
            "seed"
        )
        or
        (
            uuid.uuid4().int
            %
            (2 ** 31)
        )
    )

    noise_count = 0

    for node in wf.values():

        if not isinstance(
            node,
            dict,
        ):
            continue

        if (
            node.get(
                "class_type"
            )
            ==
            "RandomNoise"
        ):

            node[
                "inputs"
            ][
                "noise_seed"
            ] = seed

            noise_count += 1

    if noise_count == 0:

        raise RuntimeError(
            "Aucun node RandomNoise dans le workflow"
        )


    # --------------------------------------------------------------------------
    # SaveVideo
    # --------------------------------------------------------------------------

    _, save_video = _find_node(
        wf,
        class_type="SaveVideo",
    )

    if save_video is None:

        raise RuntimeError(
            "Node SaveVideo introuvable"
        )

    save_video[
        "inputs"
    ][
        "filename_prefix"
    ] = (
        f"newsreel/"
        f"{run_id}/"
        f"{item['key']}"
    )


# ==============================================================================
# COMFY API
# ==============================================================================

def _queue_prompt(
    wf,
):

    import requests

    payload = {
        "prompt":
            wf,

        "client_id":
            uuid.uuid4().hex,
    }

    r = requests.post(
        f"{COMFY_URL}/prompt",
        json=payload,
        timeout=60,
    )

    if not r.ok:

        raise RuntimeError(
            f"/prompt HTTP "
            f"{r.status_code} — "
            f"{r.text[:1500]}"
        )

    data = r.json()

    prompt_id = data.get(
        "prompt_id"
    )

    if not prompt_id:

        raise RuntimeError(
            "/prompt sans prompt_id : "
            f"{data}"
        )

    return prompt_id


def _wait_history(
    prompt_id,
    proc,
    timeout=2400,
):
    """
    IMPORTANT :

    La présence du prompt_id dans /history
    ne signifie PAS nécessairement que le rendu est fini.

    On attend réellement status.completed == True.
    """

    import requests

    t0 = time.time()

    last_print = 0

    while True:

        if proc.poll() is not None:

            raise RuntimeError(
                "ComfyUI s'est arrêté "
                "pendant la génération"
            )

        elapsed = (
            time.time()
            -
            t0
        )

        if elapsed > timeout:

            raise TimeoutError(
                f"Génération "
                f"{prompt_id} "
                f"> {timeout}s"
            )

        try:

            r = requests.get(
                f"{COMFY_URL}/history/{prompt_id}",
                timeout=15,
            )

            if r.ok:

                history = r.json()

                entry = history.get(
                    prompt_id
                )

                if entry:

                    status = (
                        entry.get(
                            "status"
                        )
                        or {}
                    )

                    completed = (
                        status.get(
                            "completed"
                        )
                    )

                    status_str = (
                        status.get(
                            "status_str"
                        )
                    )

                    if completed is True:

                        return entry

                    # Compatibilité avec certaines
                    # versions ComfyUI.
                    if (
                        status_str
                        ==
                        "success"
                    ):

                        return entry

                    if status_str in {
                        "error",
                        "failed",
                    }:

                        raise RuntimeError(
                            "ComfyUI job failed:\n"
                            +
                            json.dumps(
                                entry,
                                ensure_ascii=False,
                                indent=2,
                            )[:8000]
                        )

        except requests.RequestException:
            pass

        elapsed_int = int(
            elapsed
        )

        if (
            elapsed_int
            -
            last_print
            >=
            10
        ):

            print(
                "[MODAL] "
                f"{prompt_id[:8]} "
                "running... "
                f"{elapsed_int}s"
            )

            last_print = (
                elapsed_int
            )

        time.sleep(1)


# ==============================================================================
# FIND OUTPUT VIDEO
# ==============================================================================

def _find_video_by_prefix(
    key,
    run_id,
):

    output_root = (
        Path(COMFY_DIR)
        /
        "output"
    )

    run_dir = (
        output_root
        /
        "newsreel"
        /
        run_id
    )

    search_dirs = []

    if run_dir.is_dir():

        search_dirs.append(
            run_dir
        )

    search_dirs.append(
        output_root
    )

    for directory in search_dirs:

        try:

            candidates = [
                path

                for path
                in directory.rglob(
                    f"{key}*"
                )

                if (
                    path.is_file()
                    and
                    path.suffix.lower()
                    in VIDEO_EXTS
                )
            ]

        except Exception:

            candidates = []

        if candidates:

            # Plus gros fichier récent en priorité.
            candidates.sort(
                key=lambda p: (
                    p.stat().st_mtime,
                    p.stat().st_size,
                ),
                reverse=True,
            )

            chosen = (
                candidates[0]
            )

            print(
                "[MODAL] output found: "
                f"{chosen} "
                f"({chosen.stat().st_size} bytes)"
            )

            return (
                chosen.read_bytes()
            )

    return None


def _history_fallback(
    history,
):

    outputs = (
        history
        or {}
    ).get(
        "outputs"
    ) or {}

    for out in outputs.values():

        if not isinstance(
            out,
            dict,
        ):
            continue

        for output_key in (
            "videos",
            "gifs",
            "video",
            "files",
        ):

            value = out.get(
                output_key,
                [],
            )

            if isinstance(
                value,
                dict,
            ):
                value = [value]

            if not isinstance(
                value,
                list,
            ):
                continue

            for item in value:

                if not isinstance(
                    item,
                    dict,
                ):
                    continue

                filename = item.get(
                    "filename"
                )

                if not filename:
                    continue

                subfolder = (
                    item.get(
                        "subfolder"
                    )
                    or ""
                )

                ftype = (
                    item.get(
                        "type"
                    )
                    or
                    "output"
                )

                if ftype == "temp":

                    base = (
                        Path(COMFY_DIR)
                        /
                        "temp"
                    )

                else:

                    base = (
                        Path(COMFY_DIR)
                        /
                        "output"
                    )

                path = (
                    base
                    /
                    subfolder
                    /
                    filename
                )

                if path.exists():

                    print(
                        "[MODAL] output found "
                        "via history: "
                        f"{path}"
                    )

                    return (
                        path.read_bytes()
                    )

    return None


# ==============================================================================
# GENERATE ONE CLIP
# ==============================================================================

def _generate_one(
    wf_template,
    item,
    aspect_ratio_value,
    run_id,
    proc,
):

    wf = json.loads(
        json.dumps(
            wf_template
        )
    )

    key = item["key"]

    uid = (
        uuid.uuid4()
        .hex[:10]
    )

    img_filename = (
        f"newsreel_"
        f"{key}_"
        f"{uid}.png"
    )

    img_path = (
        Path(COMFY_DIR)
        /
        "input"
        /
        img_filename
    )

    img_path.write_bytes(
        base64.b64decode(
            item[
                "image_b64"
            ]
        )
    )

    try:

        _apply_item_to_workflow(
            wf,
            item,
            img_filename,
            aspect_ratio_value,
            run_id,
        )

        prompt_id = _queue_prompt(
            wf
        )

        print(
            "[MODAL] queued "
            f"{key} "
            f"prompt_id={prompt_id}"
        )

        history = _wait_history(
            prompt_id,
            proc,
        )

        print(
            "[MODAL] completed "
            f"{key}"
        )

        mp4 = _find_video_by_prefix(
            key,
            run_id,
        )

        if mp4 is None:

            mp4 = _history_fallback(
                history
            )

        if mp4 is None:

            raise RuntimeError(
                "Rendu ComfyUI terminé "
                "mais MP4 introuvable "
                f"pour {key}"
            )

        return mp4

    finally:

        try:

            img_path.unlink()

        except Exception:
            pass


# ==============================================================================
# MODAL ENTRYPOINT
# ==============================================================================

@app.function(
    image=_image,

    gpu="A10G",

    cpu=4,

    memory=32768,

    timeout=3600,

    max_containers=1,

    single_use_containers=True,

    volumes={
        VOLUME_MOUNT:
            _volume
    },
)
def render_batch(
    items: list,
    run_id: str = "run",
) -> list:

    remote_start = (
        time.perf_counter()
    )

    results = []

    _setup_symlinks()

    startup_start = (
        time.perf_counter()
    )

    proc = _start_comfyui()

    try:

        _wait_comfy(
            proc
        )

        comfy_startup_seconds = (
            time.perf_counter()
            -
            startup_start
        )

        print("")
        print(
            "========================================"
        )
        print(
            "NEWSREEL LTX BATCH"
        )
        print(
            "========================================"
        )

        print(
            "ComfyUI ready in "
            f"{comfy_startup_seconds:.1f}s"
        )

        print(
            f"Clips: {len(items)}"
        )

        print("")

        aspect_ratio_value = (
            _get_aspect_ratio_value()
        )

        print(
            "[MODAL] ResolutionSelector "
            "aspect_ratio = "
            f"{aspect_ratio_value!r}"
        )

        print(
            "[MODAL] ResolutionSelector "
            f"megapixels = {TARGET_MP}"
        )

        print(
            "[MODAL] ResolutionSelector "
            f"multiple = {TARGET_MULT}"
        )

        wf_template = (
            _load_workflow()
        )

        for index, item in enumerate(
            items,
            start=1,
        ):

            key = item.get(
                "key",
                f"clip-{index}",
            )

            if item.get(
                "error"
            ):

                results.append(
                    {
                        "key":
                            key,

                        "ok":
                            False,

                        "error":
                            item[
                                "error"
                            ],
                    }
                )

                continue

            print("")
            print(
                "----------------------------------------"
            )

            print(
                "CLIP "
                f"{index}/"
                f"{len(items)} "
                f": {key}"
            )

            print(
                "----------------------------------------"
            )

            clip_start = (
                time.perf_counter()
            )

            try:

                mp4 = _generate_one(
                    wf_template,
                    item,
                    aspect_ratio_value,
                    run_id,
                    proc,
                )

                clip_seconds = (
                    time.perf_counter()
                    -
                    clip_start
                )

                results.append(
                    {
                        "key":
                            key,

                        "ok":
                            True,

                        "mp4_b64":
                            base64.b64encode(
                                mp4
                            ).decode(
                                "ascii"
                            ),

                        "elapsed":
                            clip_seconds,
                    }
                )

                print(
                    "[MODAL] "
                    f"{key} OK "
                    f"in "
                    f"{clip_seconds:.1f}s"
                )

            except Exception as e:

                clip_seconds = (
                    time.perf_counter()
                    -
                    clip_start
                )

                results.append(
                    {
                        "key":
                            key,

                        "ok":
                            False,

                        "elapsed":
                            clip_seconds,

                        "error":
                            (
                                f"{type(e).__name__}: "
                                f"{e}"
                            ),
                    }
                )

                print(
                    "[MODAL] "
                    f"{key} FAILED "
                    f"after "
                    f"{clip_seconds:.1f}s "
                    f"— {e}"
                )

        total_seconds = (
            time.perf_counter()
            -
            remote_start
        )

        results.append(
            {
                "key":
                    "__metrics__",

                "ok":
                    True,

                "comfy_startup_s":
                    comfy_startup_seconds,

                "session_total_s":
                    total_seconds,
            }
        )

        print("")
        print(
            "========================================"
        )

        print(
            "BATCH COMPLETE"
        )

        print(
            "========================================"
        )

        print(
            "TOTAL GPU SESSION: "
            f"{total_seconds:.1f}s"
        )

        print(
            "========================================"
        )

        print("")

        return results

    finally:

        try:

            proc.terminate()

            try:

                proc.wait(
                    timeout=8
                )

            except Exception:

                proc.kill()

        except Exception:
            pass