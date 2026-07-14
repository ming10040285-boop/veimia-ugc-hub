"""Campaign Product Assignment API endpoint.

Timeout: Vercel enforces a 10s maximum execution time via vercel.json maxDuration.
         This endpoint performs local file I/O only — timeout risk is minimal.

Handles PUT requests for assigning products to campaigns with override support.
Endpoint: PUT /api/admin/campaign_products?campaign_id=xxx

Validates product_mode constraints:
- "single" mode: exactly 1 product allowed
- "multiple" mode: 1-50 products allowed (PRODUCT_LIMIT)

Supports per-Campaign_Product overrides:
- override_product_image_url
- override_product_detail_url
- override_size_guide_url
- override_short_description

Overrides can be set to null to revert to Product_Library defaults.
"""

import json
import os
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs


# Constants
PRODUCT_LIMIT = 50
MAX_URL_LENGTH = 2048
MAX_SHORT_DESCRIPTION_LENGTH = 500
MIN_DISPLAY_ORDER = 1
MAX_DISPLAY_ORDER = 50
VALID_PRODUCT_STATUSES = ("open", "closed")

# Resolve paths relative to this file
BASE_DIR = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    '..', '..'
))
CAMPAIGNS_DIR = os.path.join(BASE_DIR, 'public', 'config', 'campaigns')
LIBRARY_PATH = os.path.join(BASE_DIR, 'public', 'config', 'products', 'library.json')


def _json_response(handler, status_code, body):
    """Send a JSON response with the given status code and body dict."""
    payload = json.dumps(body, ensure_ascii=False).encode('utf-8')
    handler.send_response(status_code)
    handler.send_header('Content-Type', 'application/json; charset=utf-8')
    handler.send_header('Content-Length', str(len(payload)))
    handler.send_header('Access-Control-Allow-Origin', '*')
    handler.send_header('Access-Control-Allow-Methods', 'PUT, OPTIONS')
    handler.send_header('Access-Control-Allow-Headers', 'Content-Type')
    handler.end_headers()
    handler.wfile.write(payload)


def _error_response(handler, status_code, code, message):
    """Send a standardized error response."""
    _json_response(handler, status_code, {
        'status': 'error',
        'code': code,
        'message': message
    })


