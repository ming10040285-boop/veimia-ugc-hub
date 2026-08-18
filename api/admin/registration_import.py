"""Import manually confirmed Campaign registrations into Creator CRM."""

import hashlib
import json
import re
from urllib.parse import urlparse

from api._db import connect_database
from api.admin.registrations import (
    _load_campaign,
    _read_registrations_from_sheets,
    _sheet_settings,
)

MAX_IMPORT_ROWS = 500
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9._]{1,30}$")
RESERVED_PATHS = {
    "accounts", "direct", "explore", "p", "reel", "reels", "stories",
}


def _respond(handler, status, body):
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(json.dumps(body, ensure_ascii=False).encode("utf-8"))


def _read_body(handler):
    length = int(handler.headers.get("Content-Length", 0))
    if length <= 0 or length > 20_000:
        return None
    return json.loads(handler.rfile.read(length).decode("utf-8"))


def _username_from_value(value):
    raw = str(value or "").strip()
    if not raw:
        return None
    if raw.lower().startswith(("http://", "https://")):
        parsed = urlparse(raw)
        host = (parsed.hostname or "").lower()
        if host.startswith("www."):
            host = host[4:]
        if host not in {"instagram.com", "m.instagram.com"}:
            return None
        segments = [segment for segment in parsed.path.split("/") if segment]
        if len(segments) != 1 or segments[0].lower() in RESERVED_PATHS:
            return None
        raw = segments[0]
    else:
        raw = raw.lstrip("@").strip().strip("/")
        if "/" in raw or "?" in raw or "#" in raw:
            return None
    return raw if USERNAME_PATTERN.fullmatch(raw) else None


def _instagram_identity(registration):
    username_from_id = _username_from_value(registration.get("instagram_id"))
    username_from_url = _username_from_value(registration.get("instagram_profile_url"))
    if username_from_id and username_from_url:
        if username_from_id.lower() != username_from_url.lower():
            raise ValueError("Instagram 用户名与主页链接不一致")
    username = username_from_id or username_from_url
    if not username:
        raise ValueError("Instagram 用户名或主页链接无效")
    username = username.lower()
    return username, f"https://www.instagram.com/{username}/"


def _source_key(campaign_id, sheet_id, worksheet_name, registration, username):
    identity = {
        "campaign_id": campaign_id,
        "sheet_id": sheet_id,
        "worksheet_name": worksheet_name,
        "username": username,
        "timestamp": str(registration.get("timestamp") or "").strip(),
        "product_id": str(registration.get("product_id") or "").strip(),
    }
    encoded = json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _prepare_rows(campaign_id, campaign, sheet_id, worksheet_name, registrations):
    products = {
        str(product.get("product_id") or "").strip(): product
        for product in (campaign.get("products") or [])
        if str(product.get("product_id") or "").strip()
    }
    entries = {}
    invalid_rows = []
    warnings = []
    valid_rows = 0
    duplicates_collapsed = 0

    for row_number, registration in enumerate(registrations, start=2):
        try:
            username, profile_url = _instagram_identity(registration)
            product_id = str(registration.get("product_id") or "").strip()
            if not product_id:
                raise ValueError("缺少商品 ID")
            product = products.get(product_id) or {}
            product_name = str(
                registration.get("product_name") or product.get("product_name") or ""
            ).strip() or None
            if products and product_id not in products:
                warnings.append(f"第 {row_number} 行商品 {product_id} 不在当前 Campaign 商品列表中")

            entry = {
                "username": username,
                "profile_url": profile_url,
                "product_id": product_id,
                "product_name": product_name,
                "source_key": _source_key(
                    campaign_id, sheet_id, worksheet_name, registration, username
                ),
            }
            valid_rows += 1
            if username in entries:
                duplicates_collapsed += 1
            entries[username] = entry
        except ValueError as error:
            invalid_rows.append({"row": row_number, "message": str(error)})

    return {
        "entries": list(entries.values()),
        "valid_rows": valid_rows,
        "invalid_rows": invalid_rows,
        "duplicates_collapsed": duplicates_collapsed,
        "warnings": warnings[:20],
    }


