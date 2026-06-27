.PHONY: dev dev-backend dev-frontend dev-agent

dev:
	@trap 'kill 0' INT TERM; \
	echo "Starting backend (http://localhost:8000) and frontend (http://localhost:3000)…"; \
	(cd backend && uv run uvicorn app.main:app --reload --port 8000) & \
	(cd frontend && bun run dev) & \
	wait

dev-backend:
	cd backend && uv run uvicorn app.main:app --reload --port 8000

dev-agent:
	cd agent && uv run python -m livekit_worker.worker dev

dev-frontend:
	cd frontend && bun run dev
