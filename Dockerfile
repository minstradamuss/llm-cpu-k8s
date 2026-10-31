FROM vllm/vllm-openai-cpu:v0.32.0-x86_64

USER root
WORKDIR /opt/app

RUN groupadd --gid 10001 appuser && \
    useradd --uid 10001 --gid 10001 --create-home --shell /bin/sh appuser && \
    mkdir -p /opt/app /models && \
    chown -R 10001:10001 /opt/app /models /home/appuser

COPY --chown=10001:10001 scripts/ /opt/app/scripts/
COPY --chown=10001:10001 logging.json /opt/app/logging.json
COPY --chown=10001:10001 requirements.txt /opt/app/requirements-declared.txt

RUN python -m pip freeze --all > /opt/app/requirements.txt && \
    python -c "import vllm; from importlib.metadata import version; assert tuple(map(int, version('vllm').split('.')[:2])) >= (0, 27)"

ENV PYTHONPATH=/opt/app/scripts \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/home/appuser \
    HF_HOME=/models/.cache/huggingface \
    XDG_CACHE_HOME=/tmp/xdg \
    TORCHINDUCTOR_CACHE_DIR=/tmp/torchinductor \
    CUDA_VISIBLE_DEVICES="" \
    VLLM_TARGET_DEVICE=cpu

USER 10001:10001
EXPOSE 8000
CMD ["python", "/opt/app/scripts/serve.py"]
