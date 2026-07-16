"""Product Library CRUD API endpoint.

Handles POST (add), GET (list/single), PUT (update) operations
for the product library stored in /public/config/products/library.json.

Uses GitHub API for persistent storage (Vercel filesystem is ephemeral).
"""

import json
import os
import uuid
import base64
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs


GITHUB_OWNER = "ming10040285-boop"
GITHUB_REPO = "veimia-ugc-hub"
GITHUB_BRANCH = "main"
LIBRARY_FILE_PATH = "public/config/products/library.json"


def _get_token():
    return os.environ.get("GITHUB_TOKEN", "")


def _read_library():
    """Read library.json from GitHub repository."""
    token = _get_token()
    if not token:
        raise Exception("GITHUB_TOKEN not configured")

    api_url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{LIBRARY_FILE_PATH}?ref={GITHUB_BRANCH}"
    req = urllib.request.Request(api_url)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github.v3+json")
    req.add_header("User-Agent", "veimia-ugc-hub")

    with urllib.request.urlopen(req, timeout=8) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        content_b64 = data.get("content", "").replace("\n", "")
        content_bytes = base64.b64decode(content_b64)
        return json.loads(content_bytes.decode("utf-8"))


def _write_library(data):
    """Write library.json to GitHub repository via Contents API."""
    token = _get_token()
    if not token:
        raise Exception("GITHUB_TOKEN not configured")

    api_url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{LIBRARY_FILE_PATH}"

    # Get current file SHA (needed for updates)
    sha = None
    try:
        get_req = urllib.request.Request(f"{api_url}?ref={GITHUB_BRANCH}")
        get_req.add_header("Authorization", f"Bearer {token}")
        get_req.add_header("Accept", "application/vnd.github.v3+json")
        get_req.add_header("User-Agent", "veimia-ugc-hub")
        with urllib.request.urlopen(get_req, timeout=8) as resp:
            file_data = json.loads(resp.read().decode("utf-8"))
            sha = file_data.get("sha")
    except urllib.error.HTTPError:
        pass  # File doesn't exist yet, will create

    # Write file
    content_str = json.dumps(data, ensure_ascii=False, indent=2)
    content_b64 = base64.b64encode(content_str.encode("utf-8")).decode("ascii")

    payload = {
        "message": "Admin: update library.json",
        "content": content_b64,
        "branch": GITHUB_BRANCH
    }
    if sha:
        payload["sha"] = sha

    put_req = urllib.request.Request(api_url, data=json.dumps(payload).encode("utf-8"), method="PUT")
    put_req.add_header("Authorization", f"Bearer {token}")
    put_req.add_header("Accept", "application/vnd.github.v3+json")
    put_req.add_header("Content-Type", "application/json")
    put_req.add_header("User-Agent", "veimia-ugc-hub")

    urllib.request.urlopen(put_req, timeout=10)


def _validate_url(url, required=False):
    """Validate a URL field.

    Returns True if valid, False if invalid.
    - If required=True and url is None/empty, returns False.
    - If required=False and url is None, returns True (optional field).
    - Must start with http:// or https:// and be <= 2048 chars.
    """
    if url is None:
        return not required
    if not isinstance(url, str):
        return False
    if url == '':
        return not required
    if len(url) > 2048:
        return False
    if not (url.startswith('http://') or url.startswith('https://')):
        return False
    return True


def _validate_product_data(data, is_update=False):
    """Validate product data fields.

    Returns (is_valid, error_response) tuple.
    error_response is None if valid, otherwise a dict with status/code/message.
    """
    # For updates, only validate fields that are present
    if not is_update:
        # Required fields check for creation
        required_fields = ['product_name', 'product_image_url', 'short_description',
                           'available_sizes', 'available_colors']
        for field in required_fields:
            if field not in data or data[field] is None:
                return False, {
                    'status': 'error',
                    'code': 'VALIDATION_ERROR',
                    'message': f'필수 필드가 누락되었습니다: {field}'
                }

    # Validate product_name
    if 'product_name' in data:
        name = data['product_name']
        if not isinstance(name, str) or len(name) == 0 or len(name) > 200:
            return False, {
                'status': 'error',
                'code': 'VALIDATION_ERROR',
                'message': '제품명은 1~200자까지 입력 가능합니다.'
            }

    # Validate short_description
    if 'short_description' in data:
        desc = data['short_description']
        if not isinstance(desc, str) or len(desc) == 0 or len(desc) > 500:
            return False, {
                'status': 'error',
                'code': 'VALIDATION_ERROR',
                'message': '제품 설명은 1~500자까지 입력 가능합니다.'
            }

    # Validate URL fields
    if 'product_image_url' in data:
        if not _validate_url(data['product_image_url'], required=not is_update):
            return False, {
                'status': 'error',
                'code': 'INVALID_URL',
                'message': 'URL 형식이 올바르지 않습니다.'
            }

    if 'product_detail_url' in data:
        if not _validate_url(data['product_detail_url'], required=False):
            return False, {
                'status': 'error',
                'code': 'INVALID_URL',
                'message': 'URL 형식이 올바르지 않습니다.'
            }

    if 'size_guide_url' in data:
        if not _validate_url(data['size_guide_url'], required=False):
            return False, {
                'status': 'error',
                'code': 'INVALID_URL',
                'message': 'URL 형식이 올바르지 않습니다.'
            }

    # Validate available_sizes
    if 'available_sizes' in data:
        sizes = data['available_sizes']
        if not isinstance(sizes, list) or len(sizes) < 1 or len(sizes) > 20:
            return False, {
                'status': 'error',
                'code': 'SIZE_LIMIT',
                'message': '사이즈는 1~20개까지 설정 가능합니다.'
            }
        for size in sizes:
            if not isinstance(size, str) or len(size.strip()) == 0:
                return False, {
                    'status': 'error',
                    'code': 'VALIDATION_ERROR',
                    'message': '사이즈 항목은 비어있을 수 없습니다.'
                }

    # Validate available_colors
    if 'available_colors' in data:
        colors = data['available_colors']
        if not isinstance(colors, list) or len(colors) < 1 or len(colors) > 30:
            return False, {
                'status': 'error',
                'code': 'COLOR_LIMIT',
                'message': '컬러는 1~30개까지 설정 가능합니다.'
            }
        for color in colors:
            if not isinstance(color, str) or len(color.strip()) == 0:
                return False, {
                    'status': 'error',
                    'code': 'VALIDATION_ERROR',
                    'message': '컬러 항목은 비어있을 수 없습니다.'
                }

    return True, None


