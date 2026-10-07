from __future__ import annotations

import math
import re
from copy import deepcopy
from typing import Any

DEFAULT_DIRECTOR = "wes_anderson"
DEFAULT_PALETTE = "electric_coral_cyan"
DEFAULT_INTENSITY = "strong"

INTENSITY_LEVELS = {
    "subtle": "Subtile — contemplatif",
    "moderate": "Modérée — élégante",
    "strong": "Forte — cinématographique",
}

INTENSITY_RULES = {
    "subtle": (
        "Controlled absurdity: keep one primary visual gag clearly readable, restrained motion, "
        "clean staging and deadpan performances. Do not remove the retrofuturist identity."
    ),
    "moderate": (
        "Clear comic escalation: a scene-specific gag, expressive blocking and purposeful "
        "camera movement while preserving readability and character stability."
    ),
    "strong": (
        "Bold cinematic satire: an immediately readable absurd situation, committed reactions "
        "and a strong final payoff. Be inventive in staging, not in the number of simultaneous actions."
    ),
}

DIRECTORS: dict[str, dict[str, str]] = {
    "wes_anderson": {"label": "Wes Anderson", "style": "Perfect bilateral symmetry, centered frontal composition, planimetric staging, dry deadpan comedy, whimsical miniature-like production design, precise theatrical blocking.", "camera": "Locked symmetrical frames, lateral whip pans, short dolly-ins, graphic centered compositions.", "lighting": "Soft studio light with deliberate practical color blocks and clean separation.", "film": "35mm-inspired texture, subtle halation, crisp production design."},
    "kubrick": {"label": "Stanley Kubrick", "style": "One-point perspective, obsessive geometry, symmetrical architecture, unsettling precision, theatrical absurdity beneath clinical seriousness.", "camera": "Slow zooms, centered wide angles, controlled tracking, geometric vanishing points.", "lighting": "Hard motivated practicals with sculpted pools of light.", "film": "35mm-inspired grain, deep focus, high micro-detail."},
    "fincher": {"label": "David Fincher", "style": "Controlled compositions, precise urban detail, restrained camera motion, tactile surfaces, darkly comic seriousness.", "camera": "Locked frames, exact push-ins, measured tracking, selective handheld impact.", "lighting": "Motivated practicals with controlled contrast and saturated colored sources.", "film": "Clean digital cinema with subtle film texture."},
    "villeneuve": {"label": "Denis Villeneuve", "style": "Monumental scale, graphic negative space, atmospheric depth, strange futuristic architecture, solemn spectacle.", "camera": "Long-lens compression, slow tracking, crane reveals, monumental wides.", "lighting": "Volumetric atmosphere, strong backlight, sculpted practical color.", "film": "Large-format cinematic clarity, restrained texture."},
    "nolan": {"label": "Christopher Nolan", "style": "Physical realism, practical spectacle, urgent spatial storytelling, massive mechanical environments, serious performances inside absurd events.", "camera": "Dynamic tracking, handheld impact shots, wide practical-action coverage.", "lighting": "Naturalistic key light mixed with motivated practical effects.", "film": "Large-format cinematic sharpness, realistic motion blur."},
    "manga_cyberpunk": {"label": "Manga cyberpunk", "style": "High-energy manga composition fused with retrofuturist cyberpunk, expressive faces, ink-like contour emphasis, holographic architecture, absurd gadgets, explosive visual punctuation.", "camera": "Extreme perspective, Dutch angles, snap zooms, diagonal action lines, rapid reframing.", "lighting": "Hard neon rims, colored reflections, luminous signs, saturated atmosphere.", "film": "Graphic ink texture blended with cinematic depth; vivid full color."},
    "retro_manga": {"label": "Manga rétrofuturiste", "style": "1960s-1980s manga futurism, optimistic machines, ridiculous helmets, giant buttons, playful mechanical design, bold graphic silhouettes.", "camera": "Graphic panel-like framing, dramatic low angles, fast push-ins, wide comic tableaux.", "lighting": "Bright studio illumination with strong colored gels.", "film": "Printed-ink texture, crisp cel-like color separation."},
    "anime_80s": {"label": "Anime années 80", "style": "Retro anime visual language, cel-shaded characters, mechanical detail, expressive reaction shots, colorful futuristic interiors, playful melodrama.", "camera": "Dynamic anime perspective, crash zooms, dramatic close-ups, wide establishing shots.", "lighting": "Hard rim lights, colored gradients, luminous practicals.", "film": "Cel-shaded finish with subtle analog texture."},
    "manga_noir": {"label": "Manga noir", "style": "Dense graphic ink, expressive faces, urban mystery, exaggerated silhouettes, hard graphic shadows with selective vivid color.", "camera": "Extreme close-ups, low angles, rapid reframing, graphic diagonals.", "lighting": "Hard side light, colored practicals, graphic shadow shapes.", "film": "Ink texture with crisp cinematic color."},
    "shonen_pop": {"label": "Shonen pop", "style": "Exaggerated action-comedy, elastic expressions, heroic poses, ridiculous props, energetic group staging, colorful graphic spectacle.", "camera": "Fast push-ins, low-angle hero shots, whip pans, impact reframes.", "lighting": "Bright high-key light with vivid colored accents.", "film": "Clean animated-cinema texture, saturated color."},
    "shojo_futuriste": {"label": "Shojo futuriste", "style": "Elegant futuristic fashion, ornate dreamlike interiors, sparkling mechanical details, expressive poses, surreal romantic geometry.", "camera": "Graceful tracking, floating crane moves, symmetrical portraits, elegant close-ups.", "lighting": "Soft luminous sources with vivid colored highlights.", "film": "Polished cinematic image with graphic decorative detail."},
    "cyberpunk_tokyo": {"label": "Cyberpunk Tokyo", "style": "Dense retrofuturist megacity, eccentric commuters, glowing vending machines, holographic clutter, absurd technology, saturated urban spectacle.", "camera": "Street-level tracking, rapid reframing, wide crowd shots, macro gadget close-ups.", "lighting": "Aggressive neon, colored reflections, luminous signage, wet surfaces.", "film": "High-detail digital cinema with neon bloom."},
    "french_bd_pop": {"label": "BD française pop", "style": "Graphic European comic aesthetic, clean contours, expressive caricature, architectural wit, flat-but-rich color blocks, absurd staging.", "camera": "Strong diagonals, clean tableaux, punchy close-ups, lateral pans.", "lighting": "Graphic directional light with bold colored shapes.", "film": "Ink-and-paint texture with cinematic depth."},
    "comic_retro": {"label": "Comic rétrofuturiste", "style": "Pulp comic spectacle, heroic caricatures, ray-gun gadgets, impossible machines, exaggerated poses, bright poster-like visual design.", "camera": "Low-angle hero frames, dramatic zooms, dynamic diagonals, panel-like cuts.", "lighting": "Graphic key light, saturated practical colors, bold rim light.", "film": "Vintage print texture with saturated cinema color."},
    "clay_satire": {"label": "Satire de plateau", "style": "Theatrical practical-set absurdism, oversized props, fake machinery, comic costumes, miniature architecture, deliberately artificial spectacle.", "camera": "Static tableaux interrupted by comic push-ins and sudden pans.", "lighting": "Bright theatrical studio lighting with colored pools.", "film": "Tactile production texture, crisp cinematic photography."},
    "documentary_color": {"label": "Documentaire couleur halluciné", "style": "Observational documentary framing but with impossible colorful events, eccentric costumes, surreal props treated as ordinary reality.", "camera": "Reactive handheld, sudden zooms, imperfect reframing, observational close-ups.", "lighting": "Available-looking light enhanced by vivid practical colors.", "film": "Documentary texture, natural motion, rich color."},
    "mockumentary_retro": {"label": "Mockumentaire rétrofuturiste", "style": "Dead-serious fake reportage, awkward public access television energy, bizarre futuristic bureaucracy, retro costumes, visual punchlines.", "camera": "Shoulder camera, awkward zooms, interview-like starts, sudden wide reveals.", "lighting": "Flat practical light mixed with outrageous colored sources.", "film": "Analog broadcast texture with vivid chroma."},
    "giallo_pop": {"label": "Giallo pop", "style": "Stylized mystery atmosphere, saturated colored lighting, baroque interiors, theatrical suspense, grotesque visual jokes, elegant silhouettes.", "camera": "Slow tracking, extreme close-ups, sudden reveal cuts, graphic overheads.", "lighting": "Strong colored gels, sharp highlights, dramatic shadows.", "film": "Glossy cinematic texture with vivid color."},
    "bollywood_futurist": {"label": "Spectacle futuriste", "style": "Grand theatrical staging, flamboyant costumes, geometric crowd choreography, extravagant futuristic sets, joyful visual excess; no musical performance required.", "camera": "Sweeping crane shots, frontal tableaux, fast circular moves, celebratory wides.", "lighting": "Brilliant saturated stage light and colored practicals.", "film": "Glossy large-scale cinema texture."},
    "sci_fi_pulp": {"label": "Science-fiction pulp", "style": "Retro science-fiction magazine aesthetic, chrome machines, ray-gun controls, bubble helmets, strange laboratories, comic seriousness.", "camera": "Wide practical sets, gadget inserts, low-angle hero shots, quick reveals.", "lighting": "Bright colored practicals, dramatic backlight, theatrical haze.", "film": "Analog pulp texture with sharp saturated color."},
    "space_opera_comedy": {"label": "Space opera comique", "style": "Huge cosmic architecture, ridiculous uniforms, theatrical commanders, impossible vehicles, majestic absurdity, dense futuristic set dressing.", "camera": "Grand wides, orbital-feeling moves, fast reaction close-ups, dramatic reveals.", "lighting": "Cosmic colored ambience, bright practical sources, strong rims.", "film": "Epic cinematic clarity with rich chroma."},
    "stopmotion_surreal": {"label": "Stop-motion surréaliste", "style": "Tactile handcrafted world, impossible proportions, oversized props, eccentric costumes, whimsical physics, deadpan comic acting.", "camera": "Miniature-scale tracking, locked tableaux, abrupt comedic reframing.", "lighting": "Theatrical practical light with vivid colored pools.", "film": "Tactile texture and miniature depth cues, full color."},
    "noir_neon": {"label": "Noir néon", "style": "Graphic noir silhouettes against saturated neon, rain-slick surfaces, strange retrofuturist costumes, serious faces in ridiculous situations.", "camera": "Low angles, slow tracking, close-up inserts, reflective wides.", "lighting": "Hard chiaroscuro combined with saturated neon color.", "film": "Cinematic grain, deep blacks, luminous color."},
    "vhs_future": {"label": "VHS futuriste", "style": "Analog-future television, chunky gadgets, bizarre retro computers, colorful costumes, deliberately strange consumer technology.", "camera": "Zoom lenses, handheld broadcast framing, sudden push-ins, surveillance-like wides.", "lighting": "Colored practicals, CRT glow, fluorescent mixtures.", "film": "VHS-inspired texture, chromatic aberration, saturated color."},
    "retro_documentary": {"label": "Faux documentaire rétro", "style": "Old television documentary grammar, futuristic 1960s design, deadpan witnesses, absurd public infrastructure, richly colored practical props.", "camera": "Tripod interviews, slow pans, zooms, observational wides.", "lighting": "Warm practical illumination with strong colored accents.", "film": "16mm-inspired texture with vivid chroma."},
}

