"""Registra filtros customizados no Jinja2 — importar no app.py se necessário"""
import json

def register_filters(app):
    @app.template_filter('fromjson')
    def fromjson_filter(value):
        if isinstance(value, str):
            try:
                return json.loads(value)
            except:
                return []
        return value or []
