"""Admin registration viewer with Campaign-specific Google Sheet support."""

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
    gspread = None
    Credentials = None
    GSPREAD_AVAILABLE = False

logger = logging.getLogger(__name__)

CURRENT_LEGACY_COLUMNS = [
    "timestamp", "campaign_id", "product_id", "selected_size", "selected_color",
    "instagram_id", "name", "postal_code", "phone", "state", "city", "address",
    "consent", "member_type", "collaboration_status", "creator_level",
    "collaboration_count", "content_score", "post_url", "notes",
]
OLD_LEGACY_COLUMNS = [
    "timestamp", "campaign_id", "product_id", "selected_size", "selected_color",
    "instagram_id", "name", "phone", "address", "postal_code", "consent",
]


def _json_response(handler, status_code, body):
    handler.send_response(status_code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.end_headers()
    handler.wfile.write(json.dumps(body, ensure_ascii=False).encode("utf-8"))


def _load_campaign(campaign_id):
    if not campaign_id:
        return {}
    path = os.path.normpath(os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "..", "public",
        "config", "campaigns", f"{campaign_id}.json"
    ))
    if not os.path.isfile(path):
        return {}
    with open(path, "r", encoding="utf-8") as campaign_file:
        return json.load(campaign_file)


def _parse_credentials_info(credentials_json):
    """Parse the first service-account JSON object without exposing its contents."""
    parsed, _ = json.JSONDecoder().raw_decode(str(credentials_json or "").strip())
    if isinstance(parsed, str):
        parsed = json.loads(parsed)
    if not isinstance(parsed, dict):
        raise ValueError("Google Sheets credentials must be a JSON object")
    return parsed


def _extract_spreadsheet_id(value):
    value = str(value or "").strip()
    marker = "/spreadsheets/d/"
    if marker in value:
        value = value.split(marker, 1)[1].split("/", 1)[0]
    return value.split("?", 1)[0].split("#", 1)[0].strip()


def _sheet_settings(campaign_id):
    campaign = _load_campaign(campaign_id)
    storage = campaign.get("registration_storage") or {}
    configured_id = _extract_spreadsheet_id(
        storage.get("spreadsheet_id") or storage.get("spreadsheet_url")
    )
    if configured_id:
        return configured_id, str(storage.get("worksheet_name") or "Sheet1").strip(), True
    return _extract_spreadsheet_id(os.environ.get("GOOGLE_SHEETS_ID")), "", False


def _row_to_dict(row, columns):
    return {
        column: (row[index] if index < len(row) else "")
        for index, column in enumerate(columns)
    }


def _dedicated_row_to_dict(row, headers):
    values = _row_to_dict(row, headers)
    # Keep the existing admin table contract while supporting the clearer v2 names.
    values["timestamp"] = values.get("timestamp") or values.get("submitted_at", "")
    values["name"] = values.get("name") or values.get("recipient_name", "")
    values["consent"] = values.get("consent") or values.get("consent_status", "")
    return values


def _read_registrations_from_sheets(campaign_id=None):
    if not GSPREAD_AVAILABLE:
        return [], "Google Sheets 组件不可用，暂时无法读取申请数据。"

    credentials_json = os.environ.get("GOOGLE_SHEETS_CREDENTIALS")
    sheet_id, worksheet_name, dedicated = _sheet_settings(campaign_id)
    if not credentials_json or not sheet_id:
        return [], "尚未配置 Google Sheets 凭据或表格。"

    try:
        credentials_info = _parse_credentials_info(credentials_json)
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets.readonly",
            "https://www.googleapis.com/auth/drive.readonly",
        ]
        credentials = Credentials.from_service_account_info(credentials_info, scopes=scopes)
        spreadsheet = gspread.authorize(credentials).open_by_key(sheet_id)
        worksheet = spreadsheet.worksheet(worksheet_name) if dedicated else spreadsheet.sheet1
        all_rows = worksheet.get_all_values()
        if len(all_rows) <= 1:
            return [], None

        registrations = []
        if dedicated:
            headers = [str(header).strip().lower() for header in all_rows[0]]
            for row in all_rows[1:]:
                registration = _dedicated_row_to_dict(row, headers)
                if campaign_id and registration.get("campaign_id", campaign_id) != campaign_id:
                    continue
                registrations.append(registration)
        else:
            for row in all_rows[1:]:
                # Current shared rows have 20 columns; historical rows used 11.
                columns = CURRENT_LEGACY_COLUMNS if len(row) >= 14 else OLD_LEGACY_COLUMNS
                registration = _row_to_dict(row, columns)
                if campaign_id and registration.get("campaign_id") != campaign_id:
                    continue
                registrations.append(registration)

        return registrations, None
    except Exception as error:
        logger.error("Failed to read registrations from Google Sheets: %s", str(error))
        return [], f"Google Sheets 读取失败：{str(error)}"


def _handle_get(handler):
    parsed = urlparse(handler.path)
    campaign_id = parse_qs(parsed.query).get("campaign_id", [None])[0]
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
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        _handle_get(self)
