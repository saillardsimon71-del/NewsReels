from __future__ import annotations

import math
import re
from typing import Any

H3_MODEL_FILES = {
    "unet": "fastvideo_fasth3_8step_v2_pruned_int8_convrot.safetensors",
    "clip": "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
    "video_vae": "minimax_h3_video_vae_int8_convrot.safetensors",
    "audio_vae": "minimax_h3_audio_vae_fp32.safetensors",
}

H3_WIDTH = 768
H3_HEIGHT = 1344
H3_FPS = 24
H3_MIN_FRAMES = 124
H3_MAX_FRAMES = 362
H3_FRAME_STEP = 17
H3_FRAME_OFFSET = 5
H3_FRAMES = H3_MIN_FRAMES
H3_DURATION_SECONDS = H3_FRAMES / H3_FPS
H3_STEPS = 8
H3_ATTENTION_BACKEND = "comfy kitchen attention"
H3_SCHEDULER = "simple"
H3_SAMPLER = "res_multistep"
H3_DENOISE = 1.0
H3_SIGMA_SHIFT = {"shift_video": 10, "shift_audio": 3}
H3_VSA_SETTINGS = {
    "selection": "vsa",
    "selection.keep_percent": 10,
    "start_percent": 0.2,
    "end_percent": 1,
    "dense_blocks": "",
    "min_tokens": 12288,
    "extra_tokens": 256,
    "sink_conditioning": "exact_kv_and_rows",
    "verbose": False,
}
H3_VOLUME_NAME = "fasth3-models"
H3_MODAL_GPU = "L40S"
H3_MODAL_CPU = 8
H3_MODAL_MEMORY_MIB = 98304
H3_MODAL_TIMEOUT_SECONDS = 5400
H3_COMFYUI_REVISION = "d49e888586dd8ae012c0667b33466b815fee07f7"


def h3_frames_for_duration(seconds: float) -> int:
    if not math.isfinite(seconds) or seconds <= 0:
        raise ValueError("La durée H3 doit être positive et finie.")
    requested = max(H3_MIN_FRAMES, math.ceil(seconds * H3_FPS))
    frames = requested + (H3_FRAME_OFFSET - requested) % H3_FRAME_STEP
    if frames > H3_MAX_FRAMES:
        raise ValueError("Le contenu dépasse la plage H3 testée (362 frames / 15,083 s).")
    return frames


def h3_frames_for_dialogue(dialogue: str, visual_seconds: float = 0, tail_seconds: float = 0) -> int:
    words = re.findall(r"\w+(?:['\u2019-]\w+)*", dialogue)
    if not words:
        raise ValueError("Le dialogue H3 est vide.")
    # NewsReels pacing estimate: 150 words/minute plus a short lead/tail margin.
    if not math.isfinite(tail_seconds) or tail_seconds < 0:
        raise ValueError("La marge silencieuse H3 doit être positive et finie.")
    return h3_frames_for_duration(max(len(words) / 2.5 + 0.75 + tail_seconds, visual_seconds))


def validate_h3_timing(frames: int, duration_seconds: float) -> None:
    if (
        type(frames) is not int
        or not H3_MIN_FRAMES <= frames <= H3_MAX_FRAMES
        or frames % H3_FRAME_STEP != H3_FRAME_OFFSET
    ):
        raise ValueError("Frames H3 invalides: grille 17k+5, plage testée 124 à 362.")
    if not isinstance(duration_seconds, (int, float)) or not math.isclose(
        duration_seconds, frames / H3_FPS, rel_tol=0, abs_tol=1e-6
    ):
        raise ValueError("La durée H3 doit correspondre aux frames à 24 fps.")


def h3_contract_config() -> dict[str, Any]:
    """Serializable batch contract shared by the local client and Modal worker."""
    return {
        "width": H3_WIDTH,
        "height": H3_HEIGHT,
        "fps": H3_FPS,
        "min_frames": H3_MIN_FRAMES,
        "max_frames": H3_MAX_FRAMES,
        "frame_step": H3_FRAME_STEP,
        "frame_offset": H3_FRAME_OFFSET,
        "steps": H3_STEPS,
        "native_audio": True,
        "models": dict(H3_MODEL_FILES),
        "attention_backend": H3_ATTENTION_BACKEND,
        "scheduler": H3_SCHEDULER,
        "sampler": H3_SAMPLER,
        "denoise": H3_DENOISE,
        "sigma_shift": dict(H3_SIGMA_SHIFT),
        "vsa": dict(H3_VSA_SETTINGS),
        "modal_gpu": H3_MODAL_GPU,
        "modal_cpu": H3_MODAL_CPU,
        "modal_memory_mib": H3_MODAL_MEMORY_MIB,
        "modal_timeout_seconds": H3_MODAL_TIMEOUT_SECONDS,
        "modal_max_containers": 1,
        "single_use_containers": True,
        "volume_name": H3_VOLUME_NAME,
        "comfyui_revision": H3_COMFYUI_REVISION,
    }