PALETTES: dict[str, dict[str, str]] = {
    "electric_coral_cyan": {"label": "Corail électrique & Cyan", "full": "dominant electric coral #FF4F79, luminous cyan #00F5FF, hot white highlights, saturated color everywhere, no grayscale, no muted tones"},
    "acid_lime_purple": {"label": "Lime acide & Violet", "full": "acid lime #B6FF00, ultraviolet purple #7A00FF, hot pink highlights, saturated full-color world, no grayscale"},
    "turquoise_orange": {"label": "Turquoise & Orange solaire", "full": "bright turquoise #00D9C0, solar orange #FF6A00, cream-white highlights, saturated full-color world, no grayscale"},
    "fuchsia_yellow": {"label": "Fuchsia & Jaune laser", "full": "laser yellow #FFF200, electric fuchsia #FF00A8, vivid blue micro-accents, saturated full-color world, no grayscale"},
    "cobalt_tangerine": {"label": "Cobalt & Mandarine", "full": "deep cobalt #1746FF, vivid tangerine #FF7A00, hot white highlights, saturated full-color world, no grayscale"},
    "emerald_pink": {"label": "Émeraude & Rose fluo", "full": "electric emerald #00D978, fluorescent pink #FF2DAA, warm white highlights, saturated full-color world, no grayscale"},
    "violet_lime": {"label": "Violet ultraviolet & Lime", "full": "ultraviolet violet #6A00FF, radioactive lime #A8FF00, cyan highlights, saturated full-color world, no grayscale"},
    "red_cyan": {"label": "Rouge signal & Cyan", "full": "signal red #FF1838, electric cyan #00E5FF, bright ivory highlights, saturated full-color world, no grayscale"},
    "gold_azure": {"label": "Or électrique & Azur", "full": "electric gold #FFD400, vivid azure #007BFF, hot magenta micro-accents, saturated full-color world, no grayscale"},
    "magenta_teal": {"label": "Magenta & Turquoise", "full": "hot magenta #FF1493, deep turquoise #00B8A9, bright yellow highlights, saturated full-color world, no grayscale"},
    "orange_purple": {"label": "Orange mandarine & Prune", "full": "mandarin orange #FF7800, rich plum #7B1FA2, electric cyan highlights, saturated full-color world, no grayscale"},
    "lime_pink": {"label": "Citron vert & Rose bonbon", "full": "acid lime #C6FF00, candy pink #FF4FB3, sky-blue highlights, saturated full-color world, no grayscale"},
    "ultraviolet_aqua": {"label": "Ultraviolet & Aqua", "full": "ultraviolet #7000FF, luminous aqua #00FFD5, yellow highlights, saturated full-color world, no grayscale"},
    "scarlet_turquoise": {"label": "Écarlate & Turquoise", "full": "scarlet #FF2400, bright turquoise #00D4C7, lemon highlights, saturated full-color world, no grayscale"},
    "royal_blue_lime": {"label": "Bleu royal & Lime", "full": "royal blue #245BFF, electric lime #B8FF00, hot pink highlights, saturated full-color world, no grayscale"},
    "copper_electric_blue": {"label": "Cuivre & Bleu électrique", "full": "bright copper #D66A3A, electric blue #005BFF, vivid cream highlights, saturated full-color world, no grayscale"},
}

