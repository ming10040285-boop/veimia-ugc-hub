"""Route Creator and Participant APIs through one Vercel function."""

from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse

from api.admin import creators, participants


def _resource_module(handler):
    path = urlparse(handler.path).path.rstrip("/")
    return participants if path.endswith("/participants") else creators


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
        self._handle("_handle_post")

    def do_PATCH(self):
        self._handle("_handle_patch")