def build_h3_api_workflow(
    job: dict[str, Any], uploaded_image: str, output_prefix: str
) -> dict[str, dict[str, Any]]:
    """Build the FastH3 ComfyUI API graph in code for one H3 clip.

    The stable node IDs and loader inputs are intentionally identical for every job in a
    batch. ComfyUI therefore keeps/reuses the loaded checkpoint, text encoder and VAEs
    while each prompt changes only the input image, prompt, seed and output filename.
    """
    prompt = str(job.get("prompt", "")).strip()
    if not prompt:
        raise ValueError("Prompt H3 vide: impossible de construire le graphe FastH3.")
    if not uploaded_image:
        raise ValueError("Image H3 ComfyUI absente pour construire le graphe FastH3.")
    if not output_prefix:
        raise ValueError("Préfixe de sortie vide pour construire le graphe FastH3.")

    for key, expected in (
        ("width", H3_WIDTH),
        ("height", H3_HEIGHT),
        ("fps", H3_FPS),
        ("steps", H3_STEPS),
    ):
        if key in job and job[key] != expected:
            raise ValueError(
                f"Paramètre H3 invalide pour {key}: {job[key]!r} au lieu de {expected}."
            )

    frames = job.get("frames", H3_FRAMES)
    validate_h3_timing(frames, job.get("duration_seconds", frames / H3_FPS))

    seed = job.get("seed", 0)
    if type(seed) is not int or not 0 <= seed < 2**64:
        raise ValueError("La seed H3 doit être un entier non signé sur 64 bits.")

    return {
        # Input image and four exact checkpoint/VAE files.
        "1": {"class_type": "LoadImage", "inputs": {"image": uploaded_image}},
        "6": {
            "class_type": "UNETLoader",
            "inputs": {"unet_name": H3_MODEL_FILES["unet"], "weight_dtype": "default"},
        },
        "13": {
            "class_type": "CLIPLoader",
            "inputs": {
                "clip_name": H3_MODEL_FILES["clip"],
                "type": "minimax",
                "device": "default",
            },
        },
        "11": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": H3_MODEL_FILES["video_vae"]},
        },
        "24": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": H3_MODEL_FILES["audio_vae"]},
        },
        # Native H3 audio shift, Comfy Kitchen attention backend and VSA.
        "143": {
            "class_type": "MiniMaxH3SigmaShift",
            "inputs": {"model": ["6", 0], **H3_SIGMA_SHIFT},
        },
        "128": {
            "class_type": "ModelAttentionBackend",
            "inputs": {"model": ["143", 0], "attention": H3_ATTENTION_BACKEND},
        },
        "127": {
            "class_type": "BlockSparseAttention",
            "inputs": {"model": ["128", 0], **H3_VSA_SETTINGS},
        },
        # Video and native audio share this clip's timeline.
        "104": {
            "class_type": "MiniMaxH3ImageToVideo",
            "inputs": {
                "clip": ["13", 0],
                "vae": ["11", 0],
                "first_frame": ["1", 0],
                "prompt": prompt,
                "width": H3_WIDTH,
                "height": H3_HEIGHT,
                "length": frames,
            },
        },
        "9": {
            "class_type": "BasicScheduler",
            "inputs": {
                "model": ["127", 0],
                "scheduler": H3_SCHEDULER,
                "steps": H3_STEPS,
                "denoise": H3_DENOISE,
            },
        },
        "15": {
            "class_type": "RandomNoise",
            "inputs": {"noise_seed": seed},
        },
        "17": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": H3_SAMPLER}},
        "16": {
            "class_type": "BasicGuider",
            "inputs": {"model": ["127", 0], "conditioning": ["104", 0]},
        },
        "14": {
            "class_type": "SamplerCustomAdvanced",
            "inputs": {
                "noise": ["15", 0],
                "guider": ["16", 0],
                "sampler": ["17", 0],
                "sigmas": ["9", 0],
                "latent_image": ["104", 1],
            },
        },
        # Decode both native video and native audio, then save one ComfyUI MP4.
        "10": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["14", 0], "vae": ["11", 0]},
        },
        "23": {
            "class_type": "VAEDecodeAudio",
            "inputs": {"samples": ["14", 0], "vae": ["24", 0]},
        },
        "91": {
            "class_type": "CreateVideo",
            "inputs": {
                "images": ["10", 0],
                "audio": ["23", 0],
                "fps": H3_FPS,
                "bit_depth": "auto",
                "color_space": "sRGB",
                "codec": "none",
            },
        },
        "92": {
            "class_type": "SaveVideo",
            "inputs": {
                "video": ["91", 0],
                "filename_prefix": output_prefix,
                "format": "auto",
                "codec": "auto",
            },
        },
    }
