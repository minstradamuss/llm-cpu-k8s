import argparse
import json
import subprocess
import uuid
from urllib.error import HTTPError

from client import api_key, request


parser = argparse.ArgumentParser()
parser.add_argument("--url", default="http://127.0.0.1:8000")
parser.add_argument("--namespace", default="llm-cpu")
args = parser.parse_args()
token = api_key()
marker = "privacy_" + uuid.uuid4().hex
body = {"model": "qwen", "messages": [{"role": "user", "content": "Repeat exactly " + marker}], "max_tokens": 24, "temperature": 0}

for route in ["/v1/chat/completions", "/invocations", "/tokenize"]:
    try:
        request(args.url, route, body).close()
        raise AssertionError("Unauthenticated request was accepted")
    except HTTPError as error:
        assert error.code == 401, error.code

with request(args.url, "/v1/chat/completions?text=" + marker, body, token) as response:
    answer = json.load(response)["choices"][0]["message"]["content"]
    assert answer

invalid = dict(body, model=marker)
try:
    request(args.url, "/v1/chat/completions", invalid, token).close()
    raise AssertionError("Invalid model was accepted")
except HTTPError as error:
    assert error.code in {400, 404}

logs = subprocess.check_output(["kubectl", "-n", args.namespace, "logs", "deployment/llm", "-c", "vllm"], text=True, encoding="utf-8")
assert marker not in logs
assert json.dumps(answer)[1:-1] not in logs
assert answer not in logs
assert token not in logs
assert '"event":"request_complete"' in logs
assert '"status":401' in logs
uid = subprocess.check_output(["kubectl", "-n", args.namespace, "exec", "deployment/llm", "-c", "vllm", "--", "id", "-u"], text=True).strip()
assert uid == "10001", uid
print("PASS: inference, authentication, private logs, UID 10001")
