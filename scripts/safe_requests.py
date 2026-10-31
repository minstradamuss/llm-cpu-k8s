import hmac
import logging
import os
import time

logger = logging.getLogger('safe_requests')


class SafeRequestsMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            await self.app(scope, receive, send)
            return

        method = scope.get('method', 'UNKNOWN')
        path = scope.get('path', '')
        if path in ('/health', '/ping'):
            await self.app(scope, receive, send)
            return

        started = time.perf_counter()
        status = 500
        secret = os.environ.get('API_TOKEN', '')
        headers = dict(scope.get('headers', []))
        authorization = headers.get(b'authorization', b'').decode('latin1')
        authorized = secret and hmac.compare_digest(authorization, 'Bearer ' + secret)

        route = path if path in ('/v1/chat/completions', '/v1/completions', '/v1/models') else 'other'

        try:
            if not authorized:
                payload = b'{"error":"Unauthorized"}'
                await send({'type': 'http.response.start', 'status': 401, 'headers': [
                    (b'content-type', b'application/json'),
                    (b'content-length', str(len(payload)).encode()),
                ]})
                await send({'type': 'http.response.body', 'body': payload})
                status = 401
            else:
                async def capture(message):
                    nonlocal status
                    if message['type'] == 'http.response.start':
                        status = message['status']
                    await send(message)

                await self.app(scope, receive, capture)
        finally:
            elapsed_ms = round((time.perf_counter() - started) * 1000)
            logger.info('request method=%s endpoint=%s status=%s elapsed_ms=%s',
                        method, route, status, elapsed_ms)
