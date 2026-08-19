"""Read campaign JSON from GitHub repository (no cache).

GET /api/admin/read_campaign?id=demo

Returns the latest campaign JSON directly from GitHub Contents API,
bypassing all CDN and static file caches.
"""

from http.server import BaseHTTPRequestHandler
import json
import os
import base64
import urllib.request
import urllib.error
from urllib.parse import urlparse, parse_qs


GITHUB_OWNER = "ming10040285-boop"
GITHUB_REPO = "veimia-ugc-hub"
GITHUB_BRANCH = "main"


def _send_json(handler, status_code, body):
    handler.send_response(status_code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
    handler.end_headers()
    handler.wfile.write(json.dumps(body, ensure_ascii=False).encode("utf-8"))


def _handle_get(handler):
    parsed = urlparse(handler.path)
    params = parse_qs(parsed.query)
    campaign_id = params.get("id", [None])[0]

    if not campaign_id:
        _send_json(handler, 400, {"error": "Missing 'id' query parameter"})
        return

    # Prefer the authenticated GitHub Contents API so reads do not consume the
    # low anonymous rate limit. If the configured token is missing, expired, or
    # invalid, retry the same public repository request without authentication.
    path = f"public/config/campaigns/{campaign_id}.json"
    api_url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{path}?ref={GITHUB_BRANCH}"
    token = str(os.environ.get("GITHUB_TOKEN") or "").strip()

    def build_request(include_token):
        request = urllib.request.Request(api_url)
        if include_token and token:
            request.add_header("Authorization", f"Bearer {token}")
        request.add_header("Accept", "application/vnd.github.v3+json")
        request.add_header("User-Agent", "veimia-ugc-hub")
        return request

    def read_campaign(request):
        with urllib.request.urlopen(request, timeout=8) as response:
            data = json.loads(response.read().decode("utf-8"))
        content_bytes = base64.b64decode(data.get("content", ""))
        return json.loads(content_bytes.decode("utf-8"))

    try:
        try:
            campaign = read_campaign(build_request(include_token=bool(token)))
        except urllib.error.HTTPError as error:
            if token and error.code in (401, 403):
                campaign = read_campaign(build_request(include_token=False))
            else:
                raise
        _send_json(handler, 200, campaign)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            _send_json(handler, 404, {"error": "Campaign not found"})
        elif error.code == 403:
            _send_json(handler, 503, {"error": "GitHub public read rate limit reached"})
        else:
            _send_json(handler, 500, {"error": f"GitHub API error: {error.code}"})
    except Exception as error:
        _send_json(handler, 500, {"error": str(error)})


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        _handle_get(self)
