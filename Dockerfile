FROM vllm/vllm-openai-cpu:v0.32.0-x86_64@sha256:827ef38187f9b52f2bb838695ef815ec5b65f4bf3e4c061b002b2b0a19cb0701

USER root
WORKDIR /app
COPY requirements.txt /app/requirements.txt
COPY scripts/check_lock.py /app/check_lock.py
RUN python -m pip install --no-index --no-deps -r /app/requirements.txt && python /app/check_lock.py /app/requirements.txt
RUN groupadd --gid 10001 app && useradd --uid 10001 --gid 10001 --no-create-home app
COPY --chown=10001:10001 src/ /app/
ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOME=/tmp \
    XDG_CACHE_HOME=/tmp/cache \
    VLLM_CACHE_ROOT=/tmp/vllm \
    VLLM_NO_USAGE_STATS=1 \
    DO_NOT_TRACK=1 \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    VLLM_LOGGING_CONFIG_PATH=/app/logging.json
USER 10001:10001
EXPOSE 8000
ENTRYPOINT ["python", "/app/start.py"]
