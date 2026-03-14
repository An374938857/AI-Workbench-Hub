#!/usr/bin/env bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_PROJECT_NAME="ai-skill-sharing-platform-release"
BACKEND_ENV_FILE="${BACKEND_ENV_FILE:-$PROJECT_ROOT/backend/.env}"
BACKEND_ENV_TEMPLATE_FILE="${BACKEND_ENV_TEMPLATE_FILE:-$PROJECT_ROOT/backend/.env.example}"
MODE="prod"
BUILD_FLAG=""
REBUILD_FLAG="false"
POSITIONAL_ARGS=()

parse_compose_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --dev)
        MODE="dev"
        shift
        ;;
      --prod)
        MODE="prod"
        shift
        ;;
      --build)
        BUILD_FLAG="--build"
        shift
        ;;
      --rebuild)
        BUILD_FLAG="--build"
        REBUILD_FLAG="true"
        shift
        ;;
      *)
        POSITIONAL_ARGS+=("$1")
        shift
        ;;
    esac
  done
}

compose_file_args() {
  local args=(-f "$PROJECT_ROOT/docker/docker-compose.yml")
  if [[ "$MODE" == "dev" ]]; then
    args+=(-f "$PROJECT_ROOT/docker/docker-compose.dev.yml")
  else
    args+=(-f "$PROJECT_ROOT/docker/docker-compose.prod.yml")
  fi
  echo "${args[@]}"
}

compose_cmd() {
  local compose_files
  # shellcheck disable=SC2207
  compose_files=($(compose_file_args))
  docker compose -p "$COMPOSE_PROJECT_NAME" "${compose_files[@]}" "$@"
}

ensure_compose_cli_ready() {
  if ! docker compose version >/dev/null 2>&1; then
    echo "❌ 未检测到可用的 Docker Compose 插件（docker compose）"
    echo "   修复建议：升级 Docker Desktop / Docker Engine 后重试"
    exit 1
  fi
}

load_backend_env() {
  if [[ -f "$BACKEND_ENV_FILE" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$BACKEND_ENV_FILE"
    set +a
  fi
}

ensure_backend_env_file_exists() {
  if [[ -f "$BACKEND_ENV_FILE" ]]; then
    return 0
  fi

  if [[ -f "$BACKEND_ENV_TEMPLATE_FILE" ]]; then
    cp "$BACKEND_ENV_TEMPLATE_FILE" "$BACKEND_ENV_FILE"
    echo "ℹ️  已自动创建 backend/.env（来源: backend/.env.example）"
    return 0
  fi

  : >"$BACKEND_ENV_FILE"
  echo "ℹ️  未找到 backend/.env.example，已创建空的 backend/.env"
}

upsert_env_key_value() {
  local key="$1"
  local value="$2"
  local target_file="$3"
  local tmp_file
  tmp_file="$(mktemp)"

  awk -v key="$key" -v value="$value" '
    BEGIN { updated = 0 }
    {
      if ($0 ~ ("^" key "=")) {
        if (!updated) {
          print key "=" value
          updated = 1
        }
        next
      }
      print $0
    }
    END {
      if (!updated) {
        print key "=" value
      }
    }
  ' "$target_file" >"$tmp_file"

  mv "$tmp_file" "$target_file"
}

generate_encryption_key_via_docker() {
  docker run --rm python:3.11-alpine \
    python -c "import base64,os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
}

auto_configure_encryption_key() {
  local generated_key
  if ! generated_key="$(generate_encryption_key_via_docker)"; then
    echo "❌ 自动生成 ENCRYPTION_KEY 失败"
    echo "   修复建议：确认 Docker 网络可访问镜像仓库后重试"
    return 1
  fi

  upsert_env_key_value "ENCRYPTION_KEY" "$generated_key" "$BACKEND_ENV_FILE"
  export ENCRYPTION_KEY="$generated_key"
  echo "✅ 已自动生成并写入 ENCRYPTION_KEY 到 backend/.env"
  return 0
}

ensure_encryption_key_configured() {
  ensure_backend_env_file_exists
  load_backend_env

  if [[ -n "${ENCRYPTION_KEY:-}" ]]; then
    upsert_env_key_value "ENCRYPTION_KEY" "$ENCRYPTION_KEY" "$BACKEND_ENV_FILE"
    return 0
  fi

  auto_configure_encryption_key || exit 1
}

is_port_in_use() {
  local port="$1"
  if command -v lsof >/dev/null 2>&1; then
    lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1
    return $?
  fi

  if command -v ss >/dev/null 2>&1; then
    ss -ltn 2>/dev/null | awk '{print $4}' | grep -Eq "[:.]${port}$"
    return $?
  fi

  if command -v netstat >/dev/null 2>&1; then
    netstat -an 2>/dev/null | grep -E "LISTEN|LISTENING" | grep -Eq "[:.]${port}[[:space:]]"
    return $?
  fi

  return 1
}

get_port_owner() {
  local port="$1"
  if command -v lsof >/dev/null 2>&1; then
    lsof -nP -iTCP:"$port" -sTCP:LISTEN | awk 'NR==2{print $1 " (pid=" $2 ")"}'
    return 0
  fi
  echo "unknown"
  return 0
}

ensure_required_ports_free() {
  local mappings=(
    "15173:frontend"
    "18080:backend"
    "13306:mysql"
    "16379:redis"
    "19200:elasticsearch"
    "18000:chroma"
  )
  local conflicted=()
  local mapping port service status

  for mapping in "${mappings[@]}"; do
    port="${mapping%%:*}"
    service="${mapping##*:}"
    if is_port_in_use "$port"; then
      status="$(service_health_status "$service")"
      if [[ "$status" == "healthy" || "$status" == "running" ]]; then
        continue
      fi
      conflicted+=("$port")
    fi
  done

  if [[ "${#conflicted[@]}" -eq 0 ]]; then
    return 0
  fi

  echo "❌ 检测到端口冲突："
  for port in "${conflicted[@]}"; do
    echo "   - $port (占用进程: $(get_port_owner "$port"))"
  done
  echo "   修复建议：停止占用端口的进程后重试，或调整 docker-compose 端口映射"
  exit 1
}

ensure_runtime_prereqs() {
  ensure_compose_cli_ready
  load_backend_env
  ensure_encryption_key_configured
  ensure_required_ports_free
}

service_health_status() {
  local service="$1"
  local container_id
  container_id="$(compose_cmd ps -q "$service" | head -n 1)"
  if [[ -z "$container_id" ]]; then
    echo "missing"
    return 0
  fi

  docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container_id" 2>/dev/null || echo "unknown"
}

wait_for_service_health() {
  local service="$1"
  local timeout_sec="$2"
  local show_logs="${3:-false}"
  local status=""
  local i

  printf "  %-15s" "$service"
  for i in $(seq 1 "$timeout_sec"); do
    status="$(service_health_status "$service")"
    if [[ "$status" == "healthy" || "$status" == "running" ]]; then
      echo "✅"
      return 0
    fi
    sleep 1
  done

  echo "❌ 超时 (last_status=${status:-unknown})"
  if [[ "$show_logs" == "true" ]]; then
    compose_cmd logs --tail 120 "$service" || true
  fi
  return 1
}
