"""Registration Viewer API endpoint for VEIMIA UGC Hub Admin.

Reads registration data from Google Sheets and returns filtered results.
GET /api/admin/registrations?campaign_id=<optional>

Timeout: Vercel enforces a 10s maximum execution time via vercel.json maxDuration.
         Google Sheets reads may approach this limit under load.
"""

from http.server import BaseHTTPRequestHandler
import json
import logging
import os
from urllib.parse import urlparse, parse_qs

try:
    import gspread
    from google.oauth2.service_account import Credentials
    GSPREAD_AVAILABLE = True
except ImportError:
    GSPREAD_AVAILABLE = False

logger = logging.getLogger(__name__)

# Column indices matching the 11-column registration row format
# 0=timestamp, 1=campaign_id, 2=product_id, 3=selected_size, 4=selected_color,
# 5=instagram_id, 6=name, 7=phone, 8=address, 9=postal_code, 10=consent
COLUMN_NAMES = [
    "timestamp",
    "campaign_id",
    "product_id",
    "selected_size",
    "selected_color",
    "instagram_id",
    "name",
    "phone",
    "address",
    "postal_code",
    "consent",
]


def _json_response(handler, status_code, body):
    """Send a JSON response with the given status code and body dict."""
    handler.send_response(status_code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.end_headers()
    handler.wfile.write(json.dumps(body, ensure_ascii=False).encode("utf-8"))


def _row_to_dict(row):
    """Convert a row list to a dict using column names."""
    result = {}
    for i, col_name in enumerate(COLUMN_NAMES):
        if i < len(row):
            result[col_name] = row[i]
        else:
            result[col_name] = ""
    return result


def _read_registrations_from_sheets(campaign_id=None):
    """
    Read registrations from Google Sheets.

    Args:
        campaign_id: Optional filter — only return rows matching this campaign_id.

    Returns:
        tuple: (registrations_list, warning_message_or_None)
    """
    if not GSPREAD_AVAILABLE:
        return [], "gspread library not available — showing empty list"

    credentials_json = os.environ.get("GOOGLE_SHEETS_CREDENTIALS")
    sheet_id = os.environ.get("GOOGLE_SHEETS_ID")

    if not credentials_json or not sheet_id:
        return [], "Google Sheets credentials not configured — showing empty list"

    try:
        credentials_info = json.loads(credentials_json)
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets.readonly",
            "https://www.googleapis.com/auth/drive.readonly",
        ]
        credentials = Credentials.from_service_account_info(
            credentials_info, scopes=scopes
        )
        client = gspread.authorize(credentials)
        spreadsheet = client.open_by_key(sheet_id)
        worksheet = spreadsheet.sheet1

        all_rows = worksheet.get_all_values()

        # Skip header row (first row)
        data_rows = all_rows[1:] if len(all_rows) > 1 else []

        registrations = []
        for row in data_rows:
            reg = _row_to_dict(row)

            # Filter by campaign_id if specified
            if campaign_id and reg.get("campaign_id") != campaign_id:
                continue

            registrations.append(reg)

        return registrations, None

    except Exception as e:
        logger.error("Failed to read registrations from Google Sheets: %s", str(e))
        return [], f"Google Sheets 읽기 실패 — {str(e)}"


def _handle_get(handler):
    """Handle GET - Read registrations, optionally filtered by campaign_id."""
    parsed = urlparse(handler.path)
    params = parse_qs(parsed.query)

    campaign_id = params.get("campaign_id", [None])[0]

    registrations, warning = _read_registrations_from_sheets(campaign_id)

    response = {
        "status": "success",
        "registrations": registrations,
        "count": len(registrations),
    }

    if warning:
        response["warning"] = warning

    _json_response(handler, 200, response)


class handler(BaseHTTPRequestHandler):
    """Vercel serverless function handler for registration viewer."""

    def do_OPTIONS(self):
        """Handle CORS preflight requests."""
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        _handle_get(self)
