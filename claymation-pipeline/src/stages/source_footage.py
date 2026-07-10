"""
Stage 4a: source real interview/statement footage for "interview"-routed
stories.

Searches YouTube via yt-dlp (no API key needed), keeps only uploads from
the last N days (default 10), downloads up to max_clips, and pre-trims
each to a short segment used as muted visual b-roll under the continuous
voiceover.

Freshness gate: if nothing qualifying exists (or YouTube is unreachable),
returns an empty list and the caller falls back to claymation. Stale or
off-topic footage is never used.

Sourced clip metadata (title, channel, URL, upload date) is returned so
the build summary can carry attribution.
"""

import json
import shutil
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

MIN_DURATION_S = 45        # skip shorts/teasers with no real statement
MAX_DURATION_S = 3600      # skip multi-hour streams
SEGMENT_S = 20             # trimmed length per clip
SEARCH_LIMIT = 6           # results inspected per query
SKIP_INTRO_FRACTION = 0.10 # start segment 10% in, past intros/titles


def _yt_dlp() -> str | None:
    return shutil.which("yt-dlp")


def _search(query: str, days: int) -> list[dict]:
    """Return metadata for uploads within the freshness window."""
    binpath = _yt_dlp()
    cmd = [
        binpath, f"ytsearch{SEARCH_LIMIT}:{query}",
        "--dump-json", "--skip-download", "--no-warnings", "--no-playlist",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    except (subprocess.TimeoutExpired, OSError) as e:
        print(f"      [Footage] search failed for '{query}': {e}")
        return []
    if proc.returncode != 0 and not proc.stdout.strip():
        print(f"      [Footage] search returned nothing for '{query}'")
        return []
    cutoff = (datetime.utcnow() - timedelta(days=days)).strftime("%Y%m%d")
    hits = []
    for line in proc.stdout.splitlines():
        try:
            meta = json.loads(line)
        except json.JSONDecodeError:
            continue
        upload_date = meta.get("upload_date") or ""
        duration = meta.get("duration") or 0
        if upload_date >= cutoff and MIN_DURATION_S <= duration <= MAX_DURATION_S:
            hits.append({
                "id": meta.get("id"),
                "url": meta.get("webpage_url") or meta.get("original_url"),
                "title": meta.get("title", ""),
                "channel": meta.get("channel") or meta.get("uploader", ""),
                "upload_date": upload_date,
                "duration": duration,
            })
    return hits


def source_footage(queries: list[str], out_dir: Path,
                   days: int = 10, max_clips: int = 2) -> list[dict]:
    """
    Returns up to max_clips of:
      {"path": <trimmed mp4>, "url", "title", "channel", "upload_date"}
    Empty list means: fall back to claymation.
    """
    if not _yt_dlp():
        print("      [Footage] yt-dlp not installed, falling back to claymation")
        return []
    out_dir.mkdir(parents=True, exist_ok=True)

    seen: set[str] = set()
    candidates: list[dict] = []
    for q in queries:
        print(f"      [Footage] searching: {q}")
        for hit in _search(q, days):
            if hit["id"] and hit["id"] not in seen:
                seen.add(hit["id"])
                candidates.append(hit)
    candidates.sort(key=lambda h: h["upload_date"], reverse=True)
    if not candidates:
        print(f"      [Footage] no uploads within the last {days} days")
        return []

    clips: list[dict] = []
    for hit in candidates:
        if len(clips) >= max_clips:
            break
        raw = out_dir / f"raw_{hit['id']}.mp4"
        trimmed = out_dir / f"footage_{len(clips) + 1:02d}.mp4"
        print(f"      [Footage] downloading: {hit['title'][:70]} ({hit['upload_date']})")
        dl = subprocess.run(
            [_yt_dlp(), hit["url"],
             "-f", "mp4[height<=1080]/best[height<=1080]/best",
             "-o", str(raw), "--no-playlist", "--no-warnings"],
            capture_output=True, text=True, timeout=600,
        )
        if dl.returncode != 0 or not raw.exists():
            print(f"      [Footage] download failed, trying next candidate")
            continue
        start = max(0, int(hit["duration"] * SKIP_INTRO_FRACTION))
        trim = subprocess.run(
            ["ffmpeg", "-y", "-ss", str(start), "-i", str(raw),
             "-t", str(SEGMENT_S), "-c:v", "libx264", "-pix_fmt", "yuv420p",
             "-an", str(trimmed)],
            capture_output=True, timeout=300,
        )
        raw.unlink(missing_ok=True)
        if trim.returncode != 0 or not trimmed.exists():
            print(f"      [Footage] trim failed, trying next candidate")
            continue
        clips.append({
            "path": str(trimmed),
            "url": hit["url"],
            "title": hit["title"],
            "channel": hit["channel"],
            "upload_date": hit["upload_date"],
        })
    if not clips:
        print("      [Footage] every candidate failed to download, falling back")
    return clips
