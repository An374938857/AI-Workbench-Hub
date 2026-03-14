# Docker 部署说明（统一版）

## 运行模式

本项目采用**全量 Docker**运行：

- 容器：`frontend`、`backend`、`mysql`、`redis`、`elasticsearch`、`chroma`
- 不再支持“本地 backend + 部分 Docker 基础设施”的混合模式

## 支持平台

- Linux + Docker Engine + Docker Compose v2
- macOS + Docker Desktop + Docker Compose v2
- Windows 10/11 + Docker Desktop + Docker Compose v2（建议 WSL2 / Git Bash）

## 目录约定

- `docker/docker-compose.yml`：公共服务定义（默认生产形态）
- `docker/docker-compose.dev.yml`：开发模式覆盖（热更新）
- `docker/docker-compose.prod.yml`：生产模式覆盖
- `docker/Dockerfile.frontend`：前端多阶段镜像（`dev` / `prod`）
- `docker/Dockerfile.elasticsearch`：ES + IK 分词插件
- `docker/nginx.frontend.conf`：前端生产静态站点配置

## 前置准备

1. 复制配置模板：

```bash
cp backend/.env.example backend/.env
```

2. 生成并写入 `ENCRYPTION_KEY`：

```bash
docker run --rm python:3.11-alpine python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

把输出写入 `backend/.env`：

```bash
ENCRYPTION_KEY=<generated-value>
```

> `ENCRYPTION_KEY` 缺失会导致 `bootstrap` 在种子导入阶段失败。

## 启动命令

```bash
# 首次初始化（推荐）
./scripts/bootstrap.sh

# 开发模式
./scripts/bootstrap.sh --dev

# 日常启动
./scripts/start.sh

# 停止
./scripts/stop.sh
```

## 服务端口

- Frontend: `15173`
- Backend: `18080`
- MySQL: `13306`
- Redis: `16379`
- Elasticsearch: `19200`
- Chroma: `18000`

## 最小可用验证

```bash
curl -fsS http://localhost:18080/api/health
curl -fsS http://localhost:15173 >/dev/null
```

## 常见问题

### 1) `ENCRYPTION_KEY` 缺失

现象：`bootstrap` 在 `init_release_seed.py` 失败。  
处理：按“前置准备”补齐 `backend/.env` 的 `ENCRYPTION_KEY` 后重试。

### 2) 端口冲突

现象：脚本提示某端口被占用并中止。  
处理：停止占用端口的进程，或修改 `docker-compose.yml` 的映射端口。

### 3) Docker Compose 不可用

现象：脚本提示未检测到 `docker compose`。  
处理：升级 Docker Desktop / Docker Engine 并确认 `docker compose version` 可执行。
