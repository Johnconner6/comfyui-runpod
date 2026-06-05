import os
import sys
import runpod

print(f"[startup] Python {sys.version}", flush=True)
print(f"[startup] PYTHONPATH: {os.environ.get('PYTHONPATH')}", flush=True)
print(f"[startup] /runpod-volume exists: {os.path.exists('/runpod-volume')}", flush=True)
print(f"[startup] handler loaded", flush=True)

def handler(job):
    try:
        files = os.listdir("/runpod-volume/models")
        return {"files": files}
    except Exception as e:
        return {"error": str(e)}

runpod.serverless.start({"handler": handler})
