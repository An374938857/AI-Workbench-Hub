#!/usr/bin/env bash
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/ensure-docker.sh"
source "$SCRIPT_DIR/compose-common.sh"

parse_compose_args "$@"
ensure_docker_ready

cd "$PROJECT_ROOT"
if [[ "$REBUILD_FLAG" == "true" ]]; then
  compose_cmd down --remove-orphans
  compose_cmd up -d --build
else
  compose_cmd down
  compose_cmd up -d $BUILD_FLAG
fi
