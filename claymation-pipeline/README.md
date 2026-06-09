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
- Stage 2 (planned): character reference image (Nano Banana Pro)
- Stage 3 (planned): voiceover audio (ElevenLabs Daniel) from full_narration
- Stage 4 (planned): b-roll scene videos (Veo 3.1) from each broll_prompt
- Stage 5 (planned): captions (Whisper + submagic style overlay)
- Stage 6 (planned): assembly into final .mp4 (ffmpeg)
