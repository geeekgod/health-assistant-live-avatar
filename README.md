# Health Assistant Live Avatar

A system for a live voice and video AI agent to act as a healthcare front desk assistant.

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
