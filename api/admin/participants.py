"""Protected Campaign Participant workflow API.

GET   /api/admin/participants?campaign_id=&creator_id=&participant_id=
POST  /api/admin/participants
PATCH /api/admin/participants?participant_id=<uuid>
"""

from http.server import BaseHTTPRequestHandler
import json
import logging
from urllib.parse import parse_qs, urlparse

from api._admin_auth import AdminAuthError, require_admin
from api._db import DatabaseUnavailableError, connect_database

logger = logging.getLogger(__name__)
MAX_LIMIT = 200
STATUS_VALUES = {
    "screening_status": {"pending", "eligible", "manual_review", "filtered"},
    "dm_status": {"pending", "sent", "replied", "agreed", "no_response", "rejected"},
    "form_status": {"pending", "submitted"},
    "shipping_status": {"pending", "preparing", "shipped", "in_transit", "delivered"},
    "shipping_update_source": {"logistics_api", "manual"},
    "ugc_status": {"pending", "waiting_for_content", "posted", "completed"},
}


def _json_default(value):
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _respond(handler, status, body):
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(json.dumps(body, ensure_ascii=False, default=_json_default).encode("utf-8"))


def _read_body(handler):
    length = int(handler.headers.get("Content-Length", 0))
    if length <= 0 or length > 100_000:
        return None
    return json.loads(handler.rfile.read(length).decode("utf-8"))


def _parse_pagination(params):
    try:
        limit = min(max(int(params.get("limit", [50])[0]), 1), MAX_LIMIT)
        offset = max(int(params.get("offset", [0])[0]), 0)
    except (TypeError, ValueError):
        raise ValueError("Invalid pagination")
    return limit, offset


def _handle_get(handler):
    params = parse_qs(urlparse(handler.path).query)
    participant_id = str(params.get("participant_id", [""])[0]).strip()
    limit, offset = _parse_pagination(params)
    filters = []
    values = []

    if participant_id:
        filters.append("p.participant_id = %s")
        values.append(participant_id)
    for field in ("campaign_id", "creator_id"):
        value = str(params.get(field, [""])[0]).strip()
        if value:
            filters.append(f"p.{field} = %s")
            values.append(value)
    for field in STATUS_VALUES:
        value = str(params.get(field, [""])[0]).strip()
        if value:
            if value not in STATUS_VALUES[field]:
                raise ValueError(f"Invalid {field}")
            filters.append(f"p.{field} = %s")
            values.append(value)

    where = "where " + " and ".join(filters) if filters else ""
    with connect_database() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                select p.*, c.instagram_user_id, c.instagram_username,
                       c.instagram_profile_url, c.follower_count, c.is_private,
                       c.last_post_at, c.tags
                from public.campaign_participants p
                join public.creators c on c.creator_id = p.creator_id
                {where}
                order by p.updated_at desc
                limit %s offset %s
                """,
                tuple(values + [limit, offset]),
            )
            participants = cursor.fetchall()
            cursor.execute(
                f"""
                select count(*) as total
                from public.campaign_participants p
                {where}
                """,
                tuple(values),
            )
            total = cursor.fetchone()["total"]
    _respond(handler, 200, {
        "status": "success",
        "data": participants,
        "page": {"limit": limit, "offset": offset, "total": total},
    })


def _handle_post(handler):
    body = _read_body(handler)
    if not isinstance(body, dict):
        raise ValueError("A JSON body is required")
    campaign_id = str(body.get("campaign_id") or "").strip()
    creator_id = str(body.get("creator_id") or "").strip()
    if not campaign_id or not creator_id:
        raise ValueError("campaign_id and creator_id are required")
    screening_status = str(body.get("screening_status") or "pending").strip()
    if screening_status not in STATUS_VALUES["screening_status"]:
        raise ValueError("Invalid screening_status")

    with connect_database() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                insert into public.campaign_participants (
                  campaign_id, creator_id, product_id, product_name,
                  screening_status, source_provider, source_registration_key
                ) values (%s, %s, %s, %s, %s, %s, %s)
                on conflict (campaign_id, creator_id) do update set
                  product_id = coalesce(excluded.product_id, campaign_participants.product_id),
                  product_name = coalesce(excluded.product_name, campaign_participants.product_name),
                  source_provider = coalesce(excluded.source_provider, campaign_participants.source_provider),
                  source_registration_key = coalesce(
                    excluded.source_registration_key,
                    campaign_participants.source_registration_key
                  )
                returning *
                """,
                (
                    campaign_id,
                    creator_id,
                    body.get("product_id"),
                    body.get("product_name"),
                    screening_status,
                    body.get("source_provider"),
                    body.get("source_registration_key"),
                ),
            )
            participant = cursor.fetchone()
        connection.commit()
    _respond(handler, 201, {"status": "success", "data": participant})


