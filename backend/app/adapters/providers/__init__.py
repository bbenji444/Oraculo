"""Adaptadores de proveedores de noticias (SearchApi, GDELT, Google News RSS).

Cada uno cumple ``NewsProviderPort`` y traduce la respuesta de su proveedor
al formato común ``RawArticle``. Todos usan el cliente de ``http.py``.
"""
