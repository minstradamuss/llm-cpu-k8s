import argparse
import concurrent.futures
import datetime
import json
import statistics
import time
from pathlib import Path

from client import api_key, request


def one(args, token, size, number):
    prompt = f"Task {number}: Explain why database indexes improve reads."
    if size == "long":
        prompt += " A service stores user events in a database and needs fast searches by date and user identifier." * 60
        prompt += " Summarize the best indexing strategy in two sentences."
    body = {
        "model": args.model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": args.output_tokens,
        "temperature": 0,
        "ignore_eos": True,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    start = time.perf_counter()
    first = None
    usage = None
    done = False
    try:
        with request(args.url, "/v1/chat/completions", body, token, args.timeout) as response:
            for raw in response:
                line = raw.decode("utf-8").strip()
                if not line.startswith("data: "):
                    continue
                data = line[6:]
                if data == "[DONE]":
                    done = True
                    break
                chunk = json.loads(data)
                if chunk.get("error"):
                    raise RuntimeError("Stream error")
                for choice in chunk.get("choices", []):
                    if choice.get("delta", {}).get("content") and first is None:
                        first = time.perf_counter()
                if chunk.get("usage"):
                    usage = chunk["usage"]
        end = time.perf_counter()
        if first is None or usage is None or not done:
            raise RuntimeError("Incomplete stream")
        return {
            "id": number, "ok": True,
            "ttft_ms": (first - start) * 1000,
            "latency_ms": (end - start) * 1000,
            "input_tokens": usage["prompt_tokens"],
            "output_tokens": usage["completion_tokens"],
        }
    except Exception as error:
        return {"id": number, "ok": False, "error_type": type(error).__name__,
                "latency_ms": (time.perf_counter() - start) * 1000}


def percentile(values, quantile):
    values = sorted(values)
    point = (len(values) - 1) * quantile
    lower = int(point)
    upper = min(lower + 1, len(values) - 1)
    return values[lower] + (values[upper] - values[lower]) * (point - lower)


def table(results):
    lines = [
        "| Промпт | Параллельность | Успех/всего | Вход, ток. | TTFT p50/p95, мс | Latency p50/p95, мс | Запр./с | Выходных ток./с |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in results:
        stats = item["summary"]
        if not stats["success"]:
            lines.append(f"| {item['size']} | {item['concurrency']} | 0/{len(item['requests'])} | — | — | — | 0 | 0 |")
            continue
        lines.append(
            f"| {item['size']} | {item['concurrency']} | {stats['success']}/{len(item['requests'])} "
            f"| {stats['input_tokens_mean']:.1f} | {stats['ttft_p50_ms']:.1f} / {stats['ttft_p95_ms']:.1f} "
            f"| {stats['latency_p50_ms']:.1f} / {stats['latency_p95_ms']:.1f} "
            f"| {stats['requests_per_second']:.3f} | {stats['output_tokens_per_second']:.2f} |"
        )
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--model", default="qwen")
    parser.add_argument("--requests", type=int, default=12)
    parser.add_argument("--warmup", type=int, default=2)
    parser.add_argument("--concurrency", nargs="+", type=int, default=[1, 4])
    parser.add_argument("--output-tokens", type=int, default=32)
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--output", type=Path, default=Path("benchmark/results.json"))
    args = parser.parse_args()
    if args.requests < 1 or args.warmup < 0 or min(args.concurrency) < 1:
        parser.error("Invalid request counts")
    token = api_key()
    results = []
    for size in ["short", "long"]:
        for concurrency in args.concurrency:
            for number in range(args.warmup):
                if not one(args, token, size, -number - 1)["ok"]:
                    raise SystemExit("Warmup failed")
            start = time.perf_counter()
            with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
                rows = list(pool.map(lambda number: one(args, token, size, number), range(args.requests)))
            elapsed = time.perf_counter() - start
            good = [row for row in rows if row["ok"]]
            summary = {"success": len(good), "failed": len(rows) - len(good), "wall_seconds": elapsed}
            if good:
                summary.update({
                    "input_tokens_mean": statistics.mean(row["input_tokens"] for row in good),
                    "output_tokens_mean": statistics.mean(row["output_tokens"] for row in good),
                    "requests_per_second": len(good) / elapsed,
                    "output_tokens_per_second": sum(row["output_tokens"] for row in good) / elapsed,
                })
                for metric in ["ttft", "latency"]:
                    for label, quantile in [("p50", 0.5), ("p95", 0.95)]:
                        summary[f"{metric}_{label}_ms"] = percentile([row[f"{metric}_ms"] for row in good], quantile)
            results.append({"size": size, "concurrency": concurrency, "summary": summary, "requests": rows})
            print(f"{size}, concurrency={concurrency}: {len(good)}/{len(rows)}, {elapsed:.1f}s", flush=True)
    report = {
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "model": args.model, "warmup_per_case": args.warmup,
        "max_output_tokens": args.output_tokens, "results": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    args.output.with_suffix(".md").write_text(table(results), encoding="utf-8")
    print(table(results))
    if any(item["summary"]["failed"] for item in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
