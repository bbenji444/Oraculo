"""Backend del monitor de noticias geolocalizadas (API FastAPI y worker Celery).

La organización sigue la arquitectura hexagonal de ADR-0001: ``domain`` y
``application`` forman el núcleo; ``adapters``, ``api`` y ``worker`` lo
conectan con el mundo exterior.
"""