DEFAULT_HOST = {
    "name": "Chroniqueur",
    "description": "silver-haired anchor, grey suit, oversized round glasses",
    "plateau": "TV studio, symmetrical, chrome desk, giant circular portholes",
    "host_action": "the host presses a giant chrome button and the entire studio rotates while paper confetti explodes",
    "stanislavski": {
        "objective": "to deliver the news with authority",
        "obstacle": "the studio is falling apart around him",
        "given_circumstances": "He has been anchoring for 20 years and is exhausted",
        "physical_action": "presses button with deliberate slowness",
    },
}
DEFAULT_HOST_FALLBACK_ACTION = "the host turns a giant chrome crank and the studio walls split open to reveal a cityscape while paper birds fly out"
DEFAULT_REPORTER = {"name": "Reporter", "description": "grey trench coat, black umbrella, round glasses", "dialogue": ""}
DEFAULT_SCENE_ACTION = "the reporter and the people on set perform an incredible synchronized choreography while smoke fills the frame"
DEFAULT_CAMERA_PLAN = ""
DEFAULT_LOCATION = "location, symmetrical, chrome arches, concrete textures"
DEFAULT_EMOTION = "spectaculaire"
DEFAULT_REPORTER_DIALOGUE_FALLBACK = "Même ma machine à café aurait demandé une mutation."
RETRO_COSTUME_SUFFIX = "retro-futuristic funny costume with oversized geometric details, chrome accessories, absurd gadget"
LOCATION_HALLUCINATION_SUFFIX = "hallucinatory retrofuturist architecture, oversized news-related props, impossible scale"

