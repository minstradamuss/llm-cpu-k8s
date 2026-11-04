import json
import logging
import hmac
import os
import time
import uuid


class SafeFormatter(logging.Formatter):
    def format(self, record):
        data = {
            "time": round(record.created, 3),
            "level": record.levelname,
            "logger": record.name,
            "event": "runtime",
            "line": record.lineno,
        }
        if record.name == "audit" and hasattr(record, "audit"):
            data.update(record.audit)
        if record.exc_info and record.exc_info[0]:
            data["error_type"] = record.exc_info[0].__name__
        result = json.dumps(data, ensure_ascii=True, separators=(",", ":"))
        nonce = os.environ.get("VLLM_AUDIT_NONCE")
        return f"AUDIT_{nonce} {result}" if nonce else result


class AuditMiddleware:
    routes = {
        "/v1/chat/completions",
        "/v1/completions",
        "/v1/models",
        "/tokenize",
        "/detokenize",
    }

    def __init__(self, app):
        self.app = app
        self.logger = logging.getLogger("audit")
        self.token = os.environ.get("VLLM_API_KEY", "").encode()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("path") in {"/health", "/metrics"}:
            await self.app(scope, receive, send)
            return
        start = time.perf_counter()
        status = 500
        request_id = uuid.uuid4().hex

        async def send_response(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                message = dict(message)
                message["headers"] = list(message.get("headers", [])) + [
                    (b"x-request-id", request_id.encode())
                ]
            await send(message)

        try:
            headers = dict(scope.get("headers", []))
            supplied = headers.get(b"authorization", b"")
            if not self.token or not hmac.compare_digest(supplied, b"Bearer " + self.token):
                await send_response({"type": "http.response.start", "status": 401,
                                     "headers": [(b"content-type", b"application/json")]})
                await send_response({"type": "http.response.body", "body": b'{"error":"Unauthorized"}'})
                return
            if scope.get("path") not in self.routes:
                await send_response({"type": "http.response.start", "status": 404, "headers": []})
                await send_response({"type": "http.response.body", "body": b""})
                return
            await self.app(scope, receive, send_response)
        finally:
            method = scope.get("method")
            self.logger.info("", extra={"audit": {
                "event": "request_complete",
                "request_id": request_id,
                "method": method if method in {"GET", "POST", "OPTIONS"} else "OTHER",
                "route": scope["path"] if scope["path"] in self.routes else "other",
                "status": status,
                "duration_ms": round((time.perf_counter() - start) * 1000, 3),
            }})
