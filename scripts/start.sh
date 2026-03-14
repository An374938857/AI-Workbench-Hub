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
ensure_runtime_prereqs
cd "$PROJECT_ROOT"

echo ""
echo "🐳 启动 Docker 基础设施..."
retry_compose_cmd "启动基础容器" up -d $BUILD_FLAG redis mysql elasticsearch chroma || exit 1

echo "⏳ 等待基础设施就绪..."
for svc in redis mysql elasticsearch chroma; do
  wait_for_service_health "$svc" 90 true || exit 1
done

ensure_service_image_ready backend || exit 1

echo "📦 安装依赖..."
echo "   Docker 镜像已内置依赖，跳过本地安装"

echo "🔄 数据库迁移..."
if ! compose_cmd run --rm backend alembic upgrade head; then
  echo "❌ 数据库迁移失败"
  echo "   修复建议："
  echo "   1) 查看日志：docker compose -p \"$COMPOSE_PROJECT_NAME\" $(compose_file_args) logs --tail 120 backend mysql"
  echo "   2) 确认 DATABASE_URL 等配置有效后重试"
  exit 1
fi

echo "🧪 数据库关键表校验..."
if ! compose_cmd run --rm backend python scripts/check_required_tables.py; then
  echo "❌ 数据库结构校验失败（检测到关键表缺失）"
  echo "   修复建议：docker compose -p \"$COMPOSE_PROJECT_NAME\" $(compose_file_args) run --rm backend alembic upgrade head"
  exit 1
fi

ensure_service_image_ready frontend || exit 1

echo ""
echo "🚀 启动应用容器..."
retry_compose_cmd "启动应用容器" up -d $BUILD_FLAG backend frontend || exit 1

echo "⏳ 等待 Backend 健康检查..."
wait_for_service_health backend 90 true || {
  echo "❌ Backend 健康检查失败"
  echo "   修复建议：docker compose -p \"$COMPOSE_PROJECT_NAME\" $(compose_file_args) logs -f backend"
  exit 1
}
echo "✅ Backend 健康检查通过"

backend_container_id="$(compose_cmd ps -q backend | head -n 1)"
compose_files="$(compose_file_args)"

echo "🚀 Backend 已启动 (Container: ${backend_container_id:-unknown})"
echo "   后端接口  http://0.0.0.0:18080"
echo "   前端访问  http://localhost:15173"
echo "   查看日志  docker compose -p \"$COMPOSE_PROJECT_NAME\" $compose_files logs -f backend"
echo "=========================================="
