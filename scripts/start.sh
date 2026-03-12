#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_FILE="$PROJECT_ROOT/docker/docker-compose.yml"
COMPOSE_PROJECT_NAME="ai-skill-sharing-platform-release"

source "$SCRIPT_DIR/ensure-docker.sh"

echo "=========================================="
echo "  AI 能力共享平台 - Docker 启动"
echo "=========================================="

ensure_docker_ready
cd "$PROJECT_ROOT"

docker compose -p "$COMPOSE_PROJECT_NAME" -f "$COMPOSE_FILE" up -d --build

echo "⏳ 等待服务健康检查..."
for svc in redis mysql elasticsearch chroma backend; do
  printf "  %-15s" "$svc"
  for i in $(seq 1 90); do
    status=$(docker compose -p "$COMPOSE_PROJECT_NAME" -f "$COMPOSE_FILE" ps --format json "$svc" 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('Health',''))" 2>/dev/null || echo "")
    if [ "$status" = "healthy" ]; then
      echo "✅"
      break
    fi
    if [ "$i" -eq 90 ]; then
      echo "❌ 超时"
      docker compose -p "$COMPOSE_PROJECT_NAME" -f "$COMPOSE_FILE" logs --tail 80 "$svc" || true
      exit 1
    fi
    sleep 1
  done
done

echo "🚀 启动完成"
echo "   前端: http://localhost:15173"
echo "   后端: http://localhost:18080/api/health"
echo "=========================================="
