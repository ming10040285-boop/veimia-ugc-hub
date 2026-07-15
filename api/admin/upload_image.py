"""UGC Image upload API endpoint - stores images in GitHub repository.

Accepts POST requests with JSON body containing:
- filename: original filename with extension
- data: Base64-encoded image content

Returns a persistent raw.githubusercontent.com URL for the uploaded image.

This is a self-contained Vercel serverless function.
No imports from other modules in the api/ directory.
"""

from http.server import BaseHTTPRequestHandler
import json
import os
import re
import urllib.error
import urllib.request
import uuid


def _send_json(handler, status_code, body):
    """Send a JSON response with CORS headers."""
    handler.send_response(status_code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.end_headers()
    handler.wfile.write(json.dumps(body, ensure_ascii=False).encode("utf-8"))


def _error_response(handler, status_code, code, message):
    """Send an error response with the standard format."""
    _send_json(handler, status_code, {
        "error": message,
        "code": code
    })


def _is_valid_base64(data):
    """Check that data contains only valid Base64 characters [A-Za-z0-9+/=]."""
    return bool(re.fullmatch(r'[A-Za-z0-9+/=]+', data))


def _handle_post(handler):
    """Handle POST request for image upload."""
    # Read request body
    content_length = int(handler.headers.get("Content-Length", 0))
    if content_length == 0:
        _error_response(handler, 400, "INVALID_REQUEST",
                        "Required fields missing: filename and data are required")
        return

    try:
        raw_body = handler.rfile.read(content_length)
        body = json.loads(raw_body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        _error_response(handler, 400, "INVALID_REQUEST",
                        "Required fields missing: filename and data are required")
        return

    # Validate presence of required fields
    filename = body.get("filename")
    data = body.get("data")

    if not filename or not data:
        _error_response(handler, 400, "INVALID_REQUEST",
                        "Required fields missing: filename and data are required")
        return

    # Validate Base64 content
    if not _is_valid_base64(data):
        _error_response(handler, 400, "INVALID_REQUEST",
                        "Invalid Base64 encoding in data field")
        return

    # Extension validation
    ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
    if "." not in filename:
        _error_response(handler, 400, "INVALID_FORMAT",
                        "Unsupported format. Accepted: PNG, JPEG, WebP")
        return

    extension = filename.rsplit(".", 1)[-1].lower()
    if extension not in ALLOWED_EXTENSIONS:
        _error_response(handler, 400, "INVALID_FORMAT",
                        "Unsupported format. Accepted: PNG, JPEG, WebP")
        return

    # Generate UUID v4 filename
    generated_filename = f"{uuid.uuid4()}.{extension}"

    # GitHub API integration
    github_token = os.environ.get("GITHUB_TOKEN")
    if not github_token:
        _error_response(handler, 500, "TOKEN_NOT_CONFIGURED",
                        "Server configuration error: GitHub token not configured")
        return

    # GitHub Contents API request
    repo_path = f"public/uploads/ugc/{generated_filename}"
    api_url = f"https://api.github.com/repos/ming10040285-boop/veimia-ugc-hub/contents/{repo_path}"

    request_body = json.dumps({
        "message": f"Upload UGC image: {generated_filename}",
        "content": data,
        "branch": "main"
    }).encode("utf-8")

    req = urllib.request.Request(api_url, data=request_body, method="PUT")
    req.add_header("Authorization", f"Bearer {github_token}")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/vnd.github.v3+json")
    req.add_header("User-Agent", "veimia-ugc-upload")

    try:
        with urllib.request.urlopen(req) as response:
            response.read()  # Consume response body
        image_url = f"https://raw.githubusercontent.com/ming10040285-boop/veimia-ugc-hub/main/{repo_path}"
        _send_json(handler, 200, {"image_url": image_url})
    except urllib.error.HTTPError as e:
        error_body = ""
        try:
            error_body = e.read().decode("utf-8")
            error_detail = json.loads(error_body).get("message", error_body)
        except Exception:
            error_detail = error_body or str(e)
        _error_response(handler, 500, "GITHUB_API_ERROR",
                        f"Failed to upload image: {error_detail}")
    except urllib.error.URLError as e:
        _error_response(handler, 500, "GITHUB_API_ERROR",
                        f"Failed to upload image: {e.reason}")


class handler(BaseHTTPRequestHandler):
    """Vercel serverless function handler for UGC image upload to GitHub."""

    def do_OPTIONS(self):
        """Handle CORS preflight requests."""
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self):
        """Handle POST requests for image upload."""
        _handle_post(self)
