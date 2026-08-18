"""Route Creator, Candidate, and Participant APIs through one Vercel function."""

from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

from api.admin import candidates, creators, participants, registration_import


def _resource_module(handler):
    path = urlparse(handler.path).path.rstrip("/")
    if path.endswith("/participants"):
        return participants
    if path.endswith("/candidates"):
        return candidates
    return creators


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Allow", "GET, POST, PATCH, OPTIONS")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PATCH, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.end_headers()

    def _handle(self, action_name):
        module = _resource_module(self)
        module._dispatch(self, getattr(module, action_name))

    def do_GET(self):
        self._handle("_handle_get")

    def do_POST(self):
        module = _resource_module(self)
        action = parse_qs(urlparse(self.path).query).get("action", [""])[0]
        if module is participants and action == "import_registrations":
            module._dispatch(self, registration_import.handle_import)
            return
        module._dispatch(self, module._handle_post)

    def do_PATCH(self):
        self._handle("_handle_patch")
