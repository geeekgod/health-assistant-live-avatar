.PHONY: dev dev-backend dev-frontend dev-agent

dev:
	@trap 'kill 0' INT TERM; \
	echo "Starting backend (:8000), frontend (:3000), and agent worker…"; \
	(cd backend && uv run uvicorn app.main:app --reload --port 8000) & \
	(cd frontend && bun run dev) & \
	(cd agent && uv run python -m livekit_worker.worker dev) & \
	wait

dev-backend:
	cd backend && uv run uvicorn app.main:app --reload --port 8000

dev-agent:
	cd agent && uv run python -m livekit_worker.worker dev

dev-frontend:
	cd frontend && bun run dev
