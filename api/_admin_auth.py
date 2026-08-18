"""Minimal server-side authorization for new CRM admin APIs."""

import hmac
import os


class AdminAuthError(RuntimeError):
    def __init__(self, status_code, message):
        self.status_code = status_code
        super().__init__(message)


def require_admin(handler):
    """Require a server-configured bearer token; fail closed when absent."""
    expected = str(os.environ.get("ADMIN_API_TOKEN") or "").strip()
    if not expected:
        raise AdminAuthError(503, "Admin access is not configured")

    authorization = str(handler.headers.get("Authorization") or "")
    scheme, separator, supplied = authorization.partition(" ")
    if not separator or scheme.lower() != "bearer":
        raise AdminAuthError(401, "Administrator authentication required")

    if not hmac.compare_digest(supplied.strip(), expected):
        raise AdminAuthError(403, "Administrator authentication failed")
