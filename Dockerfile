FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV COMFY_DIR=/root/comfy/ComfyUI
ENV MODEL_DIR=/runpod-volume/models
ENV PYTHONPATH=/app
RUN apt-get update && apt-get install -y \
    python3.11 python3.11-venv python3-pip \
    git wget libgl1 libglib2.0-0 ffmpeg procps curl \
    && rm -rf /var/lib/apt/lists/*
RUN ln -sf /usr/bin/python3.11 /usr/bin/python && \
    ln -sf /usr/bin/python3.11 /usr/bin/python3
RUN pip install comfy-cli
RUN comfy --skip-prompt install --nvidia
RUN pip install --no-cache-dir \
    torch --pre --index-url https://download.pytorch.org/whl/nightly/cu124
RUN pip install --no-cache-dir \
    aiohttp requests Pillow gguf safetensors \
    transformers accelerate opencv-python-headless \
    imageio imageio-ffmpeg fastapi uvicorn runpod==1.7.3
# Step 4 — custom nodes TEMPORARILY DISABLED for isolation test
# RUN cd ${COMFY_DIR}/custom_nodes && \
#     git clone https://github.com/MoonGoblinDev/Civicomfy.git && \
#     git clone https://github.com/chibiace/ComfyUI-Chibi-Nodes.git && \
#     git clone https://github.com/pythongosssss/ComfyUI-Custom-Scripts.git && \
#     git clone https://github.com/LeonQ8/ComfyUI-Dynamic-Lora-Scheduler.git && \
#     git clone https://github.com/yolain/ComfyUI-Easy-Use.git && \
#     git clone https://github.com/city96/ComfyUI-GGUF.git && \
#     git clone https://github.com/kijai/ComfyUI-KJNodes.git && \
#     git clone https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git && \
#     git clone https://github.com/Smirnov75/ComfyUI-mxtoolkit.git && \
#     git clone https://github.com/cubiq/ComfyUI_essentials.git && \
#     git clone https://github.com/chrisgoringe/cg-use-everywhere.git && \
#     git clone https://github.com/WASasquatch/was-node-suite-comfyui.git && \
#     git clone https://github.com/kijai/ComfyUI-WanVideoWrapper.git && \
#     git clone https://github.com/rgthree/rgthree-comfy.git && \
#     git clone https://github.com/PozzettiAndrea/ComfyUI-SAM3.git && \
#     find . -name requirements.txt | xargs -I{} pip install -r {} -q || true
COPY src/ /app/
COPY src/extra_model_paths.yaml /root/comfy/ComfyUI/extra_model_paths.yaml
WORKDIR /app
CMD ["python", "-u", "handler.py"]
