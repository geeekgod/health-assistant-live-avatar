dev-backend:
	cd backend && uv run uvicorn app.main:app --reload --port 8000

dev-agent:
	cd agent && uv run python -m livekit_worker.worker dev

dev-frontend:
	cd frontend && bun run dev