DEFAULT_PEOPLE = [
    {"name": "Figurant 1", "description": "outfit matching the news, playful expression", "role": "witness", "stanislavski": {"objective": "to be seen", "obstacle": "anonymity", "given_circumstances": "ordinary person caught in extraordinary events", "physical_action": "waves nervously"}},
    {"name": "Figurant 2", "description": "outfit matching the news, playful expression", "role": "witness", "stanislavski": {"objective": "to understand", "obstacle": "chaos", "given_circumstances": "confused by the situation", "physical_action": "shrugs dramatically"}},
    {"name": "Figurant 3", "description": "outfit matching the news, playful expression", "role": "witness", "stanislavski": {"objective": "to help", "obstacle": "helplessness", "given_circumstances": "wants to make a difference", "physical_action": "reaches out"}},
]


def _director(key: str) -> dict[str, str]:
    try:
        return DIRECTORS[key]
    except KeyError as exc:
        raise ValueError(f"Direction artistique inconnue: {key}") from exc


def _palette(key: str) -> dict[str, str]:
    try:
        return PALETTES[key]
    except KeyError as exc:
        raise ValueError(f"Palette inconnue: {key}") from exc


def _intensity(key: str) -> str:
    try:
        return INTENSITY_RULES[key]
    except KeyError as exc:
        raise ValueError(f"Intensité inconnue: {key}") from exc


def _news_field(item: Any, name: str) -> str:
    if isinstance(item, dict):
        return str(item.get(name, "") or "").strip()
    return str(getattr(item, name, "") or "").strip()


def creative_catalog() -> dict[str, Any]:
    return {
        "directors": [{"value": key, "label": value["label"]} for key, value in DIRECTORS.items()],
        "palettes": [{"value": key, "label": value["label"], "full": value["full"]} for key, value in PALETTES.items()],
        "intensity": [{"value": key, "label": label} for key, label in INTENSITY_LEVELS.items()],
        "defaults": {
            "director": DEFAULT_DIRECTOR,
            "palette": DEFAULT_PALETTE,
            "intensity": DEFAULT_INTENSITY,
        },
    }


def camera_direction(segment: dict[str, Any], role: str) -> str:
    plan = segment.get("camera_plan")
    # Legacy prose was never sent to H3 and can request unsafe wide opening shots.
    return str(plan.get(role, "")).strip() if isinstance(plan, dict) else ""


def silent_tail_seconds(segment: dict[str, Any]) -> float:
    plan = segment.get("camera_plan")
    value = plan.get("silent_tail_seconds", 0) if isinstance(plan, dict) else 0
    if type(value) not in {int, float} or not math.isfinite(value) or not 0 <= value <= 3:
        raise ValueError("camera_plan.silent_tail_seconds doit être un nombre entre 0 et 3.")
    return float(value)


