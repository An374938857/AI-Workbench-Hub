<p align="center">
  <a href="./README.md">简体中文</a> | English
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
# AI Workbench Hub

AI Workbench Hub is an open-source collaboration platform primarily designed for project managers, product managers, engineers, and knowledge workers. It helps teams centrally manage projects, requirements, materials, and conversations through a unified web workspace, supports local Docker deployment and private self-hosting, and enables on-demand secondary development to build a workflow hub that fits real team processes.

## Author

- 千成文

## License

- MIT License (see [LICENSE](./LICENSE))

## Release

- Open-source baseline release

## Features

- Fully Dockerized runtime (`frontend`, `backend`, `mysql`, `redis`, `elasticsearch`, `chroma`)
- Single bootstrap entry for first-time setup
- SemVer-ready release process

## Quick Start (From Clone to Running)

### 1. Clone repository

```bash
git clone <your-repo-url>
cd AI-Workbench-Hub
```

### 2. Check prerequisites

- Docker Desktop / Docker Engine is installed and running
- The following host ports are available:
  - `15173` (frontend)
  - `18080` (backend)
  - `13306` (mysql)
  - `16379` (redis)
  - `19200` (elasticsearch)
  - `18000` (chroma)

### 3. First-time initialization and startup

```bash
./scripts/bootstrap.sh
```

`bootstrap.sh` will automatically:

1. Start all required containers
2. Wait for service health checks
3. Run database migration (`alembic upgrade head`)
4. Initialize Elasticsearch indices
5. Create default admin account
6. Start backend and frontend

### 4. Access application

- Frontend: `http://localhost:15173`
- Backend health: `http://localhost:18080/api/health`

Default admin credentials:

- username: `admin`
- password: `admin123`

## Admin Console (Quick Guide)

After logging in with the admin account:

1. Click the user avatar at the top-right corner
2. Open the **Admin Console**
3. In Admin Console, you can:
   - Configure model providers and model routing rules
   - Manage skills (create/edit/enable/disable)
   - Manage MCP-related capabilities and settings

## Daily Operations

```bash
# Start / rebuild
./scripts/start.sh

# Restart
./scripts/restart.sh

# Stop
./scripts/stop.sh

# Restart backend only
./scripts/restart-backend.sh
```

## Architecture

- Frontend: Vue 3 + Vite
- Backend: Python 3.13 + FastAPI + SQLAlchemy + Alembic
- Storage: MySQL 8.0 + Redis 7 + Elasticsearch 8 + Chroma

## Configuration

Use `backend/.env.example` as template.

Important runtime variables:

- `DATABASE_URL`
- `REDIS_URL`
- `ELASTICSEARCH_URL`
- `CHROMA_URL`
- `JWT_SECRET_KEY`

## Migrations

- Baseline migration starts at `backend/migrations/versions/001_baseline.py`
- For future releases, add incremental Alembic revisions only

## Project Policies

- No personal business data in repository
- No built-in MCP configuration in runtime
- Release process follows SemVer and changelog discipline

## Documentation

- [CONTRIBUTING.md](./CONTRIBUTING.md)
- [CHANGELOG.md](./CHANGELOG.md)
- [RELEASE.md](./RELEASE.md)
- [SECURITY.md](./SECURITY.md)
- [LICENSE](./LICENSE)
