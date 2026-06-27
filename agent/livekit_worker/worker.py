import json
import logging
import os
import re
import asyncio
from datetime import datetime, timezone

import httpx
from dotenv import load_dotenv
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    JobContext,
    RoomInputOptions,
    RunContext,
    TurnHandlingOptions,
    cli,
    inference,
)
from livekit.agents.llm import function_tool
from livekit.plugins import cartesia, deepgram, groq

from .avatar import start_avatar
from .gemini_tts import GeminiTTS

_ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
load_dotenv()
load_dotenv(os.path.join(_ROOT, ".env"))
load_dotenv(os.path.join(_ROOT, "backend", ".env"))
load_dotenv(os.path.join(_ROOT, "agent", ".env"))

if not os.getenv("LIVEKIT_URL", "").strip():
    public = os.getenv("LIVEKIT_PUBLIC_URL", "").strip()
    if public:
        os.environ["LIVEKIT_URL"] = public

logger = logging.getLogger("health-assistant-worker")

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
WORKER_API_SECRET = os.getenv("WORKER_API_SECRET", "dev-worker-secret")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
DEEPGRAM_MODEL = os.getenv("DEEPGRAM_MODEL", "nova-3")

DEFAULT_SYSTEM_PROMPT = (
    "You are a helpful voice assistant for scheduling appointments. "
    "Use the provided tools to identify callers, check availability, and book slots. "
    "Keep responses concise and conversational. "
    "Only call identify_user after the caller has clearly given both their full name and phone number. "
    "Never invent, guess, or use placeholder values for name or phone. "
    "Ask for missing information before calling any tool."
)

server = AgentServer()


def _parse_job_metadata(ctx: JobContext) -> dict:
    raw = ctx.job.metadata or "{}"
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Invalid job metadata JSON: %s", raw)
        return {}


def _resolve_session_id(ctx: JobContext, metadata: dict) -> str:
    session_id = metadata.get("session_id")
    if session_id:
        return session_id
    room_name = ctx.room.name or ""
    if room_name.startswith("room-"):
        return room_name.removeprefix("room-")
    return room_name or "unknown"


