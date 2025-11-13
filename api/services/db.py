"""Placeholder Snowflake connector.

Phase 0 uses in-memory repositories. This module acts as a placeholder for
future Snowflake connectivity and exposes a minimal interface so call sites
do not change when the real connector is implemented.
"""

import logging
import os
import threading
import time
from contextlib import contextmanager
from typing import Optional
from queue import Queue, Empty

import snowflake.connector
from fastapi import Depends
from config import get_settings


class SnowflakeConnectionError(Exception):
    pass


class ConnectionPool:
    """Thread-safe connection pool for Snowflake connections."""
    
    def __init__(self, max_size: int = 10, min_size: int = 1):
        self.max_size = max_size
        self.min_size = min_size
        self._pool: Queue = Queue(maxsize=max_size)
        self._active_count = 0  # Connections currently in use or in pool
        self._lock = threading.Lock()
        self._connection_times = {}  # Track when connections were created
        
        # Pre-create minimum connections
        for _ in range(min_size):
            try:
                conn = self._create_connection()
                self._pool.put(conn)
            except Exception as e:
                logging.warning(f"Failed to pre-create connection: {e}")
        
        logging.info(f"Connection pool initialized (min={min_size}, max={max_size}, pre-created={self._pool.qsize()})")
    
    def _create_connection(self):
        """Create a new Snowflake connection."""
        conn = snowflake.connector.connect(**_conn_kwargs())
        
        # Set context
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
            logging.warning(f"Failed to set Snowflake context: {e}")
        finally:
            if cur:
                cur.close()
        
        with self._lock:
            self._active_count += 1
            self._connection_times[id(conn)] = time.time()
        
        return conn
    
    def get_connection(self, timeout: float = 5.0):
        """Get a connection from the pool."""
        try:
            # Try to get from pool (non-blocking)
            conn = self._pool.get_nowait()
            
            # Lightweight validation - just check if connection is closed
            # Full validation (SELECT 1) is too slow and will be caught on first use anyway
            if conn.is_closed():
                # Connection is closed, create new one
                logging.debug("Pooled connection is closed, creating new one")
                try:
                    conn.close()
                except:
                    pass
                with self._lock:
                    self._active_count -= 1
                    if id(conn) in self._connection_times:
                        del self._connection_times[id(conn)]
                return self._create_connection()
            
            logging.debug("Reused connection from pool")
            return conn
        except Empty:
            # Pool is empty, create new connection if under max
            with self._lock:
                if self._active_count < self.max_size:
                    logging.debug("Pool empty, creating new connection")
                    return self._create_connection()
            
            # Wait for a connection to become available
            try:
                conn = self._pool.get(timeout=timeout)
                logging.debug("Got connection from pool after wait")
                return conn
            except Empty:
                raise SnowflakeConnectionError("Connection pool timeout - all connections in use")
    
    def return_connection(self, conn):
        """Return a connection to the pool."""
        if conn is None:
            return
        
        # Skip validation for performance - validate only when getting from pool if needed
        # Check if pool has space
        try:
            if not self._pool.full():
                self._pool.put_nowait(conn)
                logging.debug("Connection returned to pool")
            else:
                # Pool is full, close this connection
                conn.close()
                with self._lock:
                    self._active_count -= 1
                    if id(conn) in self._connection_times:
                        del self._connection_times[id(conn)]
                logging.debug("Pool full, closed connection")
        except Exception as e:
            # Pool operation failed, close connection
            logging.debug(f"Failed to return connection to pool, closing: {e}")
            try:
                conn.close()
            except:
                pass
            with self._lock:
                self._active_count -= 1
                if id(conn) in self._connection_times:
                    del self._connection_times[id(conn)]


# Global connection pool instance
_connection_pool: Optional[ConnectionPool] = None
_pool_lock = threading.Lock()


