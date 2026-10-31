import argparse
import json
import os
import statistics
import time
import urllib.request


def measure(url, token, prompt):
    data = json.dumps({
        'model': 'qwen-cpu',
        'messages': [{'role': 'user', 'content': prompt}],
        'max_tokens': 32,
        'stream': True,
        'stream_options': {'include_usage': True},
        'temperature': 0,
    }).encode()
    req = urllib.request.Request(
        url.rstrip('/') + '/v1/chat/completions',
        data=data,
        headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token},
    )
    started = time.perf_counter()
    first = None
    tokens = None
    with urllib.request.urlopen(req, timeout=600) as response:
        for raw in response:
            if not raw.startswith(b'data: '):
                continue
            chunk = raw[6:].strip()
            if chunk == b'[DONE]':
                break
            event = json.loads(chunk)
            for choice in event.get('choices', []):
                if choice.get('delta', {}).get('content') and first is None:
                    first = time.perf_counter()
            usage = event.get('usage')
            if usage and usage.get('completion_tokens') is not None:
                tokens = usage['completion_tokens']
    ended = time.perf_counter()
    if first is None or tokens is None:
        raise ValueError('No streamed token or token usage; check vLLM response')
    return (first - started, ended - started, tokens / (ended - started), tokens)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--url', default='http://127.0.0.1:8000')
    ap.add_argument('--samples', type=int, default=3)
    args = ap.parse_args()
    token = os.environ.get('API_TOKEN', '')
    if not token:
        raise SystemExit('Export API_TOKEN before running the benchmark')
    tests = {
        'short': 'Что такое ETL? Ответь одним абзацем.',
        'long': ('Объясни основные этапы ETL, проверку качества данных, обработку ошибок, '
                 'хранение в базе, контроль дубликатов и мониторинг. ' * 30),
    }
    print('| Prompt | TTFT, s | E2E latency, s | Throughput, tok/s |')
    print('|---|---:|---:|---:|')
    for name, prompt in tests.items():
        results = [measure(args.url, token, prompt) for _ in range(args.samples)]
        med = [statistics.median(x[i] for x in results) for i in range(3)]
        print(f'| {name} | {med[0]:.3f} | {med[1]:.3f} | {med[2]:.2f} |')


if __name__ == '__main__':
    main()
