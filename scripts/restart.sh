#!/usr/bin/env bash
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_FILE="$PROJECT_ROOT/docker/docker-compose.yml"
COMPOSE_PROJECT_NAME="ai-skill-sharing-platform-release"

source "$SCRIPT_DIR/ensure-docker.sh"
ensure_docker_ready

cd "$PROJECT_ROOT"
docker compose -p "$COMPOSE_PROJECT_NAME" -f "$COMPOSE_FILE" down
docker compose -p "$COMPOSE_PROJECT_NAME" -f "$COMPOSE_FILE" up -d --build
