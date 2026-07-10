"""
Stages 5 + 6: caption overlay and final video assembly.

Inputs:
- script JSON with scene list and per-scene narration
- voiceover.mp3 from Stage 3
- per-scene media from Stage 4 (PNG image or pre-rendered MP4)

Output:
- final.mp4 in 1080x1920 (TikTok vertical) with Ken Burns zoom on image
  scenes, scene-segment captions burned in (submagic cyan highlight),
  voiceover audio mixed in, total duration matched to the voiceover.

Captions: rather than calling Whisper (which would re-transcribe what we
already wrote), we use scene narration text segmented across the audio
duration proportionally. Submagic-style: cyan highlight on currently
spoken word group, bold sans on dark.
"""

import json
import shlex
import subprocess
import sys
from pathlib import Path

W, H = 1080, 1920
FPS = 30
PER_SCENE_S = 6


def _run(cmd: list[str]) -> None:
    print(f"      $ {' '.join(shlex.quote(c) for c in cmd)}")
    subprocess.run(cmd, check=True, capture_output=True)


def _audio_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return float(out)


def _ken_burns_clip(image_path: Path, out_path: Path, duration: float) -> None:
    """Render a Ken Burns zoom-in MP4 clip from a still image."""
    frames = int(duration * FPS)
    zoom_per_frame = 0.0008
    # zoompan: zoom from 1.0 to ~1 + (0.0008 * frames). scale to 1080x1920.
    vf = (
        f"scale=2160:3840:force_original_aspect_ratio=increase,"
        f"crop=2160:3840,"
        f"zoompan=z='min(zoom+{zoom_per_frame},1.25)':d={frames}:s={W}x{H}:fps={FPS}"
    )
    _run([
        "ffmpeg", "-y", "-loop", "1", "-i", str(image_path),
        "-vf", vf, "-c:v", "libx264", "-t", f"{duration:.3f}",
        "-pix_fmt", "yuv420p", "-r", str(FPS), str(out_path),
    ])


def _normalize_video_clip(in_path: Path, out_path: Path, duration: float) -> None:
    vf = (
        f"scale={W}:{H}:force_original_aspect_ratio=increase,"
        f"crop={W}:{H},fps={FPS}"
    )
    _run([
        "ffmpeg", "-y", "-i", str(in_path), "-vf", vf,
        "-t", f"{duration:.3f}", "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-an", str(out_path),
    ])


def _build_concat_list(clip_paths: list[Path], list_path: Path) -> None:
    list_path.write_text("\n".join(f"file '{p.as_posix()}'" for p in clip_paths))


def _font_path_for_filter() -> str:
    """
    Return a fontfile value pre-escaped for ffmpeg's drawtext filter parser.
    Drawtext uses ':' as an option separator, so on Windows we escape the
    colon in 'C:/...' as 'C\\:/...' to keep ffmpeg happy.
    """
    if sys.platform.startswith("win"):
        candidates = [
            r"C\:/Windows/Fonts/arialbd.ttf",
            r"C\:/Windows/Fonts/segoeuib.ttf",
            r"C\:/Windows/Fonts/arial.ttf",
        ]
        for c in candidates:
            real = c.replace(r"\:", ":")
            if Path(real).exists():
                return c
    if sys.platform == "darwin":
        for c in ["/System/Library/Fonts/Helvetica.ttc",
                  "/Library/Fonts/Arial Bold.ttf"]:
            if Path(c).exists():
                return c
    for c in ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"]:
        if Path(c).exists():
            return c
    raise RuntimeError("No usable bold font found for drawtext on this OS.")


def _drawtext_filter_for_scenes(scenes: list[dict], scene_duration: float) -> str:
    """
    Build a chained drawtext filter that shows each scene's narration as
    a centered submagic-style caption, cyan highlight, only during that
    scene window.
    """
    font = _font_path_for_filter()
    parts = []
    for i, sc in enumerate(scenes):
        text = sc["narration"].replace("'", "’").replace(":", " -").replace("\n", " ")
        text = text.replace("\\", "\\\\")
        start = i * scene_duration
        end = (i + 1) * scene_duration
        parts.append(
            f"drawtext=fontfile={font}:"
            f"text='{text}':"
            "fontcolor=white:fontsize=58:"
            "borderw=4:bordercolor=black:"
            "box=1:boxcolor=0x00E5FF@0.85:boxborderw=18:"
            "x=(w-text_w)/2:y=h*0.78:"
            f"enable='between(t,{start:.2f},{end:.2f})'"
        )
    return ",".join(parts)


