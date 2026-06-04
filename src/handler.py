import base64
import os
import runpod
import requests

from model_utils  import setup_model_symlinks, download_models
from comfy_utils  import (setup_reference_images, start_comfyui,
                           upload_images, queue_prompt, poll_until_done)

# ── On worker startup: symlink volume dirs, download any missing models ──────
print("[init] Setting up model symlinks...")
setup_model_symlinks()
print("[init] Checking/downloading models...")
download_models()
print("[init] Ready.")


def handler(job):
    job_input    = job["input"]
    callback_url = job_input.get("callback_url", "")
    chat_id      = job_input.get("chat_id")
    message_id   = job_input.get("message_id")
    is_video     = job_input.get("is_video", False)
    output_key   = "video_base64" if is_video else "image_base64"

    proc = None
    try:
        setup_reference_images()
        proc = start_comfyui()
        upload_images(job_input.get("images", []))

        media_bytes, fname, mime = poll_until_done(
            queue_prompt(job_input["workflow"]),
            callback_url,
            is_video=is_video,
            timeout=900,
            chat_id=chat_id,
            message_id=message_id,
        )

        result = {
            output_key:  base64.b64encode(media_bytes).decode(),
            "filename":  fname,
            "mime":      mime,
            "done":      True,
            "chat_id":   chat_id,
            "message_id": message_id,
        }

        if callback_url:
            try:
                requests.post(callback_url, json=result, timeout=30)
            except Exception as e:
                print(f"[result] callback failed: {e}")

        return result

    except Exception as e:
        print(f"[error] {e}")
        err = {
            "done": True, "error": str(e), "pct": 0,
            "text": f"❌ Generation failed: {e}",
            "chat_id": chat_id, "message_id": message_id,
        }
        if callback_url:
            try:
                requests.post(callback_url, json=err, timeout=10)
            except Exception:
                pass
        raise

    finally:
        if proc:
            proc.terminate()


runpod.serverless.start({"handler": handler})
