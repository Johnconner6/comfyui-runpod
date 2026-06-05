import os
import sys

print(f"[startup] Python {sys.version}", flush=True)
print(f"[startup] PYTHONPATH: {os.environ.get('PYTHONPATH')}", flush=True)
print(f"[startup] /runpod-volume exists: {os.path.exists('/runpod-volume')}", flush=True)
print(f"[startup] /runpod-volume/models exists: {os.path.exists('/runpod-volume/models')}", flush=True)
print(f"[startup] handler loaded", flush=True)

# --- Wait for volume, set up symlinks, validate/download models BEFORE anything else ---
from model_utils import wait_for_volume, setup_model_symlinks, download_models

wait_for_volume()
setup_model_symlinks()
download_models()

print(f"[startup] all models ready, starting handler", flush=True)

import runpod

def handler(job):
    print("[handler] job received", flush=True)
    try:
        path = "/runpod-volume/models"
        print(f"[handler] listing {path}", flush=True)
        files = {}
        for subdir in os.listdir(path):
            subpath = os.path.join(path, subdir)
            if os.path.isdir(subpath):
                files[subdir] = os.listdir(subpath)
        print(f"[handler] found: {files}", flush=True)
        return {"files": files}
    except Exception as e:
        print(f"[handler] error: {e}", flush=True)
        return {"error": str(e)}

runpod.serverless.start({"handler": handler})
