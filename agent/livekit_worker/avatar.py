"""Optional avatar attach for LiveKit agent sessions.

Provider-specific plugins live here so worker.py stays transport-agnostic.
Switch via agent_config avatar_provider (bey | tavus | none).
"""

from __future__ import annotations

import logging
import os
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from livekit import rtc
    from livekit.agents import AgentSession

logger = logging.getLogger("health-assistant-worker")

AvatarStarter = Callable[["AgentSession", "rtc.Room"], Awaitable[None]]

_LOCAL_LIVEKIT_MARKERS = ("localhost", "127.0.0.1", "livekit:")


def _normalize_livekit_ws_url(url: str) -> str:
    """BEY/Tavus/LiveKit expect ws(s):// — ngrok gives https:// which must become wss://."""
    url = url.strip().rstrip("/")
    if url.startswith("https://"):
        return "wss://" + url[len("https://") :]
    if url.startswith("http://"):
        return "ws://" + url[len("http://") :]
    return url


def _livekit_credentials() -> tuple[str, str, str]:
    """Return (url, api_key, api_secret) for cloud avatar workers joining the SFU."""
    public_url = os.getenv("LIVEKIT_PUBLIC_URL", "").strip()
    local_url = os.getenv("LIVEKIT_URL", "").strip()
    url = _normalize_livekit_ws_url(public_url or local_url)

    api_key = os.getenv("LIVEKIT_API_KEY", "")
    api_secret = os.getenv("LIVEKIT_API_SECRET", "")

    if not url or not api_key or not api_secret:
        raise ValueError(
            "LIVEKIT_URL, LIVEKIT_API_KEY, and LIVEKIT_API_SECRET must be set for cloud avatars"
        )

    if not public_url and any(marker in local_url for marker in _LOCAL_LIVEKIT_MARKERS):
        raise ValueError(
            "Cloud avatars (BEY/Tavus) cannot reach ws://localhost or docker-internal LiveKit. "
            "Set LIVEKIT_PUBLIC_URL=wss://<tunnel-host> (from ngrok/cloudflared) or use LiveKit Cloud."
        )

    if public_url and public_url.startswith("https://"):
        logger.warning(
            "LIVEKIT_PUBLIC_URL uses https:// — auto-converted to %s for WebSocket",
            url,
        )

    return url, api_key, api_secret


async def _start_bey(session: AgentSession, room: rtc.Room) -> None:
    if not os.getenv("BEY_API_KEY"):
        logger.warning("avatar_provider=bey but BEY_API_KEY unset — audio-only")
        return

    livekit_url, livekit_api_key, livekit_api_secret = _livekit_credentials()
    logger.info(
        "Starting BEY avatar against LiveKit url=%s room=%s",
        livekit_url,
        room.name,
    )

    from livekit.agents import APIConnectOptions
    from livekit.plugins import bey

    avatar_id = os.getenv("BEY_AVATAR_ID")
    conn_options = APIConnectOptions(max_retry=2, retry_interval=1.0, timeout=30.0)
    avatar = (
        bey.AvatarSession(avatar_id=avatar_id, conn_options=conn_options)
        if avatar_id
        else bey.AvatarSession(conn_options=conn_options)
    )
    await avatar.start(
        session,
        room=room,
        livekit_url=livekit_url,
        livekit_api_key=livekit_api_key,
        livekit_api_secret=livekit_api_secret,
    )
    logger.info(
        "Beyond Presence avatar started in room=%s via %s",
        room.name,
        livekit_url,
    )


async def _start_tavus(session: AgentSession, room: rtc.Room) -> None:
    if not os.getenv("TAVUS_API_KEY"):
        logger.warning("avatar_provider=tavus but TAVUS_API_KEY unset — audio-only")
        return

    persona_id = os.getenv("TAVUS_PERSONA_ID", "").strip()
    replica_id = (
        os.getenv("TAVUS_REPLICA_ID", "").strip()
        or os.getenv("TAVUS_FACE_ID", "").strip()
    )
    if not persona_id or not replica_id:
        logger.warning(
            "avatar_provider=tavus but TAVUS_PERSONA_ID and "
            "TAVUS_REPLICA_ID (or TAVUS_FACE_ID) are required — audio-only"
        )
        return

    logger.info(
        "Starting Tavus avatar (persona=%s, replica=%s) in room=%s",
        persona_id,
        replica_id,
        room.name,
    )

    from livekit.agents import APIConnectOptions
    from livekit.plugins import tavus

    conn_options = APIConnectOptions(max_retry=2, retry_interval=1.0, timeout=30.0)
    avatar = tavus.AvatarSession(
        persona_id=persona_id,
        replica_id=replica_id,
        conn_options=conn_options,
    )
    await avatar.start(session, room=room)
    logger.info("Tavus avatar started in room=%s", room.name)


_STARTERS: dict[str, AvatarStarter] = {
    "bey": _start_bey,
    "tavus": _start_tavus,
}


async def start_avatar(
    session: AgentSession,
    room: rtc.Room,
    *,
    provider: str | None = None,
) -> str:
    """Attach avatar if configured. Returns active provider or 'none'."""
    resolved = (provider or os.getenv("AVATAR_PROVIDER", "none")).lower().strip()
    if resolved == "none":
        logger.info("avatar_provider=none — audio-only")
        return "none"

    starter = _STARTERS.get(resolved)
    if starter is None:
        logger.warning("Unknown avatar_provider=%s — audio-only", resolved)
        return "none"

    try:
        await starter(session, room)
        return resolved
    except ValueError as exc:
        logger.error("%s — audio-only", exc)
        return "none"
    except Exception as exc:
        detail = str(exc).lower()
        if "timed out" in detail or "connection" in detail:
            logger.error(
                "Avatar ICE/media failed (signaling may work via ngrok but UDP 50000-60000 "
                "is not reachable from cloud avatars on Mac+Docker). "
                "Fix: use LiveKit Cloud for LIVEKIT_URL + LIVEKIT_PUBLIC_URL, or deploy "
                "LiveKit on a VPS with public UDP. Error: %s",
                exc,
            )
        else:
            logger.exception("Avatar provider %s failed — continuing audio-only", resolved)
        return "none"
