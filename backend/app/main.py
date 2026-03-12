import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import SessionLocal
from app.routers import auth, users, scene_tags, skills, conversations, files, models, search, commands, prompt, compression
from app.routers import admin_skills, admin_model_providers, admin_dashboard, admin_fallback, admin_embedding
from app.routers import tags, sort_preferences, admin_routing_rules, system_config, prompt_templates, reference
from app.routers import admin_audit
from app.routers import (
    admin_workflows,
    projects,
    requirements,
    workflow_instances,
    assets,
    workflow_definitions,
    sandbox_views,
)

logger = logging.getLogger(__name__)
settings = get_settings()

app = FastAPI(
    title="业财产品 AI 能力共享平台",
    version="1.0.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)

if settings.APP_ENV == "development":
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Content-Disposition", "X-Archive-Filename"],
    )

app.include_router(auth.router, prefix="/api/auth", tags=["认证"])
app.include_router(users.router, prefix="/api/users", tags=["用户管理"])
app.include_router(scene_tags.router, prefix="/api/scene-tags", tags=["场景标签"])
app.include_router(skills.router, prefix="/api/skills", tags=["能力广场"])
app.include_router(conversations.router, prefix="/api/conversations", tags=["对话"])
app.include_router(search.router, prefix="/api/search", tags=["搜索"])
app.include_router(commands.router, tags=["快捷指令"])
app.include_router(prompt.router, prefix="/api/prompt", tags=["提示词优化"])
app.include_router(compression.router, prefix="/api", tags=["上下文压缩"])
app.include_router(models.router, prefix="/api/models", tags=["模型"])
app.include_router(files.router, prefix="/api/files", tags=["文件"])
app.include_router(admin_skills.router, prefix="/api/admin/skills", tags=["Skill管理"])
app.include_router(admin_model_providers.router, prefix="/api/admin/model-providers", tags=["模型配置"])
app.include_router(admin_embedding.router, prefix="/api/admin/embedding", tags=["Embedding管理"])
app.include_router(admin_fallback.router, prefix="/api/admin/model-fallbacks", tags=["Fallback配置"])
app.include_router(admin_dashboard.router, prefix="/api/admin/dashboard", tags=["数据看板"])
app.include_router(tags.router, prefix="/api/tags", tags=["标签管理"])
app.include_router(sort_preferences.router, prefix="/api/sort-preferences", tags=["排序偏好"])
app.include_router(admin_routing_rules.router, prefix="/api/admin/routing-rules", tags=["路由规则管理"])
app.include_router(system_config.router, prefix="/api/admin", tags=["系统配置管理"])
app.include_router(prompt_templates.router, prefix="/api/prompt-templates", tags=["提示词模板管理"])
app.include_router(reference.router, prefix="/api/reference", tags=["引用治理"])
app.include_router(admin_audit.router, prefix="/api/admin/audit", tags=["对话审计"])
app.include_router(admin_workflows.router, prefix="/api/admin/workflows", tags=["流程编排"])
app.include_router(projects.router, prefix="/api/v1/projects", tags=["项目管理"])
app.include_router(requirements.router, prefix="/api/v1/requirements", tags=["需求池"])
app.include_router(workflow_instances.router, prefix="/api/v1/workflow-instances", tags=["流程实例"])
app.include_router(assets.router, prefix="/api/v1/assets", tags=["资料管理"])
app.include_router(workflow_definitions.router, prefix="/api/v1/workflow-definitions", tags=["流程定义"])
app.include_router(sandbox_views.router, prefix="/api/v1/sandbox-views", tags=["关联沙箱"])


@app.on_event("startup")
async def startup_event():
    from app.services.conversation_events import get_conversation_event_bus
    from app.services.embedding_rebuild_runtime import get_embedding_rebuild_runtime
    from app.services.skill_package_health import check_skill_package_paths

    db = SessionLocal()
    try:
        check_skill_package_paths(db)
    except Exception:
        logger.exception("Skill 包路径启动自检失败")
    finally:
        db.close()

    await get_conversation_event_bus().startup()
    await get_embedding_rebuild_runtime().startup_resume()


@app.on_event("shutdown")
async def shutdown_event():
    from app.services.conversation_events import get_conversation_event_bus
    await get_conversation_event_bus().shutdown()


@app.get("/api/health")
async def health_check():
    return {"status": "ok"}
