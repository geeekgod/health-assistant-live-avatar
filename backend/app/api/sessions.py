import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Optional, Literal

import yaml
from fastapi import APIRouter, Depends, Header, HTTPException
from livekit import api
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.api.summaries import generate_summary_with_llm
from app.config import settings
from app.db.database import get_db
from app.db.models import CallSession, ToolEvent

logger = logging.getLogger(__name__)

router = APIRouter()
TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "..", "templates")
AGENT_NAME = "health-assistant"

class CreateSessionRequest(BaseModel):
    template_id: str
    avatar_provider: Literal["bey", "tavus", "none"] = "none"
    tts_provider: Literal["cartesia", "gemini"] = "cartesia"

class TranscriptAppendRequest(BaseModel):
    role: str
    text: str
    source: str = "agent"

class TranscriptBulkRequest(BaseModel):
    segments: list[dict[str, Any]]

async def verify_worker(authorization: Optional[str] = Header(None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    token = authorization.split(" ")[1]
    if token != settings.WORKER_API_SECRET:
        raise HTTPException(status_code=403, detail="Invalid worker token")
    return token

def _build_agent_config(
    template_data: dict,
    template_id: str,
    *,
    avatar_provider: str = "none",
    tts_provider: str = "cartesia",
) -> dict:
    return {
        "system_prompt": template_data.get("system_prompt"),
        "greeting": template_data.get("greeting"),
        "template_id": template_id,
        "tool_labels": template_data.get("tool_labels") or {},
        "avatar_provider": avatar_provider,
        "tts_provider": tts_provider,
    }

async def _dispatch_agent(room_name: str, session_id: str, agent_config: dict) -> None:
    lkapi = api.LiveKitAPI(
        url=settings.livekit_http_url,
        api_key=settings.LIVEKIT_API_KEY,
        api_secret=settings.LIVEKIT_API_SECRET,
    )
    try:
        metadata = json.dumps({"session_id": session_id, "agent_config": agent_config})
        await lkapi.agent_dispatch.create_dispatch(
            api.CreateAgentDispatchRequest(
                agent_name=AGENT_NAME,
                room=room_name,
                metadata=metadata,
            )
        )
    finally:
        await lkapi.aclose()

@router.get("/sessions")
async def list_sessions(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(CallSession).order_by(CallSession.started_at.desc()))
    sessions = result.scalars().all()
    return [{
        "session_id": s.id,
        "template_id": s.template_id,
        "status": s.status,
        "summary_status": s.summary_status,
        "started_at": s.started_at.isoformat() if s.started_at else None,
        "ended_at": s.ended_at.isoformat() if s.ended_at else None,
    } for s in sessions]

@router.get("/sessions/{session_id}")
async def get_session(session_id: str, db: AsyncSession = Depends(get_db)):
    session_query = await db.execute(select(CallSession).where(CallSession.id == session_id))
    db_session = session_query.scalar_one_or_none()
    if not db_session:
        raise HTTPException(status_code=404, detail="Session not found")

    events_query = await db.execute(
        select(ToolEvent).where(ToolEvent.session_id == session_id).order_by(ToolEvent.timestamp)
    )
    return {
        "session_id": db_session.id,
        "template_id": db_session.template_id,
        "status": db_session.status,
        "summary_status": db_session.summary_status,
        "transcript": db_session.transcript_json or [],
        "summary_json": db_session.summary_json,
        "tool_events": [
            {
                "tool_name": e.tool_name,
                "status": e.status,
                "args": e.args,
                "result": e.result,
                "timestamp": e.timestamp.isoformat() if e.timestamp else None,
            }
            for e in events_query.scalars().all()
        ]
    }

@router.post("/sessions")
async def create_session(req: CreateSessionRequest, db: AsyncSession = Depends(get_db)):
    filepath = os.path.join(TEMPLATES_DIR, f"{req.template_id}.yaml")
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Template not found")

    with open(filepath, "r") as f:
        template_data = yaml.safe_load(f)

    session_id = str(uuid.uuid4())
    agent_config = _build_agent_config(
        template_data,
        req.template_id,
        avatar_provider=req.avatar_provider,
        tts_provider=req.tts_provider,
    )
    runtime_config = {"avatar_provider": req.avatar_provider, "tts_provider": req.tts_provider}

    db_session = CallSession(id=session_id, template_id=req.template_id, runtime_config=runtime_config)
    db.add(db_session)
    await db.commit()

    room_name = f"room-{session_id}"
    participant_identity = f"user-{uuid.uuid4().hex[:8]}"

    token = api.AccessToken(settings.LIVEKIT_API_KEY, settings.LIVEKIT_API_SECRET)
    token.with_identity(participant_identity).with_name("User").with_grants(
        api.VideoGrants(room_join=True, room=room_name, can_publish=True, can_subscribe=True)
    )

    try:
        await _dispatch_agent(room_name, session_id, agent_config)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Agent dispatch failed: {exc}") from exc

    return {
        "sessionId": session_id,
        "token": token.to_jwt(),
        "url": settings.LIVEKIT_URL,
        "agent_config": agent_config,
    }

@router.post("/sessions/{session_id}/end")
async def end_session(session_id: str, db: AsyncSession = Depends(get_db)):
    session_query = await db.execute(select(CallSession).where(CallSession.id == session_id))
    db_session = session_query.scalar_one_or_none()

    if not db_session:
        raise HTTPException(status_code=404, detail="Session not found")

    needs_summary = db_session.summary_status not in ("ready", "generating")
    if db_session.status != "ended":
        db_session.status = "ended"
        db_session.ended_at = datetime.now(timezone.utc)
        await db.commit()

    if needs_summary:
        await generate_summary_with_llm(session_id, db)

    return {"status": "ended"}

@router.post("/sessions/{session_id}/transcript")
async def append_transcript(session_id: str, req: TranscriptAppendRequest, db: AsyncSession = Depends(get_db), _worker: str = Depends(verify_worker)):
    session_query = await db.execute(select(CallSession).where(CallSession.id == session_id))
    db_session = session_query.scalar_one_or_none()
    if not db_session:
        raise HTTPException(status_code=404, detail="Session not found")

    text = (req.text or "").strip()
    if not text or "<function=" in text: return {"status": "skipped"}

    entry = {"role": req.role, "text": text, "source": req.source, "timestamp": datetime.now(timezone.utc).isoformat()}
    transcript = list(db_session.transcript_json or [])
    if transcript and transcript[-1].get("role") == entry["role"] and transcript[-1].get("text") == text:
        return {"status": "duplicate"}
    transcript.append(entry)
    db_session.transcript_json = transcript
    await db.commit()
    return {"status": "ok", "count": len(transcript)}

@router.put("/sessions/{session_id}/transcript")
async def replace_transcript(session_id: str, req: TranscriptBulkRequest, db: AsyncSession = Depends(get_db)):
    session_query = await db.execute(select(CallSession).where(CallSession.id == session_id))
    db_session = session_query.scalar_one_or_none()
    if not db_session:
        raise HTTPException(status_code=404, detail="Session not found")

    normalized = []
    for seg in req.segments:
        text = (seg.get("text") or "").strip()
        if not text: continue
        normalized.append({
            "role": "assistant" if seg.get("speaker") == "agent" else "user",
            "text": text,
            "source": "livekit",
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
    db_session.transcript_json = normalized
    await db.commit()
    return {"status": "ok", "count": len(normalized)}
