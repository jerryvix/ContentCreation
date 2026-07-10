"""
Self-bootstrap for scheduled runs: no manual steps on the host machine.

Called at the very top of every entry point, BEFORE any third-party
imports:
1. git fetch + fast-forward pull if the local revision is behind origin,
   then re-exec the script so the updated code runs this same cycle
2. ensure every package in REQUIRED_PACKAGES is importable, pip install
   any that are missing (new dependencies go in that manifest, never in
   run instructions for the user)
3. ensure ffmpeg exists, attempting a best-effort install per-OS

Every step is fail-open except ffmpeg: a fetch/pull/install failure logs
and continues on the current revision, so a network blip never kills the
daily run. A missing, uninstallable ffmpeg is a hard stop because
nothing downstream can work without it.

This module must import ONLY the standard library: it runs before
dependencies are guaranteed to exist.
"""

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BRANCH = "claude/inspiring-keller-jGvEA"
REEXEC_GUARD = "CLAYMATION_BOOTSTRAPPED"

# import name -> pip install name. ANY new pipeline dependency gets a row
# here; the next scheduled run installs it automatically.
REQUIRED_PACKAGES = {
    "dotenv": "python-dotenv",
    "anthropic": "anthropic",
    "google.genai": "google-genai",
    "elevenlabs": "elevenlabs",
    "openai": "openai",
    "httpx": "httpx",
    "PIL": "pillow",
    "yt_dlp": "yt-dlp",
}


def _run(cmd: list[str], timeout: int = 600) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=timeout)


def _self_update() -> bool:
    """Fast-forward to origin/BRANCH if behind. Returns True if code changed."""
    try:
        fetch = _run(["git", "fetch", "origin", BRANCH], timeout=180)
        if fetch.returncode != 0:
            print(f"  [Bootstrap] git fetch failed ({fetch.stderr.strip()[:120]}), continuing on current revision")
            return False
        local = _run(["git", "rev-parse", "HEAD"]).stdout.strip()
        remote = _run(["git", "rev-parse", f"origin/{BRANCH}"]).stdout.strip()
        if not local or not remote or local == remote:
            print("  [Bootstrap] code up to date")
            return False
        pull = _run(["git", "pull", "--ff-only", "origin", BRANCH], timeout=180)
        if pull.returncode != 0:
            print(f"  [Bootstrap] pull failed ({pull.stderr.strip()[:120]}), continuing on current revision")
            return False
        print(f"  [Bootstrap] code updated {local[:7]} -> {remote[:7]}")
        return True
    except Exception as e:
        print(f"  [Bootstrap] self-update skipped: {e}")
        return False


def _import_ok(mod: str) -> tuple[bool, str]:
    """Probe an import in a subprocess so a crashing package (not just a
    missing one) can't take down the bootstrap process itself."""
    r = _run([sys.executable, "-c", f"import {mod}"], timeout=120)
    return r.returncode == 0, (r.stderr or "").strip()


def _pip(args: list[str]) -> None:
    _run([sys.executable, "-m", "pip", "install", "--quiet", *args])


def _ensure_packages() -> None:
    for mod, pip_name in REQUIRED_PACKAGES.items():
        ok, err = _import_ok(mod)
        if ok:
            continue
        print(f"  [Bootstrap] {pip_name} missing or broken, installing...")
        _pip(["--upgrade", pip_name])
        ok, err = _import_ok(mod)
        if ok:
            continue
        # Still broken: usually a damaged transitive dependency (classic
        # case: system cryptography/cffi mismatch under google-genai).
        # Repair the module the error names, plus the usual suspects.
        candidates = []
        m = re.search(r"No module named '([\w\.]+)'", err)
        if m:
            candidates.append(m.group(1).split(".")[0].lstrip("_"))
        candidates += ["cffi", "cryptography"]
        for dep in dict.fromkeys(candidates):
            print(f"  [Bootstrap] repairing dependency: {dep}")
            _pip(["--upgrade", "--ignore-installed", dep])
            ok, err = _import_ok(mod)
            if ok:
                break
        if not ok:
            print(f"  [Bootstrap] could NOT repair {pip_name}: {err[:200]}")
            print("  [Bootstrap] continuing; stages that need it will fall back or fail loudly")


def _ensure_ffmpeg() -> None:
    if shutil.which("ffmpeg") and shutil.which("ffprobe"):
        return
    print("  [Bootstrap] ffmpeg missing, attempting install...")
    try:
        if sys.platform.startswith("win"):
            _run(["winget", "install", "--id", "Gyan.FFmpeg", "-e", "--silent",
                  "--accept-source-agreements", "--accept-package-agreements"], timeout=900)
            # winget updates the registry PATH, not this process; probe common spot
            os.environ["PATH"] += os.pathsep + os.pathsep.join(
                str(p) for p in Path(os.environ.get("LOCALAPPDATA", "")).glob(
                    "Microsoft/WinGet/Packages/Gyan.FFmpeg*/**/bin") if p.is_dir()
            )
        elif sys.platform.startswith("linux"):
            _run(["apt-get", "install", "-y", "--fix-missing", "ffmpeg"], timeout=900)
    except Exception as e:
        print(f"  [Bootstrap] ffmpeg install attempt failed: {e}")
    if not shutil.which("ffmpeg"):
        raise RuntimeError(
            "HARD STOP: ffmpeg is not installed and automatic install failed. "
            "Nothing downstream can render without it. Install ffmpeg manually "
            "(winget install Gyan.FFmpeg) and re-run."
        )


def bootstrap(restart_argv: list[str] | None = None) -> None:
    """
    Run all checks. If the code was updated and restart_argv is given,
    re-exec so this same cycle runs the new code (guarded against loops).
    """
    print("  [Bootstrap] checking code revision and dependencies...")
    already_restarted = os.environ.get(REEXEC_GUARD) == "1"
    updated = False if already_restarted else _self_update()
    _ensure_packages()
    _ensure_ffmpeg()
    if updated and restart_argv:
        print("  [Bootstrap] restarting on updated code...")
        os.environ[REEXEC_GUARD] = "1"
        try:
            os.execv(sys.executable, [sys.executable] + restart_argv)
        except Exception as e:
            print(f"  [Bootstrap] restart failed ({e}), continuing on pre-update code this cycle")
