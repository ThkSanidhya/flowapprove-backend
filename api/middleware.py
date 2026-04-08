"""Request-ID middleware + matching log filter.

Every request gets an `X-Request-ID` (honoring the inbound header if present).
The ID is attached to `request.request_id` and echoed on the response so
frontend errors can be correlated with backend logs.
"""

import logging
import uuid

log = logging.getLogger('request')


class RequestIDMiddleware:
    HEADER = 'HTTP_X_REQUEST_ID'

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        rid = request.META.get(self.HEADER) or uuid.uuid4().hex[:16]
        request.request_id = rid
        response = self.get_response(request)
        response['X-Request-ID'] = rid
        log.info(
            '%s %s -> %s',
            request.method,
            request.path,
            response.status_code,
            extra={'rid': rid},
        )
        return response


class RequestIDLogFilter(logging.Filter):
    """Injects `rid` onto every log record so the formatter can reference it."""

    def filter(self, record):
        if not hasattr(record, 'rid'):
            record.rid = '-'
        return True