def validate_staging(segment: dict[str, Any], host: dict[str, Any] | None = None) -> None:
    plan = segment.get("camera_plan")
    silent_tail_seconds(segment)
    fields = [segment.get("host_action", ""), segment.get("scene_action", "")]
    if host:
        fields.extend([host.get("name", ""), host.get("host_action", "")])
    if isinstance(plan, dict):
        fields.extend([plan.get("host", ""), plan.get("reporter", "")])
    for person in segment.get("people") or []:
        if isinstance(person, dict):
            fields.extend([person.get("name", ""), person.get("role", "")])
            if isinstance(person.get("stanislavski"), dict):
                fields.append(person["stanislavski"].get("physical_action", ""))
    reporter = segment.get("reporter") or {}
    fields.append(reporter.get("name", ""))
    lines = [str(segment.get("host_dialogue", "")).strip(), str(reporter.get("dialogue", "")).strip()]
    if isinstance(plan, dict):
        if any(isinstance(person, dict) and person.get("name") == reporter.get("name") for person in segment.get("people") or []):
            raise ValueError("Le reporter ne doit pas être dupliqué comme personnage secondaire.")
        if len(re.findall(r"\w+(?:['\u2019-]\w+)*", lines[1])) > 18:
            raise ValueError("Raccourcir le dialogue reporter à 18 mots maximum, sans couper les mots.")
        for role in ("host", "reporter"):
            direction = str(plan.get(role, ""))
            opening = re.split(r"[.;]|\b(?:then|after speech|after speaking)\b", direction, maxsplit=1, flags=re.IGNORECASE)[0]
            if opening.lower().strip().startswith(("never ", "no ", "avoid ", "do not ")):
                continue
            if re.search(r"\b(?:wide|establishing|full.body|long)\s+(?:shot|view|frame)|(?:open\w*|start\w*|begin\w*).{0,30}(?:wide|full.body|long.shot)", opening, re.IGNORECASE):
                raise ValueError("Le cadrage initial du visage parlant doit rester serré.")
    for line in lines:
        if re.search(r"<[^>]*>|\(S\d+\)", line):
            raise ValueError("Le dialogue doit être du texte parlé sans balise H3.")
    for text in fields:
        if not isinstance(text, str):
            raise ValueError("Les actions et directions caméra doivent être du texte.")
        if re.search(r"<[^>]*>|\(S\d+\)", text) or any(line and line in text for line in lines):
            raise ValueError("Les champs de mise en scène ne doivent pas contenir de dialogue.")
        if isinstance(plan, dict) and len(text.split()) > 70:
            raise ValueError("Simplifier chaque champ de mise en scène à 70 mots maximum.")


