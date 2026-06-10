"""
Stage 3: voiceover audio from full_narration.

Primary: ElevenLabs Daniel (matches the script's voice_config).
Fallback: Gemini 2.5 Flash TTS using a deep male voice ("Charon"). This
exists so the pipeline can produce a complete .mp4 even when ElevenLabs
is unreachable. The Gemini key already used for Imagen and Veo powers
this too.

Writes output/<story>/voiceover.mp3 and returns the path + duration.
"""

import os
import subprocess
import wave
from pathlib import Path

ELEVEN_DEFAULT_VOICE_ID = "onwK4e9ZLuTAKqWW03F9"  # Daniel
ELEVEN_MODEL = "eleven_turbo_v2_5"

GEMINI_TTS_MODEL = "gemini-2.5-flash-preview-tts"
GEMINI_TTS_VOICE = "Charon"  # deep, news-anchor timbre
GEMINI_TTS_SAMPLE_RATE = 24000


def _audio_duration_seconds(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return float(out)


def _elevenlabs_generate(narration: str, out_path: Path, api_key: str) -> bool:
    try:
        from elevenlabs.client import ElevenLabs
        client = ElevenLabs(api_key=api_key)
        stream = client.text_to_speech.convert(
            voice_id=ELEVEN_DEFAULT_VOICE_ID,
            model_id=ELEVEN_MODEL,
            text=narration,
            output_format="mp3_44100_128",
        )
        with open(out_path, "wb") as f:
            for chunk in stream:
                if chunk:
                    f.write(chunk)
        return out_path.exists() and out_path.stat().st_size > 1000
    except Exception as e:
        print(f"      [ElevenLabs] failed: {e}")
        return False


def _gemini_tts_generate(narration: str, out_path: Path, api_key: str) -> bool:
    try:
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=GEMINI_TTS_MODEL,
            contents=narration,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name=GEMINI_TTS_VOICE,
                        )
                    )
                ),
            ),
        )
        pcm = response.candidates[0].content.parts[0].inline_data.data
        wav_path = out_path.with_suffix(".wav")
        with wave.open(str(wav_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(GEMINI_TTS_SAMPLE_RATE)
            wf.writeframes(pcm)
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(wav_path),
             "-c:a", "libmp3lame", "-b:a", "128k", str(out_path)],
            check=True, capture_output=True,
        )
        wav_path.unlink(missing_ok=True)
        return True
    except Exception as e:
        print(f"      [Gemini TTS] failed: {e}")
        return False


def generate_voiceover(narration: str, out_dir: Path) -> dict:
    """Returns {path, duration_seconds, provider, voice_id}."""
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "voiceover.mp3"

    eleven_key = os.environ.get("ELEVENLABS_API_KEY")
    gemini_key = os.environ.get("GEMINI_API_KEY")

    if eleven_key:
        print("    [Voiceover] ElevenLabs Daniel...")
        if _elevenlabs_generate(narration, out_path, eleven_key):
            return {
                "path": str(out_path),
                "duration_seconds": _audio_duration_seconds(out_path),
                "provider": "elevenlabs",
                "voice_id": ELEVEN_DEFAULT_VOICE_ID,
            }

    if gemini_key:
        print("    [Voiceover] ElevenLabs unavailable, falling back to Gemini TTS (Charon)...")
        if _gemini_tts_generate(narration, out_path, gemini_key):
            return {
                "path": str(out_path),
                "duration_seconds": _audio_duration_seconds(out_path),
                "provider": "gemini_tts",
                "voice_id": GEMINI_TTS_VOICE,
            }

    raise RuntimeError(
        "Voiceover generation failed on all providers. Check ELEVENLABS_API_KEY "
        "and GEMINI_API_KEY in .env."
    )
