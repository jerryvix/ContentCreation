"""
Re-runs only Stages 5+6 (caption overlay + ffmpeg assembly) against
existing voiceover.mp3 + broll/ assets in output/. Skips voiceover
and b-roll generation so no extra API spend.

Usage:
  python scripts/assemble_only.py              # all ready stories
  python scripts/assemble_only.py --stories apple_gemini_swappable
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.stages.assemble_video import assemble_video


def reconstruct_broll(broll_dir: Path, scenes: list[dict]) -> dict:
    """Build broll_result dict by inspecting existing files."""
    result_scenes = []
    providers_used = set()
    for sc in scenes:
        n = sc["scene_number"]
        png = broll_dir / f"scene_{n:02d}.png"
        mp4 = broll_dir / f"scene_{n:02d}.mp4"
        if png.exists():
            result_scenes.append({"scene_number": n, "media": str(png), "kind": "image"})
            providers_used.add("imagen")
        elif mp4.exists():
            result_scenes.append({"scene_number": n, "media": str(mp4), "kind": "video"})
            providers_used.add("veo")
        else:
            raise FileNotFoundError(f"No media file for scene {n} in {broll_dir}")
    provider = "mixed" if len(providers_used) > 1 else next(iter(providers_used))
    return {"provider": provider, "scenes": result_scenes}


def ready(d: Path) -> bool:
    return (
        d.is_dir()
        and (d / "script.json").exists()
        and (d / "voiceover.mp3").exists()
        and (d / "broll").is_dir()
        and any((d / "broll").iterdir())
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stories", default="", help="Comma-separated story names")
    args = parser.parse_args()

    out = ROOT / "output"
    if args.stories:
        names = [s.strip() for s in args.stories.split(",") if s.strip()]
        targets = [out / n for n in names]
    else:
        targets = [d for d in sorted(out.iterdir()) if ready(d)]

    if not targets:
        print("No stories ready for assembly. Need script.json + voiceover.mp3 + broll/ in each output/<name>/.")
        sys.exit(1)

    built, failed = [], []
    for d in targets:
        name = d.name
        print(f"\n=== Assembling {name} ===")
        if not ready(d):
            print(f"  SKIPPED: missing assets in {d}")
            failed.append((name, "missing assets"))
            continue
        try:
            work = d / "_work"
            if work.exists():
                shutil.rmtree(work)
            script = json.loads((d / "script.json").read_text())
            broll = reconstruct_broll(d / "broll", script["scenes"])
            final = assemble_video(script, d / "voiceover.mp3", broll, d)
            size = final.stat().st_size
            print(f"  OK: {final} ({size:,} bytes)")
            built.append((name, str(final)))
        except Exception as e:
            print(f"  FAILED: {e}")
            failed.append((name, str(e)))

    print(f"\n{'='*60}\nSUMMARY\n{'='*60}")
    for name, path in built:
        print(f"  {name}: {path}")
    for name, err in failed:
        print(f"  {name}: FAILED ({err})")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
