import fcntl
import hashlib
import json
import os
import re
import sys
import shutil
import time
from pathlib import Path
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class SafeRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, url):
        if urlsplit(url).scheme != "https":
            raise ValueError("HTTPS is required")
        redirected = super().redirect_request(request, fp, code, message, headers, url)
        if urlsplit(request.full_url).netloc != urlsplit(url).netloc:
            redirected.remove_header("Authorization")
        return redirected


def matches(path, item):
    if not path.is_file() or path.stat().st_size != item["size"]:
        return False
    if item.get("lfs"):
        return digest(path) == item["lfs"]["sha256"]
    value = hashlib.sha1(f"blob {item['size']}\0".encode())
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest() == item["blobId"]


def download(repo, revision, target):
    headers = {"User-Agent": "student-vllm-cpu/1.0"}
    if os.environ.get("HF_TOKEN"):
        headers["Authorization"] = "Bearer " + os.environ["HF_TOKEN"]
    opener = build_opener(SafeRedirect())
    api = f"https://huggingface.co/api/models/{quote(repo, safe='/')}/revision/{revision}?blobs=true"
    with opener.open(Request(api, headers=headers), timeout=60) as response:
        metadata = json.load(response)
    if metadata["sha"] != revision:
        raise ValueError("Model revision mismatch")
    for item in metadata["siblings"]:
        name = item["rfilename"]
        if Path(name).suffix not in {".json", ".safetensors", ".txt", ".model", ".jinja"}:
            continue
        path = (target / name).resolve()
        if not path.is_relative_to(target.resolve()):
            raise ValueError("Invalid model path")
        path.parent.mkdir(parents=True, exist_ok=True)
        if matches(path, item):
            continue
        url = f"https://huggingface.co/{quote(repo, safe='/')}/resolve/{revision}/{quote(name, safe='/')}?download=true"
        pending = path.with_name(path.name + ".part")
        for attempt in range(8):
            try:
                if matches(pending, item):
                    pending.replace(path)
                    break
                if pending.exists() and pending.stat().st_size >= item["size"]:
                    pending.unlink()
                offset = pending.stat().st_size if pending.exists() else 0
                request_headers = dict(headers)
                if offset:
                    request_headers["Range"] = f"bytes={offset}-"
                with opener.open(Request(url, headers=request_headers), timeout=600) as response:
                    mode = "ab" if offset and response.status == 206 else "wb"
                    with pending.open(mode) as stream:
                        shutil.copyfileobj(response, stream, 1024 * 1024)
                if pending.stat().st_size != item["size"]:
                    if pending.stat().st_size > item["size"]:
                        pending.unlink()
                    raise OSError("Incomplete download")
                if not matches(pending, item):
                    pending.unlink()
                    raise OSError("Checksum mismatch")
                pending.replace(path)
                break
            except OSError:
                if attempt == 7:
                    raise
                time.sleep(2)


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def cached(target, repo, revision):
    try:
        manifest = json.loads((target / ".ready.json").read_text())
        if manifest["repo"] != repo or manifest["revision"] != revision or not manifest["files"]:
            return False
        for item in manifest["files"]:
            path = (target / item["name"]).resolve()
            if not path.is_relative_to(target.resolve()):
                return False
            if path.stat().st_size != item["size"] or digest(path) != item["sha256"]:
                return False
        return True
    except (OSError, ValueError, KeyError, TypeError):
        return False


def main():
    repo = os.environ["MODEL_ID"]
    revision = os.environ["MODEL_REVISION"]
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("A commit SHA is required")
    root = Path(os.environ["MODEL_DIR"])
    root.mkdir(parents=True, exist_ok=True)
    target = root / revision
    target.mkdir(exist_ok=True)
    with (root / ".download.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if cached(target, repo, revision):
            print(json.dumps({"event": "model_cache_hit"}), flush=True)
            return
        (target / ".ready.json").unlink(missing_ok=True)
        download(repo, revision, target)
        if not (target / "config.json").is_file() or not list(target.glob("*.safetensors")):
            raise ValueError("Incomplete model")
        files = [
            {"name": str(path.relative_to(target)), "size": path.stat().st_size, "sha256": digest(path)}
            for path in sorted(target.rglob("*"))
            if path.is_file() and not any(part.startswith(".") for part in path.relative_to(target).parts)
        ]
        pending = target / ".ready.tmp"
        pending.write_text(json.dumps({"repo": repo, "revision": revision, "files": files}))
        pending.replace(target / ".ready.json")
        print(json.dumps({"event": "model_download_complete", "files": len(files)}), flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(json.dumps({"event": "model_download_failed", "error_type": type(error).__name__}), flush=True)
        sys.exit(1)