def _existing_records(cursor, campaign_id, usernames):
    cursor.execute(
        """
        select instagram_username_normalized
        from public.creators
        where instagram_username_normalized = any(%s)
        """,
        (usernames,),
    )
    creators = {row["instagram_username_normalized"] for row in cursor.fetchall()}
    cursor.execute(
        """
        select c.instagram_username_normalized
        from public.campaign_participants p
        join public.creators c on c.creator_id = p.creator_id
        where p.campaign_id = %s
          and c.instagram_username_normalized = any(%s)
        """,
        (campaign_id, usernames),
    )
    participants = {row["instagram_username_normalized"] for row in cursor.fetchall()}
    return creators, participants


def _import_entries(campaign_id, entries):
    usernames = [entry["username"] for entry in entries]
    with connect_database() as connection:
        with connection.cursor() as cursor:
            existing_creators, existing_participants = _existing_records(
                cursor, campaign_id, usernames
            )
            for entry in entries:
                cursor.execute(
                    """
                    with upserted_creator as (
                      insert into public.creators (
                        instagram_username, instagram_profile_url
                      ) values (%s, %s)
                      on conflict (instagram_username_normalized) do update set
                        instagram_username = excluded.instagram_username,
                        instagram_profile_url = coalesce(
                          excluded.instagram_profile_url,
                          creators.instagram_profile_url
                        )
                      returning creator_id
                    )
                    insert into public.campaign_participants (
                      campaign_id, creator_id, product_id, product_name,
                      screening_status, source_provider, source_registration_key
                    )
                    select %s, creator_id, %s, %s, 'eligible', 'google_sheets', %s
                    from upserted_creator
                    on conflict (campaign_id, creator_id) do update set
                      product_id = coalesce(
                        excluded.product_id,
                        campaign_participants.product_id
                      ),
                      product_name = coalesce(
                        excluded.product_name,
                        campaign_participants.product_name
                      ),
                      source_provider = excluded.source_provider,
                      source_registration_key = excluded.source_registration_key
                    returning participant_id
                    """,
                    (
                        entry["username"],
                        entry["profile_url"],
                        campaign_id,
                        entry["product_id"],
                        entry["product_name"],
                        entry["source_key"],
                    ),
                )
        connection.commit()

    return {
        "creators_created": len(set(usernames) - existing_creators),
        "creators_updated": len(set(usernames) & existing_creators),
        "participants_created": len(set(usernames) - existing_participants),
        "participants_updated": len(set(usernames) & existing_participants),
    }


def handle_import(handler):
    body = _read_body(handler)
    if not isinstance(body, dict):
        raise ValueError("需要 JSON 请求内容")
    campaign_id = str(body.get("campaign_id") or "").strip()
    if not campaign_id:
        raise ValueError("缺少 campaign_id")
    if body.get("confirmed_eligible") is not True:
        raise ValueError("仅允许导入已人工确认通过筛选的达人")

    campaign = _load_campaign(campaign_id)
    if not campaign:
        raise ValueError("Campaign 不存在")
    sheet_id, worksheet_name, dedicated = _sheet_settings(campaign_id)
    if not dedicated or not sheet_id:
        raise ValueError("本 Campaign 尚未配置独立 Google Sheet")

    registrations, warning = _read_registrations_from_sheets(campaign_id)
    if warning:
        _respond(handler, 502, {"status": "error", "message": warning})
        return
    if len(registrations) > MAX_IMPORT_ROWS:
        raise ValueError(f"一次最多导入 {MAX_IMPORT_ROWS} 行报名数据")

    prepared = _prepare_rows(
        campaign_id, campaign, sheet_id, worksheet_name, registrations
    )
    entries = prepared.pop("entries")
    counts = {
        "creators_created": 0,
        "creators_updated": 0,
        "participants_created": 0,
        "participants_updated": 0,
    }
    if entries:
        counts = _import_entries(campaign_id, entries)

    _respond(handler, 200, {
        "status": "success",
        "data": {
            "rows_read": len(registrations),
            "imported_rows": len(entries),
            "invalid_count": len(prepared["invalid_rows"]),
            **prepared,
            **counts,
        },
    })
