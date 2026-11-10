"""Versión 1 de la API REST (``/api/v1``)."""

from fastapi import APIRouter, Depends

from app.api.auth import require_superuser_user, superuser_for_changes
from app.api.v1.access import router as access_router
from app.api.v1.app_config import router as app_config_router
from app.api.v1.articles import router as articles_router
from app.api.v1.auth import router as auth_router
from app.api.v1.case_graph import router as case_graph_router
from app.api.v1.cases import router as cases_router
from app.api.v1.categories import router as categories_router
from app.api.v1.concepts import router as concepts_router
from app.api.v1.deliveries import router as deliveries_router
from app.api.v1.entities import router as entities_router
from app.api.v1.health import router as health_router
from app.api.v1.regions import router as regions_router
from app.api.v1.relationships import router as relationships_router
from app.api.v1.reports import router as reports_router
from app.api.v1.resolution import router as resolution_router
from app.api.v1.schedule import router as schedule_router
from app.api.v1.searches import router as searches_router
from app.api.v1.sources import router as sources_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(app_config_router)
api_router.include_router(auth_router)
api_router.include_router(access_router)
api_router.include_router(regions_router)
# Etapa 1 (ADR-0042): todos leen; solo el superusuario cambia.
_CHANGES_BY_SUPERUSER = [Depends(superuser_for_changes)]
_SUPERUSER_ONLY = [Depends(require_superuser_user)]
api_router.include_router(concepts_router, dependencies=_CHANGES_BY_SUPERUSER)
api_router.include_router(searches_router)
api_router.include_router(sources_router)
api_router.include_router(categories_router, dependencies=_CHANGES_BY_SUPERUSER)
api_router.include_router(articles_router)
api_router.include_router(reports_router)
# Antes que cases_router: "/cases/map" no debe leerse como "/cases/{id}".
api_router.include_router(case_graph_router)
api_router.include_router(cases_router)
api_router.include_router(entities_router)
api_router.include_router(resolution_router)
api_router.include_router(relationships_router)
# Envíos y horario: del superusuario hasta la etapa 3 (envíos por persona).
api_router.include_router(deliveries_router, dependencies=_SUPERUSER_ONLY)
api_router.include_router(schedule_router, dependencies=_SUPERUSER_ONLY)

# Descripción de cada grupo de rutas en la documentación (/api/v1/docs).
OPENAPI_TAGS = [
    {"name": "diagnóstico", "description": "Estado de la API, la base, Redis y el worker."},
    {
        "name": "acceso",
        "description": (
            "Entrar con una llave orc_live_… (cookie de sesión) o mandarla en "
            "Authorization: Bearer; personas y llaves, solo superusuarios (ADR-0042)."
        ),
    },
    {"name": "regiones", "description": "Catálogo geográfico INEGI y países (§12)."},
    {"name": "conceptos", "description": "Temas que se buscan, con sus palabras clave (§7)."},
    {
        "name": "búsquedas",
        "description": (
            "Estimar, lanzar y seguir una búsqueda; sus notas y el mapa de calor (§9 y §13). "
            "Lanzar gasta créditos de SearchApi y tokens de la IA: estima primero."
        ),
    },
    {
        "name": "fuentes",
        "description": (
            "Fuentes que el analista enciende o apaga en la búsqueda manual (F12.2, "
            "ADR-0027): cuáles hay, cuáles cuestan créditos y cuáles están configuradas."
        ),
    },
    {
        "name": "envíos",
        "description": (
            "Qué se manda, a quién y por qué canal (F12.11, ADR-0039): cuentas de correo "
            "vía Composio, destinatarios, cómo se manda cada fuente e historial auditable."
        ),
    },
    {
        "name": "categorías",
        "description": (
            "Catálogo con que la IA clasifica cada nota por delito (F12.4, ADR-0029), "
            "con «Otros» para lo que no encaje."
        ),
    },
    {"name": "notas", "description": "Detalle de una nota. Nunca el texto completo (§8)."},
    {
        "name": "casos",
        "description": (
            "Casos de investigación (Fase 9): crear, listar, abrir y editar. Cada persona ve "
            "solo los casos de los que es miembro, y abrir un caso queda en la bitácora."
        ),
    },
    {
        "name": "entidades",
        "description": (
            "Entidades que la IA propone de las notas de un caso (Fase 9.4): revisarlas, "
            "confirmarlas con su estatus legal o descartarlas; unir las que son la misma y "
            "separarlas (9.5). Analizar gasta tokens de la IA."
        ),
    },
    {
        "name": "vínculos",
        "description": (
            "Vínculos entre entidades confirmadas de un caso (Fase 9.5): los que sugiere la "
            "coocurrencia en las notas y los que dibuja el analista. Solo una persona confirma."
        ),
    },
    {
        "name": "reportes",
        "description": (
            "Reporte de una búsqueda terminada en PDF o HTML y sus notas en CSV o GeoJSON "
            "(§15). La primera vez el reporte le pide un resumen a la IA (~0.001 USD)."
        ),
    },
    {
        "name": "horario",
        "description": (
            "Horario único de las corridas automáticas (ADR-0040): un solo horario para todos, "
            "lo maneja el administrador. Cada hora es una corrida nueva con IA (máx. 8 al día)."
        ),
    },
]
