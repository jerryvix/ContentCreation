"""
Validates Stages 5+6 (caption overlay + ffmpeg Ken Burns assembly) without
calling OpenArt, ElevenLabs, or Gemini. Generates placeholder claymation-tinted
PNG scenes and a silent-but-correct-length WAV voiceover, then runs the real
assembly path. Result: output/<name>/final.mp4 you can play and verify the
ffmpeg pipeline produces a valid TikTok-aspect captioned video.
"""

import json
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.stages.assemble_video import assemble_video

STORY = "apple_gemini_swappable"


def make_placeholder_image(text: str, out_path: Path) -> None:
    colors = ["#1a1a2e", "#16213e", "#0f3460", "#1f2041", "#2a1a3d"]
    bg = colors[hash(text) % len(colors)]
    img = Image.new("RGB", (1080, 1920), bg)
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 48)
    except Exception:
        font = ImageFont.load_default()
    label = "PLACEHOLDER\n(OpenArt blocked from sandbox)\n\n" + text[:80]
    draw.multiline_text((80, 800), label, fill="white", font=font, spacing=12)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)


def make_placeholder_audio(duration_s: float, out_path: Path) -> None:
    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi", "-i",
        f"sine=frequency=220:duration={duration_s}",
        "-c:a", "libmp3lame", "-b:a", "128k", str(out_path),
    ], check=True, capture_output=True)


def main():
    script_path = ROOT / "output" / STORY / "script.json"
    script = json.loads(script_path.read_text())
    out_dir = ROOT / "output" / STORY
    work = out_dir / "smoke_work"
    work.mkdir(parents=True, exist_ok=True)

    print(f"Smoke-testing assembly with story: {STORY}")
    print(f"  scenes: {len(script['scenes'])}")

    duration_s = float(script["estimated_duration_seconds"])
    vo_path = work / "voiceover.mp3"
    make_placeholder_audio(duration_s, vo_path)
    print(f"  generated placeholder audio: {duration_s:.1f}s")

    broll_scenes = []
    for sc in script["scenes"]:
        n = sc["scene_number"]
        img_path = work / f"scene_{n:02d}.png"
        make_placeholder_image(sc["narration"], img_path)
        broll_scenes.append({"scene_number": n, "media": str(img_path), "kind": "image"})
    print(f"  generated {len(broll_scenes)} placeholder PNG scenes")

    broll_result = {"provider": "placeholder", "scenes": broll_scenes}

    print("  assembling final.mp4...")
    final = assemble_video(script, vo_path, broll_result, work)
    size = final.stat().st_size

    probe = subprocess.run([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height,duration",
        "-of", "default=noprint_wrappers=1", str(final),
    ], capture_output=True, text=True, check=True).stdout

    print(f"\nSMOKE TEST PASSED")
    print(f"  output: {final}")
    print(f"  size: {size:,} bytes")
    print(f"  ffprobe:\n    " + probe.strip().replace("\n", "\n    "))


if __name__ == "__main__":
    main()