def build_scenario_prompt(
    news_items: list[Any],
    seg_count: int,
    director: str,
    palette: str,
    intensity: str = DEFAULT_INTENSITY,
) -> str:
    d = _director(director)
    p = _palette(palette)
    intensity_rule = _intensity(intensity)
    news_blocks = []
    for index, item in enumerate(news_items[:20], start=1):
        title = _news_field(item, "title")
        if not title:
            continue
        context = _news_field(item, "summary")[:1200] or "No additional context provided."
        news_blocks.append("\n".join([
            f"[NEWS {index}]",
            f"HEADLINE: {title}",
            f"SOURCE: {_news_field(item, 'source') or 'Unspecified'}",
            f"PUBLISHED: {_news_field(item, 'published') or 'Unspecified'}",
            f"CONTEXT: {context}",
        ]))
    return "\n".join([
        "Write a social-first satirical French TV news show. Return JSON only.",
        "LANGUAGE: titles and spoken dialogue in French. ALL visual fields and directing notes in English.",
        "CORE FORMAT — EVERY SEGMENT IS A COMPLETE COMEDIC SKETCH:",
        "Host: immediate factual hook, one natural French sentence, 8-16 words. Reporter: one original satirical punchline, 8-18 words, about the physical situation. Never repeat the host's facts or joke structures.",
        "ABSOLUTE FACT RULE:",
        "Copy the EXACT selected HEADLINE verbatim. Facts come ONLY from the supplied HEADLINE / SOURCE / PUBLISHED / CONTEXT. No invented names, numbers or events. Select distinct news events, not several articles about the same story.",
        "NEWS SOURCES:",
        "\n\n".join(news_blocks),
        "COMEDIC CONSTRUCTION FOR EVERY SEGMENT:",
        "Invent a specific satirical situation grounded in the news: expose its hypocrisy, incentives or institutional absurdity through a visible setup, readable escalation and strong final payoff. A decorative spectacle alone is not a joke. The reporter is the foreground protagonist caught in the gag. A small supporting cast only if useful; people contains secondary characters only, NEVER the reporter. Supporting characters stay silent. Perform with complete journalistic seriousness.",
        "You are the director. Invent camera moves, transitions, gags and endings freely according to the scene; no closed menu. Choose one or two purposeful camera moves, not a catalogue of instructions.",
        "H3 GUARDRAILS:",
        "Each clip lasts about 5-15 seconds. The edit alternates host and reporter shots. Every opening shows the principal speaker's face in a medium close-up, NEVER starts on a prop. Keep that face large and unobstructed while speaking. Wide views may show scenery, extras or silent action after speech.",
        "camera_plan.host and camera_plan.reporter are concise English directing notes. Describe coherent progression and payoff, always keeping the NAMED SPEAKER's face prominent during their line, not an inspector or other supporting actor. A silent serious face alone is not a final payoff. Subjective camera directions move the viewpoint itself; do not accidentally invent another filming device or second camera. Keep supporting crew silent.",
        "camera_plan.silent_tail_seconds: 0-3 seconds reserved AFTER the reporter's line for the chosen silent ending. Budget enough time for the ending without rushing speech.",
        "host_action / scene_action: concise physical comedy only, no camera instructions or dialogue. reporter_image_prompt: static initial pose and props BEFORE escalation, no montage, no framing instructions. Costumes must leave the face unobstructed: no tinted visor, mask or opaque glasses.",
        "Aim for 20-40 words per action/camera note, maximum 70. No speech tags, repeated dialogue, extra speakers, generated subtitles, logos, readable signs or music. Quiet diegetic sound only.",
        "VISUAL WORLD — MANDATORY FOR ALL CHARACTERS AND SETS:",
        "Funny retrofuturist costumes, surreal news-related props, hallucinatory sets. Rich color; never grey, monochrome or bland beige. Principal character descriptions focus on face and upper-body costume, not shoes or full-body accessories. Stage spectacle around the foreground face, not by moving the speaker far away.",
        "STANISLAVSKI: objective, obstacle, given_circumstances, physical_action for characters. Keep physical actions simple and coordinated.",
        f"CREATIVE INTENSITY — {INTENSITY_LEVELS[intensity].upper()}:",
        intensity_rule,
        f"DIRECTOR / VISUAL GRAMMAR — {d['label'].upper()}:",
        d["style"],
        f"Camera inspiration, not a required shot list: {d['camera']}",
        f"Lighting: {d['lighting']} Film: {d['film']}",
        f"COLOR PALETTE — {p['label'].upper()}: {p['full']}",
        "OUTPUT JSON:",
        '{"jt_title":"French title","host":{"name":"...","description":"English costume","plateau":"English set","host_action":"simple recurring physical action","stanislavski":{"objective":"...","obstacle":"...","given_circumstances":"...","physical_action":"..."}},"segments":[{"headline":"EXACT supplied headline","summary":"supported factual summary","host_dialogue":"8-16 French words","host_action":"English physical gag","people":[{"name":"...","description":"English costume","role":"...","stanislavski":{"objective":"...","obstacle":"...","given_circumstances":"...","physical_action":"English action"}}],"location":"English set","scene_action":"English physical sketch","reporter_image_prompt":"English static initial setup","camera_plan":{"host":"English studio direction","reporter":"English field direction and payoff","silent_tail_seconds":0},"reporter":{"name":"...","description":"English costume","dialogue":"8-18 natural French words"},"emotion":"..."}]}',
        f"Exactly {seg_count} segments. Before returning, verify English visual fields, grammatical French dialogue within word budgets, safe first-frame faces, achievable action and a sharp ending. Simplify visuals rather than rush speech.",
    ])


