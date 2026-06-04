import os
import json
import shutil
import struct
import requests

COMFY_DIR = "/root/comfy/ComfyUI"
MODEL_DIR = "/runpod-volume/models"

MODEL_SUBDIRS = [
    "checkpoints", "unet", "loras", "vae", "clip",
    "controlnet", "upscale_models", "embeddings", "configs", "sam3"
]

MODEL_MIN_SIZES = {
    "Qwen-Image-Edit-2509-Q8_0.gguf":        8_000_000_000,
    "wan2.1-i2v-14b-720p-Q8_0.gguf":         14_000_000_000,
    "qwen_2.5_vl_7b_fp8_scaled.safetensors": 7_000_000_000,
    "umt5-xxl-enc-bf16.safetensors":          10_000_000_000,
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
    if not os.path.exists(path):
        return False
    min_size = MODEL_MIN_SIZES.get(filename, 0)
    if min_size > 0:
        actual = os.path.getsize(path)
        if actual < min_size:
            print(f"[models] CORRUPT: {filename} is {actual} bytes, expected >= {min_size}")
            return False
    if filename.endswith(".safetensors"):
        try:
            file_size = os.path.getsize(path)
            with open(path, "rb") as f:
                raw = f.read(8)
                if len(raw) < 8:
                    return False
                header_size = struct.unpack("<Q", raw)[0]
                if file_size < 8 + header_size:
                    return False
                header_bytes = f.read(header_size)
                metadata = json.loads(header_bytes)
                max_end = 0
                for key, info in metadata.items():
                    if key == "__metadata__":
                        continue
                    if isinstance(info, dict) and "data_offsets" in info:
                        end = info["data_offsets"][1]
                        if end > max_end:
                            max_end = end
                if file_size < 8 + header_size + max_end:
                    return False
        except Exception as e:
            print(f"[models] CORRUPT: {filename} validation failed: {e}")
            return False
    return True


def download_models():
    hf_token = os.environ.get("HF_TOKEN", "")
    headers  = {"Authorization": f"Bearer {hf_token}"} if hf_token else {}
    for subdir, filename, url in MODELS:
        dest = f"{MODEL_DIR}/{subdir}/{filename}"
        if is_file_valid(dest, filename):
            print(f"[models] cached: {filename}")
            continue
        if os.path.exists(dest):
            print(f"[models] removing corrupt: {filename}")
            os.remove(dest)
        tmp = dest + ".tmp"
        print(f"[models] downloading {filename}...")
        try:
            r = requests.get(url, headers=headers, stream=True, timeout=3600)
            r.raise_for_status()
            downloaded = 0
            with open(tmp, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 1024):
                    f.write(chunk)
                    downloaded += len(chunk)
            os.rename(tmp, dest)
            print(f"[models] done: {filename} ({downloaded:,} bytes)")
        except Exception as e:
            if os.path.exists(tmp):
                os.remove(tmp)
            raise RuntimeError(f"Failed to download {filename}: {e}")
