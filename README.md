# Health Assistant Live Avatar

A system for a live voice and video AI agent to act as a healthcare front desk assistant. It orchestrates real-time voice, video (avatar), and tool-execution capabilities to converse with patients, identify them, and manage their appointments.

## System Architecture & Overview

### High-Level Flow
1. **User interaction:** A user opens the frontend and initiates a call session. 
2. **Session Initialization:** The Next.js frontend requests a session from the FastAPI backend. The backend creates a DB record, provisions a LiveKit room, and dispatches the AI worker.
3. **Real-time WebRTC:** The frontend connects to the LiveKit server. The Python LiveKit worker joins the same room.
4. **Conversation Loop:** 
   - **STT (Speech-to-Text):** Deepgram transcribes user audio.
   - **LLM:** Groq processes the user intent based on a healthcare-specific system prompt.
   - **Tools:** The LLM triggers function calls (e.g., `book_appointment`), which the worker executes by proxying HTTP requests to the FastAPI backend.
   - **TTS (Text-to-Speech):** Cartesia (or Gemini) synthesizes the AI's response.
5. **Post-Call:** Upon ending the call, the backend utilizes Groq to generate a structured JSON summary (Chief complaint, action items, call rating) and saves the audio recording.

### Core Technologies
- **Frontend:** Next.js (React), Tailwind CSS, LiveKit React Components.
- **Backend:** Python FastAPI, SQLAlchemy (SQLite/Async).
- **Agent Worker:** Python, LiveKit Agents SDK, Groq (LLM), Deepgram (STT), Cartesia (TTS).
- **Infrastructure:** Docker Compose, Nginx, GitHub Actions (Blue/Green Deployment).

## Project Structure Breakdown

| Directory / File | Description |
| :--- | :--- |
| `frontend/` | Next.js application handling the UI, WebRTC video/audio handling, and session history viewing. |
| `backend/` | FastAPI application acting as the control plane. Manages DB state (SQLite) for users and bookings. |
| `agent/` | The LiveKit Agent worker script. Contains the logic for the AI's turn-taking, STT, LLM inference, TTS, and function calling. |
| `docker/` | Dockerfiles and Docker Compose configuration. Supports local or cloud LiveKit instances. |
| `nginx/` | Deployment scripts and Nginx configuration for production blue-green deployment. |
| `Makefile` | CLI shortcuts for local development (`make dev`) and container orchestration (`make docker-up`). |

### 1. Frontend (`frontend/`)

Built with Next.js App Router and styled with Tailwind CSS + Radix UI primitives. It uses `@livekit/components-react` heavily to manage WebRTC connections.

**Key Routes**
- `/call`: The active session view where the user speaks with the AI. Includes the `AvatarVideo` component and a `ToolActivityFeed` showing background API actions.
- `/conversations`: A list of historical calls, displaying status and previews.
- `/summary/[id]`: A detailed post-call view showing the structured AI summary, full transcript, tool execution history, and audio recording playback (`CallRecordingPlayer`).

**LiveKit Integration**
The frontend relies on receiving a LiveKit JWT token from the backend. It uses `<LiveKitRoom>` to connect to the server and manages local microphone/camera tracks. The UI reacts to Custom Events emitted by the agent (e.g., `tool_call`, `transcript`) to update the UI without requiring polling.

### 2. Backend (`backend/`)

A FastAPI application that acts as the source of truth for application state, proxying LLM tool requests into database mutations.

**Database Models (`app/db/models.py`)**
- `Contact`: Represents a patient (identified via Indian mobile number and Name).
- `Booking`: Represents an appointment. Contains unique constraints to prevent double-booking active slots.
- `CallSession`: The overarching container for a single call. Tracks timestamps, the full transcript, and the final LLM-generated summary.
- `ToolEvent`: An audit log of every function call attempted by the AI agent during a session.

**Core API Routes**
- `POST /api/sessions`: Parses `healthcare_front_desk.yaml`, creates a LiveKit token, and dispatches the worker.
- `POST /api/tools/execute`: The endpoint the Agent hits when the LLM triggers a function call. Handles logic for booking, modifying, and canceling appointments.
- `GET /api/summaries/{session_id}`: If a session has ended and needs a summary, it triggers `generate_summary_with_llm` to process the transcript and tool events into a structured JSON response.

**Templating**
Behavior is dictated by `backend/app/templates/healthcare_front_desk.yaml`. This file defines the system prompt, greeting, tool labels, and the specific fields the LLM must extract for the post-call summary.

