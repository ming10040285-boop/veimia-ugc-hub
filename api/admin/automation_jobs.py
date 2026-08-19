"""Persistent administrator-started automation job API."""

import json
import logging
import re
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse
from uuid import UUID

from api._admin_auth import AdminAuthError, require_admin
from api._db import DatabaseUnavailableError, connect_database
from api.admin.campaigns import _load_campaign

logger = logging.getLogger(__name__)

JOB_TYPES = {"COMMENT_IMPORT", "PROFILE_SCREENING", "UGC_MONITORING"}
JOB_STATUSES = {
    "queued", "running", "stop_requested", "succeeded", "failed", "stopped"
}
RETRYABLE_STATUSES = {"failed", "stopped"}
CAMPAIGN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
MAX_LIMIT = 200


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


def _required_job_id(body):
    value = str(body.get("job_id") or "").strip()
    if not value:
        raise ValueError("缺少 job_id")
    try:
        return str(UUID(value))
    except ValueError as error:
        raise ValueError("job_id 无效") from error


def _validate_campaign(campaign_id):
    if not CAMPAIGN_ID_PATTERN.fullmatch(campaign_id):
        raise ValueError("Campaign ID 无效")
    if _load_campaign(campaign_id) is None:
        raise ValueError("Campaign 不存在")


def _handle_get(handler):
    params = parse_qs(urlparse(handler.path).query)
    limit, offset = _pagination(params)
    filters = []
    values = []

    campaign_id = str(params.get("campaign_id", [""])[0]).strip()
    job_type = str(params.get("job_type", [""])[0]).strip()
    status = str(params.get("status", [""])[0]).strip()
    if campaign_id:
        filters.append("campaign_id = %s")
        values.append(campaign_id)
    if job_type:
        if job_type not in JOB_TYPES:
            raise ValueError("任务类型无效")
        filters.append("job_type = %s")
        values.append(job_type)
    if status:
        if status not in JOB_STATUSES:
            raise ValueError("任务状态无效")
        filters.append("status = %s")
        values.append(status)

    where = "where " + " and ".join(filters) if filters else ""
    with connect_database() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                select * from public.automation_jobs
                {where}
                order by created_at desc
                limit %s offset %s
                """,
                tuple(values + [limit, offset]),
            )
            jobs = cursor.fetchall()
            cursor.execute(
                f"select count(*) as total from public.automation_jobs {where}",
                tuple(values),
            )
            total = cursor.fetchone()["total"]
    _respond(handler, 200, {
        "status": "success",
        "data": jobs,
        "page": {"limit": limit, "offset": offset, "total": total},
    })


def _start_job(handler, body):
    campaign_id = str(body.get("campaign_id") or "").strip()
    job_type = str(body.get("job_type") or "").strip()
    job_input = body.get("input", {})
    if not campaign_id:
        raise ValueError("请选择 Campaign")
    _validate_campaign(campaign_id)
    if job_type not in JOB_TYPES:
        raise ValueError("任务类型无效")
    if not isinstance(job_input, dict):
        raise ValueError("任务 input 必须是 JSON 对象")

    with connect_database() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                insert into public.automation_jobs (campaign_id, job_type, input)
                values (%s, %s, %s::jsonb)
                returning *
                """,
                (campaign_id, job_type, json.dumps(job_input, ensure_ascii=False)),
            )
            job = cursor.fetchone()
        connection.commit()
    _respond(handler, 201, {"status": "success", "data": job})


def _stop_job(handler, body):
    job_id = _required_job_id(body)
    with connect_database() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "select * from public.automation_jobs where job_id = %s for update",
                (job_id,),
            )
            job = cursor.fetchone()
            if not job:
                _respond(handler, 404, {"status": "error", "message": "任务不存在"})
                return
            if job["status"] == "queued":
                cursor.execute(
                    """
                    update public.automation_jobs
                    set status = 'stopped', finished_at = now(), lease_expires_at = null
                    where job_id = %s returning *
                    """,
                    (job_id,),
                )
                job = cursor.fetchone()
            elif job["status"] == "running":
                cursor.execute(
                    """
                    update public.automation_jobs
                    set status = 'stop_requested'
                    where job_id = %s returning *
                    """,
                    (job_id,),
                )
                job = cursor.fetchone()
            elif job["status"] != "stop_requested":
                raise ValueError("当前任务状态不能停止")
        connection.commit()
    _respond(handler, 200, {"status": "success", "data": job})


def _retry_job(handler, body):
    job_id = _required_job_id(body)
    with connect_database() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "select * from public.automation_jobs where job_id = %s for update",
                (job_id,),
            )
            original = cursor.fetchone()
            if not original:
                _respond(handler, 404, {"status": "error", "message": "任务不存在"})
                return
            if original["status"] not in RETRYABLE_STATUSES:
                raise ValueError("只有失败或已停止的任务可以重试")
            cursor.execute(
                """
                insert into public.automation_jobs (
                  campaign_id, job_type, input, retry_of_job_id
                ) values (%s, %s, %s::jsonb, %s)
                returning *
                """,
                (
                    original["campaign_id"],
                    original["job_type"],
                    json.dumps(original["input"] or {}, ensure_ascii=False),
                    job_id,
                ),
            )
            job = cursor.fetchone()
        connection.commit()
    _respond(handler, 201, {"status": "success", "data": job})


def _handle_post(handler):
    body = _read_body(handler)
    if not isinstance(body, dict):
        raise ValueError("需要 JSON 请求内容")
    action = parse_qs(urlparse(handler.path).query).get("action", [""])[0]
    if action == "start":
        _start_job(handler, body)
    elif action == "stop":
        _stop_job(handler, body)
    elif action == "retry":
        _retry_job(handler, body)
    else:
        raise ValueError("不支持的任务操作")


def _handle_patch(handler):
    raise ValueError("任务状态不能直接修改")


def _dispatch(handler, action):
    try:
        require_admin(handler)
        action(handler)
    except AdminAuthError as error:
        _respond(handler, error.status_code, {"status": "error", "message": str(error)})
    except DatabaseUnavailableError:
        _respond(handler, 503, {"status": "error", "message": "任务数据库未配置"})
    except (json.JSONDecodeError, ValueError) as error:
        _respond(handler, 400, {"status": "error", "message": str(error)})
    except Exception:
        logger.exception("Automation job API request failed")
        _respond(handler, 500, {"status": "error", "message": "任务请求失败"})


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Allow", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.end_headers()

    def do_GET(self):
        _dispatch(self, _handle_get)

    def do_POST(self):
        _dispatch(self, _handle_post)