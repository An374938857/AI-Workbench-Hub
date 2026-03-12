#!/usr/bin/env bash

docker_info_output() {
  docker info 2>&1
}

is_docker_daemon_connection_error() {
  case "$1" in
    *"Cannot connect to the Docker daemon"*|*"Is the docker daemon running?"*|*"docker.sock"*|*"error during connect"*)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

force_kill_docker() {
  echo "⚠️  检测到 Docker daemon 连接异常，准备强制重启 Docker..."

  case "$(uname -s)" in
    Darwin)
      pkill -9 -x Docker >/dev/null 2>&1 || true
      pkill -9 -f "Docker Desktop" >/dev/null 2>&1 || true
      pkill -9 -f "com.docker.backend" >/dev/null 2>&1 || true
      pkill -9 -f "com.docker.vmnetd" >/dev/null 2>&1 || true
      ;;
    Linux)
      if command -v systemctl >/dev/null 2>&1; then
        systemctl stop docker >/dev/null 2>&1 || true
      fi
      pkill -9 dockerd >/dev/null 2>&1 || true
      pkill -9 containerd >/dev/null 2>&1 || true
      ;;
  esac

  sleep 2
}

start_docker_service() {
  case "$(uname -s)" in
    Darwin)
      open -ga Docker >/dev/null 2>&1 || open -a Docker >/dev/null 2>&1 || true
      ;;
    Linux)
      if command -v systemctl >/dev/null 2>&1; then
        systemctl start docker >/dev/null 2>&1 || true
      fi
      ;;
  esac
}

wait_for_docker_ready() {
  echo "⏳ 等待 Docker 服务就绪..."
  for i in $(seq 1 90); do
    if docker info >/dev/null 2>&1; then
      echo "✅ Docker 已就绪"
      return 0
    fi
    sleep 2
  done

  return 1
}

ensure_docker_ready() {
  if ! command -v docker >/dev/null 2>&1; then
    echo "❌ 未检测到 Docker 命令，请先安装 Docker Desktop / Docker Engine"
    exit 1
  fi

  local docker_status_output
  if docker_status_output="$(docker_info_output)"; then
    return 0
  fi

  if is_docker_daemon_connection_error "$docker_status_output"; then
    force_kill_docker
  else
    echo "🐳 检测到 Docker 未就绪，正在尝试拉起..."
  fi

  start_docker_service

  if wait_for_docker_ready; then
    return 0
  fi

  echo "❌ Docker 启动超时，请手动确认 Docker Desktop / Docker Engine 是否已启动"
  echo "$docker_status_output"
  exit 1
}
