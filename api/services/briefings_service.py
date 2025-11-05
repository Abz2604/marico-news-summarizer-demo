from __future__ import annotations

import json
from datetime import datetime

from pydantic import BaseModel, HttpUrl

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
    })
    
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
    rows = fetch_dicts(created_query, {"user_id": user_id, "name": name})
    if not rows:
        raise Exception("Failed to retrieve created briefing.") # Or a more specific exception
        
    row = rows[0]
    row['primary_links'] = json.loads(row['primary_links'])
    return Briefing(**row)


def get_briefing_by_id(briefing_id: str) -> Briefing | None:
    """Retrieves a single briefing by its ID."""
    query = """
        SELECT id, user_id, name, description, status, prompt, primary_links, created_at, updated_at, last_run_at
        FROM AI_NW_SUMM_BRIEFINGS
        WHERE id = %(briefing_id)s;
    """
    rows = fetch_dicts(query, {"briefing_id": briefing_id})
    if not rows:
        return None
    
    row = rows[0]
    row['primary_links'] = json.loads(row['primary_links'])
    return Briefing(**row)


def list_briefings(status: str | None = None, limit: int = 20) -> list[Briefing]:
    """Lists all briefings, with optional status filtering."""
    params = {}
    query = "SELECT id, user_id, name, description, status, prompt, primary_links, created_at, updated_at, last_run_at FROM AI_NW_SUMM_BRIEFINGS"
    if status:
        query += " WHERE status = %(status)s"
        params["status"] = status
    query += " ORDER BY created_at DESC LIMIT %(limit)s;"
    params["limit"] = limit

    rows = fetch_dicts(query, params)
    
    for row in rows:
        row['primary_links'] = json.loads(row['primary_links'])
        
    return [Briefing(**row) for row in rows]


def update_briefing_last_run(briefing_id: str) -> None:
    """Updates the last_run_at timestamp for a briefing."""
    query = """
        UPDATE AI_NW_SUMM_BRIEFINGS
        SET last_run_at = CURRENT_TIMESTAMP()
        WHERE id = %(briefing_id)s;
    """
    execute(query, {"briefing_id": briefing_id})
