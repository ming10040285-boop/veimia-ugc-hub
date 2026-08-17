"""Test or initialize a Campaign registration worksheet from the admin UI."""

from http.server import BaseHTTPRequestHandler
import json
import os

try:
    import gspread
    from google.oauth2.service_account import Credentials
    GSPREAD_AVAILABLE = True
except ImportError:
    gspread = None
    Credentials = None
    GSPREAD_AVAILABLE = False

HEADERS = [
    "timestamp", "campaign_id", "product_id", "product_name",
    "selected_size", "selected_color", "instagram_id",
    "instagram_profile_url", "member_type", "name", "phone",
    "postal_code", "state", "city", "address", "consent_status",
]


def _respond(handler, status, body):
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.end_headers()
    handler.wfile.write(json.dumps(body, ensure_ascii=False).encode("utf-8"))


def _read_body(handler):
    length = int(handler.headers.get("Content-Length", 0))
    return json.loads(handler.rfile.read(length)) if length else {}


def _parse_credentials_info(credentials_json):
    """Parse the first service-account JSON object without exposing its contents."""
    parsed, _ = json.JSONDecoder().raw_decode(str(credentials_json or "").strip())
    if isinstance(parsed, str):
        parsed = json.loads(parsed)
    if not isinstance(parsed, dict):
        raise ValueError("Google Sheets credentials must be a JSON object")
    return parsed


def _extract_id(value):
    value = str(value or "").strip()
    marker = "/spreadsheets/d/"
    if marker in value:
        value = value.split(marker, 1)[1].split("/", 1)[0]
    return value.split("?", 1)[0].split("#", 1)[0].strip()

def _handle_post(handler):
    if not GSPREAD_AVAILABLE:
        _respond(handler, 503, {"status": "error", "message": "Google Sheets 组件不可用。"})
        return

    try:
        body = _read_body(handler)
        sheet_id = _extract_id(body.get("spreadsheet_id"))
        worksheet_name = str(body.get("worksheet_name") or "Sheet1").strip()
        action = body.get("action", "test")
        credentials_json = os.environ.get("GOOGLE_SHEETS_CREDENTIALS")
        if not sheet_id or not credentials_json:
            _respond(handler, 400, {"status": "error", "message": "请填写 Google Sheet 链接，并确认服务账号凭据已配置。"})
            return

        credentials_info = _parse_credentials_info(credentials_json)
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        credentials = Credentials.from_service_account_info(credentials_info, scopes=scopes)
        spreadsheet = gspread.authorize(credentials).open_by_key(sheet_id)

        try:
            worksheet = spreadsheet.worksheet(worksheet_name)
        except gspread.WorksheetNotFound:
            if action != "initialize":
                raise
            worksheet = spreadsheet.add_worksheet(
                title=worksheet_name, rows=1000, cols=len(HEADERS)
            )

        rows = worksheet.get_all_values()
        initialized = False
        if action == "initialize":
            if not rows:
                worksheet.append_row(HEADERS, value_input_option="RAW")
                rows = [HEADERS]
                initialized = True
            elif [str(value).strip().lower() for value in rows[0]] != HEADERS:
                _respond(handler, 409, {
                    "status": "error",
                    "message": "工作表已有数据且表头不是系统标准格式。为避免覆盖数据，未执行初始化。",
                })
                return

        _respond(handler, 200, {
            "status": "success",
            "message": "表格连接成功。" if not initialized else "连接成功，标准表头已创建。",
            "spreadsheet_title": spreadsheet.title,
            "worksheet_title": worksheet.title,
            "row_count": max(len(rows) - 1, 0),
            "headers": rows[0] if rows else [],
            "initialized": initialized,
        })
    except Exception as error:
        _respond(handler, 400, {
            "status": "error",
            "message": f"无法连接 Google Sheet：{str(error)}",
        })


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self):
        _handle_post(self)
