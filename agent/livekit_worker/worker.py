import json
import logging
import os
import re
import asyncio
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

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
RECORDINGS_DIR = os.getenv(
    "RECORDINGS_DIR",
    os.path.join(_ROOT, "backend", "recordings"),
)
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

_FAKE_PHONES = frozenset({
    "1234567890",
    "0000000000",
    "1111111111",
    "9890123456",
    "9876543210",
    "9123456789",
    "9999999999",
    "8888888888",
    "9000000000",
    "9876512340",
})
_INDIAN_MOBILE_RE = re.compile(r"^[6-9]\d{9}$")


def _parse_indian_mobile(phone: str) -> str | None:
    digits = re.sub(r"\D", "", (phone or "").strip())
    if digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    if len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if not _INDIAN_MOBILE_RE.match(digits):
        return None
    return digits


def _format_indian_phone(phone: str) -> str:
    ten = _parse_indian_mobile(phone)
    return f"+91{ten}" if ten else phone


def _display_tool_args(args: dict) -> dict:
    out = dict(args)
    if "phone" in out and out["phone"] is not None:
        ten = _parse_indian_mobile(str(out["phone"]))
        if ten:
            out["phone"] = f"+91{ten}"
    return out


def _display_tool_result(result: dict) -> dict:
    out = dict(result)
    if "phone" in out and out["phone"] is not None:
        ten = _parse_indian_mobile(str(out["phone"]))
        if ten:
            out["phone"] = f"+91{ten}"
    return out


def _normalize_slot_date(date: str) -> str:
    now = datetime.now()
    normalized = (date or "").strip().lower()
    if normalized == "today":
        return now.strftime("%Y-%m-%d")
    if normalized == "tomorrow":
        return (now + timedelta(days=1)).strftime("%Y-%m-%d")
    return (date or "").strip()


def _digits_from_speech(text: str) -> str:
    return re.sub(r"\D", "", text or "")


_WORD_TO_DIGIT: dict[str, str] = {
    "zero": "0",
    "oh": "0",
    "one": "1",
    "won": "1",
    "two": "2",
    "to": "2",
    "too": "2",
    "three": "3",
    "four": "4",
    "for": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "ate": "8",
    "nine": "9",
}

_AFFIRMATIONS = frozenset({
    "yes",
    "yeah",
    "yep",
    "yup",
    "correct",
    "right",
    "ok",
    "okay",
    "sure",
    "absolutely",
    "that's right",
    "thats right",
    "that is right",
    "correct",
})


def _words_to_digits(text: str) -> str:
    tokens = re.findall(r"[a-z0-9]+", (text or "").lower())
    out: list[str] = []
    for token in tokens:
        if token.isdigit():
            out.append(token)
        elif token in _WORD_TO_DIGIT:
            out.append(_WORD_TO_DIGIT[token])
    return "".join(out)


def _all_spoken_digits(text: str) -> str:
    direct = _digits_from_speech(text)
    spoken = _words_to_digits(text)
    return direct if len(direct) >= len(spoken) else spoken


def _indian_phones_in_text(text: str) -> list[str]:
    blob = _all_spoken_digits(text)
    found: list[str] = []
    for i in range(max(0, len(blob) - 9)):
        chunk = blob[i : i + 10]
        if _INDIAN_MOBILE_RE.match(chunk):
            found.append(chunk)
    return found


def _is_affirmation(text: str) -> bool:
    normalized = re.sub(r"[^\w\s']", "", (text or "").lower()).strip()
    if not normalized:
        return False
    if normalized in _AFFIRMATIONS:
        return True
    return any(normalized.startswith(f"{word} ") for word in ("yes", "yeah", "yep", "ok", "okay"))


def _phone_stated_in_transcript(
    phone_digits: str,
    user_lines: list[str],
    confirmed_phones: set[str] | None = None,
) -> bool:
    if not phone_digits:
        return False
    if confirmed_phones and phone_digits in confirmed_phones:
        return True
    if not user_lines:
        return False
    blob = _all_spoken_digits(" ".join(user_lines))
    return phone_digits in blob


