"""
Stage 4b: extract a real soundbite (with original audio) from a sourced
interview clip, so the final video cuts to the figure actually saying it
instead of muted footage under narration.

1. ffmpeg pulls a mono 16 kHz audio track from the raw clip (first 20 min)
2. OpenAI Whisper transcribes it with segment timestamps
3. Claude reads the transcript segments + story context and picks the
   sharpest on-topic quote window (6-25 s)
4. ffmpeg cuts that window from the raw clip, video AND audio

Any failure at any step returns None and the caller falls back to muted
footage under continuous voiceover (which itself falls back to
claymation). No user escalation unless everything above is exhausted.
"""

import json
import os
import re
import subprocess
from pathlib import Path

MAX_TRANSCRIBE_S = 1200      # transcribe at most the first 20 minutes
MIN_BITE_S, MAX_BITE_S = 4, 25
MAX_SEGMENTS_TO_CLAUDE = 250
CLAUDE_MODEL = "claude-sonnet-4-6"


def _extract_audio(raw_clip: Path, out_dir: Path) -> Path | None:
    audio = out_dir / "transcribe_input.mp3"
    r = subprocess.run(
        ["ffmpeg", "-y", "-i", str(raw_clip), "-t", str(MAX_TRANSCRIBE_S),
         "-vn", "-ac", "1", "-ar", "16000", "-b:a", "48k", str(audio)],
        capture_output=True, timeout=600,
    )
    if r.returncode != 0 or not audio.exists():
        print("      [Soundbite] audio extraction failed")
        return None
    return audio


def _transcribe(audio: Path) -> list[dict] | None:
    try:
        from openai import OpenAI
        client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        with open(audio, "rb") as f:
            result = client.audio.transcriptions.create(
                model="whisper-1", file=f, response_format="verbose_json",
            )
        segments = [
            {"start": round(s.start, 1), "end": round(s.end, 1), "text": s.text.strip()}
            for s in (result.segments or [])
        ]
        if not segments:
            print("      [Soundbite] transcript came back empty")
            return None
        return segments[:MAX_SEGMENTS_TO_CLAUDE]
    except Exception as e:
        print(f"      [Soundbite] transcription failed: {e}")
        return None


def _pick_window(segments: list[dict], story_context: str) -> dict | None:
    try:
        from anthropic import Anthropic
        client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        system = (
            "You pick the single best soundbite from an interview transcript for a "
            "short-form business news video. Pick the sharpest, most quotable on-topic "
            "moment: a complete thought, ideally surprising or definitive, spoken by the "
            "key figure. Return ONLY JSON: "
            '{"start": <seconds>, "end": <seconds>, "quote": "<the text>"} '
            f"with end-start between {MIN_BITE_S} and {MAX_BITE_S} seconds, aligned to "
            "segment boundaries. start and end must bound ONLY the segments whose text "
            "you put in quote: never include interviewer questions or reactions before "
            "or after it. If NOTHING in the transcript is on-topic for the story, "
            'return {"start": null, "end": null, "quote": "NONE"}.'
        )
        user = (
            f"STORY CONTEXT:\n{story_context}\n\n"
            f"TRANSCRIPT SEGMENTS (start, end, text):\n{json.dumps(segments)}"
        )
        messages = [{"role": "user", "content": user}]
        for attempt in (1, 2):
            res = client.messages.create(
                model=CLAUDE_MODEL, max_tokens=500, system=system, messages=messages,
            )
            raw = res.content[0].text.strip()
            cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)
            win = json.loads(cleaned)
            if win.get("start") is None or win.get("quote") == "NONE":
                print("      [Soundbite] Claude found no on-topic quote in this clip")
                return None
            start, end = float(win["start"]), float(win["end"])
            if MIN_BITE_S <= end - start <= MAX_BITE_S and start >= 0:
                return {"start": start, "end": end, "quote": win.get("quote", "")}
            print(f"      [Soundbite] picked window {start}-{end}s out of bounds"
                  + (", retrying with feedback" if attempt == 1 else ""))
            messages += [
                {"role": "assistant", "content": raw},
                {"role": "user", "content":
                    f"That window is {end - start:.1f}s, outside the {MIN_BITE_S}-{MAX_BITE_S}s "
                    "limit. Pick ONE contiguous run of the figure's own segments, dropping "
                    "everything else, and return the JSON again."},
            ]
        return None
    except Exception as e:
        print(f"      [Soundbite] quote selection failed: {e}")
        return None


def _cut(raw_clip: Path, start: float, end: float, out_dir: Path) -> Path | None:
    bite = out_dir / "soundbite.mp4"
    r = subprocess.run(
        ["ffmpeg", "-y", "-ss", f"{start:.2f}", "-i", str(raw_clip),
         "-t", f"{end - start:.2f}",
         "-c:v", "libx264", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-ar", "44100", "-ac", "2", str(bite)],
        capture_output=True, timeout=600,
    )
    if r.returncode != 0 or not bite.exists():
        print("      [Soundbite] cut failed")
        return None
    return bite


def extract_soundbite(raw_clip: Path, story_context: str, out_dir: Path) -> dict | None:
    """
    Returns {"path": <mp4 with audio>, "quote": <text>, "start": s, "end": s}
    or None (caller falls back to muted footage).
    """
    if not os.environ.get("OPENAI_API_KEY"):
        print("      [Soundbite] OPENAI_API_KEY missing, skipping soundbite extraction")
        return None
    out_dir.mkdir(parents=True, exist_ok=True)
    print("      [Soundbite] transcribing clip...")
    audio = _extract_audio(raw_clip, out_dir)
    if not audio:
        return None
    segments = _transcribe(audio)
    audio.unlink(missing_ok=True)
    if not segments:
        return None
    print(f"      [Soundbite] {len(segments)} transcript segments, picking quote...")
    win = _pick_window(segments, story_context)
    if not win:
        return None
    bite = _cut(raw_clip, win["start"], win["end"], out_dir)
    if not bite:
        return None
    print(f'      [Soundbite] cut {win["end"] - win["start"]:.1f}s: "{win["quote"][:80]}"')
    return {"path": str(bite), **win}
