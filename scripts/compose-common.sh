#!/usr/bin/env bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_PROJECT_NAME="ai-skill-sharing-platform-release"
MODE="prod"
BUILD_FLAG=""
REBUILD_FLAG="false"
POSITIONAL_ARGS=()

parse_compose_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --dev)
        MODE="dev"
        shift
        ;;
      --prod)
        MODE="prod"
        shift
        ;;
      --build)
        BUILD_FLAG="--build"
        shift
        ;;
      --rebuild)
        BUILD_FLAG="--build"
        REBUILD_FLAG="true"
        shift
        ;;
      *)
        POSITIONAL_ARGS+=("$1")
        shift
        ;;
    esac
  done
}

compose_file_args() {
  local args=(-f "$PROJECT_ROOT/docker/docker-compose.yml")
  if [[ "$MODE" == "dev" ]]; then
    args+=(-f "$PROJECT_ROOT/docker/docker-compose.dev.yml")
  else
    args+=(-f "$PROJECT_ROOT/docker/docker-compose.prod.yml")
  fi
  echo "${args[@]}"
}

compose_cmd() {
  local compose_files
  # shellcheck disable=SC2207
  compose_files=($(compose_file_args))
  docker compose -p "$COMPOSE_PROJECT_NAME" "${compose_files[@]}" "$@"
}

