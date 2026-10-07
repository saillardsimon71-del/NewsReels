from copy import deepcopy

import pytest
from test_creative import _scenario_value
from test_h3_contract import _six_jobs

from newsreel.config import Settings
from newsreel.creative import (
    DIRECTORS,
    apply_creative_postprocessing,
    build_host_video_prompt,
    build_reporter_image_prompt,
    build_reporter_video_prompt,
)
from newsreel.h3_worker_contract import create_h3_jobs
from newsreel.models import Scenario


def _value(direction="A small lateral arc reveals a ridiculous egg beside the reporter.", tail=0):
    value = _scenario_value()
    value["segments"][0]["camera_plan"] = {
        "host": "A gentle push-in follows the host's raised eyebrow.",
        "reporter": direction,
        "silent_tail_seconds": tail,
    }
    return value


def test_free_staging_survives_scenario_save_and_reload():
    value = _value()
    saved = Scenario.from_mapping(value).to_dict()
    assert saved["segments"][0]["camera_plan"] == value["segments"][0]["camera_plan"]
    assert Scenario.from_mapping(saved).segments[0].camera_plan == value["segments"][0]["camera_plan"]


@pytest.mark.parametrize("direction", [
    "A small lateral arc reveals a ridiculous egg beside the reporter.",
    "A rack focus briefly reveals a chrome hen, then returns to the foreground face.",
    "A puppet curtain drops beside the reporter, who gives the lens a silent suspicious look.",
    "After speech the viewer IS the camera: the same physical viewpoint continuously pivots 180 degrees, visibly sweeping sideways to reveal the silent cameraman beside the reporter. No cut, no phone, no second camera visible. Both hold a selfie pose.",
])
def test_agnes_direction_reaches_h3_freely_without_a_catalogue(direction):
    value = _value(direction)
    segment = value["segments"][0]
    for director in DIRECTORS:
        prompt = build_reporter_video_prompt(segment, director, "electric_coral_cyan", 8)
        assert direction in prompt
        assert prompt.count(segment["reporter"]["dialogue"]) == 1
        assert prompt.count("<d>") == 1
        assert "Camera: " not in prompt
        assert len(prompt.split()) < 350
    host = build_host_video_prompt(value, segment, "wes_anderson", "electric_coral_cyan", 8)
    assert segment["camera_plan"]["host"] in host
    assert direction not in host


def test_safe_keyframe_does_not_widen_to_fit_secondary_cast():
    segment = _value()["segments"][0]
    prompt = build_reporter_image_prompt(segment, "villeneuve", "electric_coral_cyan")
    assert "head and shoulders" in prompt
    assert "quarter of the image height" in prompt
    assert "All characters are visible" not in prompt
    assert "CAMERA LANGUAGE" not in prompt
    assert segment["camera_plan"]["reporter"] not in prompt


def test_keyframe_uses_agnes_initial_setup_instead_of_animating_all_gag_stages():
    segment = _value()["segments"][0]
    segment["reporter_image_prompt"] = "A large egg rests motionless on the reporter's chrome helmet."
    segment["scene_action"] = "The egg rolls off the helmet and falls into a giant cup."
    prompt = build_reporter_image_prompt(segment, "wes_anderson", "electric_coral_cyan")
    assert segment["reporter_image_prompt"] in prompt
    assert segment["scene_action"] not in prompt


def test_reporter_can_leave_frame_after_speaking_without_framing_contradiction():
    segment = _value("After speech, a continuous turn reveals the silent crew.")["segments"][0]
    prompt = build_reporter_video_prompt(segment, "wes_anderson", "electric_coral_cyan", 8)
    assert "while speaking" in prompt
    assert "throughout the shot" not in prompt
    assert "No readable text, subtitles or logos" in prompt


def test_legacy_camera_plan_remains_loadable_without_unsafe_first_frame():
    value = _scenario_value()
    scenario = Scenario.from_mapping(value)
    assert scenario.to_dict()["segments"][0]["camera_plan"] == value["segments"][0]["camera_plan"]
    prompt = build_reporter_video_prompt(scenario.segments[0].to_dict(), "wes_anderson", "electric_coral_cyan", 8)
    assert "medium close-up" in prompt
    assert "establishing shot" not in prompt
    assert "final wide" not in prompt


def test_free_direction_is_deterministic_and_postprocessing_does_not_choose_effects():
    value = _value("The reporter silently hides a giant rubber egg inside an absurd pocket.")
    a = apply_creative_postprocessing(value, 1, "wes_anderson", "electric_coral_cyan")
    b = apply_creative_postprocessing(deepcopy(value), 1, "wes_anderson", "electric_coral_cyan")
    assert a["segments"][0]["camera_plan"] == value["segments"][0]["camera_plan"]
    assert a == b
    assert "selfie" not in build_reporter_video_prompt(a["segments"][0], "wes_anderson", "electric_coral_cyan", 8)


@pytest.mark.parametrize("field", ["host_action", "scene_action", "camera_plan"])
def test_visual_fields_cannot_duplicate_spoken_line(field):
    value = _value()
    segment = value["segments"][0]
    if field == "camera_plan":
        segment[field]["reporter"] += " " + segment["reporter"]["dialogue"]
    else:
        segment[field] += " " + segment["reporter"]["dialogue"]
    with pytest.raises(ValueError, match="dialogue"):
        apply_creative_postprocessing(value, 1, "wes_anderson", "electric_coral_cyan")


