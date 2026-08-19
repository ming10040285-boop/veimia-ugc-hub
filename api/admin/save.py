"""Admin Save API - writes campaign config to GitHub repository.

POST /api/admin/save
Body: { "path": "public/config/campaigns/demo.json", "content": {...} }

This endpoint uses GitHub API to update files in the repository.
After saving, the raw file is immediately available at:
  https://raw.githubusercontent.com/ming10040285-boop/veimia-ugc-hub/main/{path}

Vercel also auto-redeploys on push, so static file serving updates within ~60s.
"""

from http.server import BaseHTTPRequestHandler
from datetime import datetime, timezone
import json
import os
import base64
import re
from urllib.request import Request, urlopen
from urllib.error import HTTPError

GITHUB_OWNER = "ming10040285-boop"
GITHUB_REPO = "veimia-ugc-hub"
GITHUB_BRANCH = "main"
GITHUB_REPO_API = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}"
GITHUB_API_BASE = f"{GITHUB_REPO_API}/contents"
CAMPAIGN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")


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


def _github_request(api_path, token, method="GET", payload=None):
    """Call a GitHub repository API endpoint and decode its JSON response."""
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(f"{GITHUB_REPO_API}{api_path}", data=data, method=method)
    request.add_header("Authorization", f"Bearer {token}")
    request.add_header("Accept", "application/vnd.github+json")
    request.add_header("Content-Type", "application/json")
    request.add_header("User-Agent", "veimia-ugc-admin")
    with urlopen(request, timeout=12) as response:
        raw = response.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def _publish_campaign_atomic(campaign_input, token):
    """Publish a Campaign and switch current.json in one Git commit."""
    if not isinstance(campaign_input, dict):
        raise ValueError("缺少完整的 Campaign 数据")
    campaign_id = str(campaign_input.get("campaign_id") or "").strip()
    if not CAMPAIGN_ID_PATTERN.fullmatch(campaign_id):
        raise ValueError("Campaign ID 无效")
    products = campaign_input.get("products")
    if not isinstance(products, list) or not products:
        raise ValueError("请至少分配 1 个商品")

    campaign = dict(campaign_input)
    campaign["campaign_id"] = campaign_id
    campaign["status"] = "published"
    campaign["updated_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    campaign_content = json.dumps(campaign, ensure_ascii=False, indent=2) + "\n"
    current_content = json.dumps({"campaign_id": campaign_id}, ensure_ascii=False, indent=2) + "\n"

    branch_ref = _github_request(f"/git/ref/heads/{GITHUB_BRANCH}", token)
    parent_sha = branch_ref["object"]["sha"]
    parent_commit = _github_request(f"/git/commits/{parent_sha}", token)
    base_tree_sha = parent_commit["tree"]["sha"]

    campaign_blob = _github_request("/git/blobs", token, "POST", {
        "content": campaign_content, "encoding": "utf-8"
    })
    current_blob = _github_request("/git/blobs", token, "POST", {
        "content": current_content, "encoding": "utf-8"
    })
    tree = _github_request("/git/trees", token, "POST", {
        "base_tree": base_tree_sha,
        "tree": [
            {
                "path": f"public/config/campaigns/{campaign_id}.json",
                "mode": "100644", "type": "blob", "sha": campaign_blob["sha"],
            },
            {
                "path": "public/config/current.json",
                "mode": "100644", "type": "blob", "sha": current_blob["sha"],
            },
        ],
    })
    commit = _github_request("/git/commits", token, "POST", {
        "message": f"Admin: publish {campaign_id}",
        "tree": tree["sha"],
        "parents": [parent_sha],
    })
    _github_request(f"/git/refs/heads/{GITHUB_BRANCH}", token, "PATCH", {
        "sha": commit["sha"], "force": False
    })
    return campaign, commit["sha"]


def _github_error_message(error):
    if error.code == 401:
        return "GitHub 写入凭证无效，请在 Vercel 项目 veimia-ugc 更新 GITHUB_TOKEN。"
    if error.code == 403:
        return "GitHub 写入权限不足或 API 限流，请检查 GITHUB_TOKEN 的 Contents 写权限。"
    if error.code == 422:
        return "发布时仓库内容发生变化，请重新点击发布。"
    return f"GitHub API error: {error.code}"


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
        
        action = str(body.get("action") or "").strip()
        if action == "publish":
            try:
                campaign, commit_sha = _publish_campaign_atomic(body.get("campaign"), token)
                self._send(200, {
                    "status": "success",
                    "message": "活动已发布并设为当前活动。",
                    "data": {"campaign": campaign, "commit_sha": commit_sha},
                })
            except ValueError as error:
                self._send(400, {"status": "error", "message": str(error)})
            except HTTPError as error:
                self._send(502, {"status": "error", "message": _github_error_message(error)})
            except Exception:
                self._send(500, {"status": "error", "message": "发布失败，请稍后重试。"})
            return
        if action:
            self._send(400, {"status": "error", "message": "Unsupported save action"})
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
            self._send(502, {"status": "error", "message": _github_error_message(e)})
        except Exception:
            self._send(500, {"status": "error", "message": "GitHub 保存失败，请稍后重试。"})
    
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