def _get_pool() -> ConnectionPool:
    """Get or create the global connection pool."""
    global _connection_pool
    if _connection_pool is None:
        with _pool_lock:
            if _connection_pool is None:
                _connection_pool = ConnectionPool(max_size=10, min_size=1)
    return _connection_pool


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
        logging.debug("Snowflake connection established.")
        
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
            logging.debug("Snowflake connection closed.")


def get_db_connection():
    """
    FastAPI dependency that provides a request-scoped Snowflake connection.
    Connections are obtained from a pool and returned to the pool after use,
    significantly improving performance by reusing connections.
    """
    import uuid
    request_id = str(uuid.uuid4())[:8]
    conn = None
    pool = _get_pool()
    
    try:
        # Get connection from pool
        conn = pool.get_connection()
        logging.debug(f"[{request_id}] Connection obtained from pool")
        
        yield conn
    except snowflake.connector.Error as e:
        logging.exception(f"[{request_id}] Snowflake connection failed: {e}")
        raise SnowflakeConnectionError(f"Failed to connect to Snowflake: {e}") from e
    except Exception as e:
        logging.exception(f"[{request_id}] Unexpected error: {e}")
        raise
    finally:
        if conn:
            # Return connection to pool (reuse for next request)
            pool.return_connection(conn)
            logging.debug(f"[{request_id}] Connection returned to pool")


def fetch_dicts(sql: str, params: dict | None = None, conn: Optional[snowflake.connector.SnowflakeConnection] = None) -> list[dict]:
    """
    Executes a SQL query and returns a list of dictionaries.
    
    Args:
        sql: SQL query string
        params: Optional query parameters
        conn: Optional existing connection. If provided, uses it; otherwise creates a new one.
    """
    if conn:
        # Use provided connection (reusing request-scoped connection)
        logging.debug(f"Reusing connection for query: {sql[:50]}...")
        with conn.cursor() as cur:
            cur.execute(sql, params or {})
            columns = [col[0].lower() for col in cur.description]
            return [dict(zip(columns, row)) for row in cur.fetchall()]
    else:
        # Create new connection (backward compatibility)
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params or {})
                columns = [col[0].lower() for col in cur.description]
                return [dict(zip(columns, row)) for row in cur.fetchall()]


def execute(sql: str, params: dict | tuple | None = None, conn: Optional[snowflake.connector.SnowflakeConnection] = None) -> None:
    """
    Executes a DML statement. Accepts dict or tuple params.
    
    Args:
        sql: SQL statement string
        params: Optional query parameters
        conn: Optional existing connection. If provided, uses it; otherwise creates a new one.
    """
    if conn:
        # Use provided connection
        with conn.cursor() as cur:
            if params is None:
                cur.execute(sql)
            elif isinstance(params, dict):
                cur.execute(sql, params)
            else:
                cur.execute(sql, params)
            conn.commit()
    else:
        # Create new connection (backward compatibility)
        with connect() as conn:
            with conn.cursor() as cur:
                if params is None:
                    cur.execute(sql)
                elif isinstance(params, dict):
                    cur.execute(sql, params)
                else:
                    cur.execute(sql, params)
                conn.commit()

def execute_and_fetchone(sql: str, params: dict | tuple | None = None, conn: Optional[snowflake.connector.SnowflakeConnection] = None) -> tuple | None:
    """
    Executes a query and returns a single row. Accepts dict or tuple params.
    
    Args:
        sql: SQL query string
        params: Optional query parameters
        conn: Optional existing connection. If provided, uses it; otherwise creates a new one.
    """
    if conn:
        # Use provided connection
        with conn.cursor() as cur:
            if params is None:
                cur.execute(sql)
            elif isinstance(params, dict):
                cur.execute(sql, params)
            else:
                cur.execute(sql, params)
            return cur.fetchone()
    else:
        # Create new connection (backward compatibility)
        with connect() as conn:
            with conn.cursor() as cur:
                if params is None:
                    cur.execute(sql)
                elif isinstance(params, dict):
                    cur.execute(sql, params)
                else:
                    cur.execute(sql, params)
                return cur.fetchone()


