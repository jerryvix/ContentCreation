"""
Stage 1: script generation + self-review.
Uses claude-sonnet-4-6 (overrides the scaffold's claude-opus-4-7 per
the latest user instruction). Self-review runs up to 3 rounds against
the mechanical rules in src/utils/validate_script.py. Does not advance
to Stages 2-6.
"""

import json
import os
import re
from anthropic import Anthropic
from dotenv import load_dotenv

from src.prompts.script_prompt import SCRIPT_PROMPT
from src.utils.validate_script import validate_script

load_dotenv()

CLAUDE_MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 4000


def _strip_code_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _call_claude(client: Anthropic, prompt: str) -> str:
    res = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )
    return res.content[0].text


def _parse_json(raw: str) -> dict:
    return json.loads(_strip_code_fences(raw))


def generate_script(user_story: str, user_direction: str = "") -> dict:
    """
    Returns a Stage 1 script JSON. Self-reviews up to 3 rounds against
    the content rules. Raises RuntimeError if it still fails after 3.
    """
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    prompt = SCRIPT_PROMPT.format(user_story=user_story, user_direction=user_direction or "(none)")

    raw = _call_claude(client, prompt)
    try:
        script = _parse_json(raw)
    except json.JSONDecodeError:
        retry = prompt + "\n\nOutput ONLY valid JSON, no markdown fences, no preamble."
        script = _parse_json(_call_claude(client, retry))

    for round_num in range(1, 4):
        violations = validate_script(script)
        if not violations:
            print(f"    [Stage 1 self-review] passed on round {round_num}")
            script["_self_review_rounds"] = round_num
            return script

        print(f"    [Stage 1 self-review] round {round_num} violations:")
        for v in violations:
            print(f"      - {v}")

        if round_num == 3:
            break

        fix_prompt = (
            "Here is a Stage 1 claymation script JSON you produced. "
            "It violates these mechanical rules:\n- "
            + "\n- ".join(violations)
            + "\n\nReturn the COMPLETE corrected JSON, same schema, fixing every violation. "
            "Do not change the underlying story or angle. Output ONLY valid JSON, no markdown, no preamble.\n\n"
            "Current JSON:\n"
            + json.dumps(script, indent=2)
        )
        try:
            script = _parse_json(_call_claude(client, fix_prompt))
        except json.JSONDecodeError:
            retry = fix_prompt + "\n\nReminder: output ONLY valid JSON, no markdown fences."
            script = _parse_json(_call_claude(client, retry))

    final_violations = validate_script(script)
    if final_violations:
        raise RuntimeError(
            "Stage 1 still failing after 3 review rounds: " + "; ".join(final_violations)
        )
    script["_self_review_rounds"] = 3
    return script
