import json
import logging
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.db.database import get_db
from app.db.models import CallSession, ToolEvent
from app.providers.llm.groq_client import GroqClient

router = APIRouter()
logger = logging.getLogger(__name__)

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "..", "templates")

DEFAULT_SUMMARY_FIELDS = [
    "identified_user",
    "bookings",
    "tools_used",
    "feedback",
    "call_rating",
]

def _load_template_data(template_id: str) -> dict:
    try:
        import yaml
        filepath = os.path.join(TEMPLATES_DIR, f"{template_id}.yaml")
        if os.path.exists(filepath):
            with open(filepath, "r") as f:
                return yaml.safe_load(f) or {}
    except Exception as e:
        logger.warning(f"Failed to load template {template_id}: {e}")
    return {}

async def generate_summary_with_llm(session_id: str, db: AsyncSession) -> dict:
    session_query = await db.execute(select(CallSession).where(CallSession.id == session_id))
    db_session = session_query.scalar_one_or_none()
    
    if not db_session:
        return {}
        
    db_session.summary_status = "generating"
    await db.commit()

    query = await db.execute(select(ToolEvent).where(ToolEvent.session_id == session_id))
    events = query.scalars().all()

    template_data = _load_template_data(db_session.template_id)
    system_prompt = template_data.get("system_prompt", "")
    summary_fields = template_data.get("summary_fields") or DEFAULT_SUMMARY_FIELDS
    entity_labels = template_data.get("entity_labels") or {}
    user_label = entity_labels.get("user", "caller")
    booking_label = entity_labels.get("booking", "appointment")

    tool_events_text = json.dumps([
        {"tool": e.tool_name, "status": e.status, "args": e.args, "result": e.result}
        for e in events
    ], indent=2)

    transcript_text = json.dumps(db_session.transcript_json, indent=2) if db_session.transcript_json else ""
    transcript_section = f"\nConversation transcript:\n{transcript_text}\n" if transcript_text else ""

    fields_schema = "\n".join(f"- {field}: value extracted from the call, or null if not mentioned" for field in summary_fields)

    user_prompt = f"""Analyze this call session and generate a structured JSON summary.

Template system prompt (agent role):
{system_prompt}

This template refers to the caller as "{user_label}" and scheduled items as "{booking_label}".

Tool events from the call:
{tool_events_text}
{transcript_section}
Generate a JSON response (valid JSON only, no markdown) with these exact fields:
{fields_schema}

Extract {user_label} details and {booking_label} information from tool events and conversation context."""

    try:
        client = GroqClient()
        summary_data = await client.complete_json(user_prompt)
    except Exception as e:
        logger.error(f"LLM generation failed: {e}")
        summary_data = {field: None for field in summary_fields}

    db_session.summary_json = summary_data
    db_session.summary_status = "ready"
    await db.commit()

    return summary_data

@router.get("/summaries/{session_id}")
async def get_summary(session_id: str, db: AsyncSession = Depends(get_db)):
    session_query = await db.execute(select(CallSession).where(CallSession.id == session_id))
    db_session = session_query.scalar_one_or_none()

    if not db_session:
        raise HTTPException(status_code=404, detail="Session not found")

    return {
        "session_id": db_session.id,
        "template_id": db_session.template_id,
        "status": db_session.status,
        "summary_status": db_session.summary_status,
        "summary_json": db_session.summary_json,
    }
