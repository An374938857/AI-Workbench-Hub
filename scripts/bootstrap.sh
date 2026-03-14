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
compose_cmd up -d $BUILD_FLAG mysql redis elasticsearch chroma

if [[ "$BUILD_FLAG" == "--build" ]]; then
  echo "🧱 构建应用镜像..."
  compose_cmd build backend frontend
fi

echo "⏳ 等待基础设施健康..."
for svc in redis mysql elasticsearch chroma; do
  wait_for_service_health "$svc" 90 true || exit 1
done

echo "🗄️ 执行数据库迁移 (migrate)..."
if ! compose_cmd run --rm backend alembic upgrade head; then
  echo "❌ 数据库迁移失败"
  echo "   修复建议："
  echo "   1) 查看日志：docker compose -p \"$COMPOSE_PROJECT_NAME\" $(compose_file_args) logs --tail 120 backend mysql"
  echo "   2) 清理并重试：./scripts/restart.sh --rebuild"
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
  echo "   1) 确认 ENCRYPTION_KEY 已配置（backend/.env 或当前 shell）"
  echo "   2) 查看日志：docker compose -p \"$COMPOSE_PROJECT_NAME\" $(compose_file_args) logs --tail 160 backend"
  echo "   3) 修复后重试：./scripts/bootstrap.sh ${MODE:+--$MODE}"
  exit 1
fi

echo "🚀 启动应用容器..."
compose_cmd up -d backend frontend

echo "⏳ 等待 backend 健康..."
wait_for_service_health backend 90 true || {
  echo "❌ backend 健康检查超时"
  exit 1
}

echo "✅ 初始化完成"
echo "   模式: $MODE"
echo "   前端: http://localhost:15173"
echo "   后端: http://localhost:18080"