def _read_body(handler):
    """Read and parse JSON body from request."""
    content_length = int(handler.headers.get('Content-Length', 0))
    if content_length == 0:
        return None
    raw = handler.rfile.read(content_length)
    try:
        return json.loads(raw.decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


def _now_iso():
    """Return current UTC timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def _load_campaign(campaign_id):
    """Load a campaign from its JSON file. Returns None if not found."""
    path = os.path.join(CAMPAIGNS_DIR, f'{campaign_id}.json')
    if not os.path.exists(path):
        return None
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def _save_campaign(campaign):
    """Persist a campaign dict to its JSON file."""
    os.makedirs(CAMPAIGNS_DIR, exist_ok=True)
    path = os.path.join(CAMPAIGNS_DIR, f"{campaign['campaign_id']}.json")
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(campaign, f, ensure_ascii=False, indent=2)


def _load_product_library():
    """Load the product library. Returns list of products."""
    if not os.path.exists(LIBRARY_PATH):
        return []
    with open(LIBRARY_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data.get('products', [])


def _validate_url(url):
    """Validate URL is http/https and within length limit.

    Returns True if valid. None values are treated as "clear override" and are valid.
    """
    if url is None:
        return True
    if not isinstance(url, str):
        return False
    if url == '':
        return True  # empty string treated as no override
    if len(url) > MAX_URL_LENGTH:
        return False
    if not (url.startswith('http://') or url.startswith('https://')):
        return False
    return True


def _validate_products_payload(products, product_mode, library_products):
    """Validate the products array from the request body.

    Returns (is_valid, error_code, error_message) tuple.
    """
    if not isinstance(products, list):
        return False, 'VALIDATION_ERROR', '상품 목록이 유효하지 않습니다.'

    # Enforce product count based on mode
    if len(products) < 1:
        return False, 'VALIDATION_ERROR', '최소 1개의 상품을 등록해야 합니다.'

    if product_mode == 'single':
        if len(products) != 1:
            return False, 'PRODUCT_LIMIT', 'single 모드에서는 정확히 1개의 상품만 등록 가능합니다.'
    elif product_mode == 'multiple':
        if len(products) > PRODUCT_LIMIT:
            return False, 'PRODUCT_LIMIT', '최대 50개 상품까지 등록 가능합니다.'

    # Build a lookup set of valid product_ids from library
    valid_product_ids = {p['product_id'] for p in library_products}

    seen_product_ids = set()

    for i, product in enumerate(products):
        if not isinstance(product, dict):
            return False, 'VALIDATION_ERROR', f'상품 항목 {i + 1}이(가) 유효하지 않습니다.'

        # Validate product_id (required, must exist in library)
        product_id = product.get('product_id')
        if not product_id or not isinstance(product_id, str):
            return False, 'VALIDATION_ERROR', f'상품 항목 {i + 1}: product_id가 필요합니다.'

        if product_id not in valid_product_ids:
            return False, 'VALIDATION_ERROR', f'상품 항목 {i + 1}: 제품 라이브러리에 존재하지 않는 product_id입니다.'

        if product_id in seen_product_ids:
            return False, 'VALIDATION_ERROR', f'상품 항목 {i + 1}: 중복된 product_id입니다.'
        seen_product_ids.add(product_id)

        # Validate override URLs (optional, null to clear)
        for url_field in ['override_product_image_url', 'override_product_detail_url', 'override_size_guide_url']:
            if url_field in product:
                val = product[url_field]
                if val is not None and val != '':
                    if not _validate_url(val):
                        return False, 'INVALID_URL', 'URL 형식이 올바르지 않습니다.'

        # Validate override_short_description (optional, null to clear)
        if 'override_short_description' in product:
            desc = product['override_short_description']
            if desc is not None and desc != '':
                if not isinstance(desc, str):
                    return False, 'VALIDATION_ERROR', f'상품 항목 {i + 1}: override_short_description은 문자열이어야 합니다.'
                if len(desc) > MAX_SHORT_DESCRIPTION_LENGTH:
                    return False, 'VALIDATION_ERROR', f'상품 항목 {i + 1}: override_short_description은 최대 {MAX_SHORT_DESCRIPTION_LENGTH}자까지 입력 가능합니다.'

        # Validate display_order (required, integer 1-50)
        display_order = product.get('display_order')
        if display_order is None:
            return False, 'VALIDATION_ERROR', f'상품 항목 {i + 1}: display_order가 필요합니다.'
        if not isinstance(display_order, int) or isinstance(display_order, bool):
            return False, 'VALIDATION_ERROR', f'상품 항목 {i + 1}: display_order는 정수여야 합니다.'
        if display_order < MIN_DISPLAY_ORDER or display_order > MAX_DISPLAY_ORDER:
            return False, 'VALIDATION_ERROR', f'상품 항목 {i + 1}: display_order는 {MIN_DISPLAY_ORDER}~{MAX_DISPLAY_ORDER} 범위여야 합니다.'

        # Validate status (required, open/closed)
        status = product.get('status')
        if not status:
            return False, 'VALIDATION_ERROR', f'상품 항목 {i + 1}: status가 필요합니다.'
        if status not in VALID_PRODUCT_STATUSES:
            return False, 'VALIDATION_ERROR', f'상품 항목 {i + 1}: status는 open 또는 closed여야 합니다.'

    return True, None, None


def _build_campaign_products(products_payload, library_products):
    """Build full CampaignProduct objects by merging library defaults with overrides.

    For each product in the payload, look up the library product and merge
    override values on top of defaults.
    """
    # Build library lookup
    library_lookup = {p['product_id']: p for p in library_products}

    campaign_products = []
    for item in products_payload:
        product_id = item['product_id']
        lib_product = library_lookup[product_id]

        # Start with library defaults
        campaign_product = {
            'product_id': product_id,
            'product_name': lib_product.get('product_name', ''),
            'product_image_url': lib_product.get('product_image_url', ''),
            'short_description': lib_product.get('short_description', ''),
            'product_detail_url': lib_product.get('product_detail_url', None),
            'size_guide_url': lib_product.get('size_guide_url', None),
            'available_sizes': lib_product.get('available_sizes', []),
            'available_colors': lib_product.get('available_colors', []),
            'status': item['status'],
            'display_order': item['display_order'],
            # Store override values (null means use library default)
            'override_product_image_url': item.get('override_product_image_url', None),
            'override_product_detail_url': item.get('override_product_detail_url', None),
            'override_size_guide_url': item.get('override_size_guide_url', None),
            'override_short_description': item.get('override_short_description', None),
        }

        # Apply overrides to the resolved display fields
        if campaign_product['override_product_image_url']:
            campaign_product['product_image_url'] = campaign_product['override_product_image_url']
        if campaign_product['override_product_detail_url']:
            campaign_product['product_detail_url'] = campaign_product['override_product_detail_url']
        if campaign_product['override_size_guide_url']:
            campaign_product['size_guide_url'] = campaign_product['override_size_guide_url']
        if campaign_product['override_short_description']:
            campaign_product['short_description'] = campaign_product['override_short_description']

        campaign_products.append(campaign_product)

    # Sort by display_order
    campaign_products.sort(key=lambda p: p['display_order'])

    return campaign_products


def _handle_put(handler):
    """Handle PUT - Assign products to a campaign with override support."""
    # Get campaign_id from query params
    parsed = urlparse(handler.path)
    params = parse_qs(parsed.query)
    campaign_id = params.get('campaign_id', [None])[0]

    # Read request body
    body = _read_body(handler)
    if not body:
        _error_response(handler, 400, 'VALIDATION_ERROR', '요청 본문이 비어있습니다.')
        return

    # Campaign ID can also come from body
    if not campaign_id:
        campaign_id = body.get('campaign_id')

    if not campaign_id:
        _error_response(handler, 400, 'VALIDATION_ERROR', 'campaign_id가 필요합니다.')
        return

    # Load campaign
    campaign = _load_campaign(campaign_id)
    if not campaign:
        _error_response(handler, 404, 'NOT_FOUND', 'Campaign not found')
        return

    product_mode = campaign.get('product_mode', 'multiple')

    # Check for product_mode change with existing products
    if 'product_mode_change' in body:
        new_mode = body['product_mode_change']
        if new_mode in ('single', 'multiple') and new_mode != product_mode:
            # Check if there are existing product assignments
            existing_products = campaign.get('products', [])
            if existing_products:
                # Return warning response for confirmation
                _json_response(handler, 200, {
                    'status': 'warning',
                    'code': 'MODE_CHANGE_CONFIRMATION',
                    'message': '상품 모드를 변경하면 기존에 등록된 상품이 모두 삭제됩니다. 계속하시겠습니까?',
                    'current_mode': product_mode,
                    'new_mode': new_mode,
                    'affected_products_count': len(existing_products)
                })
                return
            else:
                # No existing products, safe to change mode
                campaign['product_mode'] = new_mode
                product_mode = new_mode

    # Track whether a mode change occurred that cleared existing products
    mode_change_warning = False

    # Check if confirmed mode change
    if body.get('confirm_mode_change'):
        new_mode = body.get('new_product_mode')
        if new_mode in ('single', 'multiple'):
            existing_products = campaign.get('products', [])
            if existing_products and new_mode != product_mode:
                mode_change_warning = True
            campaign['product_mode'] = new_mode
            campaign['products'] = []  # Clear existing assignments
            product_mode = new_mode

    # Get products array from body
    products_payload = body.get('products')
    if products_payload is None:
        # If no products provided and this was just a mode change confirmation, save and return
        if body.get('confirm_mode_change'):
            campaign['updated_at'] = _now_iso()
            _save_campaign(campaign)
            response = {'status': 'success', 'data': campaign}
            if mode_change_warning:
                response['mode_change_warning'] = True
            _json_response(handler, 200, response)
            return
        _error_response(handler, 400, 'VALIDATION_ERROR', 'products 배열이 필요합니다.')
        return

    # Load product library for validation
    library_products = _load_product_library()

    # Validate the products payload
    is_valid, error_code, error_message = _validate_products_payload(
        products_payload, product_mode, library_products
    )
    if not is_valid:
        _error_response(handler, 400, error_code, error_message)
        return

    # Build the full CampaignProduct objects
    campaign_products = _build_campaign_products(products_payload, library_products)

    # Update campaign
    campaign['products'] = campaign_products
    campaign['updated_at'] = _now_iso()
    _save_campaign(campaign)

    response = {'status': 'success', 'data': campaign}
    if mode_change_warning:
        response['mode_change_warning'] = True
    _json_response(handler, 200, response)


class handler(BaseHTTPRequestHandler):
    """Vercel serverless function handler for campaign product assignment."""

    def do_OPTIONS(self):
        """Handle CORS preflight requests."""
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'PUT, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_PUT(self):
        """Handle PUT requests for product assignment."""
        _handle_put(self)
