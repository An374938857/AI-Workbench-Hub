# Docker 部署说明

## 当前运行模式（事实）

**后端本地运行，其他服务在 Docker 中运行。**

- Docker 容器：`redis`、`mysql`、`elasticsearch`、`chroma`、`frontend`
- 本地进程：`backend`（FastAPI）

> 说明：Backend 需要通过 MCP stdio 子进程访问公司内网服务，当前采用宿主机本地运行模式。

## 目录约定

所有 Docker 配置统一放在仓库的 `docker/` 目录：

- `docker/docker-compose.yml`
- `docker/Dockerfile.frontend`
- `docker/Dockerfile.elasticsearch`
- `docker/DOCKER_DEPLOYMENT.md`

## 服务架构

```
┌─────────────────────────────────────────────────────────┐
│                    Docker Network                        │
│                                                          │
│  ┌──────────┐    ┌──────────────────┐                  │
│  │ Frontend │───▶│ MySQL            │                  │
│  │  :5173   │    │  :3306           │                  │
│  └──────────┘    └──────────────────┘                  │
│        │                                                 │
│        ├──────────▶┌──────────────────┐                 │
│        │           │ Redis            │                 │
│        │           │  :6379           │                 │
│        │           └──────────────────┘                 │
│        │                                                 │
│        ├──────────▶┌──────────────────┐                 │
│        │           │ ElasticSearch    │                 │
│        │           │  :9200 (IK插件)  │                 │
│        │           └──────────────────┘                 │
│        │                                                 │
│        └──────────▶┌──────────────────┐                 │
│                    │ Chroma           │                 │
│                    │  :8000           │                 │
│                    └──────────────────┘                 │
└─────────────────────────────────────────────────────────┘
         ▲               ▲               ▲
         │               │               │
  localhost:5173   localhost:3306  localhost:9200/8000
         │
┌─────────────────────────────────────────────────────────┐
│                 本地 Backend (:8080)                   │
│  访问 Redis/MySQL/ES/Chroma 的 localhost 暴露端口      │
└─────────────────────────────────────────────────────────┘
```

## 服务配置

### Frontend

- 镜像：基于 `node:18-alpine` 自定义构建
- Dockerfile：`docker/Dockerfile.frontend`
- Compose：`docker/docker-compose.yml`
- 热更新：挂载 `../frontend:/app`

### Backend（本地）

- 运行方式：`./scripts/start.sh` 启动本地 uvicorn
- 端口：`8080`
- 依赖服务：Redis、MySQL、ElasticSearch、Chroma（均由 Docker 提供）
- 环境变量示例：
  - `DATABASE_URL=mysql+pymysql://root:password@localhost:3306/ai_platform`
  - `REDIS_URL=redis://localhost:6379/0`
  - `ELASTICSEARCH_URL=http://localhost:9200`
  - `CHROMA_URL=http://localhost:8000`

### ElasticSearch

- 镜像：基于 `elasticsearch:8.11.0` + IK 分词器
- Dockerfile：`docker/Dockerfile.elasticsearch`
- 配置：单节点模式，禁用安全认证

### MySQL

- 镜像：`mysql:8.0`
- 数据持久化：`mysql_data` volume
- 字符集：`utf8mb4`

### Chroma

- 镜像：`chromadb/chroma:0.5.23`
- 数据持久化：`chroma_data` volume

## 常用命令

```bash
# 启动 Docker 基础设施（Redis/MySQL/ES/Chroma/Frontend）
docker compose -f docker/docker-compose.yml up -d

# 重建并启动前端
docker compose -f docker/docker-compose.yml up -d --build frontend

# 查看容器状态
docker compose -f docker/docker-compose.yml ps

# 查看某个服务日志
docker compose -f docker/docker-compose.yml logs -f mysql
```

## 常见问题

### Q: 前端搜索没有结果？

A: 检查：
1. ES 容器正常运行：`docker compose -f docker/docker-compose.yml ps elasticsearch`
2. IK 插件已安装：`curl http://localhost:9200/_cat/plugins`
3. 索引已创建（在本地 Backend venv 中执行）：`python backend/scripts/init_es_index.py`
4. 数据已索引（在本地 Backend venv 中执行）：`python backend/scripts/reindex_from_mysql.py`

### Q: Backend 启动失败？

A: 检查：
1. 基础设施是否就绪：`docker compose -f docker/docker-compose.yml ps`
2. Backend 日志：`tail -f logs/backend.log`
3. 本地端口冲突：`lsof -i :8080`

### Q: 容器启动失败？

A: 排查步骤：
1. 查看日志：`docker compose -f docker/docker-compose.yml logs <service>`
2. 检查端口占用：`lsof -i :5173` / `lsof -i :3306` / `lsof -i :9200`
3. 清理重建：`docker compose -f docker/docker-compose.yml down -v && docker compose -f docker/docker-compose.yml up -d --build`

## 维护命令

```bash
# 完全清理（删除数据卷）
docker compose -f docker/docker-compose.yml down -v

# 重建所有镜像
docker compose -f docker/docker-compose.yml build --no-cache

# 查看资源占用
docker stats

# 导出数据库
docker compose -f docker/docker-compose.yml exec -T mysql mysqldump -uroot -ppassword ai_platform > backup.sql

# 导入数据库
docker compose -f docker/docker-compose.yml exec -T mysql mysql -uroot -ppassword ai_platform < backup.sql
```
