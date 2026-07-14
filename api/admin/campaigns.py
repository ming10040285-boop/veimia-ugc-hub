"""Campaign CRUD API endpoint for VEIMIA UGC Hub Admin.

Handles POST (create), GET (list/detail), PUT (update), DELETE operations.
Persists campaign config to /public/config/campaigns/{campaign_id}.json.

Timeout: Vercel enforces a 10s maximum execution time via vercel.json maxDuration.
         This endpoint performs local file I/O only — timeout risk is minimal.
"""

from http.server import BaseHTTPRequestHandler
import json
import os
import uuid
from datetime import datetime, timezone
from urllib.parse import urlparse, parse_qs

# Resolve campaigns directory relative to this file
CAMPAIGNS_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", "public", "config", "campaigns"
)
CAMPAIGNS_DIR = os.path.normpath(CAMPAIGNS_DIR)

VALID_PRODUCT_MODES = ("single", "multiple")
VALID_MARKETS = ("ko", "ja", "en")
VALID_STATUSES = ("draft", "published")

MAX_CAMPAIGN_NAME_LENGTH = 200
MAX_HERO_IMAGE_URL_LENGTH = 2048
MAX_INTRODUCTION_TEXT_LENGTH = 2000


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


def _list_campaigns():
    """List all campaigns from the campaigns directory."""
    campaigns = []
    if not os.path.exists(CAMPAIGNS_DIR):
        return campaigns
    for filename in os.listdir(CAMPAIGNS_DIR):
        if filename.endswith(".json") and not filename.startswith("."):
            filepath = os.path.join(CAMPAIGNS_DIR, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # Skip schema documentation files
                    if "campaign_id" in data:
                        campaigns.append(data)
            except (json.JSONDecodeError, IOError):
                continue
    # Sort by created_at descending
    campaigns.sort(key=lambda c: c.get("created_at", ""), reverse=True)
    return campaigns


def _validate_url(url):
    """Validate URL is http/https or base64 data URL, within length limit."""
    if not url:
        return True  # Optional field
    # Allow Base64 data URLs (from local image upload)
    if url.startswith("data:image/"):
        return True
    if len(url) > MAX_HERO_IMAGE_URL_LENGTH:
        return False
    try:
        parsed = urlparse(url)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False


def _now_iso():
    """Return current UTC timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _handle_post(handler):
    """Handle POST - Create a new campaign."""
    body = _read_body(handler)
    if not body:
        _error_response(handler, 400, "VALIDATION_ERROR", "Request body is required")
        return

    # Validate required field: product_mode
    product_mode = body.get("product_mode")
    if not product_mode:
        _error_response(handler, 400, "VALIDATION_ERROR", "product_mode is required")
        return
    if product_mode not in VALID_PRODUCT_MODES:
        _error_response(handler, 400, "VALIDATION_ERROR",
                        f"product_mode must be one of: {', '.join(VALID_PRODUCT_MODES)}")
        return

    # Validate optional fields
    campaign_name = body.get("campaign_name", "")
    if len(campaign_name) > MAX_CAMPAIGN_NAME_LENGTH:
        _error_response(handler, 400, "VALIDATION_ERROR",
                        f"campaign_name must be {MAX_CAMPAIGN_NAME_LENGTH} characters or less")
        return

    market = body.get("market", "ko")
    if market not in VALID_MARKETS:
        _error_response(handler, 400, "VALIDATION_ERROR",
                        f"market must be one of: {', '.join(VALID_MARKETS)}")
        return

    hero_image_url = body.get("hero_image_url", "")
    if hero_image_url and not _validate_url(hero_image_url):
        _error_response(handler, 400, "VALIDATION_ERROR",
                        "hero_image_url must be a valid http/https URL (max 2048 characters)")
        return

    introduction_text = body.get("introduction_text", "")
    if len(introduction_text) > MAX_INTRODUCTION_TEXT_LENGTH:
        _error_response(handler, 400, "VALIDATION_ERROR",
                        f"introduction_text must be {MAX_INTRODUCTION_TEXT_LENGTH} characters or less")
        return

    # Create campaign
    now = _now_iso()
    campaign = {
        "campaign_id": str(uuid.uuid4()),
        "campaign_name": campaign_name,
        "product_mode": product_mode,
        "market": market,
        "hero_image_url": hero_image_url,
        "introduction_text": introduction_text,
        "status": "draft",
        "created_at": now,
        "updated_at": now,
        "products": [],
        "ugc_gallery": []
    }

    _save_campaign(campaign)
    _json_response(handler, 201, {"status": "success", "data": campaign})


def _handle_get(handler):
    """Handle GET - List all campaigns or get a single campaign by ID."""
    parsed = urlparse(handler.path)
    params = parse_qs(parsed.query)

    campaign_id = params.get("campaign_id", [None])[0]

    if campaign_id:
        # Get single campaign
        campaign = _load_campaign(campaign_id)
        if not campaign:
            _error_response(handler, 404, "NOT_FOUND", "Campaign not found")
            return
        _json_response(handler, 200, {"status": "success", "data": campaign})
    else:
        # List all campaigns
        campaigns = _list_campaigns()
        _json_response(handler, 200, {"status": "success", "data": campaigns})


def _handle_put(handler):
    """Handle PUT - Update an existing campaign."""
    body = _read_body(handler)
    if not body:
        _error_response(handler, 400, "VALIDATION_ERROR", "Request body is required")
        return

    campaign_id = body.get("campaign_id")
    if not campaign_id:
        # Try query param
        parsed = urlparse(handler.path)
        params = parse_qs(parsed.query)
        campaign_id = params.get("campaign_id", [None])[0]

    if not campaign_id:
        _error_response(handler, 400, "VALIDATION_ERROR", "campaign_id is required")
        return

    campaign = _load_campaign(campaign_id)
    if not campaign:
        _error_response(handler, 404, "NOT_FOUND", "Campaign not found")
        return

    # Check if status is being changed to "published"
    new_status = body.get("status")
    if new_status == "published" and campaign.get("status") != "published":
        # Prevent publishing with no products
        products = body.get("products", campaign.get("products", []))
        if not products:
            _error_response(handler, 400, "NO_PRODUCTS",
                            "최소 1개의 상품을 등록해 주세요.")
            return

    # Validate updatable fields
    if "campaign_name" in body:
        if len(body["campaign_name"]) > MAX_CAMPAIGN_NAME_LENGTH:
            _error_response(handler, 400, "VALIDATION_ERROR",
                            f"campaign_name must be {MAX_CAMPAIGN_NAME_LENGTH} characters or less")
            return
        campaign["campaign_name"] = body["campaign_name"]

    if "product_mode" in body:
        if body["product_mode"] not in VALID_PRODUCT_MODES:
            _error_response(handler, 400, "VALIDATION_ERROR",
                            f"product_mode must be one of: {', '.join(VALID_PRODUCT_MODES)}")
            return
        campaign["product_mode"] = body["product_mode"]

    if "market" in body:
        if body["market"] not in VALID_MARKETS:
            _error_response(handler, 400, "VALIDATION_ERROR",
                            f"market must be one of: {', '.join(VALID_MARKETS)}")
            return
        campaign["market"] = body["market"]

    if "hero_image_url" in body:
        if body["hero_image_url"] and not _validate_url(body["hero_image_url"]):
            _error_response(handler, 400, "VALIDATION_ERROR",
                            "hero_image_url must be a valid http/https URL (max 2048 characters)")
            return
        campaign["hero_image_url"] = body["hero_image_url"]

    if "introduction_text" in body:
        if len(body["introduction_text"]) > MAX_INTRODUCTION_TEXT_LENGTH:
            _error_response(handler, 400, "VALIDATION_ERROR",
                            f"introduction_text must be {MAX_INTRODUCTION_TEXT_LENGTH} characters or less")
            return
        campaign["introduction_text"] = body["introduction_text"]

    if "status" in body:
        if body["status"] not in VALID_STATUSES:
            _error_response(handler, 400, "VALIDATION_ERROR",
                            f"status must be one of: {', '.join(VALID_STATUSES)}")
            return
        campaign["status"] = body["status"]

    if "products" in body:
        campaign["products"] = body["products"]

    if "ugc_gallery" in body:
        campaign["ugc_gallery"] = body["ugc_gallery"]

    campaign["updated_at"] = _now_iso()
    _save_campaign(campaign)
    _json_response(handler, 200, {"status": "success", "data": campaign})


def _handle_delete(handler):
    """Handle DELETE - Remove a campaign."""
    parsed = urlparse(handler.path)
    params = parse_qs(parsed.query)
    campaign_id = params.get("campaign_id", [None])[0]

    # Also try reading from body
    if not campaign_id:
        body = _read_body(handler)
        if body:
            campaign_id = body.get("campaign_id")

    if not campaign_id:
        _error_response(handler, 400, "VALIDATION_ERROR", "campaign_id is required")
        return

    path = _get_campaign_path(campaign_id)
    if not os.path.exists(path):
        _error_response(handler, 404, "NOT_FOUND", "Campaign not found")
        return

    os.remove(path)
    _json_response(handler, 200, {
        "status": "success",
        "message": "Campaign deleted successfully"
    })


class handler(BaseHTTPRequestHandler):
    """Vercel serverless function handler for campaign CRUD operations."""

    def do_OPTIONS(self):
        """Handle CORS preflight requests."""
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self):
        _handle_post(self)

    def do_GET(self):
        _handle_get(self)

    def do_PUT(self):
        _handle_put(self)

    def do_DELETE(self):
        _handle_delete(self)
