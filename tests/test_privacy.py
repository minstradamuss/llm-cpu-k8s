import asyncio
import io
import json
import logging
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from privacy import AuditMiddleware, SafeFormatter


class PrivacyTests(unittest.IsolatedAsyncioTestCase):
    async def test_streaming_and_errors_do_not_log_content(self):
        marker = "PRIVATE_PROMPT_RESPONSE_TOKEN"
        output = io.StringIO()
        handler = logging.StreamHandler(output)
        handler.setFormatter(SafeFormatter())
        logger = logging.getLogger("audit")
        old_handlers, old_level, old_propagate = logger.handlers[:], logger.level, logger.propagate
        logger.handlers = [handler]
        logger.setLevel(logging.INFO)
        logger.propagate = False
        messages = []

        async def receive():
            return {"type": "http.request", "body": marker.encode()}

        async def send(message):
            messages.append(message)

        async def app(scope, receive, send):
            await receive()
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": marker.encode(), "more_body": True})
            await asyncio.sleep(0.01)
            await send({"type": "http.response.body", "body": b"", "more_body": False})

        try:
            with patch.dict(os.environ, {"VLLM_API_KEY": marker}):
                middleware = AuditMiddleware(app)
            scope = {"type": "http", "method": "POST", "path": "/v1/chat/completions",
                     "query_string": marker.encode(), "headers": [(b"authorization", b"Bearer " + marker.encode())]}
            await middleware(scope, receive, send)
            record = json.loads(output.getvalue())
            self.assertNotIn(marker, output.getvalue())
            self.assertEqual(record["status"], 200)
            self.assertGreaterEqual(record["duration_ms"], 10)
            self.assertEqual(messages[1]["body"], marker.encode())
            self.assertEqual(messages[-1]["more_body"], False)
        finally:
            logger.handlers, logger.level, logger.propagate = old_handlers, old_level, old_propagate

    async def test_auth_also_protects_non_v1_routes(self):
        async def app(scope, receive, send):
            self.fail("Request reached the model without authorization")

        async def receive():
            self.fail("Unauthorized request body was read")

        messages = []

        async def send(message):
            messages.append(message)

        with patch.dict(os.environ, {"VLLM_API_KEY": "secret"}):
            middleware = AuditMiddleware(app)
        await middleware({"type": "http", "method": "POST", "path": "/invocations", "headers": []}, receive, send)
        self.assertEqual(messages[0]["status"], 401)

    def test_exception_text_and_format_arguments_are_not_logged(self):
        marker = "PRIVATE_PROMPT_RESPONSE_TOKEN"
        try:
            raise ValueError(marker)
        except ValueError:
            record = logging.LogRecord("vllm", logging.ERROR, "test.py", 1, "%s", (marker,), sys.exc_info())
        result = SafeFormatter().format(record)
        self.assertNotIn(marker, result)
        self.assertEqual(json.loads(result)["error_type"], "ValueError")


if __name__ == "__main__":
    unittest.main()
