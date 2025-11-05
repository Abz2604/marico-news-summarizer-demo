from __future__ import annotations

import json
from datetime import datetime

from pydantic import BaseModel

from services.db import fetch_dicts, execute


class Campaign(BaseModel):
    id: str
    name: str
    status: str
    description: str | None
    briefing_ids: list[str]
    recipient_emails: list[str]
    schedule_description: str | None
    created_at: datetime
    updated_at: datetime


def get_campaign_by_id(campaign_id: str) -> Campaign | None:
    """Gets a single campaign by ID."""
    query = """
        SELECT id, name, status, description, briefing_ids, recipient_emails, schedule_description, created_at, updated_at
        FROM AI_NW_SUMM_CAMPAIGNS
        WHERE id = %(campaign_id)s;
    """
    rows = fetch_dicts(query, {"campaign_id": campaign_id})
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
    description: str | None = None,
    schedule_description: str | None = None,
    status: str = "active"
) -> Campaign:
    """Creates a new campaign record in Snowflake."""
    # Convert lists to JSON strings for VARIANT columns
    briefings_json = json.dumps(briefing_ids)
    recipients_json = json.dumps(recipient_emails)
    
    # Use SELECT with PARSE_JSON instead of VALUES
    query = """
        INSERT INTO AI_NW_SUMM_CAMPAIGNS (name, status, description, briefing_ids, recipient_emails, schedule_description)
        SELECT %(name)s, %(status)s, %(description)s, PARSE_JSON(%(briefings_json)s), PARSE_JSON(%(recipients_json)s), %(schedule_description)s
    """
    execute(query, {
        "name": name,
        "status": status,
        "description": description,
        "briefings_json": briefings_json,
        "recipients_json": recipients_json,
        "schedule_description": schedule_description
    })
    
    # Fetch the created campaign
    created_query = """
        SELECT id, name, status, description, briefing_ids, recipient_emails, schedule_description, created_at, updated_at
        FROM AI_NW_SUMM_CAMPAIGNS
        WHERE name = %(name)s
        ORDER BY created_at DESC
        LIMIT 1;
    """
    rows = fetch_dicts(created_query, {"name": name})
    if not rows:
        raise Exception("Failed to retrieve created campaign.")
    
    row = rows[0]
    row['briefing_ids'] = json.loads(row['briefing_ids'])
    row['recipient_emails'] = json.loads(row['recipient_emails'])
    return Campaign(**row)


def list_campaigns(limit: int = 20) -> list[Campaign]:
    """Lists all campaigns."""
    query = """
        SELECT id, name, status, description, briefing_ids, recipient_emails, schedule_description, created_at, updated_at
        FROM AI_NW_SUMM_CAMPAIGNS
        ORDER BY created_at DESC
        LIMIT %(limit)s;
    """
    rows = fetch_dicts(query, {"limit": limit})
    
    for row in rows:
        row['briefing_ids'] = json.loads(row['briefing_ids'])
        row['recipient_emails'] = json.loads(row['recipient_emails'])
        
    return [Campaign(**row) for row in rows]