def _name_stated_in_transcript(name: str, user_lines: list[str]) -> bool:
    if not name or not user_lines:
        return False
    hay = " ".join(user_lines).lower()
    parts = [p for p in re.split(r"\s+", name.strip()) if len(p) >= 2]
    return bool(parts) and any(p.lower() in hay for p in parts)


def _looks_like_invented_phone(digits: str) -> bool:
    if digits in _FAKE_PHONES:
        return True
    if len(set(digits)) <= 2:
        return True
    return False


def _validate_identify_args(
    phone: str,
    name: str,
    user_lines: list[str] | None = None,
    confirmed_phones: set[str] | None = None,
) -> str | None:
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

    digits = _parse_indian_mobile(phone)
    if not digits:
        return (
            "Phone must be a valid 10-digit Indian mobile starting with 6, 7, 8, or 9. "
            "Ask for 10 digits only — no +91 or country code."
        )

    if _looks_like_invented_phone(digits):
        return "That phone number looks invented or like an example. Ask for the caller's real phone number."

    if len(name) < 2 or not re.search(r"[a-zA-Z]", name):
        return "Ask for the caller's full name before calling identify_user."

    lines = user_lines or []
    if not _name_stated_in_transcript(name, lines):
        return (
            "The caller has not stated that name in this conversation yet. "
            "Ask for their full name before calling identify_user."
        )

    if not _phone_stated_in_transcript(digits, lines, confirmed_phones):
        return (
            "The caller has not spoken this phone number yet. Ask them to say their "
            "10-digit mobile number slowly (digits only, no +91), repeat it back, get "
            "confirmation, then call identify_user with exactly what they said."
        )

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
        self._user_lines: list[str] = []
        self._confirmed_phones: set[str] = set()
        self._last_assistant_readback_phones: set[str] = set()
        super().__init__(
            instructions=system_prompt
            + "\nNever call identify_user twice for the same phone in one call."
            + "\nNever call identify_user until the caller has clearly spoken both their full name "
            "and a 10-digit Indian mobile number (6–9 as first digit, no +91). Do not pass placeholders."
            + "\nAfter the caller gives their phone number, repeat all 10 digits back and ask them to confirm "
            "before calling identify_user."
            + "\nNever invent, guess, or use example phone numbers."
        )

    def note_user_speech(self, text: str) -> None:
        cleaned = (text or "").strip()
        if not cleaned:
            return
        if _is_affirmation(cleaned) and self._last_assistant_readback_phones:
            self._confirmed_phones.update(self._last_assistant_readback_phones)
        self._user_lines.append(cleaned)

    def note_assistant_speech(self, text: str) -> None:
        cleaned = (text or "").strip()
        if not cleaned:
            return
        phones = _indian_phones_in_text(cleaned)
        if phones:
            self._last_assistant_readback_phones = set(phones)

    def _require_identified(self) -> str | None:
        if self._identified_phone:
            return None
        return (
            "identify_user must succeed first. Collect the caller's full name and 10-digit "
            "phone (spoken aloud), confirm the number, then call identify_user."
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

        display_args = _display_tool_args(args)
        logger.info(
            "Tool call entry | session_id=%s | tool=%s | args=%s",
            self._session_id,
            tool_name,
            display_args,
        )

        await _emit_tool_event(
            self._room, self._session_id, tool_name, "running", message, {"args": display_args}
        )

        try:
            result = await _execute_tool(self._session_id, tool_name, args)
            if result.get("error") or result.get("status") == "slot_taken":
                status = "error"
            else:
                status = "done"

            display_result = _display_tool_result(result)

            logger.info(
                "Tool call exit | session_id=%s | tool=%s | status=%s | result=%s",
                self._session_id,
                tool_name,
                status,
                display_result,
            )

            await _emit_tool_event(
                self._room, self._session_id, tool_name, status, message, display_result
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

        ONLY call after the caller has spoken their full name and 10-digit mobile aloud
        in this conversation, you repeated the digits back, and they confirmed.

        Args:
            phone: 10-digit Indian mobile (without +91), starting with 6, 7, 8, or 9
            name: Caller full name (as stated by the caller)
        """
        digits = _parse_indian_mobile(phone)
        if self._identified_phone == digits and self._identified_result is not None:
            return self._identified_result

        if err := _validate_identify_args(phone, name, self._user_lines, self._confirmed_phones):
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
                {"args": _display_tool_args({"phone": phone, "name": name}), **result},
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
        """Fetch available appointment slots for a given date.

        Args:
            date: "today", "tomorrow", or YYYY-MM-DD (use the date the caller asked for)
        """
        if err := self._require_identified():
            return json.dumps({"error": err})
        return await self._run_tool("fetch_slots", {"date": _normalize_slot_date(date)})

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
        if err := self._require_identified():
            return json.dumps({"error": err})
        return await self._run_tool(
            "book_appointment",
            {"phone": _parse_indian_mobile(phone) or phone, "date": date, "time": time},
        )

    @function_tool
    async def retrieve_appointments(self, context: RunContext, phone: str) -> str:
        """List active appointments for an identified caller.

        Args:
            phone: Caller phone number (must identify_user first)

        Returns appointments with time (HH:MM 24-hour, use for cancel/modify tools)
        and display_time (12-hour, use when speaking to the caller).
        """
        if err := self._require_identified():
            return json.dumps({"error": err})
        return await self._run_tool(
            "retrieve_appointments", {"phone": _parse_indian_mobile(phone) or phone}
        )

    @function_tool
    async def cancel_appointment(
        self, context: RunContext, phone: str, date: str, time: str
    ) -> str:
        """Cancel an existing appointment for an identified caller.

        Args:
            phone: Caller phone number (must identify_user first)
            date: Appointment date in YYYY-MM-DD format
            time: Exact HH:MM time from retrieve_appointments (24-hour), not display_time
        """
        if err := self._require_identified():
            return json.dumps({"error": err})
        return await self._run_tool(
            "cancel_appointment",
            {"phone": _parse_indian_mobile(phone) or phone, "date": date, "time": time},
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
        if err := self._require_identified():
            return json.dumps({"error": err})
        return await self._run_tool(
            "modify_appointment",
            {
                "phone": _parse_indian_mobile(phone) or phone,
                "old_date": old_date,
                "old_time": old_time,
                "new_date": new_date,
                "new_time": new_time,
            },
        )

    @function_tool
    async def end_conversation(self, context: RunContext) -> str:
        """End the call after the caller explicitly confirms they have no more questions.

        Only call when the user clearly says goodbye or confirms they are done
        (e.g. "that's all", "nothing else", "bye"). Do not call after booking or
        modifying an appointment in the same turn.
        """
        if self._has_ended:
            return json.dumps({"status": "ended", "message": "Call already ended."})
        result_str = await self._run_tool("end_conversation", {})
        try:
            if not json.loads(result_str).get("error"):
                self._has_ended = True
        except json.JSONDecodeError:
            pass
        return result_str

async def _save_recording(session_id: str, path: str) -> None:
    src = Path(path)
    if not src.exists() or src.stat().st_size < 100:
        raise ValueError(f"Recording missing or too short: {path}")

    os.makedirs(RECORDINGS_DIR, exist_ok=True)
    dest = os.path.join(RECORDINGS_DIR, f"{session_id}.ogg")
    shutil.copy2(src, dest)
    logger.info("Saved session recording to %s (%d bytes)", dest, os.path.getsize(dest))


def _session_recording_enabled() -> bool:
    return os.getenv("SESSION_RECORDING", "true").lower() in ("1", "true", "yes")


def _session_record_options() -> bool | dict[str, bool]:
    if not _session_recording_enabled():
        return False
    return {"audio": True, "traces": False, "logs": False, "transcript": False}


async def on_session_end(ctx: JobContext) -> None:
    metadata = _parse_job_metadata(ctx)
    session_id = _resolve_session_id(ctx, metadata)
    if not _session_recording_enabled():
        return
    try:
        report = ctx.make_session_report()
        audio_path = report.audio_recording_path
        if audio_path and audio_path.exists():
            await _save_recording(session_id, str(audio_path))
        else:
            logger.warning(
                "No session audio to save for %s (recording was enabled but audio file missing)",
                session_id,
            )
    except Exception as exc:
        logger.warning("Failed to save session recording for %s: %s", session_id, exc)


@server.rtc_session(agent_name="health-assistant", on_session_end=on_session_end)
async def entrypoint(ctx: JobContext) -> None:
    metadata = _parse_job_metadata(ctx)
    session_id = _resolve_session_id(ctx, metadata)
    agent_config = metadata.get("agent_config") or {}

    system_prompt = agent_config.get("system_prompt") or DEFAULT_SYSTEM_PROMPT

    now = datetime.now()
    tomorrow = (now + timedelta(days=1)).strftime("%Y-%m-%d")
    current_context = (
        f"\n\nCURRENT SYSTEM CONTEXT:\n"
        f"- Current Date (today): {now.strftime('%Y-%m-%d')}\n"
        f"- Tomorrow's Date: {tomorrow}\n"
        f"- Current Time: {now.strftime('%H:%M')}\n"
        f"- Clinic open: 7 days a week\n"
    )

    system_prompt += current_context + (
        "\n\nCRITICAL INSTRUCTION: "
        "1. NEVER output raw function or XML tags like `<function=...>` in your response. "
        "You MUST invoke the native registered tools (identify_user, fetch_slots, book_appointment, end_conversation) directly via the function calling protocol. "
        "Do not type the tool execution as text.\n"
        "2. Never guess or invent tool arguments (like name or phone). Ask the user if missing. "
        "For phone, pass exactly 10 Indian mobile digits (6–9 first digit) without +91 — only digits the caller spoke aloud.\n"
        "2b. Repeat the caller's 10-digit number back and wait for confirmation before identify_user.\n"
        "3. NEVER auto-select a booking time. You MUST list available slots and WAIT for the user to explicitly choose one before calling book_appointment.\n"
        "4. NEVER call fetch_slots for today unless the caller asked about today. "
        "When they ask about tomorrow, call fetch_slots with date \"tomorrow\" or tomorrow's YYYY-MM-DD from context.\n"
        "5. NEVER call end_conversation in the same turn as book_appointment, modify_appointment, or cancel_appointment. "
        "First ask if the caller needs anything else; only call end_conversation after they clearly confirm they are done.\n"
        "6. For appointments: use display_time when speaking to the caller. For cancel_appointment and modify_appointment, "
        "pass the exact time field (HH:MM 24-hour) from retrieve_appointments — never convert spoken times yourself."
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
                "max_delay": 4.0,
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

    agent = HealthAssistantAgent(
        session_id=session_id,
        room=ctx.room,
        system_prompt=system_prompt,
        greeting=greeting,
        tool_labels=tool_labels,
    )

    @session.on("conversation_item_added")
    def on_item_added(event):
        try:
            item = event.item
            role = getattr(item, "role", None)
            content = getattr(item, "content", "")
            text = _extract_conversation_text(content)
            if role not in ("user", "assistant") or not text:
                return
            if role == "user":
                agent.note_user_speech(text)
            else:
                agent.note_assistant_speech(text)
            if role == "assistant" and "<function=" in text:
                logger.warning(
                    "Agent emitted literal function tag in session %s: %s",
                    session_id,
                    text,
                )
                return
            asyncio.create_task(
                _persist_conversation_turn(ctx.room, session_id, role, text)
            )
        except Exception:
            pass

    await ctx.connect()
    await start_avatar(session, ctx.room, provider=avatar_provider)

    await session.start(
        agent=agent,
        room=ctx.room,
        room_input_options=RoomInputOptions(text_enabled=True),
        record=_session_record_options(),
    )


if __name__ == "__main__":
    cli.run_app(server)
