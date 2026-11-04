import os
import secrets
from pathlib import Path


target = Path(__file__).resolve().parents[1] / "k8s/overlays/local/secrets.env"
if target.exists():
    print("secrets.env already exists")
else:
    token = os.environ.get("HF_TOKEN", "")
    api_key = os.environ.get("API_KEY") or secrets.token_urlsafe(32)
    if any(character in token + api_key for character in "\r\n"):
        raise SystemExit("Tokens must not contain line breaks")
    with target.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(f"HF_TOKEN={token}\nAPI_KEY={api_key}\n")
    target.chmod(0o600)
    print("Created k8s/overlays/local/secrets.env")