async def _emit_tool_event(
    room,
    session_id: str,
    tool: str,
    status: str,
    message: str = "",
    result: dict | None = None,
) -> None:
    event = {
        "type": "tool_call",
        "session_id": session_id,
        "tool": tool,
        "status": status,
        "message": message,
        "result": result or {},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    payload = json.dumps(event).encode("utf-8")
    await room.local_participant.publish_data(payload, reliable=True)


async def _emit_transcript_event(
    room,
    session_id: str,
    role: str,
    text: str,
) -> None:
    event = {
        "type": "transcript",
        "session_id": session_id,
        "role": role,
        "text": text,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    payload = json.dumps(event).encode("utf-8")
    await room.local_participant.publish_data(payload, reliable=True)


async def _execute_tool(session_id: str, tool_name: str, args: dict) -> dict:
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{BACKEND_URL.rstrip('/')}/api/tools/execute",
            json={
                "session_id": session_id,
                "tool_name": tool_name,
                "args": args,
            },
            headers={"Authorization": f"Bearer {WORKER_API_SECRET}"},
        )
        response.raise_for_status()
        return response.json()


def _extract_conversation_text(content) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for part in content:
            text = part if isinstance(part, str) else getattr(part, "text", "")
            if isinstance(text, str) and text.strip():
                parts.append(text.strip())
        return " ".join(parts)
    return ""


async def _append_transcript_entry(session_id: str, role: str, text: str) -> None:
    if not text or "<function=" in text:
        return
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(
                f"{BACKEND_URL.rstrip('/')}/api/sessions/{session_id}/transcript",
                json={"role": role, "text": text, "source": "agent"},
                headers={"Authorization": f"Bearer {WORKER_API_SECRET}"},
            )
    except Exception as exc:
        logger.warning("Failed to persist transcript for %s: %s", session_id, exc)


async def _persist_conversation_turn(room, session_id: str, role: str, text: str) -> None:
    await _append_transcript_entry(session_id, role, text)
    try:
        await _emit_transcript_event(room, session_id, role, text)
    except Exception as exc:
        logger.warning("Failed to emit transcript event for %s: %s", session_id, exc)


_INVALID_IDENTIFY_MARKERS = (
    "unknown",
    "awaiting",
    "missing",
    "please",
    "provide",
    "n/a",
    "none",
    "tbd",
    "placeholder",
    "user input",
    "not provided",
    "phone number",
)

_FAKE_PHONES = frozenset({"1234567890", "0000000000", "1111111111", "9999999999"})


def _normalize_phone(phone: str) -> str:
    return re.sub(r"\D", "", (phone or "").strip())


def _validate_identify_args(phone: str, name: str) -> str | None:
    """Return an error message when args are placeholders or incomplete."""
    phone = (phone or "").strip()
    name = (name or "").strip()
    if not phone or not name:
        return "Both name and phone are required. Ask the caller before calling identify_user."

    haystack = f"{phone} {name}".lower()
    if any(marker in haystack for marker in _INVALID_IDENTIFY_MARKERS):
        return (
            "Do not use placeholder values. Wait until the caller states their real "
            "full name and phone number, then call identify_user again."
        )

    digits = _normalize_phone(phone)
    if len(digits) < 10 or len(digits) > 15:
        return "Phone must be 10–15 digits from the caller. Ask them to say their number again."

    if digits in _FAKE_PHONES:
        return "That phone number looks like a placeholder. Ask for the caller's real phone number."

    if len(name) < 2 or not re.search(r"[a-zA-Z]", name):
        return "Ask for the caller's full name before calling identify_user."

    return None


class HealthAssistantAgent(Agent):
    def __init__(
        self,
        session_id: str,
        room,
        system_prompt: str,
        greeting: str | None = None,
        tool_labels: dict | None = None,
    ) -> None:
        self._session_id = session_id
        self._room = room
        self._greeting = greeting
        self._tool_labels = tool_labels or {}
        self._has_ended = False
        self._identified_phone: str | None = None
        self._identified_result: str | None = None
        super().__init__(
            instructions=system_prompt
            + "\nNever call identify_user twice for the same phone in one call."
            + "\nNever call identify_user until the caller has clearly spoken both their full name "
            "and a real phone number (digits only). Do not pass placeholders like 'unknown' or "
            "'awaiting user input'."
        )

    async def on_enter(self) -> None:
        if self._greeting:
            self.session.generate_reply(
                instructions=f"Greet the caller. Say exactly: {self._greeting}"
            )
        else:
            self.session.generate_reply(instructions="Greet the caller and ask how you can help.")

    async def _run_tool(self, tool_name: str, args: dict) -> str:
        message = self._tool_labels.get(tool_name, tool_name.replace("_", " "))

        log_args = dict(args)
        if "phone" in log_args and len(log_args["phone"]) >= 4:
            log_args["phone"] = "***-***-" + log_args["phone"][-4:]

        logger.info(
            "Tool call entry | session_id=%s | tool=%s | args=%s",
            self._session_id,
            tool_name,
            log_args,
        )

        await _emit_tool_event(
            self._room, self._session_id, tool_name, "running", message, {"args": args}
        )

        try:
            result = await _execute_tool(self._session_id, tool_name, args)
            if result.get("error") or result.get("status") == "slot_taken":
                status = "error"
            else:
                status = "done"

            logger.info(
                "Tool call exit | session_id=%s | tool=%s | status=%s | result=%s",
                self._session_id,
                tool_name,
                status,
                result,
            )

            await _emit_tool_event(
                self._room, self._session_id, tool_name, status, message, result
            )
            return json.dumps(result)
        except Exception as exc:
            logger.exception("Tool %s failed for session %s", tool_name, self._session_id)
            await _emit_tool_event(
                self._room,
                self._session_id,
                tool_name,
                "error",
                str(exc),
                {"error": str(exc)},
            )
            raise

    @function_tool
    async def identify_user(self, context: RunContext, phone: str, name: str) -> str:
        """Look up or create a contact by phone number and name.

        Args:
            phone: Caller phone number including area code (digits the caller stated)
            name: Caller full name (as stated by the caller)
        """
        digits = _normalize_phone(phone)
        if self._identified_phone == digits and self._identified_result is not None:
            return self._identified_result

        if err := _validate_identify_args(phone, name):
            result = {"error": err}
            message = self._tool_labels.get("identify_user", "identify user")
            logger.warning(
                "identify_user rejected | session_id=%s | phone=%s | name=%s | reason=%s",
                self._session_id,
                digits or phone,
                name,
                err,
            )
            await _emit_tool_event(
                self._room,
                self._session_id,
                "identify_user",
                "error",
                message,
                {"args": {"phone": phone, "name": name}, **result},
            )
            return json.dumps(result)

        clean_name = name.strip()
        result_str = await self._run_tool(
            "identify_user", {"phone": digits, "name": clean_name}
        )
        try:
            res_dict = json.loads(result_str)
            if not res_dict.get("error"):
                self._identified_phone = digits
                self._identified_result = result_str
        except json.JSONDecodeError:
            pass
        return result_str

    @function_tool
    async def fetch_slots(self, context: RunContext, date: str) -> str:
        """Fetch available appointment slots for a given date (YYYY-MM-DD).

        Args:
            date: Date to check in YYYY-MM-DD format
        """
        return await self._run_tool("fetch_slots", {"date": date})

    @function_tool
    async def book_appointment(
        self, context: RunContext, phone: str, date: str, time: str
    ) -> str:
        """Book an appointment for an identified caller.

        Args:
            phone: Caller phone number (must identify_user first)
            date: Appointment date in YYYY-MM-DD format
            time: Appointment time in HH:MM 24-hour format
        """
        return await self._run_tool(
            "book_appointment", {"phone": phone, "date": date, "time": time}
        )

    @function_tool
    async def retrieve_appointments(self, context: RunContext, phone: str) -> str:
        """List active appointments for an identified caller.

        Args:
            phone: Caller phone number (must identify_user first)
        """
        return await self._run_tool(
            "retrieve_appointments", {"phone": _normalize_phone(phone)}
        )

    @function_tool
    async def cancel_appointment(
        self, context: RunContext, phone: str, date: str, time: str
    ) -> str:
        """Cancel an existing appointment for an identified caller.

        Args:
            phone: Caller phone number (must identify_user first)
            date: Appointment date in YYYY-MM-DD format
            time: Appointment time in HH:MM 24-hour format
        """
        return await self._run_tool(
            "cancel_appointment",
            {"phone": _normalize_phone(phone), "date": date, "time": time},
        )

    @function_tool
    async def modify_appointment(
        self,
        context: RunContext,
        phone: str,
        old_date: str,
        old_time: str,
        new_date: str,
        new_time: str,
    ) -> str:
        """Reschedule an existing appointment to a new date and time.

        Args:
            phone: Caller phone number (must identify_user first)
            old_date: Current appointment date in YYYY-MM-DD format
            old_time: Current appointment time in HH:MM 24-hour format
            new_date: New appointment date in YYYY-MM-DD format
            new_time: New appointment time in HH:MM 24-hour format
        """
        return await self._run_tool(
            "modify_appointment",
            {
                "phone": _normalize_phone(phone),
                "old_date": old_date,
                "old_time": old_time,
                "new_date": new_date,
                "new_time": new_time,
            },
        )

    @function_tool
    async def end_conversation(self, context: RunContext) -> str:
        """End the call and trigger post-call summary generation."""
        if self._has_ended:
            return "Call already ended."
        self._has_ended = True
        return await self._run_tool("end_conversation", {})


@server.rtc_session(agent_name="health-assistant")
async def entrypoint(ctx: JobContext) -> None:
    metadata = _parse_job_metadata(ctx)
    session_id = _resolve_session_id(ctx, metadata)
    agent_config = metadata.get("agent_config") or {}

    system_prompt = agent_config.get("system_prompt") or DEFAULT_SYSTEM_PROMPT

    now = datetime.now()
    current_context = (
        f"\n\nCURRENT SYSTEM CONTEXT:\n"
        f"- Current Date: {now.strftime('%Y-%m-%d')}\n"
        f"- Current Time: {now.strftime('%H:%M')}\n"
    )

    system_prompt += current_context + (
        "\n\nCRITICAL INSTRUCTION: "
        "1. NEVER output raw function or XML tags like `<function=...>` in your response. "
        "You MUST invoke the native registered tools (identify_user, fetch_slots, book_appointment, end_conversation) directly via the function calling protocol. "
        "Do not type the tool execution as text.\n"
        "2. Never guess or invent tool arguments (like name or phone). Ask the user if missing.\n"
        "3. NEVER auto-select a booking time. You MUST list available slots and WAIT for the user to explicitly choose one before calling book_appointment."
    )
    greeting = agent_config.get("greeting")
    tool_labels = agent_config.get("tool_labels") or {}
    avatar_provider = agent_config.get("avatar_provider", "none")
    tts_provider = agent_config.get("tts_provider", "cartesia")

    ctx.log_context_fields = {
        "room": ctx.room.name,
        "session_id": session_id,
        "template_id": agent_config.get("template_id"),
        "avatar_provider": avatar_provider,
        "tts_provider": tts_provider,
    }

    logger.info(
        "Starting agent for room=%s session=%s template=%s avatar=%s tts=%s",
        ctx.room.name,
        session_id,
        agent_config.get("template_id"),
        avatar_provider,
        tts_provider,
    )

    if tts_provider == "gemini":
        tts_plugin = GeminiTTS()
    else:
        tts_plugin = cartesia.TTS()

    session = AgentSession(
        turn_handling=TurnHandlingOptions(
            turn_detection=inference.TurnDetector(version="v1-mini"),
            endpointing={
                "mode": "fixed",
                "min_delay": 0.5,
                "max_delay": 3.0,
            },
            interruption={
                "mode": "vad",
                "min_duration": 0.5,
                "min_words": 1,
                "false_interruption_timeout": 2.0,
                "resume_false_interruption": False,
            },
            preemptive_generation={
                "enabled": False,
                "max_retries": 1,
            },
        ),
        stt=deepgram.STT(model=DEEPGRAM_MODEL),
        llm=groq.LLM(model=GROQ_MODEL),
        tts=tts_plugin,
    )

    @session.on("conversation_item_added")
    def on_item_added(event):
        try:
            item = event.item
            role = getattr(item, "role", None)
            content = getattr(item, "content", "")
            text = _extract_conversation_text(content)
            if role in ("user", "assistant") and text:
                if role == "assistant" and "<function=" in text:
                    logger.warning(
                        "Agent emitted literal function tag in session %s: %s",
                        session_id,
                        text,
                    )
                else:
                    asyncio.create_task(
                        _persist_conversation_turn(ctx.room, session_id, role, text)
                    )
        except Exception:
            pass

    agent = HealthAssistantAgent(
        session_id=session_id,
        room=ctx.room,
        system_prompt=system_prompt,
        greeting=greeting,
        tool_labels=tool_labels,
    )

    await ctx.connect()
    await start_avatar(session, ctx.room, provider=avatar_provider)
    await session.start(
        agent=agent,
        room=ctx.room,
        room_input_options=RoomInputOptions(text_enabled=True),
    )


if __name__ == "__main__":
    cli.run_app(server)
