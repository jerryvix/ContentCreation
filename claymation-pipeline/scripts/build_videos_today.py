"""
Full Stages 3 -> 6 runner for every story in output/ (or --stories subset).
Assumes Stage 1 JSON exists (run_all_today.py). Self-bootstraps: pulls
its own code updates and installs missing dependencies before running,
so scheduled runs never need manual setup steps.

Visual routing per story:
  interview + soundbite extracted -> voiceover A / real quote audio / voiceover B
  interview + footage only       -> muted footage under continuous voiceover
  interview + nothing sourced    -> claymation
  claymation                     -> claymation

Captions default OFF (add in TikTok's editor); pass --captions to burn in.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Bootstrap BEFORE third-party imports: it may pull new code (re-exec)
# or install the very packages imported below.
from src.utils.bootstrap import bootstrap
bootstrap(restart_argv=sys.argv)

import argparse
import json
import shutil

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from src.stages.generate_voiceover import generate_voiceover
from src.stages.generate_broll import generate_broll
from src.stages.source_footage import source_footage
from src.stages.extract_soundbite import extract_soundbite
from src.stages.assemble_video import assemble_video, assemble_with_soundbite


def run_for_story(name: str, captions: bool) -> dict:
    print(f"\n{'='*60}\nBuilding video for: {name}\n{'='*60}")
    out_dir = ROOT / "output" / name
    script_path = out_dir / "script.json"
    if not script_path.exists():
        raise FileNotFoundError(
            f"{script_path} missing. Run scripts/run_all_today.py first."
        )
    script = json.loads(script_path.read_text())

    # ----- Visual routing -----
    route = script.get("visual_route", "claymation")
    footage_map = {}
    sourced_clips = []
    soundbite = None
    if route == "interview":
        print("  Stage 4a: sourcing real footage (interview route)...")
        sourced_clips = source_footage(
            script.get("footage_queries", []), out_dir / "footage", keep_raw=True
        )
        if sourced_clips:
            footage_scene_nums = [
                sc["scene_number"] for sc in script["scenes"]
                if sc.get("visual_source") == "footage"
            ]
            for i, n in enumerate(footage_scene_nums):
                footage_map[n] = sourced_clips[i % len(sourced_clips)]["path"]
            print(f"    {len(sourced_clips)} clip(s) sourced, covering scenes {footage_scene_nums}")

            bite_scene = script.get("soundbite_scene")
            raw = sourced_clips[0].get("raw_path")
            if bite_scene in footage_scene_nums and raw and Path(raw).exists():
                print("  Stage 4b: extracting real soundbite...")
                context = (
                    f"Topic: {script.get('topic','')}\n"
                    f"Hook: {script.get('hook','')}\n"
                    f"Angle: {script.get('narrative_arc','')}"
                )
                soundbite = extract_soundbite(Path(raw), context, out_dir / "footage")
            # raw downloads served their purpose; free the disk
            for c in sourced_clips:
                rp = c.pop("raw_path", None)
                if rp:
                    Path(rp).unlink(missing_ok=True)
        else:
            print("    no qualifying footage from the last 10 days, falling back to claymation")

    # ----- Voiceover (split around the soundbite when there is one) -----
    if soundbite:
        k = script["soundbite_scene"]
        narr_a = " ".join(
            sc["narration"] for sc in script["scenes"] if sc["scene_number"] <= k
        )
        narr_b = " ".join(
            sc["narration"] for sc in script["scenes"] if sc["scene_number"] > k
        )
        print("  Stage 3: voiceover (split for soundbite)...")
        vo_a = generate_voiceover(narr_a, out_dir, out_name="voiceover_a.mp3")
        print(f"    A: {vo_a['duration_seconds']:.1f}s ({vo_a['provider']})")
        vo_b = generate_voiceover(narr_b, out_dir, out_name="voiceover_b.mp3") if narr_b.strip() else None
        if vo_b:
            print(f"    B: {vo_b['duration_seconds']:.1f}s ({vo_b['provider']})")
        vo = vo_a
    else:
        print("  Stage 3: voiceover...")
        vo = generate_voiceover(script["full_narration"], out_dir)
        print(f"    {vo['path']} ({vo['duration_seconds']:.1f}s, {vo['provider']})")

    print("  Stage 4: b-roll...")
    broll = generate_broll(script["scenes"], out_dir / "broll", footage_map=footage_map)
    print(f"    provider: {broll['provider']}, scenes: {len(broll['scenes'])}")

    # ----- Assembly -----
    if soundbite:
        print("  Stages 5+6: assembling with spliced soundbite...")
        if captions:
            print("    (captions unsupported on the soundbite timeline, skipping)")
        final = assemble_with_soundbite(
            script, Path(vo["path"]),
            Path(vo_b["path"]) if vo_b else None,
            broll, Path(soundbite["path"]), script["soundbite_scene"], out_dir,
        )
    else:
        print("  Stages 5+6: assembling...")
        final = assemble_video(script, Path(vo["path"]), broll, out_dir, captions=captions)
    print(f"    {final}")

    return {
        "name": name,
        "final": str(final),
        "voiceover": vo,
        "broll_provider": broll["provider"],
        "visual_route": route,
        "footage_used": bool(footage_map),
        "soundbite": {k: soundbite[k] for k in ("quote", "start", "end")} if soundbite else None,
        "sourced_clips": [
            {k: c[k] for k in ("url", "title", "channel", "upload_date")}
            for c in sourced_clips
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stories", default="")
    parser.add_argument("--captions", action="store_true",
                        help="Burn in captions (default off, add in TikTok's editor)")
    args = parser.parse_args()

    if args.stories:
        names = [s.strip() for s in args.stories.split(",") if s.strip()]
    else:
        names = sorted(p.name for p in (ROOT / "output").iterdir() if p.is_dir())

    summary = []
    failed = []
    for name in names:
        try:
            summary.append(run_for_story(name, captions=args.captions))
        except Exception as e:
            print(f"  FAILED: {e}")
            failed.append((name, str(e)))

    print(f"\n{'='*60}\nSUMMARY\n{'='*60}")
    for s in summary:
        route_note = s.get("visual_route", "claymation")
        if route_note == "interview" and not s.get("footage_used"):
            route_note = "interview -> claymation fallback"
        elif route_note == "interview" and s.get("soundbite"):
            route_note = "interview + spliced soundbite"
        print(f"  {s['name']}: {s['final']} | b-roll: {s['broll_provider']} | route: {route_note}")
        if s.get("soundbite"):
            print(f"    quote: \"{s['soundbite']['quote'][:80]}\"")
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
