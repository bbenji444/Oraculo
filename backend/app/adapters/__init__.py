"""Adaptadores: implementaciones de los puertos con tecnología concreta.

Aquí viven SQLAlchemy, Redis, Celery, los clientes HTTP de los proveedores y
el LLM. Traducen errores externos a excepciones o resultados del dominio y no
contienen reglas de negocio (ADR-0001).
"""
