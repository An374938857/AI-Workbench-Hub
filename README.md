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

## 作者

- 千成文

## 协议

- MIT License（见 [LICENSE](./LICENSE)）

## 发布说明

- 开源基线版本

## 主要特性

- 全量 Docker 化运行（`frontend`、`backend`、`mysql`、`redis`、`elasticsearch`、`chroma`）
- 首次初始化单入口脚本
- 支持语义化版本发布流程

## 快速开始（从 clone 到运行）

### 1. 克隆仓库

```bash
git clone <your-repo-url>
cd AI-Workbench-Hub
```

### 2. 检查前置条件

- 已安装并启动 Docker Desktop / Docker Engine
- 以下端口未被占用：
  - `15173`（前端）
  - `18080`（后端）
  - `13306`（MySQL）
  - `16379`（Redis）
  - `19200`（Elasticsearch）
  - `18000`（Chroma）

### 3. 首次初始化并启动

```bash
./scripts/bootstrap.sh
```

`bootstrap.sh` 会自动完成：

1. 启动全部容器
2. 等待服务健康检查通过
3. 执行数据库迁移（`alembic upgrade head`）
4. 初始化 Elasticsearch 索引
5. 创建默认管理员账号
6. 启动后端与前端服务

### 4. 访问系统

- 前端：`http://localhost:15173`
- 后端健康检查：`http://localhost:18080/api/health`

默认管理员账号：

- username: `admin`
- password: `admin123`

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
# 启动 / 重建
./scripts/start.sh

# 重启
./scripts/restart.sh

# 停止
./scripts/stop.sh

# 仅重启后端
./scripts/restart-backend.sh
```

## 技术架构

- Frontend: Vue 3 + Vite
- Backend: Python 3.13 + FastAPI + SQLAlchemy + Alembic
- Storage: MySQL 8.0 + Redis 7 + Elasticsearch 8 + Chroma

## 配置

使用 `backend/.env.example` 作为模板。

关键环境变量：

- `DATABASE_URL`
- `REDIS_URL`
- `ELASTICSEARCH_URL`
- `CHROMA_URL`
- `JWT_SECRET_KEY`

## 数据库迁移

- 当前基线迁移文件：`backend/migrations/versions/001_baseline.py`
- 后续版本仅新增增量 Alembic 迁移，不修改基线

## 项目约束

- 仓库中不应包含任何个人业务数据
- 运行态不内置 MCP 配置
- 发布流程遵循 SemVer + Changelog 规范

## 相关文档

- [CONTRIBUTING.md](./CONTRIBUTING.md)
- [CHANGELOG.md](./CHANGELOG.md)
- [RELEASE.md](./RELEASE.md)
- [SECURITY.md](./SECURITY.md)
- [LICENSE](./LICENSE)
