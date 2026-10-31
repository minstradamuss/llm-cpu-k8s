import json
import os
from pathlib import Path

from huggingface_hub import HfApi, snapshot_download


def main():
    repo_id = os.environ.get('MODEL_ID', 'Qwen/Qwen2.5-0.5B-Instruct')
    revision = os.environ.get('MODEL_REVISION', 'main')
    directory = Path(os.environ.get('MODEL_DIR', '/models/qwen'))
    marker = directory / '.ready.json'

    if marker.exists() and (directory / 'config.json').exists():
        meta = json.loads(marker.read_text(encoding='utf-8'))
        if meta.get('repo_id') == repo_id and meta.get('revision') == revision:
            print('Model exists on PVC; starting without network access', flush=True)
            return

    token = os.environ.get('HF_TOKEN') or None
    print('Downloading model to persistent volume (first startup)', flush=True)
    info = HfApi(token=token).model_info(repo_id, revision=revision)
    directory.mkdir(parents=True, exist_ok=True)
    snapshot_download(
        repo_id=repo_id,
        revision=info.sha,
        local_dir=directory,
        token=token,
        allow_patterns=['*.json', '*.safetensors', '*.model', '*.txt', '*.jinja', '*.tiktoken'],
    )
    if not (directory / 'config.json').is_file():
        raise RuntimeError('Model download incomplete: config.json is missing')
    weights = list(directory.glob('*.safetensors'))
    if not weights:
        raise RuntimeError('Model download incomplete: weights are missing')
    tmp = marker.with_suffix('.tmp')
    tmp.write_text(json.dumps({'repo_id': repo_id, 'revision': revision, 'commit': info.sha}), encoding='utf-8')
    tmp.replace(marker)
    print('Model downloaded and marked ready', flush=True)


if __name__ == '__main__':
    main()
