#!/usr/bin/env bash
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/compose-common.sh"

parse_compose_args "$@"

cd "$PROJECT_ROOT"
compose_cmd down
