#!/usr/bin/env bash
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/ensure-docker.sh"
source "$SCRIPT_DIR/compose-common.sh"

parse_compose_args "$@"
ensure_docker_ready

cd "$PROJECT_ROOT"
if [[ "$REBUILD_FLAG" == "true" ]]; then
  echo "🧹 清理容器与网络（含孤儿容器）..."
  compose_cmd down --remove-orphans
  echo "🔁 重新启动（重建镜像）..."
  exec "$SCRIPT_DIR/start.sh" --build ${MODE:+--$MODE}
else
  echo "🧹 清理容器与网络..."
  compose_cmd down
  echo "🔁 重新启动..."
  if [[ -n "$BUILD_FLAG" ]]; then
    exec "$SCRIPT_DIR/start.sh" "$BUILD_FLAG" ${MODE:+--$MODE}
  else
    exec "$SCRIPT_DIR/start.sh" ${MODE:+--$MODE}
  fi
fi
