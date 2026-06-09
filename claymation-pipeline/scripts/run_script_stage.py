"""
CLI: python scripts/run_script_stage.py <story_name>

Reads stories/<name>.txt (+ optional stories/<name>.direction.txt),
calls generate_script, saves output/<name>/script.json, prints a summary.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.stages.generate_script import generate_script


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/run_script_stage.py <story_name>")
        sys.exit(1)

    name = sys.argv[1]
    story_path = ROOT / "stories" / f"{name}.txt"
    direction_path = ROOT / "stories" / f"{name}.direction.txt"

    if not story_path.exists():
        print(f"Story file not found: {story_path}")
        sys.exit(1)

    user_story = story_path.read_text().strip()
    user_direction = direction_path.read_text().strip() if direction_path.exists() else ""

    print(f"Running Stage 1 for: {name}")
    script = generate_script(user_story, user_direction)

    out_dir = ROOT / "output" / name
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "script.json"
    out_path.write_text(json.dumps(script, indent=2))

    print(f"\nSaved {out_path}")
    print(f"  hook: {script['hook']}")
    print(f"  scenes: {len(script['scenes'])}")
    print(f"  estimated_duration_seconds: {script['estimated_duration_seconds']}")
    if script.get("cuts_made"):
        print(f"  cuts_made: {script['cuts_made']}")
    if script.get("inferences_made"):
        print(f"  inferences_made: {script['inferences_made']}")
    print(f"  self_review_rounds: {script.get('_self_review_rounds', '?')}")


if __name__ == "__main__":
    main()
