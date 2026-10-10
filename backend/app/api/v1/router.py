from fastapi import APIRouter

from app.api.v1.assistant import router as assistant_router
from app.api.v1.auth import router as auth_router
from app.api.v1.dashboard import router as dashboard_router
from app.api.v1.documents import router as documents_router
from app.api.v1.embeddings import router as embeddings_router
from app.api.v1.health import router as health_router
from app.core.config import settings


api_v1_router = APIRouter(prefix=settings.api_v1_prefix)
api_v1_router.include_router(health_router)
api_v1_router.include_router(auth_router)
api_v1_router.include_router(documents_router)
api_v1_router.include_router(embeddings_router)
api_v1_router.include_router(assistant_router)
api_v1_router.include_router(dashboard_router)