def _send_json(handler, status_code, data):
    """Send a JSON response."""
    body = json.dumps(data, ensure_ascii=False).encode('utf-8')
    handler.send_response(status_code)
    handler.send_header('Content-Type', 'application/json; charset=utf-8')
    handler.send_header('Content-Length', str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _handle_get(handler):
    """Handle GET request - list all products or get single product by ID."""
    parsed = urlparse(handler.path)
    params = parse_qs(parsed.query)

    library = _read_library()
    products = library.get('products', [])

    # If product_id query param provided, return single product
    product_id = params.get('product_id', [None])[0]
    if product_id:
        for product in products:
            if product.get('product_id') == product_id:
                _send_json(handler, 200, {'status': 'success', 'data': product})
                return
        _send_json(handler, 404, {
            'status': 'error',
            'code': 'NOT_FOUND',
            'message': '제품을 찾을 수 없습니다.'
        })
        return

    # Return all products
    _send_json(handler, 200, {'status': 'success', 'data': products})


def _handle_post(handler):
    """Handle POST request - add a new product to the library."""
    content_length = int(handler.headers.get('Content-Length', 0))
    if content_length == 0:
        _send_json(handler, 400, {
            'status': 'error',
            'code': 'VALIDATION_ERROR',
            'message': '요청 본문이 비어있습니다.'
        })
        return

    body = handler.rfile.read(content_length)
    try:
        data = json.loads(body.decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError):
        _send_json(handler, 400, {
            'status': 'error',
            'code': 'VALIDATION_ERROR',
            'message': '잘못된 JSON 형식입니다.'
        })
        return

    # Validate product data
    is_valid, error = _validate_product_data(data, is_update=False)
    if not is_valid:
        _send_json(handler, 400, error)
        return

    # Generate unique product_id
    product_id = f"prod_{uuid.uuid4().hex[:12]}"

    # Build product record
    product = {
        'product_id': product_id,
        'product_name': data['product_name'],
        'product_image_url': data['product_image_url'],
        'product_detail_url': data.get('product_detail_url', None),
        'size_guide_url': data.get('size_guide_url', None),
        'short_description': data['short_description'],
        'available_sizes': data['available_sizes'],
        'available_colors': data['available_colors']
    }

    # Read library, append product, write back
    library = _read_library()
    library['products'].append(product)
    _write_library(library)

    _send_json(handler, 201, {'status': 'success', 'data': product})


def _handle_put(handler):
    """Handle PUT request - update an existing product."""
    content_length = int(handler.headers.get('Content-Length', 0))
    if content_length == 0:
        _send_json(handler, 400, {
            'status': 'error',
            'code': 'VALIDATION_ERROR',
            'message': '요청 본문이 비어있습니다.'
        })
        return

    body = handler.rfile.read(content_length)
    try:
        data = json.loads(body.decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError):
        _send_json(handler, 400, {
            'status': 'error',
            'code': 'VALIDATION_ERROR',
            'message': '잘못된 JSON 형식입니다.'
        })
        return

    # product_id is required for update
    product_id = data.get('product_id')
    if not product_id:
        _send_json(handler, 400, {
            'status': 'error',
            'code': 'VALIDATION_ERROR',
            'message': '제품 ID가 필요합니다.'
        })
        return

    # Validate provided fields (update mode)
    is_valid, error = _validate_product_data(data, is_update=True)
    if not is_valid:
        _send_json(handler, 400, error)
        return

    # Find and update the product
    library = _read_library()
    products = library.get('products', [])
    product_index = None
    for i, product in enumerate(products):
        if product.get('product_id') == product_id:
            product_index = i
            break

    if product_index is None:
        _send_json(handler, 404, {
            'status': 'error',
            'code': 'NOT_FOUND',
            'message': '제품을 찾을 수 없습니다.'
        })
        return

    # Update only provided fields
    updatable_fields = [
        'product_name', 'product_image_url', 'product_detail_url',
        'size_guide_url', 'short_description', 'available_sizes', 'available_colors'
    ]
    for field in updatable_fields:
        if field in data:
            products[product_index][field] = data[field]

    library['products'] = products
    _write_library(library)

    _send_json(handler, 200, {'status': 'success', 'data': products[product_index]})


class handler(BaseHTTPRequestHandler):
    """Vercel serverless function handler for product library CRUD."""

    def do_GET(self):
        """Handle GET requests."""
        _handle_get(self)

    def do_POST(self):
        """Handle POST requests."""
        _handle_post(self)

    def do_PUT(self):
        """Handle PUT requests."""
        _handle_put(self)

    def do_OPTIONS(self):
        """Handle CORS preflight requests."""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
