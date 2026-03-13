#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/ensure-docker.sh"
source "$SCRIPT_DIR/compose-common.sh"

parse_compose_args "$@"

ensure_docker_ready
cd "$PROJECT_ROOT"

echo "🚀 启动基础容器..."
compose_cmd up -d $BUILD_FLAG mysql redis elasticsearch chroma

if [[ "$BUILD_FLAG" == "--build" ]]; then
  echo "🧱 构建应用镜像..."
  compose_cmd build backend frontend
fi

echo "⏳ 等待基础设施健康..."
for svc in redis mysql elasticsearch chroma; do
  printf "  %-15s" "$svc"
  for i in $(seq 1 90); do
    status=$(compose_cmd ps --format json "$svc" 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('Health',''))" 2>/dev/null || echo "")
    if [ "$status" = "healthy" ]; then
      echo "✅"
      break
    fi
    [ "$i" -eq 90 ] && echo "❌ 超时" && exit 1
    sleep 1
  done
done

echo "🗄️ 执行数据库迁移 (migrate)..."
compose_cmd run --rm backend alembic upgrade head

echo "🔎 初始化 ES 索引 (init_es_index)..."
compose_cmd run --rm backend python scripts/init_es_index.py

echo "👤 初始化管理员 (init_admin)..."
compose_cmd run --rm backend python scripts/init_admin.py

echo "🌱 导入发布版种子数据 (init_release_seed)..."
compose_cmd run --rm backend python scripts/init_release_seed.py

echo "🚀 启动应用容器..."
compose_cmd up -d backend frontend

echo "⏳ 等待 backend 健康..."
for i in $(seq 1 90); do
  status=$(compose_cmd ps --format json backend 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('Health',''))" 2>/dev/null || echo "")
  if [ "$status" = "healthy" ]; then
    break
  fi
  [ "$i" -eq 90 ] && echo "❌ backend 健康检查超时" && exit 1
  sleep 1
done

echo "✅ 初始化完成"
echo "   模式: $MODE"
echo "   前端: http://localhost:15173"
echo "   后端: http://localhost:18080"
