from __future__ import annotations

import json
from datetime import datetime

from pydantic import BaseModel

from services.db import execute, execute_and_fetchone, fetch_dicts


class AgentRun(BaseModel):
    id: str
    briefing_id: str | None
    trigger_type: str | None
    status: str | None
    started_at: datetime
    completed_at: datetime | None
    error_message: str | None
    model: str | None
    token_usage_prompt: int | None
    token_usage_completion: int | None


class Summary(BaseModel):
    id: str
    agent_run_id: str
    briefing_id: str | None
    summary_markdown: str
    bullet_points: list[str]
    citations: list[dict]
    created_at: datetime


def create_agent_run(briefing_id: str, trigger_type: str = "manual") -> AgentRun:
    """Creates a new agent run record and returns its ID."""
    query = """
        INSERT INTO AI_NW_SUMM_AGENT_RUNS (briefing_id, trigger_type, status)
        VALUES (%(briefing_id)s, %(trigger_type)s, 'running')
    """
    execute(query, {"briefing_id": briefing_id, "trigger_type": trigger_type})

    # Fetch the created record to return it. This is not ideal because of potential race conditions.
    fetch_query = """
        SELECT id, briefing_id, trigger_type, status, started_at, completed_at, error_message, model, token_usage_prompt, token_usage_completion
        FROM AI_NW_SUMM_AGENT_RUNS
        WHERE briefing_id = %(briefing_id)s
        ORDER BY started_at DESC
        LIMIT 1;
    """
    rows = fetch_dicts(fetch_query, {"briefing_id": briefing_id})
    if not rows:
        raise Exception("Failed to retrieve created agent run.")
        
    return AgentRun(**rows[0])


def save_summary_and_finalize_run(
    run_id: str,
    briefing_id: str,
    summary_markdown: str,
    bullet_points: list[str],
    citations: list[dict],
    model: str,
) -> Summary:
    """Saves the summary and marks the agent run as complete."""
    
    # Convert lists/dicts to JSON strings
    bullets_json = json.dumps(bullet_points)
    citations_json = json.dumps(citations)
    
    # Use SELECT with PARSE_JSON instead of VALUES
    summary_query = """
        INSERT INTO AI_NW_SUMM_SUMMARIES (agent_run_id, briefing_id, summary_markdown, bullet_points, citations)
        SELECT %(run_id)s, %(briefing_id)s, %(summary_markdown)s, 
               PARSE_JSON(%(bullets_json)s), PARSE_JSON(%(citations_json)s)
    """
    
    run_update_query = """
        UPDATE AI_NW_SUMM_AGENT_RUNS
        SET status = 'succeeded', model = %(model)s, completed_at = CURRENT_TIMESTAMP()
        WHERE id = %(run_id)s;
    """
    
    execute(summary_query, {
        "run_id": run_id,
        "briefing_id": briefing_id,
        "summary_markdown": summary_markdown,
        "bullets_json": bullets_json,
        "citations_json": citations_json
    })
    execute(run_update_query, {"model": model, "run_id": run_id})

    # Fetch the created summary to return it
    fetch_summary_query = """
        SELECT id, agent_run_id, briefing_id, summary_markdown, bullet_points, citations, created_at
        FROM AI_NW_SUMM_SUMMARIES
        WHERE agent_run_id = %(run_id)s;
    """
    rows = fetch_dicts(fetch_summary_query, {"run_id": run_id})
    if not rows:
        raise Exception("Failed to retrieve created summary.")

    row = rows[0]
    row['bullet_points'] = json.loads(row['bullet_points'])
    row['citations'] = json.loads(row['citations'])
    return Summary(**row)


def get_latest_summary(briefing_id: str) -> Summary | None:
    """Gets the most recent summary for a briefing."""
    query = """
        SELECT id, agent_run_id, briefing_id, summary_markdown, bullet_points, citations, created_at
        FROM AI_NW_SUMM_SUMMARIES
        WHERE briefing_id = %(briefing_id)s
        ORDER BY created_at DESC
        LIMIT 1;
    """
    rows = fetch_dicts(query, {"briefing_id": briefing_id})
    if not rows:
        return None
    
    row = rows[0]
    row['bullet_points'] = json.loads(row['bullet_points'])
    row['citations'] = json.loads(row['citations'])
    return Summary(**row)


def get_summaries_for_briefings(briefing_ids: list[str]) -> dict[str, Summary | None]:
    """
    Gets the latest summary for each briefing in the list.
    Returns a dict mapping briefing_id -> Summary (or None if no summary exists).
    """
    if not briefing_ids:
        return {}
    
    # Get all latest summaries for these briefings
    placeholders = ', '.join([f"'{bid}'" for bid in briefing_ids])
    query = f"""
        WITH ranked_summaries AS (
            SELECT 
                id, agent_run_id, briefing_id, summary_markdown, 
                bullet_points, citations, created_at,
                ROW_NUMBER() OVER (PARTITION BY briefing_id ORDER BY created_at DESC) as rn
            FROM AI_NW_SUMM_SUMMARIES
            WHERE briefing_id IN ({placeholders})
        )
        SELECT id, agent_run_id, briefing_id, summary_markdown, bullet_points, citations, created_at
        FROM ranked_summaries
        WHERE rn = 1;
    """
    rows = fetch_dicts(query, {})
    
    # Parse JSON fields
    for row in rows:
        row['bullet_points'] = json.loads(row['bullet_points'])
        row['citations'] = json.loads(row['citations'])
    
    # Build result dict
    result = {bid: None for bid in briefing_ids}
    for row in rows:
        result[row['briefing_id']] = Summary(**row)
    
    return result


def get_briefing_summary_status(briefing_id: str) -> dict:
    """
    Returns status information about a briefing's latest summary.
    Useful for checking if summary exists and how old it is.
    """
    query = """
        SELECT 
            b.id as briefing_id,
            b.name as briefing_name,
            b.last_run_at,
            s.id as summary_id,
            s.created_at as summary_created_at,
            DATEDIFF(hour, s.created_at, CURRENT_TIMESTAMP()) as age_hours
        FROM AI_NW_SUMM_BRIEFINGS b
        LEFT JOIN (
            SELECT briefing_id, id, created_at,
                   ROW_NUMBER() OVER (PARTITION BY briefing_id ORDER BY created_at DESC) as rn
            FROM AI_NW_SUMM_SUMMARIES
        ) s ON b.id = s.briefing_id AND s.rn = 1
        WHERE b.id = %(briefing_id)s;
    """
    rows = fetch_dicts(query, {"briefing_id": briefing_id})
    if not rows:
        return {
            "briefing_id": briefing_id,
            "summary_exists": False,
            "last_run_at": None,
            "age_hours": None
        }
    
    row = rows[0]
    return {
        "briefing_id": row['briefing_id'],
        "briefing_name": row.get('briefing_name'),
        "summary_exists": row['summary_id'] is not None,
        "last_run_at": row['last_run_at'],
        "summary_created_at": row.get('summary_created_at'),
        "age_hours": row.get('age_hours')
    }


def mark_run_as_failed(run_id: str, error_message: str) -> None:
    """Marks an agent run as failed with an error message."""
    query = """
        UPDATE AI_NW_SUMM_AGENT_RUNS
        SET status = 'failed', 
            error_message = %(error_message)s,
            completed_at = CURRENT_TIMESTAMP()
        WHERE id = %(run_id)s;
    """
    execute(query, {"run_id": run_id, "error_message": error_message})
