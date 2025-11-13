from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr
import snowflake.connector

from services.db import execute, fetch_dicts


class User(BaseModel):
    id: str
    email: str
    display_name: str | None
    role: str
    created_at: datetime
    updated_at: datetime


def get_user_by_email(email: str, conn: Optional[snowflake.connector.SnowflakeConnection] = None) -> User | None:
    """Retrieves a user by email address."""
    query = """
        SELECT id, email, display_name, role, created_at, updated_at
        FROM AI_NW_SUMM_USERS
        WHERE email = %(email)s;
    """
    rows = fetch_dicts(query, {"email": email}, conn=conn)
    if not rows:
        return None
    
    return User(**rows[0])


def get_user_by_id(user_id: str, conn: Optional[snowflake.connector.SnowflakeConnection] = None) -> User | None:
    """Retrieves a user by ID."""
    query = """
        SELECT id, email, display_name, role, created_at, updated_at
        FROM AI_NW_SUMM_USERS
        WHERE id = %(user_id)s;
    """
    rows = fetch_dicts(query, {"user_id": user_id}, conn=conn)
    if not rows:
        return None
    
    return User(**rows[0])


def get_user_password_hash(email: str, conn: Optional[snowflake.connector.SnowflakeConnection] = None) -> str | None:
    """Retrieves the hashed password for a user by email."""
    query = """
        SELECT hashed_password
        FROM AI_NW_SUMM_USERS
        WHERE email = %(email)s;
    """
    rows = fetch_dicts(query, {"email": email}, conn=conn)
    if not rows:
        return None
    
    return rows[0]['hashed_password']


def create_user(
    email: str,
    hashed_password: str,
    display_name: str | None = None,
    role: str = "member",
    conn: Optional[snowflake.connector.SnowflakeConnection] = None,
) -> User:
    """Creates a new user record in Snowflake."""
    query = """
        INSERT INTO AI_NW_SUMM_USERS (email, hashed_password, display_name, role)
        VALUES (%(email)s, %(hashed_password)s, %(display_name)s, %(role)s)
    """
    execute(query, {
        "email": email,
        "hashed_password": hashed_password,
        "display_name": display_name,
        "role": role
    }, conn=conn)
    
    # Fetch the created user
    created_query = """
        SELECT id, email, display_name, role, created_at, updated_at
        FROM AI_NW_SUMM_USERS
        WHERE email = %(email)s
        ORDER BY created_at DESC
        LIMIT 1;
    """
    rows = fetch_dicts(created_query, {"email": email}, conn=conn)
    if not rows:
        raise Exception("Failed to retrieve created user.")
    
    return User(**rows[0])

