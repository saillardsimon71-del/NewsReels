from __future__ import annotations

import copy
import json
from typing import Any


def patch_api_workflow(
    workflow_value: dict[str, Any], job: dict[str, Any], uploaded_image: str, prefix: str
) -> dict[str, Any]:
    """Patch only per-reporter values; sampler/model/VSA settings remain from the validated graph."""
    workflow = copy.deepcopy(workflow_value)
    if "prompt" in workflow and isinstance(workflow["prompt"], dict):
        workflow = copy.deepcopy(workflow["prompt"])
    if not isinstance(workflow, dict) or not workflow:
        raise ValueError("Le workflow doit être un export ComfyUI API non vide.")
    serialized = json.dumps(workflow, ensure_ascii=False).casefold()
    if not any(
        marker in serialized
        for marker in ("vsa", "sparseattention", "sparse_attention", "sparse attention")
    ):
        raise ValueError(
            "Le workflow ne déclare pas Video Sparse Attention/VSA; le worker refuse de lancer "
            "un rendu qui ne respecte pas la configuration FastH3 validée."
        )
    if not any(marker in serialized for marker in ("fasth3", "fastvideo", "8-step v2", "8step_v2")):
        raise ValueError(
            "Le workflow ne semble pas référencer FastH3 8-Step V2; aucun checkpoint de remplacement "
            "ne sera choisi automatiquement."
        )

    image_nodes = 0
    h3_nodes = 0
    save_nodes = 0
    for node in workflow.values():
        if not isinstance(node, dict):
            continue
        class_type = str(node.get("class_type", ""))
        lower = class_type.casefold()
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        if "fps" in inputs:
            inputs["fps"] = 24
        if "loadimage" in lower and "image" in inputs:
            inputs["image"] = uploaded_image
            image_nodes += 1
        if "filename_prefix" in inputs and ("video" in lower or "save" in lower):
            inputs["filename_prefix"] = prefix
            save_nodes += 1
        is_h3 = "minimaxh3" in lower or (
            "prompt" in inputs
            and "width" in inputs
            and "height" in inputs
            and ("length" in inputs or "duration" in inputs or "value_1" in inputs)
        )
        if not is_h3:
            continue
        h3_nodes += 1
        for name, value in (
            ("prompt", job["prompt"]),
            ("width", 768),
            ("height", 1344),
            ("length", 243),
            ("duration", 10.125),
            ("value_1", 10.125),
            ("steps", 8),
        ):
            if name in inputs:
                inputs[name] = value
        for name in ("first_frame", "image"):
            if name in inputs and isinstance(inputs[name], str):
                inputs[name] = uploaded_image

    if image_nodes == 0:
        raise ValueError("Workflow FastH3 invalide: aucun nœud LoadImage à alimenter.")
    if h3_nodes != 1:
        raise ValueError(
            f"Workflow FastH3 invalide: {h3_nodes} nœuds H3 candidats trouvés, un seul attendu."
        )
    if save_nodes == 0:
        raise ValueError("Workflow FastH3 invalide: aucun SaveVideo avec filename_prefix.")
    return workflow


def validate_api_workflow(workflow_value: dict[str, Any]) -> None:
    """Fail before a paid cloud call if the supplied graph is not the validated H3/VSA graph."""
    patch_api_workflow(
        workflow_value,
        {"prompt": "NewsReel preflight"},
        "newsreel-preflight.png",
        "newsreel/preflight",
    )