### 3. AI Agent Worker (`agent/`)

The heart of the conversational AI. Built on the LiveKit Agents SDK.

**Lifecycle (`agent/livekit_worker/worker.py`)**
1. **Entrypoint:** `entrypoint` is triggered by LiveKit Server upon a Dispatch request from the backend.
2. **Configuration:** Reads the session context, current date/time, and constructs a strict System Prompt ensuring the LLM doesn't hallucinate user data.
3. **Session Setup:** Configures `VoicePipelineAgent` with Deepgram (STT), Groq (LLM), and Cartesia (TTS). Implements Voice Activity Detection (VAD) for turn-taking and interruptions.
4. **Execution:** Listens to user audio, streams to STT, feeds text to LLM.

**Function Calling (Tools)**
The agent strictly enforces that the LLM must ask the user for data before executing tools. Available tools include:
- `identify_user`: Requires a 10-digit phone and full name. Will reject the LLM's request if the user hasn't explicitly spoken this information.
- `fetch_slots`: Returns available times based on backend DB state.
- `book_appointment`, `cancel_appointment`, `modify_appointment`: Mutates the backend schedule.
- `end_conversation`: Triggers the session termination sequence.

*Note: The agent worker communicates with the backend via a secure `WORKER_API_SECRET` token.*

---

## Development

```bash
make dev-backend
make dev-agent
make dev-frontend
```

Or all at once:

```bash
make dev
```

## Docker

All Docker assets live under [`docker/`](docker/):

| Path                         | Purpose                                            |
| ---------------------------- | -------------------------------------------------- |
| `docker/compose.yml`         | Service orchestration                              |
| `docker/livekit.yaml`        | Self-hosted LiveKit config                         |
| `docker/.env.example`        | Environment template                               |
| `docker/frontend/Dockerfile` | Next.js standalone (distroless, &lt;100 MB target) |
| `docker/backend/Dockerfile`  | FastAPI + uv multi-stage                           |
| `docker/agent/Dockerfile`    | LiveKit agent worker                               |
| `docker/scripts/compose.sh`  | Compose helper used by Makefile                    |

```bash
cp docker/.env.example docker/.env   # first time only (auto-copied on docker-up)

# Full stack with local LiveKit (default)
make docker-build LIVEKIT=local
make docker-up LIVEKIT=local

# LiveKit Cloud — set wss:// URL + keys in docker/.env
make docker-up LIVEKIT=cloud

# Frontend + backend only (no agent, no LiveKit)
make docker-up LIVEKIT=off

# Run detached
make docker-up LIVEKIT=local DETACH=1

make docker-down LIVEKIT=local
make docker-logs LIVEKIT=local
```

Open **http://localhost:3000** (frontend) and **http://localhost:8000/docs** (API).

**Profiles**

| `LIVEKIT` | Services started                                          |
| --------- | --------------------------------------------------------- |
| `local`   | livekit, backend, agent, frontend                         |
| `cloud`   | backend, agent, frontend (external LiveKit URL in `.env`) |
| `off`     | backend, frontend only                                    |

**Notes**

- `NEXT_PUBLIC_API_URL` is baked in at frontend **build** time — rebuild after changing it.
- Browser clients use `LIVEKIT_URL` from `docker/.env`; the agent uses `LIVEKIT_INTERNAL_URL` (`ws://livekit:7880` when local).
- Recordings and SQLite DB persist in Docker volumes (`recordings`, `app-data`).
- **Health:** backend `GET /health` (liveness) and `GET /health/ready` (DB check); frontend `GET /api/health`.
- **Autoheal:** `docker/scripts/autoheal.sh` runs a singleton container that restarts unhealthy labelled services.

## Deploy (GitHub Actions)

One workflow: [`.github/workflows/deploy.yml`](.github/workflows/deploy.yml)

On push to `main` (or manual run), it SSHs to your server, runs `git pull`, then `docker/scripts/deploy.sh` (build + blue-green).

**Secrets:** Add under **Settings → Environments → production** (or repository secrets):

`SSH_HOST`, `SSH_USER`, `SSH_PRIVATE_KEY` — optional: `SSH_PORT`, `DEPLOY_PATH`, `LIVEKIT_MODE`

See **[docs/DEPLOY.md](docs/DEPLOY.md)** for SSH key setup and server bootstrap.

## Nginx (production)

Configs and scripts under [`nginx/`](nginx/). On the server:

```bash
sudo bash nginx/scripts/install.sh blue
sudo bash nginx/scripts/enable-ssl.sh
```
