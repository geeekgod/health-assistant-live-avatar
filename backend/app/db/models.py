from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, JSON, String, text
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.db.database import Base

class Contact(Base):
    __tablename__ = "contacts"
    id = Column(Integer, primary_key=True, index=True)
    phone = Column(String, unique=True, index=True, nullable=False)
    name = Column(String)
    preferences = Column(JSON, default=dict)

class Booking(Base):
    __tablename__ = "bookings"
    id = Column(Integer, primary_key=True, index=True)
    contact_id = Column(Integer, ForeignKey("contacts.id"), nullable=False)
    template_id = Column(String, index=True, nullable=False)
    date = Column(String, nullable=False)
    time = Column(String, nullable=False)
    status = Column(String, default="active")
    metadata_json = Column(JSON, default=dict)

    __table_args__ = (
        Index(
            "uix_template_date_time_active",
            "template_id",
            "date",
            "time",
            unique=True,
            sqlite_where=text("status = 'active'"),
        ),
    )
    contact = relationship("Contact")

class CallSession(Base):
    __tablename__ = "call_sessions"
    id = Column(String, primary_key=True, index=True)
    template_id = Column(String, index=True, nullable=False)
    status = Column(String, default="active")
    started_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    ended_at = Column(DateTime, nullable=True)
    transcript_json = Column(JSON, default=list)
    summary_json = Column(JSON, nullable=True)
    summary_status = Column(String, default="pending")
    extracted_fields = Column(JSON, default=dict)
    runtime_config = Column(JSON, default=dict)

class ToolEvent(Base):
    __tablename__ = "tool_events"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, ForeignKey("call_sessions.id"), nullable=False)
    tool_name = Column(String, nullable=False)
    args = Column(JSON, default=dict)
    result = Column(JSON, default=dict)
    status = Column(String, default="done")
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))
