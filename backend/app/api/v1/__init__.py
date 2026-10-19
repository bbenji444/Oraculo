"""Versión 1 de la API REST (``/api/v1``)."""

from fastapi import APIRouter

from app.api.v1.articles import router as articles_router
from app.api.v1.concepts import router as concepts_router
from app.api.v1.health import router as health_router
from app.api.v1.regions import router as regions_router
from app.api.v1.reports import router as reports_router
from app.api.v1.searches import router as searches_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(regions_router)
api_router.include_router(concepts_router)
api_router.include_router(searches_router)
api_router.include_router(articles_router)
api_router.include_router(reports_router)

# Descripción de cada grupo de rutas en la documentación (/api/v1/docs).
OPENAPI_TAGS = [
    {"name": "diagnóstico", "description": "Estado de la API, la base, Redis y el worker."},
    {"name": "regiones", "description": "Catálogo geográfico INEGI y países (§12)."},
    {"name": "conceptos", "description": "Temas que se buscan, con sus palabras clave (§7)."},
    {
        "name": "búsquedas",
        "description": (
            "Estimar, lanzar y seguir una búsqueda; sus notas y el mapa de calor (§9 y §13). "
            "Lanzar gasta créditos de SearchApi y tokens de la IA: estima primero."
        ),
    },
    {"name": "notas", "description": "Detalle de una nota. Nunca el texto completo (§8)."},
    {
        "name": "reportes",
        "description": (
            "Reporte de una búsqueda terminada en PDF o HTML y sus notas en CSV o GeoJSON "
            "(§15). La primera vez el reporte le pide un resumen a la IA (~0.001 USD)."
        ),
    },
]
