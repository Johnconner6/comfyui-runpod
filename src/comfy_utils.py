import base64
import json
import os
import shutil
import subprocess
import time
import requests

COMFY_DIR = "/root/comfy/ComfyUI"
MODEL_DIR  = "/runpod-volume/models"


def setup_reference_images():
    src = f"{MODEL_DIR}/reference_images"
    dst = f"{COMFY_DIR}/input"
    os.makedirs(dst, exist_ok=True)
    if os.path.exists(src):
        for root, dirs, files in os.walk(src):
            for fname in files:
                shutil.copy2(os.path.join(root, fname), os.path.join(dst, fname))
                print(f"[ref] staged: {fname}")
    else:
        print(f"[ref] WARNING: reference_images not found at {src}")


def start_comfyui():
    import signal
    # Kill any stale ComfyUI process
    try:
        for pid_str in os.listdir("/proc"):
            if not pid_str.isdigit():
                continue
            try:
                with open(f"/proc/{pid_str}/cmdline", "rb") as f:
                    cmdline = f.read().decode("utf-8", errors="replace")
                if "main.py" in cmdline and "python" in cmdline:
                    pid = int(pid_str)
                    os.kill(pid, signal.SIGKILL)
                    print(f"[comfyui] killed stale process {pid}")
            except Exception:
                pass
    except Exception as e:
        print(f"[comfyui] proc scan error: {e}")

    time.sleep(3)
    proc = subprocess.Popen(
        ["python", "main.py", "--listen", "127.0.0.1", "--port", "8188",
         "--disable-auto-launch", "--gpu-only"],
        cwd=COMFY_DIR,
    )
    for _ in range(60):
        try:
            r = requests.get("http://127.0.0.1:8188/system_stats", timeout=2)
            if r.status_code == 200:
                print("[comfyui] ready")
                return proc
        except Exception:
            pass
        time.sleep(2)
    raise RuntimeError("ComfyUI failed to start in 120s")


def upload_image_to_comfy(name: str, image_b64: str):
    if "," in image_b64:
        image_b64 = image_b64.split(",", 1)[1]
    padding = 4 - len(image_b64) % 4
    if padding != 4:
        image_b64 += "=" * padding
    img_bytes = base64.b64decode(image_b64)
    if not img_bytes:
        raise ValueError(f"Empty image data for: {name}")
    ext  = name.rsplit(".", 1)[-1].lower() if "." in name else "jpg"
    mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
            "webp": "image/webp", "gif": "image/gif"}.get(ext, "image/jpeg")
    r = requests.post(
        "http://127.0.0.1:8188/upload/image",
        files={"image": (name, img_bytes, mime), "overwrite": (None, "true")}
    )
    r.raise_for_status()
    print(f"[upload] {name}: {len(img_bytes)} bytes → {r.json()}")


def upload_images(images: list):
    for img in images:
        if isinstance(img, dict):
            name      = img.get("name") or img.get("imageFileName") or "input.png"
            image_b64 = img.get("image") or img.get("imageBase64") or img.get("data") or ""
        else:
            name, image_b64 = "input.png", str(img)
        if not image_b64:
            raise ValueError(f"No base64 data found: {img}")
        upload_image_to_comfy(name, image_b64)


def queue_prompt(workflow) -> str:
    if isinstance(workflow, str):
        workflow = json.loads(workflow)
    r = requests.post(
        "http://127.0.0.1:8188/prompt",
        json={"prompt": workflow, "client_id": "runpod-worker"}
    )
    r.raise_for_status()
    return r.json()["prompt_id"]


def push_progress(callback_url: str, pct: int, msg: str, is_video: bool,
                  chat_id=None, message_id=None):
    if not callback_url:
        return
    filled  = round(pct / 10)
    bar     = "▓" * filled + "░" * (10 - filled)
    payload = {
        "pct": pct, "bar": bar,
        "text": f"{'🎬' if is_video else '🖼️'} Generating\n\n{bar}  {pct}%\n\n⚡ {msg}",
        "done": False,
    }
    if chat_id is not None:    payload["chat_id"]    = chat_id
    if message_id is not None: payload["message_id"] = message_id
    try:
        requests.post(callback_url, json=payload, timeout=10)
    except Exception as e:
        print(f"[progress] callback failed (non-fatal): {e}")


def poll_until_done(prompt_id: str, callback_url: str, is_video: bool = False,
                    timeout: int = 600, chat_id=None, message_id=None):
    stages = [
        (0,   "⏳ Queued..."),
        (10,  "🔧 Loading models..."),
        (25,  "🎨 Sampling started..."),
        (50,  "🖌️ Painting details..."),
        (75,  "✨ Refining..."),
        (90,  "🔄 Decoding..."),
        (100, "✅ Done!"),
    ]
    stage_idx = 1
    start     = time.time()
    push_progress(callback_url, 0, stages[0][1], is_video, chat_id, message_id)

    while time.time() - start < timeout:
        time.sleep(2)
        if stage_idx < len(stages):
            elapsed  = time.time() - start
            expected = 300 if is_video else 120
            if (elapsed / expected) * 100 >= stages[stage_idx][0]:
                push_progress(callback_url, stages[stage_idx][0], stages[stage_idx][1],
                              is_video, chat_id, message_id)
                stage_idx += 1
        try:
            hist = requests.get(
                f"http://127.0.0.1:8188/history/{prompt_id}", timeout=60
            ).json()
        except requests.exceptions.ReadTimeout:
            print("[poll] timeout waiting for history, retrying...")
            continue
        except Exception as e:
            print(f"[poll] error: {e}, retrying...")
            continue

        if prompt_id not in hist:
            continue

        outputs = hist[prompt_id].get("outputs", {})
        for key in ("images", "gifs"):
            for node_out in outputs.values():
                if key in node_out and node_out[key]:
                    item   = node_out[key][0]
                    fname  = item["filename"]
                    params = f"filename={fname}&type={item.get('type', 'output')}"
                    if item.get("subfolder"):
                        params += f"&subfolder={item['subfolder']}"
                    dl = requests.get(f"http://127.0.0.1:8188/view?{params}")
                    dl.raise_for_status()
                    mime = ("video/mp4" if fname.endswith(".mp4")
                            else "image/gif" if fname.endswith(".gif")
                            else "image/png")
                    push_progress(callback_url, 100, "✅ Done!", is_video, chat_id, message_id)
                    time.sleep(1)
                    return dl.content, fname, mime

        if outputs:
            raise RuntimeError(f"No output found. Nodes: {list(outputs.keys())}")

    raise TimeoutError(f"Timed out after {timeout}s")
