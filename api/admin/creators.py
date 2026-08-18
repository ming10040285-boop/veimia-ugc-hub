"""Protected Creator CRM API.

GET  /api/admin/creators?q=&creator_id=&limit=&offset=
POST /api/admin/creators
PATCH /api/admin/creators?creator_id=<uuid>
"""

from http.server import BaseHTTPRequestHandler
import json
import logging
from urllib.parse import parse_qs, urlparse

from api._admin_auth import AdminAuthError, require_admin
from api._db import DatabaseUnavailableError, connect_database

logger = logging.getLogger(__name__)
ALLOWED_TAGS = {"favorite", "priority", "do_not_invite"}
MAX_LIMIT = 100


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


def _normalize_username(value):
    return str(value or "").strip().lstrip("@").strip()


def _validate_tags(value):
    if value is None:
        return None
    if not isinstance(value, list):
        raise ValueError("tags must be an array")
    tags = {str(tag).strip().lower() for tag in value if str(tag).strip()}
    if not tags.issubset(ALLOWED_TAGS):
        raise ValueError("tags contain unsupported values")
    return sorted(tags)


def _parse_pagination(params):
    try:
        limit = min(max(int(params.get("limit", [50])[0]), 1), MAX_LIMIT)
        offset = max(int(params.get("offset", [0])[0]), 0)
    except (TypeError, ValueError):
        raise ValueError("Invalid pagination")
    return limit, offset


def _handle_get(handler):
    params = parse_qs(urlparse(handler.path).query)
    creator_id = str(params.get("creator_id", [""])[0]).strip()

    with connect_database() as connection:
        with connection.cursor() as cursor:
            if creator_id:
                cursor.execute(
                    "select * from public.creators where creator_id = %s",
                    (creator_id,),
                )
                creator = cursor.fetchone()
                if not creator:
                    _respond(handler, 404, {"status": "error", "message": "Creator not found"})
                    return
                cursor.execute(
                    """
                    select * from public.campaign_participants
                    where creator_id = %s
                    order by created_at desc
                    """,
                    (creator_id,),
                )
                _respond(handler, 200, {
                    "status": "success",
                    "data": {"creator": creator, "participations": cursor.fetchall()},
                })
                return

            limit, offset = _parse_pagination(params)
            query = str(params.get("q", [""])[0]).strip()
            values = []
            where = ""
            if query:
                where = "where instagram_username ilike %s or instagram_user_id = %s"
                values.extend((f"%{query.lstrip('@')}%", query))
            values.extend((limit, offset))
            cursor.execute(
                f"""
                select * from public.creators
                {where}
                order by updated_at desc
                limit %s offset %s
                """,
                tuple(values),
            )
            creators = cursor.fetchall()
            cursor.execute(
                f"select count(*) as total from public.creators {where}",
                tuple(values[:-2]),
            )
            total = cursor.fetchone()["total"]
            _respond(handler, 200, {
                "status": "success",
                "data": creators,
                "page": {"limit": limit, "offset": offset, "total": total},
            })


def _handle_post(handler):
    body = _read_body(handler)
    if not isinstance(body, dict):
        raise ValueError("A JSON body is required")

    username = _normalize_username(body.get("instagram_username"))
    if not username or len(username) > 200:
        raise ValueError("instagram_username is required")
    tags = _validate_tags(body.get("tags")) if "tags" in body else None
    instagram_user_id = str(body.get("instagram_user_id") or "").strip() or None

    with connect_database() as connection:
        with connection.cursor() as cursor:
            existing = None
            if instagram_user_id:
                cursor.execute(
                    "select creator_id from public.creators where instagram_user_id = %s",
                    (instagram_user_id,),
                )
                existing = cursor.fetchone()
            if not existing:
                cursor.execute(
                    """
                    select creator_id from public.creators
                    where instagram_username_normalized = lower(%s)
                    """,
                    (username,),
                )
                existing = cursor.fetchone()

            if existing:
                cursor.execute(
                    """
                    update public.creators set
                      instagram_user_id = coalesce(%s, instagram_user_id),
                      instagram_username = %s,
                      instagram_profile_url = coalesce(%s, instagram_profile_url),
                      tags = coalesce(%s, tags),
                      notes = coalesce(%s, notes)
                    where creator_id = %s
                    returning *
                    """,
                    (
                        instagram_user_id,
                        username,
                        body.get("instagram_profile_url"),
                        tags,
                        body.get("notes"),
                        existing["creator_id"],
                    ),
                )
                status = 200
            else:
                cursor.execute(
                    """
                    insert into public.creators (
                      instagram_user_id, instagram_username,
                      instagram_profile_url, tags, notes
                    ) values (%s, %s, %s, %s, %s)
                    returning *
                    """,
                    (
                        instagram_user_id,
                        username,
                        body.get("instagram_profile_url"),
                        tags or [],
                        body.get("notes"),
                    ),
                )
                status = 201
            creator = cursor.fetchone()
        connection.commit()
    _respond(handler, status, {"status": "success", "data": creator})


def _handle_patch(handler):
    params = parse_qs(urlparse(handler.path).query)
    creator_id = str(params.get("creator_id", [""])[0]).strip()
    if not creator_id:
        raise ValueError("creator_id is required")
    body = _read_body(handler)
    if not isinstance(body, dict):
        raise ValueError("A JSON body is required")

    allowed = {
        "instagram_user_id", "instagram_username", "instagram_profile_url",
        "follower_count", "is_private", "last_post_at", "tags", "notes",
    }
    updates = []
    values = []
    for field in allowed:
        if field not in body:
            continue
        value = body[field]
        if field == "instagram_username":
            value = _normalize_username(value)
            if not value:
                raise ValueError("instagram_username cannot be blank")
        if field == "tags":
            value = _validate_tags(value)
        updates.append(f"{field} = %s")
        values.append(value)
    if not updates:
        raise ValueError("No supported fields supplied")

    values.append(creator_id)
    with connect_database() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"update public.creators set {', '.join(updates)} where creator_id = %s returning *",
                tuple(values),
            )
            creator = cursor.fetchone()
        connection.commit()
    if not creator:
        _respond(handler, 404, {"status": "error", "message": "Creator not found"})
        return
    _respond(handler, 200, {"status": "success", "data": creator})


def _dispatch(handler, action):
    try:
        require_admin(handler)
        action(handler)
    except AdminAuthError as error:
        _respond(handler, error.status_code, {"status": "error", "message": str(error)})
    except DatabaseUnavailableError:
        _respond(handler, 503, {"status": "error", "message": "Creator database is not configured"})
    except (json.JSONDecodeError, ValueError) as error:
        _respond(handler, 400, {"status": "error", "message": str(error)})
    except Exception:
        logger.exception("Creator API request failed")
        _respond(handler, 500, {"status": "error", "message": "Creator request failed"})


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