def _handle_patch(handler):
    params = parse_qs(urlparse(handler.path).query)
    participant_id = str(params.get("participant_id", [""])[0]).strip()
    if not participant_id:
        raise ValueError("participant_id is required")
    body = _read_body(handler)
    if not isinstance(body, dict):
        raise ValueError("A JSON body is required")

    allowed = {
        "screening_status", "screening_reason", "dm_status", "dm_sent_at",
        "form_status", "form_submitted_at", "shipping_status", "order_number",
        "tracking_number", "carrier", "shipped_at", "delivered_at",
        "latest_tracking_status", "last_logistics_update",
        "shipping_update_source", "ugc_status", "product_id", "product_name",
    }
    updates = []
    values = []
    for field in allowed:
        if field not in body:
            continue
        value = body[field]
        if field in STATUS_VALUES and value is not None and value not in STATUS_VALUES[field]:
            raise ValueError(f"Invalid {field}")
        updates.append(f"{field} = %s")
        values.append(value)

    if body.get("dm_status") == "sent" and "dm_sent_at" not in body:
        updates.append("dm_sent_at = coalesce(dm_sent_at, now())")
    if "dm_status" in body:
        updates.append("dm_updated_at = now()")
    if body.get("form_status") == "submitted" and "form_submitted_at" not in body:
        updates.append("form_submitted_at = coalesce(form_submitted_at, now())")
    if body.get("shipping_status") == "shipped" and "shipped_at" not in body:
        updates.append("shipped_at = coalesce(shipped_at, now())")
    if body.get("shipping_status") == "delivered":
        if "delivered_at" not in body:
            updates.append("delivered_at = coalesce(delivered_at, now())")
        if "ugc_status" not in body:
            updates.append("ugc_status = 'waiting_for_content'")
    if any(field in body for field in (
        "shipping_status", "order_number", "tracking_number", "carrier",
        "shipped_at", "delivered_at", "latest_tracking_status"
    )) and "shipping_update_source" not in body:
        updates.append("shipping_update_source = 'manual'")

    if not updates:
        raise ValueError("No supported fields supplied")
    values.append(participant_id)

    with connect_database() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                update public.campaign_participants
                set {', '.join(updates)}
                where participant_id = %s
                returning *
                """,
                tuple(values),
            )
            participant = cursor.fetchone()
        connection.commit()
    if not participant:
        _respond(handler, 404, {"status": "error", "message": "Participant not found"})
        return
    _respond(handler, 200, {"status": "success", "data": participant})


def _dispatch(handler, action):
    try:
        require_admin(handler)
        action(handler)
    except AdminAuthError as error:
        _respond(handler, error.status_code, {"status": "error", "message": str(error)})
    except DatabaseUnavailableError:
        _respond(handler, 503, {"status": "error", "message": "Participant database is not configured"})
    except (json.JSONDecodeError, ValueError) as error:
        _respond(handler, 400, {"status": "error", "message": str(error)})
    except Exception:
        logger.exception("Participant API request failed")
        _respond(handler, 500, {"status": "error", "message": "Participant request failed"})


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Allow", "GET, POST, PATCH, OPTIONS")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PATCH, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.end_headers()

    def do_GET(self):
        _dispatch(self, _handle_get)

    def do_POST(self):
        _dispatch(self, _handle_post)

    def do_PATCH(self):
        _dispatch(self, _handle_patch)
