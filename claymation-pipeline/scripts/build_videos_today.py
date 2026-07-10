"""
Full end-to-end runner: Stages 1 -> 6 on every story in stories/.
Assumes Stage 1 JSON already exists in output/<name>/script.json
(produced by run_all_today.py). Generates voiceover, b-roll, and
assembled .mp4 for each story.

Use --stories foo,bar to restrict; default is all output/*/ dirs.
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from src.stages.generate_voiceover import generate_voiceover
from src.stages.generate_broll import generate_broll
from src.stages.source_footage import source_footage
from src.stages.assemble_video import assemble_video


def run_for_story(name: str) -> dict:
    print(f"\n{'='*60}\nBuilding video for: {name}\n{'='*60}")
    out_dir = ROOT / "output" / name
    script_path = out_dir / "script.json"
    if not script_path.exists():
        raise FileNotFoundError(
            f"{script_path} missing. Run scripts/run_all_today.py first."
        )
    script = json.loads(script_path.read_text())

    print("  Stage 3: voiceover...")
    vo = generate_voiceover(script["full_narration"], out_dir)
    print(f"    {vo['path']} ({vo['duration_seconds']:.1f}s, {vo['provider']})")

    # Visual routing: interview stories try real footage first, then
    # fall back to claymation if nothing from the last 10 days exists.
    route = script.get("visual_route", "claymation")
    footage_map = {}
    sourced_clips = []
    if route == "interview":
        print("  Stage 4a: sourcing real footage (interview route)...")
        sourced_clips = source_footage(
            script.get("footage_queries", []), out_dir / "footage"
        )
        if sourced_clips:
            footage_scene_nums = [
                sc["scene_number"] for sc in script["scenes"]
                if sc.get("visual_source") == "footage"
            ]
            for i, n in enumerate(footage_scene_nums):
                footage_map[n] = sourced_clips[i % len(sourced_clips)]["path"]
            print(f"    {len(sourced_clips)} clip(s) sourced, covering scenes {footage_scene_nums}")
        else:
            print("    no qualifying footage from the last 10 days, falling back to claymation")

    print("  Stage 4: b-roll...")
    broll = generate_broll(script["scenes"], out_dir / "broll", footage_map=footage_map)
    print(f"    provider: {broll['provider']}, scenes: {len(broll['scenes'])}")

    print("  Stages 5+6: caption + assemble...")
    final = assemble_video(script, Path(vo["path"]), broll, out_dir)
    print(f"    {final}")

    return {
        "name": name,
        "final": str(final),
        "voiceover": vo,
        "broll_provider": broll["provider"],
        "visual_route": route,
        "footage_used": bool(footage_map),
        "sourced_clips": [
            {k: c[k] for k in ("url", "title", "channel", "upload_date")}
            for c in sourced_clips
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stories", default="")
    args = parser.parse_args()

    if args.stories:
        names = [s.strip() for s in args.stories.split(",") if s.strip()]
    else:
        names = sorted(p.name for p in (ROOT / "output").iterdir() if p.is_dir())

    summary = []
    failed = []
    for name in names:
        try:
            summary.append(run_for_story(name))
        except Exception as e:
            print(f"  FAILED: {e}")
            failed.append((name, str(e)))

    print(f"\n{'='*60}\nSUMMARY\n{'='*60}")
    for s in summary:
        route_note = s.get("visual_route", "claymation")
        if route_note == "interview" and not s.get("footage_used"):
            route_note = "interview -> claymation fallback"
        print(f"  {s['name']}: {s['final']} | b-roll: {s['broll_provider']} | route: {route_note}")
        for c in s.get("sourced_clips", []):
            print(f"    clip: {c['title'][:60]} | {c['channel']} | {c['upload_date']} | {c['url']}")
    for name, err in failed:
        print(f"  {name}: FAILED ({err})")

    (ROOT / "output" / "build_summary.json").write_text(
        json.dumps({"built": summary, "failed": failed}, indent=2)
    )

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
