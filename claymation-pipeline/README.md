# claymation-pipeline

Automated AI claymation short-video pipeline (style: @business.shorts on Instagram). Feeds @chatjerrpt's daily reviewed TikTok stories into a Stage 1 script generator, with downstream stages for voice (ElevenLabs Daniel), b-roll (Veo 3.1), captions (submagic cyan highlight), and assembly (ffmpeg).

## Setup
```
git clone <repo>
cd claymation-pipeline
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in keys
```

## Stage 1 usage
```
python scripts/run_script_stage.py <story_name>
# expects stories/<story_name>.txt (raw story)
# optional stories/<story_name>.direction.txt (tone/angle direction)
# writes output/<story_name>/script.json
```

To batch-run today's 3 TikTok pipeline stories:
```
python scripts/run_all_today.py
```

## Stages
- Stage 1 (done): script generation with self-review against content rules
- Stage 3 (done): voiceover (ElevenLabs Daniel) from full_narration
- Stage 4 (done): b-roll images per scene via OpenArt, automatic fallback to Gemini Veo 3 for video
- Stage 5 (done): captions overlaid via ffmpeg drawtext (submagic-style cyan highlight box)
- Stage 6 (done): ffmpeg assembly with Ken Burns zoom on still images, voiceover mixed in, output 1080x1920 mp4
- Stage 2 (deferred): character reference image — only Codex story has a `generic_role` archetype; current pipeline lets per-scene prompts carry the description

## End-to-end usage (Windows PowerShell)
```powershell
cd $HOME\ContentCreation\claymation-pipeline
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
# Fill .env with ANTHROPIC_API_KEY, OPENART_API_KEY, ELEVENLABS_API_KEY, GEMINI_API_KEY

# Stage 1: scripts (already produced by earlier session for today's 3 stories)
python scripts\run_all_today.py

# Stages 3-6: voiceover + b-roll + caption + assemble
python scripts\build_videos_today.py
```

Finished files land at:
- `output\apple_gemini_swappable\final.mp4`
- `output\codex_analyst_replacement\final.mp4`
- `output\dual_ai_ipos\final.mp4`

## Provider fallback
- OpenArt is the primary image provider for scene b-roll. On any failure (4xx, timeout, missing key) the pipeline automatically tries Gemini Veo 3 (`veo-3.0-fast-generate-001`) for that scene and notes the switch in `output/build_summary.json`.
