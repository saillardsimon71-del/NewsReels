from __future__ import annotations

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
        "Clear comic escalation: one main gag plus secondary visual beats, expressive blocking "
        "and purposeful camera movement while preserving readability and character stability."
    ),
    "strong": (
        "Bold cinematic escalation: dense but readable retrofuturist spectacle, several coordinated "
        "visual beats, stronger reactions and ambitious camera language without chaotic identity drift."
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
DEFAULT_CAMERA_PLAN = "Opening wide shot, then cuts to close-ups, shot-reverse-shot between reporter and people, ending on a wide symmetrical frame."
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

    news_blocks: list[str] = []
    for index, item in enumerate(news_items[:20], start=1):
        title = _news_field(item, "title")
        if not title:
            continue
        source = _news_field(item, "source") or "Source non précisée"
        published = _news_field(item, "published") or "Date non précisée"
        context = _news_field(item, "summary") or "Aucun contexte supplémentaire fourni."
        if len(context) > 1200:
            context = context[:1197].rstrip() + "..."
        news_blocks.append(
            "\n".join(
                [
                    f"[NEWS {index}]",
                    f"HEADLINE: {title}",
                    f"SOURCE: {source}",
                    f"PUBLISHED: {published}",
                    f"CONTEXT: {context}",
                ]
            )
        )
    news_list = "\n\n".join(news_blocks)
    return "\n".join(
        [
            "You are the head writer of a short-form satirical TV news show based on TODAY'S NEWS.",
            "",
            "CORE FORMAT — EVERY SEGMENT IS A COMPLETE COMEDIC SKETCH:",
            "- The HOST on the TV studio explains the actual news clearly and briefly.",
            "- The FIELD REPORTER MUST NOT repeat, paraphrase, restate, summarize, or give the same information as the host.",
            "- The field reporter says ONE original funny sentence inspired by the news AND by the absurd physical situation happening around them.",
            "- The reporter sentence is a punchline, observation, ironic reaction, deadpan joke, or comic metaphor. It must make sense only because of the scene.",
            "- Host and reporter dialogue must be clearly different in content and purpose.",
            "- The visual action must create a comic situation that gives the reporter a reason to say the joke.",
            "- Each clip must feel like a self-contained sketch with setup → escalation → visual gag → punchline.",
            "",
            "NEWS SOURCES (Google News, today):",
            news_list,
            "",
            "ABSOLUTE FACT RULE:",
            "- headline: copy the EXACT selected HEADLINE verbatim.",
            "- Use ONLY the supplied HEADLINE / SOURCE / PUBLISHED / CONTEXT blocks for factual claims.",
            "- summary: only facts supported by the selected news block. Never invent numbers, names, dates or events.",
            "- host_dialogue: factual TV-news statement based on the summary, 8-16 French words.",
            "- reporter.dialogue: NOT factual repetition. Exactly one funny French sentence, 8-18 words, reacting to the physical gag.",
            "",
            "COMEDIC CONSTRUCTION FOR EVERY SEGMENT:",
            "- Give the reporter a concrete comic problem caused by the news-related situation.",
            "- Make 3-5 secondary characters actively worsen the situation in a visually readable way.",
            "- The gag must be physical, safe, surreal and immediately understandable without subtitles.",
            "- The reporter remains committed as if this were serious journalism.",
            "- The joke must be different for every segment.",
            '- Avoid generic jokes such as "cest le chaos", "je ne sais plus quoi dire", "on est en direct" or simple repetition of the headline.',
            "",
            f"CREATIVE INTENSITY — {INTENSITY_LEVELS[intensity].upper()}:",
            intensity_rule,
            "",
            "VISUAL WORLD — MANDATORY FOR ALL CHARACTERS AND SETS:",
            "- Every human character wears a clearly retrofuturistic, funny, extravagant costume appropriate to their role: oversized collars, strange helmets, chrome accessories, absurd pockets, geometric shoulder pieces, unusual glasses, inflatable details, retro sci-fi fabrics or ridiculous functional gadgets.",
            "- No ordinary modern clothing unless transformed into a comic retrofuturist version.",
            "- Every location is visually hallucinatory: impossible architecture, oversized props, surreal machines, strange signage without readable text, bizarre furniture, giant objects related to the news, unusual scale relationships.",
            "- Images must be richly colored and visually exuberant. NEVER default to grey, desaturated, monochrome, beige or bland realism.",
            "- The selected palette below is the ONLY color-direction source. Do not invent another palette.",
            "",
            "STANISLAVSKI:",
            "- Every character has objective, obstacle, given_circumstances and physical_action.",
            "- Performances are committed and serious even when the situation is ridiculous.",
            "",
            f"DIRECTOR / VISUAL GRAMMAR — {d['label'].upper()}:",
            d["style"],
            f"Camera: {d['camera']}",
            f"Lighting: {d['lighting']}",
            f"Film: {d['film']}",
            "",
            f"COLOR PALETTE — {p['label'].upper()}:",
            p["full"],
            "Use this exact chromatic family throughout the image. No grayscale fallback.",
            "",
            "SOUND:",
            "- No music or soundtrack.",
            "- Only diegetic foley and environmental sound plus birds in every shot.",
            "",
            "OUTPUT JSON — ONLY JSON, no markdown:",
            "{",
            '  "jt_title": "Le JT de NewsReel — [theme]",',
            '  "host": {"name":"...","description":"detailed retrofuturistic funny outfit","plateau":"hallucinatory retrofuturistic TV set","host_action":"recurring visual gag that supports each news item","stanislavski":{"objective":"...","obstacle":"...","given_circumstances":"...","physical_action":"..."}},',
            '  "segments": [',
            "    {",
            '      "segment_number": 1,',
            '      "headline": "EXACT selected headline",',
            '      "summary": "supported factual summary",',
            '      "host_dialogue": "8-16 French words stating the actual news",',
            '      "host_action": "specific visual studio gag tied to this news",',
            '      "people": [',
            '        {"name":"...","description":"retro-futuristic funny costume + physical traits","role":"news-related role","stanislavski":{"objective":"...","obstacle":"...","given_circumstances":"...","physical_action":"..."}},',
            '        {"name":"...","description":"...","role":"...","stanislavski":{"objective":"...","obstacle":"...","given_circumstances":"...","physical_action":"..."}},',
            '        {"name":"...","description":"...","role":"...","stanislavski":{"objective":"...","obstacle":"...","given_circumstances":"...","physical_action":"..."}}',
            "      ],",
            '      "location": "hallucinatory retrofuturistic location tied to the news",',
            '      "scene_action": "continuous visual sketch: setup, escalation, absurd gag, reporter predicament, punchline moment",',
            '      "camera_plan": "short-form sketch coverage: establishing shot, reaction close-up, physical gag, punchline close-up, final wide",',
            '      "reporter": {"name":"...","description":"retro-futuristic funny outfit","dialogue":"8-18 French words: ONE original joke about the scene, NOT the news facts"},',
            '      "emotion": "one word"',
            "    }",
            "  ]",
            "}",
            f"Exactly {seg_count} segments. Every segment is a distinct sketch. Do not repeat reporter joke structures.",
        ]
    )


def _count_words(value: str) -> int:
    return len(str(value or "").strip().split())


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
        if not isinstance(people, list) or not people:
            segment["people"] = deepcopy(DEFAULT_PEOPLE)
            people = segment["people"]

        host_dialogue = str(segment.get("host_dialogue", "")).strip()
        if _count_words(host_dialogue) > 18:
            host_dialogue = " ".join(host_dialogue.split()[:16])
        elif 0 < _count_words(host_dialogue) < 6:
            host_dialogue += " aujourd'hui."
        segment["host_dialogue"] = host_dialogue

        reporter_dialogue = str(reporter.get("dialogue", "")).strip()
        if _count_words(reporter_dialogue) > 22:
            reporter_dialogue = " ".join(reporter_dialogue.split()[:18])
        elif 0 < _count_words(reporter_dialogue) < 8:
            reporter_dialogue += " — voilà le problème."
        if not reporter_dialogue or reporter_dialogue == host_dialogue:
            reporter_dialogue = DEFAULT_REPORTER_DIALOGUE_FALLBACK
        reporter["dialogue"] = reporter_dialogue

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
            f"CAMERA LANGUAGE: {d['camera']}",
            f"LIGHTING: {d['lighting']}",
            f"IMAGE TEXTURE: {d['film']}",
            f"COLOR RULE — ONLY THIS PALETTE: {p['full']}",
            f"CREATIVE INTENSITY: {intensity_rule}",
            "MANDATORY COLOR SATURATION: strong chromatic presence across costumes, architecture, props, lighting and background. Never grey, never monochrome, never desaturated, never bland beige.",
            "MANDATORY CHARACTER DESIGN: every person wears a funny retrofuturistic costume with exaggerated silhouettes, chrome/plastic accessories, unusual glasses, helmets, geometric panels, absurd gadgets and period-future details.",
            "MANDATORY SET DESIGN: hallucinatory retrofuturist environment, impossible architecture, oversized props related to the news, strange machines, surreal scale, visually dense but readable.",
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
            f"HOST: {host.get('name', '')} — {host.get('description', '')}",
            f"SET: {host.get('plateau', '')}",
            build_image_style_block(director, palette, intensity),
            "The host is the factual anchor of the sketch, composed and deadpan, while a visually absurd retrofuturist mechanism related to the current news is already malfunctioning around the desk.",
            "Create a strong instantly readable vertical composition with exaggerated props and costume details.",
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
            f"REPORTER: {reporter.get('name', '')} — {reporter.get('description', '')}",
            f"SECONDARY CHARACTERS: {people_list}",
            f"LOCATION: {segment.get('location', '')}",
            f"SCENE ACTION: {segment.get('scene_action', '')}",
            build_image_style_block(director, palette, intensity),
            "Compose the exact visual setup of a sketch: the reporter is visibly trapped in or struggling with the news-related gag while every secondary character actively contributes to the escalating situation.",
            "All characters are visible enough to read their funny retrofuturistic costumes and roles.",
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
    intensity_rule = _intensity(intensity)
    host = jt.get("host") or {}
    stani = segment.get("stanislavski") or host.get("stanislavski") or {}
    line = str(segment.get("host_dialogue", "")).strip()
    action = segment.get("host_action") or host.get("host_action") or ""
    return "\n".join(
        [
            f"COMEDIC TV NEWS SKETCH — {duration_seconds:g} seconds.",
            "The host delivers the actual news fact while the studio performs a visual joke around them.",
            d["label"].upper() + ".",
            f"HOST: {host.get('name', '')} — {host.get('description', '')}",
            f"STANISLAVSKI: objective {stani.get('objective', 'deliver the news')}; obstacle {stani.get('obstacle', 'the absurd studio')}",
            f"RETROFUTURIST STUDIO: {host.get('plateau', '')}",
            f"VISUAL GAG: {action}",
            "The host must remain the factual narrator; do not turn the host dialogue into a joke that changes the news.",
            "COMEDIC STRUCTURE: immediate visual setup, escalating malfunction, host remains serious, final visual punchline.",
            f"CAMERA: {d['camera']}",
            f"STYLE: {d['style']}",
            f"LIGHTING: {d['lighting']}",
            f"FILM: {d['film']}",
            f"PALETTE: {p['full']}",
            f"CREATIVE INTENSITY: {intensity_rule}",
            "SATURATION: maximum rich color; absolutely no grey/desaturated fallback.",
            "SOUND: no music. Only diegetic foley, mechanical noises, reactions, and birds.",
            "The host has one consistent natural French broadcast voice (S1): same timbre, apparent age, accent, cadence and vocal energy in every studio segment.",
            f"<d>[French] {line}</d>",
            "No subtitles, no readable text, no watermark, no logo.",
        ]
    )


def build_reporter_video_prompt(
    segment: dict[str, Any],
    director: str,
    palette: str,
    duration_seconds: float,
    intensity: str = DEFAULT_INTENSITY,
) -> str:
    d = _director(director)
    p = _palette(palette)
    intensity_rule = _intensity(intensity)
    reporter = segment.get("reporter") or {}
    line = str(reporter.get("dialogue", "")).strip()
    people = segment.get("people") or []
    people_desc = " || ".join(
        f"{person.get('name', '')} ({person.get('role', '')}) — {person.get('description', '')}"
        for person in people
        if isinstance(person, dict)
    )
    camera_plan = segment.get("camera_plan") or "establishing shot, reaction close-up, physical gag, punchline close-up, final wide"
    return "\n".join(
        [
            f"COMPLETE COMEDIC FIELD-REPORT SKETCH — {duration_seconds:g} seconds.",
            d["label"].upper() + ".",
            f"REPORTER: {reporter.get('name', '')} — {reporter.get('description', '')}",
            f"RETROFUTURIST CAST: {people_desc}",
            f"LOCATION: {segment.get('location', '')}",
            f"FULL VISUAL GAG: {segment.get('scene_action', '')}",
            "All characters are active. The reporter has a concrete comic problem caused by the news-related situation.",
            "COMEDIC STRUCTURE: 1) establish the bizarre situation; 2) escalate physically; 3) reporter tries to maintain journalistic seriousness; 4) the gag peaks; 5) reporter delivers the punchline while the visual chaos continues.",
            f'CRITICAL DIALOGUE RULE: the reporter MUST NOT repeat the host, headline, summary, numbers, names, dates or factual explanation. The reporter says only this scene-dependent joke: "{line}"',
            f"CAMERA: {camera_plan}; {d['camera']}",
            f"STYLE: {d['style']}",
            f"LIGHTING: {d['lighting']}",
            f"FILM: {d['film']}",
            f"PALETTE: {p['full']}",
            f"CREATIVE INTENSITY: {intensity_rule}",
            "SATURATION: maximum rich color on every frame; never grey, monochrome, desaturated or bland.",
            "SOUND: no music. Only diegetic foley, physical comedy sounds, environmental ambience and birds.",
            "The reporter has a clear natural French voice (S1).",
            f"<d>[French] {line}</d>",
            "No subtitles, no readable text, no watermark, no logo.",
        ]
    )
