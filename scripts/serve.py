import os
import subprocess


def main():
    if not os.environ.get('API_TOKEN'):
        raise RuntimeError('API_TOKEN must be set through Kubernetes Secret')
    model_path = os.environ.get('MODEL_DIR', '/models/qwen')
    if not os.path.isfile(os.path.join(model_path, 'config.json')):
        raise RuntimeError('Model files are missing. Check the initContainer and PVC.')

    cmd = [
        'vllm', 'serve', model_path,
        '--host', '0.0.0.0', '--port', '8000',
        '--served-model-name', 'qwen-cpu',
        '--dtype', os.environ.get('MODEL_DTYPE', 'float32'),
        '--max-model-len', os.environ.get('MAX_MODEL_LEN', '1024'),
        '--max-num-seqs', os.environ.get('MAX_NUM_SEQS', '2'),
        '--enforce-eager',
        '--disable-log-requests',
        '--disable-log-outputs',
        '--disable-uvicorn-access-log',
        '--logging-config.pylogging_config_file', '/opt/app/logging.json',
        '--middleware', 'safe_requests.SafeRequestsMiddleware',
    ]
    raise SystemExit(subprocess.call(cmd))


if __name__ == '__main__':
    main()
