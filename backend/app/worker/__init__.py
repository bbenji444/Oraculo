"""Worker de Celery: ejecuta en segundo plano las tareas que encola la API.

Las tareas solo invocan casos de uso de ``app.application`` (ADR-0005).
"""
