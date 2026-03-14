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

无需手工编辑 `.env`。`bootstrap/start` 脚本会自动：

1. 若 `backend/.env` 不存在，则基于 `backend/.env.example` 自动创建
2. 若 `ENCRYPTION_KEY` 缺失、是占位值、或格式非法，则自动生成并写入 `backend/.env`

> `ENCRYPTION_KEY` 用于模型密钥和 MCP 配置加密，脚本会在启动前自动保证其可用。

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

现象：启动日志提示自动生成失败（通常是 Docker 镜像拉取失败或网络问题）。  
处理：确认 Docker 网络可用后重试 `./scripts/bootstrap.sh`。

### 2) 端口冲突

现象：脚本提示某端口被占用并中止。  
处理：停止占用端口的进程，或修改 `docker-compose.yml` 的映射端口。

### 3) Docker Compose 不可用

现象：脚本提示未检测到 `docker compose`。  
处理：升级 Docker Desktop / Docker Engine 并确认 `docker compose version` 可执行。

### 4) 登录正常但发消息 500（缺表）

现象：管理后台模型连通性测试通过，但对话发送时报 500。  
说明：模型连通性测试只覆盖模型 API，不覆盖对话链路依赖的数据库表。

快速验证：

```bash
docker compose -f docker/docker-compose.yml -f docker/docker-compose.prod.yml \
  exec -T mysql mysql -uroot -ppassword -D ai_platform -e \
  "SELECT table_name FROM information_schema.tables \
   WHERE table_schema='ai_platform' \
     AND table_name IN ('conversation_compression_logs','custom_commands','model_fallback_configs','model_fallback_logs','model_comparisons');"
```

修复命令：

```bash
./scripts/bootstrap.sh --prod
```
