<p align="center">
  简体中文 | <a href="./README.en-US.md">English</a>
</p>

<p align="center">
  <img src="./assets/readme-banner.svg" alt="AI Workbench Hub Banner" width="100%" />
</p>

<p align="center">
  <img alt="License" src="https://img.shields.io/badge/License-MIT-14B8A6?style=for-the-badge&logo=opensourceinitiative&logoColor=ffffff" />
  <img alt="Runtime" src="https://img.shields.io/badge/Runtime-Dockerized-38BDF8?style=for-the-badge&logo=docker&logoColor=ffffff" />
  <img alt="Backend" src="https://img.shields.io/badge/Backend-FastAPI-22C55E?style=for-the-badge&logo=fastapi&logoColor=ffffff" />
  <img alt="Frontend" src="https://img.shields.io/badge/Frontend-Vue%203-34D399?style=for-the-badge&logo=vuedotjs&logoColor=ffffff" />
  <img alt="Database" src="https://img.shields.io/badge/Database-MySQL%208-F59E0B?style=for-the-badge&logo=mysql&logoColor=ffffff" />
</p>

# AI一站式工作台（AI Workbench Hub）

AI一站式工作台，一个主要面向项目经理、产品经理、研发人员及知识工作者的开源协作平台。它帮助你统一管理项目、需求、资料与对话内容，通过 Web 平台集中组织与分发信息，支持 Docker 本地部署与私有化运行，并可按需二次开发，打造贴合团队流程的工作中枢。

## 功能说明（快速入口）

> 首次使用建议先阅读功能说明文档：  
> **[V1.0.0 功能说明（含系统截图）](./docs/V1.0.0-功能说明.md)**

## 作者

- 千成文

## 协议

- MIT License（见 [LICENSE](./LICENSE)）

## 发布说明

- 开源基线版本

## 主要特性

- 全量 Docker 化运行（`frontend`、`backend`、`mysql`、`redis`、`elasticsearch`、`chroma`）
- 首次初始化单入口脚本
- 内置首装种子数据（通用工具 Skill、提示词模板、脱敏 MCP）
- 支持语义化版本发布流程
- 对话支持路由分叉与已发送消息重新编辑
- 项目、需求池、对话均支持文件沙箱能力

## 交互快捷能力（建议优先使用）

- `Command + K`（Windows/Linux 对应 `Ctrl + K`）：调出快捷键提示菜单
- `Command + F`（Windows/Linux 对应 `Ctrl + F`）：调出对话全局搜索
- 在输入框键入 `/`：唤起快捷指令面板（模型/模板/技能/MCP 等）

## 快速开始（从 clone 到运行）

### 官方支持矩阵

- Linux + Docker Engine + Docker Compose v2
- macOS + Docker Desktop + Docker Compose v2
- Windows 10/11 + Docker Desktop + Docker Compose v2（建议在 WSL2 / Git Bash 执行脚本）

### 1. 克隆仓库

```bash
git clone git@github.com:An374938857/AI-Workbench-Hub.git
cd AI-Workbench-Hub
```

### 2. 检查前置条件

- 已安装并启动 Docker Desktop / Docker Engine
- 已安装 Docker Compose v2（`docker compose version` 可用）
- 首次启动时脚本会自动创建 `backend/.env` 并自动写入 `ENCRYPTION_KEY`（无需手工修改）
- 若检测到占位值或非法 `ENCRYPTION_KEY`（如 `your-fernet-key-here`），脚本会自动替换为合法值
- 以下端口未被占用：
  - `15173`（前端）
  - `18080`（后端）
  - `13306`（MySQL）
  - `16379`（Redis）
  - `19200`（Elasticsearch）
  - `18000`（Chroma）

### 3. 首次初始化并启动（生产模式）

```bash
./scripts/bootstrap.sh
```

`bootstrap.sh` 会自动完成：

1. 启动全部容器
2. 等待服务健康检查通过
3. 首次自动构建 `backend/frontend` 镜像（含失败重试）
4. 执行数据库迁移（`alembic upgrade head`）
5. 初始化 Elasticsearch 索引
6. 创建默认管理员账号
7. 导入开源种子数据（幂等）
8. 启动后端与前端服务

### 4. 访问系统

- 前端：`http://localhost:15173`
- 后端健康检查：`http://localhost:18080/api/health`

默认管理员账号：

- username: `admin`
- password: `admin123`

### 4.1 最小可用安装验证（建议首次执行）

```bash
curl -fsS http://localhost:18080/api/health
curl -fsS http://localhost:15173 >/dev/null
```

两个命令都返回成功即表示“从 clone 到服务可访问”链路可用。

### 4.2 缺表故障快速排查（发消息 500）

若登录成功但“发送消息”报 500，可优先检查关键表是否缺失：

```bash
docker compose -f docker/docker-compose.yml -f docker/docker-compose.prod.yml \
  exec -T mysql mysql -uroot -ppassword -D ai_platform -e \
  "SELECT table_name FROM information_schema.tables \
   WHERE table_schema='ai_platform' \
     AND table_name IN ('conversation_compression_logs','custom_commands','model_fallback_configs','model_fallback_logs','model_comparisons');"
```

一键修复：

```bash
./scripts/bootstrap.sh --prod
```

说明：管理后台“模型连通性测试通过”仅代表模型 API 可达，不代表对话链路可用。对话链路还依赖数据库表与上下文压缩等流程。

