"""
Batch runner: generates Stage 1 scripts for all 3 of today's stories
sourced from the @chatjerrpt TikTok pipeline. Writes JSON per story,
prints a combined summary, exits non-zero if any story fails review.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Bootstrap BEFORE third-party imports: pulls code updates (re-exec) and
# installs any missing dependencies so scheduled runs are hands-off.
from src.utils.bootstrap import bootstrap
bootstrap(restart_argv=sys.argv)

from src.stages.generate_script import generate_script

STORIES = [
    "apple_gemini_swappable",
    "codex_analyst_replacement",
    "dual_ai_ipos",
]


def main():
    results = []
    for name in STORIES:
        print(f"\n{'='*60}\nStage 1: {name}\n{'='*60}")
        story = (ROOT / "stories" / f"{name}.txt").read_text().strip()
        direction_path = ROOT / "stories" / f"{name}.direction.txt"
        direction = direction_path.read_text().strip() if direction_path.exists() else ""
        try:
            script = generate_script(story, direction)
        except Exception as e:
            print(f"  FAILED: {e}")
            results.append((name, None, str(e)))
            continue
        out_dir = ROOT / "output" / name
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "script.json").write_text(json.dumps(script, indent=2))
        print(f"  hook: {script['hook']}")
        print(f"  scenes: {len(script['scenes'])}")
        print(f"  estimated_duration_seconds: {script['estimated_duration_seconds']}")
        print(f"  cuts_made: {script.get('cuts_made') or []}")
        print(f"  inferences_made: {script.get('inferences_made') or []}")
        print(f"  self_review_rounds: {script.get('_self_review_rounds')}")
        results.append((name, script, None))

    print(f"\n{'='*60}\nSUMMARY\n{'='*60}")
    any_failed = False
    for name, script, err in results:
        if err:
            any_failed = True
            print(f"  {name}: FAILED ({err})")
        else:
            print(f"  {name}: OK | hook='{script['hook']}' | {len(script['scenes'])} scenes | "
                  f"{script['estimated_duration_seconds']}s | review_rounds={script.get('_self_review_rounds')}")

    sys.exit(1 if any_failed else 0)


if __name__ == "__main__":
    main()