@pytest.mark.parametrize("tail", [-1, 4, True, "2", float("nan")])
def test_invalid_silent_duration_is_rejected_for_agnes_correction(tail):
    with pytest.raises(ValueError, match="silent_tail_seconds"):
        apply_creative_postprocessing(_value(tail=tail), 1, "wes_anderson", "electric_coral_cyan")


def test_generated_silent_ending_reserves_time_without_changing_other_durations(tmp_path):
    images = _six_jobs(tmp_path)
    scenario = Scenario.from_mapping(_value(tail=2))
    scenario.segments[0].reporter_dialogue = " ".join(["mot"] * 12)
    jobs = create_h3_jobs(scenario, images[0].image_path, [images[1].image_path], Settings(project_root=tmp_path))
    assert jobs[0].frames == 124
    assert jobs[1].frames == 192
    assert jobs[1].duration_seconds == 8
    assert "8 seconds" in jobs[1].prompt
    assert "final 2 seconds" in jobs[1].prompt


def test_generated_staging_cannot_overflow_tested_h3_duration(tmp_path):
    images = _six_jobs(tmp_path)
    scenario = Scenario.from_mapping(_value(tail=3))
    scenario.segments[0].reporter_dialogue = " ".join(["mot"] * 30)
    with pytest.raises(ValueError, match="plage H3"):
        create_h3_jobs(scenario, images[0].image_path, [images[1].image_path], Settings(project_root=tmp_path))


@pytest.mark.parametrize("legacy", [False, True])
@pytest.mark.parametrize("field", ["reporter_dialogue", "host_dialogue", "people", "scene_action"])
def test_all_h3_inputs_reject_nested_speech_and_duplicated_dialogue(legacy, field):
    value = _value()
    segment = value["segments"][0]
    if legacy:
        segment["camera_plan"] = "old wide opening"
    if field == "reporter_dialogue":
        segment["reporter"]["dialogue"] = "<d>[French] Bonjour à tous.</d>"
    elif field == "host_dialogue":
        segment[field] = "Bonjour (S1), voici le journal."
    elif field == "people":
        segment["people"][0]["stanislavski"] = {"physical_action": segment["reporter"]["dialogue"]}
    else:
        segment[field] = "<d>[French] Une voix supplémentaire.</d>"
    with pytest.raises(ValueError, match="dialogue|balise"):
        build_reporter_video_prompt(segment, "wes_anderson", "electric_coral_cyan", 8)


def test_agnes_can_choose_no_secondary_cast():
    value = _value()
    value["segments"][0]["people"] = []
    result = apply_creative_postprocessing(value, 1, "wes_anderson", "electric_coral_cyan")
    assert result["segments"][0]["people"] == []


def test_reporter_cannot_be_duplicated_as_a_secondary_character():
    value = _value()
    value["segments"][0]["people"][0]["name"] = value["segments"][0]["reporter"]["name"]
    with pytest.raises(ValueError, match="reporter.*secondaire"):
        apply_creative_postprocessing(value, 1, "wes_anderson", "electric_coral_cyan")


def test_keyframe_framing_has_priority_over_the_generated_set_description():
    segment = _value()["segments"][0]
    prompt = build_reporter_image_prompt(segment, "wes_anderson", "electric_coral_cyan")
    assert prompt.index("FIRST FRAME") < prompt.index("LOCATION")
    assert "crop below the shoulders" in prompt


def test_new_scenario_rejects_long_reporter_line_for_agnes_correction():
    value = _value()
    value["segments"][0]["reporter"]["dialogue"] = " ".join(["mot"] * 22)
    with pytest.raises(ValueError, match="18 mots"):
        apply_creative_postprocessing(value, 1, "wes_anderson", "electric_coral_cyan")


@pytest.mark.parametrize("direction", ["Opening wide shot of the speaking reporter.", "Large establishing shot then close-up.", "A wide shot initially frames the entire plaza, then closes on the speaking reporter."])
def test_new_scenario_rejects_distant_speaker_opening(direction):
    with pytest.raises(ValueError, match="cadrage"):
        apply_creative_postprocessing(_value(direction), 1, "wes_anderson", "electric_coral_cyan")


@pytest.mark.parametrize("direction", ["Never use an establishing shot; stay close while the reporter speaks.", "Medium close-up while the reporter speaks, then an establishing view after speech."])
def test_framing_guard_allows_negated_wides_and_silent_scenery(direction):
    result = apply_creative_postprocessing(_value(direction), 1, "wes_anderson", "electric_coral_cyan")
    assert result["segments"][0]["camera_plan"]["reporter"] == direction


@pytest.mark.parametrize("field", ["reporter", "people", "host"])
def test_names_cannot_insert_h3_speech_tags(field):
    value = _value()
    segment = value["segments"][0]
    if field == "host":
        value["host"]["name"] = "<d>[French] Bonjour.</d>"
        with pytest.raises(ValueError, match="dialogue"):
            build_host_video_prompt(value, segment, "wes_anderson", "electric_coral_cyan", 8)
    else:
        person = segment["people"][0] if field == "people" else segment["reporter"]
        person["name"] = "<d>[French] Bonjour.</d>"
        with pytest.raises(ValueError, match="dialogue"):
            build_reporter_video_prompt(segment, "wes_anderson", "electric_coral_cyan", 8)
