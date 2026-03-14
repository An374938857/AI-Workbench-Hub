#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/ensure-docker.sh"
source "$SCRIPT_DIR/compose-common.sh"

parse_compose_args "$@"

ensure_docker_ready
ensure_runtime_prereqs
cd "$PROJECT_ROOT"

echo "🚀 启动基础容器..."
retry_compose_cmd "启动基础容器" up -d $BUILD_FLAG mysql redis elasticsearch chroma || exit 1

if [[ "$BUILD_FLAG" == "--build" ]]; then
  echo "🧱 构建应用镜像..."
  retry_compose_cmd "构建应用镜像" build backend frontend || exit 1
fi

echo "⏳ 等待基础设施健康..."
for svc in redis mysql elasticsearch chroma; do
  wait_for_service_health "$svc" 90 true || exit 1
done

ensure_service_image_ready backend || exit 1

echo "🗄️ 执行数据库迁移 (migrate)..."
if ! compose_cmd run --rm backend alembic upgrade head; then
  echo "❌ 数据库迁移失败"
  echo "   修复建议："
  echo "   1) 查看日志：docker compose -p \"$COMPOSE_PROJECT_NAME\" $(compose_file_args) logs --tail 120 backend mysql"
  echo "   2) 清理并重试：./scripts/restart.sh --rebuild"
  exit 1
fi

echo "🧪 校验数据库关键表 (schema_check)..."
if ! compose_cmd run --rm backend python scripts/check_required_tables.py; then
  echo "❌ 数据库结构校验失败（检测到关键表缺失）"
  echo "   修复建议："
  echo "   1) 执行迁移：docker compose -p \"$COMPOSE_PROJECT_NAME\" $(compose_file_args) run --rm backend alembic upgrade head"
  echo "   2) 执行排查 SQL："
  echo "      SELECT table_name FROM information_schema.tables"
  echo "      WHERE table_schema = DATABASE()"
  echo "      AND table_name IN ('conversation_compression_logs','custom_commands','model_fallback_configs','model_fallback_logs','model_comparisons');"
  exit 1
fi

echo "🔎 初始化 ES 索引 (init_es_index)..."
if ! compose_cmd run --rm backend python scripts/init_es_index.py; then
  echo "❌ ES 索引初始化失败"
  echo "   修复建议：docker compose -p \"$COMPOSE_PROJECT_NAME\" $(compose_file_args) logs --tail 120 elasticsearch backend"
  exit 1
fi

echo "👤 初始化管理员 (init_admin)..."
if ! compose_cmd run --rm backend python scripts/init_admin.py; then
  echo "❌ 管理员初始化失败"
  echo "   修复建议：docker compose -p \"$COMPOSE_PROJECT_NAME\" $(compose_file_args) logs --tail 120 backend mysql"
  exit 1
fi

echo "🌱 导入发布版种子数据 (init_release_seed)..."
if ! compose_cmd run --rm backend python scripts/init_release_seed.py; then
  echo "❌ 发布种子导入失败"
  echo "   修复建议："
  echo "   1) 查看日志：docker compose -p \"$COMPOSE_PROJECT_NAME\" $(compose_file_args) logs --tail 160 backend"
  echo "   2) 修复后重试：./scripts/bootstrap.sh ${MODE:+--$MODE}"
  exit 1
fi

ensure_service_image_ready frontend || exit 1

echo "🚀 启动应用容器..."
retry_compose_cmd "启动应用容器" up -d backend frontend || exit 1

echo "⏳ 等待 backend 健康..."
wait_for_service_health backend 90 true || {
  echo "❌ backend 健康检查超时"
  exit 1
}

echo "✅ 初始化完成"
echo "   模式: $MODE"
echo "   前端: http://localhost:15173"
echo "   后端: http://localhost:18080"
