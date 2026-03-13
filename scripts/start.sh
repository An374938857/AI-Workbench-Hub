#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/ensure-docker.sh"
source "$SCRIPT_DIR/compose-common.sh"

parse_compose_args "$@"

echo "=========================================="
echo "  AI 能力共享平台 - Docker 启动"
echo "=========================================="
echo "  模式: $MODE"

ensure_docker_ready
cd "$PROJECT_ROOT"

echo ""
echo "🐳 启动 Docker 基础设施..."
compose_cmd up -d $BUILD_FLAG redis mysql elasticsearch chroma

echo "⏳ 等待基础设施就绪..."
for svc in redis mysql elasticsearch chroma; do
  printf "  %-15s" "$svc"
  for i in $(seq 1 90); do
    status=$(compose_cmd ps --format json "$svc" 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('Health',''))" 2>/dev/null || echo "")
    if [ "$status" = "healthy" ]; then
      echo "✅"
      break
    fi
    if [ "$i" -eq 90 ]; then
      echo "❌ 超时"
      compose_cmd logs --tail 80 "$svc" || true
      exit 1
    fi
    sleep 1
  done
done

echo "📦 安装依赖..."
echo "   Docker 镜像已内置依赖，跳过本地安装"

echo "🔄 数据库迁移..."
compose_cmd run --rm backend alembic upgrade head

echo ""
echo "🚀 启动应用容器..."
compose_cmd up -d $BUILD_FLAG backend frontend

echo "⏳ 等待 Backend 健康检查..."
for i in $(seq 1 90); do
  status=$(compose_cmd ps --format json backend 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('Health',''))" 2>/dev/null || echo "")
  if [ "$status" = "healthy" ]; then
    echo "✅ Backend 健康检查通过"
    break
  fi
  if [ "$i" -eq 90 ]; then
    echo "❌ Backend 健康检查超时"
    compose_cmd logs --tail 120 backend || true
    exit 1
  fi
  sleep 1
done

backend_container_id="$(compose_cmd ps -q backend | head -n 1)"
compose_files="$(compose_file_args)"

echo "🚀 Backend 已启动 (Container: ${backend_container_id:-unknown})"
echo "   后端接口  http://0.0.0.0:18080"
echo "   前端访问  http://localhost:15173"
echo "   查看日志  docker compose -p \"$COMPOSE_PROJECT_NAME\" $compose_files logs -f backend"
echo "=========================================="
