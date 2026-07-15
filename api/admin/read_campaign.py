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

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        _send_json(handler, 500, {"error": "GITHUB_TOKEN not configured"})
        return

    # Read file from GitHub Contents API (no cache)
    path = f"public/config/campaigns/{campaign_id}.json"
    api_url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{path}?ref={GITHUB_BRANCH}"

    req = urllib.request.Request(api_url)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github.v3+json")
    req.add_header("User-Agent", "veimia-ugc-hub")

    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            content_b64 = data.get("content", "")
            content_bytes = base64.b64decode(content_b64)
            campaign = json.loads(content_bytes.decode("utf-8"))
            _send_json(handler, 200, campaign)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            _send_json(handler, 404, {"error": "Campaign not found"})
        else:
            _send_json(handler, 500, {"error": f"GitHub API error: {e.code}"})
    except Exception as e:
        _send_json(handler, 500, {"error": str(e)})


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        _handle_get(self)
