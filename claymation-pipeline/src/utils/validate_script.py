"""
Mechanical validation of a Stage 1 script JSON against:
- the scaffold's hard rules (style prefix, word counts, scene count)
- the established @chatjerrpt content rules (em dashes, banned phrases, names)
Returns a list of violation strings. Empty list == passes.
"""

from src.prompts.script_prompt import STYLE_PREFIX

BANNED_PHRASES = [
    "let's dive in",
    "that's it",
    "in conclusion",
    "let me know in the comments",
]

REQUIRED_KEYS = {
    "topic",
    "hook",
    "narrative_arc",
    "cuts_made",
    "inferences_made",
    "visual_route",
    "footage_queries",
    "character_profile",
    "scenes",
    "full_narration",
    "estimated_duration_seconds",
    "caption_style",
    "voice_config",
}

VALID_ROUTES = {"interview", "claymation"}
VALID_VISUAL_SOURCES = {"footage", "claymation"}

VALID_CAMERAS = {"wide_shot", "medium_shot", "close_up", "over_shoulder"}
VALID_MOTION = {"subtle", "moderate", "high"}


def _word_count(text: str) -> int:
    return len([w for w in text.split() if w.strip()])


def validate_script(script: dict) -> list[str]:
    v: list[str] = []
    if not isinstance(script, dict):
        return ["Script is not a dict"]

    missing = REQUIRED_KEYS - script.keys()
    if missing:
        v.append(f"Missing required keys: {sorted(missing)}")

    hook = script.get("hook", "")
    if _word_count(hook) > 8:
        v.append(f"Hook is {_word_count(hook)} words, rule says max 8")

    scenes = script.get("scenes", []) or []
    if not (6 <= len(scenes) <= 10):
        v.append(f"Have {len(scenes)} scenes, rule requires 6-10")

    name_internal = (script.get("character_profile") or {}).get("name_internal", "") or ""

    for i, sc in enumerate(scenes, 1):
        if not isinstance(sc, dict):
            v.append(f"Scene {i} is not an object")
            continue
        if sc.get("scene_number") != i:
            v.append(f"Scene {i}: scene_number is {sc.get('scene_number')}, expected {i}")
        prompt = sc.get("broll_prompt", "") or ""
        if not prompt.startswith(STYLE_PREFIX):
            v.append(f"Scene {i}: broll_prompt missing required style prefix")
        after_prefix = prompt[len(STYLE_PREFIX):] if prompt.startswith(STYLE_PREFIX) else prompt
        if _word_count(after_prefix) > 60:
            v.append(f"Scene {i}: broll_prompt is {_word_count(after_prefix)} words after prefix, max 60")
        if name_internal and name_internal.lower() in prompt.lower() and len(name_internal) >= 3:
            v.append(f"Scene {i}: broll_prompt contains real name '{name_internal}'")
        if sc.get("camera") not in VALID_CAMERAS:
            v.append(f"Scene {i}: camera '{sc.get('camera')}' invalid")
        if sc.get("motion_level") not in VALID_MOTION:
            v.append(f"Scene {i}: motion_level '{sc.get('motion_level')}' invalid")

    narration = script.get("full_narration", "") or ""
    wc = _word_count(narration)
    if not (125 <= wc <= 160):
        v.append(f"full_narration is {wc} words, rule requires 125-160")

    duration = script.get("estimated_duration_seconds")
    if not isinstance(duration, int) or not (36 <= duration <= 60):
        v.append(f"estimated_duration_seconds is {duration}, expected int between 36 and 60")

    full_text_blob = " ".join(
        [
            hook,
            script.get("narrative_arc", "") or "",
            narration,
            *[sc.get("narration", "") or "" for sc in scenes],
        ]
    )
    if "—" in full_text_blob:
        v.append("Em dash found in narration/hook/arc, hard rule says never use them")
    lower_blob = full_text_blob.lower()
    for phrase in BANNED_PHRASES:
        if phrase in lower_blob:
            v.append(f'Banned phrase found in narration: "{phrase}"')

    route = script.get("visual_route")
    queries = script.get("footage_queries", []) or []
    footage_scenes = [
        sc.get("scene_number") for sc in scenes
        if isinstance(sc, dict) and sc.get("visual_source") == "footage"
    ]
    if route not in VALID_ROUTES:
        v.append(f"visual_route '{route}' invalid, must be interview or claymation")
    for i, sc in enumerate(scenes, 1):
        if isinstance(sc, dict):
            vs = sc.get("visual_source", "claymation")
            if vs not in VALID_VISUAL_SOURCES:
                v.append(f"Scene {i}: visual_source '{vs}' invalid")
    soundbite = script.get("soundbite_scene")
    if route == "interview":
        if not queries:
            v.append("interview route requires at least one footage_queries entry")
        if not (2 <= len(footage_scenes) <= 4):
            v.append(
                f"interview route requires 2-4 footage scenes, found {len(footage_scenes)}"
            )
        if soundbite not in footage_scenes:
            v.append(
                f"interview route requires soundbite_scene to be one of the footage scenes {footage_scenes}, got {soundbite}"
            )
    if route == "claymation":
        if queries:
            v.append("claymation route must have empty footage_queries")
        if footage_scenes:
            v.append(f"claymation route must have no footage scenes, found {footage_scenes}")
        if soundbite is not None:
            v.append("claymation route must have soundbite_scene: null")

    vc = script.get("voice_config") or {}
    if vc.get("voice_id") != "Daniel" or vc.get("provider") != "elevenlabs":
        v.append("voice_config must be ElevenLabs Daniel")

    if script.get("caption_style") != "submagic_cyan_highlight":
        v.append("caption_style must be submagic_cyan_highlight")

    return v
