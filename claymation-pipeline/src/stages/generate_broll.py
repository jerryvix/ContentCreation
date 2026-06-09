"""
Stage 4: b-roll image generation per scene.
Primary: OpenArt text-to-image with the full Aardman-style broll_prompt.
Fallback: Gemini Veo 3 for actual video output if OpenArt fails.

OpenArt returns static images, which Stage 6 turns into video clips via
ffmpeg Ken Burns zoom. Veo returns rendered video clips directly.
"""

import base64
import os
import time
from pathlib import Path
from typing import Optional

import httpx

OPENART_BASE = "https://openart.ai/api/v1"
DEFAULT_WORKFLOW_ID = "comfy_text2img_flux_schnell"  # documented OpenArt workflow

GEMINI_VEO_MODEL = "veo-3.0-fast-generate-001"  # Gemini Veo 3 fast tier


def _save_bytes(content: bytes, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _openart_generate(prompt: str, out_path: Path, api_key: str,
                      width: int = 1080, height: int = 1920) -> bool:
    """Try OpenArt. Returns True on success, False on failure."""
    try:
        with httpx.Client(timeout=120.0) as client:
            create = client.post(
                f"{OPENART_BASE}/workflows/{DEFAULT_WORKFLOW_ID}/run",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "inputs": {
                        "prompt": prompt,
                        "width": width,
                        "height": height,
                        "num_images": 1,
                    }
                },
            )
            if create.status_code >= 400:
                print(f"      [OpenArt] HTTP {create.status_code}: {create.text[:200]}")
                return False
            run_id = create.json().get("run_id") or create.json().get("id")
            if not run_id:
                return False
            for _ in range(60):
                time.sleep(3)
                status = client.get(
                    f"{OPENART_BASE}/runs/{run_id}",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                if status.status_code >= 400:
                    return False
                data = status.json()
                if data.get("status") == "completed":
                    image_url = (
                        (data.get("outputs") or [{}])[0].get("url")
                        or (data.get("images") or [{}])[0].get("url")
                    )
                    if not image_url:
                        return False
                    img = client.get(image_url)
                    _save_bytes(img.content, out_path)
                    return True
                if data.get("status") in ("failed", "error", "cancelled"):
                    return False
        return False
    except Exception as e:
        print(f"      [OpenArt] exception: {e}")
        return False


def _gemini_veo_generate(prompt: str, out_path: Path, api_key: str) -> bool:
    """Fallback: Gemini Veo 3 for direct video generation."""
    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        operation = client.models.generate_videos(
            model=GEMINI_VEO_MODEL,
            prompt=prompt,
        )
        for _ in range(60):
            if operation.done:
                break
            time.sleep(5)
            operation = client.operations.get(operation)
        if not operation.done or not operation.response:
            return False
        video = operation.response.generated_videos[0].video
        client.files.download(file=video)
        video.save(str(out_path))
        return True
    except Exception as e:
        print(f"      [Veo] exception: {e}")
        return False


def generate_broll(scenes: list[dict], out_dir: Path) -> dict:
    """
    For each scene, generate b-roll media. Saves:
      out_dir/scene_<n>.png  (OpenArt path)
      out_dir/scene_<n>.mp4  (Veo fallback path)
    Returns: {"provider": "openart" | "veo" | "mixed", "scenes": [{"scene_number":..,"media":..,"kind":"image"|"video"}, ...]}
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    openart_key = os.environ.get("OPENART_API_KEY")
    gemini_key = os.environ.get("GEMINI_API_KEY")

    results = []
    providers_used = set()

    for sc in scenes:
        n = sc["scene_number"]
        prompt = sc["broll_prompt"]
        img_path = out_dir / f"scene_{n:02d}.png"
        vid_path = out_dir / f"scene_{n:02d}.mp4"
        success = False

        if openart_key:
            print(f"    [Scene {n}] OpenArt...")
            if _openart_generate(prompt, img_path, openart_key):
                results.append({"scene_number": n, "media": str(img_path), "kind": "image"})
                providers_used.add("openart")
                success = True

        if not success and gemini_key:
            print(f"    [Scene {n}] OpenArt failed/unavailable, falling back to Gemini Veo...")
            if _gemini_veo_generate(prompt, vid_path, gemini_key):
                results.append({"scene_number": n, "media": str(vid_path), "kind": "video"})
                providers_used.add("veo")
                success = True

        if not success:
            raise RuntimeError(
                f"Scene {n} b-roll generation failed on both OpenArt and Gemini Veo. "
                "Check OPENART_API_KEY and GEMINI_API_KEY in .env."
            )

    provider_label = (
        "mixed" if len(providers_used) > 1
        else next(iter(providers_used))
    )
    return {"provider": provider_label, "scenes": results}