def apply_creative_postprocessing(
    value: dict[str, Any],
    seg_count: int,
    director: str,
    palette: str,
    intensity: str = DEFAULT_INTENSITY,
) -> dict[str, Any]:
    _director(director)
    _palette(palette)
    if intensity not in INTENSITY_LEVELS:
        raise ValueError(f"Intensité inconnue: {intensity}")
    jt = deepcopy(value)
    segments = jt.get("segments")
    if not isinstance(segments, list) or not segments:
        raise ValueError("Le scénario créatif doit contenir une liste 'segments' non vide.")

    host = jt.get("host")
    if not isinstance(host, dict):
        host = deepcopy(DEFAULT_HOST)
        jt["host"] = host
    else:
        for key in ("name", "description", "plateau", "stanislavski"):
            if not host.get(key):
                host[key] = deepcopy(DEFAULT_HOST[key])
        if not host.get("host_action"):
            host["host_action"] = DEFAULT_HOST_FALLBACK_ACTION

    if len(segments) != seg_count:
        raise ValueError(
            f"Le scénario doit contenir exactement {seg_count} sujets, reçu {len(segments)}. "
            "Aucun sujet n'est dupliqué ou tronqué silencieusement."
        )

    for index, segment in enumerate(segments):
        if not isinstance(segment, dict):
            raise ValueError(f"Segment créatif #{index + 1} invalide.")
        segment["segment_number"] = index + 1
        if not segment.get("emotion"):
            segment["emotion"] = DEFAULT_EMOTION
        reporter = segment.get("reporter")
        if not isinstance(reporter, dict):
            reporter = deepcopy(DEFAULT_REPORTER)
            segment["reporter"] = reporter
        for key, default in DEFAULT_REPORTER.items():
            if key not in reporter:
                reporter[key] = deepcopy(default)
        if not segment.get("host_action"):
            segment["host_action"] = host.get("host_action") or DEFAULT_HOST_FALLBACK_ACTION
        if not segment.get("scene_action"):
            segment["scene_action"] = DEFAULT_SCENE_ACTION
        if not segment.get("camera_plan"):
            segment["camera_plan"] = DEFAULT_CAMERA_PLAN
        if not segment.get("location"):
            segment["location"] = DEFAULT_LOCATION
        people = segment.get("people")
        if not isinstance(people, list):
            segment["people"] = deepcopy(DEFAULT_PEOPLE)
            people = segment["people"]

        host_dialogue = str(segment.get("host_dialogue", "")).strip()
        segment["host_dialogue"] = host_dialogue

        reporter_dialogue = str(reporter.get("dialogue", "")).strip()
        if not reporter_dialogue or reporter_dialogue == host_dialogue:
            reporter_dialogue = DEFAULT_REPORTER_DIALOGUE_FALLBACK
        reporter["dialogue"] = reporter_dialogue
        validate_staging(segment, host)

        description = str(reporter.get("description", "")).strip()
        if description and "retro" not in description.lower() and "futur" not in description.lower():
            reporter["description"] = f"{description}; {RETRO_COSTUME_SUFFIX}"
        elif not description:
            reporter["description"] = RETRO_COSTUME_SUFFIX

        location = str(segment.get("location", "")).strip()
        if "hallucin" not in location.lower():
            segment["location"] = f"{location}; {LOCATION_HALLUCINATION_SUFFIX}".strip("; ")

        for person in people:
            if not isinstance(person, dict):
                continue
            person_description = str(person.get("description", "")).strip()
            if not person_description:
                person["description"] = f"news-related {RETRO_COSTUME_SUFFIX}"
            elif "retro" not in person_description.lower() and "futur" not in person_description.lower():
                person["description"] = f"{person_description}; {RETRO_COSTUME_SUFFIX}"

    jt["title"] = str(jt.get("title") or jt.get("jt_title") or "Le JT NewsReel").strip()
    jt["creative"] = {
        "director": director,
        "palette": palette,
        "intensity": intensity,
    }
    return jt


def build_image_style_block(
    director: str, palette: str, intensity: str = DEFAULT_INTENSITY
) -> str:
    d = _director(director)
    p = _palette(palette)
    intensity_rule = _intensity(intensity)
    return "\n".join(
        [
            f"VISUAL STYLE: {d['style']}",
            f"LIGHTING: {d['lighting']}",
            f"IMAGE TEXTURE: {d['film']}",
            f"COLOR RULE — ONLY THIS PALETTE: {p['full']}",
            f"CREATIVE INTENSITY: {intensity_rule}",
            "MANDATORY COLOR SATURATION: strong chromatic presence across costumes, architecture, props, lighting and background. Never grey, never monochrome, never desaturated, never bland beige.",
            "MANDATORY CHARACTER DESIGN: funny retrofuturistic costume; accessories must leave the face unobstructed.",
            "MANDATORY SET DESIGN: colorful hallucinatory retrofuturist setting, visible only as a background around the foreground face.",
            "Photographic/cinematic image according to the selected visual style. No generic modern studio look.",
            "NO readable text, NO watermark, NO logos.",
        ]
    )


def build_host_image_prompt(
    host: dict[str, Any],
    director: str,
    palette: str,
    intensity: str = DEFAULT_INTENSITY,
) -> str:
    return "\n".join(
        [
            "KEYFRAME FOR A COMEDIC TV NEWS SKETCH.",
            "FIRST FRAME: medium close-up, head and shoulders filling the frame; crop below the shoulders. The unobstructed principal face occupies at least a quarter of the image height. This framing takes priority over set and props.",
            f"HOST: {host.get('name', '')} — {host.get('description', '')}",
            f"SET: {host.get('plateau', '')}",
            build_image_style_block(director, palette, intensity),
            "The host is composed and deadpan, ready to speak. Keep the set and props partly visible behind the shoulders. Do not pull back to show the desk or the whole costume. Leave space below the face for the editorial title.",
            "Portrait 9:16, rich saturated color, cinematic visual impact.",
        ]
    )


