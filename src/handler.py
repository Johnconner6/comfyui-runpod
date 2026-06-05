import os, runpod
def handler(job):
    return {"files": os.listdir("/runpod-volume/models")}
runpod.serverless.start({"handler": handler})
