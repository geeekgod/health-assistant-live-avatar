.PHONY: dev dev-backend dev-frontend dev-agent docker-build docker-up docker-down docker-logs docker-ps deploy help

# Docker: LIVEKIT=local|cloud|off  DETACH=1 for background
LIVEKIT ?= local
DETACH ?= 0
DOCKER_SCRIPT := bash docker/scripts/compose.sh

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

docker-build:
	LIVEKIT=$(LIVEKIT) $(DOCKER_SCRIPT) build

docker-up:
	LIVEKIT=$(LIVEKIT) DETACH=$(DETACH) $(DOCKER_SCRIPT) up

docker-down:
	LIVEKIT=$(LIVEKIT) $(DOCKER_SCRIPT) down

docker-logs:
	LIVEKIT=$(LIVEKIT) $(DOCKER_SCRIPT) logs

docker-ps:
	LIVEKIT=$(LIVEKIT) $(DOCKER_SCRIPT) ps

deploy:
	LIVEKIT=$(LIVEKIT) bash docker/scripts/deploy.sh

help:
	@echo ""
	@echo "Available make targets:"
	@echo "  dev            Run backend, frontend, and agent (local dev mode)"
	@echo "  dev-backend    Run backend API server locally"
	@echo "  dev-frontend   Run frontend locally"
	@echo "  dev-agent      Run agent worker locally"
	@echo "  docker-build   Build all containers for Docker Compose (LIVEKIT=local|cloud|off)"
	@echo "  docker-up      Start all containers (LIVEKIT=local|cloud|off, DETACH=1 for background)"
	@echo "  docker-down    Stop all containers"
	@echo "  docker-logs    Show logs for all containers"
	@echo "  docker-ps      Show status of all containers"
	@echo "  deploy         Blue-green production deploy (LIVEKIT=cloud)"
	@echo "  help           Show this help message"
	@echo ""