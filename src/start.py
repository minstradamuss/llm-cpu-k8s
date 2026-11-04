import os
import json
import secrets
import signal
import subprocess
import sys
from pathlib import Path


def main():
    if not os.environ.get("VLLM_API_KEY", "").strip():
        raise SystemExit("API token is required")
    model = Path(os.environ["MODEL_DIR"]) / os.environ["MODEL_REVISION"]
    if not (model / ".ready.json").is_file():
        raise SystemExit("Model has not been downloaded")
    os.environ.update({
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "VLLM_NO_USAGE_STATS": "1",
        "DO_NOT_TRACK": "1",
        "VLLM_DEBUG_LOG_API_SERVER_RESPONSE": "0",
        "VLLM_LOGGING_CONFIG_PATH": "/app/logging.json",
        "VLLM_AUDIT_NONCE": secrets.token_hex(24),
    })
    args = [
        sys.executable, "-m", "vllm.entrypoints.cli.main", "serve", str(model),
        "--host", "0.0.0.0", "--port", "8000",
        "--served-model-name", os.environ.get("SERVED_MODEL_NAME", "qwen"),
        "--dtype", os.environ.get("DTYPE", "float32"),
        "--max-model-len", os.environ.get("MAX_MODEL_LEN", "2048"),
        "--max-num-seqs", os.environ.get("MAX_NUM_SEQS", "4"),
        "--max-num-batched-tokens", os.environ.get("MAX_NUM_BATCHED_TOKENS", "512"),
        "--kv-cache-memory-bytes", os.environ.get("KV_CACHE_MEMORY_BYTES", "268435456"),
        "--enforce-eager", "--load-format", "safetensors",
        "--no-enable-log-requests", "--no-enable-log-outputs",
        "--disable-uvicorn-access-log", "--disable-fastapi-docs",
        "--log-config-file", "/app/logging.json",
        "--middleware", "privacy.AuditMiddleware",
        "--generation-config", "vllm",
    ]
    for name, flag in [
        ("ENABLE_PREFIX_CACHING", "enable-prefix-caching"),
        ("ENABLE_CHUNKED_PREFILL", "enable-chunked-prefill"),
    ]:
        args.append("--" + ("" if os.environ.get(name, "false").lower() == "true" else "no-") + flag)
    process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               text=True, errors="replace", start_new_session=True)

    def stop(signum, frame):
        try:
            os.killpg(process.pid, signum)
        except ProcessLookupError:
            pass

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    prefix = "AUDIT_" + os.environ["VLLM_AUDIT_NONCE"] + " "
    suppressed = 0
    for line in process.stdout:
        if line.startswith(prefix):
            try:
                record = json.loads(line[len(prefix):])
                print(json.dumps(record, separators=(",", ":")), flush=True)
            except json.JSONDecodeError:
                suppressed += 1
        else:
            suppressed += 1
    code = process.wait()
    print(json.dumps({"event": "server_exit", "code": code, "suppressed_lines": suppressed}), flush=True)
    raise SystemExit(code if code >= 0 else 128 - code)


if __name__ == "__main__":
    main()
