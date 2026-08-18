"""Protected Candidate screening and explicit Creator promotion API."""

import json
import logging
from urllib.parse import parse_qs, urlparse

from api._admin_auth import AdminAuthError, require_admin
from api._db import DatabaseUnavailableError, connect_database
from api.admin.registration_import import _username_from_value

logger = logging.getLogger(__name__)
MAX_LIMIT = 200
SCREENING_STATUSES = {"pending", "eligible", "manual_review", "filtered", "promoted"}
PROFILE_CHECK_STATUSES = {"not_started", "queued", "success", "failed"}


def _json_default(value):
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _respond(handler, status, body):
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(
        json.dumps(body, ensure_ascii=False, default=_json_default).encode("utf-8")
    )


def _read_body(handler):
    length = int(handler.headers.get("Content-Length", 0))
    if length <= 0 or length > 100_000:
        return None
    return json.loads(handler.rfile.read(length).decode("utf-8"))


def _pagination(params):
    try:
        limit = min(max(int(params.get("limit", [50])[0]), 1), MAX_LIMIT)
        offset = max(int(params.get("offset", [0])[0]), 0)
    except (TypeError, ValueError):
        raise ValueError("分页参数无效")
    return limit, offset


def _normalized_username(value):
    username = _username_from_value(value)
    if not username:
        raise ValueError("Instagram 用户名或主页链接无效")
    return username.lower()


def _handle_get(handler):
    params = parse_qs(urlparse(handler.path).query)
    limit, offset = _pagination(params)
    filters = []
    values = []

    campaign_id = str(params.get("campaign_id", [""])[0]).strip()
    status = str(params.get("screening_status", [""])[0]).strip()
    query = str(params.get("q", [""])[0]).strip().lstrip("@")
    if campaign_id:
        filters.append("campaign_id = %s")
        values.append(campaign_id)
    if status:
        if status not in SCREENING_STATUSES:
            raise ValueError("筛选状态无效")
        filters.append("screening_status = %s")
        values.append(status)
    if query:
        filters.append("instagram_username ilike %s")
        values.append(f"%{query}%")

    where = "where " + " and ".join(filters) if filters else ""
    with connect_database() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                select * from public.creator_candidates
                {where}
                order by updated_at desc
                limit %s offset %s
                """,
                tuple(values + [limit, offset]),
            )
            candidates = cursor.fetchall()
            cursor.execute(
                f"select count(*) as total from public.creator_candidates {where}",
                tuple(values),
            )
            total = cursor.fetchone()["total"]
    _respond(handler, 200, {
        "status": "success",
        "data": candidates,
        "page": {"limit": limit, "offset": offset, "total": total},
    })


def _create_candidate(handler, body):
    campaign_id = str(body.get("campaign_id") or "").strip()
    if not campaign_id:
        raise ValueError("请选择 Campaign")
    username = _normalized_username(
        body.get("instagram_username") or body.get("instagram_profile_url")
    )
    profile_url = f"https://www.instagram.com/{username}/"
    source_provider = str(body.get("source_provider") or "manual").strip() or "manual"
    source_key = str(body.get("source_key") or "").strip() or None

    with connect_database() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                insert into public.creator_candidates (
                  campaign_id, instagram_username, instagram_profile_url,
                  source_provider, source_key
                ) values (%s, %s, %s, %s, %s)
                on conflict (campaign_id, instagram_username_normalized) do update set
                  instagram_username = excluded.instagram_username,
                  instagram_profile_url = excluded.instagram_profile_url,
                  source_provider = coalesce(
                    excluded.source_provider, creator_candidates.source_provider
                  ),
                  source_key = coalesce(excluded.source_key, creator_candidates.source_key)
                returning *
                """,
                (campaign_id, username, profile_url, source_provider, source_key),
            )
            candidate = cursor.fetchone()
        connection.commit()
    _respond(handler, 200, {"status": "success", "data": candidate})


