"""Versión 1 de la API REST (``/api/v1``)."""

from fastapi import APIRouter

from app.api.v1.health import router as health_router
from app.api.v1.regions import router as regions_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(regions_router)
