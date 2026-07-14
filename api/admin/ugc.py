"""UGC Gallery Management API endpoint for VEIMIA UGC Hub Admin.

Handles add (POST), reorder (PUT), and remove (DELETE) operations for UGC posts.
Accepts Instagram post URLs or manual image upload (JPEG, PNG, WebP; max 5 MB).
Validates Instagram URL format and enforces maximum 20 posts per campaign.
Stores UGC data in campaign config JSON with display_order.

Endpoints (via query params):
- POST ?campaign_id=xxx&action=add     — Add a new UGC post
- PUT  ?campaign_id=xxx&action=reorder — Reorder posts
- DELETE ?campaign_id=xxx&action=remove — Remove a post

Timeout: Vercel enforces a 10s maximum execution time via vercel.json maxDuration.
         This endpoint performs local file I/O only — timeout risk is minimal.

Requirements: 9.2, 9.4
"""

from http.server import BaseHTTPRequestHandler
import json
import os
import re
import uuid
import base64
from urllib.parse import urlparse, parse_qs

# Resolve campaigns directory relative to this file
CAMPAIGNS_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", "public", "config", "campaigns"
)
CAMPAIGNS_DIR = os.path.normpath(CAMPAIGNS_DIR)

# UGC gallery constraints
MAX_UGC_POSTS = 20
MAX_IMAGE_URL_LENGTH = 2048
MAX_IMAGE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB
ALLOWED_IMAGE_FORMATS = ("image/jpeg", "image/png", "image/webp")
ALLOWED_IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")

# Instagram URL validation pattern
# Must start with https://www.instagram.com/p/ or https://instagram.com/p/
INSTAGRAM_URL_PATTERN = re.compile(
    r"^https://(www\.)?instagram\.com/p/[A-Za-z0-9_-]+/?(\?.*)?$"
)


