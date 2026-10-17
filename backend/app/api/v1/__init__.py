"""Versión 1 de la API REST (``/api/v1``)."""

from fastapi import APIRouter

from app.api.v1.concepts import router as concepts_router
from app.api.v1.health import router as health_router
from app.api.v1.local_index import router as local_index_router
from app.api.v1.regions import router as regions_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(regions_router)
api_router.include_router(concepts_router)
api_router.include_router(local_index_router)
