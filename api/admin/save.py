"""Admin Save API - writes campaign config to GitHub repository.

POST /api/admin/save
Body: { "path": "public/config/campaigns/demo.json", "content": {...} }

This endpoint uses GitHub API to update files in the repository.
After saving, the raw file is immediately available at:
  https://raw.githubusercontent.com/ming10040285-boop/veimia-ugc-hub/main/{path}

Vercel also auto-redeploys on push, so static file serving updates within ~60s.
"""

from http.server import BaseHTTPRequestHandler
import json
import os
import base64
from urllib.request import Request, urlopen
from urllib.error import HTTPError

GITHUB_OWNER = "ming10040285-boop"
GITHUB_REPO = "veimia-ugc-hub"
GITHUB_BRANCH = "main"
GITHUB_API_BASE = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents"


def _get_token():
    return os.environ.get("GITHUB_TOKEN", "")


def _get_file_sha(path, token):
    """Get the SHA of an existing file (needed for updates)."""
    url = f"{GITHUB_API_BASE}/{path}?ref={GITHUB_BRANCH}"
    req = Request(url)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github.v3+json")
    try:
        with urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("sha", "")
    except HTTPError:
        return ""


def _write_to_github(path, content_dict, token):
    """Write JSON content to a file in GitHub repo."""
    url = f"{GITHUB_API_BASE}/{path}"
    
    content_str = json.dumps(content_dict, ensure_ascii=False, indent=2)
    content_b64 = base64.b64encode(content_str.encode("utf-8")).decode("utf-8")
    
    sha = _get_file_sha(path, token)
    
    payload = {
        "message": "Admin: update " + path.split("/")[-1],
        "content": content_b64,
        "branch": GITHUB_BRANCH
    }
    if sha:
        payload["sha"] = sha
    
    req = Request(url, data=json.dumps(payload).encode("utf-8"), method="PUT")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github.v3+json")
    req.add_header("Content-Type", "application/json")
    
    with urlopen(req, timeout=9) as resp:
        return resp.status in (200, 201)


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        token = _get_token()
        if not token:
            self._send(500, {"status": "error", "message": "GITHUB_TOKEN not configured"})
            return
        
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(content_length))
        except (json.JSONDecodeError, ValueError):
            self._send(400, {"status": "error", "message": "Invalid JSON body"})
            return
        
        path = body.get("path", "")
        content = body.get("content")
        
        if not path or content is None:
            self._send(400, {"status": "error", "message": "path and content required"})
            return
        
        # Security: only allow writing to public/config/
        if not path.startswith("public/config/"):
            self._send(403, {"status": "error", "message": "Can only write to public/config/"})
            return
        
        try:
            success = _write_to_github(path, content, token)
            if success:
                self._send(200, {"status": "success", "message": "Saved successfully"})
            else:
                self._send(500, {"status": "error", "message": "GitHub API write failed"})
        except HTTPError as e:
            self._send(500, {"status": "error", "message": f"GitHub API error: {e.code}"})
        except Exception as e:
            self._send(500, {"status": "error", "message": str(e)})
    
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
    
    def _send(self, status, data):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))
