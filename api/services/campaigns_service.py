from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from pydantic import BaseModel
import snowflake.connector

from services.db import fetch_dicts, execute


class Campaign(BaseModel):
    id: str
    user_id: str
    name: str
    status: str
    description: str | None
    briefing_ids: list[str]
    recipient_emails: list[str]
    schedule_description: str | None
    created_at: datetime
    updated_at: datetime


def get_campaign_by_id(campaign_id: str, user_id: str | None = None, conn: Optional[snowflake.connector.SnowflakeConnection] = None) -> Campaign | None:
    """Gets a single campaign by ID. Optionally filters by user_id for security."""
    query = """
        SELECT id, user_id, name, status, description, briefing_ids, recipient_emails, schedule_description, created_at, updated_at
        FROM AI_NW_SUMM_CAMPAIGNS
        WHERE id = %(campaign_id)s
    """
    params = {"campaign_id": campaign_id}
    
    if user_id is not None:
        query += " AND user_id = %(user_id)s"
        params["user_id"] = user_id
    
    query += ";"
    
    rows = fetch_dicts(query, params, conn=conn)
    if not rows:
        return None
    
    row = rows[0]
    row['briefing_ids'] = json.loads(row['briefing_ids'])
    row['recipient_emails'] = json.loads(row['recipient_emails'])
    return Campaign(**row)


def create_campaign(
    name: str,
    briefing_ids: list[str],
    recipient_emails: list[str],
    user_id: str,
    description: str | None = None,
    schedule_description: str | None = None,
    status: str = "active",
    conn: Optional[snowflake.connector.SnowflakeConnection] = None
) -> Campaign:
    """Creates a new campaign record in Snowflake."""
    # Convert lists to JSON strings for VARIANT columns
    briefings_json = json.dumps(briefing_ids)
    recipients_json = json.dumps(recipient_emails)
    
    # Use SELECT with PARSE_JSON instead of VALUES
    query = """
        INSERT INTO AI_NW_SUMM_CAMPAIGNS (user_id, name, status, description, briefing_ids, recipient_emails, schedule_description)
        SELECT %(user_id)s, %(name)s, %(status)s, %(description)s, PARSE_JSON(%(briefings_json)s), PARSE_JSON(%(recipients_json)s), %(schedule_description)s
    """
    execute(query, {
        "user_id": user_id,
        "name": name,
        "status": status,
        "description": description,
        "briefings_json": briefings_json,
        "recipients_json": recipients_json,
        "schedule_description": schedule_description
    }, conn=conn)
    
    # Fetch the created campaign
    created_query = """
        SELECT id, user_id, name, status, description, briefing_ids, recipient_emails, schedule_description, created_at, updated_at
        FROM AI_NW_SUMM_CAMPAIGNS
        WHERE user_id = %(user_id)s AND name = %(name)s
        ORDER BY created_at DESC
        LIMIT 1;
    """
    rows = fetch_dicts(created_query, {"user_id": user_id, "name": name}, conn=conn)
    if not rows:
        raise Exception("Failed to retrieve created campaign.")
    
    row = rows[0]
    row['briefing_ids'] = json.loads(row['briefing_ids'])
    row['recipient_emails'] = json.loads(row['recipient_emails'])
    return Campaign(**row)


def list_campaigns(user_id: str | None = None, limit: int = 20, conn: Optional[snowflake.connector.SnowflakeConnection] = None) -> list[Campaign]:
    """Lists campaigns. If user_id is provided, filters by user. If None, returns all campaigns (for admin/system use)."""
    query = """
        SELECT id, user_id, name, status, description, briefing_ids, recipient_emails, schedule_description, created_at, updated_at
        FROM AI_NW_SUMM_CAMPAIGNS
    """
    params = {"limit": limit}
    
    if user_id is not None:
        query += " WHERE user_id = %(user_id)s"
        params["user_id"] = user_id
    
    query += " ORDER BY created_at DESC LIMIT %(limit)s;"
    
    rows = fetch_dicts(query, params, conn=conn)
    
    for row in rows:
        row['briefing_ids'] = json.loads(row['briefing_ids'])
        row['recipient_emails'] = json.loads(row['recipient_emails'])
        
    return [Campaign(**row) for row in rows]


def update_campaign(
    campaign_id: str,
    user_id: str,
    name: str | None = None,
    description: str | None = None,
    briefing_ids: list[str] | None = None,
    recipient_emails: list[str] | None = None,
    schedule_description: str | None = None,
    status: str | None = None,
    conn: Optional[snowflake.connector.SnowflakeConnection] = None
) -> Campaign | None:
    """Updates a campaign record in Snowflake. Returns None if not found or user doesn't own it."""
    # First check if campaign exists and belongs to user
    campaign = get_campaign_by_id(campaign_id, user_id=user_id, conn=conn)
    if not campaign:
        return None
    
    # Build update query dynamically based on provided fields
    updates = []
    params = {"campaign_id": campaign_id}
    
    if name is not None:
        updates.append("name = %(name)s")
        params["name"] = name
    
    if description is not None:
        updates.append("description = %(description)s")
        params["description"] = description
    
    if briefing_ids is not None:
        updates.append("briefing_ids = PARSE_JSON(%(briefings_json)s)")
        params["briefings_json"] = json.dumps(briefing_ids)
    
    if recipient_emails is not None:
        updates.append("recipient_emails = PARSE_JSON(%(recipients_json)s)")
        params["recipients_json"] = json.dumps(recipient_emails)
    
    if schedule_description is not None:
        updates.append("schedule_description = %(schedule_description)s")
        params["schedule_description"] = schedule_description
    
    if status is not None:
        updates.append("status = %(status)s")
        params["status"] = status
    
    if not updates:
        # No updates to make, return existing campaign
        return campaign
    
    # Always update updated_at
    updates.append("updated_at = CURRENT_TIMESTAMP()")
    
    query = f"""
        UPDATE AI_NW_SUMM_CAMPAIGNS
        SET {', '.join(updates)}
        WHERE id = %(campaign_id)s;
    """
    execute(query, params, conn=conn)
    
    # Fetch and return updated campaign
    return get_campaign_by_id(campaign_id, user_id=user_id, conn=conn)


def delete_campaign(campaign_id: str, user_id: str, conn: Optional[snowflake.connector.SnowflakeConnection] = None) -> bool:
    """Deletes a campaign by ID. Returns True if deleted, False if not found or user doesn't own it."""
    # First check if campaign exists and belongs to user
    campaign = get_campaign_by_id(campaign_id, user_id=user_id, conn=conn)
    if not campaign:
        return False
    
    query = """
        DELETE FROM AI_NW_SUMM_CAMPAIGNS
        WHERE id = %(campaign_id)s AND user_id = %(user_id)s;
    """
    execute(query, {"campaign_id": campaign_id, "user_id": user_id}, conn=conn)
    return True
