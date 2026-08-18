"""Shared PostgreSQL helpers for VEIMIA UGC Hub serverless APIs."""

import os

try:
    import psycopg
    from psycopg.rows import dict_row
    PSYCOPG_AVAILABLE = True
except ImportError:
    psycopg = None
    dict_row = None
    PSYCOPG_AVAILABLE = False


class DatabaseUnavailableError(RuntimeError):
    pass


def get_database_url():
    return str(os.environ.get("DATABASE_URL") or "").strip()


def _postgres_parameters():
    return {
        "host": str(os.environ.get("PGHOST") or "").strip(),
        "port": str(os.environ.get("PGPORT") or "5432").strip(),
        "dbname": str(os.environ.get("PGDATABASE") or "postgres").strip(),
        "user": str(os.environ.get("PGUSER") or "").strip(),
        "password": str(os.environ.get("PGPASSWORD") or ""),
        "sslmode": str(os.environ.get("PGSSLMODE") or "require").strip(),
    }


def database_configured():
    parameters = _postgres_parameters()
    return PSYCOPG_AVAILABLE and bool(
        get_database_url() or (
            parameters["host"] and parameters["user"] and parameters["password"]
        )
    )


def connect_database():
    """Create a short-lived connection suitable for Vercel serverless."""
    if not PSYCOPG_AVAILABLE:
        raise DatabaseUnavailableError("PostgreSQL driver is not installed")

    database_url = get_database_url()
    parameters = _postgres_parameters()
    if not database_url and not (
        parameters["host"] and parameters["user"] and parameters["password"]
    ):
        raise DatabaseUnavailableError("PostgreSQL environment variables are not configured")

    try:
        connection_target = (database_url,) if database_url else ()
        connection_options = {} if database_url else parameters
        return psycopg.connect(
            *connection_target,
            **connection_options,
            row_factory=dict_row,
            connect_timeout=8,
            prepare_threshold=None,
        )
    except Exception as error:
        raise DatabaseUnavailableError("Database connection failed") from error
