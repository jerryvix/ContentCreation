"""
Stage 4: b-roll image generation per scene.
Primary: Gemini Imagen 4 text-to-image with the Aardman-style broll_prompt.
Fallback: Gemini Veo 3 for actual video clips if Imagen rejects the prompt.

Imagen returns static PNGs, which Stage 6 turns into video clips via the
ffmpeg Ken Burns zoom. Veo returns rendered video clips directly.

Note: OpenArt was the original plan but they do not expose a public
image-gen API. Imagen 4 is the same provider as the Veo fallback so the
Gemini API key powers both paths.
"""

import os
import time
from pathlib import Path

IMAGEN_MODEL = "imagen-4.0-generate-001"
GEMINI_VEO_MODEL = "veo-3.0-fast-generate-001"
ASPECT = "9:16"  # TikTok vertical


def _save_bytes(content: bytes, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _imagen_generate(prompt: str, out_path: Path, api_key: str) -> bool:
    """Primary: Gemini Imagen 4 still image."""
    try:
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=api_key)
        result = client.models.generate_images(
            model=IMAGEN_MODEL,
            prompt=prompt,
            config=types.GenerateImagesConfig(
                number_of_images=1,
                aspect_ratio=ASPECT,
                output_mime_type="image/png",
            ),
        )
        if not result.generated_images:
            print("      [Imagen] empty response")
            return False
        img_bytes = result.generated_images[0].image.image_bytes
        _save_bytes(img_bytes, out_path)
        return True
    except Exception as e:
        print(f"      [Imagen] exception: {e}")
        return False


def _gemini_veo_generate(prompt: str, out_path: Path, api_key: str) -> bool:
    """Fallback: Gemini Veo 3 for direct video clip generation."""
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
      out_dir/scene_<n>.png  (Imagen path)
      out_dir/scene_<n>.mp4  (Veo fallback path)
    Returns:
      {"provider": "imagen" | "veo" | "mixed",
       "scenes": [{"scene_number":..,"media":..,"kind":"image"|"video"}, ...]}
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if not gemini_key:
        raise RuntimeError(
            "GEMINI_API_KEY missing in .env. Required for both Imagen 4 (primary) "
            "and Veo 3 (fallback) b-roll generation."
        )

    results = []
    providers_used = set()

    for sc in scenes:
        n = sc["scene_number"]
        prompt = sc["broll_prompt"]
        img_path = out_dir / f"scene_{n:02d}.png"
        vid_path = out_dir / f"scene_{n:02d}.mp4"

        print(f"    [Scene {n}] Imagen 4...")
        if _imagen_generate(prompt, img_path, gemini_key):
            results.append({"scene_number": n, "media": str(img_path), "kind": "image"})
            providers_used.add("imagen")
            continue

        print(f"    [Scene {n}] Imagen failed, falling back to Veo 3...")
        if _gemini_veo_generate(prompt, vid_path, gemini_key):
            results.append({"scene_number": n, "media": str(vid_path), "kind": "video"})
            providers_used.add("veo")
            continue

        raise RuntimeError(
            f"Scene {n} b-roll generation failed on both Imagen 4 and Veo 3. "
            "Check GEMINI_API_KEY billing and prompt content (Imagen may refuse "
            "person likenesses or restricted content)."
        )

    provider_label = "mixed" if len(providers_used) > 1 else next(iter(providers_used))
    return {"provider": provider_label, "scenes": results}
