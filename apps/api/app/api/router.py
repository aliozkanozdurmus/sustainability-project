from fastapi import APIRouter

from app.api.routes.auth import router as auth_router
from app.api.routes.catalog import router as catalog_router
from app.api.routes.dashboard import router as dashboard_router
from app.api.routes.documents import router as documents_router
from app.api.routes.health import router as health_router
from app.api.routes.integrations import router as integrations_router
from app.api.routes.retrieval import router as retrieval_router
from app.api.routes.runs import router as runs_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(catalog_router)
api_router.include_router(dashboard_router)
api_router.include_router(documents_router)
api_router.include_router(retrieval_router)
api_router.include_router(integrations_router)
api_router.include_router(runs_router)
