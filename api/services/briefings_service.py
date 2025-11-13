from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, HttpUrl
import snowflake.connector

from services.db import execute, execute_and_fetchone, fetch_dicts


class Briefing(BaseModel):
    id: str
    user_id: str
    name: str
    description: str | None
    status: str
    prompt: str
    primary_links: list[HttpUrl]
    created_at: datetime
    updated_at: datetime
    last_run_at: datetime | None


def create_briefing(
    name: str,
    prompt: str,
    seed_links: list[str],
    description: str | None = None,
    user_id: str = "user_0",  # Placeholder until auth is ready
    conn: Optional[snowflake.connector.SnowflakeConnection] = None,
) -> Briefing:
    """Creates a new briefing record in Snowflake."""
    # Convert list to JSON string for VARIANT column
    links_json = json.dumps(seed_links)
    
    # Use SELECT with PARSE_JSON instead of VALUES
    # This allows PARSE_JSON to work with parameterized queries
    query = """
        INSERT INTO AI_NW_SUMM_BRIEFINGS (user_id, name, description, prompt, primary_links, status)
        SELECT %(user_id)s, %(name)s, %(description)s, %(prompt)s, PARSE_JSON(%(links_json)s), 'draft'
    """
    execute(query, {
        "user_id": user_id,
        "name": name,
        "description": description,
        "prompt": prompt,
        "links_json": links_json
    }, conn=conn)
    
    # This is not ideal as it requires a second query.
    # A better approach would be to use RETURNING if Snowflake version supports it
    # or another strategy to get the created record.
    # For now, we fetch the most recently created one by this user.
    # This has potential race conditions.
    
    # Assuming name is unique for a user for now.
    created_query = """
        SELECT id, user_id, name, description, status, prompt, primary_links, created_at, updated_at, last_run_at
        FROM AI_NW_SUMM_BRIEFINGS
        WHERE user_id = %(user_id)s AND name = %(name)s
        ORDER BY created_at DESC
        LIMIT 1;
    """
    rows = fetch_dicts(created_query, {"user_id": user_id, "name": name}, conn=conn)
    if not rows:
        raise Exception("Failed to retrieve created briefing.") # Or a more specific exception
        
    row = rows[0]
    row['primary_links'] = json.loads(row['primary_links'])
    return Briefing(**row)


def get_briefing_by_id(briefing_id: str, conn: Optional[snowflake.connector.SnowflakeConnection] = None) -> Briefing | None:
    """Retrieves a single briefing by its ID."""
    query = """
        SELECT id, user_id, name, description, status, prompt, primary_links, created_at, updated_at, last_run_at
        FROM AI_NW_SUMM_BRIEFINGS
        WHERE id = %(briefing_id)s;
    """
    rows = fetch_dicts(query, {"briefing_id": briefing_id}, conn=conn)
    if not rows:
        return None
    
    row = rows[0]
    row['primary_links'] = json.loads(row['primary_links'])
    return Briefing(**row)


def list_briefings(
    status: str | None = None, 
    limit: int = 20, 
    user_id: str | None = None,
    conn: Optional[snowflake.connector.SnowflakeConnection] = None
) -> list[Briefing]:
    """Lists all briefings, with optional status filtering and user filtering."""
    params = {}
    query = "SELECT id, user_id, name, description, status, prompt, primary_links, created_at, updated_at, last_run_at FROM AI_NW_SUMM_BRIEFINGS"
    conditions = []
    if user_id:
        conditions.append("user_id = %(user_id)s")
        params["user_id"] = user_id
    if status:
        conditions.append("status = %(status)s")
        params["status"] = status
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY created_at DESC LIMIT %(limit)s;"
    params["limit"] = limit

    rows = fetch_dicts(query, params, conn=conn)
    
    for row in rows:
        row['primary_links'] = json.loads(row['primary_links'])
        
    return [Briefing(**row) for row in rows]


def update_briefing(
    briefing_id: str,
    name: str | None = None,
    description: str | None = None,
    prompt: str | None = None,
    seed_links: list[str] | None = None,
    status: str | None = None,
    conn: Optional[snowflake.connector.SnowflakeConnection] = None
) -> Briefing | None:
    """Updates a briefing record in Snowflake. Returns None if not found."""
    # First check if briefing exists
    briefing = get_briefing_by_id(briefing_id, conn=conn)
    if not briefing:
        return None
    
    # Build update query dynamically based on provided fields
    updates = []
    params = {"briefing_id": briefing_id}
    
    if name is not None:
        updates.append("name = %(name)s")
        params["name"] = name
    
    if description is not None:
        updates.append("description = %(description)s")
        params["description"] = description
    
    if prompt is not None:
        updates.append("prompt = %(prompt)s")
        params["prompt"] = prompt
    
    if seed_links is not None:
        updates.append("primary_links = PARSE_JSON(%(links_json)s)")
        params["links_json"] = json.dumps(seed_links)
    
    if status is not None:
        updates.append("status = %(status)s")
        params["status"] = status
    
    if not updates:
        # No updates to make, return existing briefing
        return briefing
    
    # Always update updated_at
    updates.append("updated_at = CURRENT_TIMESTAMP()")
    
    query = f"""
        UPDATE AI_NW_SUMM_BRIEFINGS
        SET {', '.join(updates)}
        WHERE id = %(briefing_id)s;
    """
    execute(query, params, conn=conn)
    
    # Fetch and return updated briefing
    return get_briefing_by_id(briefing_id, conn=conn)


def update_briefing_last_run(briefing_id: str, conn: Optional[snowflake.connector.SnowflakeConnection] = None) -> None:
    """Updates the last_run_at timestamp for a briefing."""
    query = """
        UPDATE AI_NW_SUMM_BRIEFINGS
        SET last_run_at = CURRENT_TIMESTAMP()
        WHERE id = %(briefing_id)s;
    """
    execute(query, {"briefing_id": briefing_id}, conn=conn)


def delete_briefing(briefing_id: str, conn: Optional[snowflake.connector.SnowflakeConnection] = None) -> bool:
    """Deletes a briefing by ID. Returns True if deleted, False if not found."""
    # First check if briefing exists
    briefing = get_briefing_by_id(briefing_id, conn=conn)
    if not briefing:
        return False
    
    query = """
        DELETE FROM AI_NW_SUMM_BRIEFINGS
        WHERE id = %(briefing_id)s;
    """
    execute(query, {"briefing_id": briefing_id}, conn=conn)
    return True
