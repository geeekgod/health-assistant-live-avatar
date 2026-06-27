import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.db.database import get_db
from app.db.models import CallSession, ToolEvent
from app.providers.llm.groq_client import GroqClient

router = APIRouter()
logger = logging.getLogger(__name__)

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "..", "templates")
RECORDINGS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "recordings")

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

def _find_recording_path(session_id: str) -> str | None:
    for ext in (".ogg", ".wav", ".mp3", ".webm"):
        path = os.path.join(RECORDINGS_DIR, f"{session_id}{ext}")
        if os.path.isfile(path):
            return path
    return None

def _brief_summary(summary_json: dict[str, Any] | None) -> str | None:
    if not summary_json:
        return None
    parts: list[str] = []
    if name := summary_json.get("patient_name"):
        parts.append(str(name))
    if complaint := summary_json.get("chief_complaint"):
        parts.append(f"— {complaint}")
    date = summary_json.get("appointment_date")
    time = summary_json.get("appointment_time")
    if date:
        appt = f"Appt {date}"
        if time:
            appt += f" at {time}"
        parts.append(appt)
    return " · ".join(parts) if parts else None

def _serialize_tool_events(events) -> list[dict]:
    return [
        {
            "tool_name": e.tool_name,
            "status": e.status,
            "args": e.args,
            "result": e.result,
            "timestamp": e.timestamp.isoformat() if e.timestamp else None,
        }
        for e in events
    ]

async def _session_detail(db_session: CallSession, db: AsyncSession) -> dict:
    events_query = await db.execute(
        select(ToolEvent)
        .where(ToolEvent.session_id == db_session.id)
        .order_by(ToolEvent.timestamp)
    )
    events = events_query.scalars().all()
    recording_path = _find_recording_path(db_session.id)
    summary_json = db_session.summary_json or {}

    return {
        "session_id": db_session.id,
        "template_id": db_session.template_id,
        "status": db_session.status,
        "summary_status": db_session.summary_status,
        "summary_json": db_session.summary_json,
        "brief_summary": _brief_summary(summary_json if db_session.summary_status == "ready" else None),
        "started_at": db_session.started_at.isoformat() if db_session.started_at else None,
        "ended_at": db_session.ended_at.isoformat() if db_session.ended_at else None,
        "transcript": db_session.transcript_json or [],
        "tool_events": _serialize_tool_events(events),
        "recording_available": recording_path is not None,
        "recording_url": f"/api/sessions/{db_session.id}/recording" if recording_path else None,
    }

async def generate_summary_with_llm(session_id: str, db: AsyncSession) -> dict:
    session_query = await db.execute(select(CallSession).where(CallSession.id == session_id))
    db_session = session_query.scalar_one_or_none()

    if not db_session:
        return {}

    if db_session.summary_status == "ready" and db_session.summary_json:
        return db_session.summary_json

    template_id = db_session.template_id
    transcript_json = db_session.transcript_json

    template_data = _load_template_data(template_id)
    summary_fields = template_data.get("summary_fields") or DEFAULT_SUMMARY_FIELDS

    db_session.summary_status = "generating"
    await db.commit()

    try:
        query = await db.execute(select(ToolEvent).where(ToolEvent.session_id == session_id))
        events = query.scalars().all()

        system_prompt = template_data.get("system_prompt", "")
        entity_labels = template_data.get("entity_labels") or {}
        user_label = entity_labels.get("user", "caller")
        booking_label = entity_labels.get("booking", "appointment")

        tool_events_text = json.dumps([
            {"tool": e.tool_name, "status": e.status, "args": e.args, "result": e.result}
            for e in events
        ], indent=2)

        transcript_text = json.dumps(transcript_json, indent=2) if transcript_json else ""
        transcript_section = f"\nConversation transcript:\n{transcript_text}\n" if transcript_text else ""

        fields_schema = "\n".join(
            f"- {field}: value extracted from the call, or null if not mentioned"
            for field in summary_fields
        )

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

        client = GroqClient()
        summary_data = await client.complete_json(user_prompt)
        if not summary_data:
            summary_data = {field: None for field in summary_fields}

        db_session.summary_json = summary_data
        db_session.summary_status = "ready"
        await db.commit()
        return summary_data
    except Exception as e:
        logger.exception("Summary generation failed for session %s: %s", session_id, e)
        db_session.summary_status = "error"
        db_session.summary_json = {field: None for field in summary_fields}
        await db.commit()
        return db_session.summary_json or {}

@router.get("/summaries/{session_id}")
async def get_summary(session_id: str, db: AsyncSession = Depends(get_db)):
    session_query = await db.execute(select(CallSession).where(CallSession.id == session_id))
    db_session = session_query.scalar_one_or_none()

    if not db_session:
        raise HTTPException(status_code=404, detail="Session not found")

    if (
        db_session.status == "ended"
        and db_session.summary_status in ("pending", "generating", "error")
    ):
        await generate_summary_with_llm(session_id, db)
        session_query = await db.execute(select(CallSession).where(CallSession.id == session_id))
        db_session = session_query.scalar_one_or_none()

    return await _session_detail(db_session, db)


@router.get("/sessions/{session_id}/recording")
async def get_session_recording(session_id: str, db: AsyncSession = Depends(get_db)):
    session_query = await db.execute(select(CallSession).where(CallSession.id == session_id))
    if not session_query.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Session not found")

    recording_path = _find_recording_path(session_id)
    if not recording_path:
        raise HTTPException(status_code=404, detail="No recording available for this session")

    if recording_path.endswith(".wav"):
        media_type = "audio/wav"
    elif recording_path.endswith(".mp3"):
        media_type = "audio/mpeg"
    elif recording_path.endswith(".ogg"):
        media_type = "audio/ogg"
    else:
        media_type = "audio/webm"
    return FileResponse(recording_path, media_type=media_type, filename=os.path.basename(recording_path))
