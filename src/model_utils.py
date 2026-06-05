import os
import shutil

COMFY_DIR = "/root/comfy/ComfyUI"
MODEL_DIR  = "/runpod-volume/models"

MODEL_SUBDIRS = [
    "checkpoints", "unet", "loras", "vae", "clip",
    "controlnet", "upscale_models", "embeddings", "configs", "sam3"
]

def setup_model_symlinks():
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
        print(f"[symlink] {comfy_path} → {vol_path}", flush=True)
