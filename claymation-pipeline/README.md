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

## Self-bootstrap (hands-off scheduled runs)
Every entry point (`run_all_today.py`, `build_videos_today.py`) starts with `src/utils/bootstrap.py`, which runs before any third-party import:
1. `git fetch` + fast-forward pull if the local revision is behind origin, then re-exec so the updated code runs the same cycle (loop-guarded)
2. probes every package in `REQUIRED_PACKAGES` via a subprocess import: installs missing ones, and repairs broken ones (upgrade + known transitive fixes like cffi/cryptography)
3. verifies ffmpeg, attempting a winget (Windows) or apt (Linux) install

New dependencies go in the `REQUIRED_PACKAGES` manifest, never in setup instructions. All bootstrap steps fail open except ffmpeg, which is a hard stop with a clear message. The daily run heals itself; the only escalations are credential failures, repeated content-policy refusals, and irrecoverable crashes.

## Visual routing (story type -> visual style)
Claymation is a stand-in visual for when nothing real exists to show. If real footage of the key figure exists, it is more credible and specific than a generated illustration.

1. **Interview / direct-quote content** (a key figure spoke on camera about this in the last 10 days): Stage 1 tags the script `visual_route: "interview"` with 1-3 YouTube search queries, marks 2-4 statement scenes `visual_source: "footage"`, and picks one as the `soundbite_scene`. Stage 4a searches via yt-dlp, keeps only uploads from the last 10 days, and downloads 1-2 clips. Stage 4b then transcribes the clip (Whisper), has Claude pick the sharpest on-topic 4-25s quote, and cuts it with its ORIGINAL audio. Assembly splices it in: voiceover part A -> real quote in the figure's own voice -> voiceover part B. Clip attribution and the chosen quote are logged in `output/build_summary.json`.
2. **Soundbite extraction fails** (no OpenAI key, transcript empty, nothing on-topic): the clips still run as muted footage under continuous voiceover.
3. **No qualifying footage found** (nothing recent enough, download failures, or offline): automatic fallback to claymation. Stale or off-topic footage is never used, which is why every footage scene still carries a full claymation `broll_prompt`.
4. **Article-based / text-only reporting** (nobody spoke on camera): `visual_route: "claymation"`, everything renders as before.

Captions are OFF by default everywhere (add them in TikTok's native editor); pass `--captions` to burn them in on non-soundbite timelines.

## Provider fallback (claymation scenes)
- **Primary**: Gemini Imagen 4 (`imagen-4.0-generate-001`) at 9:16 aspect for TikTok vertical. Roughly $0.04/image.
- **Fallback**: Gemini Veo 3 fast tier (`veo-3.0-fast-generate-001`). Triggers per-scene if Imagen refuses the prompt (real-person likeness or other content policy). The switch is noted in `output/build_summary.json`.
- OpenArt was the original target but they do not expose a public image-generation API; both paths run through `GEMINI_API_KEY`.
