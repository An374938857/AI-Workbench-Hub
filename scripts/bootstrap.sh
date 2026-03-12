#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_FILE="$PROJECT_ROOT/docker/docker-compose.yml"
COMPOSE_PROJECT_NAME="ai-skill-sharing-platform-release"

source "$SCRIPT_DIR/ensure-docker.sh"

ensure_docker_ready
cd "$PROJECT_ROOT"

echo "🚀 启动基础容器..."
docker compose -p "$COMPOSE_PROJECT_NAME" -f "$COMPOSE_FILE" up -d --build mysql redis elasticsearch chroma

echo "⏳ 等待 mysql 健康..."
for svc in mysql; do
  for i in $(seq 1 90); do
    status=$(docker compose -p "$COMPOSE_PROJECT_NAME" -f "$COMPOSE_FILE" ps --format json "$svc" 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('Health',''))" 2>/dev/null || echo "")
    if [ "$status" = "healthy" ]; then
      break
    fi
    [ "$i" -eq 90 ] && echo "❌ $svc 健康检查超时" && exit 1
    sleep 1
  done
done

echo "🗄️ 执行数据库迁移..."
docker compose -p "$COMPOSE_PROJECT_NAME" -f "$COMPOSE_FILE" run --rm backend alembic upgrade head

echo "🔎 初始化 ES 索引..."
docker compose -p "$COMPOSE_PROJECT_NAME" -f "$COMPOSE_FILE" run --rm backend python scripts/init_es_index.py

echo "👤 初始化管理员..."
docker compose -p "$COMPOSE_PROJECT_NAME" -f "$COMPOSE_FILE" run --rm backend python scripts/init_admin.py

echo "🚀 启动应用容器..."
docker compose -p "$COMPOSE_PROJECT_NAME" -f "$COMPOSE_FILE" up -d backend frontend

echo "⏳ 等待 backend 健康..."
for i in $(seq 1 90); do
  status=$(docker compose -p "$COMPOSE_PROJECT_NAME" -f "$COMPOSE_FILE" ps --format json backend 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('Health',''))" 2>/dev/null || echo "")
  if [ "$status" = "healthy" ]; then
    break
  fi
  [ "$i" -eq 90 ] && echo "❌ backend 健康检查超时" && exit 1
  sleep 1
done

echo "✅ 初始化完成"
echo "   前端: http://localhost:15173"
echo "   后端: http://localhost:18080"
