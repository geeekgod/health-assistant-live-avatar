import datetime as dt
import logging
import os
from typing import Any, Dict, Optional

import yaml
from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.config import settings
from app.api.summaries import generate_summary_with_llm
from app.db.database import get_db
from app.db.models import Booking, CallSession, Contact, ToolEvent

router = APIRouter()
logger = logging.getLogger(__name__)

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "..", "templates")

DEFAULT_SLOTS = ["09:00", "09:30", "10:00", "10:30", "11:00", "11:30", "13:00", "13:30", "14:00", "14:30", "15:00", "15:30", "16:00"]

def _load_template_data(template_id: str) -> dict:
    try:
        filepath = os.path.join(TEMPLATES_DIR, f"{template_id}.yaml")
        if os.path.exists(filepath):
            with open(filepath, "r") as f:
                return yaml.safe_load(f) or {}
    except Exception:
        pass
    return {}

def _slots_for_date(template_data: dict, date_str: str) -> list[str]:
    slot_config = template_data.get("slot_config")
    if not slot_config: return DEFAULT_SLOTS
    try:
        weekday = dt.datetime.strptime(date_str, "%Y-%m-%d").strftime("%A").lower()
    except ValueError:
        return DEFAULT_SLOTS
    slots = slot_config.get(weekday)
    return list(slots) if slots else DEFAULT_SLOTS

class ToolExecuteRequest(BaseModel):
    session_id: str
    tool_name: str
    args: Dict[str, Any]

