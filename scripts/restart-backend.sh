#!/usr/bin/env bash
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/compose-common.sh"

parse_compose_args "$@"

cd "$PROJECT_ROOT"
if [[ "$REBUILD_FLAG" == "true" ]]; then
  compose_cmd up -d --build backend
else
  compose_cmd restart backend
fi