def _promote_candidate(handler, body):
    candidate_id = str(body.get("candidate_id") or "").strip()
    if not candidate_id:
        raise ValueError("缺少 candidate_id")

    with connect_database() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "select * from public.creator_candidates where candidate_id = %s for update",
                (candidate_id,),
            )
            candidate = cursor.fetchone()
            if not candidate:
                _respond(handler, 404, {"status": "error", "message": "候选人不存在"})
                return
            if candidate["screening_status"] not in {"eligible", "promoted"}:
                raise ValueError("只有已标记为“符合条件”的候选人才能进入 Creator CRM")

            cursor.execute(
                """
                with upserted_creator as (
                  insert into public.creators (
                    instagram_username, instagram_profile_url,
                    follower_count, is_private, last_post_at
                  ) values (%s, %s, %s, %s, %s)
                  on conflict (instagram_username_normalized) do update set
                    instagram_username = excluded.instagram_username,
                    instagram_profile_url = coalesce(
                      excluded.instagram_profile_url, creators.instagram_profile_url
                    ),
                    follower_count = coalesce(excluded.follower_count, creators.follower_count),
                    is_private = coalesce(excluded.is_private, creators.is_private),
                    last_post_at = coalesce(excluded.last_post_at, creators.last_post_at)
                  returning creator_id
                ), upserted_participant as (
                  insert into public.campaign_participants (
                    campaign_id, creator_id, product_id, product_name,
                    screening_status, source_provider, source_registration_key
                  )
                  select %s, creator_id, %s, %s, 'eligible', 'candidate', %s
                  from upserted_creator
                  on conflict (campaign_id, creator_id) do update set
                    product_id = coalesce(
                      excluded.product_id, campaign_participants.product_id
                    ),
                    product_name = coalesce(
                      excluded.product_name, campaign_participants.product_name
                    )
                  returning participant_id, creator_id
                )
                select participant_id, creator_id from upserted_participant
                """,
                (
                    candidate["instagram_username"],
                    candidate["instagram_profile_url"],
                    candidate["follower_count"],
                    candidate["is_private"],
                    candidate["last_post_at"],
                    candidate["campaign_id"],
                    body.get("product_id"),
                    body.get("product_name"),
                    str(candidate_id),
                ),
            )
            promoted = cursor.fetchone()
            cursor.execute(
                """
                update public.creator_candidates
                set screening_status = 'promoted',
                    promoted_at = coalesce(promoted_at, now())
                where candidate_id = %s
                returning *
                """,
                (candidate_id,),
            )
            updated_candidate = cursor.fetchone()
        connection.commit()
    _respond(handler, 200, {
        "status": "success",
        "data": {
            "candidate": updated_candidate,
            "creator_id": promoted["creator_id"],
            "participant_id": promoted["participant_id"],
        },
    })


def _handle_post(handler):
    body = _read_body(handler)
    if not isinstance(body, dict):
        raise ValueError("需要 JSON 请求内容")
    action = parse_qs(urlparse(handler.path).query).get("action", [""])[0]
    if action == "promote":
        _promote_candidate(handler, body)
        return
    _create_candidate(handler, body)


def _handle_patch(handler):
    params = parse_qs(urlparse(handler.path).query)
    candidate_id = str(params.get("candidate_id", [""])[0]).strip()
    if not candidate_id:
        raise ValueError("缺少 candidate_id")
    body = _read_body(handler)
    if not isinstance(body, dict):
        raise ValueError("需要 JSON 请求内容")

    allowed = {
        "follower_count", "is_private", "last_post_at", "screening_status",
        "screening_reason", "profile_check_status", "profile_checked_at",
    }
    updates = []
    values = []
    for field in allowed:
        if field not in body:
            continue
        value = body[field]
        if field == "screening_status":
            if value not in SCREENING_STATUSES - {"promoted"}:
                raise ValueError("筛选状态无效")
        if field == "profile_check_status" and value not in PROFILE_CHECK_STATUSES:
            raise ValueError("主页检查状态无效")
        updates.append(f"{field} = %s")
        values.append(value)
    if body.get("profile_check_status") in {"success", "failed"}:
        if "profile_checked_at" not in body:
            updates.append("profile_checked_at = now()")
    if not updates:
        raise ValueError("没有可更新的字段")

    values.append(candidate_id)
    with connect_database() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                update public.creator_candidates
                set {', '.join(updates)}
                where candidate_id = %s
                returning *
                """,
                tuple(values),
            )
            candidate = cursor.fetchone()
        connection.commit()
    if not candidate:
        _respond(handler, 404, {"status": "error", "message": "候选人不存在"})
        return
    _respond(handler, 200, {"status": "success", "data": candidate})


def _dispatch(handler, action):
    try:
        require_admin(handler)
        action(handler)
    except AdminAuthError as error:
        _respond(handler, error.status_code, {"status": "error", "message": str(error)})
    except DatabaseUnavailableError:
        _respond(handler, 503, {"status": "error", "message": "候选人数据库尚未配置"})
    except (json.JSONDecodeError, ValueError) as error:
        _respond(handler, 400, {"status": "error", "message": str(error)})
    except Exception:
        logger.exception("Candidate API request failed")
        _respond(handler, 500, {"status": "error", "message": "候选人请求失败"})