async def verify_worker(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    token = authorization.split(" ")[1]
    if token != settings.WORKER_API_SECRET:
        raise HTTPException(status_code=403, detail="Invalid worker token")
    return token

@router.post("/tools/execute")
async def execute_tool(
    req: ToolExecuteRequest,
    db: AsyncSession = Depends(get_db),
    worker: str = Depends(verify_worker),
):
    result: dict = {}
    should_summarize = False

    session_query = await db.execute(select(CallSession).where(CallSession.id == req.session_id))
    db_session = session_query.scalar_one_or_none()
    if not db_session:
        raise HTTPException(status_code=404, detail="Session not found")

    if req.tool_name == "identify_user":
        phone = req.args.get("phone")
        name = req.args.get("name")
        query = await db.execute(select(Contact).where(Contact.phone == phone))
        contact = query.scalar_one_or_none()
        if not contact:
            contact = Contact(phone=phone, name=name)
            db.add(contact)
            await db.commit()
            await db.refresh(contact)
        result = {"contact_id": contact.id, "name": contact.name, "message": "User identified"}

    elif req.tool_name == "fetch_slots":
        date_str = req.args.get("date")
        local_now = dt.datetime.now()
        local_today = local_now.strftime("%Y-%m-%d")

        if date_str and date_str.lower() == "today":
            date_str = local_today

        template_data = _load_template_data(db_session.template_id)
        all_slots = _slots_for_date(template_data, date_str)

        query = await db.execute(select(Booking).where(
            Booking.template_id == db_session.template_id, Booking.date == date_str, Booking.status == "active"
        ))
        booked = [b.time for b in query.scalars().all()]

        available = []
        for s in all_slots:
            if s in booked: continue
            if date_str == local_today:
                if dt.datetime.strptime(s, "%H:%M").time() <= local_now.time():
                    continue
            available.append(dt.datetime.strptime(s, "%H:%M").strftime("%I:%M %p").lstrip("0"))

        result = {"date": date_str, "available_slots": available}

    elif req.tool_name == "book_appointment":
        if key := req.args.get("idempotency_key"):
            q = await db.execute(select(ToolEvent).where(ToolEvent.session_id == req.session_id, ToolEvent.tool_name == "book_appointment"))
            for ev in q.scalars().all():
                if ev.args.get("idempotency_key") == key:
                    return ev.result

        phone, date_str, time_str = req.args.get("phone"), req.args.get("date"), req.args.get("time")
        try:
            time_str = dt.datetime.strptime(time_str, "%I:%M %p").strftime("%H:%M")
        except (ValueError, TypeError): pass
        
        query = await db.execute(select(Contact).where(Contact.phone == phone))
        contact = query.scalar_one_or_none()

        if not contact:
            result = {"error": "User not found, call identify_user first"}
        else:
            query = await db.execute(select(Booking).where(
                Booking.template_id == db_session.template_id, Booking.date == date_str, Booking.time == time_str, Booking.status == "active"
            ))
            if query.scalar_one_or_none():
                result = {"status": "slot_taken", "message": "This slot is already booked."}
            else:
                db.add(Booking(contact_id=contact.id, template_id=db_session.template_id, date=date_str, time=time_str))
                await db.commit()
                result = {"status": "success", "message": f"Appointment booked for {date_str} at {time_str}"}

    elif req.tool_name == "retrieve_appointments":
        query = await db.execute(select(Contact).where(Contact.phone == req.args.get("phone")))
        if not (contact := query.scalar_one_or_none()):
            result = {"error": "User not found, call identify_user first"}
        else:
            q2 = await db.execute(select(Booking).where(Booking.contact_id == contact.id, Booking.template_id == db_session.template_id, Booking.status == "active"))
            result = {"status": "success", "appointments": [{"date": b.date, "time": b.time} for b in q2.scalars().all()]}

    elif req.tool_name == "cancel_appointment":
        phone, d_str, t_str = req.args.get("phone"), req.args.get("date"), req.args.get("time")
        try:
            t_str = dt.datetime.strptime(t_str, "%I:%M %p").strftime("%H:%M")
        except (ValueError, TypeError): pass
        query = await db.execute(select(Contact).where(Contact.phone == phone))
        if not (contact := query.scalar_one_or_none()):
            result = {"error": "User not found"}
        else:
            q2 = await db.execute(select(Booking).where(Booking.contact_id == contact.id, Booking.template_id == db_session.template_id, Booking.date == d_str, Booking.time == t_str, Booking.status == "active"))
            if b := q2.scalar_one_or_none():
                b.status = "cancelled"
                await db.commit()
                result = {"status": "success", "message": f"Cancelled {d_str} at {t_str}"}
            else:
                result = {"error": "Appointment not found"}

    elif req.tool_name == "modify_appointment":
        phone, o_date, o_time, n_date, n_time = req.args.get("phone"), req.args.get("old_date"), req.args.get("old_time"), req.args.get("new_date"), req.args.get("new_time")
        try: o_time = dt.datetime.strptime(o_time, "%I:%M %p").strftime("%H:%M")
        except (ValueError, TypeError): pass
        try: n_time = dt.datetime.strptime(n_time, "%I:%M %p").strftime("%H:%M")
        except (ValueError, TypeError): pass

        query = await db.execute(select(Contact).where(Contact.phone == phone))
        if not (contact := query.scalar_one_or_none()):
            result = {"error": "User not found"}
        else:
            q_conflict = await db.execute(select(Booking).where(Booking.template_id == db_session.template_id, Booking.date == n_date, Booking.time == n_time, Booking.status == "active"))
            if q_conflict.scalar_one_or_none():
                result = {"status": "slot_taken", "message": "New slot already booked."}
            else:
                q_old = await db.execute(select(Booking).where(Booking.contact_id == contact.id, Booking.template_id == db_session.template_id, Booking.date == o_date, Booking.time == o_time, Booking.status == "active"))
                if b := q_old.scalar_one_or_none():
                    b.date, b.time = n_date, n_time
                    await db.commit()
                    result = {"status": "success", "message": f"Modified to {n_date} at {n_time}"}
                else:
                    result = {"error": "Old appointment not found"}

    elif req.tool_name == "end_conversation":
        should_summarize = db_session.summary_status not in ("ready", "generating")
        db_session.status = "ended"
        if not db_session.ended_at:
            db_session.ended_at = dt.datetime.now(dt.timezone.utc)
        await db.commit()
        result = {"status": "ended", "message": "Call ended. Generating summary..."}

    else:
        result = {"error": "Unknown tool"}

    db.add(ToolEvent(session_id=req.session_id, tool_name=req.tool_name, args=req.args, result=result, status="success" if not result.get("error") else "error"))
    await db.commit()

    if should_summarize:
        await generate_summary_with_llm(req.session_id, db)

    return result
