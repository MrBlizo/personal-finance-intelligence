"""Per-launch token check so other local programs cannot read the API.

The desktop shell generates a random token, passes it to the backend in
``PFI_API_TOKEN`` and opens ``/auth/bootstrap?token=...`` once. That sets
an HttpOnly cookie which the WebView sends with every API call.
"""
import secrets

from fastapi import Request
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware

COOKIE = "pfi_token"
OPEN_PATHS = ("/api/health",)


class TokenMiddleware(BaseHTTPMiddleware):
    """Reject ``/api`` requests without the launch token.

    Parameters
    ----------
    app : ASGIApp
        The wrapped application.
    token : str
        The expected token; an empty string disables the check.
    """

    def __init__(self, app, token: str) -> None:
        super().__init__(app)
        self.token = token

    def _ok(self, request: Request) -> bool:
        given = (request.cookies.get(COOKIE)
                 or request.headers.get("X-PFI-Token") or "")
        return secrets.compare_digest(given, self.token)

    async def dispatch(self, request: Request, call_next):
        if not self.token:
            return await call_next(request)
        path = request.url.path
        if path == "/auth/bootstrap":
            given = request.query_params.get("token", "")
            if not secrets.compare_digest(given, self.token):
                return JSONResponse({"detail": "Invalid launch token."},
                                    status_code=403)
            target = request.query_params.get("next", "/")
            if not target.startswith("/") or target.startswith("//"):
                target = "/"
            resp = RedirectResponse(target, status_code=303)
            resp.set_cookie(COOKIE, self.token, httponly=True,
                            samesite="strict")
            return resp
        if path.startswith("/api") and path not in OPEN_PATHS \
                and not self._ok(request):
            return JSONResponse(
                {"detail": "Not authorised. Open the app through "
                 "PFI.exe; direct browser access is blocked."},
                status_code=401)
        return await call_next(request)