如果遇到 `failed to fetch anonymous token ... EOF`，属于 Docker Hub 网络波动。脚本已自动重试；若仍失败，请先手工执行：

```bash
docker pull python:3.11-slim
```

### 5. 日常启动（非首次）

```bash
./scripts/start.sh
```

### 6. 开发模式（热更新）

```bash
# 首次开发初始化
./scripts/bootstrap.sh --dev

# 日常开发启动
./scripts/start.sh --dev
```

### 7. 显式重建镜像

```bash
# 启动时构建
./scripts/start.sh --build

# 强制重建（down + build + up）
./scripts/restart.sh --rebuild
```

## 从 V1.0.0 升级到 V1.0.1（无缝升级）

可以无缝升级。`V1.0.1` 的迁移与种子导入均为幂等设计，不会清空你已有业务数据。

推荐升级步骤：

```bash
# 1) 拉取代码与标签
git fetch --all --tags
git checkout V1.0.1

# 2) 可选：如果你希望 Aliyun Coding Plan 部署后立即可用，先配置密钥
export RELEASE_ALIYUN_CODING_PLAN_API_KEY='你的API Key'

# 3) 执行升级（会自动 migrate + 索引初始化 + 管理员检查 + 种子幂等导入）
./scripts/bootstrap.sh --build
```

如果你只想更新代码与镜像、不执行初始化链路，可用：

```bash
./scripts/restart.sh --build
```

## 管理后台（快速说明）

使用管理员账号登录后：

1. 点击右上角用户头像
2. 进入 **管理后台**
3. 你可以在管理后台中：
  - 配置模型服务商与模型路由规则
  - 管理技能（创建 / 编辑 / 启停）
  - 管理 MCP 相关能力与配置

## 日常运维命令

```bash
# 启动（默认生产模式）
./scripts/start.sh

# 开发模式启动
./scripts/start.sh --dev

# 重启
./scripts/restart.sh

# 开发模式重启
./scripts/restart.sh --dev

# 强制重建
./scripts/restart.sh --rebuild

# 停止
./scripts/stop.sh

# 停止开发模式
./scripts/stop.sh --dev

# 仅重启后端
./scripts/restart-backend.sh
```

## 技术架构

- Frontend: Vue 3 + Vite（开发模式）/ Nginx 静态托管（生产模式）
- Backend: Python 3.11 + FastAPI + SQLAlchemy + Alembic
- Storage: MySQL 8.0 + Redis 7 + Elasticsearch 8 + Chroma

## 配置

配置由启动脚本自动初始化（若缺失会创建 `backend/.env` 并补齐关键项），你也可以基于 `backend/.env.example` 自行覆盖。

镜像与包管理器加速（默认国内源）：

- Docker 镜像前缀默认使用 `docker.m.daocloud.io`
- Backend 构建默认使用 `APT_MIRROR=mirrors.aliyun.com`
- Backend 依赖默认使用 `PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple`
- Frontend 依赖默认使用 `NPM_REGISTRY=https://registry.npmmirror.com`

如需切回官方源，可在项目根目录创建 `.env`（参考 `.env.example`）并设置：

```bash
DOCKER_REGISTRY_MIRROR=docker.io
# 可按需叠加：
# APT_MIRROR=deb.debian.org
# PIP_INDEX_URL=https://pypi.org/simple
# PIP_TRUSTED_HOST=pypi.org
# NPM_REGISTRY=https://registry.npmjs.org
```

关键环境变量：

- `DATABASE_URL`
- `REDIS_URL`
- `ELASTICSEARCH_URL`
- `CHROMA_URL`
- `JWT_SECRET_KEY`
- `ENCRYPTION_KEY`（必填；脚本在缺失时会自动生成并写入 `backend/.env`）
- `RELEASE_ALIYUN_CODING_PLAN_API_KEY`（可选，首次 `bootstrap` 时注入 Aliyun Coding Plan 密钥）

### 模型服务商配置说明

- 平台支持配置任意兼容以下协议的模型服务商：
  - `openai_compatible`
  - `anthropic`
- 开源版默认会初始化 `Aliyun Coding Plan` 服务商与模型清单。
- 若希望部署后直接可用，请在启动前配置：

```bash
export RELEASE_ALIYUN_CODING_PLAN_API_KEY='你的API Key'
./scripts/bootstrap.sh --build
```

- 除默认服务商外，你也可以在管理后台继续新增其他兼容 OpenAI 或 Anthropic 协议的服务商与模型。

## 数据库迁移

- 当前基线迁移文件：`backend/migrations/versions/001_baseline.py`
- 后续版本仅新增增量 Alembic 迁移，不修改基线

## 项目约束

- 仓库中不应包含任何个人业务数据
- 开源默认种子仅包含脱敏 MCP 配置（`Authorization=<REQUIRED>`，需自行补充）
- 发布流程遵循 SemVer + Changelog 规范

## 相关文档

- [CONTRIBUTING.md](./CONTRIBUTING.md)
- [CHANGELOG.md](./CHANGELOG.md)
- [RELEASE.md](./RELEASE.md)
- [SECURITY.md](./SECURITY.md)
- [LICENSE](./LICENSE)

## README 说明

- `README.md`：中文默认展示（GitHub 首页）
- `README.en-US.md`：英文版
