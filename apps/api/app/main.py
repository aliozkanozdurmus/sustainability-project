# Bu giris noktasi, API uygulamasini temel bagimliliklariyla birlikte ayaga kaldirir.

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.settings import settings


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.api_version,
    )
    cors_origins = [item.strip() for item in settings.cors_allow_origins.split(",") if item.strip()]
    if cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    app.include_router(api_router, prefix=settings.api_prefix)
    return app


app = create_app()
