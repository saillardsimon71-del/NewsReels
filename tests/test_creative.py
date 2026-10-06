from __future__ import annotations

from newsreel.creative import (
    DIRECTORS,
    PALETTES,
    apply_creative_postprocessing,
    build_host_image_prompt,
    build_host_video_prompt,
    build_reporter_image_prompt,
    build_reporter_video_prompt,
    build_scenario_prompt,
)
from newsreel.models import NewsItem


def _scenario_value():
    return {
        "jt_title": "Le JT de NewsReel — test",
        "host": {
            "name": "Alice",
            "description": "anchor with chrome glasses",
            "plateau": "television desk with giant machinery",
            "host_action": "a giant chrome lever starts moving",
            "stanislavski": {
                "objective": "deliver the news",
                "obstacle": "the absurd studio",
            },
        },
        "segments": [
            {
                "headline": "Titre exact",
                "summary": "Résumé factuel.",
                "host_dialogue": "Une information factuelle est annoncée depuis le plateau ce matin.",
                "host_action": "a giant chrome dial spins behind the host",
                "people": [
                    {"name": "Bob", "role": "witness", "description": "orange coat"}
                ],
                "location": "a civic plaza",
                "scene_action": "a huge harmless machine slowly blocks the reporter",
                "camera_plan": "establishing shot, reaction close-up, final wide",
                "reporter": {
                    "name": "Camille",
                    "description": "field reporter with round glasses",
                    "dialogue": "Même la machine semble avoir demandé son propre temps de parole aujourd'hui.",
                },
            }
        ],
    }


def test_historical_creative_catalog_and_prompt_sections_are_restored() -> None:
    assert len(DIRECTORS) == 25
    assert len(PALETTES) == 16
    prompt = build_scenario_prompt([NewsItem(title="Titre exact")], 3, "wes_anderson", "electric_coral_cyan")
    for marker in (
        "CORE FORMAT — EVERY SEGMENT IS A COMPLETE COMEDIC SKETCH",
        "ABSOLUTE FACT RULE",
        "COMEDIC CONSTRUCTION FOR EVERY SEGMENT",
        "VISUAL WORLD — MANDATORY FOR ALL CHARACTERS AND SETS",
        "STANISLAVSKI",
        "WES ANDERSON",
        "CORAIL ÉLECTRIQUE & CYAN",
        "Exactly 3 segments",
    ):
        assert marker in prompt


def test_postprocessing_and_image_prompts_restore_retrofuturist_world() -> None:
    value = apply_creative_postprocessing(
        _scenario_value(),
        1,
        director="wes_anderson",
        palette="electric_coral_cyan",
    )
    segment = value["segments"][0]
    assert "retro-futuristic funny costume" in segment["reporter"]["description"]
    assert "retro-futuristic funny costume" in segment["people"][0]["description"]
    assert "hallucinatory retrofuturist architecture" in segment["location"]

    host_prompt = build_host_image_prompt(value["host"], "wes_anderson", "electric_coral_cyan")
    reporter_prompt = build_reporter_image_prompt(segment, "wes_anderson", "electric_coral_cyan")
    assert "MANDATORY CHARACTER DESIGN" in host_prompt
    assert "MANDATORY SET DESIGN" in host_prompt
    assert "No generic modern studio look" in host_prompt
    assert "SELF-CONTAINED COMEDIC FIELD-REPORT SKETCH" in reporter_prompt
    assert "SECONDARY CHARACTERS" in reporter_prompt
    assert "SCENE ACTION" in reporter_prompt


def test_video_prompts_keep_comedy_direction_and_h3_french_dialogue() -> None:
    value = apply_creative_postprocessing(
        _scenario_value(),
        1,
        director="wes_anderson",
        palette="electric_coral_cyan",
    )
    segment = value["segments"][0]
    host_prompt = build_host_video_prompt(
        value, segment, "wes_anderson", "electric_coral_cyan", 10.125
    )
    reporter_prompt = build_reporter_video_prompt(
        segment, "wes_anderson", "electric_coral_cyan", 10.125
    )
    assert "VISUAL GAG" in host_prompt
    assert "STANISLAVSKI" in host_prompt
    assert "<d>[French] " in host_prompt
    assert "COMPLETE COMEDIC FIELD-REPORT SKETCH" in reporter_prompt
    assert "CRITICAL DIALOGUE RULE" in reporter_prompt
    assert "LIP SYNC" not in reporter_prompt
    assert "<d>[French] " in reporter_prompt
