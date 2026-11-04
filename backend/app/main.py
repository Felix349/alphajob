"""FastAPI 应用入口。

开发启动：uv run uvicorn app.main:app --reload
接口文档：http://localhost:8000/api/docs
"""

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, health
from app.core.config import get_settings


def custom_generate_unique_id(route) -> str:
    # 让 OpenAPI 里的 operationId 简洁可读（如 auth-login），前端生成的类型名也更干净
    return f"{route.tags[0]}-{route.name}" if route.tags else route.name


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="AlphaJob API",
        version="0.1.0",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        generate_unique_id_function=custom_generate_unique_id,
    )

    # 正常情况下前端经 Next.js 同源代理访问，用不到 CORS；保留给直接调试后端的场景
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    api = APIRouter(prefix="/api")
    api.include_router(health.router)
    api.include_router(auth.router)
    app.include_router(api)
    return app


app = create_app()