def assemble_video(
    script: dict,
    voiceover_path: Path,
    broll_result: dict,
    out_dir: Path,
    captions: bool = True,
) -> Path:
    """
    Assemble final.mp4. Returns the path.
    captions=False skips the drawtext overlay entirely (clean video,
    add captions in TikTok's native editor instead).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    work = out_dir / "_work"
    work.mkdir(exist_ok=True)

    audio_duration = _audio_duration(voiceover_path)
    n_scenes = len(script["scenes"])
    per_scene = audio_duration / n_scenes

    broll_by_scene = {s["scene_number"]: s for s in broll_result["scenes"]}
    normalized_clips: list[Path] = []
    for sc in script["scenes"]:
        n = sc["scene_number"]
        media = broll_by_scene[n]
        clip_out = work / f"scene_{n:02d}.mp4"
        media_path = Path(media["media"])
        if media["kind"] == "image":
            _ken_burns_clip(media_path, clip_out, per_scene)
        else:
            _normalize_video_clip(media_path, clip_out, per_scene)
        normalized_clips.append(clip_out)

    concat_list = work / "concat.txt"
    _build_concat_list(normalized_clips, concat_list)

    silent_video = work / "silent.mp4"
    _run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list),
        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(silent_video),
    ])

    if captions:
        video_track = work / "captioned.mp4"
        drawtext = _drawtext_filter_for_scenes(script["scenes"], per_scene)
        _run([
            "ffmpeg", "-y", "-i", str(silent_video),
            "-vf", drawtext, "-c:v", "libx264", "-pix_fmt", "yuv420p", str(video_track),
        ])
    else:
        video_track = silent_video

    final = out_dir / "final.mp4"
    _run([
        "ffmpeg", "-y", "-i", str(video_track), "-i", str(voiceover_path),
        "-c:v", "copy", "-c:a", "aac", "-shortest", str(final),
    ])

    return final


# ---------------------------------------------------------------------
# Soundbite timeline: [scenes 1..k + voiceover A] -> [real quote clip
# with its own audio] -> [scenes k+1..n + voiceover B]
# ---------------------------------------------------------------------

def _build_scene_track(scenes: list[dict], broll_by_scene: dict,
                       voiceover_path: Path, work: Path, tag: str) -> Path:
    """Render a video+voiceover segment for a subset of scenes, encoded
    with uniform params so segments concat cleanly."""
    audio_duration = _audio_duration(voiceover_path)
    per_scene = audio_duration / len(scenes)
    clips = []
    for sc in scenes:
        n = sc["scene_number"]
        media = broll_by_scene[n]
        clip_out = work / f"{tag}_scene_{n:02d}.mp4"
        if media["kind"] == "image":
            _ken_burns_clip(Path(media["media"]), clip_out, per_scene)
        else:
            _normalize_video_clip(Path(media["media"]), clip_out, per_scene)
        clips.append(clip_out)
    concat_list = work / f"{tag}_concat.txt"
    _build_concat_list(clips, concat_list)
    silent = work / f"{tag}_silent.mp4"
    _run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list),
          "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(FPS), str(silent)])
    seg = work / f"{tag}_segment.mp4"
    _run(["ffmpeg", "-y", "-i", str(silent), "-i", str(voiceover_path),
          "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(FPS),
          "-c:a", "aac", "-ar", "44100", "-ac", "2", "-shortest", str(seg)])
    return seg


def _normalize_soundbite(soundbite_path: Path, work: Path) -> Path:
    """Re-frame the quote clip to 1080x1920 keeping its ORIGINAL audio."""
    seg = work / "bite_segment.mp4"
    vf = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS}"
    _run(["ffmpeg", "-y", "-i", str(soundbite_path), "-vf", vf,
          "-c:v", "libx264", "-pix_fmt", "yuv420p",
          "-c:a", "aac", "-ar", "44100", "-ac", "2", str(seg)])
    return seg


def assemble_with_soundbite(
    script: dict,
    vo_a_path: Path,
    vo_b_path: Path | None,
    broll_result: dict,
    soundbite_path: Path,
    after_scene: int,
    out_dir: Path,
) -> Path:
    """
    Assemble final.mp4 with a real spoken soundbite spliced in after
    `after_scene`: narration A plays over scenes 1..k, the quote plays
    with its own audio, narration B plays over scenes k+1..n. Burned-in
    captions are not supported on this path (timing would drift); use
    TikTok's editor.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    work = out_dir / "_work"
    work.mkdir(exist_ok=True)

    broll_by_scene = {s["scene_number"]: s for s in broll_result["scenes"]}
    scenes_a = [sc for sc in script["scenes"] if sc["scene_number"] <= after_scene]
    scenes_b = [sc for sc in script["scenes"] if sc["scene_number"] > after_scene]

    segments = [
        _build_scene_track(scenes_a, broll_by_scene, vo_a_path, work, "a"),
        _normalize_soundbite(soundbite_path, work),
    ]
    if scenes_b and vo_b_path is not None:
        segments.append(_build_scene_track(scenes_b, broll_by_scene, vo_b_path, work, "b"))

    final_concat = work / "final_concat.txt"
    _build_concat_list(segments, final_concat)
    final = out_dir / "final.mp4"
    # re-encode on the final concat: safest across segment boundaries
    _run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(final_concat),
          "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(FPS),
          "-c:a", "aac", "-ar", "44100", "-ac", "2", str(final)])
    return final
