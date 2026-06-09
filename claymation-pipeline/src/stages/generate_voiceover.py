"""
Stage 3: voiceover audio from full_narration via ElevenLabs (Daniel).
Writes output/<name>/voiceover.mp3 and returns its path + duration (seconds).
ElevenLabs SDK is the supported transport.
"""

import os
import subprocess
from pathlib import Path
from elevenlabs.client import ElevenLabs

DEFAULT_VOICE_ID = "onwK4e9ZLuTAKqWW03F9"  # Daniel (ElevenLabs preset)
DEFAULT_MODEL = "eleven_turbo_v2_5"


def _audio_duration_seconds(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return float(out)


def generate_voiceover(narration: str, out_dir: Path) -> dict:
    """
    Generate Daniel voiceover from full_narration. Returns:
      {"path": <mp3 path>, "duration_seconds": <float>, "provider": "elevenlabs"}
    """
    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        raise RuntimeError("ELEVENLABS_API_KEY missing in .env")

    client = ElevenLabs(api_key=api_key)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "voiceover.mp3"

    audio_stream = client.text_to_speech.convert(
        voice_id=DEFAULT_VOICE_ID,
        model_id=DEFAULT_MODEL,
        text=narration,
        output_format="mp3_44100_128",
    )
    with open(out_path, "wb") as f:
        for chunk in audio_stream:
            if chunk:
                f.write(chunk)

    return {
        "path": str(out_path),
        "duration_seconds": _audio_duration_seconds(out_path),
        "provider": "elevenlabs",
        "voice_id": DEFAULT_VOICE_ID,
    }
