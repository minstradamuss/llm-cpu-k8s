import asyncio
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, 'scripts')
from safe_requests import SafeRequestsMiddleware


class MiddlewareTests(unittest.TestCase):
    def test_authorization_and_logging_without_body(self):
        async def app(scope, receive, send):
            await send({'type': 'http.response.start', 'status': 200, 'headers': []})
            await send({'type': 'http.response.body', 'body': b'{"answer":"hi"}'})

        async def run(token):
            messages = []
            async def send(msg):
                messages.append(msg)
            scope = {'type': 'http', 'method': 'POST', 'path': '/v1/chat/completions',
                     'headers': [(b'authorization', token.encode())]}
            await SafeRequestsMiddleware(app)(scope, None, send)
            return messages

        with patch.dict(os.environ, {'API_TOKEN': 'test-only-secret'}):
            valid = asyncio.run(run('Bearer test-only-secret'))
            invalid = asyncio.run(run('Bearer bad'))
        self.assertEqual(valid[0]['status'], 200)
        self.assertEqual(invalid[0]['status'], 401)
        self.assertNotIn(b'test-only-secret', str(invalid).encode())


if __name__ == '__main__':
    unittest.main()
