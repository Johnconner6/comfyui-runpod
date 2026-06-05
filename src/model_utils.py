import os
import json
import shutil
import struct
import time
import requests

COMFY_DIR = "/root/comfy/ComfyUI"
MODEL_DIR = "/runpod-volume/models"

MODEL_SUBDIRS = [
    "checkpoints", "unet", "loras", "vae", "clip",
    "controlnet", "upscale_models", "embeddings", "configs", "sam3"
]

# Minimum expected sizes for large models — used for fast size-only validation
MODEL_MIN_SIZES = {
    "Qwen-Image-Edit-2509-Q8_0.gguf":                    8_000_000_000,
    "wan2.1-i2v-14b-720p-Q8_0.gguf":                    14_000_000_000,
    "qwen_2.5_vl_7b_fp8_scaled.safetensors":             7_000_000_000,
    "umt5-xxl-enc-bf16.safetensors":                     1_000_000_000,
    "Qwen-Image-Lightning-4steps-V2.0-bf16.safetensors": 500_000_000,
    "Try_On_Qwen_Edit_Lora.safetensors":                 100_000_000,
    "Qwen_Snofs_1_2.safetensors":                        100_000_000,
    "qwen_image_vae.safetensors":                        100_000_000,
    "wan_2.1_vae.safetensors":                           100_000_000,
    "sam3.safetensors":                                  100_000_000,
}

MODELS = [
    ("unet", "Qwen-Image-Edit-2509-Q8_0.gguf",        "https://huggingface.co/QuantStack/Qwen-Image-Edit-2509-GGUF/resolve/main/Qwen-Image-Edit-2509-Q8_0.gguf"),
    ("unet", "wan2.1-i2v-14b-720p-Q8_0.gguf",         "https://huggingface.co/city96/Wan2.1-I2V-14B-720P-gguf/resolve/main/wan2.1-i2v-14b-720p-Q8_0.gguf"),
    ("vae",  "qwen_image_vae.safetensors",             "https://huggingface.co/Comfy-Org/Qwen-Image_ComfyUI/resolve/main/split_files/vae/qwen_image_vae.safetensors"),
    ("vae",  "wan_2.1_vae.safetensors",                "https://huggingface.co/SimonJoz/wan-2.1/resolve/main/vae/wan_2.1_vae.safetensors"),
    ("clip", "qwen_2.5_vl_7b_fp8_scaled.safetensors", "https://huggingface.co/Comfy-Org/Qwen-Image_ComfyUI/resolve/main/split_files/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors"),
    ("clip", "umt5-xxl-enc-bf16.safetensors",          "https://huggingface.co/Kijai/WanVideo_comfy/resolve/main/umt5-xxl-enc-bf16.safetensors"),
    ("sam3", "sam3.safetensors",                       "https://huggingface.co/apozz/sam3-safetensors/resolve/main/sam3.safetensors"),
    # --- LoRAs ---
    ("loras", "Qwen_Snofs_1_2.safetensors",                        "https://huggingface.co/GiorgioV/LoRA_for_WAN_22/resolve/main/Qwen_Snofs_1_2.safetensors"),
    ("loras", "Qwen-Image-Lightning-4steps-V2.0-bf16.safetensors", "https://huggingface.co/lightx2v/Qwen-Image-Lightning/resolve/main/Qwen-Image-Lightning-4steps-V2.0-bf16.safetensors"),
    ("loras", "Try_On_Qwen_Edit_Lora.safetensors",                 "https://huggingface.co/FoxBaze/Try_On_Qwen_Edit_Lora_Alpha/resolve/main/Try_On_Qwen_Edit_Lora.safetensors"),
]


def wait_for_volume(path=MODEL_DIR, timeout=60):
    """Wait until the network volume is mounted and accessible."""
    print(f"[startup] waiting for volume at {path}...", flush=True)
    start = time.time()

    # Wait for /runpod-volume to be a real mount
    while not os.path.ismount("/runpod-volume"):
        elapsed = time.time() - start
        if elapsed >= timeout:
            print(f"[startup] WARNING: /runpod-volume not mounted after {timeout}s, continuing anyway", flush=True)
            break
        print(f"[startup] volume not mounted yet, waiting... ({elapsed:.0f}s)", flush=True)
        time.sleep(2)

    # Make sure model dir exists
    os.makedirs(path, exist_ok=True)

    elapsed = time.time() - start
    print(f"[startup] volume ready after {elapsed:.1f}s", flush=True)


def setup_model_symlinks():
    """Create symlinks from ComfyUI model dirs → network volume."""
    for sub in MODEL_SUBDIRS:
        vol_path   = f"{MODEL_DIR}/{sub}"
        comfy_path = f"{COMFY_DIR}/models/{sub}"
        os.makedirs(vol_path, exist_ok=True)
        if os.path.islink(comfy_path):
            pass
        elif os.path.isdir(comfy_path):
            shutil.rmtree(comfy_path)
            os.symlink(vol_path, comfy_path)
        else:
            os.symlink(vol_path, comfy_path)


def is_file_valid(path: str, filename: str) -> bool:
    """
    Fast validation: check file exists and size is above minimum.
    For large models listed in MODEL_MIN_SIZES, size check alone is sufficient.
    For small/unknown safetensors, do a lightweight 8-byte header check only.
    Deep offset validation is skipped to keep startup fast on network volumes.
    """
    if not os.path.exists(path):
        return False

    actual = os.path.getsize(path)

    # Size check — fast and reliable for all known large models
    min_size = MODEL_MIN_SIZES.get(filename, 0)
    if min_size > 0:
        if actual < min_size:
            print(f"[models] CORRUPT: {filename} is {actual:,} bytes, expected >= {min_size:,}", flush=True)
            return False
        # Size looks good — trust it, skip deep validation
        return True

    # For files not in MODEL_MIN_SIZES, do a lightweight header check only
    if filename.endswith(".safetensors"):
        try:
            with open(path, "rb") as f:
                raw = f.read(8)
                if len(raw) < 8:
                    print(f"[models] CORRUPT: {filename} header too short", flush=True)
                    return False
                header_size = struct.unpack("<Q", raw)[0]
                if actual < 8 + header_size:
                    print(f"[models] CORRUPT: {filename} file truncated", flush=True)
                    return False
        except Exception as e:
            print(f"[models] CORRUPT: {filename} validation failed: {e}", flush=True)
            return False

    return True


def download_models():
    """Download any missing or corrupt models to the network volume."""
    hf_token = os.environ.get("HF_TOKEN", "")
    headers  = {"Authorization": f"Bearer {hf_token}"} if hf_token else {}

    for subdir, filename, url in MODELS:
        dest = f"{MODEL_DIR}/{subdir}/{filename}"

        if is_file_valid(dest, filename):
            print(f"[models] cached: {filename}", flush=True)
            continue

        if os.path.exists(dest):
            print(f"[models] removing corrupt/incomplete: {filename}", flush=True)
            os.remove(dest)

        tmp = dest + ".tmp"
        print(f"[models] downloading {filename}...", flush=True)
        try:
            r = requests.get(url, headers=headers, stream=True, timeout=3600)
            r.raise_for_status()
            downloaded = 0
            with open(tmp, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 1024):
                    f.write(chunk)
                    downloaded += len(chunk)
            os.rename(tmp, dest)
            print(f"[models] done: {filename} ({downloaded:,} bytes)", flush=True)
        except Exception as e:
            if os.path.exists(tmp):
                os.remove(tmp)
            raise RuntimeError(f"Failed to download {filename}: {e}")
