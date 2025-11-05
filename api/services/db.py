"""Placeholder Snowflake connector.

Phase 0 uses in-memory repositories. This module acts as a placeholder for
future Snowflake connectivity and exposes a minimal interface so call sites
do not change when the real connector is implemented.
"""

import logging
import os
from contextlib import contextmanager

import snowflake.connector
from config import get_settings


class SnowflakeConnectionError(Exception):
    pass


def _conn_kwargs() -> dict:
    """Builds the connection keyword arguments from environment settings."""
    settings = get_settings()
    required_keys = [
        "snowflake_account",
        "snowflake_user",
        "snowflake_password",
        "snowflake_database",
        "snowflake_schema",
    ]
    
    missing_keys = [key for key in required_keys if not getattr(settings, key)]
    if missing_keys:
        raise SnowflakeConnectionError(f"Missing Snowflake credentials: {', '.join(missing_keys)}")

    kwargs = {
        "account": settings.snowflake_account,
        "user": settings.snowflake_user,
        "password": settings.snowflake_password,
        "database": settings.snowflake_database,
        "schema": settings.snowflake_schema,
    }
    if settings.snowflake_role:
        kwargs["role"] = settings.snowflake_role
    if settings.snowflake_warehouse:
        kwargs["warehouse"] = settings.snowflake_warehouse
    return kwargs


@contextmanager
def connect():
    """Provides a managed Snowflake connection with proper context setup."""
    conn = None
    try:
        conn = snowflake.connector.connect(**_conn_kwargs())
        logging.info("Snowflake connection established.")
        
        # Set context immediately after connecting (best-effort)
        settings = get_settings()
        cur = None
        try:
            cur = conn.cursor()
            if settings.snowflake_role:
                cur.execute(f'USE ROLE "{settings.snowflake_role}"')
            if settings.snowflake_warehouse:
                cur.execute(f'USE WAREHOUSE "{settings.snowflake_warehouse}"')
            if settings.snowflake_database:
                cur.execute(f'USE DATABASE "{settings.snowflake_database}"')
            if settings.snowflake_schema:
                cur.execute(f'USE SCHEMA "{settings.snowflake_schema}"')
        except Exception as e:
            # Swallow context setup errors so fully qualified SQL still works
            logging.warning(f"Failed to set Snowflake context: {e}")
        finally:
            if cur:
                cur.close()
        
        yield conn
    except snowflake.connector.Error as e:
        logging.exception(f"Snowflake connection failed: {e}")
        raise SnowflakeConnectionError(f"Failed to connect to Snowflake: {e}") from e
    finally:
        if conn:
            conn.close()
            logging.info("Snowflake connection closed.")


def fetch_dicts(sql: str, params: dict | None = None) -> list[dict]:
    """Executes a SQL query and returns a list of dictionaries."""
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or {})
            columns = [col[0].lower() for col in cur.description]
            return [dict(zip(columns, row)) for row in cur.fetchall()]


def execute(sql: str, params: dict | tuple | None = None) -> None:
    """Executes a DML statement. Accepts dict or tuple params."""
    with connect() as conn:
        with conn.cursor() as cur:
            if params is None:
                cur.execute(sql)
            elif isinstance(params, dict):
                cur.execute(sql, params)
            else:
                cur.execute(sql, params)
            conn.commit()

def execute_and_fetchone(sql: str, params: dict | tuple | None = None) -> tuple | None:
    """Executes a query and returns a single row. Accepts dict or tuple params."""
    with connect() as conn:
        with conn.cursor() as cur:
            if params is None:
                cur.execute(sql)
            elif isinstance(params, dict):
                cur.execute(sql, params)
            else:
                cur.execute(sql, params)
            return cur.fetchone()


