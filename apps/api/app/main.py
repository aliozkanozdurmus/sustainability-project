# Bu giris noktasi, API uygulamasini temel bagimliliklariyla birlikte ayaga kaldirir.

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.settings import settings
from app.runtime import bind_runtime_services, build_app_runtime_services, shutdown_app_runtime_services
from app.telemetry import setup_telemetry, shutdown_telemetry


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Veni AI API'si acilirken once paylasilan servisleri,
    # sonra telemetry katmanini ayaga kaldiriyoruz.
    runtime_services = build_app_runtime_services()
    bind_runtime_services(app, runtime_services)
    telemetry_runtime = setup_telemetry(app)
    app.state.telemetry = telemetry_runtime
    try:
        yield
    finally:
        # Kapanista ters sirayla inmek, ozellikle local dev ve test kosullarinda
        # acik baglanti / client sizmasini azaltir.
        shutdown_telemetry(getattr(app.state, "telemetry", None))
        await shutdown_app_runtime_services(getattr(app.state, "runtime_services", None))
        app.state.telemetry = None
        app.state.runtime_services = None


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.api_version,
        lifespan=lifespan,
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
