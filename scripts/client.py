import json
import os
from pathlib import Path
from urllib.request import Request, urlopen


def api_key():
    if os.environ.get("API_KEY"):
        return os.environ["API_KEY"]
    path = Path(__file__).resolve().parents[1] / "k8s/overlays/local/secrets.env"
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if line.startswith("API_KEY="):
            return line.split("=", 1)[1]
    raise RuntimeError("API_KEY is missing")


def request(base, route, payload=None, token=None, timeout=300):
    headers = {"Content-Type": "application/json"}
    if token is not None:
        headers["Authorization"] = "Bearer " + token
    data = None if payload is None else json.dumps(payload).encode()
    return urlopen(Request(base.rstrip("/") + route, data=data, headers=headers), timeout=timeout)
