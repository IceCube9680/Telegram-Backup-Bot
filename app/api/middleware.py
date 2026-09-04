"""Security headers, request correlation IDs, and rate limiting middleware for FastAPI."""

import asyncio
from collections import defaultdict, deque
import re
import time
from typing import Callable, Deque, Dict, Optional, Tuple
import uuid
from fastapi import HTTPException, Request, Response, status
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Request ID regex validation (safe chars, max 64 chars)
REQUEST_ID_REGEX = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Middleware to extract or generate unique request correlation ID."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        raw_req_id = request.headers.get("X-Request-ID")
        if raw_req_id and REQUEST_ID_REGEX.match(raw_req_id):
            req_id = raw_req_id
        else:
            req_id = uuid.uuid4().hex

        request.state.request_id = req_id

        response = await call_next(request)
        response.headers["X-Request-ID"] = req_id
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware enforcing production HTTP security headers and Content Security Policy."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        settings = get_settings()

        # Standard Security Headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=(), payment=()"

        # Strict Content Security Policy
        csp_directives = [
            "default-src 'self'",
            "script-src 'self' 'unsafe-inline' https://telegram.org",
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
            "font-src 'self' https://fonts.gstatic.com data:",
            "img-src 'self' data: blob:",
            "connect-src 'self'",
            "frame-ancestors 'none'",
            "object-src 'none'",
            "base-uri 'self'",
            "form-action 'self'",
        ]
        response.headers["Content-Security-Policy"] = "; ".join(csp_directives)

        # HSTS (Strict-Transport-Security) only if HTTPS / Reverse-Proxy HTTPS / Cookie Secure
        is_https = (
            request.url.scheme == "https"
            or request.headers.get("x-forwarded-proto", "").lower() == "https"
            or settings.cookie_secure
        )
        if is_https:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        return response


class InMemoryRateLimiter:
    """In-memory sliding window rate limiter for single-instance deployments.

    Note: This rate limiter stores request timestamps in memory per instance.
    For multi-instance / horizontally scaled deployments, a distributed store (e.g. Redis)
    should be used in future phases.
    """

    def __init__(self) -> None:
        self._requests: Dict[Tuple[str, str], Deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()
        self._last_cleanup = time.monotonic()

    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP respecting X-Forwarded-For safely."""
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            ip = forwarded.split(",")[0].strip()
            if ip:
                return ip
        if request.client and request.client.host:
            return request.client.host
        return "unknown_client"

    async def _cleanup_old_entries(self, now: float) -> None:
        """Periodic garbage collection for stale client keys."""
        if now - self._last_cleanup < 60.0:
            return
        self._last_cleanup = now
        stale_keys = []
        for key, timestamps in list(self._requests.items()):
            while timestamps and now - timestamps[0] > 120.0:
                timestamps.popleft()
            if not timestamps:
                stale_keys.append(key)
        for key in stale_keys:
            self._requests.pop(key, None)

    async def check_rate_limit(
        self,
        request: Request,
        resource_key: str,
        max_requests: int,
        window_seconds: int = 60,
    ) -> None:
        """Check sliding window rate limit for the client IP and resource key."""
        settings = get_settings()
        if not getattr(settings, "RATE_LIMIT_ENABLED", True):
            return

        client_ip = self._get_client_ip(request)
        key = (client_ip, resource_key)
        now = time.monotonic()

        async with self._lock:
            await self._cleanup_old_entries(now)
            timestamps = self._requests[key]

            # Pop timestamps older than the sliding window
            cutoff = now - window_seconds
            while timestamps and timestamps[0] <= cutoff:
                timestamps.popleft()

            if len(timestamps) >= max_requests:
                retry_after = int(window_seconds - (now - timestamps[0])) + 1
                logger.warning(
                    f"Rate limit exceeded for {client_ip} on resource '{resource_key}'. Limit: {max_requests}/{window_seconds}s"
                )
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Too many requests. Please retry in {retry_after} seconds.",
                    headers={"Retry-After": str(max(1, retry_after))},
                )

            timestamps.append(now)


# Global rate limiter instance
limiter = InMemoryRateLimiter()


def rate_limit(resource_key: str, max_requests: int, window_seconds: int = 60) -> Callable:
    """Dependency factory for rate limiting specific route endpoints."""

    async def _dependency(request: Request) -> None:
        await limiter.check_rate_limit(
            request=request,
            resource_key=resource_key,
            max_requests=max_requests,
            window_seconds=window_seconds,
        )

    return _dependency
