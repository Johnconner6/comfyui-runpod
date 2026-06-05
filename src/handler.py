import os
import sys
import runpod

print(f"[startup] Python {sys.version}", flush=True)
print(f"[startup] PYTHONPATH: {os.environ.get('PYTHONPATH')}", flush=True)
print(f"[startup] /runpod-volume exists: {os.path.exists('/runpod-volume')}", flush=True)
print(f"[startup] /runpod-volume/models exists: {os.path.exists('/runpod-volume/models')}", flush=True)
print(f"[startup] handler loaded", flush=True)

def handler(job):
    print("[handler] job received", flush=True)
    try:
        path = "/runpod-volume/models"
        print(f"[handler] listing {path}", flush=True)
        files = os.listdir(path)
        print(f"[handler] found: {files}", flush=True)
        return {"files": files}
    except Exception as e:
        print(f"[handler] error: {e}", flush=True)
        return {"error": str(e)}

runpod.serverless.start({"handler": handler})