def build_reporter_image_prompt(
    segment: dict[str, Any],
    director: str,
    palette: str,
    intensity: str = DEFAULT_INTENSITY,
) -> str:
    reporter = segment.get("reporter") or {}
    people = segment.get("people") or []
    people_list = " | ".join(
        f"{person.get('name', '')} ({person.get('role', '')}): {person.get('description', '')}"
        for person in people
        if isinstance(person, dict)
    )
    return "\n".join(
        [
            "KEYFRAME FOR A SELF-CONTAINED COMEDIC FIELD-REPORT SKETCH.",
            "FIRST FRAME: medium close-up, head and shoulders filling the frame; crop below the shoulders. The unobstructed principal face occupies at least a quarter of the image height. This framing takes priority over the generated setup, location and cast.",
            f"REPORTER: {reporter.get('name', '')} — {reporter.get('description', '')}",
            f"SECONDARY CHARACTERS: {people_list}",
            f"LOCATION: {segment.get('location', '')}",
            f"SCENE ACTION (initial setup): {segment.get('reporter_image_prompt') or segment.get('scene_action', '')}",
            build_image_style_block(director, palette, intensity),
            "Depict the initial setup before the physical gag escalates, not a montage of its stages or its final payoff.",
            "This is a portrait of the named reporter, eyes directed toward the lens. Everything below the upper chest is outside the frame, even if described above. Keep props and secondary characters behind the shoulders, partly visible if necessary. Do not widen the shot to fit the cast, desk or whole costume. Leave space below the face for the editorial title.",
            "Portrait 9:16, extremely colorful, visually surprising, cinematic and immediately understandable.",
        ]
    )


def build_host_video_prompt(
    jt: dict[str, Any],
    segment: dict[str, Any],
    director: str,
    palette: str,
    duration_seconds: float,
    intensity: str = DEFAULT_INTENSITY,
) -> str:
    d = _director(director)
    p = _palette(palette)
    host = jt.get("host") or {}
    validate_staging(segment, host)
    motion = {"subtle": "restrained", "moderate": "expressive", "strong": "energetic"}[intensity]
    line = str(segment.get("host_dialogue", "")).strip()
    action = segment.get("host_action") or host.get("host_action") or ""
    return "\n".join(
        [
            "For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.",
            "",
            f"integrated_multimodal_description: [Shot 1] A satirical TV news shot lasting {duration_seconds:g} seconds. "
            f"{d['style']} Preserve the host, costume, set, lighting and {p['label']} colors from <Picture 1>. "
            "Begin in a medium close-up, the host's face clearly visible and large while speaking. "
            f"The physical action is {motion}, with coordinated, readable reactions. "
            f"The studio gag develops around the composed, deadpan host: {action}. "
            f"Direction: {camera_direction(segment, 'host')} "
            "No readable text, subtitles or logos. Only the host speaks. "
            f"The host {host.get('name', '')} with a natural French broadcast voice (S1) says: <d>[French] {line}</d>",
            "",
            "overall_soundscape: Quiet studio room ambience and synchronized mechanical sounds from the visible gag.",
            "",
            "non_diegetic_music: N/A",
        ]
    )


def build_reporter_video_prompt(
    segment: dict[str, Any],
    director: str,
    palette: str,
    duration_seconds: float,
    intensity: str = DEFAULT_INTENSITY,
) -> str:
    validate_staging(segment)
    tail = silent_tail_seconds(segment)
    ending = f"Reserve the final {tail:g} seconds for the silent ending after speech. " if tail else ""
    d = _director(director)
    p = _palette(palette)
    reporter = segment.get("reporter") or {}
    motion = {"subtle": "restrained", "moderate": "expressive", "strong": "energetic"}[intensity]
    line = str(reporter.get("dialogue", "")).strip()
    people = segment.get("people") or []
    people_desc = " || ".join(
        f"{person.get('name', '')} ({person.get('role', '')}): "
        f"{person['stanislavski'].get('physical_action', 'reacts to the gag') if isinstance(person.get('stanislavski'), dict) else 'reacts to the gag'}"
        for person in people
        if isinstance(person, dict)
    )
    return "\n".join(
        [
            "For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.",
            "",
            f"integrated_multimodal_description: [Shot 1] A satirical field-report shot lasting {duration_seconds:g} seconds. "
            f"{d['style']} Preserve the reporter, cast, costumes, location, lighting and {p['label']} colors from <Picture 1>. "
            "Begin in a medium close-up, the reporter's face clearly visible and large while speaking. "
            f"The physical action is {motion}, with coordinated, readable reactions. "
            f"The physical gag develops around the reporter: {segment.get('scene_action', '')}. "
            f"The secondary characters ({people_desc}) react to the visible action. "
            f"Direction: {camera_direction(segment, 'reporter')} "
            f"{ending}"
            "No readable text, subtitles or logos. Only the reporter speaks. "
            f"The reporter {reporter.get('name', '')} with a clear natural French voice (S1) says: <d>[French] {line}</d>",
            "",
            "overall_soundscape: Natural location ambience and synchronized movement and prop sounds from the visible action.",
            "",
            "non_diegetic_music: N/A",
        ]
    )