def _json_response(handler, status_code, body):
    """Send a JSON response with the given status code and body dict."""
    handler.send_response(status_code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.end_headers()
    handler.wfile.write(json.dumps(body, ensure_ascii=False).encode("utf-8"))


def _error_response(handler, status_code, code, message):
    """Send a standardized error response."""
    _json_response(handler, status_code, {
        "status": "error",
        "code": code,
        "message": message
    })


def _read_body(handler):
    """Read and parse JSON body from request."""
    content_length = int(handler.headers.get("Content-Length", 0))
    if content_length == 0:
        return None
    raw = handler.rfile.read(content_length)
    return json.loads(raw.decode("utf-8"))


def _get_campaign_path(campaign_id):
    """Get the file path for a campaign JSON file."""
    return os.path.join(CAMPAIGNS_DIR, f"{campaign_id}.json")


def _load_campaign(campaign_id):
    """Load a campaign from its JSON file. Returns None if not found."""
    path = _get_campaign_path(campaign_id)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_campaign(campaign):
    """Persist a campaign dict to its JSON file."""
    os.makedirs(CAMPAIGNS_DIR, exist_ok=True)
    path = _get_campaign_path(campaign["campaign_id"])
    with open(path, "w", encoding="utf-8") as f:
        json.dump(campaign, f, ensure_ascii=False, indent=2)


def _validate_instagram_url(url):
    """Validate that a URL matches Instagram post URL format.

    Must match https://www.instagram.com/p/... or https://instagram.com/p/...
    Returns True if valid, False otherwise.
    """
    if not url:
        return True  # source_url is optional
    return bool(INSTAGRAM_URL_PATTERN.match(url))


def _validate_image_url(url):
    """Validate that image_url is a valid http/https URL within length limit."""
    if not url:
        return False
    if len(url) > MAX_IMAGE_URL_LENGTH:
        return False
    try:
        parsed = urlparse(url)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False


def _validate_image_data(image_data):
    """Validate base64-encoded image data.

    Checks that the data can be decoded and is within the 5 MB size limit.
    Returns (is_valid, decoded_size) tuple.
    """
    if not image_data:
        return False, 0
    try:
        # Handle data URI prefix if present (e.g., "data:image/jpeg;base64,...")
        if "," in image_data and image_data.startswith("data:"):
            header, image_data = image_data.split(",", 1)
            # Validate content type from header
            content_type = header.split(";")[0].replace("data:", "")
            if content_type not in ALLOWED_IMAGE_FORMATS:
                return False, 0

        decoded = base64.b64decode(image_data)
        size = len(decoded)
        if size > MAX_IMAGE_SIZE_BYTES:
            return False, size
        if size == 0:
            return False, 0
        return True, size
    except Exception:
        return False, 0


def _get_next_display_order(ugc_gallery):
    """Get the next display_order value for a new UGC post."""
    if not ugc_gallery:
        return 1
    max_order = max(post.get("display_order", 0) for post in ugc_gallery)
    return max_order + 1


def _get_query_params(handler):
    """Extract query parameters from the request path."""
    parsed = urlparse(handler.path)
    return parse_qs(parsed.query)


def _handle_add(handler, campaign_id):
    """Handle action=add — Add a UGC post to a campaign.

    Body options:
    1. {"source_url": "https://www.instagram.com/p/...", "image_url": "https://..."}
    2. {"image_data": "base64...", "source_url": "..." (optional)}
    """
    body = _read_body(handler)
    if not body:
        _error_response(handler, 400, "VALIDATION_ERROR", "Request body is required")
        return

    # Load campaign
    campaign = _load_campaign(campaign_id)
    if not campaign:
        _error_response(handler, 404, "NOT_FOUND", "캠페인을 찾을 수 없습니다.")
        return

    # Get current gallery
    ugc_gallery = campaign.get("ugc_gallery", [])

    # Enforce maximum 20 posts
    if len(ugc_gallery) >= MAX_UGC_POSTS:
        _error_response(handler, 400, "GALLERY_LIMIT",
                        "UGC 갤러리는 최대 20개까지 등록 가능합니다.")
        return

    # Validate source_url (Instagram URL) if provided
    source_url = body.get("source_url")
    if source_url and not _validate_instagram_url(source_url):
        _error_response(handler, 400, "INVALID_URL",
                        "Instagram URL을 확인할 수 없습니다.")
        return

    # Determine image_url: either from direct URL or from base64 upload
    image_url = body.get("image_url")
    image_data = body.get("image_data")

    if image_url and image_data:
        _error_response(handler, 400, "VALIDATION_ERROR",
                        "Provide either image_url or image_data, not both")
        return

    if image_url:
        # Validate the provided image URL
        if not _validate_image_url(image_url):
            _error_response(handler, 400, "VALIDATION_ERROR",
                            "image_url must be a valid http/https URL (max 2048 characters)")
            return
    elif image_data:
        # Validate base64 image data
        is_valid, size = _validate_image_data(image_data)
        if not is_valid:
            if size > MAX_IMAGE_SIZE_BYTES:
                _error_response(handler, 400, "INVALID_IMAGE",
                                "파일 크기는 5MB 이하여야 합니다.")
            else:
                _error_response(handler, 400, "INVALID_IMAGE",
                                "파일 형식 또는 크기가 올바르지 않습니다.")
            return
        # In production, the image would be uploaded to Vercel Blob or Cloudinary.
        # For now, generate a placeholder CDN URL.
        image_url = f"https://cdn.veimia.com/ugc/uploads/{uuid.uuid4()}.webp"
    else:
        _error_response(handler, 400, "VALIDATION_ERROR",
                        "Either image_url or image_data is required")
        return

    # Create new UGC post
    post_id = str(uuid.uuid4())
    display_order = _get_next_display_order(ugc_gallery)

    new_post = {
        "post_id": post_id,
        "image_url": image_url,
        "source_url": source_url if source_url else None,
        "display_order": display_order
    }

    # Add to gallery and save
    ugc_gallery.append(new_post)
    campaign["ugc_gallery"] = ugc_gallery
    _save_campaign(campaign)

    _json_response(handler, 201, {
        "status": "success",
        "data": new_post
    })


def _handle_reorder(handler, campaign_id):
    """Handle action=reorder — Reorder UGC posts in a campaign.

    Body options:
    1. {"orders": [{"post_id": "id1", "display_order": 1}, ...]} — explicit order pairs
    2. {"post_ids": ["id1", "id2", ...]} — new order by array position (legacy)

    Updates display_order for each post.
    """
    body = _read_body(handler)
    if not body:
        _error_response(handler, 400, "VALIDATION_ERROR", "Request body is required")
        return

    # Load campaign
    campaign = _load_campaign(campaign_id)
    if not campaign:
        _error_response(handler, 404, "NOT_FOUND", "캠페인을 찾을 수 없습니다.")
        return

    ugc_gallery = campaign.get("ugc_gallery", [])

    # Build a map of existing posts by post_id
    existing_posts = {post["post_id"]: post for post in ugc_gallery}

    # Support both formats: explicit order pairs or ordered ID list
    orders = body.get("orders")
    post_ids = body.get("post_ids")

    if orders and isinstance(orders, list):
        # Format 1: Array of {post_id, display_order} pairs
        for item in orders:
            pid = item.get("post_id")
            display_order = item.get("display_order")
            if not pid or display_order is None:
                _error_response(handler, 400, "VALIDATION_ERROR",
                                "Each order item must have post_id and display_order")
                return
            if pid not in existing_posts:
                _error_response(handler, 404, "NOT_FOUND",
                                f"Post {pid} not found in campaign gallery")
                return
            if not isinstance(display_order, int) or display_order < 1 or display_order > MAX_UGC_POSTS:
                _error_response(handler, 400, "VALIDATION_ERROR",
                                f"display_order must be an integer between 1 and {MAX_UGC_POSTS}")
                return

        # Apply explicit display_order values
        for item in orders:
            existing_posts[item["post_id"]]["display_order"] = item["display_order"]

        # Rebuild gallery sorted by new display_order
        reordered_gallery = sorted(existing_posts.values(), key=lambda p: p["display_order"])

    elif post_ids and isinstance(post_ids, list):
        # Format 2: Ordered list of post IDs (position = display_order)
        for pid in post_ids:
            if pid not in existing_posts:
                _error_response(handler, 404, "NOT_FOUND",
                                f"Post {pid} not found in campaign gallery")
                return

        # Apply new display orders based on position in the array
        reordered_gallery = []
        for i, pid in enumerate(post_ids):
            post = existing_posts[pid]
            post["display_order"] = i + 1
            reordered_gallery.append(post)

        # Include any posts not in the post_ids list (append at the end)
        provided_ids = set(post_ids)
        next_order = len(post_ids) + 1
        for post in ugc_gallery:
            if post["post_id"] not in provided_ids:
                post["display_order"] = next_order
                reordered_gallery.append(post)
                next_order += 1
    else:
        _error_response(handler, 400, "VALIDATION_ERROR",
                        "Either 'orders' array or 'post_ids' array is required")
        return

    campaign["ugc_gallery"] = reordered_gallery
    _save_campaign(campaign)

    _json_response(handler, 200, {
        "status": "success",
        "data": reordered_gallery
    })


def _handle_remove(handler, campaign_id):
    """Handle action=remove — Remove a UGC post from a campaign.

    Body: {"post_id": "xxx"}
    Removes the post and reorders remaining posts to close gaps.
    """
    body = _read_body(handler)
    if not body:
        _error_response(handler, 400, "VALIDATION_ERROR", "Request body is required")
        return

    post_id = body.get("post_id")
    if not post_id:
        _error_response(handler, 400, "VALIDATION_ERROR", "post_id is required")
        return

    # Load campaign
    campaign = _load_campaign(campaign_id)
    if not campaign:
        _error_response(handler, 404, "NOT_FOUND", "캠페인을 찾을 수 없습니다.")
        return

    ugc_gallery = campaign.get("ugc_gallery", [])

    # Find and remove the post
    original_length = len(ugc_gallery)
    ugc_gallery = [post for post in ugc_gallery if post["post_id"] != post_id]

    if len(ugc_gallery) == original_length:
        _error_response(handler, 404, "NOT_FOUND",
                        f"Post {post_id} not found in campaign gallery")
        return

    # Reorder remaining posts to close gaps
    for i, post in enumerate(ugc_gallery):
        post["display_order"] = i + 1

    campaign["ugc_gallery"] = ugc_gallery
    _save_campaign(campaign)

    _json_response(handler, 200, {
        "status": "success",
        "message": "UGC post removed successfully",
        "data": ugc_gallery
    })


class handler(BaseHTTPRequestHandler):
    """Vercel serverless function handler for UGC gallery management.

    Routes based on query params:
    - POST ?campaign_id=xxx&action=add
    - PUT  ?campaign_id=xxx&action=reorder
    - DELETE ?campaign_id=xxx&action=remove
    """

    def do_OPTIONS(self):
        """Handle CORS preflight requests."""
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _get_params(self):
        """Extract campaign_id and action from query parameters."""
        params = _get_query_params(self)
        campaign_id = params.get("campaign_id", [None])[0]
        action = params.get("action", [None])[0]
        return campaign_id, action

    def do_POST(self):
        """Handle POST requests — expects action=add."""
        campaign_id, action = self._get_params()

        if not campaign_id:
            _error_response(self, 400, "VALIDATION_ERROR", "campaign_id query parameter is required")
            return

        if action != "add":
            _error_response(self, 400, "VALIDATION_ERROR",
                            "action query parameter must be 'add' for POST requests")
            return

        _handle_add(self, campaign_id)

    def do_PUT(self):
        """Handle PUT requests — expects action=reorder."""
        campaign_id, action = self._get_params()

        if not campaign_id:
            _error_response(self, 400, "VALIDATION_ERROR", "campaign_id query parameter is required")
            return

        if action != "reorder":
            _error_response(self, 400, "VALIDATION_ERROR",
                            "action query parameter must be 'reorder' for PUT requests")
            return

        _handle_reorder(self, campaign_id)

    def do_DELETE(self):
        """Handle DELETE requests — expects action=remove."""
        campaign_id, action = self._get_params()

        if not campaign_id:
            _error_response(self, 400, "VALIDATION_ERROR", "campaign_id query parameter is required")
            return

        if action != "remove":
            _error_response(self, 400, "VALIDATION_ERROR",
                            "action query parameter must be 'remove' for DELETE requests")
            return

        _handle_remove(self, campaign_id)
