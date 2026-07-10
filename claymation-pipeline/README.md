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
- Stage 4 (done): b-roll images per scene via Gemini Imagen 4, automatic fallback to Gemini Veo 3 if Imagen refuses a prompt
- Stage 5 (done): captions overlaid via ffmpeg drawtext (submagic-style cyan highlight box)
- Stage 6 (done): ffmpeg assembly with Ken Burns zoom on still images, voiceover mixed in, output 1080x1920 mp4
- Stage 2 (deferred): character reference image — only Codex story has a `generic_role` archetype; current pipeline lets per-scene prompts carry the description

## End-to-end usage (Windows PowerShell)
```powershell
cd $HOME\ContentCreation\claymation-pipeline
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
# Fill .env with ANTHROPIC_API_KEY, GEMINI_API_KEY, ELEVENLABS_API_KEY

# Stage 1: scripts (already produced by earlier session for today's 3 stories)
python scripts\run_all_today.py

# Stages 3-6: voiceover + b-roll + caption + assemble
python scripts\build_videos_today.py
```

Finished files land at:
- `output\apple_gemini_swappable\final.mp4`
- `output\codex_analyst_replacement\final.mp4`
- `output\dual_ai_ipos\final.mp4`

## Visual routing (story type -> visual style)
Claymation is a stand-in visual for when nothing real exists to show. If real footage of the key figure exists, it is more credible and specific than a generated illustration.

1. **Interview / direct-quote content** (a key figure spoke on camera about this in the last 10 days): Stage 1 tags the script `visual_route: "interview"` with 1-3 YouTube search queries and marks 2-4 statement scenes `visual_source: "footage"`. Stage 4a searches via yt-dlp, keeps only uploads from the last 10 days, downloads 1-2 clips, trims each to a ~20s muted segment, and builds those scenes around the real footage. Clip attribution (title, channel, URL, date) is logged in `output/build_summary.json`.
2. **No qualifying footage found** (nothing recent enough, download failures, or offline): automatic fallback to claymation. Stale or off-topic footage is never used, which is why every footage scene still carries a full claymation `broll_prompt`.
3. **Article-based / text-only reporting** (nobody spoke on camera): `visual_route: "claymation"`, everything renders as before.

## Provider fallback (claymation scenes)
- **Primary**: Gemini Imagen 4 (`imagen-4.0-generate-001`) at 9:16 aspect for TikTok vertical. Roughly $0.04/image.
- **Fallback**: Gemini Veo 3 fast tier (`veo-3.0-fast-generate-001`). Triggers per-scene if Imagen refuses the prompt (real-person likeness or other content policy). The switch is noted in `output/build_summary.json`.
- OpenArt was the original target but they do not expose a public image-generation API; both paths run through `GEMINI_API_KEY`.
